"""
Whisper Flight AI - Audio Processor
Version: 5.0.18
Purpose: Handles speech recognition and text-to-speech with multiple providers
Last Updated: March 31, 2025
Author: Bradley Coulter

Changes in 5.0.18:
- Added is_healthy() method for system monitor compatibility
- Ensures STT and TTS providers are available before use
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

# DO NOT import state_manager here

# --- Availability Checks ---
try:
    import speech_recognition as sr

    GOOGLE_STT_AVAILABLE = True
except ImportError:
    GOOGLE_STT_AVAILABLE = False
    logging.warning("SpeechRec N/A.")
try:
    import whisper

    WHISPER_AVAILABLE = True
    WHISPER_HAS_TIMESTAMPS = (
        hasattr(whisper.DecodingOptions(), "word_timestamps") if whisper else False
    )
except ImportError:
    WHISPER_AVAILABLE = False
    WHISPER_HAS_TIMESTAMPS = False
    logging.warning("Whisper N/A.")
except AttributeError:
    WHISPER_HAS_TIMESTAMPS = False
    logging.warning("Whisper struct changed?")
try:
    import elevenlabs

    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    logging.warning("ElevenLabs N/A.")
try:
    from gtts import gTTS

    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logging.warning("gTTS N/A.")


# --- SpeechToText Base Class and Implementations ---
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
        self.logger.debug("Recording audio started")
        device_name = config.get("Audio", "input_device", "default")
        device_index = None
        p = None
        try:
            p = pyaudio.PyAudio()
            device_count = p.get_device_count()
            if device_name != "default":
                for i in range(device_count):
                    try:
                        info = p.get_device_info_by_index(i)
                    except OSError:
                        info = None
                    if (
                        info
                        and "name" in info
                        and "maxInputChannels" in info
                        and device_name.lower() in info["name"].lower()
                        and info["maxInputChannels"] > 0
                    ):
                        device_index = i
                        self.logger.info(f"Using input: {info['name']} (Idx: {i})")
                        break
                if device_index is None:
                    self.logger.warning(
                        f"Input '{device_name}' not found, using default."
                    )
            else:
                self.logger.info("Using default audio input.")
            temp_fn = None
            stream = None
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_fn = temp_file.name
            try:
                stream = p.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self.chunk_size,
                )
                self.logger.debug("Audio stream opened.")
                frames = []
                num_chunks = int(
                    self.sample_rate / self.chunk_size * self.recording_seconds
                )
                for i in range(num_chunks):
                    try:
                        frames.append(
                            stream.read(self.chunk_size, exception_on_overflow=False)
                        )
                    except IOError as e:
                        self.logger.warning(
                            f"Audio read error: {e} (Chunk {i+1}/{num_chunks})"
                        )
                self.logger.debug("Finished reading stream.")
            finally:
                if stream:
                    try:
                        stream.stop_stream()
                        stream.close()
                        self.logger.debug("Audio stream closed.")
                    except Exception as e:
                        self.logger.error(f"Stream close error: {e}")
            try:
                with wave.open(temp_fn, "wb") as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(p.get_sample_size(self.format))
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(b"".join(frames))
                self.logger.info(f"Audio recorded: {temp_fn}")
                return temp_fn
            except Exception as e:
                self.logger.error(f"WAV write error: {e}")
                return None
        except Exception as e:
            self.logger.error(f"Recording setup error: {e}", exc_info=True)
            return None
        finally:
            if p:
                try:
                    p.terminate()
                except Exception as e:
                    self.logger.error(f"PyAudio term error: {e}")
            if (
                "temp_fn" in locals()
                and temp_fn
                and os.path.exists(temp_fn)
                and ("wf" not in locals() or not wf)
            ):
                try:
                    os.remove(temp_fn)
                    self.logger.debug("Cleaned failed temp WAV.")
                except Exception as e:
                    self.logger.warning(f"Failed cleanup temp WAV: {e}")
            elif "temp_fn" in locals() and temp_fn and not os.path.exists(temp_fn):
                pass

    def get_input(self):
        audio_file = self.record_audio()
        if not audio_file:
            self.logger.info("No audio recorded.")
            return ""
        text_result = ""
        try:
            text_result = self.transcribe(audio_file)
            # Return raw transcription result (lowercasing moved to handler)
            return text_result.strip() if text_result else ""
        except Exception as e:
            self.logger.error(f"Transcription call error: {e}", exc_info=True)
            return ""
        finally:
            try:
                if audio_file and os.path.exists(audio_file):
                    os.remove(audio_file)
                    self.logger.debug(f"Temp removed: {audio_file}")
            except Exception as e:
                self.logger.warning(f"Failed remove temp: {audio_file} ({e})")


class WhisperSTT(SpeechToText):
    def __init__(self):
        super().__init__()
        self.model = None
        self.model_name = config.get("API_Models", "whisper_model", "base")
        self.noise_threshold_conf = config.getfloat(
            "Speech", "noise_threshold", fallback=0.2
        )
        self.logger.info(
            f"WhisperSTT: Noise threshold (for VAD if used): {self.noise_threshold_conf}"
        )
        self._load_model()

    def _load_model(self):
        if not WHISPER_AVAILABLE:
            self.logger.error("Whisper N/A.")
            return
        try:
            self.logger.info(f"Loading Whisper '{self.model_name}'...")
            self.model = whisper.load_model(self.model_name)
            self.logger.info("Whisper loaded.")
        except Exception as e:
            self.logger.error(f"Whisper load error: {e}")
            self.model = None

    def transcribe(self, audio_data):
        if not self.model:
            self.logger.error("Whisper model N/A.")
            return ""
        if not os.path.exists(audio_data):
            self.logger.error(f"Audio file N/A: {audio_data}")
            return ""
        try:
            self.logger.info(f"Starting Whisper transcription: {audio_data}")
            options = {"language": "en", "fp16": False}
            if WHISPER_HAS_TIMESTAMPS:
                options["word_timestamps"] = False
            result = self.model.transcribe(audio_data, **options)
            text = result["text"].strip() if result and "text" in result else ""
            # Log raw result BEFORE returning
            self.logger.info(f"Raw Whisper result: '{text}'")
            if text.startswith("1.0.1.1"):
                self.logger.warning("Invalid numeric transcription.")
                return ""
            return text
        except Exception as e:
            self.logger.error(f"Whisper transcription error: {e}", exc_info=True)
            return ""


class GoogleSTT(SpeechToText):
    def __init__(self):
        super().__init__()
        if GOOGLE_STT_AVAILABLE:
            self.recognizer = sr.Recognizer()
        else:
            self.recognizer = None
            self.logger.error("SpeechRec N/A.")

    def transcribe(self, audio_data):
        if not self.recognizer:
            return ""
        try:
            self.logger.info(f"Starting Google STT: {audio_data}")
            with sr.AudioFile(audio_data) as source:
                audio = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio)
                self.logger.info(f"Google STT result: '{text}'")
                return text
        except sr.UnknownValueError:
            self.logger.info("Google STT: UnknownValue")
            return ""
        except sr.RequestError as e:
            self.logger.error(f"Google STT: RequestError: {e}")
            return ""
        except Exception as e:
            self.logger.error(f"Google STT Error: {e}", exc_info=True)
            return ""


# --- TextToSpeech Base Class ---
class TextToSpeech(ABC):
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
                self.logger.info("Mixer init.")
            except Exception as e:
                self.logger.error(f"Mixer init error: {e}")

    @abstractmethod
    def synthesize(self, text, output_file):
        pass

    def speak(self, text, audio_processor_instance):
        if not text:
            self.logger.info("No text to speak.")
            return False
        if not pygame.mixer.get_init():
            self.logger.error("Mixer not init.")
            return False
        temp_filename = None
        speak_success = False

        if audio_processor_instance:
            audio_processor_instance.stop_continuous_listening()
        else:
            self.logger.warning(
                "Cannot stop listening - audio_processor_instance invalid."
            )

        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                temp_filename = temp_file.name
            synthesis_ok = self.synthesize(text, temp_filename)
            if not synthesis_ok:
                self.logger.error(f"Synthesis failed: '{text[:50]}...'")
                speak_success = False
            else:
                pygame.mixer.music.load(temp_filename)
                volume = config.getfloat("Audio", "volume", 1.0)
                pygame.mixer.music.set_volume(volume)
                pygame.mixer.music.play()
                self.logger.info(f"Playing audio: '{text[:50]}...'")
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(100)
                self.logger.info(f"Finished playing: '{text[:50]}...'")
                try:
                    pygame.mixer.music.stop()
                    pygame.mixer.music.unload()
                except pygame.error as unload_err:
                    self.logger.warning(f"Error unloading music: {unload_err}")
                speak_success = True
        except Exception as e:
            self.logger.error(f"Error during speak/playback: {e}", exc_info=True)
            speak_success = False
        finally:
            time.sleep(0.1)
            try:
                if temp_filename and os.path.exists(temp_filename):
                    os.remove(temp_filename)
                    self.logger.debug(f"Temp removed: {temp_filename}")
            except Exception as e:
                self.logger.warning(f"Failed remove temp: {temp_filename} ({e})")
            # Restarting handled by StateManager

        return speak_success


# --- TextToSpeech Implementations ---
class ElevenLabsTTS(TextToSpeech):
    def __init__(self):
        super().__init__()
        pass

    def synthesize(self, text, output_file):
        # --- Keep logic from previous ---
        if not ELEVENLABS_AVAILABLE:
            self.logger.error("ElevenLabs N/A.")
            return False
        api_key = config.get_api_key("elevenlabs")
        voice_id = config.get("Audio", "elevenlabs_voice_id", "")
        if not api_key or not voice_id:
            if not api_key:
                self.logger.error("ElevenLabs key missing.")
            if not voice_id:
                self.logger.error("ElevenLabs voice_id missing.")
            return False
        try:
            self.logger.info(f"Synthesizing(11L): '{text[:50]}...'")
            import requests

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": api_key,
            }
            data = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.75, "similarity_boost": 0.75},
            }
            max_retries = 3
            timeout = 20
            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        url, json=data, headers=headers, timeout=timeout
                    )
                    response.raise_for_status()
                    with open(output_file, "wb") as f:
                        f.write(response.content)
                    self.logger.info("11L synth OK.")
                    return True
                except requests.exceptions.RequestException as e:
                    self.logger.error(
                        f"11L API err att {attempt+1}/{max_retries}: {e}",
                        exc_info=False,
                    )
                    if attempt + 1 == max_retries:
                        if GTTS_AVAILABLE:
                            self.logger.info("Falling back gTTS.")
                            return GoogleTTS().synthesize(text, output_file)
                        else:
                            return False
                    time.sleep(2**attempt)
            return False
        except Exception as e:
            self.logger.error(f"Unexpected 11L error: {e}", exc_info=True)
            return False


class GoogleTTS(TextToSpeech):
    # --- Keep logic ---
    def __init__(self):
        super().__init__()
        self.lang = config.get("API_Models", "gtts_language", "en")

    def synthesize(self, text, output_file):
        if not GTTS_AVAILABLE:
            self.logger.error("gTTS N/A.")
            return False
        try:
            self.logger.info(f"Synthesizing(gTTS): '{text[:50]}...'")
            tts = gTTS(text=text, lang=self.lang, slow=False)
            tts.save(output_file)
            self.logger.info("gTTS synth OK.")
            return True
        except Exception as e:
            self.logger.error(f"gTTS error: {e}", exc_info=True)
            return False


# --- AudioProcessor Class ---
class AudioProcessor:
    def __init__(self):
        self.logger = logging.getLogger("AudioProcessor")
        self.logger.info("Init AudioProcessor")

        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
                self.logger.info("Mixer init.")
            except Exception as e:
                self.logger.error(f"Mixer init error: {e}")

        self.stt_provider = self._create_stt_provider()
        self.tts_provider = self._create_tts_provider()
        self.audio_queue = queue.Queue()
        self.is_listening = False
        self.listen_thread = None
        self.listen_lock = threading.Lock()

        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.sound_effects = {
            "optimus_prime": os.path.join(script_dir, "Sky_Tour_Activated.mp3"),
            "deactivate": os.path.join(script_dir, "Sky_Tour_Deactivated.mp3"),
        }

        for n, p in self.sound_effects.items():
            if not os.path.exists(p):
                self.logger.warning(f"SFX N/A '{n}': {p}")
            else:
                self.logger.info(f"Found SFX '{n}': {p}")

    # New method added for system monitor compatibility
    def is_healthy(self):
        """Returns True if audio system is operational"""
        return self.stt_provider is not None and self.tts_provider is not None

    # --- _create_stt/tts_provider unchanged ---
    def _create_stt_provider(self):
        provider = config.get("Speech", "stt_engine", "whisper").lower()
        self.logger.info(f"STT engine: {provider}")
        if provider == "whisper" and WHISPER_AVAILABLE:
            return WhisperSTT()
        elif provider == "google" and GOOGLE_STT_AVAILABLE:
            return GoogleSTT()
        elif WHISPER_AVAILABLE:
            self.logger.warning("Fallback STT: Whisper")
            return WhisperSTT()
        elif GOOGLE_STT_AVAILABLE:
            self.logger.warning("Fallback STT: Google")
            return GoogleSTT()
        else:
            self.logger.error("No STT provider!")
            return None

    def _create_tts_provider(self):
        provider = config.get("Speech", "tts_engine", "elevenlabs").lower()
        self.logger.info(f"TTS engine: {provider}")
        if provider == "elevenlabs" and ELEVENLABS_AVAILABLE:
            return ElevenLabsTTS()
        elif provider == "google" and GTTS_AVAILABLE:
            return GoogleTTS()
        elif ELEVENLABS_AVAILABLE:
            self.logger.warning("Fallback TTS: 11L")
            return ElevenLabsTTS()
        elif GTTS_AVAILABLE:
            self.logger.warning("Fallback TTS: gTTS")
            return GoogleTTS()
        else:
            self.logger.error("No TTS provider!")
            return None

    def speak(self, text, sound_effect=None):
        if not pygame.mixer.get_init():
            self.logger.error("Mixer N/A.")
            return False
        played_sound = False
        if sound_effect and sound_effect in self.sound_effects:
            try:
                sound_file = self.sound_effects[sound_effect]
                if os.path.exists(sound_file):
                    # Call base speak (which stops listening) but pass empty text
                    temp_speak_success = self.tts_provider.speak("", self)
                    if temp_speak_success is not None:
                        if pygame.mixer.music.get_busy():
                            pygame.mixer.music.stop()
                            pygame.mixer.music.unload()
                            time.sleep(0.1)
                        pygame.mixer.music.load(sound_file)
                        pygame.mixer.music.play()
                        self.logger.info(f"Playing SFX: {sound_file}")
                        while pygame.mixer.music.get_busy():
                            pygame.time.wait(50)
                        pygame.mixer.music.unload()
                        played_sound = True
                else:
                    self.logger.warning(f"SFX missing: {sound_file}")
            except Exception as e:
                self.logger.error(f"Error playing SFX: {e}")
        if text and self.tts_provider:
            print(f"\n🔊 AI: {text}\n")
            return self.tts_provider.speak(text, audio_processor_instance=self)
        elif played_sound:
            return True
        else:
            return False

    def get_input(self):
        if not self.stt_provider:
            self.logger.error("No STT provider.")
            return ""
        return self.stt_provider.get_input()  # Returns raw text now

    # --- Robust Start/Stop Listening ---
    def start_continuous_listening(self):
        with self.listen_lock:
            if self.is_listening:
                self.logger.debug("Start ignored, already listening.")
                return
            if (
                hasattr(self, "listen_thread")
                and self.listen_thread
                and self.listen_thread.is_alive()
            ):
                self.logger.warning("Start: Previous listen thread alive? Stopping...")
                self._stop_listen_thread_internal()
            self.is_listening = True
            self.listen_thread = threading.Thread(
                target=self._listen_worker, daemon=True
            )
            self.listen_thread.start()
            self.logger.info("Started continuous listening thread.")

    def stop_continuous_listening(self):
        with self.listen_lock:
            self._stop_listen_thread_internal()

    def _stop_listen_thread_internal(self):
        # Internal method assumes lock is held
        if not self.is_listening and not (
            hasattr(self, "listen_thread")
            and self.listen_thread
            and self.listen_thread.is_alive()
        ):
            return
        self.is_listening = False
        thread_to_join = getattr(self, "listen_thread", None)
        if (
            thread_to_join
            and thread_to_join.is_alive()
            and threading.current_thread() != thread_to_join
        ):
            self.logger.debug("Attempting to join listening thread...")
            try:
                thread_to_join.join(timeout=0.75)  # Slightly adjusted timeout
                if thread_to_join.is_alive():
                    self.logger.warning("Listen thread failed to join!")
                else:
                    self.logger.info("Stopped continuous listening thread.")
            except Exception as e:
                self.logger.error(f"Error joining listen thread: {e}")
        elif thread_to_join == threading.current_thread():
            self.logger.warning("Stop called from listen thread itself.")
        else:
            self.logger.info("Stopped listening signal sent.")
            self.listen_thread = None  # Ensure it's cleared if already stopped

        # Clear queue after stopping
        if hasattr(self, "audio_queue"):
            count = 0
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                    count += 1
                except queue.Empty:
                    break
                except Exception:
                    break
            if count > 0:
                self.logger.debug(f"Cleared {count} items from queue on stop.")

    # --- _listen_worker ---
    def _listen_worker(self):
        """Continuously listens and puts transcription results into the queue."""
        self.logger.info("Listen worker thread started.")
        while self.is_listening:  # Check flag reliably
            try:
                text = self.get_input()  # Returns raw transcription or empty string

                # Print every result, even empty, to see what STT yields
                print(f"DEBUG STT Raw: '{text}'")

                # Only queue non-empty results *if* still listening
                if self.is_listening and text:
                    # Add basic check against simple junk here too? Optional.
                    if len(text.strip()) > 1:  # Basic check before queueing
                        self.audio_queue.put(text)
                    else:
                        self.logger.debug(
                            f"Ignoring very short STT result before queueing: '{text}'"
                        )

                # Yield control briefly
                time.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Listen worker error: {e}", exc_info=True)
                if self.is_listening:
                    time.sleep(1)  # Avoid spamming errors
        self.logger.info("Listen worker thread finished.")

    def get_next_command(self, block=True, timeout=None):
        try:
            command = self.audio_queue.get(block=block, timeout=timeout)
            self.logger.info(f"Queue retrieve: '{command}'")
            return command
        except queue.Empty:
            if block and timeout is not None:
                self.logger.debug("Timeout waiting for queue.")
            return None


# --- Singleton Instance ---
audio_processor = AudioProcessor()
