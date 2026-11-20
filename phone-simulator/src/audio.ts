const TARGET_SAMPLE_RATE = 16000;
const FRAME_DURATION_MS = 20;
const SAMPLES_PER_FRAME = Math.floor(
  (TARGET_SAMPLE_RATE * FRAME_DURATION_MS) / 1000,
);

export function floatToPcm16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const s = Math.max(-1, Math.min(1, input[i]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return output;
}

export function downsample(
  buffer: Float32Array,
  inputRate: number,
  outputRate: number,
): Int16Array {
  if (inputRate === outputRate) return floatToPcm16(buffer);
  const ratio = inputRate / outputRate;
  const newLength = Math.floor(buffer.length / ratio);
  const result = new Int16Array(newLength);
  for (let i = 0; i < newLength; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(buffer.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += buffer[j];
    const avg = end > start ? sum / (end - start) : 0;
    const clamped = Math.max(-1, Math.min(1, avg));
    result[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return result;
}

export function pcm16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

export function base64ToBlobUrl(base64: string, mime: string): string {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes], { type: mime }));
}

export class CallAudioEngine {
  private micStream: MediaStream | null = null;
  private audioCtx: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private analyser: AnalyserNode | null = null;
  private analyserData: Uint8Array | null = null;
  private pendingPcm: Int16Array = new Int16Array(0);
  private playbackQueue: string[] = [];
  private currentAudio: HTMLAudioElement | null = null;
  private currentAudioUrl: string | null = null;
  private agentSpeaking = false;
  private muted = false;
  public onLocalBargeIn: (() => void) | null = null;

  async startMic(onPcmChunk: (chunk: Int16Array) => void): Promise<void> {
    if (this.micStream) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Microphone capture is not supported in this browser.");
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    this.micStream = stream;

    const Context = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Context();
    this.audioCtx = ctx;
    if (ctx.state === "suspended") await ctx.resume();

    const source = ctx.createMediaStreamSource(stream);
    this.source = source;

    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    this.analyser = analyser;
    this.analyserData = new Uint8Array(analyser.fftSize);

    const processor = ctx.createScriptProcessor(2048, 1, 1);
    this.processor = processor;
    processor.onaudioprocess = (event) => {
      const channel = event.inputBuffer.getChannelData(0);
      const samples = downsample(channel, ctx.sampleRate, TARGET_SAMPLE_RATE);
      if (this.muted) {
        samples.fill(0);
      }
      this.accumulatePcm(samples, onPcmChunk);
    };

    // Route processor through silent gain node so mic does NOT feedback into user speakers
    const silentGain = ctx.createGain();
    silentGain.gain.value = 0;
    source.connect(processor);
    processor.connect(silentGain);
    silentGain.connect(ctx.destination);
  }

  private accumulatePcm(
    samples: Int16Array,
    onChunk: (chunk: Int16Array) => void,
  ): void {
    const merged = new Int16Array(this.pendingPcm.length + samples.length);
    merged.set(this.pendingPcm, 0);
    merged.set(samples, this.pendingPcm.length);
    this.pendingPcm = merged;

    while (this.pendingPcm.length >= SAMPLES_PER_FRAME) {
      const frame = this.pendingPcm.slice(0, SAMPLES_PER_FRAME);
      this.pendingPcm = this.pendingPcm.slice(SAMPLES_PER_FRAME);
      onChunk(frame);
    }
  }

  setMuted(value: boolean): void {
    this.muted = value;
  }

  enqueueWav(base64Wav: string): void {
    const url = base64ToBlobUrl(base64Wav, "audio/wav");
    this.playbackQueue.push(url);
    this.agentSpeaking = true;
    this.playNext();
  }

  private playNext(): void {
    if (this.currentAudio || this.playbackQueue.length === 0) return;
    const url = this.playbackQueue.shift()!;
    const audio = new Audio(url);
    this.currentAudio = audio;
    this.currentAudioUrl = url;

    const finalize = () => {
      URL.revokeObjectURL(url);
      if (this.currentAudioUrl === url) this.currentAudioUrl = null;
      if (this.currentAudio === audio) this.currentAudio = null;
      if (this.playbackQueue.length === 0) {
        this.agentSpeaking = false;
      }
      this.playNext();
    };

    audio.onended = finalize;
    audio.onerror = finalize;
    audio.play().catch(finalize);
  }

  stopPlayback(): void {
    this.playbackQueue.forEach((u) => URL.revokeObjectURL(u));
    this.playbackQueue = [];
    if (this.currentAudio) {
      try {
        this.currentAudio.pause();
      } catch {
        // Ignored
      }
      this.currentAudio = null;
    }
    if (this.currentAudioUrl) {
      URL.revokeObjectURL(this.currentAudioUrl);
      this.currentAudioUrl = null;
    }
    this.agentSpeaking = false;
  }

  getMicLevels(count: number): number[] {
    const levels = new Array<number>(count).fill(0);
    if (!this.analyser || !this.analyserData || this.muted) return levels;
    this.analyser.getByteTimeDomainData(this.analyserData as unknown as Uint8Array<ArrayBuffer>);
    const step = Math.max(1, Math.floor(this.analyserData.length / count));
    for (let i = 0; i < count; i += 1) {
      let peak = 0;
      for (let j = 0; j < step; j += 1) {
        const val = Math.abs(this.analyserData[i * step + j] - 128) / 128;
        if (val > peak) peak = val;
      }
      levels[i] = Math.min(1, peak * 2.8);
    }
    return levels;
  }

  getAgentLevels(count: number): number[] {
    const levels = new Array<number>(count).fill(0);
    if (!this.agentSpeaking) return levels;
    const t = performance.now() / 150;
    for (let i = 0; i < count; i += 1) {
      const pulse =
        Math.abs(Math.sin(t + i * 0.5)) * 0.7 +
        Math.abs(Math.sin(t * 0.7 + i * 0.2)) * 0.3;
      levels[i] = 0.15 + pulse * 0.85;
    }
    return levels;
  }

  setAgentSpeaking(value: boolean): void {
    this.agentSpeaking = value;
  }

  isAgentSpeaking(): boolean {
    return this.agentSpeaking;
  }

  stop(): void {
    this.stopPlayback();
    if (this.processor) {
      this.processor.onaudioprocess = null;
      try {
        this.processor.disconnect();
      } catch {
        // Ignored
      }
      this.processor = null;
    }
    if (this.source) {
      try {
        this.source.disconnect();
      } catch {
        // Ignored
      }
      this.source = null;
    }
    if (this.micStream) {
      this.micStream.getTracks().forEach((track) => track.stop());
      this.micStream = null;
    }
    if (this.audioCtx) {
      try {
        void this.audioCtx.close();
      } catch {
        // Ignored
      }
      this.audioCtx = null;
    }
    this.analyser = null;
    this.analyserData = null;
    this.pendingPcm = new Int16Array(0);
  }
}
