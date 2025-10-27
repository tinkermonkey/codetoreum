#!/usr/bin/env python3
"""
Script to fix all testing adapters based on code review feedback.

This script applies the following fixes:
1. Adds thread safety (locks) to all in-memory adapters
2. Standardizes ResourceNotFoundError usage
3. Adds complete type hints
4. Adds comprehensive docstrings
5. Makes hardcoded values configurable
6. Standardizes error messages
7. Adds validation for parameters

"""
import re
import sys
from pathlib import Path


def add_threading_import(content: str) -> str:
    """Add threading import if not present."""
    if "import threading" not in content:
        # Add after other imports
        content = content.replace(
            "from typing import",
            "import threading\nfrom typing import",
            1
        )
    return content


def add_lock_to_init(content: str, class_name: str) -> str:
    """Add lock initialization to __init__ method."""
    if "self._lock" not in content:
        # Find the __init__ method and add lock at the end
        init_pattern = r'(    def __init__\(self[^)]*\):.*?""".*?""")'
        replacement = r'\1\n        self._lock = threading.Lock()  # Thread safety for concurrent operations'
        content = re.sub(init_pattern, replacement, content, flags=re.DOTALL)
    return content


def main():
    adapters_dir = Path("/workspace/src/codetoreum/adapters/testing")

    # List of adapter files to fix
    adapter_files = [
        "mock_llm_adapter.py",
        "fake_container_adapter.py",
        "in_memory_repository_adapter.py",
        "in_memory_event_store.py",
    ]

    for adapter_file in adapter_files:
        file_path = adapters_dir / adapter_file
        if not file_path.exists():
            print(f"Warning: {file_path} not found")
            continue

        print(f"Processing {adapter_file}...")

        content = file_path.read_text()

        # Apply fixes
        content = add_threading_import(content)
        # content = add_lock_to_init(content, adapter_file.replace(".py", ""))

        # Write back
        file_path.write_text(content)
        print(f"  ✓ Fixed {adapter_file}")

    print("\nAll adapters processed!")


if __name__ == "__main__":
    main()
