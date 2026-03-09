## Features

- Receives image batches
- Saves images to a chosen directory
- Shows thumbnails inside the node UI
- Lets you clear the gallery
- Lets you resize thumbnails with a slider
- Click a thumbnail to open it in viewer mode
- Click the expanded image to return to the gallery
- Use on-screen left and right arrows to move through images in viewer mode
- Passes the input images through unchanged
- Automatically prunes oldest images when the gallery reaches the configured limit

## Install

1. Copy this folder into `ComfyUI/custom_nodes/`
2. Restart ComfyUI
3. Search for **Workflow Gallery** in the node menu under `image/ui`

## Inputs

- `images`: incoming image batch
- `enabled`: enable or bypass gallery collection
- `save_to_disk`: when enabled, writes originals to the chosen directory
- `output_directory`: target folder for saved images
- `filename_prefix`: filename prefix used for saved images
- `max_images`: maximum number of images retained by the gallery

## Notes

- If `save_to_disk` is disabled, the node still writes temporary originals into its package cache so viewer mode can work
- Clearing the gallery also deletes files tracked by the current node state
- This release is intentionally small and focused

## Recommended next improvements

- Add a folder picker if your target ComfyUI frontend version supports it cleanly
- Add pin/favorite support
- Add export selected / save selected
- Add captions or prompt metadata under thumbnails
- Add persistence restore from disk on startup