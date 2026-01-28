#!/usr/bin/env python3
"""Web-based viewer for individual TextBlock elements with OCR text side-by-side."""

import io
import base64
from pathlib import Path
from dataclasses import dataclass
import xml.etree.ElementTree as ET

from flask import Flask, render_template_string, jsonify
from PIL import Image, ImageDraw

ALTO_NS = {"alto": "http://www.loc.gov/standards/alto/ns-v2#"}
UNPACKED_DIR = Path("unpacked")

app = Flask(__name__)


@dataclass
class StringBox:
    """A String element with bounding box."""
    content: str
    x: int
    y: int
    width: int
    height: int


@dataclass
class TextLine:
    """A TextLine element with its strings."""
    x: int
    y: int
    width: int
    height: int
    strings: list[StringBox]


@dataclass
class TextBlock:
    """A TextBlock element with its lines."""
    id: str
    x: int
    y: int
    width: int
    height: int
    lines: list[TextLine]

    def get_text(self) -> str:
        """Get full text content of the block."""
        result = []
        for line in self.lines:
            line_text = " ".join(s.content for s in line.strings)
            result.append(line_text)
        return "\n".join(result)


def parse_alto_xml(xml_path: Path) -> tuple[list[TextBlock], int, int]:
    """Parse ALTO XML and return TextBlocks and page dimensions."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    page = root.find(".//alto:Page", ALTO_NS)
    page_width = int(page.get("WIDTH", 0))
    page_height = int(page.get("HEIGHT", 0))

    blocks = []
    for block_elem in root.findall(".//alto:TextBlock", ALTO_NS):
        lines = []
        for line_elem in block_elem.findall("alto:TextLine", ALTO_NS):
            strings = []
            for string_elem in line_elem.findall("alto:String", ALTO_NS):
                strings.append(StringBox(
                    content=string_elem.get("CONTENT", ""),
                    x=int(string_elem.get("HPOS", 0)),
                    y=int(string_elem.get("VPOS", 0)),
                    width=int(string_elem.get("WIDTH", 0)),
                    height=int(string_elem.get("HEIGHT", 0)),
                ))
            lines.append(TextLine(
                x=int(line_elem.get("HPOS", 0)),
                y=int(line_elem.get("VPOS", 0)),
                width=int(line_elem.get("WIDTH", 0)),
                height=int(line_elem.get("HEIGHT", 0)),
                strings=strings,
            ))
        blocks.append(TextBlock(
            id=block_elem.get("ID", ""),
            x=int(block_elem.get("HPOS", 0)),
            y=int(block_elem.get("VPOS", 0)),
            width=int(block_elem.get("WIDTH", 0)),
            height=int(block_elem.get("HEIGHT", 0)),
            lines=lines,
        ))

    return blocks, page_width, page_height


def find_ocr_files(base_dir: Path) -> list[tuple[Path, Path]]:
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


def find_newspaper_dirs() -> list[Path]:
    """Find all newspaper directories in the unpacked folder."""
    if not UNPACKED_DIR.exists():
        return []
    return [d for d in UNPACKED_DIR.iterdir() if d.is_dir()]


# Global state
class ViewerState:
    def __init__(self):
        self.base_dir: Path | None = None
        self.pairs: list[tuple[Path, Path]] = []
        self.current_pair_index = 0
        self.blocks: list[TextBlock] = []
        self.page_width = 0
        self.page_height = 0
        self.image: Image.Image | None = None

    def load_base_dir(self, base_dir: Path):
        self.base_dir = base_dir
        self.pairs = find_ocr_files(base_dir)
        self.current_pair_index = 0
        if self.pairs:
            self.load_current_file()

    def load_current_file(self):
        if not self.pairs:
            return
        xml_path, image_path = self.pairs[self.current_pair_index]
        self.blocks, self.page_width, self.page_height = parse_alto_xml(xml_path)
        try:
            with Image.open(image_path) as img:
                self.image = img.convert("RGB").copy()
        except Exception as e:
            print(f"Error loading image: {e}")
            self.image = None

    def get_block_image(self, block_index: int) -> str | None:
        """Get base64-encoded PNG of a block with bounding boxes."""
        if self.image is None or block_index >= len(self.blocks):
            return None

        block = self.blocks[block_index]

        # Scale from ALTO coordinates to image coordinates
        scale_x = self.image.width / self.page_width
        scale_y = self.image.height / self.page_height

        # Add padding around the block
        padding = 20
        img_x = int(block.x * scale_x)
        img_y = int(block.y * scale_y)
        img_w = int(block.width * scale_x)
        img_h = int(block.height * scale_y)

        # Crop with padding
        crop_x1 = max(0, img_x - padding)
        crop_y1 = max(0, img_y - padding)
        crop_x2 = min(self.image.width, img_x + img_w + padding)
        crop_y2 = min(self.image.height, img_y + img_h + padding)

        cropped = self.image.crop((crop_x1, crop_y1, crop_x2, crop_y2))

        # Draw bounding boxes
        draw = ImageDraw.Draw(cropped)

        # Offset for drawing (account for crop and padding)
        offset_x = img_x - crop_x1
        offset_y = img_y - crop_y1

        # Draw TextLine boxes (blue)
        for line in block.lines:
            lx = int((line.x - block.x) * scale_x) + offset_x
            ly = int((line.y - block.y) * scale_y) + offset_y
            lw = int(line.width * scale_x)
            lh = int(line.height * scale_y)
            draw.rectangle([lx, ly, lx + lw, ly + lh], outline="blue", width=2)

            # Draw String boxes (red)
            for string in line.strings:
                sx = int((string.x - block.x) * scale_x) + offset_x
                sy = int((string.y - block.y) * scale_y) + offset_y
                sw = int(string.width * scale_x)
                sh = int(string.height * scale_y)
                draw.rectangle([sx, sy, sx + sw, sy + sh], outline="red", width=1)

        # Scale for display
        max_display = 800
        display_scale = min(max_display / cropped.width, max_display / cropped.height, 2.0)
        display_w = int(cropped.width * display_scale)
        display_h = int(cropped.height * display_scale)
        cropped = cropped.resize((display_w, display_h), Image.Resampling.LANCZOS)

        # Convert to base64
        buffer = io.BytesIO()
        cropped.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()


state = ViewerState()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>TextBlock Viewer</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .controls {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .controls select {
            padding: 8px 12px;
            font-size: 14px;
            border: 1px solid #ccc;
            border-radius: 4px;
            margin-right: 10px;
        }
        .nav {
            display: flex;
            align-items: center;
            gap: 15px;
            margin-top: 15px;
        }
        .nav button {
            padding: 10px 20px;
            font-size: 14px;
            border: none;
            border-radius: 4px;
            background: #007bff;
            color: white;
            cursor: pointer;
        }
        .nav button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .nav button:hover:not(:disabled) {
            background: #0056b3;
        }
        .nav .info {
            flex: 1;
            text-align: center;
            font-weight: 500;
        }
        .content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .panel {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .panel-header {
            background: #f8f9fa;
            padding: 12px 15px;
            font-weight: 600;
            border-bottom: 1px solid #eee;
        }
        .panel-body {
            padding: 15px;
        }
        .image-container {
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 400px;
            background: #fafafa;
        }
        .image-container img {
            max-width: 100%;
            height: auto;
        }
        .text-content {
            white-space: pre-wrap;
            font-family: Georgia, serif;
            font-size: 16px;
            line-height: 1.6;
            min-height: 400px;
        }
        .legend {
            margin-top: 10px;
            font-size: 12px;
            color: #666;
        }
        .legend span {
            margin-right: 15px;
        }
        .legend .line-box { color: blue; }
        .legend .word-box { color: red; }
        .keyboard-hint {
            margin-top: 10px;
            font-size: 12px;
            color: #888;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="controls">
            <label>XML File:
                <select id="fileSelect" onchange="loadFile()">
                    {% for pair in pairs %}
                    <option value="{{ loop.index0 }}">{{ pair[0].name }}</option>
                    {% endfor %}
                </select>
            </label>
            <div class="nav">
                <button id="prevBtn" onclick="navigate(-1)">&larr; Previous</button>
                <div class="info" id="blockInfo">Loading...</div>
                <button id="nextBtn" onclick="navigate(1)">Next &rarr;</button>
            </div>
            <div class="keyboard-hint">Use arrow keys &larr; &rarr; to navigate</div>
        </div>
        <div class="content">
            <div class="panel">
                <div class="panel-header">Image</div>
                <div class="panel-body">
                    <div class="image-container">
                        <img id="blockImage" src="" alt="Block image">
                    </div>
                    <div class="legend">
                        <span class="line-box">■ TextLine</span>
                        <span class="word-box">■ String/Word</span>
                    </div>
                </div>
            </div>
            <div class="panel">
                <div class="panel-header">OCR Text</div>
                <div class="panel-body">
                    <div class="text-content" id="blockText"></div>
                </div>
            </div>
        </div>
    </div>
    <script>
        let currentBlock = 0;
        let totalBlocks = 0;

        async function loadFile() {
            const fileIndex = document.getElementById('fileSelect').value;
            const response = await fetch(`/api/load_file/${fileIndex}`);
            const data = await response.json();
            totalBlocks = data.total_blocks;
            currentBlock = 0;
            loadBlock();
        }

        async function loadBlock() {
            const response = await fetch(`/api/block/${currentBlock}`);
            const data = await response.json();

            document.getElementById('blockImage').src = 'data:image/png;base64,' + data.image;
            document.getElementById('blockText').textContent = data.text;
            document.getElementById('blockInfo').textContent =
                `Block ${currentBlock + 1} of ${totalBlocks} (${data.id})`;

            document.getElementById('prevBtn').disabled = currentBlock === 0;
            document.getElementById('nextBtn').disabled = currentBlock >= totalBlocks - 1;
        }

        function navigate(delta) {
            const newIndex = currentBlock + delta;
            if (newIndex >= 0 && newIndex < totalBlocks) {
                currentBlock = newIndex;
                loadBlock();
            }
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') navigate(-1);
            if (e.key === 'ArrowRight') navigate(1);
        });

        // Initial load
        loadFile();
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, pairs=state.pairs)


@app.route("/api/load_file/<int:file_index>")
def load_file(file_index: int):
    state.current_pair_index = file_index
    state.load_current_file()
    return jsonify({"total_blocks": len(state.blocks)})


@app.route("/api/block/<int:block_index>")
def get_block(block_index: int):
    if block_index >= len(state.blocks):
        return jsonify({"error": "Block not found"}), 404

    block = state.blocks[block_index]
    image_data = state.get_block_image(block_index)

    return jsonify({
        "id": block.id,
        "text": block.get_text(),
        "image": image_data or "",
    })


def main():
    """Main entry point."""
    dirs = find_newspaper_dirs()
    if not dirs:
        print("No unpacked newspaper directories found. Run unpack.py first.")
        return

    base_dir = dirs[0]
    print(f"Loading from: {base_dir}")

    state.load_base_dir(base_dir)

    if not state.pairs:
        print("No OCR files found.")
        return

    print(f"Found {len(state.pairs)} page(s) with {len(state.blocks)} blocks")
    print("Starting server at http://127.0.0.1:5000")
    print("Press Ctrl+C to stop")

    app.run(debug=False, port=5000)


if __name__ == "__main__":
    main()
