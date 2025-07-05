import logging
import inspect
import time
from datetime import datetime
from threading import Thread, Lock
from typing import Union, Callable, Tuple

from barix.system.barix_enums import BarixPagingApp

from IAppInfo import IAudio
from master.ipaging import IPaging
from master.paging_master import PagingMasterState, IntercomClient
from nextion.nextion_enum import KeyStatus, NextionICPagingState, NextionSimplePagingState
from nextion.nextion_interface import NextionInterface
from nextion.nextion_panel import NextionPanelReset
from server.services.audio_file_manager import AudioFileManager
from server.services.audio_file_manager.legacy_compatibility_simple import add_legacy_compatibility
from server.services.record_service import MessageRecordService
from server.services.recorded_message_service import RecordedMessagesService
from server.services.ring_service import RingService
from server.services.sound_level_updater import SoundLevelUpdater
from server.leds_control import LedsController
from server.utils import audio_uci_to_config_dict
from shared_resources import Constants

logger = logging.getLogger("PagingServer")


class PagingServer(IAudio):
    # Added "nextion_panel: NextionPanel" to allow for manual buttons state changes
    def __init__(self, nextion_panel_serial_config: dict, nextion_interface: NextionInterface, paging_master: IPaging):
        """
            This server is responsible
            for sending and receiving requests to clients as well as interface with the Nextion touch screen panel
        @param nextion_panel_serial_config: Contains the serial interface configuration for the nextion panel
        @param nextion_interface: Shared between NextionPanel, PagingServer and StateChangeRecorder
        @param paging_master: Either ICPaging or SimplePaging master class

        """

        try:
            config = audio_uci_to_config_dict()
        except Exception as e:
            logger.warning(f"Could not load settings: {e}")
            raise e
        self.leds = LedsController()
        self.leds.control(led='status', color='green', blink=True)

        self._paging_priority = int(config["paging_priority"])
        self.__pmaster = paging_master
        self.__pmaster.set_paging_server_callback(self._set_active_audio_obj_callback)

        self.__pmaster.set_paging_priority(self._paging_priority)

        self.nextion_interface = nextion_interface
        self.nextion_state = nextion_interface.nextion_state
        try:
            self.button_state = nextion_interface.buttons_state
        except Exception as e:
            logger.warning(f"Error: {e}")

        # Service accessors
        self.active_obj_lock = Lock()
        self.__active_audio_obj = {}
        self.__ring_service = None
        self.__sync_files_wd = None
        self.__sound_level_updater = None
        self.nextion_panel_serial_config: dict = nextion_panel_serial_config  # This is used to blink the Custom/Away messages buttons

        # Audio recording related
        # self.__record_service = None
        # self.__recorded_message_service = None
        self.__away_messages_manager: Union[None, AudioFileManager] = None
        self.__custom_messages_manager: Union[None, AudioFileManager] = None

        self.__initialise_services()

        # Thread handles
        self.__status_listen_service_thread = None
        self.__update_group_buttons_service_thread = None
        self.__status_send_thread = None
        self.__monitor_calling_client_thread = None
        self.__paging_thread = None
        self.__call_thread = None
        self.__sync_files_wd_thread = None
        self.__send_message_with_timeout_thread = None

        # Variables
        self.__last_group_buttons_update_time = None
        self.__group_buttons_update_timeout = 1
        # To accommodate the possibility that the selection has been automatically reset, keep the last selection
        self.__last_selected_clients = None
        self.__last_selected_clients_formatted = None

        # Flags
        self._exit = False
        self.__worker_threads_list = []  # If there are multiple worker threads to be closed, add them to the list
        self.__kill_thread_flag = False  # Only set True from __close_worker_threads function
        self.__start_away_answer_flag = False  # Set True from check_clients when an incoming call is received in UNATTENDED
        self.away_press_start_timer = None  # Use to mark the start of an Away button press.
        self._change_nextion_message = True  # Use to indicate when the message needs to be changed

    def __initialise_services(self) -> None:
        """
            Initialise all the different services, necessary for the app operation
        :return: None
        """

        self.__sound_level_updater = SoundLevelUpdater()  # Used when recording or playing recorded files
        # Create the custom messages manager
        self.__custom_messages_manager = AudioFileManager(
            storage_dir=Constants.MESSAGE_PATH,
            metadata_file=Constants.MESSAGE_PATH + Constants.CUSTOM_MESSAGE_BKP_FILE,
            input_device="plug:dsnoop_paging",
            output_device="plug:master1",
            message_type="custom_message"
        )

        # Apply legacy compatibility
        self.__custom_messages_manager = add_legacy_compatibility(self.__custom_messages_manager)

        # Set up sound level callback
        self.__custom_messages_manager.set_sound_level_callback(
            lambda level: self.__sound_level_updater.set_new_sound_level(direction="input", new_value=level)
        )

        # Create the away messages manager
        self.__away_messages_manager = AudioFileManager(
            storage_dir=Constants.MESSAGE_PATH,
            metadata_file=Constants.AWAY_MESSAGE_BKP_FILE,
            input_device="plug:dsnoop_paging",
            output_device="plug:master1",
            message_type="away_message"
        )

        # Apply legacy compatibility
        self.__away_messages_manager = add_legacy_compatibility(self.__away_messages_manager)

        # Set up sound level callback
        self.__away_messages_manager.set_sound_level_callback(
            lambda level: self.__sound_level_updater.set_new_sound_level(direction="input", new_value=level)
        )

        # self.__record_service = MessageRecordService(self.nextion_panel_serial_config, self.nextion_interface, self.__sound_level_updater)
        # self.__record_service.set_paging_server_callback(self._set_active_audio_obj_callback)
        # self.__recorded_message_service = RecordedMessagesService(self.__sound_level_updater)
        # self.__recorded_message_service.set_paging_server_callback(self._set_active_audio_obj_callback)

        self.__ring_service = RingService(use_baco=True, nextion_interface=self.nextion_interface)
        # Once the RingService has been initialised, we need to set the ding-dong
        self.__pmaster.set_ding_dong_path(self.__ring_service.active_ding_dong_path)
        self.__ring_service.set_paging_server_callback(self._set_active_audio_obj_callback)
        # self.__sync_files_wd = SyncFilesWD(["*.wav"])
        self.leds.control(led='status', color='green', blink=False)
        logger.info("All services initialised.")

    def __start_services(self):
        """
            Runs all the different services. Only call at the start from self.run()
        @return: None
        """
        if self.__pmaster.app_type == BarixPagingApp.ICPaging:
            self._monitor_calling_client(start=True)
        self._status_send_service(start=True)
        self._listen_status_message_service(start=True)
        self._update_group_buttons_service(start=True)
        # self._sync_files_service(start=True)
        logger.info("All services started.")

    def __stop_services(self):
        """
            Properly stop each individual service
        @return:
        """
        self._status_send_service(start=False)
        self._listen_status_message_service(start=False)
        self._update_group_buttons_service(start=False)
        self._monitor_calling_client(start=False)
        self._incoming_call(start=False)
        self._sync_files_service(start=False)
        logger.info("All services stopped.")

    # TODO: Not fully implemented and tested yet
    def _sync_files_service(self, start=True):
        if start:
            if self.__sync_files_wd_thread is None:
                try:
                    self.__sync_files_wd_thread = Thread(
                        target=self.__sync_files_wd.run, daemon=True, name="SyncFilesWD"
                    )
                    self.__sync_files_wd_thread.start()
                except Exception as e:
                    logger.error(f"Couldn't start the SyncFilesWD thread: {e}")
            else:
                logger.warning(
                    "Attempt to start the SyncFilesWD. Service is already running!"
                )
        else:
            logger.info(f"Stopping _sync_files_service...")
            if self.__sync_files_wd_thread is not None:
                self.__sync_files_wd.exit()
                self.__sync_files_wd_thread.join()
                self.__sync_files_wd_thread = None
            logger.info("Stopped _sync_files_service")

    def _status_send_service(self, start=True):
        if start:
            if self.__status_send_thread is None:
                logger.info("Send status service started.")
                self.__status_send_thread = Thread(
                    target=self.__pmaster.send_status_message, daemon=True, name="SendStatus"
                )
                self.__status_send_thread.start()
            else:
                logger.warning(
                    "Attempt to start the send status service. Service is already running!"
                )
        else:
            logger.info("Stopping _status_send_service...")
            if self.__status_send_thread is not None:
                self.__status_send_thread.join()
            logger.info("Stopped _status_send_service")

    def _listen_status_message_service(self, start=True):
        if start:
            if self.__status_listen_service_thread is None:
                logger.info("Status listening service started")
                self.__status_listen_service_thread = Thread(target=self.__pmaster.listen_client_status, daemon=True,
                                                             name=f"ListenStatus-{self.__pmaster.app_type}")
                self.__status_listen_service_thread.start()
            else:
                logger.warning(
                    "Attempt to start the LISTEN status service. Service is already running!"
                )
        else:
            logger.info('Stopping _listen_status_message_service...')
            if self.__status_listen_service_thread is not None:
                self.__status_listen_service_thread.join()
            logger.info("Stopped _listen_status_message_service")

    def _update_group_buttons_service(self, start=True):
        if self.__pmaster.app_type == BarixPagingApp.SimplePaging:
            if start:
                if self.__update_group_buttons_service_thread is None:
                    self.__update_group_buttons_service_thread = Thread(
                        target=self._update_group_buttons, daemon=True, name="UpdateGroupBtns"
                    )
                    self.__update_group_buttons_service_thread.start()
                    logger.info("Update group buttons service started")
                else:
                    logger.warning(
                        "Attempt to start the Update group buttons service. Service is already running!"
                    )
            else:
                logger.info('Stopping _update_group_buttons_service...')
                if self.__update_group_buttons_service_thread is not None:
                    self.__update_group_buttons_service_thread.join()
                logger.info("Stopped __update_group_buttons_service_thread")

    def _update_group_buttons(self):
        """
            This is started as a thread, and makes sure to update the groups buttons for SimplePaging clients
            when there is a change of state in the available clients
        Returns: None
        """

        def time_to_update_group_buttons() -> bool:
            """
                Check if its time to update the buttons or not. This significantly reduces the
            :return: True if buttons need to be updated, False otherwise
            """
            time_now = datetime.now()
            if self.__last_group_buttons_update_time:
                time_since_last = time_now - self.__last_group_buttons_update_time
                if time_since_last.seconds >= self.__group_buttons_update_timeout:
                    self.__last_group_buttons_update_time = time_now
                    logger.debug("Time to update!", color='bg_blue')
                    return True
            else:
                self.__last_group_buttons_update_time = time_now
            return False

        while not self._exit:
            with self.__pmaster.group_state_change_cond:
                self.__pmaster.group_state_change_cond.wait()

                if time_to_update_group_buttons():
                    self.nextion_interface.set_available_clients(available_clients=self.__pmaster.get_available_clients())

                # print('------------------------------ Finished update group buttons ----------------------------------')

    def check_clients(self):
        while not self._exit:
            if not self.__pmaster.exit_flag:
                with self.nextion_interface.nextion_condition:
                    # Using the condition will only loop through the state machine when there is an actual state change
                    self.nextion_interface.nextion_condition.wait()
                    self.__pmaster.purge_stale_calling_client()
                    calling_client: IntercomClient = self.__pmaster.get_calling_client()
                    if calling_client:

                        if self.nextion_state.state == NextionICPagingState.IDLE:
                            self.change_nextion_state(NextionICPagingState.INCOMING_CALL_REQUEST, inspect.currentframe().f_lineno)
                            self.nextion_interface.message = (f"Station {calling_client.id} calling.\r\n"
                                                              f"Use Accept/Close call buttons")
                            # TODO: handle the calling station here.
                            self.__ring_service.active_station = calling_client.id

                        # TODO: Handle away and auto rejects here.
                        elif (
                                self.__pmaster.in_call and
                                self.nextion_state.state == NextionICPagingState.IN_ACTIVE_CALL and
                                calling_client.id != self.__pmaster.client_number_in_call
                        ):
                            self.__pmaster.reject_call(reason=0)
                            message = (f"Busy in another call.\r\n"
                                       f"Call from [{calling_client.id}] rejected")
                            self.nextion_interface.message = message
                            logger.warning(message)
                            time.sleep(1)  # TODO: Find a better way to change back the message without sleep
                            message = f"In Active call"
                            self.nextion_interface.message = message

                        elif self.nextion_state.state == NextionICPagingState.UNATTENDED_MODE:
                            message = f"Station {calling_client.id} calling. Reply with away message..."
                            self.nextion_interface.message = message
                            if not self.__start_away_answer_flag:
                                self.__start_away_answer_flag = True

                        elif self.nextion_state.state == NextionICPagingState.CALL_FORWARDING_MODE:
                            self.__pmaster.reject_call(reason=2)
                            self.nextion_interface.message = "Call Forwarding Mode Active"
                            self._change_nextion_message = True

                    else:
                        if self.nextion_state.state == NextionICPagingState.INCOMING_CALL_REQUEST:
                            self.change_nextion_state(NextionICPagingState.IDLE, inspect.currentframe().f_lineno)
                            self.nextion_interface.nextion_condition.notify_all()
            else:
                logger.warning(f"Paging master set to exit. Need to exit too...")
                time.sleep(0.5)

    def _monitor_calling_client(self, start: bool):
        if start:
            if self.__monitor_calling_client_thread is None:
                self.__monitor_calling_client_thread = Thread(target=self.check_clients, daemon=True,
                                                              name="MonitorCallingClient")
                self.__monitor_calling_client_thread.start()
                logger.info("Monitoring the clients for incoming call")
            else:
                logger.warning(
                    "Attempt to start the LISTEN status service. Service is already running!"
                )
        else:
            logger.info(f"Stopping _monitor_calling_client")
            if self.__monitor_calling_client_thread is not None:
                self.__monitor_calling_client_thread.join()
            logger.info(f"Stopped _monitor_calling_client")

    def get_end_clients_selection(self) -> Tuple[list, str]:
        """
            Utility function, to help get the correct client selection. This is useful if the buttons
            on the panel were automatically deselected based on the user config
        :return:
        """
        clients, clients_formatted = self.nextion_interface.get_selected_clients()
        if len(clients) == 0:
            return self.__last_selected_clients, self.__last_selected_clients_formatted
        return clients, clients_formatted

    def _page(self, start: bool):
        stop = not start
        if start:
            if self.__paging_thread is None:
                self.__last_selected_clients, self.__last_selected_clients_formatted = self.nextion_interface.get_selected_clients()
                if len(self.__last_selected_clients):
                    logger.info("=========================================================")
                    logger.info(f"Paging started to clients: {self.__last_selected_clients_formatted}")
                    self.__paging_thread = Thread(
                        target=self.__pmaster.send_page_group_request,
                        kwargs={"receiver_id": self.__last_selected_clients, "priority": self._paging_priority},
                        daemon=True,
                        name="Paging"
                    )
                    self.__paging_thread.start()
                    self.nextion_interface.message = f"Paging to Station: {self.__last_selected_clients_formatted}"
                    self.leds.control(led='status', color='green', blink=True, blink_time=(500,500))
                else:
                    self.nextion_interface.message = f"Paging: No Station selected!"
                    logger.debug("No clients selected")
            else:
                if self.__pmaster.capture_disabled:
                    self.nextion_interface.message = "Paging, microphone disabled!"
        elif stop and self.__paging_thread is not None:
            clients, clients_formatted = self.get_end_clients_selection()
            self.__last_selected_clients = None
            self.__last_selected_clients_formatted = None
            msg = f"Paging finished for clients: {clients_formatted}"
            logger.info(msg)
            self.__pmaster.end_paging(clients)
            if self.__paging_thread is not None:
                self.__paging_thread.join()
                self.__paging_thread = None                
            self.nextion_interface.message = "Finished paging!"
            self.leds.control(led='status', color='green', blink=False)
        else:
            logger.error("Unknown paging state!")

    # TODO: Not fully tested
    def _page_custom_message(self, start: bool):
        stop = not start
        if start:
            # Use the same thread, as paging and sending message at the same time is not a valid use case
            if self.__paging_thread is None:
                self.__last_selected_clients, self.__last_selected_clients_formatted = self.nextion_interface.get_selected_clients()
                if len(self.__last_selected_clients):
                    btn_id = self.nextion_interface.custom_msg_btn_id
                    # Use hardcoded ID 11 as it was working with the adapter
                    file_path = self.__custom_messages_manager.get_message(audio_file_id="11")
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
                        self.leds.control(led='status', color='green', blink=True, blink_time=(500,500))
                        self.__paging_thread.start()
                    else:
                        # Enhanced error message with more details
                        message = f"No custom message file found for button ID 11"
                        logger.warning(message)
                        self.nextion_interface.message = message
                        
                        # List available messages for debugging
                        logger.info("Available custom messages:")
                        for button_id, info in self.__custom_messages_manager.metadata.items():
                            if info.get("message_type") == "custom_message":
                                logger.info(f"  Button ID: {button_id}, Path: {info.get('path')}")

                else:
                    self.nextion_interface.message = f"Paging: No Station selected!"
                    logger.warning("No clients selected")
            else:
                if self.__pmaster.capture_disabled:
                    self.nextion_interface.message = "Paging, microphone disabled!"

        elif stop:
            if self.__paging_thread is not None:
                clients, clients_formatted = self.get_end_clients_selection()
                self.__last_selected_clients = None
                self.__last_selected_clients_formatted = None
                logger.info(f"Paging finished for clients {clients_formatted}")
                self.__pmaster.end_paging(clients)
                if self.__paging_thread is not None:
                    self.__paging_thread.join()
                    self.__paging_thread = None
                self.leds.control(led='status', color='green', blink=False)
            else:
                logger.warning("Paging thread already closed")
        else:
            logger.error("Unknown paging state!")

    def _accept_call(self):
        calling_client: IntercomClient = self.__pmaster.get_calling_client()
        if calling_client:
            self.__pmaster.send_call_accept_message()
            active_call_client: IntercomClient = self.__pmaster.get_active_client()
            if self.nextion_interface.is_half_duplex:  # HALF DUPLEX
                if self.__start_away_answer_flag:
                    # TODO
                    logger.warning("THIS HAS NOT BEEN YET IMPLEMENTED")
                    self.__call_thread = Thread(target=self.__pmaster.half_duplex_call,
                                                kwargs={"mode": "UNATTENDED",
                                                        "filepath": self.__away_messages_manager.get_message()}
                                                )
                    # message = "Sending away message HALF duplex"
                    # self.nextion_interface.message = message
                else:
                    self.__call_thread = Thread(target=self.__pmaster.half_duplex_call)
                    message = "In Active call (Listen)"
                    logger.info(message)
                    self.nextion_interface.message = message
            else:  # FULL DUPLEX
                if self.__start_away_answer_flag:
                    self.__call_thread = Thread(
                        target=self.__pmaster.full_duplex_call,
                        kwargs={"mode": "UNATTENDED",
                                "filepath": self.__away_messages_manager.get_message()}
                    )
                    message = f"Sending away message FULL duplex to Client {active_call_client.id}"
                    logger.info(message)
                    # self.nextion_interface.message = message
                else:
                    self.nextion_interface.message = "In Active call"
                    self.__call_thread = Thread(target=self.__pmaster.full_duplex_call)
            self.__call_thread.daemon = True
            self.__call_thread.setName("IntercomCall")
            self.__call_thread.start()
            self.nextion_interface.update_call_info(caller_id=active_call_client.id, caller_ip=active_call_client.ip)
            self.leds.control(led='status', color='green', blink=True, blink_time=(500,500))
        else:
            self.nextion_interface.message = "No incoming call!"
            logger.warning("No active client present")

    def _toggle_half_duplex_mode(self):
        if (
            self.nextion_interface.is_half_duplex_listen_mode
            and not self.__pmaster.is_listen_mode
        ):
            self.nextion_interface.message = "In Active call (Listen)"
            self.__pmaster.half_duplex_listen_mode()
        elif (
            not self.nextion_interface.is_half_duplex_listen_mode
            and self.__pmaster.is_listen_mode
        ):
            self.nextion_interface.message = "Active call (Talk)"
            self.__pmaster.half_duplex_talk_mode()

    def _incoming_call(self, start: bool):
        stop = not start
        # logger.warning(f"_incoming_call, start: {start}")
        if start:
            if self.__call_thread is None:
                self._accept_call()
            elif self.nextion_interface.is_half_duplex:
                self._toggle_half_duplex_mode()
            if self.nextion_interface.relay:
                active_call_client: IntercomClient = self.__pmaster.get_active_client()
                # Only change the first time the relay is set
                if not self.__pmaster.relay_times_used:
                    self.nextion_interface.message += f":\r\nDoor open for client {active_call_client.id}"
                # If needed uncomment this to show the number of times the relay button has been pressed
                # else:
                #     new_msg = self.nextion_interface.message.split(' x ', maxsplit=1)[0]
                #     self.nextion_interface.message = new_msg + f" x {self.__pmaster.relay_times_used + 1}"

                self.__pmaster.send_relay_message(
                    receiver_id=active_call_client.id,
                    relay_number=1  # Currently this is ignored by the clients
                )
        elif stop and self.__call_thread is not None:
            # End the call gracefully.
            self.nextion_interface.message = "Hanging up"
            calling_client: IntercomClient = self.__pmaster.get_active_client()
            self.__pmaster.close_call()
            if self.__call_thread is not None:
                self.__call_thread.join()
                self.__call_thread = None
            self.nextion_interface.message = f"Call with Station ID {calling_client.id} finished"
            self.leds.control(led='status', color='green', blink=False)

    def __close_worker_threads(self):
        if self.__send_message_with_timeout_thread is not None:
            self.__kill_thread_flag = True
            self.__send_message_with_timeout_thread.join()
            self.__send_message_with_timeout_thread = None

            self.__kill_thread_flag = False  # Reset back to default
            del self.__worker_threads_list[:]  # reset the list
            logger.debug("Worker threads closed")
        else:
            pass

    def __start_worker_threads(self, message, timeout):
        if self.__send_message_with_timeout_thread is None:
            self.__send_message_with_timeout_thread = Thread(
                target=self._send_message_with_timeout,
                kwargs={"message": message, "timeout": timeout},
                daemon=True, name="SendTimeoutMsg"
            )
            self.__send_message_with_timeout_thread.start()
            self.__worker_threads_list.append(self.__send_message_with_timeout_thread)

    def _send_message_with_timeout(self, message, timeout=None):
        """
            Opened in a separate thread to send a message after a timeout has expired
        :param message: Message to be sent
        :param timeout: Time after which the message is sent
        :return:
        """
        # TODO: Use a timer instead of a thread here
        count = 0
        delay = 0.1  # Check if the thread should be killed earlier
        while self.nextion_state.state != NextionICPagingState.FINISH_OPERATION:
            # Break when needed
            if self.__kill_thread_flag:
                break

            if timeout:
                if count % (timeout // delay) == 0:
                    if not self.__pmaster.paging_audio_service.paging_state:
                        self.nextion_interface.message = message
                    # Keep the current message
                    else:
                        self.nextion_interface.message = self.nextion_interface.message

            count += 1
            time.sleep(delay)

    def change_nextion_state(self, new_state: Union[NextionSimplePagingState, NextionICPagingState], call_line) -> None:
        """
            Most of the state changes are done from the nextion_panel and paging_master.
            However, this could be useful in some cases (e.g. icpaging)
        :param new_state: New state to be set
        :param call_line: Line from which the function was called. Used during debugging
        :return: None
        """
        if self.nextion_state.state != new_state:
            logger.debug(f"[{call_line}] Current: {self.nextion_state.state} -> New: {new_state}")
            self.nextion_state.state = new_state
        else:
            logger.info(f"Nextion state already {new_state}")

    def set_paging_server_callback(self, callback: Callable):
        pass

    def _set_active_audio_obj_callback(self, new_active_obj) -> None:
        """
            This function needs to be called before any audio object starts its operation.
            This way, the paging server would be later able to call the correct function and retrieve data from them
        """
        with self.active_obj_lock:
            if new_active_obj != self.__active_audio_obj:
                logger.debug(f"Current active audio object: {self.__active_audio_obj} -> New active audio object: {new_active_obj}")
                self.__active_audio_obj['object'] = new_active_obj
                self.__active_audio_obj['timestamp'] = datetime.now()

    def get_audio_levels(self) -> dict:
        audio_object = self.__active_audio_obj.get('object', None)
        # Default empty dict, in case there are no active audio objects
        levels_dict = dict(input_levels={}, output_levels={})
        if audio_object:
            # logger.info(f"Calling {audio_object} get_audio_levels()")
            try:
                levels_dict = audio_object.get_audio_levels()
            except Exception as e:
                logger.exception(f"Could not get audio levels: {e}")
        return levels_dict

    @staticmethod
    def timeout_expired(start_time: datetime.now, timeout) -> bool:
        return (datetime.now() - start_time).seconds >= timeout

    def run(self):

        self.__start_services()
        ready_msg = True
        time.sleep(0.5)  # Give some time to the screen to get responsive
        # Start with IDLE state
        self.change_nextion_state(self.nextion_interface.paging_state_enum.IDLE, 608)
        while not self._exit:
            with (self.nextion_interface.nextion_condition):
                self.nextion_interface.nextion_condition.wait()
                if self._exit:
                    break
                # This is used only for debugging. Needs the rpdb library to be installed on the device
                # debug_threads_cpu_load("PagingServer->run()")
                # rpdb.set_trace(addr='192.168.10.120', port=45454)  # DEBUG ONLY

                if self.nextion_interface.restart_main_app_flag:
                    self.nextion_interface.message = "Please wait while the Nextion panel\r\nis properly reset..."
                    raise NextionPanelReset
                if ready_msg:
                    ready_msg = False
                    self.nextion_interface.standby()
                # logger.info("Nextion panel state: %s", self.nextion_state.state)
                if self.nextion_state.state == self.nextion_interface.paging_state_enum.PAGING_ACTIVE:
                    self._page(start=True,)
                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.IN_ACTIVE_CALL:
                    if self.__ring_service.is_running:
                        self.__ring_service.exit()

                    # Needs to be here, so half duplex can work properly and relay messages can be detected
                    # TODO: Find a more efficient way of doing that
                    self._incoming_call(start=True)

                    if not self.__pmaster.in_call:
                        # close call when mic is disabled or connection from client is lost.
                        self._incoming_call(start=False)

                        if (
                            self.__pmaster.capture_disabled
                            and self.__pmaster.client_lost
                        ):
                            self.nextion_interface.message = (
                                "Hanging up, Microphone disabled and connection lost!"
                            )
                        elif self.__pmaster.client_lost:
                            self.nextion_interface.message = (
                                "Hanging up, connection lost!"
                            )
                        elif self.__pmaster.capture_disabled:
                            self.nextion_interface.message = (
                                "Hanging up, Microphone disabled!"
                            )
                        else:
                            self.nextion_interface.message = "Hanging up"
                        self.change_nextion_state(NextionICPagingState.IDLE, inspect.currentframe().f_lineno)
                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.IDLE:

                    if self.__send_message_with_timeout_thread is not None:
                        self.__close_worker_threads()  # Make sure the messages were stopped
                    # Close the paging thread
                    if self.__paging_thread is not None:
                        self._page(start=False)
                        self.nextion_interface.standby()
                    elif self.__call_thread is not None:
                        self._incoming_call(start=False)
                    elif self.nextion_state.p_state == self.nextion_interface.paging_state_enum.INCOMING_CALL_REQUEST:
                        calling_client: IntercomClient = self.__pmaster.get_calling_client()
                        logger.debug(f"self.__pmaster.rejected_call_flag: {self.__pmaster.rejected_call_flag}, "
                                       f"self.__pmaster.calling_client: {calling_client}, "
                                       f"self.__pmaster.rejected_client: {self.__pmaster.get_rejectected_client()}")

                        # This case is possible when the client stopped calling or timed out
                        if not self.__pmaster.rejected_call_flag:
                            if calling_client is None:
                                msg = f"Client timed out or stopped calling..."
                                self.nextion_interface.message = msg
                                self.__ring_service.exit()
                                self.__pmaster.reject_call(reason=1)
                                # self.change_nextion_state(NextionICPagingState.IDLE)

                            # This case is possible when the call was rejected by the panel.
                            else:
                                msg = f"Call from client ID {calling_client.id} Rejected"
                                self.nextion_interface.message = msg
                                self.__ring_service.exit()
                                self.__pmaster.reject_call(reason=2)
                            logger.warning(msg, color='magenta')

                    # # Finish recording a message
                    # elif self.nextion_state.p_state == self.nextion_interface.paging_state_enum.MESSAGE:
                    #     self.__record_service.exit()

                    elif self.nextion_state.p_state == self.nextion_interface.paging_state_enum.UNATTENDED_MODE or \
                            self.nextion_state.p_state == self.nextion_interface.paging_state_enum.CALL_FORWARDING_MODE:
                        self.__close_worker_threads()  # Taken care at entering IDLE state
                        if self.away_press_start_timer is not None:
                            self.away_press_start_timer = None
                        if not self._change_nextion_message:
                            self._change_nextion_message = True

                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.INCOMING_CALL_REQUEST:
                    if not self.__ring_service.is_running:
                        logger.info("Incoming call! -> Start ringing", color='cyan')
                        self.__ring_service.run()
                        self.leds.control(led='status', color='green', blink=True, blink_time=(250,250))
                    logger.debug("Incoming call!")
                # TODO: This state is set when holding the Away button for more than 4 seconds.
                #    This happens inside UNATTENDED mode state.
                    self.nextion_interface.nextion_condition.notify_all()

                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.CALL_FORWARDING_MODE:
                    if self.away_press_start_timer is not None:
                        self.away_press_start_timer = None

                    if self._change_nextion_message:
                        self._change_nextion_message = False
                        self.nextion_interface.message = "All incoming calls will be rejected!!!"
                        self.__pmaster.set_master_state(PagingMasterState.CALL_REJECT_MODE)
                        # self.__start_worker_threads(message="All incoming calls will be rejected!!!", timeout=2)
                    self.nextion_interface.nextion_condition.notify_all()

                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.UNATTENDED_MODE:

                    if self.away_press_start_timer is None:
                        self.away_press_start_timer = datetime.now()

                    # Only start it if a call is not ongoing
                    if not self.__pmaster.in_call and self._change_nextion_message:
                        self.__pmaster.set_master_state(PagingMasterState.UNATTENDED_MODE)
                        self._change_nextion_message = False
                        self.nextion_interface.message = "Automatic answer to calls..."

                    # Detect a long button press
                    if self.button_state.get_button_status(self.nextion_interface.key_id.AWAY_BUTTON) == KeyStatus.PRESSED:

                        if self.timeout_expired(self.away_press_start_timer, self.nextion_interface.CALL_FORWARDING_PRESS_DURATION):
                            self._change_nextion_message = True
                            self.__close_worker_threads()
                            logger.info("This was a long press (>4s). Changing to CALL_FORWARDING_MODE")
                            self.change_nextion_state(self.nextion_interface.paging_state_enum.CALL_FORWARDING_MODE, inspect.currentframe().f_lineno)
                            self.leds.control(led='status', color='green', blink=True, blink_time=(1000, 1000))

                    # Set inside check_clients()
                    if self.__start_away_answer_flag:
                        self.__close_worker_threads()
                        if not self.__pmaster.in_call:
                            logger.info("Accepting the call")
                            self._incoming_call(start=True)

                        # # Play locally
                        # if not self.__recorded_message_service.is_running:
                        #     # self.__close_worker_threads()
                        #     self.__start_worker_threads(message="Answer with away message...", timeout=1)
                        #     self.__recorded_message_service.play_locally(audio_file_type="away_message",
                        #                                                  audio_file_id="")
                        # # Only returns True after the local playback thread has finished
                        # if self.__recorded_message_service.exit():
                        #     logger.warning("Local playback has finished for UNATTENDED MODE.")
                        #     # self.nextion_state.state = NextionPagingState.FINISH_OPERATION

                        if self.__pmaster.end_message_transmission or not self.__pmaster.in_call:
                            self.__start_away_answer_flag = False
                            self.change_nextion_state(self.nextion_interface.paging_state_enum.FINISH_OPERATION, inspect.currentframe().f_lineno)
                            # close call when mic is disabled or connection from client is lost.
                            self._incoming_call(start=False)

                            if self.__pmaster.capture_disabled and self.__pmaster.client_lost:
                                message = "Hanging up, Microphone disabled and connection lost!"
                            elif self.__pmaster.client_lost:
                                message = "Hanging up, connection lost!"
                            elif self.__pmaster.capture_disabled:
                                message = "Hanging up, Microphone disabled!"
                            else:
                                message = "Hanging up"
                            self.nextion_interface.message = message
                            # self.change_nextion_state(NextionPagingState.FINISH_OPERATION)
                    self.nextion_interface.nextion_condition.notify_all()

                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.FINISH_OPERATION:
                    if (
                        self.nextion_state.p_state == self.nextion_interface.paging_state_enum.RECORDING_AWAY_MESSAGE or
                        self.nextion_state.p_state == self.nextion_interface.paging_state_enum.RECORDING_CUSTOM_MESSAGE
                    ):
                        self.__close_worker_threads()

                        if self.nextion_state.p_state == self.nextion_interface.paging_state_enum.RECORDING_AWAY_MESSAGE:
                            self.__away_messages_manager.exit()
                        else:
                            self.__custom_messages_manager.exit()
                            tmp_info = self.__custom_messages_manager.current_file.copy()
                            logger.warning(f"Current tmp_info: {tmp_info}", color='magenta')
                            self.__custom_messages_manager.finalize_recording(tmp_info)
                        # self.__record_service.exit()
                        message = "Finished recording"
                        logger.warning(message)
                        self.nextion_interface.message = message
                        self.change_nextion_state(self.nextion_interface.paging_state_enum.IDLE, inspect.currentframe().f_lineno)

                    elif self.nextion_state.p_state == self.nextion_interface.paging_state_enum.USE_AWAY_MESSAGE:

                        if self.__away_messages_manager.is_running():
                            self.__close_worker_threads()
                            message = "Stopped playing away message..."
                            self.nextion_interface.message = message
                            self.__away_messages_manager.force_exit()
                            self.change_nextion_state(self.nextion_interface.paging_state_enum.IDLE, inspect.currentframe().f_lineno)
                        else:
                            self.__close_worker_threads()
                            message = "Finished playing away message"
                            self.nextion_interface.message = message
                            self.change_nextion_state(self.nextion_interface.paging_state_enum.IDLE, inspect.currentframe().f_lineno)

                    elif self.nextion_state.p_state == self.nextion_interface.paging_state_enum.SENDING_CUSTOM_MESSAGE:

                        self._page_custom_message(start=False)
                        self.__close_worker_threads()

                        clients, _ = self.nextion_interface.get_selected_clients()
                        if len(clients):
                            message = "Custom message sent!"
                            logger.warning(">>>>>>>>>>>>> " + message + " <<<<<<<<<<<<<<")
                            self.nextion_interface.message = message
                        if self.__custom_messages_manager.is_running:
                            self.__custom_messages_manager.force_exit()

                        self.change_nextion_state(self.nextion_interface.paging_state_enum.IDLE, inspect.currentframe().f_lineno)

                    # If a message was automatically answered
                    elif self.nextion_state.p_state == self.nextion_interface.paging_state_enum.UNATTENDED_MODE:
                        self._incoming_call(start=False)
                        self.__close_worker_threads()

                        # self.nextion_interface.message = message
                        self._change_nextion_message = True  # This way the Automatic answer message will be displayed once
                        self.change_nextion_state(self.nextion_interface.paging_state_enum.UNATTENDED_MODE, inspect.currentframe().f_lineno)
                    # logger.warning("Current running threads after FINISH_OPERATION:")
                    # for thread in enumerate():
                    #     logger.warning(thread.name)

                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.MESSAGE:

                    if not self.__custom_messages_manager.is_running() and not self.__away_messages_manager.is_running():
                        message = "Select the Away/Custom message\r\ncheckboxes. Hold Page to start recording"
                        # logger.info(message)
                        self.nextion_interface.message = message
                    else:
                        "Recording is currently undergoing... Please wait!"
                # TODO
                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.RECORDING_AWAY_MESSAGE:
                    if not self.__away_messages_manager.is_running():
                        self.__pmaster.set_master_state(PagingMasterState.RECORDING_MESSAGE)
                        self.__start_worker_threads(message="Recording Away message...",
                                                    timeout=2)
                        self.__away_messages_manager.run("away_message")
                    else:
                        message = "Nothing should happen here. The worker thread is taking" \
                                  "care of the message that needs to be displayed"
                        # logger.info(message)
                        # self.nextion_interface.message = message

                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.RECORDING_CUSTOM_MESSAGE:
                    if not self.__custom_messages_manager.is_running():
                        self.__pmaster.set_master_state(PagingMasterState.RECORDING_MESSAGE)
                        self.__start_worker_threads(message="Recording Custom message...",
                                                    timeout=2)
                        btn_id = self.nextion_interface.custom_msg_btn_id
                        self.__custom_messages_manager.start_recording(btn_id)
                    else:
                        message = "Nothing should happen here. The worker thread is taking" \
                                  "care of the message that needs to be displayed"
                        # logger.info(message)
                        # self.nextion_interface.message = message

                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.USE_AWAY_MESSAGE:
                    # aplay --channels 1 --format MU_LAW --rate 8000 away_message1.wav

                    if not self.__away_messages_manager.is_running():
                        self.__pmaster.set_master_state(PagingMasterState.SENDING_UNATTENDED_MESSAGE)
                        self.__start_worker_threads(message="Playing away message...", timeout=1)
                        self.__away_messages_manager.play_audio(self.__away_messages_manager.get_message())

                    elif self.__away_messages_manager.finished():
                        self.__away_messages_manager.played_once = False  # Reset the flag
                        self.change_nextion_state(self.nextion_interface.paging_state_enum.FINISH_OPERATION, inspect.currentframe().f_lineno)

                elif self.nextion_state.state == self.nextion_interface.paging_state_enum.SENDING_CUSTOM_MESSAGE:
                    # aplay --channels 1 --format MU_LAW --rate 8000 custom_message1.wav
                    # Page the message to the selected available_barp_clients
                    clients, _ = self.nextion_interface.get_selected_clients()

                    if len(clients) == 0:
                        # Play locally only once
                        if not self.__custom_messages_manager.is_running() and not self.__custom_messages_manager.played_once:
                            self.__pmaster.set_master_state(PagingMasterState.SENDING_PAGING_MESSAGE)
                            self.__start_worker_threads(message="Playing custom message...", timeout=1)
                            self.__custom_messages_manager.play_audio(self.nextion_interface.custom_msg_btn_id)

                        # True after the local playback finishes
                        elif self.__custom_messages_manager.finished():
                            # If we are still not done paging the message, we need to remain in this state
                            if self.__pmaster.paging_audio_service.paging_state:
                                logger.debug("Recorded message paging ongoing...")
                            else:
                                self.__custom_messages_manager.played_once = False  # Reset the flag
                                self.change_nextion_state(self.nextion_interface.paging_state_enum.FINISH_OPERATION, inspect.currentframe().f_lineno)

                    elif len(clients) and self.__paging_thread is None:
                        logger.info(">>>>>>>>>>>>>>>> Starting Custom Message Paging <<<<<<<<<<<<<<<<")
                        self._page_custom_message(start=True)

                    elif self.__pmaster.end_message_transmission:
                        self.change_nextion_state(NextionICPagingState.FINISH_OPERATION,
                                                  inspect.currentframe().f_lineno)

                else:
                    # TODO: implement other states
                    logger.warning(
                        f"State action {self.nextion_state.state} not implemented"
                    )
            # NOTE: The following delay should be carefully selected,
            # some state actions might be missed otherwise.
            # time.sleep(0.1)  # time delay between reading each state. If using the condition no longer needed
            # Make it small enough such that no state transition is ignored

    def stop(self):
        self.leds.control(led='status', color='red', blink=True, blink_time=(500,500))
        self._exit = True
        # Release the condition
        with self.nextion_interface.nextion_condition:
            self.nextion_interface.nextion_condition.notify_all()
        self.__pmaster.exit()
        self.__pmaster.stop_services()
        self.__stop_services()
        self.leds.control(led='status', color='red', blink=False)
