import unittest
import time
import platform
from unittest.mock import Mock, patch, MagicMock
from threading import Event
from audio_file_manager.backends import (
    AudioBackend, ALSABackend, SoundDeviceBackend, MockAudioBackend, get_audio_backend
)


class TestAudioBackend(unittest.TestCase):
    """Test the abstract AudioBackend class."""
    
    def test_abstract_methods(self):
        """Test that AudioBackend cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            AudioBackend()


class TestMockAudioBackend(unittest.TestCase):
    """Test the MockAudioBackend implementation."""
    
    def setUp(self):
        self.backend = MockAudioBackend()
    
    def test_is_available(self):
        """Test that MockAudioBackend is always available."""
        self.assertTrue(self.backend.is_available())
    
    def test_record_audio(self):
        """Test audio recording with mock backend."""
        stop_event = Event()
        sound_levels = []
        
        def sound_callback(level):
            sound_levels.append(level)
            if len(sound_levels) >= 3:  # Stop after a few callbacks
                stop_event.set()
        
        # Start recording and stop after a short time
        import threading
        def stop_after_delay():
            time.sleep(0.5)
            stop_event.set()
        
        threading.Thread(target=stop_after_delay, daemon=True).start()
        
        audio_data = self.backend.record_audio(
            stop_event=stop_event,
            channels=1,
            rate=44100,
            sound_level_callback=sound_callback
        )
        
        self.assertIsInstance(audio_data, bytes)
        self.assertGreater(len(audio_data), 0)
        self.assertGreater(len(sound_levels), 0)
    
    def test_play_audio(self):
        """Test audio playback with mock backend."""
        audio_data = b'\x00\x01' * 1000
        
        # Should not raise any exceptions
        self.backend.play_audio(audio_data, channels=1, rate=44100)
    
    def test_get_device_info(self):
        """Test device info retrieval."""
        info = self.backend.get_device_info()
        
        self.assertIsInstance(info, dict)
        self.assertEqual(info['device'], 'mock')
        self.assertEqual(info['backend'], 'Mock')
        self.assertTrue(info['available'])


class TestALSABackend(unittest.TestCase):
    """Test the ALSABackend implementation."""
    
    def setUp(self):
        self.backend = ALSABackend()
    
    def test_is_available_without_alsa(self):
        """Test availability check when ALSA is not available."""
        with patch.dict('sys.modules', {'alsaaudio': None}):
            backend = ALSABackend()
            self.assertFalse(backend.is_available())
    
    def test_is_available_with_alsa(self):
        """Test availability check when ALSA is available."""
        with patch.dict('sys.modules', {'alsaaudio': MagicMock()}):
            backend = ALSABackend()
            self.assertTrue(backend.is_available())
    
    def test_record_audio(self):
        """Test ALSA audio recording."""
        with patch.dict('sys.modules', {'alsaaudio': MagicMock(), 'audioop': MagicMock()}) as mock_modules:
            mock_alsa = mock_modules['alsaaudio']
            mock_audioop = mock_modules['audioop']
            
            # Mock ALSA PCM
            mock_pcm = Mock()
            
            def mock_read():
                # Return data a few times, then return empty to stop
                if not hasattr(mock_read, 'call_count'):
                    mock_read.call_count = 0
                mock_read.call_count += 1
                
                if mock_read.call_count <= 3:
                    return (1024, b'\x00\x01' * 512)
                else:
                    return (0, b'')
            
            mock_pcm.read.side_effect = mock_read
            mock_alsa.PCM.return_value = mock_pcm
            mock_alsa.PCM_CAPTURE = 'capture'
            mock_alsa.PCM_NONBLOCK = 'nonblock'
            mock_alsa.PCM_FORMAT_S16_LE = 'format'
            
            # Mock audioop for sound level calculation
            mock_audioop.rms.return_value = 1000
        
            stop_event = Event()
            sound_levels = []
            
            def sound_callback(level):
                sound_levels.append(level)
                if len(sound_levels) >= 2:
                    stop_event.set()
            
            # Start recording and stop after collecting some data
            import threading
            def stop_after_delay():
                time.sleep(0.1)
                stop_event.set()
            
            threading.Thread(target=stop_after_delay, daemon=True).start()
            
            backend = ALSABackend()
            audio_data = backend.record_audio(
                stop_event=stop_event,
                channels=1,
                rate=44100,
                sound_level_callback=sound_callback
            )
            
            self.assertIsInstance(audio_data, bytes)
            mock_pcm.setchannels.assert_called_with(1)
            mock_pcm.setrate.assert_called_with(44100)
            mock_pcm.close.assert_called_once()
    
    def test_play_audio(self):
        """Test ALSA audio playback."""
        with patch.dict('sys.modules', {'alsaaudio': MagicMock()}) as mock_modules:
            mock_alsa = mock_modules['alsaaudio']
            mock_pcm = Mock()
            mock_alsa.PCM.return_value = mock_pcm
            mock_alsa.PCM_PLAYBACK = 'playback'
            mock_alsa.PCM_FORMAT_S16_LE = 'format'
            
            audio_data = b'\x00\x01' * 1000
            
            backend = ALSABackend()
            backend.play_audio(audio_data, channels=1, rate=44100)
            
            mock_pcm.setchannels.assert_called_with(1)
            mock_pcm.setrate.assert_called_with(44100)
            mock_pcm.write.assert_called()
            mock_pcm.close.assert_called_once()
    
    def test_get_device_info(self):
        """Test ALSA device info retrieval."""
        backend = ALSABackend()
        mock_pcm = Mock()
        mock_pcm.info.return_value = {'rate': 44100, 'channels': 1}
        backend._audio_input = mock_pcm
        
        info = backend.get_device_info()
        
        self.assertIsInstance(info, dict)
        self.assertEqual(info['rate'], 44100)
        self.assertEqual(info['channels'], 1)


class TestSoundDeviceBackend(unittest.TestCase):
    """Test the SoundDeviceBackend implementation."""
    
    def setUp(self):
        self.backend = SoundDeviceBackend()
    
    def test_is_available_without_sounddevice(self):
        """Test availability check when SoundDevice is not available."""
        with patch.dict('sys.modules', {'sounddevice': None, 'numpy': None}):
            backend = SoundDeviceBackend()
            self.assertFalse(backend.is_available())
    
    def test_is_available_with_sounddevice(self):
        """Test availability check when SoundDevice is available."""
        with patch.dict('sys.modules', {'sounddevice': MagicMock(), 'numpy': MagicMock()}):
            backend = SoundDeviceBackend()
            self.assertTrue(backend.is_available())
    
    def test_record_audio(self):
        """Test SoundDevice audio recording."""
        with patch.dict('sys.modules', {'sounddevice': MagicMock(), 'numpy': MagicMock(), 'queue': MagicMock()}) as mock_modules:
            mock_sd = mock_modules['sounddevice']
            mock_np = mock_modules['numpy']
            mock_queue_module = mock_modules['queue']
            
            # Mock queue
            mock_queue = Mock()
            mock_queue.get.side_effect = [
                mock_np.array([[1, 2, 3]]),
                mock_np.array([[4, 5, 6]]),
                Exception("Empty")  # To break the loop
            ]
            mock_queue_module.Queue.return_value = mock_queue
            mock_queue_module.Empty = Exception
            
            # Mock numpy
            mock_audio_array = Mock()
            mock_audio_array.tobytes.return_value = b'\x00\x01' * 1000
            mock_np.concatenate.return_value = mock_audio_array
            mock_np.sqrt.return_value = 1000
            mock_np.mean.return_value = 500
            
            # Mock sounddevice
            mock_sd.InputStream.return_value.__enter__ = Mock()
            mock_sd.InputStream.return_value.__exit__ = Mock()
            mock_sd.CallbackStop = Exception
        
            stop_event = Event()
            sound_levels = []
            
            def sound_callback(level):
                sound_levels.append(level)
                if len(sound_levels) >= 2:
                    stop_event.set()
            
            # Start recording and stop after a short time
            import threading
            def stop_after_delay():
                time.sleep(0.1)
                stop_event.set()
            
            threading.Thread(target=stop_after_delay, daemon=True).start()
            
            backend = SoundDeviceBackend()
            audio_data = backend.record_audio(
                stop_event=stop_event,
                channels=1,
                rate=44100,
                sound_level_callback=sound_callback
            )
            
            self.assertIsInstance(audio_data, bytes)
    
    def test_play_audio(self):
        """Test SoundDevice audio playback."""
        with patch.dict('sys.modules', {'sounddevice': MagicMock(), 'numpy': MagicMock()}) as mock_modules:
            mock_sd = mock_modules['sounddevice']
            mock_np = mock_modules['numpy']
            
            audio_data = b'\x00\x01' * 1000
            mock_audio_array = Mock()
            mock_audio_array.__len__ = Mock(return_value=1000)  # Add len() support
            mock_np.frombuffer.return_value = mock_audio_array
            
            backend = SoundDeviceBackend()
            backend.play_audio(audio_data, channels=1, rate=44100)
            
            mock_np.frombuffer.assert_called_with(audio_data, dtype=mock_np.int16)
            mock_sd.play.assert_called_once()
    
    def test_get_device_info(self):
        """Test SoundDevice device info retrieval."""
        with patch.dict('sys.modules', {'sounddevice': MagicMock()}) as mock_modules:
            mock_sd = mock_modules['sounddevice']
            mock_sd.query_devices.return_value = {'name': 'Test Device', 'channels': 2}
            mock_sd.default.device = [0, 1]
            
            backend = SoundDeviceBackend()
            info = backend.get_device_info()
            
            self.assertIsInstance(info, dict)
            self.assertEqual(info['name'], 'Test Device')
            self.assertEqual(info['channels'], 2)


class TestGetAudioBackend(unittest.TestCase):
    """Test the get_audio_backend factory function."""
    
    @patch('audio_file_manager.backends.platform')
    @patch('audio_file_manager.backends.ALSABackend')
    def test_get_alsa_backend_on_linux(self, mock_alsa_class, mock_platform):
        """Test that ALSA backend is returned on Linux when available."""
        mock_platform.system.return_value = "Linux"
        mock_alsa_instance = Mock()
        mock_alsa_instance.is_available.return_value = True
        mock_alsa_class.return_value = mock_alsa_instance
        
        backend = get_audio_backend()
        
        self.assertEqual(backend, mock_alsa_instance)
        mock_alsa_class.assert_called_with("default")
    
    @patch('audio_file_manager.backends.platform')
    @patch('audio_file_manager.backends.ALSABackend')
    @patch('audio_file_manager.backends.SoundDeviceBackend')
    def test_fallback_to_sounddevice(self, mock_sd_class, mock_alsa_class, mock_platform):
        """Test fallback to SoundDevice when ALSA is not available."""
        mock_platform.system.return_value = "Linux"
        mock_alsa_instance = Mock()
        mock_alsa_instance.is_available.return_value = False
        mock_alsa_class.return_value = mock_alsa_instance
        
        mock_sd_instance = Mock()
        mock_sd_instance.is_available.return_value = True
        mock_sd_class.return_value = mock_sd_instance
        
        backend = get_audio_backend()
        
        self.assertEqual(backend, mock_sd_instance)
    
    @patch('audio_file_manager.backends.platform')
    @patch('audio_file_manager.backends.SoundDeviceBackend')
    def test_get_sounddevice_backend_on_windows(self, mock_sd_class, mock_platform):
        """Test that SoundDevice backend is returned on Windows."""
        mock_platform.system.return_value = "Windows"
        mock_sd_instance = Mock()
        mock_sd_instance.is_available.return_value = True
        mock_sd_class.return_value = mock_sd_instance
        
        backend = get_audio_backend()
        
        self.assertEqual(backend, mock_sd_instance)
    
    @patch('audio_file_manager.backends.platform')
    @patch('audio_file_manager.backends.ALSABackend')
    @patch('audio_file_manager.backends.SoundDeviceBackend')
    @patch('audio_file_manager.backends.MockAudioBackend')
    def test_fallback_to_mock_backend(self, mock_mock_class, mock_sd_class, mock_alsa_class, mock_platform):
        """Test fallback to mock backend when no real backends are available."""
        mock_platform.system.return_value = "Linux"
        
        # Make all real backends unavailable
        mock_alsa_instance = Mock()
        mock_alsa_instance.is_available.return_value = False
        mock_alsa_class.return_value = mock_alsa_instance
        
        mock_sd_instance = Mock()
        mock_sd_instance.is_available.return_value = False
        mock_sd_class.return_value = mock_sd_instance
        
        mock_mock_instance = Mock()
        mock_mock_class.return_value = mock_mock_instance
        
        backend = get_audio_backend()
        
        self.assertEqual(backend, mock_mock_instance)
        mock_mock_class.assert_called_once()
    
    @patch('audio_file_manager.backends.platform')
    @patch('audio_file_manager.backends.ALSABackend')
    def test_custom_device_parameter(self, mock_alsa_class, mock_platform):
        """Test that custom device parameter is passed correctly."""
        mock_platform.system.return_value = "Linux"
        mock_alsa_instance = Mock()
        mock_alsa_instance.is_available.return_value = True
        mock_alsa_class.return_value = mock_alsa_instance
        
        backend = get_audio_backend("custom_device")
        
        mock_alsa_class.assert_called_with("custom_device")


if __name__ == '__main__':
    unittest.main()