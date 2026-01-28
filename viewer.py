#!/usr/bin/env python3
"""Simple viewer for newspaper OCR XML files with bounding box overlay."""

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from dataclasses import dataclass
import xml.etree.ElementTree as ET
import io

from PIL import Image, ImageDraw

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


def parse_alto_xml(xml_path: Path) -> tuple[list[TextBox], int, int]:
    """Parse ALTO XML and return list of text boxes and page dimensions."""
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

    return boxes, page_width, page_height


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


class NewspaperViewer:
    """Main viewer application."""

    def __init__(self, root: tk.Tk, base_dir: Path):
        self.root = root
        self.root.title("Newspaper OCR Viewer")

        self.pairs = find_ocr_pairs(base_dir)
        self.current_index = 0

        if not self.pairs:
            ttk.Label(root, text="No OCR files found").pack()
            return

        self.setup_ui()
        self.load_current()

    def setup_ui(self):
        """Set up the user interface."""
        # Navigation frame
        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        self.prev_btn = ttk.Button(nav_frame, text="< Previous", command=self.prev_page)
        self.prev_btn.pack(side=tk.LEFT)

        self.page_label = ttk.Label(nav_frame, text="")
        self.page_label.pack(side=tk.LEFT, expand=True)

        self.next_btn = ttk.Button(nav_frame, text="Next >", command=self.next_page)
        self.next_btn.pack(side=tk.RIGHT)

        # Main container with shared scrollbars
        main_frame = ttk.Frame(self.root)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Shared scrollbars
        self.scroll_y = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.sync_yview)
        self.scroll_x = ttk.Scrollbar(main_frame, orient=tk.HORIZONTAL, command=self.sync_xview)

        # Content frame for the two panels
        content_frame = ttk.Frame(main_frame)

        # Left panel: Image with bounding boxes
        left_frame = ttk.LabelFrame(content_frame, text="Image with Bounding Boxes")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 2))

        self.left_canvas = tk.Canvas(left_frame, bg="gray")
        self.left_canvas.pack(fill=tk.BOTH, expand=True)

        # Right panel: Bounding boxes with text only
        right_frame = ttk.LabelFrame(content_frame, text="Text and Bounding Boxes")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(2, 0))

        self.right_canvas = tk.Canvas(right_frame, bg="white")
        self.right_canvas.pack(fill=tk.BOTH, expand=True)

        # Configure canvases to report scroll position to shared scrollbar
        self.left_canvas.configure(
            yscrollcommand=self.sync_scroll_y,
            xscrollcommand=self.sync_scroll_x
        )
        self.right_canvas.configure(
            yscrollcommand=self.sync_scroll_y,
            xscrollcommand=self.sync_scroll_x
        )

        # Layout with grid for proper scrollbar placement
        self.scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Keyboard bindings
        self.root.bind("<Left>", lambda e: self.prev_page())
        self.root.bind("<Right>", lambda e: self.next_page())

        # Mouse wheel scrolling
        self.left_canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.right_canvas.bind("<MouseWheel>", self.on_mousewheel)
        # Linux mouse wheel
        self.left_canvas.bind("<Button-4>", lambda e: self.on_mousewheel_linux(-1))
        self.left_canvas.bind("<Button-5>", lambda e: self.on_mousewheel_linux(1))
        self.right_canvas.bind("<Button-4>", lambda e: self.on_mousewheel_linux(-1))
        self.right_canvas.bind("<Button-5>", lambda e: self.on_mousewheel_linux(1))

    def sync_yview(self, *args):
        """Scroll both canvases vertically."""
        self.left_canvas.yview(*args)
        self.right_canvas.yview(*args)

    def sync_xview(self, *args):
        """Scroll both canvases horizontally."""
        self.left_canvas.xview(*args)
        self.right_canvas.xview(*args)

    def sync_scroll_y(self, first, last):
        """Update shared vertical scrollbar."""
        self.scroll_y.set(first, last)

    def sync_scroll_x(self, first, last):
        """Update shared horizontal scrollbar."""
        self.scroll_x.set(first, last)

    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling (Windows/Mac)."""
        self.left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.right_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_mousewheel_linux(self, direction):
        """Handle mouse wheel scrolling (Linux)."""
        self.left_canvas.yview_scroll(direction, "units")
        self.right_canvas.yview_scroll(direction, "units")

    def load_current(self):
        """Load the current XML/image pair."""
        xml_path, image_path = self.pairs[self.current_index]

        # Update page label
        self.page_label.config(
            text=f"Page {self.current_index + 1} of {len(self.pairs)}: {xml_path.stem}"
        )

        # Update button states
        self.prev_btn.config(state=tk.NORMAL if self.current_index > 0 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL if self.current_index < len(self.pairs) - 1 else tk.DISABLED)

        # Parse XML
        boxes, page_width, page_height = parse_alto_xml(xml_path)

        # Load and display image with bounding boxes
        try:
            image = Image.open(image_path)
            # Convert grayscale to RGB for display
            if image.mode != "RGB":
                image = image.convert("RGB")
            img_scale = min(1600 / image.width, 1600 / image.height, 2.0)
            display_width = int(image.width * img_scale)
            display_height = int(image.height * img_scale)

            # Scale boxes relative to image
            box_scale_x = image.width / page_width
            box_scale_y = image.height / page_height

            # Draw bounding boxes on image
            overlay = image.copy()
            draw = ImageDraw.Draw(overlay)
            for box in boxes:
                x1 = int(box.x * box_scale_x)
                y1 = int(box.y * box_scale_y)
                x2 = int((box.x + box.width) * box_scale_x)
                y2 = int((box.y + box.height) * box_scale_y)
                draw.rectangle([x1, y1, x2, y2], outline="red", width=2)

            # Resize for display
            overlay = overlay.resize((display_width, display_height), Image.Resampling.LANCZOS)
            # Use PNG bytes workaround for ImageTk compatibility
            buffer = io.BytesIO()
            overlay.save(buffer, format="PNG")
            self.left_photo = tk.PhotoImage(data=buffer.getvalue())

            self.left_canvas.delete("all")
            self.left_canvas.create_image(0, 0, anchor=tk.NW, image=self.left_photo)
            self.left_canvas.configure(scrollregion=(0, 0, display_width, display_height))

            # Draw bounding boxes with text on right panel
            # Use same scaling as left panel for consistency
            self.right_canvas.delete("all")
            right_scale_x = display_width / page_width
            right_scale_y = display_height / page_height

            for box in boxes:
                x1 = int(box.x * right_scale_x)
                y1 = int(box.y * right_scale_y)
                x2 = int((box.x + box.width) * right_scale_x)
                y2 = int((box.y + box.height) * right_scale_y)

                self.right_canvas.create_rectangle(x1, y1, x2, y2, outline="blue", width=1)
                # Draw text centered in box
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                self.right_canvas.create_text(cx, cy, text=box.content, font=("TkDefaultFont", 8))

            self.right_canvas.configure(scrollregion=(0, 0, display_width, display_height))

        except Exception as e:
            print(f"Error loading image: {e}")
            import traceback
            traceback.print_exc()
            self.left_canvas.delete("all")
            self.left_canvas.create_text(10, 10, anchor=tk.NW, text=f"Error loading image: {e}")

    def prev_page(self):
        """Go to previous page."""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current()

    def next_page(self):
        """Go to next page."""
        if self.current_index < len(self.pairs) - 1:
            self.current_index += 1
            self.load_current()


def find_newspaper_dirs() -> list[Path]:
    """Find all newspaper directories in the unpacked folder."""
    if not UNPACKED_DIR.exists():
        return []
    return [d for d in UNPACKED_DIR.iterdir() if d.is_dir()]


def main():
    """Main entry point."""
    dirs = find_newspaper_dirs()
    if not dirs:
        print("No unpacked newspaper directories found. Run unpack.py first.")
        return

    # Use the first directory found
    base_dir = dirs[0]
    print(f"Loading from: {base_dir}")

    root = tk.Tk()
    root.geometry("1400x900")
    NewspaperViewer(root, base_dir)
    root.mainloop()


if __name__ == "__main__":
    main()
