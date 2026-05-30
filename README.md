# Viewfinder

Viewfinder is a desktop image viewer and editor built with Python, OpenCV, and PySide6.
It is designed for basic image editing and is being extended toward face detection,
face recognition, and automated image sorting.

---

## Requirements

- Python 3.10 or newer

Install dependencies:

```
pip install -r requirements.txt
```

---

## Running the application

```
python viewfinder.py
```

---

## Features

### Viewing

- Open a single image or an entire directory.
- Navigate between images in the current directory using the left and right arrow keys.
- Zoom in and out with Ctrl + Mouse Wheel.
- Pan a zoomed image by holding the right mouse button and dragging.

### Selection (ROI)

A region of interest can be drawn on the image before applying any editing operation.
When a selection is active, edits affect only the selected area.

| Tool | How to use |
|---|---|
| Rectangle | Click and drag |
| Circle | Click and drag from the center |
| Polygon | Left-click to add vertices, right-click to close |
| Brush | Paint a free-form selection while a tool is open |

- **Ctrl+A** selects the entire image.
- **Ctrl+I** inverts the current selection.
- **Esc** cancels an in-progress polygon or clears the selection.

### Adjustments

Open the Adjustments panel to apply the following within the active selection
(or the whole image if no selection is active):

- Brightness (-100 to +100)
- Contrast (-100 to +100)
- Saturation (-100 to +100)
- Grayscale conversion

### Blur

Open the Blur panel to apply Gaussian blur.
Adjust blur strength and brush size with the sliders.
Click "Apply Blur" to apply to the selection, or use the brush to paint blur
directly onto the image.

### Transform

Open the Transform panel to flip or rotate the image:

- Flip horizontally (mirror left to right)
- Flip vertically (mirror top to bottom)
- Rotate 90 degrees clockwise
- Rotate 90 degrees counter-clockwise
- Rotate 180 degrees

### Crop and cut

- **Ctrl+K** crops the image to the bounding box of the active selection.
  For non-rectangular shapes (circle, polygon), pixels outside the selection
  become transparent and the image is saved with an alpha channel.
- **Ctrl+X** makes the selected area fully transparent (converts to RGBA if needed).
  Transparency is displayed as a grey and white checkerboard pattern.

When saving a file with transparency, choose PNG to preserve the alpha channel.
Saving to JPEG or BMP flattens the image onto a white background.

### Edit history

- **Ctrl+Z** undoes the last operation.
- **Ctrl+Y** redoes the last undone operation.

Every destructive edit (adjust, blur, crop, cut, transform) is recorded in the
undo stack. Any new edit clears the redo stack, matching the standard behaviour
of most editors.

### Saving

**Ctrl+S** opens a save dialog. Supported output formats:

- PNG (with optional transparency)
- JPEG
- BMP

---

## Keyboard shortcuts

A full list of shortcuts is available in the application under **Settings > Shortcuts**
or by pressing **Ctrl+/**.

---

## Project structure

```
viewfinder.py        Entry point
ui/
    main_window.py   Main window, image operations, shortcut bindings
    image_panel.py   Scrollable image display with zoom, pan, and ROI drawing
    tools_panel.py   Left sidebar with tool buttons and options
    directory_panel.py  Directory browser
assets/              Tool icons (PNG)
```

---

## Planned features

- Face detection and sorting of images by the people they contain
- Recognition of the same person across different ages
- Moving the open image to a target folder via keyboard shortcut
- Red-eye correction
- Histogram editing