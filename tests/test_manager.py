import unittest
import tempfile
import shutil
import os
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
import platform

try:
    from audio_file_manager import AudioFileManager
    if platform.system() == "Linux":
        import alsaaudio
        AUDIO_AVAILABLE = True
    else:
        import sounddevice as sd
        AUDIO_AVAILABLE = True
except (ImportError, OSError):
    AUDIO_AVAILABLE = False


DUMMY_AUDIO = b'\x00\x01' * 8000


@unittest.skipUnless(AUDIO_AVAILABLE, "Audio backend not available for recording tests.")
class TestAudioFileManager(unittest.TestCase):
    def setUp(self):
        self.info = {}
        self.test_dir = tempfile.mkdtemp()
        self.meta_file = os.path.join(self.test_dir, 'meta.json')
        self.manager = AudioFileManager(storage_dir=self.test_dir, metadata_file=self.meta_file)

    def tearDown(self):
        self.manager.cleanup()
        shutil.rmtree(self.test_dir)

    def test_temp_record_and_finalize(self):
        stop_event = threading.Event()

        def record():
            self.info = self.manager.record_audio_to_temp('btn1', 'note', stop_event)

        thread = threading.Thread(target=record)
        thread.start()
        time.sleep(0.1)
        stop_event.set()
        thread.join()

        self.assertTrue(Path(self.info['temp_path']).exists())
        self.assertGreaterEqual(self.info['duration'], 0.0)
        self.manager.finalize_recording(self.info)
        meta = self.manager.metadata['btn1']
        self.assertEqual(meta['message_type'], 'note')
        self.assertTrue(Path(meta['path']).exists())

    def test_discard_temp_keeps_confirmed(self):
        confirmed_path = Path(self.test_dir) / "confirmed.wav"
        confirmed_path.write_bytes(DUMMY_AUDIO)
        self.manager.metadata['btn2'] = {
            "name": "confirmed.wav",
            "path": str(confirmed_path),
            "read_only": False,
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": "confirmed",
            "duration": 1.0,
            "audio_format": "wav"
        }
        self.manager._save_metadata()
        # Create a temp file that follows the manager's naming convention
        temp = self.manager.temp_dir / f"btn2_test_{int(time.time())}.wav"
        temp.write_bytes(b"temp")
        self.manager.discard_recording('btn2')
        self.assertTrue(confirmed_path.exists())
        self.assertFalse(temp.exists())

    def test_assign_and_restore_default(self):
        dummy = Path(self.test_dir) / "default.wav"
        dummy.write_bytes(DUMMY_AUDIO)
        self.manager.assign_default('btn3', dummy)
        self.assertTrue(self.manager.metadata['btn3']['read_only'])

        self.manager.restore_default('btn3')
        restored = self.manager.metadata['btn3']
        self.assertIn('restored', restored['name'])
        self.assertFalse(restored['read_only'])
        self.assertTrue(Path(restored['path']).exists())

    def test_set_read_only_toggle(self):
        self.manager.metadata['btn4'] = {"read_only": False}
        self.manager.set_read_only('btn4', True)
        self.assertTrue(self.manager.metadata['btn4']['read_only'])

    def test_get_info_and_listings(self):
        self.manager.metadata['btn5'] = {"message_type": "greeting"}
        info = self.manager.get_recording_info('btn5')
        self.assertEqual(info['message_type'], "greeting")
        self.assertIn('btn5', self.manager.list_all_recordings())

    def test_finalize_blocked_for_readonly_logs_warning(self):
        button_id = 'btn6'
        self.manager.metadata[button_id] = {"read_only": True}
        self.manager._save_metadata()

        dummy_info = {
            "button_id": button_id,
            "temp_path": str(self.manager.temp_dir / "dummy.wav")
        }
        Path(dummy_info["temp_path"]).touch()

        with self.assertLogs('audio_file_manager.manager', level='WARNING') as cm:
            self.manager.finalize_recording(dummy_info)
            self.assertIn(f"Finalizing recording blocked: Button {button_id} is read-only.", cm.output[0])

        # Ensure the temp file was not moved and metadata was not updated
        self.assertTrue(Path(dummy_info["temp_path"]).exists())
        self.assertTrue(self.manager.metadata[button_id]['read_only']) # check it wasn't overwritten

    def test_cleanup_removes_temp_dir(self):
        temp_dir_path = self.manager.temp_dir
        self.assertTrue(temp_dir_path.exists())
        self.manager.cleanup()
        self.assertFalse(temp_dir_path.exists())
