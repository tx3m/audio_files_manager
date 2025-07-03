#!/usr/bin/env python3
"""
Test script to identify failures in the tests.
"""

import unittest
import tempfile
import shutil
import os
import sys
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from audio_file_manager import AudioFileManager
from audio_file_manager.legacy_compatibility_simple import add_legacy_compatibility

def run_basic_test():
    """Run a basic test to check if the manager works correctly."""
    print("Running basic test...")
    
    # Create temporary directory for testing
    test_dir = tempfile.mkdtemp()
    
    try:
        # Test 1: Create manager with custom_message type
        print("Test 1: Creating AudioFileManager with message_type='custom_message'")
        manager = AudioFileManager(
            storage_dir=test_dir, 
            message_type="custom_message"
        )
        
        print(f"Manager message_type: {manager.message_type}")
        
        # Test 2: Test record_audio_to_temp
        print("\nTest 2: Testing record_audio_to_temp")
        import threading
        stop_event = threading.Event()
        stop_event.set()  # Immediately stop to avoid actual recording
        
        try:
            recording_info = manager.record_audio_to_temp("button1", stop_event)
            print("record_audio_to_temp succeeded")
            print(f"Recording info: {recording_info}")
        except Exception as e:
            print(f"record_audio_to_temp failed: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()
        
        # Test 3: Test legacy compatibility
        print("\nTest 3: Testing legacy compatibility")
        try:
            legacy_manager = add_legacy_compatibility(manager)
            print("Legacy compatibility added successfully")
            
            # Test get_message
            try:
                path = legacy_manager.get_message()
                print(f"get_message() returned: {path}")
            except Exception as e:
                print(f"get_message() failed: {e}")
                import traceback
                traceback.print_exc()
                
        except Exception as e:
            print(f"Legacy compatibility failed: {e}")
            import traceback
            traceback.print_exc()
        
        print("\nAll tests completed")
        
        # Cleanup
        manager.cleanup()
        
    finally:
        # Clean up test directory
        shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == "__main__":
    run_basic_test()