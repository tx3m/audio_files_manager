import json
import time
import logging
import wave
import shutil
from pathlib import Path
from datetime import datetime
import platform
import tempfile
from threading import Event
from typing import Any, Dict, Optional, Union

try:
    if platform.system() == "Linux":
        import alsaaudio
        AUDIO_BACKEND = "alsaaudio"
    else:
        import sounddevice as sd
        import numpy as np
        AUDIO_BACKEND = "sounddevice"
except ImportError:
    AUDIO_BACKEND = None

logger = logging.getLogger(__name__)


class AudioFileManager:
    def __init__(self, storage_dir: Optional[Union[str, Path]] = None, metadata_file: Optional[Union[str, Path]] = None, num_buttons: int = 16):
        if storage_dir is None:
            base_dir = Path.home() / ".audio_files_manager"
            storage_dir = base_dir / "storage"
            if metadata_file is None:
                metadata_file = base_dir / "metadata.json"

        self.storage_dir = Path(storage_dir)
        self.metadata_file = Path(metadata_file) if metadata_file else self.storage_dir.parent / "metadata.json"
        self._temp_dir_obj = tempfile.TemporaryDirectory(prefix="audio_staging_")
        self.temp_dir = Path(self._temp_dir_obj.name)
        self.num_buttons = num_buttons

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.metadata: Dict[str, Dict[str, Any]] = self._load_metadata()
        logger.info(f"AudioFileManager initialized. Storage: {self.storage_dir}")

    def _load_metadata(self) -> Dict[str, Dict[str, Any]]:
        if self.metadata_file.exists():
            logger.debug(f"Loading metadata from {self.metadata_file}")
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_metadata(self):
        with open(self.metadata_file, 'w') as f:
            logger.debug(f"Saving metadata to {self.metadata_file}")
            json.dump(self.metadata, f, indent=4)

    def record_audio_to_temp(self, button_id: Union[str, int], message_type: str, stop_event: Event, channels: int = 1, rate: int = 44100) -> Dict[str, Any]:
        """
            Records audio from the system microphone to a temporary WAV file until the provided stop_event is triggered.

            The recording is platform-aware:
            - On Linux: Uses ALSA via pyalsaaudio
            - On Windows/macOS: Uses sounddevice

            Audio data is streamed in real time, accumulated in memory, and written to a WAV file once stopped.
            The duration is calculated based on the recorded byte length.

        :param button_id: (str or int) ID representing the logical button associated with this recording.
        :param message_type: Semantic label or category for the audio (away, custom, etc.)
        :param stop_event: A live threading event object. When set, recording stops.
        :param channels: Number of channels to record. Default is 1 (mono).
        :param rate: Sample rate in Hz. Default is 44100.
        :return: dict: A metadata dictionary with the following keys:
            - 'button_id': Button ID used
            - 'message_type': Provided label for the message
            - 'duration': Length of the recording in seconds (float)
            - 'temp_path': Absolute path to the temporary WAV file
            - 'timestamp': UTC timestamp of the recording start
        """
        button_id = str(button_id)
        keyword = message_type.lower().replace(" ", "_")
        filename = f"{button_id}_{keyword}_{int(time.time())}.wav"
        temp_path = self.temp_dir / filename
        timestamp = datetime.utcnow().isoformat()
        pcm_bytes = b''
        # For S16_LE format, each sample is 2 bytes
        sample_width_bytes = 2

        if AUDIO_BACKEND == "alsaaudio":
            inp = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NORMAL)
            inp.setchannels(channels)
            inp.setrate(rate)
            inp.setformat(alsaaudio.PCM_FORMAT_S16_LE)
            inp.setperiodsize(1024)

            frames = []
            while not stop_event.is_set():
                length, data = inp.read()
                if length:
                    frames.append(data)
            pcm_bytes = b''.join(frames)

        elif AUDIO_BACKEND == "sounddevice":
            import queue

            q = queue.Queue()

            def callback(indata, frames, time, status):
                if stop_event.is_set():
                    raise sd.CallbackStop()
                q.put(indata.copy())

            audio_chunks = []

            with sd.InputStream(callback=callback, channels=channels, samplerate=rate, dtype='int16'):
                while not stop_event.is_set():
                    try:
                        data = q.get(timeout=0.1)
                        audio_chunks.append(data)
                    except queue.Empty:
                        continue

            if audio_chunks:
                all_audio = np.concatenate(audio_chunks)
                pcm_bytes = all_audio.tobytes()
            else:
                # If no audio was captured, pcm_bytes remains empty
                pcm_bytes = b''

        else:
            raise NotImplementedError("No supported audio backend available on this platform.")

        duration = len(pcm_bytes) / (rate * channels * sample_width_bytes)
        with wave.open(str(temp_path), 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(pcm_bytes)

        return {
            "button_id": button_id,
            "message_type": message_type,
            "duration": round(duration, 2),
            "temp_path": str(temp_path),
            "timestamp": timestamp
        }

    def play_audio(self, file_path: Union[str, Path]) -> None:
        """
        Plays the audio from the given WAV file.

        This functionality is only supported on platforms using the 'sounddevice' backend
        (e.g., Windows and macOS).

        :param file_path: The absolute path to the WAV file to be played.
        """
        if AUDIO_BACKEND != "sounddevice":
            logger.warning("Playback is only supported with the 'sounddevice' backend.")
            raise NotImplementedError("Playback not supported on this audio backend.")

        import sounddevice as sd
        import numpy as np

        path = Path(file_path)
        if not path.exists():
            logger.error(f"Cannot play audio: file not found at {path}")
            return

        try:
            with wave.open(str(path), 'rb') as wf:
                samplerate = wf.getframerate()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                n_frames = wf.getnframes()
                audio_bytes = wf.readframes(n_frames)

            # The recorder uses 16-bit audio, so we expect that for playback.
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

            logger.info(f"Playing audio from {path}...")
            sd.play(audio_array, samplerate=samplerate, blocking=True)
            logger.info("Playback finished.")
        except Exception as e:
            logger.error(f"Failed to play audio file {path}: {e}")

    def finalize_recording(self, temp_path_info: Dict[str, Any]) -> None:
        button_id = str(temp_path_info["button_id"])
        if self.metadata.get(button_id, {}).get('read_only'):
            logger.warning(f"Finalizing recording blocked: Button {button_id} is read-only.")
            return

        final_path = self.storage_dir / Path(temp_path_info["temp_path"]).name
        shutil.move(temp_path_info["temp_path"], final_path)
        logger.info(f"Finalized recording for button '{button_id}' to {final_path}")

        self.metadata[button_id] = {
            "name": final_path.name,
            "duration": temp_path_info["duration"],
            "path": str(final_path),
            "timestamp": temp_path_info["timestamp"],
            "message_type": temp_path_info["message_type"],
            "audio_format": "wav",
            "read_only": False,
            "is_default": False
        }
        self._save_metadata()

    def cleanup(self) -> None:
        """Removes the temporary directory and all its contents."""
        self._temp_dir_obj.cleanup()

    def discard_recording(self, button_id: Union[str, int]) -> None:
        button_id = str(button_id)
        for f in self.temp_dir.glob(f"{button_id}_*.wav"):
            f.unlink()

    def set_read_only(self, button_id: Union[str, int], read_only: bool = True) -> None:
        button_id = str(button_id)
        if button_id not in self.metadata:
            return
        self.metadata[button_id]['read_only'] = read_only
        self._save_metadata()

    def get_recording_info(self, button_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        return self.metadata.get(str(button_id))

    def list_all_recordings(self) -> Dict[str, Dict[str, Any]]:
        return self.metadata

    def assign_default(self, button_id: Union[str, int], file_path: Union[str, Path]) -> None:
        button_id = str(button_id)
        if not Path(file_path).exists():
            logger.error(f"Cannot assign default: source file not found at {file_path}")
            return

        default_name = f"default_{button_id}.wav"
        default_path = self.storage_dir / default_name
        shutil.copy(file_path, default_path)

        duration = None
        try:
            with wave.open(str(default_path), 'rb') as wf:
                duration = round(wf.getnframes() / float(wf.getframerate()), 2)
        except wave.Error:
            logger.warning(f"Could not read duration from {default_path}. Duration set to None.")

        self.metadata[button_id] = {
            "name": default_name,
            "duration": duration,
            "path": str(default_path),
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": "default",
            "audio_format": "wav",
            "read_only": True,
            "is_default": True
        }
        self._save_metadata()

    def restore_default(self, button_id: Union[str, int]) -> None:
        button_id = str(button_id)
        default_path = self.storage_dir / f"default_{button_id}.wav"
        if not default_path.exists():
            logger.warning(f"Cannot restore default for '{button_id}': default file not found.")
            return

        restored_path = self.storage_dir / f"{button_id}_restored_{int(time.time())}.wav"
        shutil.copy(default_path, restored_path)

        duration = None
        try:
            with wave.open(str(restored_path), 'rb') as wf:
                duration = round(wf.getnframes() / float(wf.getframerate()), 2)
        except wave.Error:
            logger.warning(f"Could not read duration from restored file {restored_path}. Duration set to None.")


        self.metadata[button_id] = {
            "name": restored_path.name,
            "duration": duration,
            "path": str(restored_path),
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": "restored_default",
            "audio_format": "wav",
            "read_only": False,
            "is_default": False
        }
        self._save_metadata()
