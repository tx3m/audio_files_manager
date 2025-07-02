import logging
import threading
from audio_file_manager import AudioFileManager


def main():
    """
    An interactive command-line script to test the AudioFileManager.
    """
    # --- Setup ---
    # Configure logging to see output from the manager and this script
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Instantiate the manager. It will use default paths in your home dir.
    manager = AudioFileManager()
    log = logging.getLogger("RecordExample")

    # --- State Variables ---
    recording_thread = None
    stop_event = None
    temp_info = None

    # --- Instructions ---
    print("\n--- Audio File Manager Interactive Test ---")
    print("Commands:")
    print("  start   - Begin recording audio for button 'test_button'.")
    print("  stop    - Stop the current recording and create a temporary file.")
    print("  ok      - Confirm the temporary recording and save it permanently.")
    print("  exit    - Quit the script and clean up temporary files.")
    print("-------------------------------------------")

    try:
        while True:
            command = input("> ").strip().lower()

            if command == "start":
                if recording_thread and recording_thread.is_alive():
                    log.warning("A recording is already in progress.")
                    continue

                # Use 'nonlocal' to allow the thread to update the temp_info variable
                def record_task():
                    nonlocal temp_info
                    log.info("Recording thread started. Say something!")
                    temp_info = manager.record_audio_to_temp(
                        'test_button', 'interactive_test', stop_event
                    )

                stop_event = threading.Event()
                recording_thread = threading.Thread(target=record_task)
                recording_thread.start()

            elif command == "stop":
                if not (recording_thread and recording_thread.is_alive()):
                    log.warning("No recording is currently active.")
                    continue

                log.info("Signaling recording to stop...")
                stop_event.set()
                recording_thread.join()  # Wait for the thread to finish writing the file
                log.info(f"Recording stopped. Temporary file created at: {temp_info.get('temp_path')}")

            elif command == "ok":
                if not temp_info:
                    log.warning("No temporary recording to confirm. Please 'start' and 'stop' first.")
                    continue

                log.info(f"Confirming recording for button '{temp_info['button_id']}'...")
                manager.finalize_recording(temp_info)
                log.info("Recording saved permanently.")
                temp_info = None  # Reset for the next recording

            elif command == "exit":
                if recording_thread and recording_thread.is_alive():
                    log.info("Active recording detected. Stopping it before exiting...")
                    stop_event.set()
                    recording_thread.join()
                break

            else:
                log.error(f"Unknown command: '{command}'")

    finally:
        # This ensures the temporary directory is always removed on exit
        log.info("Cleaning up temporary files...")
        manager.cleanup()
        print("Cleanup complete. Exiting.")


if __name__ == "__main__":
    main()