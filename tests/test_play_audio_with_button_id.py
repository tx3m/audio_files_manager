import unittest
import tempfile
import shutil
import os
import wave
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

from audio_file_manager.manager import AudioFileManager


class TestPlayAudioWithButtonId(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.storage_dir = Path(self.temp_dir) / "storage"
        self.metadata_file = Path(self.temp_dir) / "metadata.json"
        
        # Create the manager with a mock audio backend
        self.manager = AudioFileManager(
            storage_dir=self.storage_dir,
            metadata_file=self.metadata_file
        )
        
        # Mock the audio backend
        self.manager.audio_backend.play_audio = MagicMock()
        
        # Create a test audio file
        self.test_audio_path = Path(self.temp_dir) / "test_audio.wav"
        self._create_test_wav_file(self.test_audio_path)
        
        # Add a test recording to metadata
        self.button_id = "1"
        self.manager.metadata_manager.metadata[self.button_id] = {
            "name": "test_recording.wav",
            "duration": 1.0,
            "path": str(self.test_audio_path),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message_type": "test",
            "audio_format": "wav",
            "read_only": False,
            "is_default": False
        }
        self.manager.metadata_manager.save()

    def tearDown(self):
        # Clean up temporary directory
        shutil.rmtree(self.temp_dir)

    def _create_test_wav_file(self, file_path):
        """Create a simple test WAV file with silence."""
        sample_rate = 44100
        duration = 0.1  # seconds (short duration for test)
        n_samples = int(sample_rate * duration)
        
        # Create silence (all zeros)
        silence_data = b'\x00\x00' * n_samples
        
        with wave.open(str(file_path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(silence_data)

    def test_play_audio_with_file_path(self):
        """Test playing audio with a file path."""
        # Call play_audio with a file path
        result = self.manager.play_audio(self.test_audio_path)
        
        # Verify the audio backend was called correctly
        self.manager.audio_backend.play_audio.assert_called_once()
        self.assertTrue(result)

    def test_play_audio_with_button_id(self):
        """Test playing audio with a button ID."""
        # Call play_audio with a button ID
        result = self.manager.play_audio(self.button_id)
        
        # Verify the audio backend was called correctly
        self.manager.audio_backend.play_audio.assert_called_once()
        self.assertTrue(result)

    def test_play_audio_with_nonexistent_button_id(self):
        """Test playing audio with a nonexistent button ID."""
        # Call play_audio with a nonexistent button ID
        result = self.manager.play_audio("999")
        
        # Verify the audio backend was not called
        self.manager.audio_backend.play_audio.assert_not_called()
        self.assertFalse(result)

    def test_play_audio_with_nonexistent_file_path(self):
        """Test playing audio with a nonexistent file path."""
        # Call play_audio with a nonexistent file path
        result = self.manager.play_audio("/nonexistent/path.wav")
        
        # Verify the audio backend was not called
        self.manager.audio_backend.play_audio.assert_not_called()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()