import io
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from aiohttp import web
from server import PromptServer
import folder_paths


GALLERY_STATE: Dict[str, Dict[str, Any]] = {}
ENTRY_INDEX: Dict[str, Dict[str, Any]] = {}
STATE_LOCK = threading.Lock()


PACKAGE_DIR = Path(__file__).resolve().parent
# Use ComfyUI's built-in folder_paths module — works for all install types
# (manual, portable, desktop app, etc.)
DEFAULT_SAVE_DIR = Path(folder_paths.get_output_directory()) / "workflow_gallery"
LEGACY_SAVE_DIR = PACKAGE_DIR / "gallery_output"
CACHE_BASE_DIR = DEFAULT_SAVE_DIR / "Workflow-Gallery"
DEFAULT_SAVE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_BASE_DIR.mkdir(parents=True, exist_ok=True)


ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

SESSION_DIR = CACHE_BASE_DIR / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

PROMPT_LIBRARY_FILE = CACHE_BASE_DIR / "prompt_library.json"
PROMPT_LIBRARY_LOCK = threading.Lock()


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
        "display_prompt": entry.get("display_prompt", entry.get("positive_prompt", "")),
        "prompt_source": entry.get("prompt_source", "unavailable"),
        "positive_prompt": entry.get("positive_prompt", ""),
        "negative_prompt": entry.get("negative_prompt", ""),
        "exported": entry.get("exported", False),
        "seed": entry.get("seed", None),
        "full_url": f"/workflow_gallery/file/{entry['id']}?kind=full",
        "thumb_url": f"/workflow_gallery/file/{entry['id']}?kind=thumb",
    }


def _get_ref_node_id(value: Any) -> str:
    if isinstance(value, (list, tuple)) and value:
        return str(value[0])
    if isinstance(value, (str, int)):
        return str(value)
    return ""


def _iter_child_node_ids(inputs: Dict[str, Any]) -> List[str]:
    child_ids: List[str] = []
    for child_value in inputs.values():
        child_node_id = _get_ref_node_id(child_value)
        if child_node_id:
            child_ids.append(child_node_id)
    return child_ids


def _is_sampler_node(node: Dict[str, Any]) -> bool:
    """Return True if this node looks like a KSampler or equivalent."""
    class_type = str(node.get("class_type", ""))
    inputs = node.get("inputs", {})
    if not isinstance(inputs, dict):
        inputs = {}
    has_sampler_links = (
        ("positive" in inputs)
        or ("negative" in inputs)
        or ("cond_pos" in inputs)
        or ("cond_neg" in inputs)
    )
    return class_type.startswith("KSampler") or has_sampler_links


def _find_relevant_sampler(prompt_graph: Dict[str, Any], gallery_node_id: str | None) -> Dict[str, Any] | None:
    if not gallery_node_id:
        return None

    gallery_node = prompt_graph.get(str(gallery_node_id))
    if not isinstance(gallery_node, dict):
        return None

    gallery_inputs = gallery_node.get("inputs", {})
    if not isinstance(gallery_inputs, dict):
        gallery_inputs = {}

    start_node_id = _get_ref_node_id(gallery_inputs.get("images"))
    if not start_node_id:
        return None

    # BFS upstream from the gallery's image input so we find the *closest*
    # sampler to this specific gallery node, not just any sampler in the graph.
    from collections import deque
    queue: deque[str] = deque([start_node_id])
    visited: set[str] = set()

    while queue:
        node_id = queue.popleft()
        if not node_id or node_id in visited:
            continue
        visited.add(node_id)

        node = prompt_graph.get(node_id)
        if not isinstance(node, dict):
            continue

        if _is_sampler_node(node):
            return node

        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            inputs = {}

        # Prefer latent/image inputs first so we stay on the image pipeline path
        preferred_input_order = ["samples", "latent", "latent_image", "images", "image"]
        ordered_children: List[str] = []
        for key in preferred_input_order:
            child_id = _get_ref_node_id(inputs.get(key))
            if child_id and child_id not in ordered_children:
                ordered_children.append(child_id)
        for child_id in _iter_child_node_ids(inputs):
            if child_id not in ordered_children:
                ordered_children.append(child_id)

        for child_node_id in ordered_children:
            if child_node_id not in visited:
                queue.append(child_node_id)

    return None

def _resolve_text_from_ref(prompt_graph: Dict[str, Any], value: Any, visited: set[str] | None = None) -> str:
    node_ref = ""
    if isinstance(value, (list, tuple)) and value:
        node_ref = str(value[0])
    elif isinstance(value, (str, int)):
        node_ref = str(value)

    if not node_ref:
        return ""

    if node_ref not in prompt_graph:
        return ""

    if visited is None:
        visited = set()
    if node_ref in visited:
        return ""
    current_visited = set(visited)
    current_visited.add(node_ref)

    node = prompt_graph.get(node_ref)
    if not isinstance(node, dict):
        return ""

    class_type = str(node.get("class_type", ""))
    inputs = node.get("inputs", {})
    if not isinstance(inputs, dict):
        inputs = {}

    # ZeroOut nodes intentionally nullify conditioning — stop walking here
    # so we don't trace back through them and bleed positive text into negative.
    if "ZeroOut" in class_type or "zero_out" in class_type.lower():
        return ""

    # PromptLibrary node — the selected_prompt_id widget stores the full
    # built output string directly (set by the JS UI).
    if class_type == "PromptLibrary":
        val = inputs.get("selected_prompt_id", "")
        if isinstance(val, str) and val.strip():
            return val.strip()
        return ""

    if "TextEncode" in class_type:
        text_field_keys = ["text", "prompt", "text_g", "text_l", "clip_l", "clip_g", "t5xxl", "t5xxl_text"]
        parts: List[str] = []
        for key in text_field_keys:
            field_value = inputs.get(key)
            if field_value is None:
                continue
            if isinstance(field_value, str) and field_value.strip():
                # Literal text directly in the field — use it as-is
                parts.append(field_value.strip())
            elif isinstance(field_value, (list, tuple)) and field_value:
                # It's a node reference — follow it upstream to resolve the string.
                # This handles wildcard nodes, string concatenators, primitive nodes, etc.
                resolved = _resolve_text_from_ref(prompt_graph, field_value, current_visited)
                if resolved:
                    parts.append(resolved)
        if parts:
            unique_parts = list(dict.fromkeys(parts))
            return "\n".join(unique_parts)
        # TextEncode node had no text — return empty rather than walking
        # non-text children (e.g. clip input) which can bleed positive text into negative.
        return ""

    # For non-TextEncode nodes (e.g. wildcard node, string node, primitive),
    # check common string output fields first before walking all children.
    string_field_keys = ["text", "string", "value", "prompt", "output", "result", "wildcard_text", "populated_text"]
    for key in string_field_keys:
        field_value = inputs.get(key)
        if isinstance(field_value, str) and field_value.strip():
            return field_value.strip()

    for child_value in inputs.values():
        text = _resolve_text_from_ref(prompt_graph, child_value, current_visited)
        if text:
            return text
    return ""


def _extract_prompts(prompt_graph: Any, gallery_node_id: str | None = None) -> tuple[str, str]:
    if not isinstance(prompt_graph, dict):
        return "", ""

    sampler = _find_relevant_sampler(prompt_graph, gallery_node_id)
    if sampler is not None:
        inputs = sampler.get("inputs", {})
        if not isinstance(inputs, dict):
            inputs = {}

        positive = _resolve_text_from_ref(prompt_graph, inputs.get("positive"))
        negative = _resolve_text_from_ref(prompt_graph, inputs.get("negative"))
        if not positive:
            positive = _resolve_text_from_ref(prompt_graph, inputs.get("cond_pos"))
        if not negative:
            negative = _resolve_text_from_ref(prompt_graph, inputs.get("cond_neg"))
        if positive:
            return positive, negative

    samplers: list[dict[str, Any]] = []
    for node_key, node in prompt_graph.items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", ""))
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            inputs = {}

        has_sampler_links = ("positive" in inputs) or ("negative" in inputs)
        if class_type.startswith("KSampler") or has_sampler_links:
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

    if not positive:
        positive = _resolve_text_from_ref(prompt_graph, inputs.get("cond_pos"))
    if not negative:
        negative = _resolve_text_from_ref(prompt_graph, inputs.get("cond_neg"))
    return positive, negative


def _extract_prompts_with_fallback(prompt_graph: Any, extra_pnginfo: Any, gallery_node_id: str | None = None) -> tuple[str, str, str]:
    # --- Primary: live workflow graph, walked from our specific gallery node ---
    positive, negative = _extract_prompts(prompt_graph, gallery_node_id)
    if positive:
        return positive, negative, "workflow graph"

    if not isinstance(extra_pnginfo, dict):
        return positive, negative, "unavailable"

    # --- Fallback 1: embedded prompt JSON (also scoped to gallery_node_id) ---
    embedded_prompt = extra_pnginfo.get("prompt")
    if embedded_prompt is not None:
        fallback_positive, fallback_negative = _extract_prompts(embedded_prompt, gallery_node_id)
        if fallback_positive:
            return fallback_positive, fallback_negative, "embedded prompt metadata"
        # If gallery_node_id scoped walk failed, try unscoped on embedded prompt
        # but only as a last resort before the stale workflow fallback.
        fallback_positive, fallback_negative = _extract_prompts(embedded_prompt, None)
        if fallback_positive:
            return fallback_positive, fallback_negative, "embedded prompt metadata"

    # --- Fallback 2: embedded workflow JSON (LiteGraph format) ---
    # Pass gallery_node_id so we resolve from the correct sampler, not just
    # the first sampler in the graph (which caused the "random prompt" bug).
    fallback_positive, fallback_negative = _extract_prompts_from_workflow(
        extra_pnginfo.get("workflow"), gallery_node_id
    )
    if fallback_positive:
        return fallback_positive, fallback_negative, "embedded workflow metadata"

    return positive, negative, "unavailable"


def _extract_seed(prompt_graph: Any, gallery_node_id: str | None = None) -> int | None:
    """Extract the seed from the sampler node connected to the gallery."""
    if not isinstance(prompt_graph, dict):
        return None

    sampler = _find_relevant_sampler(prompt_graph, gallery_node_id)
    if sampler is None:
        # Fall back to any sampler in the graph
        for node in prompt_graph.values():
            if isinstance(node, dict) and _is_sampler_node(node):
                sampler = node
                break

    if sampler is None:
        return None

    inputs = sampler.get("inputs", {})
    if not isinstance(inputs, dict):
        return None

    # Try common seed field names across different sampler types
    for key in ("seed", "noise_seed", "seed_num", "rand_seed"):
        val = inputs.get(key)
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)

    return None


def _extract_prompt_text_from_workflow_node(node: Dict[str, Any]) -> str:
    node_type = str(node.get("type", ""))
    if "TextEncode" not in node_type:
        return ""

    widgets = node.get("widgets_values")
    if not isinstance(widgets, list):
        return ""

    parts = [item.strip() for item in widgets if isinstance(item, str) and item.strip()]
    if not parts:
        return ""
    return "\n".join(list(dict.fromkeys(parts)))


def _extract_prompts_from_workflow(workflow: Any, gallery_node_id: str | None = None) -> tuple[str, str]:
    if not isinstance(workflow, dict):
        return "", ""

    nodes = workflow.get("nodes")
    links = workflow.get("links")
    if not isinstance(nodes, list) or not isinstance(links, list):
        return "", ""

    node_by_id: Dict[str, Dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if node_id is None:
            continue
        node_by_id[str(node_id)] = node

    link_to_from: Dict[int, str] = {}
    for link in links:
        if not isinstance(link, list) or len(link) < 2:
            continue
        link_id, from_node_id = link[0], link[1]
        if isinstance(link_id, int):
            link_to_from[link_id] = str(from_node_id)

    def resolve_from_node_id(node_id: str, visited: set[str]) -> str:
        if node_id in visited:
            return ""
        visited_next = set(visited)
        visited_next.add(node_id)

        node = node_by_id.get(node_id)
        if not isinstance(node, dict):
            return ""

        text = _extract_prompt_text_from_workflow_node(node)
        if text:
            return text

        inputs = node.get("inputs")
        if not isinstance(inputs, list):
            return ""

        for input_def in inputs:
            if not isinstance(input_def, dict):
                continue
            link_id = input_def.get("link")
            if not isinstance(link_id, int):
                continue
            upstream_id = link_to_from.get(link_id)
            if not upstream_id:
                continue
            text = resolve_from_node_id(upstream_id, visited_next)
            if text:
                return text
        return ""

    sampler_candidates: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, list):
            continue
        names = {str(item.get("name", "")).lower() for item in inputs if isinstance(item, dict)}
        if {"positive", "negative"}.intersection(names) or {"cond_pos", "cond_neg"}.intersection(names):
            sampler_candidates.append(node)

    # If we know which gallery node to scope to, find the sampler that feeds it
    # by walking upstream through the LiteGraph link map.
    if gallery_node_id and sampler_candidates:
        gallery_wf_node = node_by_id.get(str(gallery_node_id))
        if isinstance(gallery_wf_node, dict):
            gallery_inputs_list = gallery_wf_node.get("inputs")
            if isinstance(gallery_inputs_list, list):
                # Find the link id connected to the "images" input of the gallery node
                images_link_id = None
                for inp in gallery_inputs_list:
                    if isinstance(inp, dict) and str(inp.get("name", "")).lower() == "images":
                        images_link_id = inp.get("link")
                        break
                if isinstance(images_link_id, int):
                    # BFS upstream from gallery's image input to find closest sampler
                    from collections import deque as _deque
                    upstream_start = link_to_from.get(images_link_id)
                    if upstream_start:
                        bfs_queue: _deque[str] = _deque([upstream_start])
                        bfs_visited: set[str] = set()
                        sampler_candidate_ids = {str(n.get("id", "")) for n in sampler_candidates}
                        while bfs_queue:
                            cur_id = bfs_queue.popleft()
                            if not cur_id or cur_id in bfs_visited:
                                continue
                            bfs_visited.add(cur_id)
                            if cur_id in sampler_candidate_ids:
                                # Found the closest sampler upstream — use it exclusively
                                sampler_candidates = [n for n in sampler_candidates if str(n.get("id", "")) == cur_id]
                                break
                            cur_node = node_by_id.get(cur_id)
                            if not isinstance(cur_node, dict):
                                continue
                            cur_inputs = cur_node.get("inputs")
                            if isinstance(cur_inputs, list):
                                for inp in cur_inputs:
                                    if isinstance(inp, dict):
                                        lid = inp.get("link")
                                        if isinstance(lid, int):
                                            nxt = link_to_from.get(lid)
                                            if nxt and nxt not in bfs_visited:
                                                bfs_queue.append(nxt)

    def sort_key(node: Dict[str, Any]) -> tuple[int, str]:
        node_id = str(node.get("id", ""))
        return (0, node_id) if node_id.isdigit() else (1, node_id)

    for sampler in sorted(sampler_candidates, key=sort_key):
        inputs = sampler.get("inputs")
        if not isinstance(inputs, list):
            continue

        by_name = {str(item.get("name", "")).lower(): item for item in inputs if isinstance(item, dict)}

        def resolve_input(*names: str) -> str:
            for name in names:
                input_def = by_name.get(name)
                if not isinstance(input_def, dict):
                    continue
                link_id = input_def.get("link")
                if not isinstance(link_id, int):
                    continue
                upstream_id = link_to_from.get(link_id)
                if not upstream_id:
                    continue
                text = resolve_from_node_id(upstream_id, set())
                if text:
                    return text
            return ""

        positive = resolve_input("positive", "cond_pos")
        negative = resolve_input("negative", "cond_neg")
        if positive:
            return positive, negative

    return "", ""


def _build_pnginfo(prompt: Any, extra_pnginfo: Any) -> PngInfo:
    pnginfo = PngInfo()

    if prompt is not None:
        try:
            pnginfo.add_text("prompt", json.dumps(prompt, ensure_ascii=False))
        except Exception:
            pass

    if isinstance(extra_pnginfo, dict):
        for key, value in extra_pnginfo.items():
            try:
                pnginfo.add_text(str(key), json.dumps(value, ensure_ascii=False))
            except Exception:
                pass

    return pnginfo

def _gallery_payload(node_id: str) -> Dict[str, Any]:
    with STATE_LOCK:
        state = GALLERY_STATE.get(node_id, {})
        entries = [_entry_public(item) for item in state.get("entries", [])]
        return {
            "node_id": node_id,
            "count": len(entries),
            "max_images": state.get("max_images", 100),
            "output_directory": state.get("output_directory", str(DEFAULT_SAVE_DIR)),
            "save_to_disk": state.get("save_to_disk", False),
            "entries": entries,
        }


def _send_gallery_update(node_id: str) -> None:
    _save_session(node_id)
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
        # Fast path — normal operation
        entry = ENTRY_INDEX.get(entry_id)
        if entry:
            return entry
        # Fallback: scan all gallery states (handles session restore edge cases
        # where ENTRY_INDEX may not have been fully rebuilt). Repairs the index
        # on the fly so subsequent lookups are fast.
        for state in GALLERY_STATE.values():
            for e in state.get("entries", []):
                if e.get("id") == entry_id:
                    ENTRY_INDEX[entry_id] = e
                    return e
        return None


def _session_path(node_id: str) -> Path:
    safe_id = "".join(ch for ch in str(node_id) if ch.isalnum() or ch in ("-", "_"))
    return SESSION_DIR / f"session_{safe_id}.json"


def _save_session(node_id: str) -> None:
    try:
        with STATE_LOCK:
            state = GALLERY_STATE.get(str(node_id))
            if not state:
                return
            data = {
                "node_id": str(node_id),
                "max_images": state.get("max_images", 48),
                "output_directory": state.get("output_directory", str(DEFAULT_SAVE_DIR)),
                "save_to_disk": state.get("save_to_disk", False),
                "entries": list(state.get("entries", [])),
            }
        path = _session_path(node_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)
    except Exception as e:
        print(f"[WorkflowGallery] Warning: could not save session for node {node_id}: {e}", flush=True)


def _load_all_sessions() -> None:
    if not SESSION_DIR.exists():
        print("[WorkflowGallery] Session directory not found.", flush=True)
        return

    session_files = list(SESSION_DIR.glob("session_*.json"))
    if not session_files:
        return

    print(f"[WorkflowGallery] Found {len(session_files)} session file(s), restoring...", flush=True)

    for session_file in session_files:
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            node_id = str(data.get("node_id", ""))
            if not node_id:
                continue

            raw_entries: List[Dict[str, Any]] = data.get("entries", [])
            valid_entries: List[Dict[str, Any]] = []
            for entry in raw_entries:
                full_path = entry.get("full_path", "")
                thumb_path = entry.get("thumb_path", "")
                # Use os.path.exists for reliable Windows path checking
                if not full_path or not os.path.exists(full_path):
                    print(f"[WorkflowGallery] Skipping {entry.get('id','?')}: full image missing at {full_path!r}", flush=True)
                    continue
                if not thumb_path or not os.path.exists(thumb_path):
                    print(f"[WorkflowGallery] Skipping {entry.get('id','?')}: thumbnail missing at {thumb_path!r}", flush=True)
                    continue
                valid_entries.append(entry)

            if not valid_entries:
                print(f"[WorkflowGallery] No valid entries in {session_file.name}, removing.", flush=True)
                session_file.unlink(missing_ok=True)
                continue

            with STATE_LOCK:
                state = GALLERY_STATE.setdefault(node_id, {
                    "entries": [],
                    "max_images": data.get("max_images", 48),
                    "output_directory": data.get("output_directory", str(DEFAULT_SAVE_DIR)),
                    "save_to_disk": data.get("save_to_disk", False),
                })
                state["entries"] = valid_entries
                state["max_images"] = data.get("max_images", 48)
                state["output_directory"] = data.get("output_directory", str(DEFAULT_SAVE_DIR))
                state["save_to_disk"] = data.get("save_to_disk", False)
                for entry in valid_entries:
                    ENTRY_INDEX[entry["id"]] = entry

            print(f"[WorkflowGallery] Restored {len(valid_entries)} image(s) for node {node_id}", flush=True)

        except Exception as e:
            import traceback
            print(f"[WorkflowGallery] ERROR loading {session_file.name}: {e}", flush=True)
            traceback.print_exc()


_load_all_sessions()


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
                "save_to_disk": ("BOOLEAN", {"default": False}),
                "output_directory": ("STRING", {"default": str(DEFAULT_SAVE_DIR), "multiline": False}),
                "filename_prefix": ("STRING", {"default": "workflow_gallery", "multiline": False}),
                "max_images": ("INT", {"default": 48, "min": 1, "max": 500, "step": 1}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    def collect(
        self,
        images,
        enabled: bool = True,
        save_to_disk: bool = False,
        output_directory: str = str(DEFAULT_SAVE_DIR),
        filename_prefix: str = "workflow_gallery",
        max_images: int = 48,
        unique_id: str | None = None,
        prompt: Dict[str, Any] | None = None,
        extra_pnginfo: Dict[str, Any] | None = None,
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
        positive_prompt, negative_prompt, prompt_source = _extract_prompts_with_fallback(prompt, extra_pnginfo, node_id)
        display_prompt = positive_prompt
        seed = _extract_seed(prompt, node_id)
        pnginfo = _build_pnginfo(prompt, extra_pnginfo)

        new_entries: List[Dict[str, Any]] = []
        for idx, image_tensor in enumerate(images):
            pil_image = _tensor_to_pil(image_tensor)
            width, height = pil_image.size
            entry_id = uuid.uuid4().hex
            filename = f"{safe_prefix}_{timestamp}_{idx:03d}_{entry_id[:8]}.png"
            full_path = resolved_output_dir / filename

            if save_to_disk:
                pil_image.save(full_path, format="PNG", compress_level=4, pnginfo=pnginfo)
            else:
                # Still save to a temp-ish package folder so the frontend can display original-size images.
                temp_dir = CACHE_BASE_DIR / "unsaved_cache"
                temp_dir.mkdir(parents=True, exist_ok=True)
                full_path = temp_dir / filename
                pil_image.save(full_path, format="PNG", compress_level=4, pnginfo=pnginfo)

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
                    "display_prompt": display_prompt,
                    "prompt_source": prompt_source,
                    "positive_prompt": positive_prompt,
                    "negative_prompt": negative_prompt,
                    "seed": seed,
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
        state = GALLERY_STATE.setdefault(node_id, {"entries": [], "max_images": 100, "output_directory": str(DEFAULT_SAVE_DIR), "save_to_disk": False})
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
    try:
        _session_path(node_id).unlink(missing_ok=True)
    except Exception:
        pass
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
    if not path.exists():
        print(f"[WorkflowGallery] File missing: {path}", flush=True)
        return web.Response(status=404, text="File missing")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return web.Response(status=404, text="File type not allowed")

    content_type_map = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    content_type = content_type_map.get(path.suffix.lower(), "application/octet-stream")
    try:
        data = path.read_bytes()
        return web.Response(
            body=data,
            content_type=content_type,
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        print(f"[WorkflowGallery] Error reading file {path}: {e}", flush=True)
        return web.Response(status=500, text="Error reading file")


@routes.post("/workflow_gallery/export")
async def workflow_gallery_export(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    node_id = str(body.get("node_id", ""))
    entry_ids: List[str] = body.get("entry_ids", [])
    output_directory = str(body.get("output_directory", "")).strip()

    if not entry_ids:
        return web.json_response({"ok": False, "error": "No entry IDs provided"}, status=400)

    # Resolve destination — use the node's configured output dir or fall back to default
    dest_dir = _resolve_output_dir(output_directory) if output_directory else DEFAULT_SAVE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    exported: List[str] = []
    errors: List[str] = []

    for entry_id in entry_ids:
        entry = _find_entry(entry_id)
        if not entry:
            errors.append(f"{entry_id}: not found")
            continue

        src_path = Path(entry.get("full_path", ""))
        if not src_path.exists():
            errors.append(f"{entry_id}: source file missing")
            continue

        dest_path = dest_dir / src_path.name
        # Avoid overwriting — append a suffix if needed
        counter = 1
        while dest_path.exists():
            dest_path = dest_dir / f"{src_path.stem}_{counter}{src_path.suffix}"
            counter += 1

        try:
            import shutil
            shutil.copy2(str(src_path), str(dest_path))
            # Mark entry as exported in state
            with STATE_LOCK:
                entry["exported"] = True
                entry["exported_path"] = str(dest_path)
            exported.append(entry_id)
        except Exception as e:
            errors.append(f"{entry_id}: {e}")

    if node_id:
        _send_gallery_update(node_id)

    return web.json_response({
        "ok": True,
        "exported": exported,
        "errors": errors,
        "dest_directory": str(dest_dir),
    })


@routes.post("/workflow_gallery/clear_unexported/{node_id}")
async def workflow_gallery_clear_unexported(request):
    node_id = request.match_info["node_id"]
    with STATE_LOCK:
        state = GALLERY_STATE.get(node_id)
        if not state:
            return web.json_response({"ok": True, "removed": 0})

        to_remove = [e for e in state.get("entries", []) if not e.get("exported", False)]
        state["entries"] = [e for e in state.get("entries", []) if e.get("exported", False)]
        for entry in to_remove:
            ENTRY_INDEX.pop(entry.get("id", ""), None)

    # Clean up files for removed entries
    for entry in to_remove:
        for key in ("thumb_path",):
            path = entry.get(key)
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
        # Only delete full_path if it's in the cache (not a user-configured save dir)
        full_path = entry.get("full_path", "")
        if full_path and str(CACHE_BASE_DIR) in full_path:
            try:
                Path(full_path).unlink(missing_ok=True)
            except Exception:
                pass

    _send_gallery_update(node_id)
    return web.json_response({"ok": True, "removed": len(to_remove)})


def _load_prompt_library() -> List[Dict[str, Any]]:
    try:
        if PROMPT_LIBRARY_FILE.exists():
            return json.loads(PROMPT_LIBRARY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[PromptLibrary] Error loading library: {e}", flush=True)
    return []


def _save_prompt_library(entries: List[Dict[str, Any]]) -> None:
    try:
        tmp = PROMPT_LIBRARY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(PROMPT_LIBRARY_FILE)
    except Exception as e:
        print(f"[PromptLibrary] Error saving library: {e}", flush=True)


class PromptLibrary:
    CATEGORY = "utils/prompt"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "get_prompt"
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # This widget stores the full built prompt string set by the JS UI
                "selected_prompt_id": ("STRING", {"default": "", "multiline": False}),
            },
        }

    def get_prompt(self, selected_prompt_id: str = ""):
        # The JS stores the full built output (selected + manual) directly in this widget
        return (selected_prompt_id,)


@routes.get("/prompt_library/list")
async def prompt_library_list(request):
    with PROMPT_LIBRARY_LOCK:
        entries = _load_prompt_library()
    return web.json_response({"entries": entries})


@routes.post("/prompt_library/save")
async def prompt_library_save(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    name = str(body.get("name", "")).strip()
    positive_prompt = str(body.get("positive_prompt", "")).strip()
    negative_prompt = str(body.get("negative_prompt", "")).strip()
    tags = [str(t).strip() for t in body.get("tags", []) if str(t).strip()]

    if not name:
        return web.json_response({"ok": False, "error": "Name is required"}, status=400)
    if not positive_prompt:
        return web.json_response({"ok": False, "error": "Prompt is required"}, status=400)

    with PROMPT_LIBRARY_LOCK:
        entries = _load_prompt_library()
        for entry in entries:
            if entry.get("positive_prompt", "").strip() == positive_prompt:
                return web.json_response({"ok": False, "error": "Prompt already exists", "id": entry["id"]}, status=409)
        new_entry = {
            "id": uuid.uuid4().hex,
            "name": name,
            "positive_prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            "tags": tags,
            "created": int(time.time()),
        }
        entries.append(new_entry)
        _save_prompt_library(entries)

    return web.json_response({"ok": True, "entry": new_entry})


@routes.post("/prompt_library/delete")
async def prompt_library_delete(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    entry_id = str(body.get("id", "")).strip()
    if not entry_id:
        return web.json_response({"ok": False, "error": "ID required"}, status=400)

    with PROMPT_LIBRARY_LOCK:
        entries = _load_prompt_library()
        new_entries = [e for e in entries if e.get("id") != entry_id]
        if len(new_entries) == len(entries):
            return web.json_response({"ok": False, "error": "Not found"}, status=404)
        _save_prompt_library(new_entries)

    return web.json_response({"ok": True})


@routes.post("/prompt_library/update")
async def prompt_library_update(request):
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON"}, status=400)

    entry_id = str(body.get("id", "")).strip()
    if not entry_id:
        return web.json_response({"ok": False, "error": "ID required"}, status=400)

    with PROMPT_LIBRARY_LOCK:
        entries = _load_prompt_library()
        for entry in entries:
            if entry.get("id") == entry_id:
                if "name" in body: entry["name"] = str(body["name"]).strip()
                if "tags" in body: entry["tags"] = [str(t).strip() for t in body["tags"] if str(t).strip()]
                if "positive_prompt" in body: entry["positive_prompt"] = str(body["positive_prompt"]).strip()
                if "negative_prompt" in body: entry["negative_prompt"] = str(body["negative_prompt"]).strip()
                _save_prompt_library(entries)
                return web.json_response({"ok": True, "entry": entry})

    return web.json_response({"ok": False, "error": "Not found"}, status=404)


@routes.get("/prompt_library/export")
async def prompt_library_export(request):
    fmt = request.query.get("format", "json")
    with PROMPT_LIBRARY_LOCK:
        entries = _load_prompt_library()

    if fmt == "csv":
        import csv
        import io as _io
        buf = _io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["id", "name", "tags", "positive_prompt", "negative_prompt", "created"])
        writer.writeheader()
        for e in entries:
            writer.writerow({
                "id": e.get("id", ""),
                "name": e.get("name", ""),
                "tags": ",".join(e.get("tags", [])),
                "positive_prompt": e.get("positive_prompt", ""),
                "negative_prompt": e.get("negative_prompt", ""),
                "created": e.get("created", ""),
            })
        return web.Response(
            body=buf.getvalue().encode("utf-8"),
            content_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=prompt_library.csv"}
        )
    else:
        return web.Response(
            body=json.dumps(entries, ensure_ascii=False, indent=2).encode("utf-8"),
            content_type="application/json",
            headers={"Content-Disposition": "attachment; filename=prompt_library.json"}
        )


NODE_CLASS_MAPPINGS = {
    "WorkflowGallery": WorkflowGallery,
    "PromptLibrary": PromptLibrary,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WorkflowGallery": "Workflow Gallery",
    "PromptLibrary": "Prompt Library",
}
