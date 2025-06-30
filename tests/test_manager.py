import unittest
import tempfile
import shutil
import os
from pathlib import Path
from datetime import datetime

DUMMY_AUDIO = b'\x00\x01' * 8000

try:
    from audio_file_manager import AudioFileManager
    ALSA_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    ALSA_AVAILABLE = False

@unittest.skipUnless(ALSA_AVAILABLE, "Skipping tests because alsaaudio is not available.")
class TestAudioFileManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.meta_file = os.path.join(self.test_dir, 'meta.json')
        self.manager = AudioFileManager(storage_dir=self.test_dir, metadata_file=self.meta_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_temp_record_and_finalize(self):
        info = self.manager.record_audio_to_temp('btn1', 0.01, 'note')
        self.assertTrue(Path(info['temp_path']).exists())
        self.manager.finalize_recording(info)
        meta = self.manager.metadata['btn1']
        self.assertIn('note', meta['message_type'])
        self.assertTrue(Path(meta['path']).exists())

    def test_discard_temp_keeps_confirmed(self):
        self.manager.metadata['btn2'] = {
            "name": "confirmed.wav",
            "path": str(Path(self.test_dir) / "confirmed.wav"),
            "read_only": False,
            "timestamp": datetime.utcnow().isoformat(),
            "message_type": "confirmed",
            "duration": 1.0,
            "audio_format": "wav"
        }
        Path(self.manager.metadata['btn2']['path']).write_bytes(DUMMY_AUDIO)
        temp = self.manager.temp_dir / "btn2_temp.wav"
        temp.write_bytes(b"temp")
        self.manager.discard_recording('btn2')
        self.assertTrue(Path(self.manager.metadata['btn2']['path']).exists())
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

    def test_set_read_only_toggle(self):
        self.manager.metadata['btn4'] = {"read_only": False}
        self.manager.set_read_only('btn4', True)
        self.assertTrue(self.manager.metadata['btn4']['read_only'])

    def test_get_info_and_listings(self):
        self.manager.metadata['btn5'] = {"message_type": "greeting"}
        info = self.manager.get_recording_info('btn5')
        self.assertEqual(info['message_type'], "greeting")
        self.assertIn('btn5', self.manager.list_all_recordings())
