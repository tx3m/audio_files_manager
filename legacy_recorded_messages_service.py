import logging
from datetime import datetime
from multiprocessing import Process
import sys
import alsaaudio
from os import path, popen
import subprocess
import time
import json

from IAppInfo import IAudio
from server.utils import audio_uci_to_config_dict
from server.services.sound_level_updater import SoundLevelUpdater
from nextion.nextion_interface import NextionInterface
from utilities.utils import read_json
from shared_resources import Constants


logger = logging.getLogger("RecordedMessagesService")


class RecordedMessagesService(IAudio):

    def __init__(self, sound_level_updater: SoundLevelUpdater):

        # Thread handles
        self.__message_play_thread = None
        self.__local_playback_process_handle = None
        # Flags
        self.__is_running = False
        self.__played_once = False  # Needed because of the ding-dong
        self._paging_server_callback = None  # Used to notify paging_server that this is the active audio object
        self.__exit_flag = False

        try:
            config = audio_uci_to_config_dict()
        except Exception as e:
            logger.warning(f"Could not load settings: {e}")
            raise ValueError
        self.config = config

        self.local_alsa_player = None
        self.__output_device = self.config["output_device"]
        self.__frequency = self.config["sample_rate"]
        self.__audio_format = self.config["audio_format"]
        self.__alsa_period_size = 1000  # self.config["sample_rate"]
        self.__num_channel = self.config["num_channels"]
        self.__audio_codec = "pcm_mulaw" if self.__audio_format == "ulaw" else "pcm_alaw"
        self.__alsa_audio_codec = alsaaudio.PCM_FORMAT_MU_LAW if self.__audio_format == "ulaw" else alsaaudio.PCM_FORMAT_A_LAW

        # At this point the path has been already prepared in record_service
        self.__message_path = Constants.MESSAGE_PATH
        # Away messages
        self._away_msg_backup_file = path.join(self.__message_path, Constants.AWAY_MESSAGE_BKP_FILE)
        self._away_messages = read_json(self._away_msg_backup_file)
        # Custom messages
        self._custom_msg_backup_file = path.join(self.__message_path, Constants.CUSTOM_MESSAGE_BKP_FILE)
        self._custom_messages = read_json(self._custom_msg_backup_file)
        # To be used to read from
        self._current_file = dict.fromkeys(["away_message", "custom_message"])

        self._load_newest_files()
        self._correct_encoding()  # Check files encoding, and if needed reencode them
        self.file_type = "default"

        # TODO: Currently the audio is sent as a file to alsa, hence cannot use the sound level updater atm
        self.__sound_level_updater = sound_level_updater

        logger.info(f"{self.name} initialized!")

    @property
    def name(self):
        return str(type(self).__name__)

    @property
    def is_running(self):
        return self.__is_running

    @property
    def played_once(self):
        return self.__played_once

    @played_once.setter
    def played_once(self, new_value: bool):
        if self.__played_once != new_value:
            logger.debug(f"Changing self.__played_once. to {new_value}")
            self.__played_once = new_value
        else:
            logger.debug(f"Same value {new_value} for self.__played_once")

    def set_paging_server_callback(self, callback):
        self._paging_server_callback = callback

    def get_audio_levels(self) -> dict:
        # TODO
        return dict(input_levels={}, output_levels={})

    def _get_local_player(self):
        logger.debug("Getting local alsa player")
        local_alsa_player = alsaaudio.PCM(
            alsaaudio.PCM_PLAYBACK,
            alsaaudio.PCM_NORMAL,
            self.__output_device
        )
        local_alsa_player.setchannels(self.__num_channel)
        local_alsa_player.setperiodsize(self.__alsa_period_size)  # 2972
        local_alsa_player.setrate(self.__frequency)
        local_alsa_player.setformat(self.__alsa_audio_codec)  # alsaaudio.PCM_FORMAT_S16_LE

        return local_alsa_player

    def _correct_encoding(self):
        """
            Check the encoding settings of the device and the stored files.
            If they are different, re-encode them.
            Apr 2025: In the new version of the app using baco this is no longer desired
        @return: None
        """
        logger.warning(f"TODO Use this to re-encode from ulaw/alaw to PCM", color='bg_cyan')

        # for file_id in self._away_messages:
        #     if self._away_messages[file_id]["sampling_rate"] != self.__frequency or \
        #             self._away_messages[file_id]["encoding"] != self.__audio_format:
        #         result, settings = self._reencode_audio_file(self._away_messages[file_id])
        #         if result:
        #             self.update_json_backup(message_type="away_message", file_id=file_id, new_settings=settings)
        #
        # for file_id in self._custom_messages:
        #     if self._custom_messages[file_id]["sampling_rate"] != self.__frequency or \
        #             self._custom_messages[file_id]["encoding"] != self.__audio_format:
        #         result, settings = self._reencode_audio_file(self._custom_messages[file_id])
        #         if result:
        #             self.update_json_backup(message_type="custom_message", file_id=file_id, new_settings=settings)

    def _reencode_audio_file(self, source_config):
        """

        @param source_config: Dictionary containing the current file configuration
        @return: Bool of the result, Dictionary with settings to be updated
        """
        # logger.info("Source config: %s", source_config)
        tmp_file = "/var/tmp/paging_master/tmp_audio_file.wav"
        updated_file_settings = {}

        file = source_config["filename"]
        input_audio_format = "mulaw"
        if source_config["encoding"] == "alaw":
            input_audio_format = "alaw"
        input_smp_rate = source_config["sampling_rate"]

        output_audio_format = input_audio_format
        if source_config["encoding"] != self.__audio_format:
            output_audio_format = "mulaw"
            if self.__audio_format == "alaw":
                output_audio_format = "alaw"

        file_to_encode = path.join(self.__message_path, f"{file}")
        # 1. Make a copy of the existing file in the RAM
        popen(f'cp {file_to_encode} {tmp_file}')
        # 2. Use this file as a source, and the original file as destination
        destination = path.join(self.__message_path, f"{file}")

        # Linux syntax : ffmpeg -y -f mulaw -ar 8000 -ac 1 -i away_message1.wav -ar 24000 away_message1_24.wav
        # ffmpeg -y -f mulaw -ar 8000 -ac 1 -i away_message1.wav -acodec pcm_alaw -f alaw -ar 8000 -ac 1 ./test.wav
        # For wav with header, the -f for the output needs to be wav:
        # ffmpeg -y -f mulaw -ar 8000 -ac 1 -i away_message1.wav -acodec pcm_alaw -f wav -ar 8000 -ac 1 ./test.wav
        command = [
            "ffmpeg",
            "-y",  # overwrite the output file if exists.
            "-f",
            f"{input_audio_format}",  # input file format
            "-ar",
            f"{input_smp_rate}",  # input file sample rate
            "-ac",
            "1",
            "-i",
            tmp_file,
            "-acodec",
            f"{self.__audio_codec}",  # output codec
            "-f",
            f"{output_audio_format}",  # output file format
            "-ar",
            f"{self.__frequency}",
            "-ac",
            "1",
            destination,
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            # logger.info("Executing command: %s", " ".join(command))
            outs, errs = process.communicate(timeout=5)

            if process.returncode == 0:
                popen(f'rm {tmp_file}')  # 3. Remove the file from RAM
                # use the same timestamp as the orig file, to avoid message order issues
                updated_file_settings = {
                                        "filename": file,
                                        "sampling_rate": self.__frequency,
                                        "encoding": self.__audio_format,
                                        "timestamp": source_config["timestamp"],
                                        }
                return True, updated_file_settings

            logger.debug(f"Outs: {outs}")
            logger.debug(f"Errs: {errs}")
            return False, updated_file_settings

        except subprocess.TimeoutExpired:
            process.kill()
            outs, errs = process.communicate()
            logger.warning(
                f"Timed out, killing processing of {file}.wav : errs :{errs}"
            )
            logger.warning("To avoid this, try increasing the timeout so larger files can be processed")
        return False, updated_file_settings

    def update_json_backup(self, new_settings, message_type="", file_id="", ):
        logger.info(f"Updating json backup file information for {new_settings['filename']}...")
        if message_type == "away_message":
            try:
                self._away_messages[file_id] = {
                    "filename": new_settings["filename"],
                    "sampling_rate": new_settings["sampling_rate"],
                    "encoding": new_settings["encoding"],
                    "timestamp": new_settings["timestamp"]
                }
                self.save(message_type, self._away_msg_backup_file)
            except Exception as e:
                logger.warning("Couldn't write to the backup file: %s ", self._away_messages)
                logger.warning(f"Error: {e}")

        elif message_type == "custom_message":
            try:
                self._custom_messages[file_id] = {
                    "filename": new_settings["filename"],
                    "sampling_rate": new_settings["sampling_rate"],
                    "encoding": new_settings["encoding"],
                    "timestamp": new_settings["timestamp"]
                }
                self.save(message_type, self._custom_msg_backup_file)
            except Exception as e:
                logger.warning("Couldn't write to the backup file: %s ", self._custom_messages)
                logger.warning(f"Error: {e}")
        else:
            logger.error(f"Unsupported message type: {message_type}")
            raise Exception(f"Message type [{message_type}] not supported!!!")

    def save(self, message_type, updated_backup_file):
        with open(updated_backup_file, "w") as f:
            if message_type == "away_message":
                json.dump(self._away_messages, f)

            elif message_type == "custom_message":
                json.dump(self._custom_messages, f)

        logger.debug(f"Backup information was stored to {updated_backup_file}")

    @staticmethod
    def _create_timestamp() -> str:
        return str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def _load_newest_files(self):
        from datetime import datetime

        newest_away_id = -1
        newest_custom_id = -1
        epochs = dict()
        logger.debug("Loading latest recorded messages...")
        if len(self._away_messages):
            # logger.info("Loading newest away message...")
            for elem in self._away_messages:
                curr_elem_timestamp = self._away_messages[elem]["timestamp"]

                utc_time = datetime.strptime(curr_elem_timestamp, "%Y-%m-%d %H:%M:%S")
                # logger.info("UTC time: %s", utc_time)
                current_file_epoch = (utc_time - datetime(1970, 1, 1)).total_seconds()
                # logger.info("Current file epoch: %s", current_file_epoch)

                epochs[elem] = current_file_epoch

            # logger.info(epochs)
            newest_away_id = max(epochs, key=epochs.get)
            self._current_file["away_message"] = newest_away_id
            self._current_file["away_message"] = self._load_particular_file("away_message", newest_away_id)

            del epochs
            epochs = dict()

        # logger.info("Custom message file: %s", self._away_messages)
        if len(self._custom_messages):
            # logger.info("Loading newest custom message...")
            for elem in self._custom_messages:
                curr_elem_timestamp = self._custom_messages[elem]["timestamp"]

                utc_time = datetime.strptime(curr_elem_timestamp, "%Y-%m-%d %H:%M:%S")
                # logger.info("UTC time: %s", utc_time)
                current_file_epoch = (utc_time - datetime(1970, 1, 1)).total_seconds()
                # logger.info("Current file epoch: %s", current_file_epoch)

                epochs[elem] = current_file_epoch

            # logger.info(epochs)
            newest_custom_id = max(epochs, key=epochs.get)
            self._current_file["custom_message"] = newest_custom_id
            self._current_file["custom_message"] = self._load_particular_file("custom_message", newest_custom_id)
            # logger.info("Files loaded: %s", self._current_file)
        logger.debug("Loading latest recorded messages finished!")

    def _load_particular_file(self, audio_file_type, file_id):
        if audio_file_type == "away_message":
            return self._away_messages[file_id]["filename"]
        elif audio_file_type == "custom_message":
            # file = read_json(self.away_msg_backup_file)
            return self._custom_messages[file_id]["filename"]
        else:
            logger.error("Missing or unrecognised file type: %s", audio_file_type)

    def _refresh_files_lists(self):
        self._away_messages = read_json(self._away_msg_backup_file)
        self._custom_messages = read_json(self._custom_msg_backup_file)

    def _load_audio_data(self, audio_file_path):
        audio_file = None
        # logger.info("Reading from file: %s", audio_file_path)
        with open(audio_file_path, 'rb') as fp:
            audio_file = fp.read()
        # # convert the data to 16-bit signed
        # if self.__audio_format == "ulaw":
        #     audio_file = audioop.ulaw2lin(audio_file, 2)
        # elif self.__audio_format == "alaw":
        #     audio_file = audioop.alaw2lin(audio_file, 2)
        # else:
        #     warning = "Unsupported audio format!"
        #     logger.warning(warning)
        #     raise Exception(warning)

        # logger.info("Loaded successfully!")
        return audio_file

    def _run(self, audio_file):
        self.__exit_flag = False
        if audio_file is not None:
            if self.__local_playback_process_handle is None:
                self.__local_playback_process_handle = Process(
                    target=self.local_alsa_player.write,
                    args=(audio_file,)
                )
                self.__local_playback_process_handle.daemon = True
                self.__local_playback_process_handle.start()
                # logger.info("Current process state: %s", self.__local_playback_process_handle.is_alive())

        else:
            logger.error("Not a valid audio file. Local playback not possible")

    def __terminate_local_play_operation(self):
        # Kill the local playback process. Directly terminates without waiting for finish
        if self.__local_playback_process_handle is not None:
            self.__local_playback_process_handle.terminate()
            self.__local_playback_process_handle.join()
            while self.__local_playback_process_handle.is_alive():
                logger.info("Still alive local_playback_process")
                time.sleep(1)
            self.__local_playback_process_handle = None
            self.__is_running = False
            logger.debug("Closed local message play process")

    def __exit(self):
        self.__exit_flag = True
        self.__terminate_local_play_operation()

        # Free the audio resource
        if self.local_alsa_player is not None:
            self.local_alsa_player.close()
            self.local_alsa_player = None
            logger.debug("Closed local alsa player")


    def force_exit(self):
        # logger.warning("Force exit function!!!")
        self.__exit()
        self.__is_running = False

    def finished(self):
        """
            Ends the operation after the playback has finished and returns True
            Otherwise immediately returns False
        """
        # logger.info("Local playback handle: %s", self.__local_playback_process_handle)
        if self.__local_playback_process_handle is not None:
            if not self.__local_playback_process_handle.is_alive():
                self.played_once = True
                self.force_exit()
                return True
            # logger.info("Still running...")

        # If None handle and exit flag -> Could not load file for playing
        elif self.__exit_flag:
            self.force_exit()
            return True

        return False

    def get_empty_custom_messages(self):
        """
                Use this function to returns a bitmask of missing custom message files (their IDs missing as keys)
                The returned string is to be sent to the Nextion Panel as a value to empty_msgs variable
            @return: 16 bits mask as a string (for example: 0xFEFE when only messages 1(bit0 and 9(bit8) are recorded)
        """
        self._refresh_files_lists()
        expected_ids = {str(i) for i in range(1, 17)}
        bitmask = 0xffff

        if len(self._custom_messages):
            found_ids = set(self._custom_messages.keys())
            missing_ids = expected_ids - found_ids
            bitmask = 0
            for id in missing_ids:
                bit = int(id) - 1
                bitmask |= (1 << bit)

        empty_bitmask = f"0x{bitmask:04X}"
        return empty_bitmask

    def get_message(self, audio_file_type="", audio_file_id=""):
        """
            Use this function to select an already recorded message
        @param audio_file_type: away_message OR custom_message
        @param audio_file_id: leave empty to select the newest message, otherwise chose the particular file ID
        @return: The filepath to be executed. If no files are available, return "No file found"
        """

        self._refresh_files_lists()
        self._load_newest_files()

        if len(self._away_messages) and audio_file_type == "away_message":
            if audio_file_id == "":  # Load the newest file
                audio_file_name = self._current_file["away_message"]
            else:  # Load the particular file requested
                logger.info("Loading file type: %s, file ID: %s", audio_file_type, audio_file_id)
                audio_file_name = self._load_particular_file(audio_file_type, audio_file_id)
            file_to_open = path.join(Constants.MESSAGE_PATH, audio_file_name)
            logger.info("File to be played: %s", file_to_open)

        elif len(self._custom_messages) and audio_file_type == "custom_message":
            if audio_file_id == "":  # Load the newest file
                audio_file_name = self._current_file["custom_message"]
            else:
                logger.info("Loading file type: %s, file ID: %s", audio_file_type, audio_file_id)
                audio_file_name = self._load_particular_file(audio_file_type, audio_file_id)
            file_to_open = path.join(Constants.MESSAGE_PATH, audio_file_name)
            logger.info("File to be played: %s", file_to_open)

        else:
            warning = f"Unknown file type {audio_file_type} or missing file"
            logger.warning(warning)
            file_to_open = "No file found"
            # raise Exception(warning)

        return file_to_open

    def play_locally(self, audio_file_type="", audio_file_id=""):
        # TODO: This needs to be moved to the paging/call service and use baco
        self.local_alsa_player = self._get_local_player()
        self.__is_running = True
        self._refresh_files_lists()
        self._load_newest_files()

        if len(self._away_messages) and audio_file_type == "away_message":
            self.__is_running = True
            if audio_file_id == "":  # Load the newest file
                audio_file_name = self._current_file["away_message"]
            else:  # Load the particular file requested
                logger.info("Loading file type: %s, file ID: %s", audio_file_type, audio_file_id)
                audio_file_name = self._load_particular_file(audio_file_type, audio_file_id)
            file_to_open = path.join(Constants.MESSAGE_PATH, audio_file_name)
            # logger.info("File to be loaded: %s", file_to_open)

            try:
                audio_file = self._load_audio_data(file_to_open)
            except Exception as ex:
                logger.warning("Unable to read the given %s into bytes: %s", file_to_open, ex)
                raise Exception("Could not load audio file data")

            # Local playback
            try:
                logger.info(f"Playing locally: {file_to_open}", color='cyan')
                self._run(audio_file)
            except TypeError:
                logger.warning(f"Oops: {sys.exc_info()[0]} occurred")
            except OSError as error:
                logger.warning("While in self._run(audio_file) the following error occurred:")
                logger.warning("Check audio device: %s", self.config["audio_device"]["playback"])
                logger.warning(error)

        elif len(self._custom_messages) and audio_file_type == "custom_message":
            self.__is_running = True
            if audio_file_id == "":  # Load the newest file
                audio_file_name = self._current_file["custom_message"]
            else:
                logger.info("Loading file type: %s, file ID: %s", audio_file_type, audio_file_id)
                audio_file_name = self._load_particular_file(audio_file_type, audio_file_id)
            file_to_open = path.join(Constants.MESSAGE_PATH, audio_file_name)
            # logger.info("File to be loaded: %s", file_to_open)

            try:
                audio_file = self._load_audio_data(file_to_open)
            except Exception as ex:
                logger.warning("Unable to read the given %s into bytes: %s", file_to_open, ex)
                raise Exception("Could not load audio file data")

            # Local playback
            try:
                logger.info(f"Playing locally: {file_to_open}", color='cyan')
                self._run(audio_file)
            except TypeError:
                logger.warning(f"Oops: {sys.exc_info()[0]} occurred")
            except OSError as error:
                logger.warning("While in self._run(audio_file) the following error occurred:")
                logger.warning("Check audio device: %s", self.config["audio_device"]["playback"])
                logger.warning(error)
                raise Exception("Local playback unsuccessful!")
        else:
            logger.error("Couldn't load the requested file of type: %s", audio_file_type)
            self.__exit_flag = True
            # raise Exception(f"File of type {audio_file_type} not found. Make sure such file exists!")
