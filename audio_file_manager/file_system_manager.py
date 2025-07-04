"""
Manages file system operations for the audio files.
"""
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FileSystemManager:
    """Handles file paths, temporary files, and format conversions."""

    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize the FileSystemManager.

        Args:
            storage_dir: The main directory for storing audio files.
        """
        if storage_dir is None:
            self.storage_dir = Path.home() / ".audio_files_manager" / "storage"
        else:
            self.storage_dir = storage_dir

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._temp_dir_obj = tempfile.TemporaryDirectory(prefix="audio_staging_")
        self.temp_dir = Path(self._temp_dir_obj.name)

    def get_storage_dir(self) -> Path:
        """
        Get the main storage directory for audio files.

        Returns:
            The path to the storage directory.
        """
        return self.storage_dir

    def get_temp_dir(self) -> Path:
        """
        Get the temporary directory for staging recordings.

        Returns:
            The path to the temporary directory.
        """
        return self.temp_dir

    def move_to_storage(self, source: Path, dest_name: str) -> Path:
        """
        Move a file to the main storage directory.

        Args:
            source: The source path of the file to move.
            dest_name: The name of the file in the destination directory.

        Returns:
            The final path of the moved file.
        """
        dest_path = self.storage_dir / dest_name
        shutil.move(source, dest_path)
        return dest_path

    def convert_audio_format(self, input_path: Path, output_path: Path, target_format: str,
                             sample_rate: int, channels: int) -> bool:
        """
        Convert audio format using FFmpeg.

        Args:
            input_path: Path to the input audio file.
            output_path: Path to save the converted audio file.
            target_format: The target audio format ('alaw' or 'ulaw').
            sample_rate: The sample rate for the conversion.
            channels: The number of channels for the conversion.

        Returns:
            True if conversion was successful, False otherwise.
        """
        if target_format not in ["alaw", "ulaw"]:
            return False

        codec_out = "pcm_alaw" if target_format == "alaw" else "pcm_mulaw"
        command = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-c:a", codec_out,
            "-ar", str(sample_rate),
            "-ac", str(channels),
            str(output_path)
        ]

        try:
            process = subprocess.run(command, capture_output=True, timeout=10, text=True, check=True)
            logger.info(f"Successfully converted {input_path} to {target_format}")
            return True
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg conversion timed out")
        except FileNotFoundError:
            logger.error("FFmpeg not found. Install FFmpeg for audio format conversion.")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg conversion failed: {e.stderr}")

        return False

    def cleanup(self):
        """
        Clean up temporary directories and resources.
        """
        self._temp_dir_obj.cleanup()
