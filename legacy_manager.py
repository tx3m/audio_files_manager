import logging
import os
import pathlib
import subprocess
import time
from datetime import datetime
from os import path, remove
from threading import Thread
import json
from serial import Serial

import alsaaudio
import audioop

from IAppInfo import IAudio
from server.utils import audio_uci_to_config_dict
from utilities.utils import read_json
from shared_resources import Constants

from nextion.nextion_interface import NextionInterface

from server.services.sound_level_updater import SoundLevelUpdater

# configure logger
logger = logging.getLogger("MessageRecordService")


class MessageRecordService(IAudio):
    """Class to control the audio(capture) aspect for recording a custom message
    methods:
        run  : Start the service.
        exit : Stops the service.
    For usage see paging_server's class definition.
    """
    MAX_NEW_FILES = set([str(i) for i in range(1, 5)])

    # TODO: Added nextion_panel: NextionPanel, nextion_interface: NextionInterface
    #  to allow for manual button state manipulation
    def __init__(self, nextion_panel_serial_config: dict, nextion_interface: NextionInterface,
                 sound_level_updater: SoundLevelUpdater):
        try:
            self.config = audio_uci_to_config_dict()
        except Exception as e:
            logger.error("Initialization failed")
            raise Exception("MessageRecordService Initialization failed")

        self._paging_server_callback = None  # Used to notify paging_server that this is the active audio object
        self.__exit_flag = False
        if self.config["audio_format"] == "alaw":
            self.__audio_codec = alsaaudio.PCM_FORMAT_A_LAW
        elif self.config["audio_format"] == "ulaw":
            self.__audio_codec = alsaaudio.PCM_FORMAT_MU_LAW
        else:
            raise Exception(
                "Audio codec not recognized by Message Record service, valid option 'ulaw' and 'alaw'."
            )
        self.nextion_panel_serial_config = nextion_panel_serial_config
        self.nextion_interface = nextion_interface
        try:
            self.button_state = nextion_interface.buttons_state  # use for the flip_button function
        except Exception as e:
            logger.warning(f"Error: {e}")
        self._button_id = -1

        self.__frequency = self.config["sample_rate"]
        # "plug:dsnoop_paging" is only working with new FW versions. Use self.config["input_device"] otherwise
        self.__record_device = "plug:dsnoop_paging"
        # Those next values must match the alsa interface config on OS level
        self.__alsa_audio_format = alsaaudio.PCM_FORMAT_S16_LE
        self.__alsa_sample_rate = 44100
        self.__alsa_period_size = 480  # self.config["sample_rate"]
        self.__num_channel = self.config["num_channels"]

        self.message_type = "default"
        self.current_file = dict.fromkeys(["id", "filename", "sampling_rate", "encoding", "timestamp"])

        self.__message_path = Constants.MESSAGE_PATH
        # Initialize directory structure
        pathlib.Path(self.__message_path).mkdir(parents=True, exist_ok=True)
        # Away messages
        self.occupied_away_messages = set([])
        self._away_msg_backup_file = path.join(self.__message_path, Constants.AWAY_MESSAGE_BKP_FILE)
        self._away_messages = read_json(self._away_msg_backup_file)
        # Custom messages
        self.occupied_custom_messages = set([])
        self._custom_msg_backup_file = path.join(self.__message_path, Constants.CUSTOM_MESSAGE_BKP_FILE)
        self._custom_messages = read_json(self._custom_msg_backup_file)

        # Init SoundLevelUpdater
        self.__sound_level_updater = sound_level_updater  # SoundLevelUpdater()

        # Thread handles
        self.__message_record_thread = None
        self.__blink_button_text_thread = None
        self.__sound_level_updater_thread = None

        self.is_running = False

    def set_paging_server_callback(self, callback):
        self._paging_server_callback = callback

    def get_audio_levels(self) -> dict:
        # TODO
        if self._paging_server_callback:
            self._paging_server_callback(new_active_obj=self, obj_type='input')
        return dict(input_levels={}, output_levels={})

    def _generate_new_file_name(self) -> None:
        new_id = self.new_id
        if self.message_type == "away_message":
            self.occupied_away_messages.add(new_id)
            self._button_id = self.nextion_interface.key_id.AWAY_MESSAGE_CHECKBOX
        elif self.message_type == "custom_message":
            self.occupied_custom_messages.add(new_id)
            self._button_id = self.nextion_interface.key_id.CUSTOM_MESSAGE_CHECKBOX

        file_name = self.message_type + new_id + ".wav"
        full_path = path.join(self.__message_path, file_name)
        logger.info(f"Full path for new file: {full_path}")

        # TODO
        if path.exists(full_path):
            remove(full_path)
            logger.info("Overwriting existing file")
        else:
            logger.info("Creating new file...")

        open(full_path, mode="w").close()  # create new file
        self.current_file = {"id": new_id,
                             "filename": file_name,
                             "timestamp": self._create_timestamp(),
                             "sampling_rate": self.config["sample_rate"],
                             "encoding": self.config["audio_format"]
                             }

    # TODO
    def _already_used_ids(self):
        """
            Use to check the backup files which IDs have been already used
            to prevent unnecessary overwriting of files (e.g. on restart of the app)
        """
        pass

    @property
    def new_file_name(self):
        file = path.join(self.__message_path, self.current_file["filename"])
        return file

    # TODO: Not tested
    @property
    def new_id(self) -> [None, str]:
        """
            Gets an unoccupied new file id.
        """
        available_ids = []
        if self.message_type == "away_message":
            available_ids = MessageRecordService.MAX_NEW_FILES - self.occupied_away_messages
        elif self.message_type == "custom_message":
            available_ids = MessageRecordService.MAX_NEW_FILES - self.occupied_custom_messages
        else:
            # TODO: Take action if the message type is different than expected
            logger.warning("Message type not recognised")
            pass

        # logger.info(f"Available IDs: {available_ids}")

        if len(available_ids) == 0:
            logger.warning("Starting to overwrite files")
            if self.message_type == "away_message":
                self.occupied_away_messages = set([])
                available_ids = MessageRecordService.MAX_NEW_FILES - self.occupied_away_messages
            elif self.message_type == "custom_message":
                self.occupied_custom_messages = set([])
                available_ids = MessageRecordService.MAX_NEW_FILES - self.occupied_custom_messages
            else:
                # TODO: Take action if the message type is different than expected
                logger.warning("Message type not recognised")
                pass

        return min(available_ids)

    @staticmethod
    def _create_timestamp() -> str:
        return str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def update_json_backup(self, message_type=""):
        logger.info("Updating json backup file information...")
        if message_type == "away_message":
            try:
                self._away_messages[self.current_file["id"]] = {
                    "filename": self.current_file["filename"],
                    "sampling_rate": self.current_file["sampling_rate"],
                    "encoding": self.current_file["encoding"],
                    "timestamp": self.current_file["timestamp"]
                }
                self.save(self._away_msg_backup_file)
            except Exception as e:
                logger.warning("Couldn't write to the backup file: %s ", self._away_messages)
                logger.warning(f"Error: {e}")

        elif message_type == "custom_message":
            try:
                self._custom_messages[self.current_file["id"]] = {
                    "filename": self.current_file["filename"],
                    "sampling_rate": self.current_file["sampling_rate"],
                    "encoding": self.current_file["encoding"],
                    "timestamp": self.current_file["timestamp"]
                }
                self.save(self._custom_msg_backup_file)
            except Exception as e:
                logger.warning("Couldn't write to the backup file: %s ", self._custom_messages)
                logger.warning(f"Error: {e}")
        else:
            logger.error(f"Unsupported message type: {message_type}")
            raise Exception(f"Message type [{message_type}] not supported!!!")

    def save(self, backup_file):
        with open(backup_file, "w") as f:
            if self.message_type == "away_message":
                json.dump(self._away_messages, f)

            elif self.message_type == "custom_message":
                json.dump(self._custom_messages, f)

        logger.info(f"Backup information was stored to {backup_file}")

    def run(self, message_type):
        if self.__message_record_thread is None:
            self.__message_record_thread = Thread(target=self._record_audio, kwargs={"message_type": message_type},
                                                  daemon=True, name="MsgRecord")
            self.__message_record_thread.start()
            # logger.info("Started __message_record_thread : %s", self.__message_record_thread.name)

        if self.__blink_button_text_thread is None:
            logger.warning(f"DEBUG THIS HAS BEEN MOVED TO NEXTION PANEL")
            # self.__blink_button_text_thread = Thread(target=self._blink_button_text,
            #                                          daemon=True, name="BlinkButtonText")
            # self.__blink_button_text_thread.start()
            # logger.info("Started __blink_button_text_thread: %s", self.__blink_button_text_thread.name)

        if self.__sound_level_updater_thread is None:
            self.__sound_level_updater_thread = Thread(target=self.__sound_level_updater.run,
                                                       daemon=True, name="SoundLvlUpdater")
            self.__sound_level_updater_thread.start()

    def exit(self):
        self.__exit_flag = True

        if self.__sound_level_updater_thread is not None:
            self.__sound_level_updater.exit()
            self.__sound_level_updater_thread.join()
            self.__sound_level_updater_thread = None
            logger.info("Closed Sound level updater thread")

        if self.__blink_button_text_thread is not None:
            self.__blink_button_text_thread.join()
            self.__blink_button_text_thread = None
            logger.info("Closed Blink text thread")

        if self.__message_record_thread is not None:
            self.__message_record_thread.join()
            self.__message_record_thread = None
            logger.info("Closed Recording thread")

        self._reset_buttons_default_state()
        self.__exit_flag = False

    def _get_audio_device(self):
        # TODO: This no longer works as expected, and is only using the default values instead of the ones we set
        try:
            logger.info(f"Using type={alsaaudio.PCM_CAPTURE}, "
                        f"mode={alsaaudio.PCM_NONBLOCK}, device={str(self.__record_device).split(':')[1]}, channels={self.__num_channel}, "
                        f"rate={self.__alsa_sample_rate}, format={self.__alsa_audio_format}, periodsize={ self.__alsa_period_size }")
            audio_device = alsaaudio.PCM(
                type=alsaaudio.PCM_CAPTURE,
                mode=alsaaudio.PCM_NONBLOCK,  # PCM_NONBLOCK PCM_NORMAL
                device=self.__record_device,
                channels=self.__num_channel,
                rate=self.__alsa_sample_rate,
                format=self.__alsa_audio_format,
                periodsize=self.__alsa_period_size
            )
            return audio_device
        except Exception as e:
            logger.exception(f"Failure: Audio device inaccessible: {e}")
            return None

    def _blink_button_text(self):
        while self._button_id == -1:
            time.sleep(0.001)
        logger.info("Start blinking")
        logger.info("Button ID: %s", self._button_id)
        while not self.__exit_flag:
            self._sync_text_leds(self._button_id, "flip")
            time.sleep(0.4)

    def _sync_text_leds(self, button, operation):
        sync = False
        if operation == "set":
            self.button_state.set_button(button)
            sync = True
        elif operation == "reset":
            self.button_state.reset_button(button)
            sync = True
        elif operation == "flip":
            self.button_state.flip_button(button)
            sync = True

        if sync:
            if self.nextion_interface.nextion_panel_sync_leds_callback_fn:
                with Serial(
                        port=self.nextion_panel_serial_config["serial_port"],
                        baudrate=self.nextion_panel_serial_config["serial_baud_rate"],
                        timeout=self.nextion_panel_serial_config["serial_timeout"]
                ) as ser:
                    self.nextion_interface.nextion_panel_sync_leds_callback_fn(ser)
                    # self.nextion_panel.sync_leds(ser)
            else:
                logger.error(f"Callback for sync_leds not set!")

    def _reset_buttons_default_state(self):
        # self._sync_text_leds(KeyID.AWAY_MESSAGE_CHECKBOX, "reset")
        # self._sync_text_leds(KeyID.CUSTOM_MESSAGE_CHECKBOX, "reset")
        # sometimes self.button_id is -1, which crashes the app when calling self._sync_text_leds with that value
        # so just do nothing when is -1
        if self._button_id != -1:
            self._sync_text_leds(self._button_id, "reset")
            self._button_id = -1  # Reset button_id to default state

    def _record_audio(self, message_type="custom_message"):
        logger.info(f"Start recording message.")
        # When recording audio, have a parameter type of message
        self.message_type = message_type
        self.is_running = True
        audio_input_dev = self._get_audio_device()
        if audio_input_dev is None:
            logger.info(f"Could not get a recording device!.")
            self.is_running = False
            return False
        record_device_info_dic = audio_input_dev.info()
        logger.info(f"Current PCM recording device info: {record_device_info_dic}")
        refresh_max_value_counter = 0
        self._generate_new_file_name()

        tmp_raw_file_path = Constants.PAGING_MASTER_TMP_PATH + Constants.RECODED_MESSAGES
        pathlib.Path(tmp_raw_file_path).mkdir(parents=True, exist_ok=True)
        tmp_file = tmp_raw_file_path + f"last_{message_type}_message.wav"

        with open(tmp_file, "wb") as message_file:
            while not self.__exit_flag:
                l, data = audio_input_dev.read()
                if l:
                    refresh_max_value_counter += 1
                    if refresh_max_value_counter % 150 == 0:
                        sound_level = audioop.rms(data, 2)

                        # sound_level = audioop.max(data, 2)
                        # sound_level = audioop.avgpp(data, 2)
                        # sound_level = audioop.avg(data, 2)
                        self.__sound_level_updater.set_new_sound_level(direction="input", new_value=sound_level)

                    message_file.write(data)
                # Prevents excessive CPU usage
                time.sleep(0.001)

        if self.config["audio_format"] == "alaw":
            codec_in = "s16le"
            codec_out = "pcm_alaw"
        elif self.config["audio_format"] == "ulaw":
            codec_in = "s16le"
            codec_out = "pcm_mulaw"
        else:
            codec_in = "s16le"
            codec_out = "pcm_mulaw"

        add_header = True
        if add_header:
            self._add_audio_header(input_file=tmp_file, output_file=self.new_file_name,
                                   sample_rate_in=record_device_info_dic['rate'], sample_rate_out=self.__frequency,
                                   chan_in=record_device_info_dic['channels'], chan_out=self.__num_channel,
                                   ffmpeg_codec_in=codec_in, ffmpeg_codec_out=codec_out)
        else:
            # This will be equivalent to the original implementation
            os.system(f"cp {tmp_file} {self.new_file_name}")

        # Once done writing the data to the file, store it in the json backup
        self.update_json_backup(self.message_type)

        audio_input_dev.close()  # Free the audio resource
        self.is_running = False
        logger.info(f"Stop recording message")

    @staticmethod
    def _add_audio_header(input_file, output_file, sample_rate_in, sample_rate_out,
                          chan_in, chan_out, ffmpeg_codec_in, ffmpeg_codec_out) -> bool:

        command = [
            "ffmpeg",
            "-y",  # overwrite the output file if exists.
            "-f",
            f"{ffmpeg_codec_in}",
            "-ar",
            f"{sample_rate_in}",
            "-ac",
            f"{chan_in}",
            "-i",
            f"{input_file}",
            "-c:a",
            f"{ffmpeg_codec_out}",
            "-ar",
            f"{sample_rate_out}",
            "-ac",
            f"{chan_out}",
            f"{output_file}"
        ]

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        errs, outs = None, None
        try:
            outs, errs = process.communicate(timeout=10)

            if process.returncode == 0:
                # logger.info(f"Outs: {outs}")
                logger.info(f"Successful processing of: {output_file}")
                return True

            logger.info(f"Errs: {errs}")
            logger.warning(f"Failed processing of: {output_file}. Check for header-less source files.")
            logger.warning(f"Command used: {command}")
            return False
        except subprocess.CalledProcessError as e:
            logger.info(f"Errs: {e}")
            logger.warning(f"Failed processing of: {output_file}")
            return False

        except subprocess.TimeoutExpired:
            process.kill()
            logger.debug(f"Killing processing of {output_file} : errs :{errs}")
            # outs, errs = process.communicate()
            logger.warning(f"Timed out!")
            logger.warning(f"Command used: {command}")
            logger.warning("To avoid this, try increasing the timeout so larger files can be processed")
        return False
