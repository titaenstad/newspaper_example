#!/usr/bin/env python3
"""Simple script to unpack tar files in the newspaper archive directory."""

import tarfile
from pathlib import Path

UNPACKED_DIR = Path("unpacked")


def unpack_directory(source_dir: str):
    """Find and extract all .tar files in the given directory to the unpacked directory."""
    source_path = Path(source_dir)

    if not source_path.exists():
        print(f"Directory not found: {source_dir}")
        return

    tar_files = list(source_path.rglob("*.tar"))

    if not tar_files:
        print("No .tar files found")
        return

    print(f"Found {len(tar_files)} tar file(s)")

    for tar_path in tar_files:
        # Mirror the source directory structure under UNPACKED_DIR
        relative_path = tar_path.parent.relative_to(source_path.parent)
        extract_dir = UNPACKED_DIR / relative_path
        extract_dir.mkdir(parents=True, exist_ok=True)

        print(f"Extracting: {tar_path.name} -> {extract_dir}")

        with tarfile.open(tar_path, "r") as tar:
            tar.extractall(path=extract_dir)

        print(f"  Done!")


if __name__ == "__main__":
    unpack_directory("no-nb_digavis_fjellljom_null_null_19770426_91_46_1")
