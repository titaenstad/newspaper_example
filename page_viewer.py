#!/usr/bin/env python3
"""Simple viewer for newspaper OCR XML files with bounding box overlay - Flask version."""

from flask import Flask, render_template, send_file, jsonify, request
from pathlib import Path
from dataclasses import dataclass
import xml.etree.ElementTree as ET
import io

from PIL import Image

from alto_utils import ALTO_NS, find_newspaper_dirs, find_ocr_pairs

app = Flask(__name__)


@dataclass
class TextBox:
    """A text element with its bounding box."""
    content: str
    x: int
    y: int
    width: int
    height: int


@dataclass
class TextLine:
    """A text line with its bounding box."""
    x: int
    y: int
    width: int
    height: int


@dataclass
class Illustration:
    """An illustration with its bounding box."""
    x: int
    y: int
    width: int
    height: int
    type: str


@dataclass
class ComposedBlock:
    """A composed block (article) with its bounding box."""
    x: int
    y: int
    width: int
    height: int
    id: str


# Global state and caches
_pairs: list[tuple[Path, Path]] = []
_base_dir: Path | None = None
_xml_cache: dict[Path, tuple] = {}
_image_dims_cache: dict[Path, tuple[int, int]] = {}
_rendered_image_cache: dict[tuple, bytes] = {}  # (path, zoom) -> JPEG bytes


def parse_alto_xml(xml_path: Path) -> tuple[list[TextBox], list[TextLine], list[Illustration], list[ComposedBlock], int, int]:
    """Parse ALTO XML and return text boxes, text lines, illustrations, composed blocks, and page dimensions."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    page = root.find(".//alto:Page", ALTO_NS)
    page_width = int(page.get("WIDTH", 0))
    page_height = int(page.get("HEIGHT", 0))

    boxes = []
    for string in root.findall(".//alto:String", ALTO_NS):
        boxes.append(TextBox(
            content=string.get("CONTENT", ""),
            x=int(string.get("HPOS", 0)),
            y=int(string.get("VPOS", 0)),
            width=int(string.get("WIDTH", 0)),
            height=int(string.get("HEIGHT", 0))
        ))

    lines = []
    for line in root.findall(".//alto:TextLine", ALTO_NS):
        lines.append(TextLine(
            x=int(line.get("HPOS", 0)),
            y=int(line.get("VPOS", 0)),
            width=int(line.get("WIDTH", 0)),
            height=int(line.get("HEIGHT", 0))
        ))

    illustrations = []
    for ill in root.findall(".//alto:Illustration", ALTO_NS):
        illustrations.append(Illustration(
            x=int(ill.get("HPOS", 0)),
            y=int(ill.get("VPOS", 0)),
            width=int(ill.get("WIDTH", 0)),
            height=int(ill.get("HEIGHT", 0)),
            type=ill.get("TYPE", "")
        ))

    composed_blocks = []
    for block in root.findall(".//alto:ComposedBlock", ALTO_NS):
        composed_blocks.append(ComposedBlock(
            x=int(block.get("HPOS", 0)),
            y=int(block.get("VPOS", 0)),
            width=int(block.get("WIDTH", 0)),
            height=int(block.get("HEIGHT", 0)),
            id=block.get("ID", "")
        ))

    return boxes, lines, illustrations, composed_blocks, page_width, page_height


def init_pairs():
    """Initialize the OCR pairs."""
    global _pairs, _base_dir
    if not _pairs:
        dirs = find_newspaper_dirs()
        if dirs:
            _base_dir = dirs[0]
            _pairs = find_ocr_pairs(_base_dir)


def get_parsed_xml(xml_path: Path):
    """Get parsed XML data, using cache if available."""
    if xml_path not in _xml_cache:
        _xml_cache[xml_path] = parse_alto_xml(xml_path)
    return _xml_cache[xml_path]


def get_image_dims(image_path: Path) -> tuple[int, int]:
    """Get image dimensions, using cache if available."""
    if image_path not in _image_dims_cache:
        with Image.open(image_path) as img:
            _image_dims_cache[image_path] = (img.width, img.height)
    return _image_dims_cache[image_path]


@app.route("/")
def index():
    """Serve the main viewer page."""
    init_pairs()
    return render_template("page_viewer.html")


@app.route("/api/info")
def api_info():
    """Return basic info about available pages."""
    init_pairs()
    return jsonify({
        "total_pages": len(_pairs),
        "base_dir": str(_base_dir) if _base_dir else None
    })


@app.route("/api/page/<int:index>")
def api_page(index: int):
    """Return page data (boxes and dimensions) for a specific page."""
    init_pairs()

    if not _pairs or index < 0 or index >= len(_pairs):
        return jsonify({"error": "Page not found"})

    xml_path, image_path = _pairs[index]
    boxes, lines, illustrations, composed_blocks, page_width, page_height = get_parsed_xml(xml_path)

    zoom = int(request.args.get("zoom", 100))
    zoom_factor = zoom / 100.0

    try:
        img_width, img_height = get_image_dims(image_path)
        base_scale = min(3200 / img_width, 3200 / img_height, 4.0)
        img_scale = base_scale * zoom_factor
        display_width = int(img_width * img_scale)
        display_height = int(img_height * img_scale)

        box_scale_x = img_width / page_width
        box_scale_y = img_height / page_height

        def scale_box(b):
            return {
                "x": int(b.x * box_scale_x * img_scale),
                "y": int(b.y * box_scale_y * img_scale),
                "width": int(b.width * box_scale_x * img_scale),
                "height": int(b.height * box_scale_y * img_scale)
            }

        scaled_boxes = [{**scale_box(b), "content": b.content} for b in boxes]
        scaled_lines = [scale_box(l) for l in lines]
        scaled_illustrations = [{**scale_box(i), "type": i.type} for i in illustrations]
        scaled_composed_blocks = [{**scale_box(c), "id": c.id} for c in composed_blocks]

        return jsonify({
            "filename": xml_path.stem,
            "total_pages": len(_pairs),
            "display_width": display_width,
            "display_height": display_height,
            "boxes": scaled_boxes,
            "lines": scaled_lines,
            "illustrations": scaled_illustrations,
            "composed_blocks": scaled_composed_blocks
        })

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/image/<int:index>")
def api_image(index: int):
    """Return the base image without bounding boxes (cached)."""
    init_pairs()

    if not _pairs or index < 0 or index >= len(_pairs):
        return "Not found", 404

    xml_path, image_path = _pairs[index]
    zoom = int(request.args.get("zoom", 100))

    # Check cache
    cache_key = (image_path, zoom)
    if cache_key in _rendered_image_cache:
        buffer = io.BytesIO(_rendered_image_cache[cache_key])
        return send_file(buffer, mimetype="image/jpeg")

    zoom_factor = zoom / 100.0

    try:
        image = Image.open(image_path)
        orig_width, orig_height = image.width, image.height

        if image.mode != "RGB":
            image = image.convert("RGB")

        base_scale = min(3200 / orig_width, 3200 / orig_height, 4.0)
        img_scale = base_scale * zoom_factor
        display_width = int(orig_width * img_scale)
        display_height = int(orig_height * img_scale)

        image = image.resize((display_width, display_height), Image.Resampling.BILINEAR)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        jpeg_bytes = buffer.getvalue()

        _rendered_image_cache[cache_key] = jpeg_bytes

        buffer.seek(0)
        return send_file(buffer, mimetype="image/jpeg")

    except Exception as e:
        return str(e), 500


def main():
    """Main entry point."""
    dirs = find_newspaper_dirs()
    if not dirs:
        print("No unpacked newspaper directories found. Run unpack.py first.")
        return

    print(f"Loading from: {dirs[0]}")
    print("Starting server at http://127.0.0.1:5001/")
    app.run(host="127.0.0.1", port=5001, debug=False)


if __name__ == "__main__":
    main()
