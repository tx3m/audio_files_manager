"""
Legacy compatibility extensions for AudioFileManager.
This module adds methods to AudioFileManager to directly support legacy functionality
without requiring the LegacyServiceAdapter.
"""

import logging
from datetime import datetime
from typing import Optional, Union, Dict, Any
from pathlib import Path
import os
import types

logger = logging.getLogger(__name__)

def add_legacy_compatibility(manager):
    """
    Function to add legacy compatibility methods to an AudioFileManager instance.
    
    This function adds methods and properties to an AudioFileManager instance that were previously
    provided by LegacyServiceAdapter, allowing direct usage without the adapter.
    
    Args:
        manager: The AudioFileManager instance to extend
        
    Returns:
        The extended AudioFileManager instance
    """
    # Initialize legacy state attributes
    manager._playback_active = False
    manager._played_once = False
    
    # Define legacy methods
    def get_message(self, audio_file_id=""):
        """
        Legacy compatibility method to get a message file path.
        
        Args:
            audio_file_id: ID of the message, or empty for newest
            
        Returns:
            str: Path to the message file, or "No file found" if not found
        """
        # If audio_file_id is provided, use it directly
        if audio_file_id:
            button_id = str(audio_file_id)
            # Check if this button exists in metadata
            if button_id in self.metadata:
                return self.metadata[button_id]["path"]
        else:
            # Find the newest message of the manager's message type
            newest_timestamp = 0
            newest_button = None
            
            for button_id, info in self.metadata.items():
                if info.get("message_type") == self.message_type:
                    try:
                        timestamp = datetime.strptime(info["timestamp"], "%Y-%m-%d %H:%M:%S")
                        epoch_time = (timestamp - datetime(1970, 1, 1)).total_seconds()
                        
                        if epoch_time > newest_timestamp:
                            newest_timestamp = epoch_time
                            newest_button = button_id
                    except Exception as e:
                        logger.warning(f"Error processing timestamp for button {button_id}: {e}")
            
            if newest_button:
                return self.metadata[newest_button]["path"]
        
        return "No file found"
    
    def exit(self):
        """Legacy compatibility method to stop recording and clean up."""
        if self.is_recording_active():
            self.stop_recording()
        
        # Reset playback state
        self._playback_active = False
        
        logger.info("AudioFileManager exit called")
    
    def force_exit(self):
        """Legacy compatibility method to force exit any operations."""
        self.exit()
    
    def finished(self):
        """
        Legacy compatibility method to check if playback has finished.
        
        Returns:
            bool: True if playback has finished, False otherwise
        """
        # Since play_audio is blocking, if we reach here and played_once is True,
        # it means playback has finished
        if self._played_once and not self.is_recording_active() and not self._playback_active:
            return True
        return False
    
    # Store the original play_audio method
    original_play_audio = manager.play_audio
    
    def enhanced_play_audio(file_path_or_button_id):
        """
        Enhanced version of play_audio that tracks playback state for legacy compatibility.
        """
        # Set playback tracking variables for legacy compatibility
        manager._playback_active = True
        
        try:
            # Call the original method
            result = original_play_audio(file_path_or_button_id)
            if result:
                manager._played_once = True
            return result
        finally:
            manager._playback_active = False
    
    # Add the methods to the instance
    manager.get_message = types.MethodType(get_message, manager)
    manager.exit = types.MethodType(exit, manager)
    manager.force_exit = types.MethodType(force_exit, manager)
    manager.finished = types.MethodType(finished, manager)
    
    # Replace play_audio with enhanced version
    manager.play_audio = enhanced_play_audio
    
    # Add is_running property as a method for simplicity
    def is_running(self):
        return self.is_recording_active() or self._playback_active
    
    manager.is_running = types.MethodType(is_running, manager)
    
    # Add played_once property as getter/setter methods
    def get_played_once(self):
        return self._played_once
    
    def set_played_once(self, value):
        self._played_once = value
    
    manager.get_played_once = types.MethodType(get_played_once, manager)
    manager.set_played_once = types.MethodType(set_played_once, manager)
    
    # Add property-like access through __getattr__
    original_getattr = manager.__class__.__getattr__ if hasattr(manager.__class__, '__getattr__') else None
    
    def __getattr__(self, name):
        if name == 'played_once':
            return self.get_played_once()
        elif original_getattr:
            return original_getattr(self, name)
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")
    
    manager.__class__.__getattr__ = __getattr__
    
    # Add property-like setting through __setattr__
    original_setattr = manager.__class__.__setattr__
    
    def __setattr__(self, name, value):
        if name == 'played_once':
            return self.set_played_once(value)
        return original_setattr(self, name, value)
    
    manager.__class__.__setattr__ = __setattr__
    
    return manager