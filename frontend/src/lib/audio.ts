const TARGET_RATE = 16000;
const FRAME_SAMPLES = 320;

function downsampleToPcm16(
  input: Float32Array,
  inputRate: number,
  muted: boolean,
): Int16Array {
  const ratio = inputRate / TARGET_RATE;
  const length = Math.floor(input.length / ratio);
  const output = new Int16Array(Math.max(0, length));
  if (muted) return output;
  for (let i = 0; i < output.length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += input[j];
    const sample = end > start ? sum / (end - start) : 0;
    const clamped = Math.max(-1, Math.min(1, sample));
    output[i] = Math.round(clamped * (clamped < 0 ? 0x8000 : 0x7fff));
  }
  return output;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x2000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return window.btoa(binary);
}

export function pcm16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  return bytesToBase64(bytes);
}

function base64ToArrayBuffer(value: string): ArrayBuffer {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function readLevels(
  analyser: AnalyserNode | null,
  data: Uint8Array<ArrayBuffer> | null,
  count: number,
): number[] {
  const levels = new Array<number>(count).fill(0);
  if (!analyser || !data) return levels;
  analyser.getByteTimeDomainData(data);
  const step = Math.max(1, Math.floor(data.length / count));
  for (let i = 0; i < count; i += 1) {
    let peak = 0;
    for (let j = 0; j < step; j += 1) {
      const index = i * step + j;
      if (index >= data.length) break;
      const value = Math.abs(data[index] - 128) / 128;
      if (value > peak) peak = value;
    }
    levels[i] = Math.min(1, peak * 2.8);
  }
  return levels;
}

export class CallAudio {
  private micContext: AudioContext | null = null;
  private micStream: MediaStream | null = null;
  private micSource: MediaStreamAudioSourceNode | null = null;
  private micProcessor: ScriptProcessorNode | null = null;
  private micAnalyser: AnalyserNode | null = null;
  private micBuffer: Uint8Array<ArrayBuffer> | null = null;

  private playbackContext: AudioContext | null = null;
  private playbackAnalyser: AnalyserNode | null = null;
  private playbackBuffer: Uint8Array<ArrayBuffer> | null = null;

  private queue: ArrayBuffer[] = [];
  private currentSource: AudioBufferSourceNode | null = null;
  private generation = 0;
  private draining = false;
  private muted = false;
  private pending = new Int16Array(0);
  private onFrame: ((pcm: Int16Array) => void) | null = null;

  async start(onFrame: (pcm: Int16Array) => void): Promise<void> {
    this.onFrame = onFrame;
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Microphone capture is unavailable in this browser.");
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

    const context = new AudioContext();
    this.micContext = context;
    await context.resume();

    const source = context.createMediaStreamSource(stream);
    this.micSource = source;

    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    this.micAnalyser = analyser;
    this.micBuffer = new Uint8Array(analyser.fftSize);
    source.connect(analyser);

    const processor = context.createScriptProcessor(2048, 1, 1);
    processor.onaudioprocess = (event) => {
      if (!this.onFrame) return;
      const pcm = downsampleToPcm16(
        event.inputBuffer.getChannelData(0),
        context.sampleRate,
        this.muted,
      );
      this.queueFrames(pcm);
    };
    source.connect(processor);
    processor.connect(context.destination);
    this.micProcessor = processor;

    this.ensurePlayback();
  }

  stop(): void {
    this.stopPlayback();
    this.onFrame = null;

    if (this.micProcessor) {
      this.micProcessor.onaudioprocess = null;
      try {
        this.micProcessor.disconnect();
      } catch {
        this.micProcessor = null;
      }
      this.micProcessor = null;
    }
    if (this.micSource) {
      try {
        this.micSource.disconnect();
      } catch {
        this.micSource = null;
      }
      this.micSource = null;
    }
    if (this.micStream) {
      this.micStream.getTracks().forEach((track) => track.stop());
      this.micStream = null;
    }
    if (this.micContext) {
      void this.micContext.close();
      this.micContext = null;
    }
    this.micAnalyser = null;
    this.micBuffer = null;

    if (this.playbackContext) {
      void this.playbackContext.close();
      this.playbackContext = null;
    }
    this.playbackAnalyser = null;
    this.playbackBuffer = null;
    this.pending = new Int16Array(0);
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
  }

  micLevels(count: number): number[] {
    return readLevels(this.micAnalyser, this.micBuffer, count);
  }

  agentLevels(count: number): number[] {
    return readLevels(this.playbackAnalyser, this.playbackBuffer, count);
  }

  isAgentActive(): boolean {
    return this.queue.length > 0 || this.currentSource !== null;
  }

  enqueueWav(base64: string): void {
    if (!base64) return;
    this.ensurePlayback();
    this.queue.push(base64ToArrayBuffer(base64));
    void this.drain();
  }

  stopPlayback(): void {
    this.generation += 1;
    this.queue = [];
    const source = this.currentSource;
    this.currentSource = null;
    if (source) {
      try {
        source.stop();
      } catch {
        return;
      }
    }
  }

  private ensurePlayback(): void {
    if (this.playbackContext && this.playbackContext.state !== "closed") {
      void this.playbackContext.resume();
      return;
    }
    const context = new AudioContext();
    this.playbackContext = context;
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    analyser.connect(context.destination);
    this.playbackAnalyser = analyser;
    this.playbackBuffer = new Uint8Array(analyser.fftSize);
    void context.resume();
  }

  private queueFrames(pcm: Int16Array): void {
    if (!pcm.length || !this.onFrame) return;
    const merged = new Int16Array(this.pending.length + pcm.length);
    merged.set(this.pending, 0);
    merged.set(pcm, this.pending.length);
    this.pending = merged;
    while (this.pending.length >= FRAME_SAMPLES) {
      const frame = this.pending.slice(0, FRAME_SAMPLES);
      this.pending = this.pending.slice(FRAME_SAMPLES);
      this.onFrame(frame);
    }
  }

  private async drain(): Promise<void> {
    if (this.draining) return;
    this.draining = true;
    try {
      while (this.queue.length) {
        const context = this.playbackContext;
        if (!context || context.state === "closed") return;
        const generation = this.generation;
        const payload = this.queue.shift();
        if (!payload) break;
        let decoded: AudioBuffer;
        try {
          decoded = await context.decodeAudioData(payload.slice(0));
        } catch {
          continue;
        }
        if (generation !== this.generation) continue;
        await this.playBuffer(decoded, generation);
      }
    } finally {
      this.draining = false;
      if (this.queue.length) void this.drain();
    }
  }

  private playBuffer(buffer: AudioBuffer, generation: number): Promise<void> {
    const context = this.playbackContext;
    const analyser = this.playbackAnalyser;
    if (!context || !analyser || generation !== this.generation) {
      return Promise.resolve();
    }
    return new Promise<void>((resolve) => {
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(analyser);
      this.currentSource = source;
      source.onended = () => {
        if (this.currentSource === source) this.currentSource = null;
        resolve();
      };
      source.start();
    });
  }
}
