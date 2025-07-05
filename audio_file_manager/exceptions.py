"""
Custom exceptions for the audio_file_manager library.
"""


class AudioFileManagerError(Exception):
    """Base exception for the audio_file_manager library."""
    pass


class BackendNotAvailableError(AudioFileManagerError):
    """Raised when an audio backend is not available."""
    pass


class DeviceNotFoundError(AudioFileManagerError):
    """Raised when an audio device cannot be found."""
    pass
