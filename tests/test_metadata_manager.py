import unittest
import tempfile
import shutil
import json
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
import threading
import time

from audio_file_manager.metadata_manager import MetadataManager
from audio_file_manager import AudioFileManager

DUMMY_AUDIO = b'\x00\x01' * 8000

class TestMetadataManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.metadata_file = Path(self.test_dir) / "metadata.json"
        self.manager = MetadataManager(self.metadata_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_corrupted_json(self):
        """Test that loading a corrupted JSON file returns an empty dict and logs a warning."""
        with open(self.metadata_file, 'w') as f:
            f.write("{'invalid_json': ")  # Corrupted JSON

        with self.assertLogs('audio_file_manager.metadata_manager', level='WARNING') as cm:
            manager = MetadataManager(self.metadata_file)
            self.assertEqual(manager.metadata, {})
            self.assertIn(f"Could not decode JSON from {self.metadata_file}", cm.output[0])

    def test_get_occupied_sets(self):
        """Test getting occupied sets for legacy compatibility."""
        self.manager.metadata = {
            "1": {"message_type": "away_message"},
            "2": {"message_type": "custom_message"},
            "3": {"message_type": "away_message"},
            "4": {"message_type": "other_message"},
            "5": {} # no message_type
        }
        occupied_away, occupied_custom = self.manager.get_occupied_sets()
        self.assertEqual(occupied_away, {"1", "3"})
        self.assertEqual(occupied_custom, {"2"})

    def test_get_messages_by_type(self):
        """Test getting all messages of a specific type."""
        self.manager.metadata = {
            "1": {"message_type": "away_message", "data": "a"},
            "2": {"message_type": "custom_message", "data": "b"},
            "3": {"message_type": "away_message", "data": "c"},
        }
        away_messages = self.manager.get_messages_by_type("away_message")
        self.assertEqual(len(away_messages), 2)
        self.assertIn("1", away_messages)
        self.assertIn("3", away_messages)
        self.assertEqual(away_messages["1"]["data"], "a")

        custom_messages = self.manager.get_messages_by_type("custom_message")
        self.assertEqual(len(custom_messages), 1)
        self.assertIn("2", custom_messages)

        other_messages = self.manager.get_messages_by_type("other_message")
        self.assertEqual(len(other_messages), 0)

    def test_get_newest_message_of_type_success(self):
        """Test finding the newest message of a given type."""
        now = datetime.now()
        self.manager.metadata = {
            "1": {"message_type": "test", "timestamp": (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")},
            "2": {"message_type": "test", "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")}, # newest
            "3": {"message_type": "other", "timestamp": (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")},
            "4": {"message_type": "test", "timestamp": (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")},
        }
        newest = self.manager.get_newest_message_of_type("test")
        self.assertIsNotNone(newest)
        self.assertEqual(newest["timestamp"], now.strftime("%Y-%m-%d %H:%M:%S"))

    def test_get_newest_message_of_type_no_match(self):
        """Test finding the newest message when none of the type exist."""
        self.manager.metadata = {
            "1": {"message_type": "other", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        }
        newest = self.manager.get_newest_message_of_type("test")
        self.assertIsNone(newest)

    def test_get_newest_message_of_type_invalid_timestamp(self):
        """Test that messages with invalid timestamps are skipped."""
        now = datetime.now()
        self.manager.metadata = {
            "1": {"message_type": "test", "timestamp": "invalid-date"},
            "2": {"message_type": "test", "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")}, # newest valid
        }
        with self.assertLogs('audio_file_manager.metadata_manager', level='WARNING') as cm:
            newest = self.manager.get_newest_message_of_type("test")
            self.assertIn("Error processing timestamp for button 1", cm.output[0])
        
        self.assertIsNotNone(newest)
        self.assertEqual(newest["timestamp"], now.strftime("%Y-%m-%d %H:%M:%S"))

    def test_get_message_path_success(self):
        """Test getting a message path successfully."""
        self.manager.metadata["1"] = {"message_type": "test", "path": "/path/to/file"}
        path = self.manager.get_message_path("1", "test")
        self.assertEqual(path, "/path/to/file")

    def test_get_message_path_not_found(self):
        """Test getting a message path for a non-existent ID."""
        path = self.manager.get_message_path("nonexistent", "test")
        self.assertIsNone(path)

    def test_get_message_path_wrong_type(self):
        """Test getting a message path when the message type does not match."""
        self.manager.metadata["1"] = {"message_type": "other", "path": "/path/to/file"}
        path = self.manager.get_message_path("1", "test")
        self.assertIsNone(path)

    def test_get_message_path_empty_id(self):
        """Test getting a message path with empty ID."""
        path = self.manager.get_message_path("", "test")
        self.assertIsNone(path)
        
        path = self.manager.get_message_path(None, "test")
        self.assertIsNone(path)

    def test_load_nonexistent_file(self):
        """Test loading metadata from a non-existent file."""
        nonexistent_file = Path(self.test_dir) / "nonexistent.json"
        manager = MetadataManager(nonexistent_file)
        self.assertEqual(manager.metadata, {})

    def test_load_existing_valid_file(self):
        """Test loading metadata from an existing valid JSON file."""
        test_data = {"button1": {"message_type": "test", "path": "/test/path"}}
        with open(self.metadata_file, 'w') as f:
            json.dump(test_data, f)
        
        with self.assertLogs('audio_file_manager.metadata_manager', level='DEBUG') as cm:
            manager = MetadataManager(self.metadata_file)
            self.assertEqual(manager.metadata, test_data)
            self.assertIn(f"Loading metadata from {self.metadata_file}", cm.output[0])

    def test_save_creates_directory(self):
        """Test that save creates parent directories if they don't exist."""
        nested_dir = Path(self.test_dir) / "nested" / "deep"
        nested_file = nested_dir / "metadata.json"
        manager = MetadataManager(nested_file)
        
        manager.metadata["test"] = {"data": "value"}
        
        with self.assertLogs('audio_file_manager.metadata_manager', level='DEBUG') as cm:
            manager.save()
            self.assertTrue(nested_file.exists())
            self.assertIn(f"Saving metadata to {nested_file}", cm.output[0])

    def test_save_with_data(self):
        """Test saving metadata to file."""
        test_data = {"button1": {"message_type": "test", "path": "/test/path"}}
        self.manager.metadata = test_data
        self.manager.save()
        
        # Verify file was created and contains correct data
        self.assertTrue(self.metadata_file.exists())
        with open(self.metadata_file, 'r') as f:
            saved_data = json.load(f)
        self.assertEqual(saved_data, test_data)

    def test_get_existing_button(self):
        """Test getting metadata for an existing button."""
        test_data = {"message_type": "test", "path": "/test/path"}
        self.manager.metadata["button1"] = test_data
        result = self.manager.get("button1")
        self.assertEqual(result, test_data)

    def test_get_nonexistent_button(self):
        """Test getting metadata for a non-existent button."""
        result = self.manager.get("nonexistent")
        self.assertIsNone(result)

    def test_get_all_empty(self):
        """Test getting all metadata when empty."""
        result = self.manager.get_all()
        self.assertEqual(result, {})

    def test_get_all_with_data(self):
        """Test getting all metadata with data."""
        test_data = {
            "button1": {"message_type": "test1", "path": "/path1"},
            "button2": {"message_type": "test2", "path": "/path2"}
        }
        self.manager.metadata = test_data
        result = self.manager.get_all()
        self.assertEqual(result, test_data)
        # Ensure it returns a copy, not the original
        self.assertIsNot(result, self.manager.metadata)

    def test_update_recording_new(self):
        """Test updating metadata for a new recording."""
        test_data = {"message_type": "test", "path": "/test/path"}
        self.manager.update_recording("button1", test_data)
        
        self.assertEqual(self.manager.metadata["button1"], test_data)
        # Verify it was saved to file
        self.assertTrue(self.metadata_file.exists())

    def test_update_recording_existing(self):
        """Test updating metadata for an existing recording."""
        original_data = {"message_type": "old", "path": "/old/path"}
        self.manager.metadata["button1"] = original_data
        
        new_data = {"message_type": "new", "path": "/new/path"}
        self.manager.update_recording("button1", new_data)
        
        self.assertEqual(self.manager.metadata["button1"], new_data)

    def test_set_read_only_existing_button(self):
        """Test setting read-only status for an existing button."""
        self.manager.metadata["button1"] = {"read_only": False}
        self.manager.set_read_only("button1", True)
        
        self.assertTrue(self.manager.metadata["button1"]["read_only"])
        # Verify it was saved to file
        self.assertTrue(self.metadata_file.exists())

    def test_set_read_only_nonexistent_button(self):
        """Test setting read-only status for a non-existent button."""
        self.manager.set_read_only("nonexistent", True)
        # Should not create the button or crash
        self.assertNotIn("nonexistent", self.manager.metadata)

    def test_threading_safety(self):
        """Test that metadata operations are thread-safe."""
        results = []
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(10):
                    button_id = f"thread_{thread_id}_button_{i}"
                    data = {"thread": thread_id, "iteration": i}
                    self.manager.update_recording(button_id, data)
                    
                    # Read back the data
                    result = self.manager.get(button_id)
                    if result != data:
                        errors.append(f"Thread {thread_id}: Data mismatch")
                    
                    results.append((thread_id, i))
                    time.sleep(0.001)  # Small delay to increase chance of race conditions
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        self.assertEqual(len(errors), 0, f"Threading errors: {errors}")
        self.assertEqual(len(results), 50)  # 5 threads * 10 iterations each
        
        # Verify all data was saved correctly
        all_metadata = self.manager.get_all()
        self.assertEqual(len(all_metadata), 50)

    def test_get_newest_message_no_timestamp(self):
        """Test getting newest message when some entries have no timestamp."""
        now = datetime.now()
        self.manager.metadata = {
            "1": {"message_type": "test"},  # No timestamp
            "2": {"message_type": "test", "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")},
            "3": {"message_type": "test", "timestamp": ""},  # Empty timestamp
        }
        newest = self.manager.get_newest_message_of_type("test")
        self.assertIsNotNone(newest)
        self.assertEqual(newest["timestamp"], now.strftime("%Y-%m-%d %H:%M:%S"))

    def test_get_newest_message_all_invalid_timestamps(self):
        """Test getting newest message when all timestamps are invalid."""
        self.manager.metadata = {
            "1": {"message_type": "test", "timestamp": "invalid"},
            "2": {"message_type": "test"},  # No timestamp
            "3": {"message_type": "test", "timestamp": "also-invalid"},
        }
        
        with self.assertLogs('audio_file_manager.metadata_manager', level='WARNING'):
            newest = self.manager.get_newest_message_of_type("test")
            self.assertIsNone(newest)


class TestMetadataManagerIntegration(unittest.TestCase):
    """Integration tests with AudioFileManager to ensure metadata operations work correctly."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.meta_file = os.path.join(self.test_dir, 'meta.json')
        self.manager = AudioFileManager(storage_dir=self.test_dir, metadata_file=self.meta_file)

    def tearDown(self):
        self.manager.cleanup()
        shutil.rmtree(self.test_dir)

    def test_assign_default_updates_metadata(self):
        """Test that assign_default properly updates metadata."""
        source_path = Path(self.test_dir) / "default.wav"
        source_path.write_bytes(DUMMY_AUDIO)
        button_id = 'btn10'
        self.manager.assign_default(button_id, source_path)
        meta = self.manager.metadata_manager.metadata[button_id]
        expected_path = self.manager.fs_manager.storage_dir / f"default_{button_id}.wav"

        self.assertTrue(meta['is_default'])
        self.assertTrue(meta['read_only'])
        self.assertEqual(meta['message_type'], 'default')
        self.assertEqual(Path(meta['path']), expected_path)
        self.assertTrue(expected_path.exists())

    def test_restore_default_creates_new_file(self):
        """Test that restore_default creates a new file with correct metadata."""
        default_path = Path(self.test_dir) / "default.wav"
        default_path.write_bytes(DUMMY_AUDIO)
        self.manager.assign_default('btn20', default_path)
        original_path = Path(self.manager.get_recording_info('btn20')['path'])

        self.manager.restore_default('btn20')
        restored_meta = self.manager.metadata_manager.metadata['btn20']
        restored_path = Path(restored_meta['path'])

        self.assertNotEqual(original_path, restored_path, "Restoring should create a new file with a new path.")
        self.assertIn('restored', restored_meta['name'])
        self.assertFalse(restored_meta['read_only'])
        # Duration should be copied from the original default file (0.0 for dummy audio)
        self.assertEqual(restored_meta['duration'], 0.0, "Duration should be copied from the original default file.")
        self.assertTrue(restored_path.exists())

    def test_set_read_only_flag(self):
        """Test setting read-only flag through AudioFileManager."""
        button_id = 'btn30'
        self.manager.metadata_manager.metadata[button_id] = {"read_only": False}
        self.manager.set_read_only(button_id, True)
        self.assertTrue(self.manager.metadata_manager.metadata[button_id]['read_only'])
        self.manager.set_read_only(button_id, False)
        self.assertFalse(self.manager.metadata_manager.metadata[button_id]['read_only'])

    def test_get_recording_info(self):
        """Test getting recording info through AudioFileManager."""
        self.manager.metadata_manager.metadata['btn40'] = {"message_type": "test"}
        info = self.manager.get_recording_info('btn40')
        self.assertEqual(info['message_type'], "test")
        self.assertIsNone(self.manager.get_recording_info('non_existent_btn'))

    def test_discard_recording_removes_temp_file_only(self):
        """Test that discard_recording only removes temp files."""
        button_id = 'btn50'
        final_path = Path(self.test_dir) / "final.wav"
        final_path.write_bytes(DUMMY_AUDIO)
        self.manager.metadata_manager.metadata[button_id] = {
            "name": "final.wav",
            "path": str(final_path),
            "read_only": False,
            "message_type": "saved",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": 1.0,
            "audio_format": "wav"
        }
        temp = self.manager.fs_manager.temp_dir / f"{button_id}_test.wav"
        temp.write_bytes(b"temp")
        self.manager.discard_recording(button_id)
        self.assertTrue(final_path.exists())
        self.assertFalse(temp.exists())

    def test_assign_default_with_missing_source_logs_error(self):
        """Test that assign_default logs error for missing source file."""
        button_id = 'btn60'
        missing_path = Path(self.test_dir) / "non_existent.wav"

        with self.assertLogs('audio_file_manager.manager', level='ERROR') as cm:
            self.manager.assign_default(button_id, missing_path)
            self.assertIn(f"Cannot assign default: source file not found at {missing_path}", cm.output[0])

        self.assertNotIn(button_id, self.manager.metadata_manager.metadata)

    def test_restore_default_with_no_default_logs_warning(self):
        """Test that restore_default logs warning when no default exists."""
        button_id = 'btn70'
        # Ensure no default exists for this button
        self.assertNotIn(button_id, self.manager.metadata_manager.metadata)

        with self.assertLogs('audio_file_manager.manager', level='WARNING') as cm:
            self.manager.restore_default(button_id)
            self.assertIn(f"Cannot restore default for '{button_id}': default file not found or not marked as default.", cm.output[0])

    def test_set_read_only_on_nonexistent_button(self):
        """Test setting read-only on non-existent button."""
        button_id = 'btn80'
        self.assertNotIn(button_id, self.manager.metadata_manager.metadata)
        # This should execute without error and without changing metadata
        self.manager.set_read_only(button_id, True)
        self.assertNotIn(button_id, self.manager.metadata_manager.metadata)

    def test_metadata_persistence_across_instances(self):
        """Test that metadata persists across AudioFileManager instances."""
        button_id = 'persistence_test'
        test_data = {
            "message_type": "test",
            "path": "/test/path",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Save data with first instance
        self.manager.metadata_manager.update_recording(button_id, test_data)
        self.manager.cleanup()
        
        # Create new instance and verify data persists
        new_manager = AudioFileManager(storage_dir=self.test_dir, metadata_file=self.meta_file)
        try:
            retrieved_data = new_manager.get_recording_info(button_id)
            self.assertEqual(retrieved_data, test_data)
        finally:
            new_manager.cleanup()


if __name__ == '__main__':
    unittest.main()