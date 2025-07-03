# Audio File Manager

A Python module to safely record, review, and manage `.wav` audio clips by UI button—using temporary staging with cross-platform support and OS abstraction.

## Platform Compatibility

This module supports:
- Linux (with ALSA via `pyalsaaudio`)
- Windows/macOS (via `sounddevice`)
- Fallback to mock backend for testing environments

Dependencies are chosen automatically on installation.

![Build](https://github.com/tx3m/audio_files_manager/actions/workflows/python-tests.yml/badge.svg)

## Features

- **Cross-platform audio recording and playback**: Works seamlessly across Linux, Windows, and macOS
- **OS abstraction**: Each audio backend has its own class, making the main manager clean and extensible
- **Message type management**: Support for different message types (away_message, custom_message, etc.)
- **File ID management**: Tracks occupied IDs to prevent overwriting
- **Audio format conversion**: Supports PCM, A-law, and u-law formats
- **Threading support**: Background operations for recording and playback
- **Sound level monitoring**: Real-time audio level feedback during recording
- **Read-only protection**: Prevent accidental overwriting of important recordings
- **Default file management**: Assign and restore default recordings

## Architecture

The module is designed with a clean separation of concerns:

- `AudioFileManager`: Main class that handles recording, playback, and file management
- `AudioBackend`: Abstract base class for audio backends
  - `ALSABackend`: Linux-specific implementation using ALSA
  - `SoundDeviceBackend`: Cross-platform implementation for Windows and macOS
  - `MockAudioBackend`: Testing implementation when no audio hardware is available
- `LegacyServiceAdapter`: Adapter class that provides compatibility with legacy services
  - Integrates MessageRecordService functionality
  - Integrates RecordedMessagesService functionality

## Usage

### Basic Usage

```python
from audio_file_manager import AudioFileManager
from threading import Event

# Initialize the manager
manager = AudioFileManager()

# Record audio for a specific button
stop_event = Event()
recording_info = manager.record_audio_to_temp("button1", "greeting", stop_event)

# Finalize the recording
manager.finalize_recording(recording_info)

# Play back the recording
info = manager.get_recording_info("button1")
manager.play_audio(info["path"])

# Clean up when done
manager.cleanup()
```

### Advanced Usage

```python
# Initialize with custom settings
manager = AudioFileManager(
    storage_dir="/path/to/storage",
    metadata_file="/path/to/metadata.json",
    num_buttons=10,
    audio_format="alaw",  # "pcm", "alaw", or "ulaw"
    sample_rate=16000,
    channels=1
)

# Set a sound level callback for monitoring
def sound_level_callback(level):
    print(f"Current sound level: {level}")

manager.set_sound_level_callback(sound_level_callback)

# Record in a separate thread
manager.record_audio_threaded("button2", "away_message")

# Stop recording after some time
import time
time.sleep(5)
manager.stop_recording()

# Set recording as read-only
manager.set_read_only("button2", True)

# Assign a default recording
manager.assign_default("button3", "/path/to/default.wav")

# Restore default recording
manager.restore_default("button3")

# List all recordings
all_recordings = manager.list_all_recordings()
for button_id, info in all_recordings.items():
    print(f"Button {button_id}: {info['message_type']} ({info.get('duration', 'N/A')}s)")
```

## Legacy Integration

The library provides a `LegacyServiceAdapter` that allows seamless integration with code that depends on the legacy `MessageRecordService` and `RecordedMessagesService` classes.

```python
from audio_file_manager import AudioFileManager, LegacyServiceAdapter

# Initialize the AudioFileManager
manager = AudioFileManager(
    storage_dir="/path/to/storage",
    audio_format="alaw",  # Legacy format
    sample_rate=8000      # Legacy sample rate
)

# Create the legacy adapter
legacy_service = LegacyServiceAdapter(
    audio_manager=manager,
    message_path="/path/to/messages",
    sound_level_updater=sound_level_updater,  # Optional
    nextion_interface=nextion_interface       # Optional
)

# Use legacy methods
legacy_service.run("away_message")  # Start recording
time.sleep(3)                       # Record for 3 seconds
legacy_service.exit()               # Stop recording

# Play back the recorded message
legacy_service.play_locally("away_message")

# Get information about available messages
empty_mask = legacy_service.get_empty_custom_messages()
```

See `legacy_integration_example.py` for a complete example of legacy integration.

## Example Applications

- `example_enhanced_manager.py`: A complete command-line application demonstrating all features
- `legacy_integration_example.py`: Example showing how to integrate with legacy code

## Installation

```bash
pip install audio-file-manager
```

Or install from source:

```bash
git clone https://github.com/tx3m/audio_files_manager.git
cd audio_files_manager
pip install -e .
```