"""
Whisper Flight AI - Audio Processor Diagnostic
Version: 5.1.11-DEBUG
Purpose: Diagnose audio processing and wake word detection issues
Last Updated: March 28, 2025
Author: Your Name

Changes in this version:
- Added extensive debug logging for wake word detection
- Added audio level monitoring in continuous listening
- Added transcription detail logging
- Added timing benchmarks for performance analysis
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

# Setup a special debug logger
debug_logger = logging.getLogger("AUDIO_DEBUG")
debug_handler = logging.FileHandler("audio_debug.log")
debug_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
debug_handler.setFormatter(debug_formatter)
debug_logger.addHandler(debug_handler)
debug_logger.setLevel(logging.DEBUG)

def debug_log(message, level="INFO"):
   """Centralized debug logging with console output"""
   if level == "DEBUG":
       debug_logger.debug(message)
   elif level == "INFO":
       debug_logger.info(message)
   elif level == "WARNING":
       debug_logger.warning(message)
   elif level == "ERROR":
       debug_logger.error(message)
   elif level == "CRITICAL":
       debug_logger.critical(message)
   
   # Also print to console for immediate feedback
   print(f"AUDIO_DEBUG: {message}")

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
       debug_log(f"Recording audio started for {self.recording_seconds} seconds", "INFO")
       device_name = config.get("Audio", "input_device", "default")
       device_index = None
       p = pyaudio.PyAudio()
       
       # Log available devices for diagnosis
       devices_info = []
       for i in range(p.get_device_count()):
           info = p.get_device_info_by_index(i)
           devices_info.append(f"Device {i}: {info['name']} (Inputs: {info['maxInputChannels']})")
       debug_log(f"Available audio devices:\n" + "\n".join(devices_info), "INFO")
       
       if device_name != "default":
           for i in range(p.get_device_count()):
               info = p.get_device_info_by_index(i)
               if device_name.lower() in info["name"].lower() and info["maxInputChannels"] > 0:
                   device_index = i
                   break
           debug_log(f"Selected device: {device_name} (index: {device_index})", "INFO")
       else:
           debug_log("Using default recording device", "INFO")
           
       temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
       temp_filename = temp_file.name
       temp_file.close()
       
       debug_log(f"Temporary audio file: {temp_filename}", "INFO")
       
       max_retries = 3
       for attempt in range(max_retries):
           try:
               debug_log(f"Opening audio stream (attempt {attempt+1}/{max_retries})", "INFO")
               stream = p.open(
                   format=self.format,
                   channels=self.channels,
                   rate=self.sample_rate,
                   input=True,
                   input_device_index=device_index,
                   frames_per_buffer=self.chunk_size
               )
               frames = []
               
               debug_log("Recording started", "INFO")
               
               # Audio level monitoring
               max_level = 0
               for i in range(int(self.sample_rate / self.chunk_size * self.recording_seconds)):
                   data = stream.read(self.chunk_size, exception_on_overflow=False)
                   frames.append(data)
                   
                   # Calculate audio level for debugging
                   audio_data = np.frombuffer(data, dtype=np.int16)
                   audio_level = np.abs(audio_data).mean() / 32767.0  # Normalize to 0-1
                   max_level = max(max_level, audio_level)
                   
                   # Log every few frames to avoid excessive logs
                   if i % 10 == 0:
                       level_indicator = "#" * int(audio_level * 50)
                       debug_log(f"Audio level: {audio_level:.4f} [{level_indicator}]", "DEBUG")
               
               stream.stop_stream()
               stream.close()
               
               debug_log(f"Recording finished. Max audio level: {max_level:.4f}", "INFO")
               debug_log(f"Frames captured: {len(frames)}", "INFO")
               
               wf = wave.open(temp_filename, 'wb')
               wf.setnchannels(self.channels)
               wf.setsampwidth(p.get_sample_size(self.format))
               wf.setframerate(self.sample_rate)
               wf.writeframes(b''.join(frames))
               wf.close()
               
               debug_log(f"Audio saved to {temp_filename}", "INFO")
               break
           except Exception as e:
               debug_log(f"Error recording audio (attempt {attempt + 1}/{max_retries}): {e}", "ERROR")
               if attempt + 1 == max_retries:
                   return None
               time.sleep(1)
       
       p.terminate()
       return temp_filename
   
   def get_input(self):
       audio_file = self.record_audio()
       if not audio_file:
           debug_log("No audio file recorded, returning empty string", "ERROR")
           return ""
       try:
           debug_log(f"Transcribing audio file: {audio_file}", "INFO")
           text = self.transcribe(audio_file)
           debug_log(f"Transcribed audio input: '{text}'", "INFO")
           return text.lower().strip()
       except Exception as e:
           debug_log(f"Error transcribing audio: {e}", "ERROR")
           return ""
       finally:
           try:
               os.remove(audio_file)
               debug_log(f"Temporary audio file {audio_file} removed", "INFO")
           except Exception as e:
               debug_log(f"Failed to remove temporary file {audio_file}: {e}", "WARNING")


class WhisperSTT(SpeechToText):
   def __init__(self):
       super().__init__()
       self.model = None
       self.model_name = config.get("API_Models", "whisper_model", "base")
       self.noise_threshold = config.getfloat("Speech", "noise_threshold", 0.05)  # Lowered to 0.05
       debug_log(f"WhisperSTT initialized with model={self.model_name}, noise_threshold={self.noise_threshold}", "INFO")
       self._load_model()
   
   def _load_model(self):
       if not WHISPER_AVAILABLE:
           debug_log("Whisper module not available", "ERROR")
           return
       try:
           debug_log(f"Loading Whisper {self.model_name} model...", "INFO")
           start_time = time.time()
           self.model = whisper.load_model(self.model_name)
           load_time = time.time() - start_time
           debug_log(f"Whisper {self.model_name} model loaded successfully in {load_time:.2f} seconds", "INFO")
       except Exception as e:
           debug_log(f"Error loading Whisper model: {e}", "ERROR")
           self.model = None
   
   def transcribe(self, audio_data):
       if not self.model:
           debug_log("Attempting to reload Whisper model", "WARNING")
           self._load_model()
           if not self.model:
               debug_log("Whisper model not loaded, transcription aborted", "ERROR")
               return ""
       try:
           debug_log(f"Starting Whisper transcription for audio file: {audio_data}", "INFO")
           
           # File existence check
           if not os.path.exists(audio_data):
               debug_log(f"Audio file does not exist: {audio_data}", "ERROR")
               return ""
               
           # File size check
           file_size = os.path.getsize(audio_data)
           debug_log(f"Audio file size: {file_size} bytes", "INFO")
           if file_size < 100:  # Suspiciously small file
               debug_log("Audio file is suspiciously small, possibly empty recording", "WARNING")
           
           # Benchmark transcription time
           start_time = time.time()
           
           if WHISPER_HAS_TIMESTAMPS:
               debug_log("Using Whisper with word timestamps", "INFO")
               result = self.model.transcribe(audio_data, word_timestamps=True)
           else:
               debug_log("Using Whisper without word timestamps", "INFO")
               result = self.model.transcribe(audio_data)
           
           transcription_time = time.time() - start_time
           debug_log(f"Transcription completed in {transcription_time:.2f} seconds", "INFO")
           
           # Log detailed result information
           text = result["text"].strip()
           debug_log(f"Raw Whisper transcription result: '{text}'", "INFO")
           
           # Log segmentation info if available
           if "segments" in result:
               segments_info = [f"Segment {i}: {seg.get('text', '')[:30]}..." for i, seg in enumerate(result["segments"])]
               debug_log(f"Segments detected: {len(result['segments'])}", "DEBUG")
               debug_log(f"Segment samples: {'; '.join(segments_info[:3])}", "DEBUG")
           
           # Wake word detection logging
           wake_variations = [
               "sky tour", "skytour", "sky to", "sky tore", "sky tor", 
               "skator", "skater", "sky door", "sky t", "sky2", "scatour", "scator"
           ]
           
           lower_text = text.lower()
           debug_log(f"Checking for wake phrases in: '{lower_text}'", "INFO")
           
           # Check each wake variation
           for variation in wake_variations:
               if variation in lower_text:
                   debug_log(f"Wake phrase detected: '{variation}' in '{lower_text}'", "INFO")
                   debug_log("Normalizing to 'sky tour'", "INFO")
                   return "sky tour"
           
           # Check for API commands
           if any(word in lower_text for word in ["grok", "growth", "rock", "crock", "roc"]):
               debug_log(f"Grok command detected: '{lower_text}'", "INFO")
               return "use grok"
               
           if any(word in lower_text for word in ["open ai", "openai", "open eye", "open a", "gpt"]):
               debug_log(f"OpenAI command detected: '{lower_text}'", "INFO")
               return "use openai"
               
           if "philadelphia" in lower_text and any(word in lower_text for word in ["airport", "international"]):
               debug_log(f"Philadelphia airport command detected: '{lower_text}'", "INFO")
               return "navigate to philadelphia international airport"
               
           if "question" in lower_text or "i have a question" in lower_text:
               debug_log(f"Reactivation phrase detected: '{lower_text}'", "INFO")
               return "question"
           
           debug_log(f"No wake phrase or command detected in: '{lower_text}'", "INFO")
           debug_log(f"Transcription completed successfully: '{text}'", "INFO")
           return text
       except Exception as e:
           debug_log(f"Error during Whisper transcription: {e}", "ERROR")
           import traceback
           debug_log(f"Traceback: {traceback.format_exc()}", "ERROR")
           return ""


class GoogleSTT(SpeechToText):
   def __init__(self):
       super().__init__()
       self.recognizer = sr.Recognizer() if GOOGLE_STT_AVAILABLE else None
       debug_log(f"GoogleSTT initialized, available: {GOOGLE_STT_AVAILABLE}", "INFO")
   
   def transcribe(self, audio_data):
       if not self.recognizer:
           debug_log("Google Speech Recognition not available", "ERROR")
           return ""
       try:
           debug_log(f"Starting Google STT transcription for audio file: {audio_data}", "INFO")
           with sr.AudioFile(audio_data) as source:
               audio = self.recognizer.record(source)
               text = self.recognizer.recognize_google(audio)
               debug_log(f"Google STT transcription result: '{text}'", "INFO")
               return text
       except sr.UnknownValueError:
           debug_log("Google STT could not understand audio", "WARNING")
           return ""
       except sr.RequestError as e:
           debug_log(f"Google STT request error: {e}", "ERROR")
           return ""
       except Exception as e:
           debug_log(f"Error in Google STT: {e}", "ERROR")
           return ""


class TextToSpeech(ABC):
   def __init__(self):
       self.logger = logging.getLogger(self.__class__.__name__)
       self.voice = config.get("Speech", "tts_voice", "default")
       pygame.mixer.init()
       debug_log(f"TextToSpeech base class initialized", "INFO")
   
   @abstractmethod
   def synthesize(self, text, output_file):
       pass
   
   def speak(self, text):
       if not text:
           debug_log("No text provided to speak", "INFO")
           return False
       try:
           temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
           temp_filename = temp_file.name
           temp_file.close()
           
           debug_log(f"Synthesizing speech for text: '{text[:50]}...'", "INFO")
           debug_log(f"Temporary audio file: {temp_filename}", "DEBUG")
           
           if not self.synthesize(text, temp_filename):
               debug_log(f"Synthesis failed for text: '{text}'", "ERROR")
               return False
               
           debug_log("Synthesis successful, playing audio", "INFO")
           
           # Check if pygame mixer is initialized
           if not pygame.mixer.get_init():
               debug_log("PyGame mixer not initialized, attempting to initialize", "WARNING")
               pygame.mixer.init()
               
           pygame.mixer.music.load(temp_filename)
           pygame.mixer.music.play()
           
           debug_log(f"Playing audio for text: '{text[:50]}...'", "INFO")
           
           while pygame.mixer.music.get_busy():
               pygame.time.wait(100)
               
           debug_log(f"Finished playing audio for text: '{text[:50]}...'", "INFO")
           return True
       except Exception as e:
           debug_log(f"Error speaking text: {e}", "ERROR")
           import traceback
           debug_log(f"Traceback: {traceback.format_exc()}", "ERROR")
           return False
       finally:
           try:
               os.remove(temp_filename)
               debug_log(f"Temporary audio file {temp_filename} removed", "DEBUG")
           except Exception as e:
               debug_log(f"Failed to remove temporary file {temp_filename}: {e}", "WARNING")


class ElevenLabsTTS(TextToSpeech):
   def __init__(self):
       super().__init__()
       self.api_key = config.get_api_key("elevenlabs")
       self.voice_id = config.get("Audio", "elevenlabs_voice_id", "")
       
       debug_log(f"ElevenLabsTTS initialized", "INFO")
       debug_log(f"API key exists: {bool(self.api_key)}", "INFO")
       debug_log(f"Voice ID: {self.voice_id}", "INFO")
       
       if not self.api_key:
           debug_log("ElevenLabs API key not set", "WARNING")
       else:
           debug_log("ElevenLabs API key found", "INFO")
           
       if not self.voice_id:
           debug_log("ElevenLabs voice ID not set", "WARNING")
       else:
           debug_log(f"ElevenLabs using voice ID: {self.voice_id}", "INFO")
   
   def synthesize(self, text, output_file):
       if not ELEVENLABS_AVAILABLE:
           debug_log("ElevenLabs module not available", "ERROR")
           return False
       if not self.api_key or not self.voice_id:
           debug_log("ElevenLabs API key or voice ID not set", "ERROR")
           return False
       try:
           debug_log(f"Synthesizing text with ElevenLabs: '{text[:50]}...'", "INFO")
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
                   debug_log(f"ElevenLabs API request (attempt {attempt+1}/{max_retries})", "INFO")
                   start_time = time.time()
                   response = requests.post(url, json=data, headers=headers, timeout=20)
                   response_time = time.time() - start_time
                   debug_log(f"ElevenLabs API response received in {response_time:.2f} seconds", "INFO")
                   
                   response.raise_for_status()
                   with open(output_file, "wb") as f:
                       f.write(response.content)
                   debug_log(f"Successfully generated audio with ElevenLabs", "INFO")
                   debug_log(f"Audio file size: {os.path.getsize(output_file)} bytes", "DEBUG")
                   return True
               except Exception as e:
                   debug_log(f"Error in ElevenLabs synthesis attempt {attempt + 1}/{max_retries}: {str(e)}", "ERROR")
                   if attempt + 1 == max_retries and GTTS_AVAILABLE:
                       debug_log("Falling back to Google TTS", "WARNING")
                       return GoogleTTS().synthesize(text, output_file)
                   time.sleep(2 ** attempt)
           return False
       except Exception as e:
           debug_log(f"Error in ElevenLabs synthesis: {e}", "ERROR")
           return False


class GoogleTTS(TextToSpeech):
   def __init__(self):
       super().__init__()
       self.lang = config.get("API_Models", "gtts_language", "en")
       debug_log(f"GoogleTTS initialized with language={self.lang}", "INFO")
   
   def synthesize(self, text, output_file):
       if not GTTS_AVAILABLE:
           debug_log("Google TTS module not available", "ERROR")
           return False
       try:
           debug_log(f"Synthesizing text with Google TTS: '{text[:50]}...'", "INFO")
           start_time = time.time()
           tts = gTTS(text=text, lang=self.lang, slow=False)
           tts.save(output_file)
           synthesis_time = time.time() - start_time
           debug_log(f"Google TTS synthesis successful in {synthesis_time:.2f} seconds", "INFO")
           debug_log(f"Audio file size: {os.path.getsize(output_file)} bytes", "DEBUG")
           return True
       except Exception as e:
           debug_log(f"Error in Google TTS synthesis: {e}", "ERROR")
           return False


class AudioProcessor:
   def __init__(self):
       self.logger = logging.getLogger("AudioProcessor")
       debug_log("Initializing AudioProcessor", "INFO")
       
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
       
       # Check sound effect files
       for name, path in self.sound_effects.items():
           if os.path.exists(path):
               debug_log(f"Sound effect '{name}' found at: {path}", "INFO")
               debug_log(f"File size: {os.path.getsize(path)} bytes", "DEBUG")
           else:
               debug_log(f"Sound effect '{name}' not found at: {path}", "WARNING")
       
       debug_log("AudioProcessor initialization complete", "INFO")
   
   def _create_stt_provider(self):
       provider_name = config.get("Speech", "stt_engine", "whisper").lower()
       debug_log(f"Creating STT provider: {provider_name}", "INFO")
       
       if provider_name == "whisper" and WHISPER_AVAILABLE:
           debug_log("Creating WhisperSTT instance", "INFO")
           return WhisperSTT()
       elif provider_name == "google" and GOOGLE_STT_AVAILABLE:
           debug_log("Creating GoogleSTT instance", "INFO")
           return GoogleSTT()
       elif WHISPER_AVAILABLE:
           debug_log(f"STT provider '{provider_name}' unavailable, using Whisper as fallback", "WARNING")
           return WhisperSTT()
       elif GOOGLE_STT_AVAILABLE:
           debug_log(f"STT provider '{provider_name}' unavailable, using Google as fallback", "WARNING")
           return GoogleSTT()
           
       debug_log("No STT provider available", "ERROR")
       return None
   
   def _create_tts_provider(self):
       provider_name = config.get("Speech", "tts_engine", "elevenlabs").lower()
       debug_log(f"Creating TTS provider: {provider_name}", "INFO")
       
       if provider_name == "elevenlabs" and ELEVENLABS_AVAILABLE:
           debug_log("Creating ElevenLabsTTS instance", "INFO")
           return ElevenLabsTTS()
       elif provider_name == "google" and GTTS_AVAILABLE:
           debug_log("Creating GoogleTTS instance", "INFO")
           return GoogleTTS()
       elif ELEVENLABS_AVAILABLE:
           debug_log(f"TTS provider '{provider_name}' unavailable, using ElevenLabs as fallback", "WARNING")
           return ElevenLabsTTS()
       elif GTTS_AVAILABLE:
           debug_log(f"TTS provider '{provider_name}' unavailable, using Google as fallback", "WARNING")
           return GoogleTTS()
           
       debug_log("No TTS provider available", "ERROR")
       return None
   
   def speak(self, text, sound_effect=None):
       if sound_effect and sound_effect in self.sound_effects:
           debug_log(f"Playing sound effect: {sound_effect}", "INFO")
           try:
               sound_file = self.sound_effects[sound_effect]
               if os.path.exists(sound_file):
                   # Check pygame initialization
                   if not pygame.mixer.get_init():
                       debug_log("PyGame mixer not initialized for sound effect, initializing", "WARNING")
                       pygame.mixer.init()
                   
                   pygame.mixer.music.load(sound_file)
                   pygame.mixer.music.play()
                   debug_log(f"Playing sound effect: {sound_file}", "INFO")
                   
                   while pygame.mixer.music.get_busy():
                       pygame.time.wait(100)
                       
                   debug_log(f"Finished playing sound effect: {sound_file}", "INFO")
                   return True
               else:
                   debug_log(f"Sound effect file not found: {sound_file}", "WARNING")
           except Exception as e:
               debug_log(f"Error playing sound effect: {e}", "ERROR")
               
       if not text or not self.tts_provider:
           if not text:
               debug_log("No text provided for TTS", "INFO")
           if not self.tts_provider:
               debug_log("No TTS provider available", "ERROR")
           return False
           
       debug_log(f"Speaking text: '{text}'", "INFO")
       print("\n🔊 AI: " + text + "\n")
       return self.tts_provider.speak(text)
   
   def listen(self):
       debug_log("Starting listen() method", "INFO")
       if not self.stt_provider:
           debug_log("No STT provider available", "ERROR")
           return ""
           
       debug_log("Calling STT provider's get_input() method", "INFO")
       return self.stt_provider.get_input()
   
   def start_continuous_listening(self):
       debug_log("start_continuous_listening() called", "INFO")
       if self.is_listening:
           debug_log("Continuous listening already active", "INFO")
           return
           
       self.is_listening = True
       debug_log("Creating listen_worker thread", "INFO")
       self.listen_thread = threading.Thread(target=self._listen_worker)
       self.listen_thread.daemon = True
       self.listen_thread.start()
       debug_log("Started continuous listening thread", "INFO")
   
   def stop_continuous_listening(self):
       debug_log("stop_continuous_listening() called", "INFO")
       if not self.is_listening:
           debug_log("Continuous listening not active", "INFO")
           return
           
       self.is_listening = False
       debug_log("Set is_listening to False", "INFO")
       
       if self.listen_thread:
           debug_log("Waiting for listen thread to terminate", "INFO")
           self.listen_thread.join(timeout=1.0)
           self.listen_thread = None
           debug_log("Listen thread terminated", "INFO")
   
   def _listen_worker(self):
       debug_log("_listen_worker thread started", "INFO")
       listen_count = 0
       
       while self.is_listening:
           try:
               listen_count += 1
               debug_log(f"Starting listening cycle #{listen_count}", "INFO")
               
               text = self.listen()
               if text:
                   debug_log(f"Recognized text: '{text}'", "INFO")
                   self.audio_queue.put(text)
                   debug_log(f"Added text to audio queue: '{text}'", "INFO")
               else:
                   debug_log("No text recognized in this listening cycle", "INFO")
           except Exception as e:
               debug_log(f"Error in listening cycle: {e}", "ERROR")
               import traceback
               debug_log(f"Traceback: {traceback.format_exc()}", "ERROR")
               
           # Small delay to prevent CPU overload
           time.sleep(0.1)
       
       debug_log("_listen_worker thread exiting", "INFO")
   
   def get_next_command(self, block=True, timeout=None):
       try:
           debug_log(f"Attempting to get command from queue (block={block}, timeout={timeout})", "DEBUG")
           command = self.audio_queue.get(block=block, timeout=timeout)
           debug_log(f"Retrieved command from queue: '{command}'", "INFO")
           return command
       except queue.Empty:
           debug_log("Queue empty, no command available", "DEBUG")
           return None
   
   def get_audio_input(self):
       debug_log("get_audio_input() called", "INFO")
       return self.listen()


audio_processor = AudioProcessor()

# Check for sound effect files
activate_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sky_Tour_Activated.mp3")
deactivate_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sky_Tour_Deactivated.mp3")

if not os.path.exists(activate_file):
   debug_log(f"Activation sound file not found at {activate_file}", "WARNING")
else:
   debug_log(f"Found activation sound file at {activate_file}", "INFO")
   
if not os.path.exists(deactivate_file):
   debug_log(f"Deactivation sound file not found at {deactivate_file}", "WARNING")
else:
   debug_log(f"Found deactivation sound file at {deactivate_file}", "INFO")

# Diagnostic output of key parameters
debug_log("=== AUDIO PROCESSOR CONFIGURATION ===", "INFO")
debug_log(f"STT Engine: {config.get('Speech', 'stt_engine', 'whisper')}", "INFO")
debug_log(f"TTS Engine: {config.get('Speech', 'tts_engine', 'elevenlabs')}", "INFO")
debug_log(f"Whisper Model: {config.get('API_Models', 'whisper_model', 'base')}", "INFO")
debug_log(f"Noise Threshold: {config.getfloat('Speech', 'noise_threshold', 0.05)}", "INFO")
debug_log(f"Recording Seconds: {config.getfloat('Speech', 'recording_seconds', 5)}", "INFO")
debug_log(f"Input Device: {config.get('Audio', 'input_device', 'default')}", "INFO")
debug_log(f"Output Device: {config.get('Audio', 'output_device', 'default')}", "INFO")
debug_log("==========================================", "INFO")

def run_audio_diagnostics():
   """Run diagnostics on the audio processing system"""
   debug_log("=== RUNNING AUDIO DIAGNOSTICS ===", "INFO")
   
   # Test PyGame initialization
   debug_log("Testing PyGame initialization", "INFO")
   if pygame.mixer.get_init():
       debug_log("PyGame mixer is initialized", "INFO")
   else:
       debug_log("PyGame mixer is NOT initialized", "WARNING")
       try:
           pygame.mixer.init()
           debug_log("Successfully initialized PyGame mixer", "INFO")
       except Exception as e:
           debug_log(f"Failed to initialize PyGame mixer: {e}", "ERROR")
   
   # Test STT provider
   debug_log("Testing STT provider", "INFO")
   if audio_processor.stt_provider:
       debug_log(f"STT provider type: {type(audio_processor.stt_provider).__name__}", "INFO")
       if isinstance(audio_processor.stt_provider, WhisperSTT):
           if audio_processor.stt_provider.model:
               debug_log("Whisper model is loaded", "INFO")
           else:
               debug_log("Whisper model is NOT loaded", "ERROR")
   else:
       debug_log("No STT provider available", "ERROR")
   
   # Test TTS provider
   debug_log("Testing TTS provider", "INFO")
   if audio_processor.tts_provider:
       debug_log(f"TTS provider type: {type(audio_processor.tts_provider).__name__}", "INFO")
   else:
       debug_log("No TTS provider available", "ERROR")
   
   # Test sound effects
   debug_log("Testing sound effect file paths", "INFO")
   for name, path in audio_processor.sound_effects.items():
       if os.path.exists(path):
           debug_log(f"Sound effect '{name}' exists at: {path}", "INFO")
       else:
           debug_log(f"Sound effect '{name}' not found at: {path}", "WARNING")
   
   debug_log("Audio diagnostics complete", "INFO")
   return True

# Run diagnostics if this file is executed directly
if __name__ == "__main__":
   debug_log("Running audio_processor.py directly", "INFO")
   run_audio_diagnostics()
   
   # Test record and transcribe
   print("\n=== Testing Audio Recording and Transcription ===")
   print("This will record 5 seconds of audio and attempt to transcribe it.")
   print("Please speak clearly during the recording.")
   input("Press Enter to begin recording...")
   
   if audio_processor.stt_provider:
       print("Recording started...")
       text = audio_processor.get_audio_input()
       print(f"Transcription result: '{text}'")
   else:
       print("No STT provider available for testing.")