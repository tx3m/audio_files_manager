import unittest
import tempfile
import shutil
import io
import sys
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from enhanced_record_example import EnhancedInteractiveAudioTester


class TestEnhancedInteractiveAudioTester(unittest.TestCase):
    """Test the EnhancedInteractiveAudioTester functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        
        # Patch the AudioFileManager to use our test directory
        with patch('enhanced_record_example.AudioFileManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager.storage_dir = Path(self.test_dir)
            mock_manager.audio_backend.__class__.__name__ = "MockAudioBackend"
            mock_manager.get_audio_device_info.return_value = {"device": "test", "backend": "Mock"}
            mock_manager.audio_format = "pcm"
            mock_manager.sample_rate = 44100
            mock_manager.channels = 1
            mock_manager_class.return_value = mock_manager
            
            self.tester = EnhancedInteractiveAudioTester()
            self.mock_manager = mock_manager
    
    def tearDown(self):
        """Clean up test environment."""
        if hasattr(self.tester, 'manager'):
            self.tester.manager.cleanup()
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_initialization(self):
        """Test tester initialization."""
        self.assertIsNotNone(self.tester.manager)
        self.assertIsNotNone(self.tester.legacy_adapter)
        self.assertEqual(self.tester.current_button, "test_button")
        self.assertEqual(self.tester.current_message_type, "interactive_test")
        self.assertIsInstance(self.tester.sound_levels, list)
        self.assertIsInstance(self.tester.commands, dict)
    
    def test_sound_level_callback(self):
        """Test sound level callback functionality."""
        # Clear any existing sound levels
        self.tester.sound_levels.clear()
        
        # Simulate sound level callback
        self.tester._sound_level_callback(1500)
        
        # Verify sound level was recorded
        self.assertIn(1500, self.tester.sound_levels)
    
    def test_show_current_config(self):
        """Test configuration display."""
        # Capture stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._show_current_config()
            output = captured_output.getvalue()
            
            # Verify configuration elements are displayed
            self.assertIn("Current Configuration:", output)
            self.assertIn("Button ID:", output)
            self.assertIn("Message Type:", output)
            self.assertIn("Audio Format:", output)
            self.assertIn("Sample Rate:", output)
            self.assertIn("Audio Backend:", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_print_instructions(self):
        """Test instructions printing."""
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._print_instructions()
            output = captured_output.getvalue()
            
            # Verify all command categories are shown
            self.assertIn("BASIC RECORDING:", output)
            self.assertIn("FILE MANAGEMENT:", output)
            self.assertIn("CONFIGURATION:", output)
            self.assertIn("LEGACY COMPATIBILITY:", output)
            self.assertIn("UTILITY:", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_button_command(self):
        """Test button ID setting command."""
        with patch('builtins.input', return_value='new_button_id'):
            self.tester._handle_button()
            
            self.assertEqual(self.tester.current_button, 'new_button_id')
    
    def test_handle_type_command(self):
        """Test message type setting command."""
        with patch('builtins.input', return_value='new_message_type'):
            self.tester._handle_type()
            
            self.assertEqual(self.tester.current_message_type, 'new_message_type')
    
    def test_handle_format_command(self):
        """Test audio format setting command."""
        # Test valid format
        with patch('builtins.input', return_value='alaw'):
            self.tester._handle_format()
            
            self.assertEqual(self.tester.manager.audio_format, 'alaw')
        
        # Test invalid format
        with patch('builtins.input', return_value='invalid_format'):
            captured_output = io.StringIO()
            sys.stdout = captured_output
            
            try:
                self.tester._handle_format()
                output = captured_output.getvalue()
                self.assertIn("Invalid format", output)
            finally:
                sys.stdout = sys.__stdout__
    
    def test_handle_rate_command(self):
        """Test sample rate setting command."""
        # Test valid rate
        with patch('builtins.input', return_value='8000'):
            self.tester._handle_rate()
            
            self.assertEqual(self.tester.manager.sample_rate, 8000)
        
        # Test invalid rate
        with patch('builtins.input', return_value='invalid_rate'):
            captured_output = io.StringIO()
            sys.stdout = captured_output
            
            try:
                self.tester._handle_rate()
                output = captured_output.getvalue()
                self.assertIn("Invalid sample rate", output)
            finally:
                sys.stdout = sys.__stdout__
    
    def test_handle_status_command(self):
        """Test status display command."""
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_status()
            output = captured_output.getvalue()
            
            # Verify status information is displayed
            self.assertIn("Current Configuration:", output)
            self.assertIn("Backend Details:", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_list_command_empty(self):
        """Test list command with no recordings."""
        self.mock_manager.list_all_recordings.return_value = {}
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_list()
            output = captured_output.getvalue()
            
            self.assertIn("No recordings found", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_list_command_with_recordings(self):
        """Test list command with recordings."""
        mock_recordings = {
            "btn1": {
                "message_type": "test",
                "duration": 2.5,
                "read_only": False,
                "audio_format": "pcm",
                "path": "/test/path/file.wav"
            },
            "btn2": {
                "message_type": "greeting",
                "duration": 1.0,
                "read_only": True,
                "audio_format": "alaw",
                "path": "/test/path/file2.wav"
            }
        }
        self.mock_manager.list_all_recordings.return_value = mock_recordings
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_list()
            output = captured_output.getvalue()
            
            # Verify recordings are displayed
            self.assertIn("btn1", output)
            self.assertIn("btn2", output)
            self.assertIn("test", output)
            self.assertIn("greeting", output)
            self.assertIn("2.50s", output)
            self.assertIn("1.00s", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_info_command_no_recording(self):
        """Test info command with no recording."""
        self.mock_manager.get_recording_info.return_value = None
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_info()
            output = captured_output.getvalue()
            
            self.assertIn("No recording found", output)
            self.assertIn(self.tester.current_button, output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_info_command_with_recording(self):
        """Test info command with recording."""
        mock_info = {
            "message_type": "test",
            "duration": 2.5,
            "path": "/test/path",
            "timestamp": "2023-01-01T12:00:00"
        }
        self.mock_manager.get_recording_info.return_value = mock_info
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_info()
            output = captured_output.getvalue()
            
            # Verify info is displayed
            self.assertIn("Recording info", output)
            self.assertIn("message_type: test", output)
            self.assertIn("duration: 2.5", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_readonly_command(self):
        """Test read-only toggle command."""
        # Test with existing recording
        mock_info = {"read_only": False}
        self.mock_manager.get_recording_info.return_value = mock_info
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_readonly()
            output = captured_output.getvalue()
            
            # Verify read-only was toggled
            self.mock_manager.set_read_only.assert_called_once_with(
                self.tester.current_button, True
            )
            self.assertIn("read-only: True", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_readonly_command_no_recording(self):
        """Test read-only command with no recording."""
        self.mock_manager.get_recording_info.return_value = None
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_readonly()
            output = captured_output.getvalue()
            
            self.assertIn("No recording found", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_default_command(self):
        """Test default file assignment command."""
        test_file_path = "/test/default.wav"
        
        with patch('builtins.input', return_value=test_file_path):
            captured_output = io.StringIO()
            sys.stdout = captured_output
            
            try:
                self.tester._handle_default()
                output = captured_output.getvalue()
                
                # Verify default assignment was attempted
                self.mock_manager.assign_default.assert_called_once_with(
                    self.tester.current_button, test_file_path
                )
                self.assertIn("Default recording set", output)
                
            finally:
                sys.stdout = sys.__stdout__
    
    def test_handle_default_command_empty_input(self):
        """Test default command with empty input."""
        with patch('builtins.input', return_value=''):
            self.tester._handle_default()
            
            # Should not call assign_default with empty input
            self.mock_manager.assign_default.assert_not_called()
    
    def test_handle_restore_command(self):
        """Test default restoration command."""
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_restore()
            output = captured_output.getvalue()
            
            # Verify restore was attempted
            self.mock_manager.restore_default.assert_called_once_with(
                self.tester.current_button
            )
            self.assertIn("Default recording restored", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_delete_command_no_recording(self):
        """Test delete command with no recording."""
        self.mock_manager.get_recording_info.return_value = None
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_delete()
            output = captured_output.getvalue()
            
            self.assertIn("No recording found", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_delete_command_readonly(self):
        """Test delete command with read-only recording."""
        mock_info = {"read_only": True}
        self.mock_manager.get_recording_info.return_value = mock_info
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_delete()
            output = captured_output.getvalue()
            
            self.assertIn("Cannot delete", output)
            self.assertIn("read-only", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_delete_command_confirmed(self):
        """Test delete command with confirmation."""
        mock_info = {"read_only": False, "path": "/test/file.wav"}
        self.mock_manager.get_recording_info.return_value = mock_info
        
        with patch('builtins.input', return_value='y'):
            with patch('pathlib.Path.unlink') as mock_unlink:
                captured_output = io.StringIO()
                sys.stdout = captured_output
                
                try:
                    self.tester._handle_delete()
                    output = captured_output.getvalue()
                    
                    # Verify deletion was attempted
                    mock_unlink.assert_called_once()
                    self.assertIn("deleted", output)
                    
                finally:
                    sys.stdout = sys.__stdout__
    
    def test_handle_delete_command_cancelled(self):
        """Test delete command cancelled."""
        mock_info = {"read_only": False, "path": "/test/file.wav"}
        self.mock_manager.get_recording_info.return_value = mock_info
        
        with patch('builtins.input', return_value='n'):
            with patch('pathlib.Path.unlink') as mock_unlink:
                self.tester._handle_delete()
                
                # Should not delete when cancelled
                mock_unlink.assert_not_called()
    
    def test_handle_help_command(self):
        """Test help command."""
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_help()
            output = captured_output.getvalue()
            
            # Verify help is displayed (same as instructions)
            self.assertIn("Enhanced Audio File Manager", output)
            self.assertIn("BASIC RECORDING:", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_legacy_command(self):
        """Test legacy recording command."""
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            with patch('time.sleep'):  # Speed up the test
                self.tester._handle_legacy()
                output = captured_output.getvalue()
                
                # Verify legacy recording was attempted
                self.assertIn("Starting legacy recording", output)
                
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_legacy_play_command(self):
        """Test legacy playback command."""
        # Mock successful file retrieval
        mock_file_path = "/test/legacy_file.wav"
        self.tester.legacy_adapter.get_message.return_value = mock_file_path
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_legacy_play()
            output = captured_output.getvalue()
            
            # Verify legacy playback was attempted
            self.assertIn("Playing legacy recording", output)
            self.tester.legacy_adapter.play_locally.assert_called_once()
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_legacy_play_command_no_file(self):
        """Test legacy playback command with no file."""
        self.tester.legacy_adapter.get_message.return_value = "No file found"
        
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        try:
            self.tester._handle_legacy_play()
            output = captured_output.getvalue()
            
            self.assertIn("No legacy recording found", output)
            
        finally:
            sys.stdout = sys.__stdout__
    
    def test_handle_exit_command(self):
        """Test exit command."""
        result = self.tester._handle_exit()
        
        # Exit command should return True to signal exit
        self.assertTrue(result)
    
    def test_handle_exit_with_active_recording(self):
        """Test exit command with active recording."""
        # Mock active recording
        self.tester.recording_thread = Mock()
        self.tester.recording_thread.is_alive.return_value = True
        self.tester.stop_event = Mock()
        
        result = self.tester._handle_exit()
        
        # Should stop recording and return True
        self.tester.stop_event.set.assert_called_once()
        self.tester.recording_thread.join.assert_called_once()
        self.assertTrue(result)
    
    def test_command_mapping(self):
        """Test that all expected commands are mapped."""
        expected_commands = [
            'start', 'stop', 'cancel', 'play', 'ok',
            'list', 'info', 'delete', 'readonly', 'default', 'restore',
            'button', 'type', 'format', 'rate', 'status',
            'legacy', 'legacy-play',
            'help', 'exit'
        ]
        
        for command in expected_commands:
            self.assertIn(command, self.tester.commands)
            self.assertTrue(callable(self.tester.commands[command]))


class TestEnhancedExampleIntegration(unittest.TestCase):
    """Integration tests for the enhanced example."""
    
    def test_example_import(self):
        """Test that the enhanced example can be imported."""
        # This test verifies that all imports work correctly
        from enhanced_record_example import EnhancedInteractiveAudioTester
        
        # Should be able to create an instance
        tester = EnhancedInteractiveAudioTester()
        self.assertIsNotNone(tester)
        
        # Clean up
        tester.manager.cleanup()
    
    def test_example_initialization_with_real_manager(self):
        """Test example initialization with real AudioFileManager."""
        from enhanced_record_example import EnhancedInteractiveAudioTester
        
        tester = EnhancedInteractiveAudioTester()
        
        # Verify real components are initialized
        self.assertIsNotNone(tester.manager)
        self.assertIsNotNone(tester.legacy_adapter)
        self.assertIsInstance(tester.sound_levels, list)
        
        # Verify configuration
        self.assertEqual(tester.current_button, "test_button")
        self.assertEqual(tester.current_message_type, "interactive_test")
        
        # Clean up
        tester.manager.cleanup()


if __name__ == '__main__':
    unittest.main()