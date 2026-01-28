"""Shared utilities for ALTO XML newspaper viewers."""

from pathlib import Path

# ALTO XML namespace
ALTO_NS = {"alto": "http://www.loc.gov/standards/alto/ns-v2#"}

# Default directory for unpacked newspapers
UNPACKED_DIR = Path("unpacked")


def find_newspaper_dirs(unpacked_dir: Path = UNPACKED_DIR) -> list[Path]:
    """Find all newspaper directories in the unpacked folder."""
    if not unpacked_dir.exists():
        return []
    return [d for d in unpacked_dir.iterdir() if d.is_dir()]


def find_ocr_pairs(base_dir: Path) -> list[tuple[Path, Path]]:
    """Find pairs of (xml_file, image_file) in the OCR directory."""
    ocr_dir = base_dir / "ocr"
    if not ocr_dir.exists():
        return []

    pairs = []
    for xml_file in sorted(ocr_dir.glob("*_null.xml")):
        image_file = xml_file.with_suffix(".jp2")
        if image_file.exists():
            pairs.append((xml_file, image_file))
    return pairs
