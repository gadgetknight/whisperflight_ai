"""
Whisper Flight AI - Audio Processor
Version: 5.1.11
Purpose: Handles speech recognition and text-to-speech with multiple providers
Last Updated: March 25, 2025
Author: Your Name

Changes in this version:
- Lowered Whisper noise_threshold to 0.05 (line 179)
- Added audio detection log in transcribe (line 205)
- Retained ElevenLabs timeout fixes from v5.1.9 (lines 540-554)
- Kept TTS debug log from v5.1.10 (line 655)
"""

import os
import sys
import time
import logging
import threading
import numpy as np
import pyaudio
import wave
import pygame
import queue
import tempfile
from abc import ABC, abstractmethod
from config_manager import config

try:
    import speech_recognition as sr
    GOOGLE_STT_AVAILABLE = True
except ImportError:
    GOOGLE_STT_AVAILABLE = False
    logging.warning("SpeechRecognition module not found. Google STT unavailable.")

try:
    import whisper
    WHISPER_AVAILABLE = True
    WHISPER_HAS_TIMESTAMPS = hasattr(whisper.DecodingOptions(), "word_timestamps")
except ImportError:
    WHISPER_AVAILABLE = False
    WHISPER_HAS_TIMESTAMPS = False
    logging.warning("Whisper module not found. Whisper STT unavailable.")

try:
    import elevenlabs
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    logging.warning("ElevenLabs module not found. ElevenLabs TTS unavailable.")

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logging.warning("gTTS module not found. Google TTS unavailable.")

class SpeechToText(ABC):
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.recording_seconds = config.getfloat("Speech", "recording_seconds", 5)
        self.sample_rate = 16000
        self.channels = 1
        self.chunk_size = 1024
        self.format = pyaudio.paInt16
    
    @abstractmethod
    def transcribe(self, audio_data):
        pass
    
    def record_audio(self):
        self.logger.info("Recording audio started")
        device_name = config.get("Audio", "input_device", "default")
        device_index = None
        p = pyaudio.PyAudio()
        if device_name != "default":
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if device_name.lower() in info["name"].lower() and info["maxInputChannels"] > 0:
                    device_index = i
                    break
        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_filename = temp_file.name
        temp_file.close()
        max_retries = 3
        for attempt in range(max_retries):
            try:
                stream = p.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self.chunk_size
                )
                frames = []
                for _ in range(int(self.sample_rate / self.chunk_size * self.recording_seconds)):
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    frames.append(data)
                stream.stop_stream()
                stream.close()
                wf = wave.open(temp_filename, 'wb')
                wf.setnchannels(self.channels)
                wf.setsampwidth(p.get_sample_size(self.format))
                wf.setframerate(self.sample_rate)
                wf.writeframes(b''.join(frames))
                wf.close()
                self.logger.info(f"Audio recorded to {temp_filename}")
                break
            except Exception as e:
                self.logger.error(f"Error recording audio (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt + 1 == max_retries:
                    return None
                time.sleep(1)
        p.terminate()
        return temp_filename
    
    def get_input(self):
        audio_file = self.record_audio()
        if not audio_file:
            self.logger.info("No audio file recorded, returning empty string")
            return ""
        try:
            text = self.transcribe(audio_file)
            self.logger.info(f"Transcribed audio input: '{text}'")
            return text.lower().strip()
        except Exception as e:
            self.logger.error(f"Error transcribing audio: {e}")
            return ""
        finally:
            try:
                os.remove(audio_file)
                self.logger.info(f"Temporary audio file {audio_file} removed")
            except:
                self.logger.warning(f"Failed to remove temporary file {audio_file}")

class WhisperSTT(SpeechToText):
    def __init__(self):
        super().__init__()
        self.model = None
        self.model_name = config.get("API_Models", "whisper_model", "base")
        self.noise_threshold = config.getfloat("Speech", "noise_threshold", 0.05)  # Lowered to 0.05
        self._load_model()
    
    def _load_model(self):
        if not WHISPER_AVAILABLE:
            self.logger.error("Whisper module not available")
            return
        try:
            self.logger.info(f"Loading Whisper {self.model_name} model...")
            self.model = whisper.load_model(self.model_name)
            self.logger.info(f"Whisper {self.model_name} model loaded successfully")
        except Exception as e:
            self.logger.error(f"Error loading Whisper model: {e}")
            self.model = None
    
    def transcribe(self, audio_data):
        if not self.model:
            self._load_model()
            if not self.model:
                self.logger.error("Whisper model not loaded, transcription aborted")
                return ""
        try:
            self.logger.info(f"Starting Whisper transcription for audio file: {audio_data}")
            if WHISPER_HAS_TIMESTAMPS:
                result = self.model.transcribe(audio_data, word_timestamps=True)
            else:
                result = self.model.transcribe(audio_data)
            text = result["text"].strip()
            self.logger.info(f"Raw Whisper transcription result: '{text}'")  # Debug audio detection
            if len(text) < 2 or "1.0.1" in text:
                self.logger.info("Transcription too short or invalid, returning empty string")
                return ""
            lower_text = text.lower()
            if any(phrase in lower_text for phrase in [
                "sky tour", "skytour", "sky to", "sky tore", "sky tor", 
                "skator", "skater", "sky door", "sky t", "sky2", "scatour", "scator"
            ]):
                self.logger.info(f"Wake phrase detected: '{lower_text}' - Normalized to 'sky tour'")
                return "sky tour"
            if any(word in lower_text for word in ["grok", "growth", "rock", "crock", "roc"]):
                self.logger.info(f"Grok command detected: '{lower_text}'")
                return "use grok"
            if any(word in lower_text for word in ["open ai", "openai", "open eye", "open a", "gpt"]):
                self.logger.info(f"OpenAI command detected: '{lower_text}'")
                return "use openai"
            if "philadelphia" in lower_text and any(word in lower_text for word in ["airport", "international"]):
                self.logger.info(f"Philadelphia airport command detected: '{lower_text}'")
                return "navigate to philadelphia international airport"
            if "question" in lower_text or "i have a question" in lower_text:
                self.logger.info(f"Reactivation phrase detected: '{lower_text}'")
                return "question"
            self.logger.info(f"Transcription completed successfully: '{text}'")
            return text
        except Exception as e:
            self.logger.error(f"Error during Whisper transcription: {e}")
            return ""

class GoogleSTT(SpeechToText):
    def __init__(self):
        super().__init__()
        self.recognizer = sr.Recognizer() if GOOGLE_STT_AVAILABLE else None
    
    def transcribe(self, audio_data):
        if not self.recognizer:
            self.logger.error("Google Speech Recognition not available")
            return ""
        try:
            self.logger.info(f"Starting Google STT transcription for audio file: {audio_data}")
            with sr.AudioFile(audio_data) as source:
                audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio)
                self.logger.info(f"Google STT transcription result: '{text}'")
                return text
        except sr.UnknownValueError:
            self.logger.info("Google STT could not understand audio")
            return ""
        except sr.RequestError as e:
            self.logger.error(f"Google STT request error: {e}")
            return ""
        except Exception as e:
            self.logger.error(f"Error in Google STT: {e}")
            return ""

class TextToSpeech(ABC):
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.voice = config.get("Speech", "tts_voice", "default")
        pygame.mixer.init()
    
    @abstractmethod
    def synthesize(self, text, output_file):
        pass
    
    def speak(self, text):
        if not text:
            self.logger.info("No text provided to speak")
            return False
        try:
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_filename = temp_file.name
            temp_file.close()
            if not self.synthesize(text, temp_filename):
                self.logger.error(f"Synthesis failed for text: '{text}'")
                return False
            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            self.logger.info(f"Playing audio for text: '{text[:50]}...'")
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            self.logger.info(f"Finished playing audio for text: '{text[:50]}...'")
            return True
        except Exception as e:
            self.logger.error(f"Error speaking text: {e}")
            return False
        finally:
            try:
                os.remove(temp_filename)
                self.logger.info(f"Temporary audio file {temp_filename} removed")
            except:
                self.logger.warning(f"Failed to remove temporary file {temp_filename}")

class ElevenLabsTTS(TextToSpeech):
    def __init__(self):
        super().__init__()
        self.api_key = config.get_api_key("elevenlabs")
        self.voice_id = config.get("Audio", "elevenlabs_voice_id", "")
        if not self.api_key:
            self.logger.warning("ElevenLabs API key not set")
        else:
            self.logger.info("ElevenLabs API key found")
        if not self.voice_id:
            self.logger.warning("ElevenLabs voice ID not set")
        else:
            self.logger.info(f"ElevenLabs using voice ID: {self.voice_id}")
    
    def synthesize(self, text, output_file):
        if not ELEVENLABS_AVAILABLE:
            self.logger.error("ElevenLabs module not available")
            return False
        if not self.api_key or not self.voice_id:
            self.logger.error("ElevenLabs API key or voice ID not set")
            return False
        try:
            self.logger.info(f"Synthesizing text with ElevenLabs: '{text[:50]}...'")
            import requests
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            data = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.75, "similarity_boost": 0.75}
            }
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.post(url, json=data, headers=headers, timeout=20)
                    response.raise_for_status()
                    with open(output_file, "wb") as f:
                        f.write(response.content)
                    self.logger.info("Successfully generated audio with ElevenLabs")
                    return True
                except Exception as e:
                    self.logger.error(f"Error in ElevenLabs synthesis attempt {attempt + 1}/{max_retries}: {str(e)}")
                    if attempt + 1 == max_retries and GTTS_AVAILABLE:
                        self.logger.info("Falling back to Google TTS")
                        return GoogleTTS().synthesize(text, output_file)
                    time.sleep(2 ** attempt)
            return False
        except Exception as e:
            self.logger.error(f"Error in ElevenLabs synthesis: {e}")
            return False

class GoogleTTS(TextToSpeech):
    def __init__(self):
        super().__init__()
        self.lang = config.get("API_Models", "gtts_language", "en")
    
    def synthesize(self, text, output_file):
        if not GTTS_AVAILABLE:
            self.logger.error("Google TTS module not available")
            return False
        try:
            self.logger.info(f"Synthesizing text with Google TTS: '{text[:50]}...'")
            tts = gTTS(text=text, lang=self.lang, slow=False)
            tts.save(output_file)
            self.logger.info("Google TTS synthesis successful")
            return True
        except Exception as e:
            self.logger.error(f"Error in Google TTS synthesis: {e}")
            return False

class AudioProcessor:
    def __init__(self):
        self.logger = logging.getLogger("AudioProcessor")
        self.logger.info("Initializing AudioProcessor")
        self.stt_provider = self._create_stt_provider()
        self.tts_provider = self._create_tts_provider()
        self.audio_queue = queue.Queue()
        self.is_listening = False
        self.listen_thread = None
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.sound_effects = {
            "optimus_prime": os.path.join(script_dir, "Sky_Tour_Activated.mp3"),
            "deactivate": os.path.join(script_dir, "Sky_Tour_Deactivated.mp3")
        }
        self.logger.info(f"Activation sound: {self.sound_effects['optimus_prime']}")
        self.logger.info(f"Deactivation sound: {self.sound_effects['deactivate']}")
    
    def _create_stt_provider(self):
        provider_name = config.get("Speech", "stt_engine", "whisper").lower()
        if provider_name == "whisper" and WHISPER_AVAILABLE:
            return WhisperSTT()
        elif provider_name == "google" and GOOGLE_STT_AVAILABLE:
            return GoogleSTT()
        elif WHISPER_AVAILABLE:
            self.logger.warning(f"STT provider '{provider_name}' unavailable, using Whisper")
            return WhisperSTT()
        elif GOOGLE_STT_AVAILABLE:
            self.logger.warning(f"STT provider '{provider_name}' unavailable, using Google")
            return GoogleSTT()
        self.logger.error("No STT provider available")
        return None
    
    def _create_tts_provider(self):
        provider_name = config.get("Speech", "tts_engine", "elevenlabs").lower()
        self.logger.info(f"Selected TTS engine: {provider_name}")
        if provider_name == "elevenlabs" and ELEVENLABS_AVAILABLE:
            return ElevenLabsTTS()
        elif provider_name == "google" and GTTS_AVAILABLE:
            return GoogleTTS()
        elif ELEVENLABS_AVAILABLE:
            self.logger.warning(f"TTS provider '{provider_name}' unavailable, using ElevenLabs")
            return ElevenLabsTTS()
        elif GTTS_AVAILABLE:
            self.logger.warning(f"TTS provider '{provider_name}' unavailable, using Google")
            return GoogleTTS()
        self.logger.error("No TTS provider available")
        return None
    
    def speak(self, text, sound_effect=None):
        if sound_effect and sound_effect in self.sound_effects:
            try:
                sound_file = self.sound_effects[sound_effect]
                if os.path.exists(sound_file):
                    pygame.mixer.music.load(sound_file)
                    pygame.mixer.music.play()
                    self.logger.info(f"Playing sound effect: {sound_file}")
                    while pygame.mixer.music.get_busy():
                        pygame.time.wait(100)
                    return True
                else:
                    self.logger.warning(f"Sound effect file not found: {sound_file}")
            except Exception as e:
                self.logger.error(f"Error playing sound effect: {e}")
        if not text or not self.tts_provider:
            if not self.tts_provider:
                self.logger.error("No TTS provider available")
            return False
        print("\n🔊 AI: " + text + "\n")
        return self.tts_provider.speak(text)
    
    def listen(self):
        if not self.stt_provider:
            self.logger.error("No STT provider available")
            return ""
        return self.stt_provider.get_input()
    
    def start_continuous_listening(self):
        if self.is_listening:
            self.logger.info("Continuous listening already active")
            return
        self.is_listening = True
        self.listen_thread = threading.Thread(target=self._listen_worker)
        self.listen_thread.daemon = True
        self.listen_thread.start()
        self.logger.info("Started continuous listening thread")
    
    def stop_continuous_listening(self):
        self.is_listening = False
        if self.listen_thread:
            self.listen_thread.join(timeout=1.0)
            self.listen_thread = None
        self.logger.info("Stopped continuous listening thread")
    
    def _listen_worker(self):
        while self.is_listening:
            text = self.listen()
            if text:
                self.audio_queue.put(text)
    
    def get_next_command(self, block=True, timeout=None):
        try:
            command = self.audio_queue.get(block=block, timeout=timeout)
            self.logger.info(f"Retrieved command from queue: '{command}'")
            return command
        except queue.Empty:
            self.logger.info("No command in queue, returning None")
            return None
    
    def get_audio_input(self):
        return self.listen()

audio_processor = AudioProcessor()

activate_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sky_Tour_Activated.mp3")
deactivate_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sky_Tour_Deactivated.mp3")
if not os.path.exists(activate_file):
    logging.warning(f"Activation sound file not found at {activate_file}")
else:
    logging.info(f"Found activation sound file at {activate_file}")
if not os.path.exists(deactivate_file):
    logging.warning(f"Deactivation sound file not found at {deactivate_file}")
else:
    logging.info(f"Found deactivation sound file at {deactivate_file}")