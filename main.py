from ollama import chat
from piper.voice import PiperVoice
from faster_whisper import WhisperModel
import pyaudio
import webrtcvad
import numpy as np
import subprocess
import time
import re
import os
# Suppress ALSA junk
os.environ['PYTHONWARNINGS'] = 'ignore'
devnull = os.open(os.devnull, os.O_WRONLY)
old_stderr = os.dup(2)
os.dup2(devnull, 2)

pa    = pyaudio.PyAudio()
audio = pyaudio.PyAudio()

os.dup2(old_stderr, 2)  # restore stderr
os.close(devnull)
os.close(old_stderr)

# ── Config ────────────────────────────────────────────────────────────────────
WAKE_WORD          = "fish on the wall"
MIC_DEVICE_INDEX   = None
SAMPLE_RATE        = 16000
FRAME_MS           = 30
FRAME_BYTES        = int(SAMPLE_RATE * FRAME_MS / 1000) * 2
SILENCE_TIMEOUT    = 1.5
VAD_AGGRESSIVENESS = 2
LLM_MODEL          = 'llama3.2'
PIPER_MODEL        = "/tmp/en_US-lessac-medium.onnx"
SOURCE             = "alsa_input.usb-C-Media_Electronics_Inc._USB_PnP_Sound_Device-00.analog-mono"

# ── Init ──────────────────────────────────────────────────────────────────────
print("Loading TTS model...")
tts_voice  = PiperVoice.load(PIPER_MODEL)
pa         = pyaudio.PyAudio()
# Replace the tts_stream init with a larger buffer
tts_stream = pa.open(
    format=pyaudio.paInt16,
    channels=1,
    rate=22050,
    output=True,
    frames_per_buffer=4096  # larger buffer prevents underruns
)
print("TTS ready.")

print("Loading Whisper model...")
whisper = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=4, num_workers=2)
print("Whisper ready.")

vad   = webrtcvad.Vad(VAD_AGGRESSIVENESS)
audio = pyaudio.PyAudio()

messages = [
    {"role": "system", "content": "You are a helpful assistant. Keep your answers concise. I mean as short as possible. Like, really short."},
]

# ── Audio ─────────────────────────────────────────────────────────────────────
def record_until_silence() -> bytes:
    stream = audio.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=MIC_DEVICE_INDEX,
        frames_per_buffer=FRAME_BYTES // 2,
    )
    frames, silence_frames, speaking = [], 0, False
    max_silence = int(SILENCE_TIMEOUT * 1000 / FRAME_MS)

    try:
        while True:
            frame = stream.read(FRAME_BYTES // 2, exception_on_overflow=False)
            if len(frame) < FRAME_BYTES:
                continue
            is_speech = vad.is_speech(frame, SAMPLE_RATE)
            if is_speech:
                speaking, silence_frames = True, 0
                frames.append(frame)
            elif speaking:
                silence_frames += 1
                frames.append(frame)
                if silence_frames >= max_silence:
                    break
    finally:
        stream.stop_stream()
        stream.close()

    return b"".join(frames)

def transcribe(audio_bytes: bytes) -> str:
    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = whisper.transcribe(audio_np, language="en", vad_filter=True)
    return " ".join(seg.text for seg in segments).strip()

def listen_for_wake_word() -> str | None:
    print(f"\nWaiting for wake word: 'hey {WAKE_WORD}'...")
    while True:
        audio_bytes = record_until_silence()
        if not audio_bytes:
            continue
        text = transcribe(audio_bytes).lower()
        print(f"  heard: {text}")
        if WAKE_WORD in text:
            after = text.split(WAKE_WORD, 1)[-1].strip()
            if after:
                return after
            print("Wake word detected! Speak your command...")
            return transcribe(record_until_silence())

# ── TTS ───────────────────────────────────────────────────────────────────────
def speak(text: str):
    print(f"Assistant: {text}")
    subprocess.run(["pactl", "set-source-mute", SOURCE, "1"])

    import io, wave
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        tts_voice.synthesize_wav(text, wav_file)

    wav_io.seek(0)
    with wave.open(wav_io, 'rb') as wav_file:
        rate     = wav_file.getframerate()
        n_frames = wav_file.getnframes()
        raw      = wav_file.readframes(n_frames)

    # Reopen stream at correct sample rate if needed
    global tts_stream
    if tts_stream._rate != rate:
        tts_stream.stop_stream()
        tts_stream.close()
        tts_stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=rate,
            output=True,
            frames_per_buffer=4096
        )

    tts_stream.write(raw)
    time.sleep(0.3)
    subprocess.run(["pactl", "set-source-mute", SOURCE, "0"])

# ── LLM ───────────────────────────────────────────────────────────────────────
def ask(user_input: str) -> str:
    messages.append({"role": "user", "content": user_input})
    response = chat(LLM_MODEL, messages=messages)
    reply = response['message']['content']
    messages.append({"role": "assistant", "content": reply})
    return reply

# ── Main loop ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    speak("Ready. Say hey fish on the wall to wake me up.")

    while True:
        command = listen_for_wake_word()
        if not command:
            continue

        print(f"You: {command}")
        reply = ask(command)
        speak(reply)