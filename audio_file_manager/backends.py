"""
Audio backend abstractions for different operating systems.
Each backend implements the same interface for recording and playback.
"""

import logging
import time
from abc import ABC, abstractmethod
from threading import Event
from typing import Dict, Any, Optional, Callable
import platform

logger = logging.getLogger(__name__)


class AudioBackend(ABC):
    """Abstract base class for audio backends."""
    
    @abstractmethod
    def record_audio(self, stop_event: Event, channels: int = 1, rate: int = 44100, 
                    period_size: int = 1024, sound_level_callback: Optional[Callable] = None) -> bytes:
        """Record audio until stop_event is set. Returns raw PCM bytes."""
        pass
    
    @abstractmethod
    def play_audio(self, audio_data: bytes, channels: int = 1, rate: int = 44100) -> None:
        """Play audio data."""
        pass
    
    @abstractmethod
    def get_device_info(self) -> Dict[str, Any]:
        """Get information about the current audio device."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available on the current system."""
        pass


class ALSABackend(AudioBackend):
    """ALSA audio backend for Linux systems."""
    
    def __init__(self, input_device: str = "default", output_device: str = "default"):
        self.input_device = input_device
        self.output_device = output_device
        self._audio_input = None
        
    def is_available(self) -> bool:
        try:
            import alsaaudio
            return True
        except ImportError:
            return False
    
    def record_audio(self, stop_event: Event, channels: int = 1, rate: int = 44100, 
                    period_size: int = 1024, sound_level_callback: Optional[Callable] = None) -> bytes:
        try:
            import alsaaudio
            import audioop
        except ImportError:
            raise RuntimeError("ALSA audio not available")
        
        # Configure ALSA input
        inp = alsaaudio.PCM(alsaaudio.PCM_CAPTURE, alsaaudio.PCM_NONBLOCK, device=self.input_device)
        inp.setchannels(channels)
        inp.setrate(rate)
        inp.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        inp.setperiodsize(period_size)
        
        self._audio_input = inp
        frames = []
        sound_level_counter = 0
        
        logger.info(f"ALSA recording started: input_device={self.input_device}, rate={rate}, channels={channels}")
        
        try:
            while not stop_event.is_set():
                length, data = inp.read()
                if length > 0:
                    frames.append(data)
                    
                    # Sound level monitoring
                    if sound_level_callback:
                        sound_level_counter += 1
                        if sound_level_counter % 150 == 0:  # Same as legacy
                            sound_level = audioop.rms(data, 2)
                            sound_level_callback(sound_level)
                
                time.sleep(0.001)  # Prevent excessive CPU usage
                
        finally:
            inp.close()
            self._audio_input = None
            
        return b''.join(frames)
    
    def play_audio(self, audio_data: bytes, channels: int = 1, rate: int = 44100) -> None:
        try:
            import alsaaudio
        except ImportError:
            raise RuntimeError("ALSA audio not available")
        
        # ALSA playback implementation
        out = alsaaudio.PCM(alsaaudio.PCM_PLAYBACK, device=self.output_device)
        out.setchannels(channels)
        out.setrate(rate)
        out.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        out.setperiodsize(1024)
        
        try:
            # Write audio data in chunks
            chunk_size = 1024 * 2 * channels  # 2 bytes per sample for S16_LE
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                out.write(chunk)
        finally:
            out.close()
    
    def get_device_info(self) -> Dict[str, Any]:
        if self._audio_input:
            try:
                return self._audio_input.info()
            except:
                pass
        return {"input_device": self.input_device, "output_device": self.output_device, "backend": "ALSA"}


class SoundDeviceBackend(AudioBackend):
    """SoundDevice backend for Windows, macOS, and other platforms."""
    
    def __init__(self, input_device: Optional[int] = None, output_device: Optional[int] = None):
        self.input_device = input_device
        self.output_device = output_device
        
    def is_available(self) -> bool:
        try:
            import sounddevice as sd
            import numpy as np
            return True
        except ImportError:
            return False
    
    def record_audio(self, stop_event: Event, channels: int = 1, rate: int = 44100, 
                    period_size: int = 1024, sound_level_callback: Optional[Callable] = None) -> bytes:
        try:
            import sounddevice as sd
            import numpy as np
            import queue
        except ImportError:
            raise RuntimeError("SoundDevice not available")
        
        q = queue.Queue()
        sound_level_counter = 0
        
        def callback(indata, frames, time, status):
            if stop_event.is_set():
                raise sd.CallbackStop()
            q.put(indata.copy())
        
        audio_chunks = []
        
        logger.info(f"SoundDevice recording started: input_device={self.input_device}, rate={rate}, channels={channels}")
        
        with sd.InputStream(callback=callback, channels=channels, samplerate=rate, 
                          dtype='int16', device=self.input_device):
            while not stop_event.is_set():
                try:
                    data = q.get(timeout=0.1)
                    audio_chunks.append(data)
                    
                    # Sound level monitoring
                    if sound_level_callback:
                        sound_level_counter += 1
                        if sound_level_counter % 150 == 0:
                            # Calculate RMS similar to ALSA backend
                            rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))
                            sound_level_callback(int(rms * 32767))  # Convert to int16 range
                            
                except queue.Empty:
                    continue
        
        if audio_chunks:
            all_audio = np.concatenate(audio_chunks)
            return all_audio.tobytes()
        return b''
    
    def play_audio(self, audio_data: bytes, channels: int = 1, rate: int = 44100) -> None:
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            raise RuntimeError("SoundDevice not available")
        
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        if channels > 1:
            audio_array = audio_array.reshape(-1, channels)
        
        logger.info(f"Playing audio: {len(audio_array)} samples at {rate}Hz")
        sd.play(audio_array, samplerate=rate, device=self.output_device, blocking=True)
    
    def get_device_info(self) -> Dict[str, Any]:
        try:
            import sounddevice as sd
            info = {"backend": "SoundDevice"}
            
            # Get input device info
            if self.input_device is not None:
                info["input_device"] = sd.query_devices(self.input_device)
            else:
                info["input_device"] = sd.query_devices(sd.default.device[0])
                
            # Get output device info
            if self.output_device is not None:
                info["output_device"] = sd.query_devices(self.output_device)
            else:
                info["output_device"] = sd.query_devices(sd.default.device[1])
                
            return info
        except:
            return {"input_device": self.input_device, "output_device": self.output_device, "backend": "SoundDevice"}


class MockAudioBackend(AudioBackend):
    """Mock audio backend for testing when no real audio hardware is available."""
    
    def is_available(self) -> bool:
        return True
    
    def record_audio(self, stop_event: Event, channels: int = 1, rate: int = 44100, 
                    period_size: int = 1024, sound_level_callback: Optional[Callable] = None) -> bytes:
        logger.info("Mock recording started")
        # Simulate recording by waiting for stop event and generating dummy audio
        start_time = time.time()
        while not stop_event.is_set():
            if sound_level_callback and int(time.time() - start_time) % 1 == 0:
                sound_level_callback(1000)  # Mock sound level
            time.sleep(0.1)
        
        # Generate dummy audio data (1 second of silence)
        duration = time.time() - start_time
        samples = int(rate * channels * duration)
        return b'\x00\x01' * samples
    
    def play_audio(self, audio_data: bytes, channels: int = 1, rate: int = 44100) -> None:
        logger.info(f"Mock playback: {len(audio_data)} bytes at {rate}Hz")
        time.sleep(len(audio_data) / (rate * channels * 2))  # Simulate playback time
    
    def get_device_info(self) -> Dict[str, Any]:
        return {"input_device": "mock", "output_device": "mock", "backend": "Mock", "available": True}


def get_audio_backend(input_device: Optional[str] = None, output_device: Optional[str] = None) -> AudioBackend:
    """Factory function to get the appropriate audio backend for the current platform."""

    # Try ALSA first on Linux
    if platform.system() == "Linux":
        alsa_backend = ALSABackend(input_device or "default", output_device or "default")
        if alsa_backend.is_available():
            logger.info("Using ALSA audio backend")
            return alsa_backend

    
    # Fall back to SoundDevice
    # Convert string device names to integers for SoundDevice if needed
    input_dev = None
    output_dev = None
    
    if input_device is not None:
        try:
            input_dev = int(input_device)
        except (ValueError, TypeError):
            input_dev = None
            
    if output_device is not None:
        try:
            output_dev = int(output_device)
        except (ValueError, TypeError):
            output_dev = None
    
    sounddevice_backend = SoundDeviceBackend(input_dev, output_dev)
    if sounddevice_backend.is_available():
        logger.info("Using SoundDevice audio backend")
        return sounddevice_backend
    
    # Use mock backend as last resort
    logger.warning("No real audio backend available, using mock backend")
    return MockAudioBackend()
