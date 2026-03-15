# ComfyUI-Workflow-Gallery

Workflow Gallery is a custom ComfyUI node that collects images passing through it and displays them inside a scrollable gallery directly on the node. Review, compare, and export your generations without ever leaving ComfyUI.

## Version

Current release: **v0.1.16**

## Why I made this

I wanted a cleaner way to review multiple generated images inside a workflow without digging through output folders every time.

A practical use case is generating multiple showcase images for wildcard packs, LoRAs, prompt packs, or Civitai posts. Instead of hunting through saved files, this node lets you review, compare, and selectively export results directly inside ComfyUI.

## Features

### Gallery
- Receives image batches and displays them as thumbnails inside the node
- Hover over any thumbnail to see the positive and negative prompt used to generate it
- Resize thumbnails with the slider at the bottom
- Thumbnails show newest images first
- Automatically prunes oldest images when the gallery reaches the configured limit
- Passes input images through unchanged so it works anywhere in your pipeline

### Viewer
- Click any thumbnail to expand it in full viewer mode
- Full prompt (positive and negative) displayed below the expanded image
- Copy prompt button for quick clipboard access
- Navigate between images with left and right arrow buttons
- Click the expanded image to return to the gallery

### Image Comparison
- Shift-click two thumbnails to select them (highlighted in orange)
- Click the **⇔ Compare** button that appears in the toolbar
- Side-by-side viewer opens with a draggable divider between the two images
- Drag the divider left and right to reveal more of either image
- Each side shows its own prompt below the image
- Compare stage automatically resizes when you resize the node
- Click **✕ Exit compare** to return to the gallery

### Export & Selection
- Shift-click any number of thumbnails to select them
- **↓ Export Selected** button appears when one or more images are selected
- Exported images are copied to your configured output folder
- A green **✓ badge** appears on exported thumbnails so you always know what's been saved
- **Clear Unexported** removes all non-exported images from the cache (with confirmation)
- **Clear All** removes everything including exported images (with confirmation)

### Cache-first workflow
- By default, images are stored in a local cache — nothing is permanently saved until you export
- Turn on **Save to Disk** if you want every image automatically saved as it generates
- Default export path is `ComfyUI/output/workflow_gallery/` — customizable in the node settings
- Uses ComfyUI's universal `folder_paths` API so the correct output directory is detected automatically across all install types (manual, portable, desktop app)

### Prompt Resolution
- Prompts are resolved directly from the live workflow graph, scoped to the sampler connected to your gallery node
- Supports wildcard nodes, string nodes, primitive nodes, and any other upstream text-feeding nodes — not just literal text typed into a CLIPTextEncode
- Works correctly in workflows with multiple samplers

## Installation

### Option 1 — ComfyUI Manager (recommended)
Search for **Workflow Gallery** in ComfyUI Manager and install directly.

### Option 2 — Manual
1. Copy this folder into `ComfyUI/custom_nodes/`
2. Restart ComfyUI
3. Search for **Workflow Gallery** in the node menu under `image/ui`

```text
ComfyUI/
└── custom_nodes/
    └── ComfyUI-Workflow-Gallery/
```

## Node Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| images | IMAGE | — | Image batch to collect and display |
| enabled | BOOLEAN | true | Pass-through toggle — disable to bypass the gallery |
| save_to_disk | BOOLEAN | false | Save every image to disk as it generates |
| output_directory | STRING | output/workflow_gallery | Where exported images are saved |
| filename_prefix | STRING | workflow_gallery | Prefix used for saved filenames |
| max_images | INT | 48 | Maximum number of images to keep in the gallery |

## How to use

### Basic review workflow
1. Place the **Workflow Gallery** node between your sampler and any Save Image node
2. Connect your image output to the `images` input
3. Queue your generation — images will appear in the gallery as they complete
4. Click any thumbnail to expand it and read the prompt

### Selective export workflow
1. Leave **Save to Disk** off (default)
2. Generate a batch of images
3. Shift-click the ones you want to keep
4. Click **↓ Export Selected** — they're copied to your output folder with a ✓ badge
5. Click **Clear Unexported** to clean up the rest

### Comparison workflow
1. Shift-click exactly two thumbnails
2. Click **⇔ Compare**
3. Drag the divider to compare the images side by side

## Screenshots

### Workflow Example
![Workflow Example](screenshots/workflow.png)

### Gallery View
![Gallery View](screenshots/Screenshot%202026-03-08%20000942.png)

### Viewer Mode
![Viewer Mode](screenshots/Screenshot%202026-03-08%20014404.png)
