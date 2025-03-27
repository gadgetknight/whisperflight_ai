"""
Whisper Flight AI - Audio Processor
Version: 5.1.11 (Corrected for key/ID loading)
Purpose: Handles speech recognition and text-to-speech with multiple providers
Last Updated: March 26, 2025
Author: Your Name

Changes based on debugging:
- Corrected ElevenLabsTTS __init__ to remove all key/ID references.
- Moved ElevenLabsTTS API Key and Voice ID fetching into the synthesize method.
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

# --- Availability Checks (Keep as they are) ---
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

# --- SpeechToText Base Class and Implementations (Keep as they are) ---
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
    
    # record_audio method remains the same...
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
                break # Success
            except Exception as e:
                self.logger.error(f"Error recording audio (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt + 1 == max_retries:
                    p.terminate() # Terminate PyAudio if retries fail
                    return None
                time.sleep(1)
        p.terminate()
        return temp_filename
    
    # get_input method remains the same...
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
                if audio_file and os.path.exists(audio_file): # Check if exists before removing
                   os.remove(audio_file)
                   self.logger.info(f"Temporary audio file {audio_file} removed")
            except Exception as remove_e: # Catch potential errors during removal
                self.logger.warning(f"Failed to remove temporary file {audio_file}: {remove_e}")

class WhisperSTT(SpeechToText):
    # This class remains the same...
    def __init__(self):
        super().__init__()
        self.model = None
        self.model_name = config.get("API_Models", "whisper_model", "base")
        self.noise_threshold = config.getfloat("Speech", "noise_threshold", 0.05)
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
            self.logger.info(f"Raw Whisper transcription result: '{text}'") 
            if len(text) < 2 or "1.0.1" in text: # Basic check
                self.logger.info("Transcription too short or invalid, returning empty string")
                return ""
            lower_text = text.lower()
            # Keyword checks remain the same...
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
    # This class remains the same...
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

# --- TextToSpeech Base Class (Keep as is) ---
class TextToSpeech(ABC):
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        # Removed self.voice assignment here, get specific voice in subclass if needed
        # Ensure pygame mixer is initialized only once, perhaps better in AudioProcessor
        if not pygame.mixer.get_init():
             pygame.mixer.init() 
    
    @abstractmethod
    def synthesize(self, text, output_file):
        pass
    
    # speak method remains the same...
    def speak(self, text):
        if not text:
            self.logger.info("No text provided to speak")
            return False
        temp_filename = None # Define outside try block
        try:
            # Use a context manager for the temporary file
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                 temp_filename = temp_file.name

            if not self.synthesize(text, temp_filename):
                self.logger.error(f"Synthesis failed for text: '{text}'")
                # Clean up temp file if synthesis failed before playing
                if temp_filename and os.path.exists(temp_filename):
                     os.remove(temp_filename)
                return False
                
            # Check if mixer is initialized before loading/playing
            if not pygame.mixer.get_init():
                self.logger.error("Pygame mixer not initialized.")
                return False

            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            self.logger.info(f"Playing audio for text: '{text[:50]}...'")
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100) # Use pygame time wait
            self.logger.info(f"Finished playing audio for text: '{text[:50]}...'")
            
            # Stop and unload to release the file before deleting
            pygame.mixer.music.stop() 
            pygame.mixer.music.unload() 
            
            return True
        except Exception as e:
            self.logger.error(f"Error speaking text: {e}")
            return False
        finally:
            # Ensure cleanup happens even if errors occur
            try:
                # Wait a very short moment before deleting, sometimes needed on Windows
                time.sleep(0.1) 
                if temp_filename and os.path.exists(temp_filename):
                    os.remove(temp_filename)
                    self.logger.info(f"Temporary audio file {temp_filename} removed")
            except Exception as remove_e:
                self.logger.warning(f"Failed to remove temporary file {temp_filename}: {remove_e}")


# --- TextToSpeech Implementations (Corrected) ---
class ElevenLabsTTS(TextToSpeech):
    def __init__(self):
        super().__init__()
        # ** COMPLETELY EMPTY or just 'pass' **
        # No api_key or voice_id checks/storage here!
        pass 

    def synthesize(self, text, output_file):
        if not ELEVENLABS_AVAILABLE:
            self.logger.error("ElevenLabs module not available")
            return False

        # Fetch key and ID HERE, just before use
        api_key = config.get_api_key("elevenlabs") 
        voice_id = config.get("Audio", "elevenlabs_voice_id", "") 

        if not api_key or not voice_id: 
            if not api_key: self.logger.error("ElevenLabs API key not found in environment or .env file.")
            if not voice_id: self.logger.error("ElevenLabs voice ID not found in config.ini [Audio] section.")
            return False

        try:
            self.logger.info(f"Synthesizing text with ElevenLabs (Voice ID: {voice_id}): '{text[:50]}...'") 
            import requests # Import requests here if not imported globally
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}" 
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": api_key 
            }
        
            data = {
                "text": text,
                "model_id": "eleven_monolingual_v1", # Consider making this configurable
                "voice_settings": {"stability": 0.75, "similarity_boost": 0.75} # Consider making these configurable
            }
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = requests.post(url, json=data, headers=headers, timeout=20) # Increased timeout
                    response.raise_for_status() # Check for HTTP errors (4xx, 5xx)
                    with open(output_file, "wb") as f:
                        f.write(response.content)
                    self.logger.info("Successfully generated audio with ElevenLabs")
                    return True
                except requests.exceptions.RequestException as e: # Catch specific request errors
                    self.logger.error(f"Error in ElevenLabs synthesis attempt {attempt + 1}/{max_retries}: {str(e)}")
                    if attempt + 1 == max_retries:
                         self.logger.error("ElevenLabs failed after multiple retries.")
                         # Optional: Fallback to Google TTS if available
                         if GTTS_AVAILABLE:
                             self.logger.info("Falling back to Google TTS")
                             return GoogleTTS().synthesize(text, output_file)
                         else:
                             return False # No fallback available
                    time.sleep(2 ** attempt) # Exponential backoff
            return False # Should not be reached if logic above is correct, but as safety
        except Exception as e: # Catch any other unexpected errors
            self.logger.error(f"Unexpected error in ElevenLabs synthesis: {e}")
            return False

class GoogleTTS(TextToSpeech):
    # This class remains the same...
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

# --- AudioProcessor Class (Keep as is, relies on corrected providers) ---
class AudioProcessor:
    def __init__(self):
        self.logger = logging.getLogger("AudioProcessor")
        self.logger.info("Initializing AudioProcessor")
        # Ensure pygame mixer is initialized once here
        if not pygame.mixer.get_init():
             pygame.mixer.init() 
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
        # Check if sound files exist during init
        for name, path in self.sound_effects.items():
            if os.path.exists(path):
                 self.logger.info(f"Found sound effect '{name}': {path}")
            else:
                 self.logger.warning(f"Sound effect file not found for '{name}': {path}")
    
    def _create_stt_provider(self):
        provider_name = config.get("Speech", "stt_engine", "whisper").lower()
        if provider_name == "whisper" and WHISPER_AVAILABLE:
            return WhisperSTT()
        elif provider_name == "google" and GOOGLE_STT_AVAILABLE:
            # Add check for Google STT API key here if needed by SpeechRecognition library setup
            # key = config.get_api_key("google_stt") 
            # if not key: self.logger.error("Google STT key not found.") ; return None
            return GoogleSTT()
        elif WHISPER_AVAILABLE:
            self.logger.warning(f"STT provider '{provider_name}' unavailable, falling back to Whisper")
            return WhisperSTT()
        elif GOOGLE_STT_AVAILABLE:
             self.logger.warning(f"STT provider '{provider_name}' unavailable, falling back to Google")
             return GoogleSTT()
        else:
             self.logger.error("No STT provider available")
             return None
    
    def _create_tts_provider(self):
        provider_name = config.get("Speech", "tts_engine", "elevenlabs").lower()
        self.logger.info(f"Selected TTS engine: {provider_name}")
        if provider_name == "elevenlabs" and ELEVENLABS_AVAILABLE:
            # No need to check keys here anymore, done in synthesize
            return ElevenLabsTTS() 
        elif provider_name == "google" and GTTS_AVAILABLE:
             # No need to check keys here anymore (gTTS doesn't use key directly)
            return GoogleTTS()
        # Fallback logic
        elif ELEVENLABS_AVAILABLE:
            self.logger.warning(f"TTS provider '{provider_name}' unavailable, falling back to ElevenLabs")
            return ElevenLabsTTS()
        elif GTTS_AVAILABLE:
            self.logger.warning(f"TTS provider '{provider_name}' unavailable, falling back to Google")
            return GoogleTTS()
        else:
            self.logger.error("No TTS provider available")
            return None
    
    def speak(self, text, sound_effect=None):
        # Check mixer init just in case
        if not pygame.mixer.get_init():
             self.logger.error("Pygame mixer not initialized in speak().")
             # Optionally try to init again: pygame.mixer.init()
             return False
             
        if sound_effect and sound_effect in self.sound_effects:
            try:
                sound_file = self.sound_effects[sound_effect]
                if os.path.exists(sound_file):
                    # Stop potentially playing music first
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.stop()
                        pygame.mixer.music.unload() # Ensure unloaded
                        time.sleep(0.1) # Short pause after stopping

                    pygame.mixer.music.load(sound_file)
                    pygame.mixer.music.play()
                    self.logger.info(f"Playing sound effect: {sound_file}")
                    # Wait for sound effect to finish
                    while pygame.mixer.music.get_busy():
                        pygame.time.wait(100)
                    # Don't return True here if text should also be spoken
                else:
                    self.logger.warning(f"Sound effect file not found: {sound_file}")
            except Exception as e:
                self.logger.error(f"Error playing sound effect: {e}")
                # Continue to speaking text even if sound effect fails

        if not text or not self.tts_provider:
            if not text: self.logger.info("No text provided to speak (after sound effect check).")
            if not self.tts_provider: self.logger.error("No TTS provider available")
            return False
            
        print("\n🔊 AI: " + text + "\n") # Keep console output for now
        # TTS provider's speak method handles actual synthesis and playback
        return self.tts_provider.speak(text) 
    
    # listen, start/stop_continuous_listening, _listen_worker, 
    # get_next_command, get_audio_input methods remain the same...
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
        # Ensure thread resources are cleaned up if method called again
        if self.listen_thread and self.listen_thread.is_alive():
             self.logger.warning("Previous listen thread still alive? Attempting to stop.")
             self.stop_continuous_listening() # Attempt cleanup first

        self.listen_thread = threading.Thread(target=self._listen_worker, daemon=True)
        self.listen_thread.start()
        self.logger.info("Started continuous listening thread")
    
    def stop_continuous_listening(self):
        if not self.is_listening and not (self.listen_thread and self.listen_thread.is_alive()):
             self.logger.info("Continuous listening already stopped.")
             return

        self.is_listening = False
        if self.listen_thread and self.listen_thread.is_alive():
             try:
                 # Don't wait indefinitely, especially if thread is stuck
                 self.listen_thread.join(timeout=1.5) 
                 if self.listen_thread.is_alive():
                      self.logger.warning("Listen thread did not terminate gracefully.")
             except Exception as e:
                 self.logger.error(f"Error stopping listen thread: {e}")
        self.listen_thread = None
        # Clear the queue on stop? Optional, depends on desired behavior.
        # while not self.audio_queue.empty():
        #    try: self.audio_queue.get_nowait()
        #    except queue.Empty: break
        self.logger.info("Stopped continuous listening thread")
    
    def _listen_worker(self):
        while self.is_listening:
            try:
                 text = self.listen()
                 if text:
                     self.audio_queue.put(text)
                 # Add a small sleep to prevent busy-waiting if listen() returns quickly
                 time.sleep(0.1) 
            except Exception as e:
                 self.logger.error(f"Error in listen worker loop: {e}")
                 # Avoid continuous error spamming
                 time.sleep(1)

    def get_next_command(self, block=True, timeout=None):
        try:
            command = self.audio_queue.get(block=block, timeout=timeout)
            self.logger.info(f"Retrieved command from queue: '{command}'")
            return command
        except queue.Empty:
            # Don't log every time it's empty if non-blocking, only if timeout occurs
            if block and timeout is not None: 
                 self.logger.info("Timeout waiting for command in queue.")
            return None
    
    def get_audio_input(self):
        # This seems redundant with listen(), maybe intended for one-off recording?
        # Keeping it as it was unless specific different behavior is needed.
        return self.listen()

# --- Singleton Instance ---
# Ensure logger is configured before creating instance if not already done globally
# logging.basicConfig(level=logging.INFO) # Example if needed here
audio_processor = AudioProcessor()

# --- Sound File Check (Keep as is, already done in __init__) ---
# activate_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sky_Tour_Activated.mp3")
# deactivate_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Sky_Tour_Deactivated.mp3")
# ... (logging checks already moved to __init__) ...