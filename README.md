# ComfyUI-Workflow-Gallery

A suite of ComfyUI custom nodes for reviewing, comparing, exporting, and reusing generated images and prompts — all without leaving ComfyUI.

## Version

Current release: **v0.1.16**

## Why I made this

I wanted a cleaner way to review multiple generated images inside a workflow without digging through output folders every time.

A practical use case is generating multiple showcase images for wildcard packs, LoRAs, prompt packs, or Civitai posts. Instead of hunting through saved files, these nodes let you review, compare, selectively export, and reuse prompts directly inside ComfyUI.

## Nodes

This package includes two nodes:

- **Workflow Gallery** — image gallery, viewer, comparison, and export (`image/ui`)
- **Prompt Library** — save, search, and reuse prompts across workflows (`utils/prompt`)

---

## Workflow Gallery

### Gallery
- Receives image batches and displays them as thumbnails inside the node
- Hover over any thumbnail to see the positive and negative prompt used to generate it
- Seed is shown on hover and in the viewer
- Resize thumbnails with the slider at the bottom
- Thumbnails show newest images first
- Automatically prunes oldest images when the gallery reaches the configured limit
- Passes input images through unchanged so it works anywhere in your pipeline
- Gallery state persists across ComfyUI restarts — your images are right where you left them

### Viewer
- Click any thumbnail to expand it in full viewer mode
- Seed, positive, and negative prompts displayed in labeled sections
- Inline **Copy** button next to each section for quick clipboard access
- **Save Prompt** button on the positive prompt section — saves directly to your Prompt Library with a custom name and optional tags
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
- Supports wildcard nodes, string nodes, primitive nodes, Prompt Library nodes, and any other upstream text-feeding nodes
- Handles `ConditioningZeroOut` correctly — no bleed from positive to negative
- Works correctly in workflows with multiple samplers

### Node Inputs

| Input | Type | Default | Description |
|---|---|---|---|
| images | IMAGE | — | Image batch to collect and display |
| enabled | BOOLEAN | true | Pass-through toggle — disable to bypass the gallery |
| save_to_disk | BOOLEAN | false | Save every image to disk as it generates |
| output_directory | STRING | output/workflow_gallery | Where exported images are saved |
| filename_prefix | STRING | workflow_gallery | Prefix used for saved filenames |
| max_images | INT | 48 | Maximum number of images to keep in the gallery |

---

## Prompt Library

A persistent prompt manager that lives directly in your workflow. Save, search, tag, and reuse prompts — and connect them directly to your CLIPTextEncode nodes.

### Features
- Outputs a `STRING` that connects directly to any CLIPTextEncode `text` input
- Search prompts by text or filter by tags
- Add manual text that combines with your selected prompt — insert before or after
- **💾 Save Current** — saves the manual text area content to the library
- **Save Prompt** button in the Workflow Gallery viewer saves any image's prompt directly to the library
- Edit saved prompts inline — update name, tags, and text
- Delete prompts with confirmation
- Second click on a selected prompt deselects it
- Export your entire library as **JSON** or **CSV**
- Library persists across restarts

### How to use
1. Add the **Prompt Library** node to your workflow
2. Connect its `prompt` output to a CLIPTextEncode `text` input
3. Select a saved prompt from the list — it becomes the output string immediately
4. Optionally type additional text in the manual input and choose whether it goes before or after the selected prompt
5. Save new prompts using **+ Add**, **💾 Save Current**, or the **Save Prompt** button in the Workflow Gallery viewer

---

## Installation

### Option 1 — ComfyUI Manager (recommended)
Search for **Workflow Gallery** in ComfyUI Manager and install directly.

### Option 2 — Manual
1. Copy this folder into `ComfyUI/custom_nodes/`
2. Restart ComfyUI
3. Find **Workflow Gallery** under `image/ui` and **Prompt Library** under `utils/prompt`

```text
ComfyUI/
└── custom_nodes/
    └── ComfyUI-Workflow-Gallery/
        ├── nodes.py
        ├── js/
        │   ├── workflow_gallery.js
        │   └── prompt_library.js
        └── ...
```

---

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

### Prompt Library workflow
1. Add the Prompt Library node and connect it to your CLIPTextEncode
2. Generate images — click any thumbnail to expand it in the gallery viewer
3. Click **Save Prompt** on the positive prompt section to save it with a name and tags
4. The saved prompt appears in your Prompt Library node immediately after clicking Refresh
5. Select it from the list — it feeds directly into your encoder on the next generation

---

## Screenshots

### Workflow Example
![Workflow Example](screenshots/workflow.png)

### Gallery View
![Gallery View](screenshots/Screenshot%202026-03-08%20000942.png)

### Viewer Mode
![Viewer Mode](screenshots/Screenshot%202026-03-08%20014404.png)
