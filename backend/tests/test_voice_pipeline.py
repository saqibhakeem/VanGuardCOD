"""Phase 3 verification: chunker, WAV framing, RMS VAD, and Groq audio wrappers."""

from __future__ import annotations

import struct

import pytest

from app.voice.audio import pcm16_duration_ms, pcm16_to_wav, wav_frame_count
from app.voice.stt_groq import GroqSpeechToText, MockTranscriptionClient
from app.voice.tts_provider import (
    GroqTextToSpeech,
    MockSpeechClient,
    split_into_orpheus_chunks,
    wav_chunk_duration_ms,
)
from app.voice.vad import RmsBargeInDetector, rms_energy


def pcm_frame(amplitude: int, frames: int = 320) -> bytes:
    return struct.pack(f"<{frames}h", *([amplitude] * frames))


def test_chunker_respects_orpheus_limit_on_sentences_and_clauses():
    text = (
        "This first sentence is short. "
        "This second sentence is deliberately written to be much longer than the strict "
        "Orpheus limit because it keeps adding clauses, details, and extra words, "
        "which forces the splitter to break it on clause and word boundaries safely."
    )
    chunks = split_into_orpheus_chunks(text)
    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert any("Orpheus limit" in chunk for chunk in chunks)


def test_chunker_hard_splits_pathological_single_word():
    chunks = split_into_orpheus_chunks("x" * 450)
    assert [len(chunk) for chunk in chunks] == [200, 200, 50]


def test_chunker_handles_empty_and_rejects_bad_limits():
    assert split_into_orpheus_chunks("") == []
    assert split_into_orpheus_chunks("   \n\t ") == []
    with pytest.raises(ValueError):
        split_into_orpheus_chunks("hello", max_len=0)


def test_pcm16_wav_framing_is_valid_and_timed():
    pcm = pcm_frame(1200)
    wav = pcm16_to_wav(pcm, sample_rate=16000)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wav_frame_count(wav) == 320
    assert pcm16_duration_ms(pcm, sample_rate=16000) == 20.0


def test_rms_energy_matches_amplitudes():
    assert rms_energy(pcm_frame(0)) == 0.0
    assert rms_energy(pcm_frame(8000)) == pytest.approx(8000.0)
    assert rms_energy(b"") == 0.0


def test_barge_in_requires_three_speech_frames_while_agent_speaks():
    detector = RmsBargeInDetector()
    first = detector.process_frame(pcm_frame(6000), agent_speaking=True)
    second = detector.process_frame(pcm_frame(6000), agent_speaking=True)
    third = detector.process_frame(pcm_frame(6000), agent_speaking=True)
    assert first.barge_in is False
    assert second.barge_in is False
    assert third.barge_in is True
    assert third.is_speech is True


def test_no_barge_in_when_agent_is_silent():
    detector = RmsBargeInDetector()
    decisions = [
        detector.process_frame(pcm_frame(6000), agent_speaking=False)
        for _ in range(5)
    ]
    assert all(decision.barge_in is False for decision in decisions)


def test_utterance_finalizes_after_silence_window():
    detector = RmsBargeInDetector()
    detector.process_frame(pcm_frame(6000), agent_speaking=False)
    final = None
    for _ in range(23):
        final = detector.process_frame(pcm_frame(0), agent_speaking=False)
    assert final is not None
    assert final.speech_finalized is True
    assert len(final.buffered_pcm) == 640 * 24
    assert detector.process_frame(pcm_frame(0), agent_speaking=False).speech_finalized is False


def test_utterance_truncates_at_max_length():
    detector = RmsBargeInDetector(max_utterance_ms=40.0)
    first = detector.process_frame(pcm_frame(6000), agent_speaking=False)
    second = detector.process_frame(pcm_frame(6000), agent_speaking=False)
    assert first.speech_finalized is False
    assert second.speech_finalized is True
    assert second.truncated is True
    assert len(second.buffered_pcm) == 640 * 2
    assert detector.process_frame(pcm_frame(0), agent_speaking=False).speech_finalized is False


async def test_mock_stt_wraps_pcm_and_reports_latency():
    mock = MockTranscriptionClient(script=["Is the order confirmed?"])
    stt = GroqSpeechToText(client=mock)
    result = await stt.transcribe_pcm_buffer(pcm_frame(2000))

    assert result.text == "Is the order confirmed?"
    assert result.model == "whisper-large-v3-turbo"
    assert result.audio_ms == 20.0
    assert result.wav_bytes > 44
    assert result.latency_ms >= 0.0
    call = mock.calls[0]
    assert call["model"] == "whisper-large-v3-turbo"
    assert call["response_format"] == "json"
    assert call["language"] == "en"
    filename, payload, mime = call["file"]
    assert filename == "audio.wav"
    assert payload[:4] == b"RIFF"
    assert mime == "audio/wav"


async def test_empty_stt_buffer_returns_no_network_call():
    mock = MockTranscriptionClient()
    stt = GroqSpeechToText(client=mock)
    result = await stt.transcribe_pcm_buffer(b"")
    assert result.text == ""
    assert result.latency_ms == 0.0
    assert mock.calls == []


async def test_tts_synthesizes_each_chunk_within_limit():
    mock = MockSpeechClient()
    tts = GroqTextToSpeech(client=mock)
    text = (
        "Your order is confirmed for dispatch tomorrow afternoon. "
        "The rider will call you when he reaches the main market gate, "
        "so please keep the cash amount ready at that time."
    )
    chunks = await tts.synthesize_speech(text, voice="hannah")

    assert len(chunks) == len(split_into_orpheus_chunks(text))
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(len(chunk.text) <= 200 for chunk in chunks)
    assert all(chunk.wav_bytes[:4] == b"RIFF" for chunk in chunks)
    assert all(wav_chunk_duration_ms(chunk.wav_bytes) > 0 for chunk in chunks)
    assert all(len(call["input"]) <= 200 for call in mock.calls)
    assert all(call["voice"] == "hannah" for call in mock.calls)
    assert all(call["response_format"] == "wav" for call in mock.calls)


async def test_tts_stream_yields_chunks_in_order():
    tts = GroqTextToSpeech(client=MockSpeechClient())
    collected = [chunk async for chunk in tts.stream_speech("First sentence. Second sentence.")]
    assert [chunk.text for chunk in collected] == ["First sentence.", "Second sentence."]
    assert [chunk.index for chunk in collected] == [0, 1]
