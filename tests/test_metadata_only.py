import unittest
import tempfile
import shutil
import os
from pathlib import Path
import logging
from datetime import datetime
from audio_file_manager import AudioFileManager

DUMMY_AUDIO = b'\x00\x01' * 8000


class TestAudioFileManagerMetadataOnly(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.meta_file = os.path.join(self.test_dir, 'meta.json')
        self.manager = AudioFileManager(storage_dir=self.test_dir, metadata_file=self.meta_file)

    def tearDown(self):
        self.manager.cleanup()
        shutil.rmtree(self.test_dir)

    def test_assign_default_updates_metadata(self):
        source_path = Path(self.test_dir) / "default.wav"
        source_path.write_bytes(DUMMY_AUDIO)
        button_id = 'btn10'
        self.manager.assign_default(button_id, source_path)
        meta = self.manager.metadata[button_id]
        expected_path = self.manager.storage_dir / f"default_{button_id}.wav"

        self.assertTrue(meta['is_default'])
        self.assertTrue(meta['read_only'])
        self.assertEqual(meta['message_type'], 'default')
        self.assertEqual(Path(meta['path']), expected_path)
        self.assertTrue(expected_path.exists())

    def test_restore_default_creates_new_file(self):
        default_path = Path(self.test_dir) / "default.wav"
        default_path.write_bytes(DUMMY_AUDIO)
        self.manager.assign_default('btn20', default_path)
        original_path = Path(self.manager.get_recording_info('btn20')['path'])

        self.manager.restore_default('btn20')
        restored_meta = self.manager.metadata['btn20']
        restored_path = Path(restored_meta['path'])

        self.assertNotEqual(original_path, restored_path, "Restoring should create a new file with a new path.")
        self.assertIn('restored', restored_meta['name'])
        self.assertFalse(restored_meta['read_only'])
        self.assertIsNone(restored_meta['duration'], "Duration should be None for restored files by default.")
        self.assertTrue(restored_path.exists())

    def test_set_read_only_flag(self):
        button_id = 'btn30'
        self.manager.metadata[button_id] = {"read_only": False}
        self.manager.set_read_only(button_id, True)
        self.assertTrue(self.manager.metadata[button_id]['read_only'])
        self.manager.set_read_only(button_id, False)
        self.assertFalse(self.manager.metadata[button_id]['read_only'])

    def test_get_recording_info(self):
        self.manager.metadata['btn40'] = {"message_type": "test"}
        info = self.manager.get_recording_info('btn40')
        self.assertEqual(info['message_type'], "test")
        self.assertIsNone(self.manager.get_recording_info('non_existent_btn'))

    def test_discard_recording_removes_temp_file_only(self):
        button_id = 'btn50'
        final_path = Path(self.test_dir) / "final.wav"
        final_path.write_bytes(DUMMY_AUDIO)
        self.manager.metadata[button_id] = {
            "name": "final.wav",
            "path": str(final_path),
            "read_only": False,
            "message_type": "saved",
            "timestamp": datetime.utcnow().isoformat(),
            "duration": 1.0,
            "audio_format": "wav"
        }
        temp = self.manager.temp_dir / f"{button_id}_test.wav"
        temp.write_bytes(b"temp")
        self.manager.discard_recording(button_id)
        self.assertTrue(final_path.exists())
        self.assertFalse(temp.exists())

    def test_assign_default_with_missing_source_logs_error(self):
        button_id = 'btn60'
        missing_path = Path(self.test_dir) / "non_existent.wav"

        with self.assertLogs('audio_file_manager.manager', level='ERROR') as cm:
            self.manager.assign_default(button_id, missing_path)
            self.assertIn(f"Cannot assign default: source file not found at {missing_path}", cm.output[0])

        self.assertNotIn(button_id, self.manager.metadata)

    def test_restore_default_with_no_default_logs_warning(self):
        button_id = 'btn70'
        # Ensure no default exists for this button
        self.assertNotIn(button_id, self.manager.metadata)

        with self.assertLogs('audio_file_manager.manager', level='WARNING') as cm:
            self.manager.restore_default(button_id)
            self.assertIn(f"Cannot restore default for '{button_id}': default file not found.", cm.output[0])

    def test_set_read_only_on_nonexistent_button(self):
        button_id = 'btn80'
        self.assertNotIn(button_id, self.manager.metadata)
        # This should execute without error and without changing metadata
        self.manager.set_read_only(button_id, True)
        self.assertNotIn(button_id, self.manager.metadata)
