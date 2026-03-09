import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const EXTENSION_NAME = "comfyui.workflow.gallery";
const TARGET_CLASS = "WorkflowGallery";
const GALLERY_HEIGHT = 680;

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "style") Object.assign(node.style, value);
    else if (key === "className") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function ensureStyles() {
  if (document.getElementById("workflow-gallery-styles")) return;
  const style = document.createElement("style");
  style.id = "workflow-gallery-styles";
  style.textContent = `
    .wg-root { display:flex; flex-direction:column; gap:8px; padding:8px; box-sizing:border-box; height:100%; min-height:${GALLERY_HEIGHT}px; }
    .wg-topbar { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
    .wg-topbar button { cursor:pointer; }
    .wg-count { margin-left:auto; opacity:0.85; font-size:12px; }
    .wg-preview { flex:1 1 auto; min-height:520px; overflow:hidden; border:1px solid rgba(255,255,255,0.15); border-radius:8px; padding:8px; background:rgba(0,0,0,0.2); display:flex; flex-direction:column; position:relative; }
    .wg-preview.hidden { display:none; }
    .wg-preview-stage { flex:1 1 auto; min-height:0; display:flex; align-items:stretch; gap:8px; }
    .wg-preview-lane { flex:0 0 48px; display:flex; align-items:center; justify-content:center; }
    .wg-preview-img-wrap { flex:1 1 auto; min-width:0; min-height:0; display:flex; align-items:center; justify-content:center; overflow:hidden; }
    .wg-preview-img { display:block; max-width:100%; max-height:100%; width:auto; height:auto; margin:0 auto; border-radius:8px; object-fit:contain; cursor:pointer; }
    .wg-nav { width:40px; height:88px; display:flex; align-items:center; justify-content:center; border:1px solid rgba(255,255,255,0.16); border-radius:10px; background:rgba(255,255,255,0.06); color:rgba(255,255,255,0.95); font-size:28px; line-height:1; cursor:pointer; user-select:none; transition:background 0.12s ease, opacity 0.12s ease; }
    .wg-nav:hover { background:rgba(255,255,255,0.12); }
    .wg-nav.hidden { visibility:hidden; pointer-events:none; opacity:0; }
    .wg-preview-caption { padding-top:6px; font-size:11px; line-height:1.25; word-break:break-word; opacity:0.9; text-align:center; }
    .wg-gallery { flex:1 1 auto; overflow:auto; border:1px solid rgba(255,255,255,0.15); border-radius:8px; padding:6px; display:grid; gap:6px; align-content:start; min-height:180px; }
    .wg-root.viewer-mode .wg-gallery, .wg-root.viewer-mode .wg-slider-row, .wg-root.viewer-mode .wg-dir { display:none; }
    .wg-root.viewer-mode .wg-preview { flex:1 1 auto; min-height:620px; }
    .wg-item { border:1px solid rgba(255,255,255,0.12); border-radius:8px; overflow:hidden; background:rgba(0,0,0,0.18); cursor:pointer; }
    .wg-item img { display:block; width:100%; height:auto; }
    .wg-item.selected { outline:2px solid rgba(120,180,255,0.9); }
    .wg-caption { padding:4px 6px; font-size:11px; line-height:1.25; word-break:break-word; opacity:0.9; }
    .wg-empty { opacity:0.7; font-size:12px; padding:10px; text-align:center; }
    .wg-slider-row { display:flex; gap:8px; align-items:center; font-size:12px; }
    .wg-slider-row input[type='range'] { flex:1; }
    .wg-order-hint { font-size:11px; opacity:0.75; text-align:right; }
  `;
  document.head.appendChild(style);
}

async function fetchGallery(nodeId) {
  const res = await api.fetchApi(`/workflow_gallery/state/${nodeId}`);
  if (!res.ok) throw new Error(`Failed to load gallery ${nodeId}`);
  return await res.json();
}

async function clearGallery(nodeId) {
  const res = await api.fetchApi(`/workflow_gallery/clear/${nodeId}`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to clear gallery ${nodeId}`);
  return await res.json();
}

function layoutGrid(galleryEl, thumbSize) {
  const size = Math.max(80, Math.min(240, Number(thumbSize) || 120));
  galleryEl.style.gridTemplateColumns = `repeat(auto-fill, minmax(${size}px, 1fr))`;
}

function getDisplayEntries(payload) {
  return payload?.entries?.slice().reverse() || [];
}

function closeViewer(node) {
  const state = node.__wgState;
  if (!state) return;
  state.selectedId = null;
  state.root.classList.remove("viewer-mode");
  state.preview.classList.add("hidden");
  state.previewImg.removeAttribute("src");
  state.previewCaption.textContent = "";
  renderGallery(node, state.payload || { entries: [] });
  node.setDirtyCanvas(true, true);
}

function navigateViewer(node, direction) {
  const state = node.__wgState;
  if (!state?.selectedId || !state.payload) return;
  const entries = getDisplayEntries(state.payload);
  const idx = entries.findIndex((entry) => entry.id === state.selectedId);
  if (idx === -1 || !entries.length) return;
  const nextIdx = Math.max(0, Math.min(entries.length - 1, idx + direction));
  if (nextIdx === idx) return;
  state.selectedId = entries[nextIdx].id;
  renderGallery(node, state.payload);
  node.setDirtyCanvas(true, true);
}

function updateNavButtons(state, entries) {
  if (!state?.navLeft || !state?.navRight) return;
  const idx = entries.findIndex((entry) => entry.id === state.selectedId);
  const atStart = idx <= 0;
  const atEnd = idx === -1 || idx >= entries.length - 1;
  state.navLeft.classList.toggle('hidden', atStart);
  state.navRight.classList.toggle('hidden', atEnd);
}


function renderGallery(node, payload) {
  const state = node.__wgState;
  if (!state) return;

  state.payload = payload;
  state.count.textContent = `${payload.count} / ${payload.max_images}`;
  state.dir.textContent = payload.output_directory || "";
  if (state.dirWrap) state.dirWrap.textContent = payload.output_directory || "";
  state.gallery.innerHTML = "";
  layoutGrid(state.gallery, state.thumbSlider.value);

  if (!payload.entries?.length) {
    state.selectedId = null;
    state.root.classList.remove("viewer-mode");
    state.preview.classList.add("hidden");
    state.previewImg.removeAttribute("src");
    state.previewCaption.textContent = "";
    state.gallery.appendChild(el("div", { className: "wg-empty" }, ["Gallery is empty. Queue an image batch through this node."]));
    return;
  }

  const entries = getDisplayEntries(payload);
  const selectedStillExists = entries.some((entry) => entry.id === state.selectedId);
  if (!selectedStillExists) {
    state.selectedId = null;
  }

  for (const entry of entries) {
    const selected = entry.id === state.selectedId;
    const item = el("div", { className: `wg-item${selected ? " selected" : ""}` });
    const img = el("img", { src: entry.thumb_url, loading: "lazy", alt: entry.filename });
    const caption = el("div", { className: "wg-caption" }, [`${entry.filename}
${entry.width}×${entry.height}`]);

    item.appendChild(img);
    item.appendChild(caption);
    item.addEventListener("click", () => {
      if (state.selectedId === entry.id) {
        state.selectedId = null;
        state.root.classList.remove("viewer-mode");
        state.preview.classList.add("hidden");
        state.previewImg.removeAttribute("src");
        state.previewCaption.textContent = "";
      } else {
        state.selectedId = entry.id;
        state.root.classList.add("viewer-mode");
        state.preview.classList.remove("hidden");
        state.previewImg.src = entry.full_url;
        state.previewImg.alt = entry.filename;
        state.previewCaption.textContent = `${entry.filename} • ${entry.width}×${entry.height}`;
      }
      renderGallery(node, state.payload || payload);
      node.setDirtyCanvas(true, true);
    });

    state.gallery.appendChild(item);
  }

  if (state.selectedId) {
    const active = entries.find((entry) => entry.id === state.selectedId);
    if (active) {
      state.root.classList.add("viewer-mode");
      state.preview.classList.remove("hidden");
      state.previewImg.src = active.full_url;
      state.previewImg.alt = active.filename;
      state.previewCaption.textContent = `${active.filename} • ${active.width}×${active.height}`;
      updateNavButtons(state, entries);
    }
  } else {
    state.root.classList.remove("viewer-mode");
    state.preview.classList.add("hidden");
    state.previewImg.removeAttribute("src");
    state.previewCaption.textContent = "";
    updateNavButtons(state, entries);
  }
}

function attachDom(node) {
  ensureStyles();

  const clearBtn = el("button", { type: "button" }, ["Clear"]);
  const refreshBtn = el("button", { type: "button" }, ["Refresh"]);
  const count = el("span", { className: "wg-count" }, ["0 / 0"]);
  const previewImg = el("img", { className: "wg-preview-img", loading: "eager", alt: "Selected image preview" });
  const navLeft = el("button", { type: "button", className: "wg-nav hidden", "aria-label": "Previous image" }, ["‹"]);
  const navRight = el("button", { type: "button", className: "wg-nav hidden", "aria-label": "Next image" }, ["›"]);
  const previewCaption = el("div", { className: "wg-preview-caption" }, [""]);
  const previewStage = el("div", { className: "wg-preview-stage" }, [el("div", { className: "wg-preview-lane wg-preview-lane-left" }, [navLeft]), el("div", { className: "wg-preview-img-wrap" }, [previewImg]), el("div", { className: "wg-preview-lane wg-preview-lane-right" }, [navRight])]);
  const preview = el("div", { className: "wg-preview hidden" }, [previewStage, previewCaption]);
  const gallery = el("div", { className: "wg-gallery" });
  const thumbSlider = el("input", {
    type: "range",
    min: "80",
    max: "240",
    step: "10",
    value: "120",
  });
  const dir = el("span", {}, [""]);

  previewImg.addEventListener("click", () => closeViewer(node));
  navLeft.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    navigateViewer(node, -1);
  });
  navRight.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    navigateViewer(node, 1);
  });

  const root = el("div", { className: "wg-root" }, [
    el("div", { className: "wg-topbar" }, [clearBtn, refreshBtn, count]),
    preview,
    gallery,
    el("div", { className: "wg-slider-row" }, [el("span", {}, ["Thumbnail size"]), thumbSlider]),
    el("div", { className: "wg-order-hint" }, ["Newest first"]),
    el("div", { className: "wg-dir", style: { fontSize: "11px", opacity: "0.8", wordBreak: "break-all" } }, [dir]),
  ]);

  const dirWrap = root.querySelector('.wg-dir');
  node.__wgState = { root, clearBtn, refreshBtn, count, preview, previewStage, previewImg, previewCaption, navLeft, navRight, gallery, thumbSlider, dir, dirWrap, selectedId: null, payload: null };

  thumbSlider.addEventListener("input", () => {
    layoutGrid(gallery, thumbSlider.value);
    node.setDirtyCanvas(true, true);
  });


  clearBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    try {
      await clearGallery(node.id);
      const payload = await fetchGallery(node.id);
      renderGallery(node, payload);
    } catch (err) {
      console.warn("Workflow Gallery clear failed", err);
    }
  });

  refreshBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    try {
      const payload = await fetchGallery(node.id);
      renderGallery(node, payload);
    } catch (err) {
      console.warn("Workflow Gallery refresh failed", err);
    }
  });


  const domWidget = node.addDOMWidget("workflow_gallery", "WGDOM", root, {
    serialize: false,
    hideOnZoom: false,
    getValue: () => null,
    setValue: () => {},
  });

  if (domWidget?.element?.style) {
    domWidget.element.style.width = "100%";
    domWidget.element.style.height = "100%";
    domWidget.element.style.display = "block";
  }

  node.size = [Math.max(node.size?.[0] || 0, 420), Math.max(node.size?.[1] || 0, 900)];

  fetchGallery(node.id)
    .then((payload) => renderGallery(node, payload))
    .catch((err) => console.warn("Workflow Gallery load failed", err));
}

app.registerExtension({
  name: EXTENSION_NAME,

  async setup() {
    api.addEventListener("workflow_gallery_update", (event) => {
      const detail = event.detail;
      if (!detail?.node_id) return;
      const node = app.graph?._nodes_by_id?.[detail.node_id] || app.graph?._nodes?.find((n) => String(n.id) === String(detail.node_id));
      if (!node || node.comfyClass !== TARGET_CLASS) return;
      renderGallery(node, detail);
    });
  },

  async beforeRegisterNodeDef(nodeType) {
    if (nodeType.comfyClass !== TARGET_CLASS && nodeType.ComfyClass !== TARGET_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      if (!this.__wgMounted) {
        this.__wgMounted = true;
        attachDom(this);
      }
      return result;
    };

    const onRemoved = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function () {
      if (this.__wgKeyHandler) {
        document.removeEventListener("keydown", this.__wgKeyHandler);
        this.__wgKeyHandler = null;
      }
      return onRemoved?.apply(this, arguments);
    };
  },
});
