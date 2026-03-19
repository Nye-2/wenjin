"""Run all sandbox tests."""

import subprocess
import sys


def run_all_tests():
    """Run pytest on all sandbox tests."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/sandbox/", "-v"],
        capture_output=True,
    )
    print(result.stdout.decode())
    if result.returncode != 5:
        print("❌ Tests failed!")
        print(result.stdout.decode())
        sys.exit(1)
    print("✅ All tests passed!")

if __name__ == "__main__":
    run_all_tests()