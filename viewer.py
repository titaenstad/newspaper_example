#!/usr/bin/env python3
"""Simple viewer for newspaper OCR XML files with bounding box overlay - Flask version."""

from flask import Flask, render_template_string, send_file, jsonify
from pathlib import Path
from dataclasses import dataclass
import xml.etree.ElementTree as ET
import io

from PIL import Image, ImageDraw

app = Flask(__name__)

ALTO_NS = {"alto": "http://www.loc.gov/standards/alto/ns-v2#"}
UNPACKED_DIR = Path("unpacked")


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


def parse_alto_xml(xml_path: Path) -> tuple[list[TextBox], list[TextLine], int, int]:
    """Parse ALTO XML and return list of text boxes, text lines, and page dimensions."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Get page dimensions
    page = root.find(".//alto:Page", ALTO_NS)
    page_width = int(page.get("WIDTH", 0))
    page_height = int(page.get("HEIGHT", 0))

    boxes = []
    for string in root.findall(".//alto:String", ALTO_NS):
        content = string.get("CONTENT", "")
        x = int(string.get("HPOS", 0))
        y = int(string.get("VPOS", 0))
        width = int(string.get("WIDTH", 0))
        height = int(string.get("HEIGHT", 0))
        boxes.append(TextBox(content, x, y, width, height))

    lines = []
    for line in root.findall(".//alto:TextLine", ALTO_NS):
        x = int(line.get("HPOS", 0))
        y = int(line.get("VPOS", 0))
        width = int(line.get("WIDTH", 0))
        height = int(line.get("HEIGHT", 0))
        lines.append(TextLine(x, y, width, height))

    return boxes, lines, page_width, page_height


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


def find_newspaper_dirs() -> list[Path]:
    """Find all newspaper directories in the unpacked folder."""
    if not UNPACKED_DIR.exists():
        return []
    return [d for d in UNPACKED_DIR.iterdir() if d.is_dir()]


# Global state
_pairs: list[tuple[Path, Path]] = []
_base_dir: Path | None = None


def init_pairs():
    """Initialize the OCR pairs."""
    global _pairs, _base_dir
    if not _pairs:
        dirs = find_newspaper_dirs()
        if dirs:
            _base_dir = dirs[0]
            _pairs = find_ocr_pairs(_base_dir)


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Newspaper OCR Viewer</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: #1a1a1a;
            color: #fff;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .nav {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 20px;
            background: #2a2a2a;
            border-bottom: 1px solid #444;
        }
        .nav button {
            padding: 8px 16px;
            background: #444;
            color: #fff;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        .nav button:hover:not(:disabled) {
            background: #555;
        }
        .nav button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .page-info {
            font-size: 14px;
            color: #aaa;
        }
        .container {
            display: flex;
            flex: 1;
            overflow: hidden;
        }
        .panel {
            flex: 1;
            display: flex;
            flex-direction: column;
            border: 1px solid #444;
            margin: 10px;
            border-radius: 4px;
            overflow: hidden;
        }
        .panel-header {
            padding: 8px 12px;
            background: #333;
            border-bottom: 1px solid #444;
            font-size: 13px;
            color: #aaa;
        }
        .panel-content {
            flex: 1;
            overflow: auto;
            position: relative;
        }
        .left-panel .panel-content {
            background: #333;
        }
        .right-panel .panel-content {
            background: #fff;
        }
        .canvas-container {
            position: relative;
            display: inline-block;
        }
        .canvas-container img {
            display: block;
        }
        .text-overlay {
            position: relative;
        }
        .text-box {
            position: absolute;
            border: 1px solid blue;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 8px;
            color: #000;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .text-line {
            position: absolute;
            border: 2px solid green;
            pointer-events: none;
        }
        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: #aaa;
        }
    </style>
</head>
<body>
    <div class="nav">
        <button id="prevBtn" onclick="navigate(-1)">&lt; Previous</button>
        <span class="page-info" id="pageInfo">Loading...</span>
        <button id="nextBtn" onclick="navigate(1)">Next &gt;</button>
    </div>
    <div class="container">
        <div class="panel left-panel">
            <div class="panel-header">Image with Bounding Boxes</div>
            <div class="panel-content" id="leftPanel">
                <div class="loading">Loading...</div>
            </div>
        </div>
        <div class="panel right-panel">
            <div class="panel-header">Text and Bounding Boxes</div>
            <div class="panel-content" id="rightPanel">
                <div class="loading">Loading...</div>
            </div>
        </div>
    </div>

    <script>
        let currentIndex = 0;
        let totalPages = 0;

        const leftPanel = document.getElementById('leftPanel');
        const rightPanel = document.getElementById('rightPanel');

        // Synchronized scrolling
        let syncing = false;

        leftPanel.addEventListener('scroll', () => {
            if (syncing) return;
            syncing = true;
            rightPanel.scrollTop = leftPanel.scrollTop;
            rightPanel.scrollLeft = leftPanel.scrollLeft;
            syncing = false;
        });

        rightPanel.addEventListener('scroll', () => {
            if (syncing) return;
            syncing = true;
            leftPanel.scrollTop = rightPanel.scrollTop;
            leftPanel.scrollLeft = rightPanel.scrollLeft;
            syncing = false;
        });

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') navigate(-1);
            if (e.key === 'ArrowRight') navigate(1);
        });

        async function loadPage(index) {
            currentIndex = index;

            // Update navigation
            document.getElementById('prevBtn').disabled = currentIndex <= 0;
            document.getElementById('nextBtn').disabled = currentIndex >= totalPages - 1;

            // Show loading
            leftPanel.innerHTML = '<div class="loading">Loading...</div>';
            rightPanel.innerHTML = '<div class="loading">Loading...</div>';

            try {
                // Get page data
                const response = await fetch(`/api/page/${index}`);
                const data = await response.json();

                if (data.error) {
                    leftPanel.innerHTML = `<div class="loading">${data.error}</div>`;
                    rightPanel.innerHTML = `<div class="loading">${data.error}</div>`;
                    return;
                }

                totalPages = data.total_pages;
                document.getElementById('pageInfo').textContent =
                    `Page ${currentIndex + 1} of ${totalPages}: ${data.filename}`;

                // Load left panel (image with boxes)
                leftPanel.innerHTML = `
                    <div class="canvas-container">
                        <div class="loading" id="imageLoading">Image is loading...</div>
                        <img src="/api/image/${index}" alt="Page image" onload="document.getElementById('imageLoading').style.display='none'" style="display:none" onload="this.style.display='block'">
                    </div>
                `;
                // Show image when loaded
                const img = leftPanel.querySelector('img');
                img.onload = () => {
                    document.getElementById('imageLoading').style.display = 'none';
                    img.style.display = 'block';
                };

                // Load right panel (text lines and text boxes)
                let textHtml = `<div class="text-overlay" style="width: ${data.display_width}px; height: ${data.display_height}px; position: relative;">`;
                // Draw TextLine boxes first (green)
                for (const line of data.lines) {
                    textHtml += `
                        <div class="text-line" style="
                            left: ${line.x}px;
                            top: ${line.y}px;
                            width: ${line.width}px;
                            height: ${line.height}px;
                        "></div>
                    `;
                }
                // Draw String boxes on top (blue)
                for (const box of data.boxes) {
                    textHtml += `
                        <div class="text-box" style="
                            left: ${box.x}px;
                            top: ${box.y}px;
                            width: ${box.width}px;
                            height: ${box.height}px;
                        ">${escapeHtml(box.content)}</div>
                    `;
                }
                textHtml += '</div>';
                rightPanel.innerHTML = textHtml;

            } catch (err) {
                leftPanel.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
                rightPanel.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function navigate(delta) {
            const newIndex = currentIndex + delta;
            if (newIndex >= 0 && newIndex < totalPages) {
                loadPage(newIndex);
            }
        }

        // Initial load
        fetch('/api/info').then(r => r.json()).then(data => {
            totalPages = data.total_pages;
            if (totalPages > 0) {
                loadPage(0);
            } else {
                document.getElementById('pageInfo').textContent = 'No OCR files found';
                leftPanel.innerHTML = '<div class="loading">No OCR files found. Run unpack.py first.</div>';
                rightPanel.innerHTML = '<div class="loading">No OCR files found. Run unpack.py first.</div>';
            }
        });
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    """Serve the main viewer page."""
    init_pairs()
    return render_template_string(HTML_TEMPLATE)


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
    boxes, lines, page_width, page_height = parse_alto_xml(xml_path)

    # Load image to get actual dimensions
    try:
        image = Image.open(image_path)
        img_scale = min(3200 / image.width, 3200 / image.height, 4.0)
        display_width = int(image.width * img_scale)
        display_height = int(image.height * img_scale)

        # Scale factors for boxes
        box_scale_x = image.width / page_width
        box_scale_y = image.height / page_height

        # Calculate scaled box positions for display
        scaled_boxes = []
        for box in boxes:
            x1 = int(box.x * box_scale_x * img_scale)
            y1 = int(box.y * box_scale_y * img_scale)
            w = int(box.width * box_scale_x * img_scale)
            h = int(box.height * box_scale_y * img_scale)
            scaled_boxes.append({
                "content": box.content,
                "x": x1,
                "y": y1,
                "width": w,
                "height": h
            })

        # Calculate scaled line positions for display
        scaled_lines = []
        for line in lines:
            x1 = int(line.x * box_scale_x * img_scale)
            y1 = int(line.y * box_scale_y * img_scale)
            w = int(line.width * box_scale_x * img_scale)
            h = int(line.height * box_scale_y * img_scale)
            scaled_lines.append({
                "x": x1,
                "y": y1,
                "width": w,
                "height": h
            })

        return jsonify({
            "filename": xml_path.stem,
            "total_pages": len(_pairs),
            "display_width": display_width,
            "display_height": display_height,
            "boxes": scaled_boxes,
            "lines": scaled_lines
        })

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/image/<int:index>")
def api_image(index: int):
    """Return the image with bounding boxes drawn."""
    init_pairs()

    if not _pairs or index < 0 or index >= len(_pairs):
        return "Not found", 404

    xml_path, image_path = _pairs[index]
    boxes, lines, page_width, page_height = parse_alto_xml(xml_path)

    try:
        image = Image.open(image_path)

        # Convert grayscale to RGB for display
        if image.mode != "RGB":
            image = image.convert("RGB")

        img_scale = min(3200 / image.width, 3200 / image.height, 4.0)
        display_width = int(image.width * img_scale)
        display_height = int(image.height * img_scale)

        # Scale boxes relative to image
        box_scale_x = image.width / page_width
        box_scale_y = image.height / page_height

        # Draw bounding boxes on image
        draw = ImageDraw.Draw(image)

        # Draw TextLine boxes in green
        for line in lines:
            x1 = int(line.x * box_scale_x)
            y1 = int(line.y * box_scale_y)
            x2 = int((line.x + line.width) * box_scale_x)
            y2 = int((line.y + line.height) * box_scale_y)
            draw.rectangle([x1, y1, x2, y2], outline="green", width=2)

        # Draw String boxes in red
        for box in boxes:
            x1 = int(box.x * box_scale_x)
            y1 = int(box.y * box_scale_y)
            x2 = int((box.x + box.width) * box_scale_x)
            y2 = int((box.y + box.height) * box_scale_y)
            draw.rectangle([x1, y1, x2, y2], outline="red", width=2)

        # Resize for display
        image = image.resize((display_width, display_height), Image.Resampling.LANCZOS)

        # Return as PNG
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png")

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
