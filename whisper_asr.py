"""
S.P.I.D.Y — OpenAI Whisper ASR Module
Python-side speech recognition — more accurate than browser!
Supports: English, Tamil, Hindi, and 99 other languages!
"""

import whisper
import sounddevice as sd
import soundfile as sf
import numpy as np
import threading
import tempfile
import os
import time

class WhisperASR:
    """
    OpenAI Whisper-based Automatic Speech Recognition.
    Records audio from microphone and transcribes using Whisper.
    
    Models: tiny (39M), base (74M), small (244M), medium (769M)
    Recommend: 'base' for good accuracy + speed balance.
    """

    def __init__(self, model_size='base'):
        self.model = None
        self.model_size = model_size
        self.loaded = False
        self.loading = False
        self.is_recording = False
        self.sample_rate = 16000  # Whisper expects 16kHz
        self.recording_data = []
        # Load model in background
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        self.loading = True
        try:
            print(f"Loading Whisper {self.model_size} model...")
            self.model = whisper.load_model(self.model_size)
            self.loaded = True
            print(f"Whisper ASR Model LOADED! ({self.model_size})")
        except Exception as e:
            print(f"Whisper load failed: {e}")
            self.loaded = False
        self.loading = False

    def record_audio(self, duration=5, language='en'):
        """
        Record audio from microphone for given duration.
        Returns transcribed text.
        """
        if not self.loaded:
            return None, "Whisper model not loaded yet!"

        try:
            print(f"Recording for {duration} seconds...")
            # Record audio
            audio_data = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32'
            )
            sd.wait()  # Wait for recording to complete

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name
                sf.write(tmp_path, audio_data, self.sample_rate)

            # Transcribe with Whisper
            result = self.model.transcribe(
                tmp_path,
                language=language if language != 'auto' else None,
                task='transcribe'
            )

            # Cleanup temp file
            os.unlink(tmp_path)

            text = result['text'].strip()
            detected_lang = result.get('language', language)
            return text, detected_lang

        except Exception as e:
            return None, f"Recording error: {str(e)}"

    def transcribe_audio_file(self, audio_path, language='auto'):
        """
        Transcribe an existing audio file.
        Used when browser sends audio blob to Flask.
        """
        if not self.loaded:
            return None, "Whisper model not loaded!"

        try:
            result = self.model.transcribe(
                audio_path,
                language=language if language != 'auto' else None,
                task='transcribe'
            )
            text = result['text'].strip()
            detected_lang = result.get('language', 'unknown')
            return text, detected_lang
        except Exception as e:
            return None, f"Transcription error: {str(e)}"

    def transcribe_from_bytes(self, audio_bytes, language='auto'):
        if not self.loaded:
            return None, "Whisper model not loaded!"

        try:
            import tempfile, os
            from pydub import AudioSegment
            import pydub.utils

            # Set ffmpeg path directly
            FFMPEG_PATH = r"C:\Users\ACER\Documents\Projects\Spidy\ffmpeg-master-latest-win64-gpl-shared\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe"
            FFPROBE_PATH = r"C:\Users\ACER\Documents\Projects\Spidy\ffmpeg-master-latest-win64-gpl-shared\ffmpeg-master-latest-win64-gpl-shared\bin\ffprobe.exe"

            if os.path.exists(FFMPEG_PATH):
                pydub.utils.get_prober_name = lambda: FFPROBE_PATH
                AudioSegment.converter = FFMPEG_PATH
                AudioSegment.ffmpeg = FFMPEG_PATH
                AudioSegment.ffprobe = FFPROBE_PATH
                print(f"ffmpeg found: {FFMPEG_PATH}")
            else:
                print(f"ffmpeg not found at: {FFMPEG_PATH}")
                return None, "ffmpeg not found!"

            # Save raw bytes to temp file
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
                tmp.write(audio_bytes)
                webm_path = tmp.name

            wav_path = webm_path.replace('.webm', '.wav')

            # Convert WebM → WAV
            audio = AudioSegment.from_file(webm_path, format='webm')
            audio = audio.set_frame_rate(16000).set_channels(1)
            audio.export(wav_path, format='wav')

            # Transcribe with Whisper
            result = self.model.transcribe(
                wav_path,
                language=language if language != 'auto' else None,
                task='transcribe',
                fp16=False
            )

            # Cleanup
            try:
                os.unlink(webm_path)
                os.unlink(wav_path)
            except:
                pass

            text = result['text'].strip()
            detected_lang = result.get('language', 'unknown')

            if not text:
                return None, "No speech detected"

            return text, detected_lang

        except Exception as e:
            print(f"Whisper transcribe error: {e}")
            return None, f"Error: {str(e)}"

    def get_status(self):
        if self.loaded:
            return f"loaded ({self.model_size})"
        elif self.loading:
            return f"loading {self.model_size}..."
        else:
            return "failed"


# Global instance
whisper_asr = WhisperASR(model_size='tiny')