from ollama import chat
from TTS.api import TTS
from faster_whisper import WhisperModel
import pyaudio
import webrtcvad
import numpy as np
import subprocess
import time
import re
import threading
import queue

# ── Config ────────────────────────────────────────────────────────────────────
WAKE_WORD          = "hey fish on the wall"
MIC_DEVICE_INDEX   = None
SAMPLE_RATE        = 16000
FRAME_MS           = 30
FRAME_BYTES        = int(SAMPLE_RATE * FRAME_MS / 1000) * 2
SILENCE_TIMEOUT    = 1.5
VAD_AGGRESSIVENESS = 2
LLM_MODEL          = 'llama3.2'
SINK               = "alsa_output.usb-Jieli_Technology_UACDemoV1.0_415035313136340C-00.stereo-fallback"
SOURCE             = "alsa_input.usb-C-Media_Electronics_Inc._USB_PnP_Sound_Device-00.analog-mono"

# ── Init ──────────────────────────────────────────────────────────────────────
print("Loading TTS model...")
tts = TTS("tts_models/en/ljspeech/tacotron2-DDC")
print("TTS ready.")

print("Loading Whisper model...")
whisper = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=4, num_workers=2)
print("Whisper ready.")

vad        = webrtcvad.Vad(VAD_AGGRESSIVENESS)
audio      = pyaudio.PyAudio()
speak_lock = threading.Lock()  # prevent overlapping speech

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
    print(f"\nWaiting for wake word: '{WAKE_WORD}'...")
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
def speak_sentence(sentence: str):
    """Synthesize and play a single sentence."""
    sentence = sentence.strip()
    if not sentence:
        return
    tts.tts_to_file(text=sentence, file_path="/tmp/speech.wav")
    subprocess.run(["aplay", "/tmp/speech.wav"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def speak_streaming(text: str):
    """Split into sentences and speak each as soon as it's synthesized."""
    print(f"Assistant: {text}")
    subprocess.run(["pactl", "set-source-mute", SOURCE, "1"])

    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    for sentence in sentences:
        speak_sentence(sentence)

    time.sleep(0.3)
    subprocess.run(["pactl", "set-source-mute", SOURCE, "0"])

# ── LLM with streaming ────────────────────────────────────────────────────────
def ask_streaming(user_input: str):
    """
    Stream tokens from Ollama, accumulate into sentences,
    and speak each sentence as soon as it's complete.
    """
    messages.append({"role": "user", "content": user_input})
    subprocess.run(["pactl", "set-source-mute", SOURCE, "1"])

    buffer   = ""
    full     = ""
    sentence_end = re.compile(r'(?<=[.!?])\s+')

    print("Assistant: ", end="", flush=True)

    for chunk in chat(LLM_MODEL, messages=messages, stream=True):
        token = chunk['message']['content']
        print(token, end="", flush=True)
        buffer += token
        full   += token

        # Speak each complete sentence immediately
        parts = sentence_end.split(buffer)
        if len(parts) > 1:
            for sentence in parts[:-1]:
                speak_sentence(sentence)
            buffer = parts[-1]  # keep incomplete sentence for next chunk

    # Speak any remaining text
    if buffer.strip():
        speak_sentence(buffer)

    print()  # newline after streamed output
    messages.append({"role": "assistant", "content": full})

    time.sleep(0.3)
    subprocess.run(["pactl", "set-source-mute", SOURCE, "0"])

# ── Main loop ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    speak_streaming("Ready. Say hey fish on the wall to wake me up.")

    while True:
        command = listen_for_wake_word()
        if not command:
            continue

        print(f"You: {command}")
        ask_streaming(command)  # streams LLM tokens and speaks sentence by sentence