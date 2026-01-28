# Newspaper OCR Viewer

Tools for unpacking and viewing digitized newspaper archives with OCR data.

## Scripts

**unpack.py** - Extracts `.tar` files from a newspaper archive directory into `unpacked/`.

**viewer.py** - GUI viewer showing newspaper pages side-by-side with OCR bounding boxes overlay.

**block_viewer.py** - GUI viewer for individual TextBlocks. Shows cropped image regions with TextLine (blue) and String (red) bounding boxes alongside extracted text. Select XML files from dropdown, navigate blocks with arrow keys.

## Usage
With [uv](https://docs.astral.sh/uv/#installation) 

```bash
# Install dependencies
uv sync

# Unpack the archive
uv run unpack.py

# Launch the full page viewer
uv run viewer.py

# Launch the TextBlock viewer
uv run block_viewer.py
```

Use arrow keys or buttons to navigate.
