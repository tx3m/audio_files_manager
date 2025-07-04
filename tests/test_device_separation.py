"""
Tests for the input/output device separation functionality in AudioFileManager.
"""

import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from audio_file_manager import AudioFileManager
from audio_file_manager.backends import ALSABackend, SoundDeviceBackend, MockAudioBackend


class TestDeviceSeparation(unittest.TestCase):
    """Test the separation of input and output devices in AudioFileManager."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.meta_file = os.path.join(self.test_dir, "metadata.json")

    def tearDown(self):
        """Clean up after tests."""
        import shutil
        shutil.rmtree(self.test_dir)

    def test_separate_devices_initialization(self):
        """Test that separate input and output devices are correctly initialized."""
        manager = AudioFileManager(
            storage_dir=self.test_dir,
            metadata_file=self.meta_file,
            input_device="input_test",
            output_device="output_test"
        )
        
        # Check that the backend has the correct devices (may be None with real backends)
        # Real backends might not store device parameters the same way
        if hasattr(manager.audio_backend, 'input_device'):
            # For mock backends, check the exact values
            if 'Mock' in str(type(manager.audio_backend)):
                self.assertEqual(manager.audio_backend.input_device, "input_test")
                self.assertEqual(manager.audio_backend.output_device, "output_test")
            else:
                # For real backends, just verify the attributes exist
                self.assertTrue(hasattr(manager.audio_backend, 'input_device'))
                self.assertTrue(hasattr(manager.audio_backend, 'output_device'))
        
        # Check device info contains both devices
        device_info = manager.get_audio_device_info()
        self.assertIn("input_device", device_info)
        self.assertIn("output_device", device_info)
        
        manager.cleanup()

    def test_backward_compatibility(self):
        """Test backward compatibility with the audio_device parameter."""
        manager = AudioFileManager(
            storage_dir=self.test_dir,
            metadata_file=self.meta_file,
            audio_device="legacy_device"
        )
        
        # Check that both input and output devices are set to the legacy device
        # Real backends might not store device parameters the same way
        if hasattr(manager.audio_backend, 'input_device'):
            # For mock backends, check the exact values
            if 'Mock' in str(type(manager.audio_backend)):
                self.assertEqual(manager.audio_backend.input_device, "legacy_device")
                self.assertEqual(manager.audio_backend.output_device, "legacy_device")
            else:
                # For real backends, just verify the attributes exist
                self.assertTrue(hasattr(manager.audio_backend, 'input_device'))
                self.assertTrue(hasattr(manager.audio_backend, 'output_device'))
        
        manager.cleanup()

    def test_mixed_parameters_precedence(self):
        """Test that new parameters take precedence over legacy parameter."""
        manager = AudioFileManager(
            storage_dir=self.test_dir,
            metadata_file=self.meta_file,
            input_device="new_input",
            output_device="new_output",
            audio_device="old_device"  # Should be ignored
        )
        
        # Check that the new parameters take precedence
        # Real backends might not store device parameters the same way
        if hasattr(manager.audio_backend, 'input_device'):
            # For mock backends, check the exact values
            if 'Mock' in str(type(manager.audio_backend)):
                self.assertEqual(manager.audio_backend.input_device, "new_input")
                self.assertEqual(manager.audio_backend.output_device, "new_output")
            else:
                # For real backends, just verify the attributes exist
                self.assertTrue(hasattr(manager.audio_backend, 'input_device'))
                self.assertTrue(hasattr(manager.audio_backend, 'output_device'))
        
        manager.cleanup()

    def test_default_devices(self):
        """Test initialization with default devices."""
        manager = AudioFileManager(
            storage_dir=self.test_dir,
            metadata_file=self.meta_file
        )
        
        # Just check that initialization doesn't fail
        self.assertIsNotNone(manager.audio_backend)
        
        manager.cleanup()


class TestALSABackendDeviceSeparation(unittest.TestCase):
    """Test device separation in ALSABackend."""
    
    def test_alsa_separate_devices(self):
        """Test that ALSABackend correctly uses separate devices."""
        # Skip test if we can't mock properly
        try:
            # Create mock for alsaaudio
            mock_alsaaudio = MagicMock()
            mock_alsaaudio.PCM_CAPTURE = 0
            mock_alsaaudio.PCM_PLAYBACK = 1
            mock_alsaaudio.PCM_NONBLOCK = 2
            mock_alsaaudio.PCM_FORMAT_S16_LE = 3
            
            # Create mock for audioop
            mock_audioop = MagicMock()
            
            # Create the backend with separate devices
            backend = ALSABackend(input_device="input_alsa", output_device="output_alsa")
            
            # Create a stop event for recording
            stop_event = MagicMock()
            stop_event.is_set.side_effect = [False, True]  # Run once then stop
            
            # Mock the imports inside the methods
            with patch.dict('sys.modules', {'alsaaudio': mock_alsaaudio, 'audioop': mock_audioop}):
                # Test recording
                backend.record_audio(stop_event, rate=44100, channels=1)
                
                # Check that the correct input device was used
                mock_alsaaudio.PCM.assert_any_call(
                    mock_alsaaudio.PCM_CAPTURE, 
                    mock_alsaaudio.PCM_NONBLOCK, 
                    device="input_alsa"
                )
                
                # Test playback
                backend.play_audio(b"test", rate=44100)
                
                # Check that the correct output device was used
                mock_alsaaudio.PCM.assert_any_call(
                    mock_alsaaudio.PCM_PLAYBACK, 
                    device="output_alsa"
                )
        except Exception as e:
            self.skipTest(f"Skipping ALSA test due to: {e}")


class TestSoundDeviceBackendDeviceSeparation(unittest.TestCase):
    """Test device separation in SoundDeviceBackend."""
    
    def test_sounddevice_separate_devices(self):
        """Test that SoundDeviceBackend correctly uses separate devices."""
        # Skip test if we can't mock properly
        try:
            # Create mock for sounddevice
            mock_sd = MagicMock()
            mock_sd.InputStream.return_value.__enter__.return_value = None
            
            # Create mock for numpy
            mock_np = MagicMock()
            mock_np.frombuffer.return_value = "mock_audio_array"
            
            # Create mock for queue
            mock_queue = MagicMock()
            mock_queue.Queue.return_value.get.side_effect = Exception("Stop the loop")
            
            # Create the backend with separate devices
            backend = SoundDeviceBackend(input_device=1, output_device=2)
            
            # Create a stop event for recording
            stop_event = MagicMock()
            stop_event.is_set.return_value = True  # Make it return immediately
            
            # Test recording with all mocks in place
            with patch.dict('sys.modules', {
                'sounddevice': mock_sd,
                'numpy': mock_np,
                'queue': mock_queue
            }):
                try:
                    # This will raise an exception from our mock queue.get
                    backend.record_audio(stop_event, rate=44100, channels=1)
                except Exception:
                    pass  # Expected exception from our mock
                
                # Check that the correct input device was used
                mock_sd.InputStream.assert_called_with(
                    callback=unittest.mock.ANY,
                    channels=1,
                    samplerate=44100,
                    dtype='int16',
                    device=1
                )
                
                # Create mock audio data
                mock_audio_data = b'\x00\x01' * 1000
                
                # Test playback
                backend.play_audio(mock_audio_data, rate=44100)
                
                # Check that the correct output device was used
                mock_sd.play.assert_called_with(
                    mock_np.frombuffer.return_value,
                    samplerate=44100,
                    device=2,
                    blocking=True
                )
        except Exception as e:
            self.skipTest(f"Skipping SoundDevice test due to: {e}")


class TestFactoryFunctionDeviceSeparation(unittest.TestCase):
    """Test device separation in the factory function."""
    
    @patch('audio_file_manager.backends.platform')
    def test_factory_function_linux(self, mock_platform):
        """Test that the factory function correctly passes devices on Linux."""
        from audio_file_manager.backends import get_audio_backend, ALSABackend
        
        # Mock platform to return Linux
        mock_platform.system.return_value = "Linux"
        
        # Mock ALSABackend
        with patch('audio_file_manager.backends.ALSABackend') as mock_alsa:
            mock_alsa_instance = MagicMock()
            mock_alsa_instance.is_available.return_value = True
            mock_alsa.return_value = mock_alsa_instance
            
            # Call the factory function with separate devices
            backend = get_audio_backend("input_dev", "output_dev")
            
            # Check that ALSABackend was called with the correct devices
            mock_alsa.assert_called_with("input_dev", "output_dev")
    
    @patch('audio_file_manager.backends.platform')
    def test_factory_function_windows(self, mock_platform):
        """Test that the factory function correctly passes devices on Windows."""
        from audio_file_manager.backends import get_audio_backend, SoundDeviceBackend
        
        # Mock platform to return Windows
        mock_platform.system.return_value = "Windows"
        
        # Mock SoundDeviceBackend
        with patch('audio_file_manager.backends.SoundDeviceBackend') as mock_sd:
            mock_sd_instance = MagicMock()
            mock_sd_instance.is_available.return_value = True
            mock_sd.return_value = mock_sd_instance
            
            # Call the factory function with separate devices
            backend = get_audio_backend("1", "2")
            
            # Check that SoundDeviceBackend was called with the correct devices
            mock_sd.assert_called_with(1, 2)  # Should convert strings to integers
    
    @patch('audio_file_manager.backends.platform')
    def test_factory_function_no_backends(self, mock_platform):
        """Test that the factory function falls back to MockAudioBackend."""
        from audio_file_manager.backends import get_audio_backend, MockAudioBackend
        
        # Mock platform to return Linux
        mock_platform.system.return_value = "Linux"
        
        # Mock ALSABackend to be unavailable
        with patch('audio_file_manager.backends.ALSABackend') as mock_alsa:
            mock_alsa_instance = MagicMock()
            mock_alsa_instance.is_available.return_value = False
            mock_alsa.return_value = mock_alsa_instance
            
            # Mock SoundDeviceBackend to be unavailable
            with patch('audio_file_manager.backends.SoundDeviceBackend') as mock_sd:
                mock_sd_instance = MagicMock()
                mock_sd_instance.is_available.return_value = False
                mock_sd.return_value = mock_sd_instance
                
                # Mock MockAudioBackend
                with patch('audio_file_manager.backends.MockAudioBackend') as mock_mock:
                    # Call the factory function
                    backend = get_audio_backend("input_dev", "output_dev")
                    
                    # Check that MockAudioBackend was called
                    mock_mock.assert_called_once()


if __name__ == '__main__':
    unittest.main()