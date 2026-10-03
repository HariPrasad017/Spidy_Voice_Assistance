"""
S.P.I.D.Y — OpenAI Whisper Automatic Speech Recognition Module
Handles browser WebM/Opus blobs and microphone recordings with CUDA acceleration,
robust FFmpeg path resolution, silence handling, and automatic temporary file cleanup.

FIX v5.2.1: Replaced pydub AudioSegment.from_file() with a direct FFmpeg subprocess
call to eliminate the KeyError('sample_width') crash that occurs for WebM/Opus audio
in pydub 0.25.1 on Windows when ffprobe is not in PATH or when codec_name='opus'
(bits_per_sample=0, triggering invalid 'pcm_s0le' acodec).
"""

import os
import shutil
import tempfile
import subprocess
import logging
import torch
import whisper
from config import (
    WHISPER_MODEL_SIZE,
    WHISPER_LANGUAGE,
    FFMPEG_AVAILABLE,
    FFMPEG_PATH,
    TORCH_DEVICE,
    logger
)


class WhisperASR:
    """
    OpenAI Whisper Automatic Speech Recognition Engine.
    Configured for high accuracy voice command recognition.
    """

    def __init__(self, model_size=None, auto_load=True):
        self.model = None
        self.model_size = model_size or WHISPER_MODEL_SIZE
        self.device = TORCH_DEVICE if TORCH_DEVICE else torch.device('cpu')
        self.loaded = False
        self.loading = False

        if auto_load:
            self.load_model()

    def load_model(self):
        """
        Loads the Whisper model deterministically onto CUDA if available, else CPU.
        """
        if self.loaded:
            return True

        self.loading = True
        try:
            device_str = 'cuda' if torch.cuda.is_available() else 'cpu'
            logger.info(f"Loading Whisper model '{self.model_size}' on {device_str}...")
            self.model = whisper.load_model(self.model_size, device=device_str)
            self.loaded = True
            logger.info(f"OpenAI Whisper ASR READY! ({self.model_size} on {device_str})")
        except Exception as e:
            logger.error(f"Whisper model load failed: {e}")
            self.loaded = False
        finally:
            self.loading = False

        return self.loaded

    def _get_ffmpeg_path(self):
        """
        Returns the absolute path to the ffmpeg executable.
        Prefers the path discovered by config.py, then falls back to PATH lookup.
        """
        if FFMPEG_PATH and os.path.isfile(FFMPEG_PATH):
            return FFMPEG_PATH
        found = shutil.which("ffmpeg")
        if found:
            return found
        return None

    def _convert_to_wav_via_ffmpeg(self, input_path: str, output_path: str) -> bool:
        """
        Converts any audio file (WebM/Opus, WAV, MP3, OGG, etc.) to 16 kHz mono
        PCM WAV using a direct FFmpeg subprocess call.

        WHY THIS REPLACES pydub.AudioSegment.from_file():
        ──────────────────────────────────────────────────
        pydub 0.25.1 probes the input file with ffprobe before running ffmpeg.
        For a WebM container with Opus audio, ffprobe reports:

            codec_name      = 'opus'
            sample_fmt      = 'fltp'
            bits_per_sample = 0          <-- ffprobe cannot determine this for Opus

        pydub's workaround for fltp/bits_per_sample=0 only fires when codec_name
        is one of ['mp3','mp4','aac','webm','ogg'].  'opus' is NOT in that list.
        So bits_per_sample=0 reaches:

            acodec = 'pcm_s%dle' % 0    => 'pcm_s0le'  (invalid FFmpeg codec)

        FFmpeg then fails, p_out is empty, cls(p_out) gets broken WAV bytes,
        read_wav_audio() returns None, and AudioSegment.__init__ raises:

            KeyError: 'sample_width'

        Additionally, on this machine ffprobe is NOT on the system PATH (only
        ffmpeg is discoverable via the custom path set in config.py), so
        pydub's mediainfo_json() raises FileNotFoundError on every call.

        This direct FFmpeg subprocess approach is codec-agnostic: FFmpeg
        auto-detects the container+codec without needing ffprobe metadata,
        and always produces correct 16 kHz mono PCM WAV output.

        Returns True on success, False on failure.
        """
        ffmpeg_exe = self._get_ffmpeg_path()
        if not ffmpeg_exe:
            logger.error("FFmpeg executable not found — cannot convert audio.")
            return False

        cmd = [
            ffmpeg_exe,
            "-y",                 # overwrite output without prompting
            "-loglevel", "error", # suppress noisy info; only show real errors
            "-i", input_path,     # input: any format FFmpeg understands
            "-ar", "16000",       # output sample rate: 16 kHz (Whisper requirement)
            "-ac", "1",           # output channels: mono
            "-f", "wav",          # output format: WAV (defaults to pcm_s16le)
            output_path
        ]

        logger.debug(f"FFmpeg cmd: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                logger.error(
                    f"FFmpeg conversion failed (rc={result.returncode}): "
                    f"{result.stderr.strip()[:300]}"
                )
                return False
            if not os.path.exists(output_path) or os.path.getsize(output_path) < 44:
                logger.error(f"FFmpeg produced no usable output at {output_path}")
                return False
            logger.info(
                f"FFmpeg conversion success: {os.path.getsize(output_path)} bytes WAV"
            )
            return True
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg conversion timed out (60 s).")
            return False
        except Exception as exc:
            logger.error(f"FFmpeg subprocess error: {exc}")
            return False

    def transcribe_audio_file(self, audio_path: str, language: str = 'auto'):
        """
        Transcribes an existing audio file on disk.
        """
        if not self.loaded or not self.model:
            return None, "Whisper model not loaded"

        if not os.path.exists(audio_path):
            return None, "Audio file not found"

        try:
            target_lang = None if language in [None, '', 'auto'] else language
            use_fp16 = torch.cuda.is_available()

            result = self.model.transcribe(
                audio_path,
                language=target_lang,
                task='transcribe',
                fp16=use_fp16,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                temperature=0.0
            )

            text = result.get('text', '').strip()
            detected_lang = result.get('language', 'unknown')
            return text, detected_lang
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            return None, f"Transcription error: {str(e)}"

    def transcribe_from_bytes(self, audio_bytes: bytes, language: str = 'auto'):
        """
        Processes audio bytes received from browser MediaRecorder
        (WebM/Opus, WAV, MP3, OGG, etc.) and returns a transcription.

        Pipeline:
            1. Validate input size
            2. Persist bytes to a named temp file (.webm extension)
            3. Convert to 16 kHz mono WAV via direct FFmpeg subprocess  [BUG FIX]
            4. Validate output WAV
            5. Run Whisper transcription
            6. Clean up all temp files (guaranteed via finally block)
        """
        # ── Guard: empty or trivially small input ────────────────────────────
        if not audio_bytes or len(audio_bytes) < 100:
            logger.warning(
                f"transcribe_from_bytes: rejecting upload — "
                f"{len(audio_bytes) if audio_bytes else 0} bytes (< 100 byte minimum)."
            )
            return None, "Audio input is empty or too short."

        if not self.loaded:
            return None, "Whisper model is still loading. Please retry in a moment."

        ffmpeg_exe = self._get_ffmpeg_path()
        if not ffmpeg_exe:
            return None, "FFmpeg is not available. Audio conversion cannot proceed."

        temp_input_path = None
        temp_wav_path = None

        try:
            # ── 1. Persist raw browser audio bytes to disk ───────────────────
            # Use .webm extension: gives FFmpeg a correct demuxer hint and avoids
            # any accidental extension-based path in pydub (e.g. '.tmp' would
            # still trigger the broken pydub path in the fallback).
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp_in:
                tmp_in.write(audio_bytes)
                temp_input_path = tmp_in.name

            input_size = len(audio_bytes)
            logger.info(
                f"Whisper upload received: {input_size} bytes, "
                f"temp={os.path.basename(temp_input_path)}"
            )
            if input_size < 1000:
                logger.warning(
                    f"Whisper: upload is suspiciously small ({input_size} bytes). "
                    "Possible silent/empty recording."
                )

            temp_wav_path = temp_input_path + ".wav"

            # ── 2. Convert to 16 kHz mono WAV via direct FFmpeg subprocess ───
            logger.info("Whisper: converting audio to 16 kHz mono WAV via FFmpeg...")
            conversion_ok = self._convert_to_wav_via_ffmpeg(temp_input_path, temp_wav_path)

            if not conversion_ok:
                return None, "Audio conversion failed. FFmpeg could not process the file."


            # ── 3. Validate output WAV ────────────────────────────────────────
            if not os.path.exists(temp_wav_path):
                return None, "Converted WAV file does not exist."

            wav_size = os.path.getsize(temp_wav_path)
            logger.info(f"Whisper: WAV output = {wav_size} bytes")

            if wav_size < 44:
                return None, "Converted WAV file is empty or malformed."

            # Rough duration check: WAV PCM s16le mono at 16 kHz
            # 1 sample = 2 bytes; duration_ms = (data_bytes / 2 / 16000) * 1000
            estimated_ms = max(0, (wav_size - 44) / 2 / 16000 * 1000)
            logger.info(f"Whisper: estimated audio duration ≈ {estimated_ms:.0f} ms")
            if estimated_ms < 200:
                return None, "Audio recording too short (< 200 ms)."

            # ── 4. Transcribe with Whisper ────────────────────────────────────
            logger.info(f"Whisper: running transcription (language='{language}')...")
            text, detected_lang = self.transcribe_audio_file(temp_wav_path, language=language)

            if text:
                logger.info(
                    f"Whisper: transcription complete — "
                    f"'{text[:80]}' (lang='{detected_lang}')"
                )
                return text, detected_lang
            else:
                logger.info("Whisper: model returned no text — no speech detected.")
                return None, "No speech detected in audio."

        except Exception as exc:
            logger.error(f"Whisper processing error: {exc}", exc_info=True)
            return None, f"Whisper processing error: {str(exc)}"

        finally:
            # ── 5. Guaranteed cleanup of all temp files ───────────────────────
            for p in [temp_input_path, temp_wav_path]:
                if p and os.path.exists(p):
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

    def record_audio(self, duration: int = 5, language: str = 'auto'):
        """
        Direct recording via sounddevice (optional desktop microphone).
        """
        if not self.loaded or not self.model:
            return None, "Whisper model not loaded."

        temp_wav = None
        try:
            import sounddevice as sd
            import soundfile as sf

            sample_rate = 16000
            logger.info(f"Direct recording from mic for {duration} seconds...")
            audio_data = sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype='float32'
            )
            sd.wait()

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                temp_wav = tmp.name
                sf.write(temp_wav, audio_data, sample_rate)

            text, detected_lang = self.transcribe_audio_file(temp_wav, language=language)
            return text, detected_lang

        except Exception as e:
            logger.error(f"Microphone recording error: {e}")
            return None, f"Microphone error: {str(e)}"
        finally:
            if temp_wav and os.path.exists(temp_wav):
                try:
                    os.unlink(temp_wav)
                except Exception:
                    pass

    def get_status(self):
        device_str = 'cuda' if torch.cuda.is_available() else 'cpu'
        if self.loaded:
            return f"loaded ({self.model_size} on {device_str})"
        elif self.loading:
            return f"loading {self.model_size}..."
        return "failed"


# Global singleton instance
whisper_asr = WhisperASR(auto_load=True)