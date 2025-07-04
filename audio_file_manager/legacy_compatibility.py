"""
Legacy compatibility extensions for AudioFileManager.
This module adds methods to AudioFileManager to directly support legacy functionality
without requiring the LegacyServiceAdapter.
"""

import logging
from datetime import datetime
from typing import Optional, Union, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

def add_legacy_compatibility(cls):
    """
    Class decorator to add legacy compatibility methods to AudioFileManager.
    """
    # Add properties for legacy compatibility
    @property
    def is_running(self):
        """Legacy compatibility property for checking if recording or playback is active."""
        return self.is_recording_active() or hasattr(self, '_playback_active') and self._playback_active
    
    @property
    def played_once(self):
        """Legacy compatibility property for tracking if audio has been played once."""
        if not hasattr(self, '_played_once'):
            self._played_once = False
        return self._played_once
    
    @played_once.setter
    def played_once(self, value):
        """Set the played_once flag."""
        self._played_once = value
    
    # Add methods for legacy compatibility
    def get_message(self, audio_file_type="", audio_file_id=""):
        """
        Legacy compatibility method to get a message file path.
        
        Args:
            audio_file_type: Type of message ("away_message" or "custom_message")
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
            # Find the newest message of the given type
            newest_timestamp = 0
            newest_button = None
            
            for button_id, info in self.metadata.items():
                if info.get("message_type") == audio_file_type:
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
        if not hasattr(self, '_playback_active'):
            self._playback_active = False
        else:
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
        if self.played_once and not self.is_recording_active() and not getattr(self, '_playback_active', False):
            return True
        return False
    
    # Enhance play_audio to track playback state
    original_play_audio = cls.play_audio
    
    def enhanced_play_audio(self, file_path_or_button_id: Union[str, Path, int]) -> bool:
        """
        Enhanced version of play_audio that tracks playback state for legacy compatibility.
        """
        # Set playback tracking variables for legacy compatibility
        if not hasattr(self, '_playback_active'):
            self._playback_active = False
            
        self._playback_active = True
        
        try:
            # Call the original method
            result = original_play_audio(self, file_path_or_button_id)
            if result:
                if not hasattr(self, '_played_once'):
                    self._played_once = False
                self._played_once = True
            return result
        finally:
            self._playback_active = False
    
    # Add the new methods and properties to the class
    cls.is_running = is_running
    cls.played_once = played_once
    cls.get_message = get_message
    cls.exit = exit
    cls.force_exit = force_exit
    cls.finished = finished
    cls.play_audio = enhanced_play_audio
    
    return cls