#!/usr/bin/env python3
"""
Script to refactor large FastAPI files into smaller modules.

This script will:
1. Split fastapi_app.py into middleware/, factories/, and mocks/
2. Split large router files into sub-modules
3. Update import statements
"""

import os
import re
from pathlib import Path


def extract_mock_classes(source_file: Path, output_dir: Path):
    """Extract mock classes from fastapi_app.py to mocks/ directory."""
    with open(source_file, 'r') as f:
        content = f.read()

    # Find the start of mock implementations
    mock_start = content.find("# Mock implementations for development")
    mock_end = content.find("return create_app(", mock_start)

    if mock_start == -1 or mock_end == -1:
        print("Could not find mock implementations section")
        return False

    # Extract mock section
    mock_section = content[mock_start:mock_end]

    # Split into individual mock classes
    mock_classes = re.split(r'\n    class (Mock\w+)', mock_section)

    # Process each mock class
    mock_files = {}
    for i in range(1, len(mock_classes), 2):
        class_name = mock_classes[i]
        class_body = mock_classes[i+1] if i+1 < len(mock_classes) else ""

        # Find the full class definition
        class_def = f"class {class_name}" + class_body

        # Determine the file name
        file_name = class_name.lower().replace("mock", "mock_") + ".py"
        if file_name.startswith("mock__"):
            file_name = file_name.replace("mock__", "mock_")

        mock_files[file_name] = class_def

    # Write mock files
    output_dir.mkdir(parents=True, exist_ok=True)
    for file_name, class_content in mock_files.items():
        output_path = output_dir / file_name
        print(f"Creating {output_path}")

        # Would write files here, but let's print for review first
        print(f"  -> {class_name}")

    return True


def main():
    """Main refactoring process."""
    workspace = Path("/workspace")
    primary_adapters = workspace / "src" / "codetoreum" / "adapters" / "primary"

    # Paths
    fastapi_app_file = primary_adapters / "fastapi_app.py"
    mocks_dir = primary_adapters / "mocks"

    print("=" * 80)
    print("FastAPI Refactoring Script")
    print("=" * 80)

    # Step 1: Extract mock classes
    print("\nStep 1: Analyzing mock classes...")
    extract_mock_classes(fastapi_app_file, mocks_dir)

    print("\nDone!")


if __name__ == "__main__":
    main()
