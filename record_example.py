import logging
import threading
from typing import Any, Dict, Optional
from audio_file_manager import AudioFileManager


class InteractiveAudioTester:
    """
    A class-based interactive command-line script to test the AudioFileManager.
    This structure encapsulates state and logic, avoiding the need for `nonlocal`.
    """
    def __init__(self):
        self.log = logging.getLogger("RecordExample")
        self.manager = AudioFileManager()

        # --- State Variables ---
        self.recording_thread: Optional[threading.Thread] = None
        self.stop_event: Optional[threading.Event] = None
        self.temp_info: Optional[Dict[str, Any]] = None

        self.commands = {
            "start": self._handle_start,
            "stop": self._handle_stop,
            "cancel": self._handle_cancel,
            "play": self._handle_play,
            "ok": self._handle_ok,
            "exit": self._handle_exit,
        }

    def _print_instructions(self):
        print("\n--- Audio File Manager Interactive Test ---")
        print("Commands:")
        print("  start   - Begin recording audio for button 'test_button'.")
        print("  stop    - Stop the current recording and create a temporary file.")
        print("  cancel  - Stop the current recording and discard it.")
        print("  play    - Play the last recorded temporary file.")
        print("  ok      - Confirm the temporary recording and save it permanently.")
        print("  exit    - Quit the script and clean up temporary files.")
        print("-------------------------------------------")

    def _record_task(self, event: threading.Event):
        """The target function for the recording thread."""
        self.log.info("Recording thread started. Say something!")
        # The thread directly modifies the instance's temp_info attribute
        self.temp_info = self.manager.record_audio_to_temp(
            'test_button', 'interactive_test', event
        )

    def _handle_start(self):
        if self.recording_thread and self.recording_thread.is_alive():
            self.log.warning("A recording is already in progress.")
            return

        self.stop_event = threading.Event()
        self.recording_thread = threading.Thread(target=self._record_task, args=(self.stop_event,))
        self.recording_thread.start()

    def _handle_stop(self):
        if not (self.recording_thread and self.recording_thread.is_alive() and self.stop_event):
            self.log.warning("No recording is currently active.")
            return

        self.log.info("Signaling recording to stop...")
        self.stop_event.set()
        self.recording_thread.join()
        if self.temp_info:
            self.log.info(f"Recording stopped. Temporary file created at: {self.temp_info.get('temp_path')}")
        else:
            self.log.error("Recording thread finished, but no temporary file info was generated.")

    def _handle_cancel(self):
        if not (self.recording_thread and self.recording_thread.is_alive() and self.stop_event):
            self.log.warning("No recording is currently active.")
            return

        self.log.info("Canceling recording...")
        self.stop_event.set()
        self.recording_thread.join()
        self.log.info("Recording stopped and discarded.")
        self.temp_info = None

    def _handle_play(self):
        if not self.temp_info:
            self.log.warning("No temporary recording to play. Please 'start' and 'stop' first.")
            return

        path_to_play = self.temp_info.get('temp_path')
        if not path_to_play:
            self.log.error("Temporary recording info exists, but the path is missing.")
            return

        try:
            self.log.info("Attempting to play the last recording...")
            self.manager.play_audio(path_to_play)
        except NotImplementedError:
            self.log.error("Playback is not supported on your system's audio backend (e.g., Linux with ALSA).")

    def _handle_ok(self):
        if not self.temp_info:
            self.log.warning("No temporary recording to confirm. Please 'start' and 'stop' first.")
            return

        button_id = self.temp_info.get('button_id', 'N/A')
        self.log.info(f"Confirming recording for button '{button_id}'...")
        self.manager.finalize_recording(self.temp_info)
        self.log.info("Recording saved permanently.")
        self.temp_info = None

    def _handle_exit(self):
        if self.recording_thread and self.recording_thread.is_alive() and self.stop_event:
            self.log.info("Active recording detected. Stopping it before exiting...")
            self.stop_event.set()
            self.recording_thread.join()
        return True  # Signal to the main loop to break

    def run(self):
        self._print_instructions()
        try:
            while True:
                command_str = input("> ").strip().lower()
                handler = self.commands.get(command_str)

                if handler:
                    if handler():  # Exit command returns True
                        break
                else:
                    self.log.error(f"Unknown command: '{command_str}'")
        finally:
            self.log.info("Cleaning up temporary files...")
            self.manager.cleanup()
            print("Cleanup complete. Exiting.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    tester = InteractiveAudioTester()
    tester.run()