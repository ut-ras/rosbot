from ollama import chat
import pyttsx3
from TTS.api import TTS
import subprocess

tts = TTS("tts_models/en/ljspeech/tacotron2-DDC")

model = 'glm-4.7-flash'
model = 'gwen3.5:9b'
model = 'llama3.2'

messages = [
    {"role": "system", "content": "You are a helpful assistant. Keep your answers concise. I mean as short as possible. Like, really short."},
    {"role": "user", "content": "is it better to earn 1 dollar a day for the rest of your life or 1000000 dollars right now?"},
]

# def speak(text: str, rate: int = 175, volume: float = 1.0, voice_index: int = 0):
    # engine = pyttsx3.init()

    # # Adjust speech rate (words per minute, default ~200)
    # engine.setProperty('rate', rate)

    # # Adjust volume (0.0 to 1.0)
    # engine.setProperty('volume', volume)

    # # Pick a voice (0 = first available, usually male; 1 = second, often female)
    # voices = engine.getProperty('voices')
    # if voice_index < len(voices):
    #     engine.setProperty('voice', voices[voice_index].id)

    # engine.say(text)
    # engine.runAndWait()
    # engine.stop()
def speak(text: str):
    tts.tts_to_file(text=text, file_path="/tmp/speech.wav")
    subprocess.run(["aplay", "/tmp/speech.wav"])

# List all available voices on your system
# def list_voices():
#     engine = pyttsx3.init()
#     for i, voice in enumerate(engine.getProperty('voices')):
#         print(f"[{i}] {voice.name} — {voice.id}")
#     engine.stop()

response = chat(model, messages=messages)
# speak(response['message']['content'], rate=160, volume=1, voice_index=19)
speak(response['message']['content'])
print(response['message']['content'])

# list_voices()