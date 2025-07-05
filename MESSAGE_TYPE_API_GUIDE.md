# Message Type API Guide

This guide explains the updated API for working with message types in the AudioFileManager.

## Overview

The AudioFileManager now uses a more consistent approach to message types. Instead of passing the message type to each method call, the message type is now set once in the constructor and used throughout the instance's lifecycle.

## Key Changes

1. Message type is now set in the constructor
2. Methods no longer accept message_type as a parameter
3. Each AudioFileManager instance has a fixed message type
4. To work with different message types, create separate manager instances

## Usage Examples

### Creating Managers with Specific Message Types

```python
# Create a manager for custom messages
custom_manager = AudioFileManager(
    storage_dir="/path/to/storage",
    message_type="custom_message"
)

# Create a manager for away messages
away_manager = AudioFileManager(
    storage_dir="/path/to/storage",
    message_type="away_message"
)
```

### Recording Audio

```python
# Old API (no longer supported)
# manager.start_recording("button1", "custom_message")

# New API
custom_manager.start_recording("button1")
```

### Getting Messages

```python
# Old API (no longer supported)
# file_path = manager.get_message("custom_message", audio_file_id="1")

# New API - get specific message by ID
file_path = custom_manager.get_message(audio_file_id="1")

# New API - get newest message of the manager's type
file_path = custom_manager.get_message()
```

### Using with Legacy Compatibility

When using the legacy compatibility layer, the same principles apply:

```python
# Create manager with specific message type
custom_manager = AudioFileManager(message_type="custom_message")

# Apply legacy compatibility
from audio_file_manager.legacy_compatibility_simple import add_legacy_compatibility
custom_manager = add_legacy_compatibility(custom_manager)

# Use legacy methods with the manager's message type
file_path = custom_manager.get_message()  # Gets newest custom message
file_path = custom_manager.get_message("1")  # Gets custom message with ID 1
```

## Benefits of the New API

1. **Consistency**: Each manager instance has a fixed message type that cannot be changed after creation
2. **Type Safety**: Prevents accidentally mixing message types within the same instance
3. **Cleaner Code**: Fewer parameters needed for method calls
4. **Better Separation of Concerns**: Each manager instance is responsible for one type of message

## Migration Guide

To migrate from the old API to the new API:

1. Create separate manager instances for each message type you need to work with
2. Set the message_type in the constructor for each manager
3. Remove message_type parameters from method calls
4. Update any code that calls `get_message()` to set the message type on the manager instance first

Example:

```python
# Old code
manager = AudioFileManager()
manager.start_recording("button1", "custom_message")
file_path = manager.get_message("custom_message")

# New code
custom_manager = AudioFileManager(message_type="custom_message")
custom_manager.start_recording("button1")
file_path = custom_manager.get_message()
```

## Working with Multiple Message Types

If you need to work with multiple message types, create separate manager instances:

```python
# Create managers for different message types
custom_manager = AudioFileManager(
    storage_dir="/path/to/storage",
    message_type="custom_message"
)

away_manager = AudioFileManager(
    storage_dir="/path/to/storage",
    message_type="away_message"
)

# Use each manager for its specific message type
custom_manager.start_recording("button1")
away_manager.start_recording("button2")

# Get messages from each manager
custom_file = custom_manager.get_message()
away_file = away_manager.get_message()
```

## Initialization in the Paging Server

In the paging server, the managers are initialized like this:

```python
# Create the custom messages manager
self.__custom_messages_manager = AudioFileManager(
    storage_dir=Constants.MESSAGE_PATH,
    metadata_file=Constants.MESSAGE_PATH + Constants.CUSTOM_MESSAGE_BKP_FILE,
    input_device="plug:dsnoop_paging",
    output_device="plug:master1",
    message_type="custom_message"
)

# Create the away messages manager
self.__away_messages_manager = AudioFileManager(
    storage_dir=Constants.MESSAGE_PATH,
    metadata_file=Constants.AWAY_MESSAGE_BKP_FILE,
    input_device="plug:dsnoop_paging",
    output_device="plug:master1",
    message_type="away_message"
)
```