import unittest
import tempfile
import shutil
import os
from pathlib import Path
from datetime import datetime
from audio_file_manager import AudioFileManager

DUMMY_AUDIO = b'\x00\x01' * 8000


class TestAudioFileManagerMetadataOnly(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.meta_file = os.path.join(self.test_dir, 'meta.json')
        self.manager = AudioFileManager(storage_dir=self.test_dir, metadata_file=self.meta_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_assign_default_metadata_only(self):
        dummy = Path(self.test_dir) / "default.wav"
        dummy.write_bytes(DUMMY_AUDIO)
        self.manager.assign_default('btn10', dummy)
        meta = self.manager.metadata['btn10']
        self.assertTrue(meta['is_default'])
        self.assertTrue(meta['read_only'])
        self.assertIn('default', meta['message_type'])
        self.assertTrue(Path(meta['path']).exists())

    def test_restore_default_generates_new_file(self):
        dummy = Path(self.test_dir) / "default.wav"
        dummy.write_bytes(DUMMY_AUDIO)
        self.manager.assign_default('btn20', dummy)
        self.manager.restore_default('btn20')
        meta = self.manager.metadata['btn20']
        self.assertIn('restored', meta['name'])
        self.assertFalse(meta['read_only'])
        self.assertTrue(Path(meta['path']).exists())

    def test_set_read_only_flag(self):
        self.manager.metadata['btn30'] = {"read_only": False}
        self.manager.set_read_only('btn30', True)
        self.assertTrue(self.manager.metadata['btn30']['read_only'])

    def test_get_recording_info_returns_expected(self):
        self.manager.metadata['btn40'] = {"message_type": "test"}
        info = self.manager.get_recording_info('btn40')
        self.assertEqual(info['message_type'], "test")

    def test_discard_temp_files_does_not_remove_final(self):
        final = Path(self.test_dir) / "final.wav"
        final.write_bytes(DUMMY_AUDIO)
        self.manager.metadata['btn50'] = {
            "name": "final.wav",
            "path": str(final),
            "read_only": False,
            "message_type": "saved",
            "timestamp": datetime.utcnow().isoformat(),
            "duration": 1.0,
            "audio_format": "wav"
        }
        temp = self.manager.temp_dir / "btn50_test.wav"
        temp.write_bytes(b"temp")
        self.manager.discard_recording('btn50')
        self.assertTrue(final.exists())
        self.assertFalse(temp.exists())
