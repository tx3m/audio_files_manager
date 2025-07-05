"""
Refactored legacy paging server that uses AudioFileManager directly without LegacyServiceAdapter.
"""

import logging
import time
import inspect
from threading import Thread, Event
from typing import Union, List, Dict, Any, Optional

from audio_file_manager import AudioFileManager
from audio_file_manager.legacy_compatibility import add_legacy_compatibility

# Apply the legacy compatibility decorator to AudioFileManager
AudioFileManager = add_legacy_compatibility(AudioFileManager)

# Rest of the imports...
from server.services.sound_level_updater import SoundLevelUpdater
from shared_resources import Constants
# ... other imports ...

logger = logging.getLogger(__name__)

class LegacyPagingServer:
    def __init__(self):
        # Initialize variables
        
        # Audio managers for away and custom messages
        self.__away_messages_manager: Union[None, AudioFileManager] = None
        self.__custom_messages_manager: Union[None, AudioFileManager] = None
        
        self.__initialise_services()
        
        # Other initialization code...
        
    def __initialise_services(self) -> None:
        """
        Initialize all the different services necessary for the app operation
        """
        self.__sound_level_updater = SoundLevelUpdater()  # Used when recording or playing recorded files
        
        # Initialize custom messages manager with legacy compatibility
        self.__custom_messages_manager = AudioFileManager(
            storage_dir=Constants.MESSAGE_PATH,
            metadata_file=Constants.CUSTOM_MESSAGE_BKP_FILE,
            input_device="plug:dsnoop_paging",
            output_device="plug:master1"
        )
        
        # Set up sound level callback
        self.__custom_messages_manager.set_sound_level_callback(
            lambda level: self.__sound_level_updater.set_new_sound_level(direction="input", new_value=level)
        )
        
        # Initialize away messages manager with legacy compatibility
        self.__away_messages_manager = AudioFileManager(
            storage_dir=Constants.MESSAGE_PATH,
            metadata_file=Constants.AWAY_MESSAGE_BKP_FILE,
            input_device="plug:dsnoop_paging",
            output_device="plug:master1"
        )
        
        # Set up sound level callback
        self.__away_messages_manager.set_sound_level_callback(
            lambda level: self.__sound_level_updater.set_new_sound_level(direction="input", new_value=level)
        )
        
        # Rest of initialization...
    
    # Rest of the class implementation...
    
    def _page_custom_message(self, start: bool):
        stop = not start
        if start:
            # Use the same thread, as paging and sending message at the same time is not a valid use case
            if self.__paging_thread is None:
                self.__last_selected_clients, self.__last_selected_clients_formatted = self.nextion_interface.get_selected_clients()
                if len(self.__last_selected_clients):
                    # Use get_message directly from the manager
                    file_path = self.__custom_messages_manager.get_message("custom_message", audio_file_id=11)
                    if file_path != "No file found":
                        logger.debug(f"Paging custom message to {self.__last_selected_clients_formatted}")
                        self.__paging_thread = Thread(
                            target=self.__pmaster.send_page_group_request,
                            kwargs={"receiver_id": self.__last_selected_clients, "priority": self._paging_priority,
                                    "audio_file_path": file_path},
                            daemon=True, name="PageCustomMsg"
                        )
                        message = f"Paging custom message to Station {self.__last_selected_clients_formatted}"
                        self.nextion_interface.message = message
                        # Rest of the implementation...
    
    # Other methods...
    
    def handle_nextion_state_changes(self):
        # Handle state changes...
        
        # Example of handling recording completion
        if self.nextion_state.p_state == self.nextion_interface.paging_state_enum.RECORDING_CUSTOM_MESSAGE:
            if self.nextion_interface.buttons_state.get_button(self.nextion_interface.key_id.STOP_BUTTON):
                # Close worker threads
                self.__close_worker_threads()
                
                # Finalize recording using the manager directly
                tmp_info = self.__custom_messages_manager.current_file.copy()
                self.__custom_messages_manager.finalize_recording(tmp_info)
                self.__custom_messages_manager.exit()  # Use exit directly from manager
                
                message = "Finished recording"
                logger.warning(message)
                self.nextion_interface.message = message
                self.change_nextion_state(self.nextion_interface.paging_state_enum.IDLE, inspect.currentframe().f_lineno)
        
        # Example of handling force exit
        elif self.nextion_state.p_state == self.nextion_interface.paging_state_enum.USE_AWAY_MESSAGE:
            if self.__custom_messages_manager.is_running:  # Use is_running directly from manager
                self.__custom_messages_manager.force_exit()  # Use force_exit directly from manager
        
        # Example of checking if recording/playback is active
        if not self.__custom_messages_manager.is_running and not self.__away_messages_manager.is_running:
            # Do something when neither is active
            pass
        
        # Example of starting recording
        elif self.nextion_state.state == self.nextion_interface.paging_state_enum.RECORDING_CUSTOM_MESSAGE:
            if not self.__custom_messages_manager.is_running:  # Use is_running directly from manager
                self.__pmaster.set_master_state(PagingMasterState.RECORDING_MESSAGE)
                self.__start_worker_threads(message="Recording Custom message...", timeout=2)
                btn_id = self.nextion_interface.custom_msg_btn_id
                self.__custom_messages_manager.start_recording(btn_id, "custom_message")
        
        # Example of playing audio
        elif self.nextion_state.state == self.nextion_interface.paging_state_enum.SENDING_CUSTOM_MESSAGE:
            clients, _ = self.nextion_interface.get_selected_clients()
            
            if len(clients) == 0:
                # Play locally only once
                if not self.__custom_messages_manager.is_running and not self.__custom_messages_manager.played_once:
                    self.__pmaster.set_master_state(PagingMasterState.SENDING_PAGING_MESSAGE)
                    self.__start_worker_threads(message="Playing custom message...", timeout=1)
                    self.__custom_messages_manager.play_audio(self.nextion_interface.custom_msg_btn_id)
                
                # Check if playback has finished
                elif self.__custom_messages_manager.finished():
                    if self.__pmaster.paging_audio_service.paging_state:
                        logger.debug("Recorded message paging ongoing...")
                    else:
                        self.__custom_messages_manager.played_once = False  # Reset the flag
                        self.change_nextion_state(self.nextion_interface.paging_state_enum.FINISH_OPERATION, inspect.currentframe().f_lineno)
    
    # Rest of the class implementation...