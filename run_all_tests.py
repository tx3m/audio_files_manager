#!/usr/bin/env python3
"""
Comprehensive test runner for the Enhanced Audio File Manager.
This script runs all tests and provides detailed reporting.
"""

import unittest
import sys
import os
import time
from pathlib import Path

# Add the source directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

def discover_and_run_tests():
    """Discover and run all tests with detailed reporting."""
    
    print("=" * 80)
    print("Enhanced Audio File Manager - Comprehensive Test Suite")
    print("=" * 80)
    
    # Test discovery
    loader = unittest.TestLoader()
    start_dir = Path(__file__).parent / 'tests'
    
    # Discover all test files
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    # Count total tests
    total_tests = suite.countTestCases()
    print(f"Discovered {total_tests} tests")
    print("-" * 80)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout,
        descriptions=True,
        failfast=False
    )
    
    start_time = time.time()
    result = runner.run(suite)
    end_time = time.time()
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    print(f"Total time: {end_time - start_time:.2f} seconds")
    
    # Print detailed failure information
    if result.failures:
        print("\n" + "-" * 80)
        print("FAILURES:")
        print("-" * 80)
        for test, traceback in result.failures:
            print(f"\nFAILED: {test}")
            print(traceback)
    
    if result.errors:
        print("\n" + "-" * 80)
        print("ERRORS:")
        print("-" * 80)
        for test, traceback in result.errors:
            print(f"\nERROR: {test}")
            print(traceback)
    
    # Return success status
    return len(result.failures) == 0 and len(result.errors) == 0


def run_specific_test_module(module_name):
    """Run tests from a specific module."""
    
    print(f"Running tests from module: {module_name}")
    print("-" * 80)
    
    loader = unittest.TestLoader()
    
    try:
        # Import the test module
        test_module = __import__(f'tests.{module_name}', fromlist=[''])
        suite = loader.loadTestsFromModule(test_module)
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        return len(result.failures) == 0 and len(result.errors) == 0
        
    except ImportError as e:
        print(f"Error importing test module {module_name}: {e}")
        return False


def run_test_categories():
    """Run tests by category."""
    
    categories = {
        "Backend Tests": ["test_backends"],
        "Enhanced Manager Tests": ["test_enhanced_manager"],
        "Legacy Integration Tests": ["test_legacy_integration"],
        "Example Tests": ["test_enhanced_examples"],
        "Comprehensive Tests": ["test_comprehensive"],
        "Original Tests": ["test_manager", "test_metadata_only"]
    }
    
    results = {}
    
    for category, modules in categories.items():
        print(f"\n{'=' * 80}")
        print(f"RUNNING {category.upper()}")
        print("=" * 80)
        
        category_success = True
        
        for module in modules:
            print(f"\n--- {module} ---")
            success = run_specific_test_module(module)
            if not success:
                category_success = False
        
        results[category] = category_success
        
        status = "✅ PASSED" if category_success else "❌ FAILED"
        print(f"\n{category}: {status}")
    
    # Print category summary
    print(f"\n{'=' * 80}")
    print("CATEGORY SUMMARY")
    print("=" * 80)
    
    for category, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{category:<30} {status}")
    
    return all(results.values())


def main():
    """Main test runner function."""
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "all":
            success = discover_and_run_tests()
        elif command == "categories":
            success = run_test_categories()
        elif command.startswith("test_"):
            success = run_specific_test_module(command)
        else:
            print(f"Unknown command: {command}")
            print("Usage:")
            print("  python run_all_tests.py all          # Run all tests")
            print("  python run_all_tests.py categories   # Run tests by category")
            print("  python run_all_tests.py test_module  # Run specific test module")
            return 1
    else:
        # Default: run by categories for better organization
        success = run_test_categories()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())