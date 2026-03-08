# Workflow Gallery for ComfyUI

Workflow Gallery is a custom ComfyUI node that collects images passing through it and displays them inside a scrollable gallery directly on the node.

##v0.1.8
## Changes
- Added on-screen left/right navigation arrows in viewer mode
- Removed keyboard navigation
- Click expanded image to return to gallery
- Fixed viewer layout so images stay centered and properly scaled
- Improved portrait image display in viewer mode

## What v0.1 does

- Receives image batches
- Saves images to a chosen directory
- Shows thumbnails inside the node UI
- Lets you clear the gallery
- Lets you resize thumbnails with a slider
- Click a thumbnail to enlarge it
- Click again to shrink it back
- Passes the input images through unchanged
- Automatically prunes oldest images when the gallery reaches the configured limit

## Install

1. Copy this folder into `ComfyUI/custom_nodes/`
2. Restart ComfyUI
3. Search for **Workflow Gallery** in the node menu under `image/ui`

## Inputs

- **images**: incoming image batch
- **enabled**: enable or bypass gallery collection
- **save_to_disk**: when enabled, writes originals to the chosen directory
- **output_directory**: target folder for saved images
- **filename_prefix**: filename prefix used for saved images
- **max_images**: maximum number of images retained by the gallery

## Notes

- If `save_to_disk` is disabled, the node still writes temporary originals into its package cache so the expand view can work.
- Clearing the gallery also deletes files tracked by the current node state.
- This release is intentionally small and focused.

## Recommended next improvements

- Add a folder picker if your target ComfyUI frontend version supports it cleanly
- Add pin/favorite support
- Add export selected / save selected
- Add captions or prompt metadata under thumbnails
- Add persistence restore from disk on startup

## Publishing on GitHub

1. Create a new GitHub repo
2. Upload these files
3. Replace the repository URL in `pyproject.toml`
4. Add screenshots or a demo GIF to the README
5. Tag a release like `v0.1.0`

## Suggested repo name

`ComfyUI-Workflow-Gallery`
