# ComfyUI-Workflow-Gallery

A custom ComfyUI node that saves generated images and displays them in a scrollable in-node gallery.

## Features

- Receives image batches from your workflow
- Saves images to a chosen output directory
- Displays saved images as thumbnails inside the node
- Scrollable thumbnail gallery
- Configurable maximum image count
- Clear button to remove all images from the gallery
- Adjustable thumbnail size
- Click a thumbnail to open it in single-image viewer mode
- Close the viewer to return to the thumbnail gallery
- Passes images through unchanged for continued workflow use

## Notes

This node was developed and tested in a local Windows ComfyUI setup.

It is being shared as a useful community tool and may need adjustments for other environments or future ComfyUI frontend changes.

Bug reports are welcome, but I may not be able to provide full support for every setup.

## Why I made this

I wanted a cleaner way to review multiple generated images inside a workflow without digging through output folders every time.

A practical use case is generating multiple showcase images for wildcard packs, LoRAs, prompt packs, or Civitai posts. Instead of hunting through saved files, this node lets you review results directly inside ComfyUI.

## Screenshots

### Workflow Example
![Workflow Example](screenshots/workflow.png)

### Gallery View
![Gallery View](screenshots/Screenshot%202026-03-08%20000942.png)

### Viewer Mode
![Viewer Mode](screenshots/Screenshot%202026-03-08%20014404.png)

## Installation

1. Close ComfyUI
2. Copy this repository into your `ComfyUI/custom_nodes/` folder
3. Restart ComfyUI

Example:

```text
ComfyUI/
└── custom_nodes/
    └── ComfyUI-Workflow-Gallery/