# Audio Device Guide

This guide explains how to use the input and output device parameters in the AudioFileManager.

## Overview

The AudioFileManager now supports separate input and output devices, allowing you to:
- Use different hardware for recording and playback
- Configure specific audio interfaces for each operation
- Optimize audio quality for both input and output

## Device Parameters

When initializing the AudioFileManager, you can specify:

```python
from audio_file_manager import AudioFileManager

manager = AudioFileManager(
    input_device="device_for_recording",
    output_device="device_for_playback"
)
```

## Device Formats

The format for device specification depends on the backend:

### ALSA (Linux)

For ALSA, devices are specified as strings:

```python
# Examples
input_device="default"           # Default ALSA input device
input_device="hw:0,0"            # First subdevice of first card
input_device="hw:1,0"            # First subdevice of second card
output_device="plughw:0,0"       # Use plug layer for automatic format conversion
```

Common ALSA device formats:
- `default`: System default device
- `hw:CARD,DEVICE`: Direct hardware device (CARD and DEVICE are numbers)
- `plughw:CARD,DEVICE`: Hardware device with automatic format conversion
- `sysdefault:CARD,DEVICE`: System default with ALSA configuration applied

### SoundDevice (Windows/macOS)

For SoundDevice, devices can be specified as integers or strings (which will be converted to integers):

```python
# Examples
input_device=0                  # First input device
input_device="0"                # Same as above (string will be converted)
output_device=1                 # Second output device
```

## Finding Available Devices

### Linux (ALSA)

You can list available ALSA devices using the command line:

```bash
arecord -l   # List recording (input) devices
aplay -l     # List playback (output) devices
```

### Windows/macOS (SoundDevice)

You can list available devices in Python:

```python
import sounddevice as sd
print(sd.query_devices())
```

## Backward Compatibility

For backward compatibility, the `audio_device` parameter is still supported:

```python
# Old style - sets both input and output to the same device
manager = AudioFileManager(audio_device="default")
```

When both new and old parameters are provided, the new parameters take precedence:

```python
# input_device and output_device will be used, audio_device is ignored
manager = AudioFileManager(
    input_device="hw:0,0",
    output_device="hw:1,0",
    audio_device="default"  # Ignored
)
```

## Best Practices

1. **Testing Devices**: Always test your device configuration before deploying to production
2. **Error Handling**: Handle cases where specified devices might not be available
3. **Default Fallback**: Provide sensible defaults when specific devices aren't critical
4. **Device Capabilities**: Be aware that some devices may support different sample rates or formats

## Example: Using Different Devices

```python
from audio_file_manager import AudioFileManager

# Example: USB microphone for input, built-in speakers for output
manager = AudioFileManager(
    input_device="hw:1,0",    # USB microphone
    output_device="hw:0,0",   # Built-in speakers
    sample_rate=44100,
    channels=1
)

# Record and play using different devices
recording_info = manager.record_audio_to_temp("button1", "greeting", stop_event)
manager.finalize_recording(recording_info)
manager.play_audio(recording_info["temp_path"])
```

## Troubleshooting

If you encounter issues with audio devices:

1. **Device Not Found**: Verify the device exists using system tools
2. **Permission Issues**: Ensure your application has permission to access audio devices
3. **Format Mismatch**: Try using `plughw:` instead of `hw:` on Linux to enable format conversion
4. **Sample Rate**: Some devices only support specific sample rates
5. **Backend Selection**: If one backend doesn't work, try forcing a different one

## Advanced: Custom Backend Configuration

For advanced users who need more control over the audio backend:

```python
from audio_file_manager.backends import ALSABackend, SoundDeviceBackend

# Create a custom backend
custom_backend = ALSABackend(
    input_device="hw:2,0",
    output_device="hw:1,0"
)

# Use it with AudioFileManager
manager = AudioFileManager(
    storage_dir="/path/to/storage",
    audio_backend=custom_backend  # Use custom backend directly
)
```

Note: Direct backend configuration is an advanced feature and may not be supported in all versions.