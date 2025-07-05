"""
Configuration for the AudioFileManager.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """
    Configuration class for AudioFileManager.

    Attributes:
        num_buttons: The number of buttons (and recording slots) to support.
        sample_rate: The audio sample rate in Hz.
        channels: The number of audio channels.
        audio_format: The target audio format for recordings (e.g., "pcm", "alaw", "ulaw").
        period_size: The size of audio chunks (in frames) for recording.
        message_type: The default message type for new recordings.
        input_device: The name or ID of the audio input device.
        output_device: The name or ID of the audio output device.
        audio_device: (Deprecated) The name or ID for both input and output devices.
    """
    num_buttons: int = 16
    sample_rate: int = 44100
    channels: int = 1
    audio_format: str = "pcm"
    period_size: int = 1024
    message_type: str = "custom_message"
    input_device: Optional[str] = None
    output_device: Optional[str] = None
    audio_device: Optional[str] = None  # Deprecated
