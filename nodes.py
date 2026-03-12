import io
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image
from aiohttp import web
from server import PromptServer


GALLERY_STATE: Dict[str, Dict[str, Any]] = {}
ENTRY_INDEX: Dict[str, Dict[str, Any]] = {}
STATE_LOCK = threading.Lock()


PACKAGE_DIR = Path(__file__).resolve().parent
COMFY_ROOT_DIR = PACKAGE_DIR.parents[2] if len(PACKAGE_DIR.parents) >= 3 else PACKAGE_DIR
DEFAULT_SAVE_DIR = COMFY_ROOT_DIR / "output"
LEGACY_SAVE_DIR = PACKAGE_DIR / "gallery_output"
CACHE_BASE_DIR = DEFAULT_SAVE_DIR / "Workflow-Gallery"
DEFAULT_SAVE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_BASE_DIR.mkdir(parents=True, exist_ok=True)


ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _safe_int(value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(value)
    except Exception:
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result



def _sanitize_prefix(prefix: str) -> str:
    cleaned = "".join(ch for ch in prefix if ch.isalnum() or ch in ("-", "_"))
    return cleaned[:80] or "workflow_gallery"


def _resolve_output_dir(raw_path: str) -> Path:
    raw_path = (raw_path or "").strip()
    if not raw_path:
        return DEFAULT_SAVE_DIR
    expanded = Path(os.path.expandvars(os.path.expanduser(raw_path)))
    return expanded if expanded.is_absolute() else (PACKAGE_DIR / expanded).resolve()


def _normalize_output_dir(raw_path: str) -> Path:
    resolved = _resolve_output_dir(raw_path).resolve()
    legacy = LEGACY_SAVE_DIR.resolve()
    if os.path.normcase(str(resolved)) == os.path.normcase(str(legacy)):
        return DEFAULT_SAVE_DIR
    return resolved


def _tensor_to_pil(image_tensor) -> Image.Image:
    arr = image_tensor.cpu().numpy()
    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _thumbnail_bytes(image: Image.Image, max_size: int = 256) -> bytes:
    thumb = image.copy()
    thumb.thumbnail((max_size, max_size), Image.LANCZOS)
    buffer = io.BytesIO()
    thumb.save(buffer, format="WEBP", quality=85, method=6)
    return buffer.getvalue()


def _entry_public(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": entry["id"],
        "filename": entry["filename"],
        "created": entry["created"],
        "width": entry["width"],
        "height": entry["height"],
        "positive_prompt": entry.get("positive_prompt", ""),
        "negative_prompt": entry.get("negative_prompt", ""),
        "full_url": f"/workflow_gallery/file/{entry['id']}?kind=full",
        "thumb_url": f"/workflow_gallery/file/{entry['id']}?kind=thumb",
    }


def _resolve_text_from_ref(prompt_graph: Dict[str, Any], value: Any, visited: set[str] | None = None) -> str:
    if isinstance(value, str):
        return value.strip()

    if not isinstance(value, (list, tuple)) or not value:
        return ""

    node_ref = str(value[0])
    if visited is None:
        visited = set()
    if node_ref in visited:
        return ""
    visited.add(node_ref)

    node = prompt_graph.get(node_ref)
    if not isinstance(node, dict):
        return ""

    class_type = str(node.get("class_type", ""))
    inputs = node.get("inputs", {})
    if not isinstance(inputs, dict):
        inputs = {}

    if class_type.startswith("CLIPTextEncode"):
        text = inputs.get("text")
        return text.strip() if isinstance(text, str) else ""

    for child_value in inputs.values():
        text = _resolve_text_from_ref(prompt_graph, child_value, visited)
        if text:
            return text
    return ""


def _extract_prompts(prompt_graph: Any) -> tuple[str, str]:
    if not isinstance(prompt_graph, dict):
        return "", ""

    samplers: list[dict[str, Any]] = []
    for node_key, node in prompt_graph.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", ""))
        if class_type.startswith("KSampler"):
            samplers.append({"key": str(node_key), "node": node})

    if not samplers:
        return "", ""

    def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
        key = item["key"]
        return (0, key) if key.isdigit() else (1, key)

    sampler = sorted(samplers, key=_sort_key)[0]["node"]
    inputs = sampler.get("inputs", {})
    if not isinstance(inputs, dict):
        return "", ""

    positive = _resolve_text_from_ref(prompt_graph, inputs.get("positive"))
    negative = _resolve_text_from_ref(prompt_graph, inputs.get("negative"))
    return positive, negative


def _gallery_payload(node_id: str) -> Dict[str, Any]:
    with STATE_LOCK:
        state = GALLERY_STATE.get(node_id, {})
        entries = [_entry_public(item) for item in state.get("entries", [])]
        return {
            "node_id": node_id,
            "count": len(entries),
            "max_images": state.get("max_images", 100),
            "output_directory": state.get("output_directory", str(DEFAULT_SAVE_DIR)),
            "save_to_disk": state.get("save_to_disk", True),
            "entries": entries,
        }


def _send_gallery_update(node_id: str) -> None:
    PromptServer.instance.send_sync("workflow_gallery_update", _gallery_payload(node_id))


def _ensure_state(node_id: str, output_directory: str, max_images: int, save_to_disk: bool) -> Dict[str, Any]:
    with STATE_LOCK:
        state = GALLERY_STATE.setdefault(
            str(node_id),
            {
                "entries": [],
                "max_images": max_images,
                "output_directory": output_directory,
                "save_to_disk": save_to_disk,
            },
        )
        state["max_images"] = max_images
        state["output_directory"] = output_directory
        state["save_to_disk"] = save_to_disk
        return state


def _prune_entries(node_id: str, state: Dict[str, Any], max_images: int) -> None:
    removed: List[Dict[str, Any]] = []
    while len(state["entries"]) > max_images:
        removed.append(state["entries"].pop(0))

    for entry in removed:
        ENTRY_INDEX.pop(entry.get("id", ""), None)
        for key in ("full_path", "thumb_path"):
            try:
                if entry.get(key):
                    Path(entry[key]).unlink(missing_ok=True)
            except Exception:
                pass


def _find_entry(entry_id: str) -> Dict[str, Any] | None:
    with STATE_LOCK:
        return ENTRY_INDEX.get(entry_id)


class WorkflowGallery:
    CATEGORY = "image/ui"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "collect"
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "enabled": ("BOOLEAN", {"default": True}),
                "save_to_disk": ("BOOLEAN", {"default": True}),
                "output_directory": ("STRING", {"default": str(DEFAULT_SAVE_DIR), "multiline": False}),
                "filename_prefix": ("STRING", {"default": "workflow_gallery", "multiline": False}),
                "max_images": ("INT", {"default": 48, "min": 1, "max": 500, "step": 1}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "prompt": "PROMPT",
            },
        }

    def collect(
        self,
        images,
        enabled: bool = True,
        save_to_disk: bool = True,
        output_directory: str = str(DEFAULT_SAVE_DIR),
        filename_prefix: str = "workflow_gallery",
        max_images: int = 48,
        unique_id: str | None = None,
        prompt: Dict[str, Any] | None = None,
    ):
        node_id = str(unique_id or "unknown")
        max_images = _safe_int(max_images, 48, 1, 500)
        resolved_output_dir = _normalize_output_dir(output_directory)
        resolved_output_dir.mkdir(parents=True, exist_ok=True)

        state = _ensure_state(node_id, str(resolved_output_dir), max_images, bool(save_to_disk))

        if not enabled:
            _send_gallery_update(node_id)
            return (images,)

        safe_prefix = _sanitize_prefix(filename_prefix)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        positive_prompt, negative_prompt = _extract_prompts(prompt)

        new_entries: List[Dict[str, Any]] = []
        for idx, image_tensor in enumerate(images):
            pil_image = _tensor_to_pil(image_tensor)
            width, height = pil_image.size
            entry_id = uuid.uuid4().hex
            filename = f"{safe_prefix}_{timestamp}_{idx:03d}_{entry_id[:8]}.png"
            full_path = resolved_output_dir / filename

            if save_to_disk:
                pil_image.save(full_path, format="PNG", compress_level=4)
            else:
                # Still save to a temp-ish package folder so the frontend can display original-size images.
                temp_dir = CACHE_BASE_DIR / "unsaved_cache"
                temp_dir.mkdir(parents=True, exist_ok=True)
                full_path = temp_dir / filename
                pil_image.save(full_path, format="PNG", compress_level=4)

            thumb_path = CACHE_BASE_DIR / "thumb_cache" / f"{entry_id}.webp"
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            thumb_path.write_bytes(_thumbnail_bytes(pil_image))

            new_entries.append(
                {
                    "id": entry_id,
                    "filename": filename,
                    "created": int(time.time()),
                    "width": width,
                    "height": height,
                    "positive_prompt": positive_prompt,
                    "negative_prompt": negative_prompt,
                    "full_path": str(full_path),
                    "thumb_path": str(thumb_path),
                }
            )

        with STATE_LOCK:
            state["entries"].extend(new_entries)
            for entry in new_entries:
                ENTRY_INDEX[entry["id"]] = entry
            _prune_entries(node_id, state, max_images)

        _send_gallery_update(node_id)
        return (images,)


routes = PromptServer.instance.routes


@routes.get("/workflow_gallery/state/{node_id}")
async def workflow_gallery_state(request):
    node_id = request.match_info["node_id"]
    return web.json_response(_gallery_payload(node_id))


@routes.post("/workflow_gallery/clear/{node_id}")
async def workflow_gallery_clear(request):
    node_id = request.match_info["node_id"]
    with STATE_LOCK:
        state = GALLERY_STATE.setdefault(node_id, {"entries": [], "max_images": 100, "output_directory": str(DEFAULT_SAVE_DIR), "save_to_disk": True})
        entries = list(state.get("entries", []))
        state["entries"] = []
        for entry in entries:
            ENTRY_INDEX.pop(entry.get("id", ""), None)

    for entry in entries:
        for key in ("full_path", "thumb_path"):
            path = entry.get(key)
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass

    _send_gallery_update(node_id)
    return web.json_response({"ok": True})


@routes.get("/workflow_gallery/file/{entry_id}")
async def workflow_gallery_file(request):
    entry_id = request.match_info["entry_id"]
    kind = request.query.get("kind", "thumb")
    entry = _find_entry(entry_id)
    if not entry:
        return web.Response(status=404, text="Not found")

    path_key = "thumb_path" if kind == "thumb" else "full_path"
    path = Path(entry[path_key])
    if not path.exists() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return web.Response(status=404, text="File missing")

    content_type_map = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    content_type = content_type_map.get(path.suffix.lower(), "application/octet-stream")
    response = web.FileResponse(path, headers={"Cache-Control": "no-store"})
    response.content_type = content_type
    return response


NODE_CLASS_MAPPINGS = {
    "WorkflowGallery": WorkflowGallery,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WorkflowGallery": "Workflow Gallery",
}
