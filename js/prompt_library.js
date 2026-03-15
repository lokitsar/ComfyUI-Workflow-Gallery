import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const PL_EXTENSION_NAME = "comfyui.prompt.library";
const PL_TARGET_CLASS = "PromptLibrary";

function plEl(tag, attrs = {}, children = []) {
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

function ensurePlStyles() {
  if (document.getElementById("prompt-library-styles")) return;
  const style = document.createElement("style");
  style.id = "prompt-library-styles";
  style.textContent = `
    .pl-root { display:flex; flex-direction:column; gap:6px; padding:8px; box-sizing:border-box; width:100%; height:100%; overflow:hidden; min-height:0; }
    .pl-topbar { display:flex; gap:6px; align-items:center; flex-wrap:wrap; flex-shrink:0; }
    .pl-topbar button { cursor:pointer; }
    .pl-search-row { display:flex; gap:6px; flex-shrink:0; }
    .pl-search { flex:1; padding:4px 8px; border-radius:6px; border:1px solid rgba(255,255,255,0.2); background:rgba(0,0,0,0.3); color:inherit; font-size:12px; }
    .pl-tag-filter { padding:4px 8px; border-radius:6px; border:1px solid rgba(255,255,255,0.2); background:rgba(0,0,0,0.3); color:inherit; font-size:12px; min-width:80px; }
    .pl-list { flex:1 1 auto; min-height:120px; overflow-y:auto; display:flex; flex-direction:column; gap:4px; }
    .pl-item { border:1px solid rgba(255,255,255,0.12); border-radius:8px; padding:8px; background:rgba(0,0,0,0.2); cursor:pointer; transition:background 0.1s; }
    .pl-item:hover { background:rgba(255,255,255,0.08); }
    .pl-item.selected { outline:2px solid rgba(120,180,255,0.9); background:rgba(120,180,255,0.08); }
    .pl-item-name { font-size:12px; font-weight:bold; margin-bottom:3px; }
    .pl-item-preview { font-size:11px; opacity:0.7; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .pl-item-tags { display:flex; gap:4px; flex-wrap:wrap; margin-top:4px; }
    .pl-tag { font-size:10px; padding:1px 6px; border-radius:10px; background:rgba(120,180,255,0.2); border:1px solid rgba(120,180,255,0.3); }
    .pl-item-actions { display:flex; gap:4px; margin-top:6px; }
    .pl-item-actions button { cursor:pointer; font-size:10px; padding:2px 6px; border-radius:4px; border:1px solid rgba(255,255,255,0.2); background:rgba(255,255,255,0.06); color:inherit; }
    .pl-item-actions button:hover { background:rgba(255,255,255,0.14); }
    .pl-empty { opacity:0.6; font-size:12px; text-align:center; padding:20px; }
    .pl-selected-bar { flex-shrink:0; padding:6px 8px; border:1px solid rgba(120,180,255,0.3); border-radius:8px; background:rgba(120,180,255,0.08); font-size:11px; }
    .pl-selected-name { font-weight:bold; margin-bottom:2px; }
    .pl-selected-preview { opacity:0.8; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .pl-add-form { flex-shrink:0; border:1px solid rgba(255,255,255,0.12); border-radius:8px; padding:8px; background:rgba(0,0,0,0.2); display:flex; flex-direction:column; gap:6px; }
    .pl-add-form.hidden { display:none; }
    .pl-add-form input, .pl-add-form textarea { padding:4px 8px; border-radius:6px; border:1px solid rgba(255,255,255,0.2); background:rgba(0,0,0,0.3); color:inherit; font-size:11px; width:100%; box-sizing:border-box; }
    .pl-add-form textarea { resize:vertical; min-height:60px; }
    .pl-add-form label { font-size:10px; opacity:0.7; margin-bottom:1px; display:block; }
    .pl-add-actions { display:flex; gap:6px; }
    .pl-add-actions button { cursor:pointer; flex:1; padding:4px; border-radius:6px; border:1px solid rgba(255,255,255,0.2); background:rgba(255,255,255,0.06); color:inherit; font-size:11px; }
    .pl-export-btn { cursor:pointer; font-size:11px; }
    .pl-count { margin-left:auto; font-size:11px; opacity:0.8; }
    .pl-save-current { cursor:pointer; background:rgba(60,180,80,0.15); border:1px solid rgba(60,180,80,0.5); color:rgba(100,220,120,1); border-radius:4px; padding:2px 8px; font-size:11px; }
    .pl-save-current:hover { background:rgba(60,180,80,0.28); }
    .pl-edit-form { flex-shrink:0; border:1px solid rgba(255,200,50,0.3); border-radius:8px; padding:8px; background:rgba(255,200,50,0.05); display:flex; flex-direction:column; gap:6px; }
    .pl-edit-form.hidden { display:none; }
    .pl-edit-form input, .pl-edit-form textarea { padding:4px 8px; border-radius:6px; border:1px solid rgba(255,255,255,0.2); background:rgba(0,0,0,0.3); color:inherit; font-size:11px; width:100%; box-sizing:border-box; }
    .pl-edit-form textarea { resize:vertical; min-height:60px; }
    .pl-edit-form label { font-size:10px; opacity:0.7; margin-bottom:1px; display:block; }
  `;
  document.head.appendChild(style);
}

async function plFetch(path, options = {}) {
  const res = await fetch(path, options);
  return res.json();
}

function attachPlDom(node) {
  ensurePlStyles();

  let allEntries = [];
  let selectedId = null;

  // ── Top bar ──────────────────────────────────────────────────────────────
  const addBtn = plEl("button", { type: "button" }, ["+ Add"]);
  const saveCurrentBtn = plEl("button", { type: "button", className: "pl-save-current" }, ["💾 Save Current"]);
  const refreshBtn = plEl("button", { type: "button" }, ["↻ Refresh"]);
  const exportJsonBtn = plEl("button", { type: "button", className: "pl-export-btn" }, ["↓ JSON"]);
  const exportCsvBtn = plEl("button", { type: "button", className: "pl-export-btn" }, ["↓ CSV"]);
  const count = plEl("span", { className: "pl-count" }, ["0 prompts"]);
  const topbar = plEl("div", { className: "pl-topbar" }, [addBtn, saveCurrentBtn, refreshBtn, exportJsonBtn, exportCsvBtn, count]);

  // ── Search + tag filter ───────────────────────────────────────────────────
  const searchInput = plEl("input", { type: "text", className: "pl-search", placeholder: "Search prompts..." });
  const tagSelect = plEl("select", { className: "pl-tag-filter" });
  tagSelect.appendChild(plEl("option", { value: "" }, ["All tags"]));
  const searchRow = plEl("div", { className: "pl-search-row" }, [searchInput, tagSelect]);

  // ── Add form ──────────────────────────────────────────────────────────────
  const nameInput = plEl("input", { type: "text", placeholder: "Name *" });
  const tagsInput = plEl("input", { type: "text", placeholder: "Tags (comma separated)" });
  const promptInput = plEl("textarea", { placeholder: "Positive prompt *" });
  const saveNewBtn = plEl("button", { type: "button" }, ["Save"]);
  const cancelAddBtn = plEl("button", { type: "button" }, ["Cancel"]);
  const addForm = plEl("div", { className: "pl-add-form hidden" }, [
    plEl("label", {}, ["Name"]), nameInput,
    plEl("label", {}, ["Tags (comma separated)"]), tagsInput,
    plEl("label", {}, ["Positive Prompt"]), promptInput,
    plEl("div", { className: "pl-add-actions" }, [saveNewBtn, cancelAddBtn]),
  ]);

  // ── Selected bar ──────────────────────────────────────────────────────────
  const selectedName = plEl("div", { className: "pl-selected-name" }, ["No prompt selected"]);
  const selectedPreview = plEl("div", { className: "pl-selected-preview" }, [""]);
  const selectedBar = plEl("div", { className: "pl-selected-bar" }, [selectedName, selectedPreview]);

  // ── List ──────────────────────────────────────────────────────────────────
  const list = plEl("div", { className: "pl-list" });

  // ── Edit form ─────────────────────────────────────────────────────────────
  const editNameInput = plEl("input", { type: "text", placeholder: "Name *" });
  const editTagsInput = plEl("input", { type: "text", placeholder: "Tags (comma separated)" });
  const editPromptInput = plEl("textarea", { placeholder: "Positive prompt *" });
  const saveEditBtn = plEl("button", { type: "button" }, ["Save Changes"]);
  const cancelEditBtn = plEl("button", { type: "button" }, ["Cancel"]);
  const editForm = plEl("div", { className: "pl-edit-form hidden" }, [
    plEl("label", {}, ["Name"]), editNameInput,
    plEl("label", {}, ["Tags (comma separated)"]), editTagsInput,
    plEl("label", {}, ["Positive Prompt"]), editPromptInput,
    plEl("div", { className: "pl-add-actions" }, [saveEditBtn, cancelEditBtn]),
  ]);
  let editingId = null;
  const manualTextarea = plEl("textarea", { placeholder: "Manual text (optional — combined with selected prompt or used alone)", rows: "3" });
  manualTextarea.style.cssText = "width:100%;box-sizing:border-box;padding:4px 8px;border-radius:6px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.3);color:inherit;font-size:11px;resize:vertical;max-height:120px;";
  const positionBefore = plEl("input", { type: "radio", name: `pl-pos-${Math.random().toString(36).slice(2)}`, value: "before", id: "pl-before" });
  const positionAfter = plEl("input", { type: "radio", name: positionBefore.name, value: "after", id: "pl-after" });
  positionAfter.checked = true;
  const posLabel = plEl("div", { style: { display:"flex", gap:"12px", alignItems:"center", fontSize:"11px", opacity:"0.8" } }, [
    plEl("span", {}, ["Insert manual text:"]),
    plEl("label", { style: { display:"flex", gap:"4px", alignItems:"center", cursor:"pointer" } }, [positionBefore, "Before prompt"]),
    plEl("label", { style: { display:"flex", gap:"4px", alignItems:"center", cursor:"pointer" } }, [positionAfter, "After prompt"]),
  ]);
  const manualSection = plEl("div", { style: { display:"flex", flexDirection:"column", gap:"4px", flexShrink:"0" } }, [posLabel, manualTextarea]);

  const root = plEl("div", { className: "pl-root" }, [topbar, searchRow, addForm, editForm, selectedBar, manualSection, list]);

  // ── Render list ───────────────────────────────────────────────────────────
  function getFilteredEntries() {
    const q = searchInput.value.trim().toLowerCase();
    const tag = tagSelect.value;
    return allEntries.filter(e => {
      const matchesTag = !tag || (e.tags || []).includes(tag);
      const matchesSearch = !q ||
        e.name.toLowerCase().includes(q) ||
        (e.positive_prompt || "").toLowerCase().includes(q) ||
        (e.tags || []).some(t => t.toLowerCase().includes(q));
      return matchesTag && matchesSearch;
    });
  }

  function rebuildTagFilter() {
    const currentVal = tagSelect.value;
    tagSelect.innerHTML = "";
    tagSelect.appendChild(plEl("option", { value: "" }, ["All tags"]));
    const allTags = [...new Set(allEntries.flatMap(e => e.tags || []))].sort();
    for (const tag of allTags) {
      const opt = plEl("option", { value: tag }, [tag]);
      if (tag === currentVal) opt.selected = true;
      tagSelect.appendChild(opt);
    }
  }

  function renderList() {
    list.innerHTML = "";
    const filtered = getFilteredEntries();
    count.textContent = `${allEntries.length} prompt${allEntries.length !== 1 ? "s" : ""}`;

    if (!filtered.length) {
      list.appendChild(plEl("div", { className: "pl-empty" }, [
        allEntries.length ? "No prompts match your search." : "No saved prompts yet. Click + Add or save from the Gallery."
      ]));
      return;
    }

    for (const entry of filtered) {
      const isSelected = entry.id === selectedId;
      const item = plEl("div", { className: `pl-item${isSelected ? " selected" : ""}` });
      const tags = (entry.tags || []).map(t => plEl("span", { className: "pl-tag" }, [t]));
      const tagRow = tags.length ? plEl("div", { className: "pl-item-tags" }, tags) : null;

      const useBtn = plEl("button", { type: "button" }, ["✓ Use"]);
      const editBtn = plEl("button", { type: "button" }, ["✎ Edit"]);
      const deleteBtn = plEl("button", { type: "button" }, ["✕ Delete"]);

      item.appendChild(plEl("div", { className: "pl-item-name" }, [entry.name]));
      item.appendChild(plEl("div", { className: "pl-item-preview" }, [entry.positive_prompt || ""]));
      if (tagRow) item.appendChild(tagRow);
      item.appendChild(plEl("div", { className: "pl-item-actions" }, [useBtn, editBtn, deleteBtn]));

      useBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        selectEntry(entry);
      });

      editBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        editingId = entry.id;
        editNameInput.value = entry.name || "";
        editTagsInput.value = (entry.tags || []).join(", ");
        editPromptInput.value = entry.positive_prompt || "";
        editForm.classList.remove("hidden");
        addForm.classList.add("hidden");
        editNameInput.focus();
      });

      deleteBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`Delete "${entry.name}"?`)) return;
        await plFetch("/prompt_library/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: entry.id }),
        });
        if (selectedId === entry.id) {
          selectedId = null;
          updateSelectedBar(null);
          updateNodeWidget("");
        }
        await loadEntries();
      });

      item.addEventListener("click", () => selectEntry(entry));
      list.appendChild(item);
    }
  }

  function selectEntry(entry) {
    if (selectedId === entry.id) {
      // Second click — deselect
      selectedId = null;
      updateSelectedBar(null);
      updateNodeWidget("");
    } else {
      selectedId = entry.id;
      updateSelectedBar(entry);
      updateNodeWidget(entry.positive_prompt || "");
    }
    renderList();
    node.setDirtyCanvas(true, true);
  }

  function updateSelectedBar(entry) {
    if (!entry) {
      selectedName.textContent = manualTextarea?.value.trim() ? "Manual text only" : "No prompt selected";
      selectedPreview.textContent = manualTextarea?.value.trim() || "";
    } else {
      selectedName.textContent = entry.name;
      selectedPreview.textContent = buildOutputPrompt(entry.positive_prompt || "");
    }
  }

  function buildOutputPrompt(promptText) {
    const manual = manualTextarea.value.trim();
    if (!manual && !promptText) return "";
    if (!manual) return promptText;
    if (!promptText) return manual;
    return positionBefore.checked
      ? `${manual}, ${promptText}`
      : `${promptText}, ${manual}`;
  }

  function updateNodeWidget(promptText) {
    const built = buildOutputPrompt(promptText);
    // Store in the widget value directly so Python can read it
    const widget = node.widgets?.find(w => w.name === "selected_prompt_id");
    if (widget) {
      widget.value = built;
    }
  }

  async function loadEntries() {
    try {
      const data = await plFetch("/prompt_library/list");
      allEntries = data.entries || [];
      rebuildTagFilter();
      renderList();
    } catch (err) {
      console.warn("Prompt Library load failed", err);
    }
  }

  // ── Add form handlers ─────────────────────────────────────────────────────
  addBtn.addEventListener("click", () => {
    addForm.classList.toggle("hidden");
    if (!addForm.classList.contains("hidden")) nameInput.focus();
  });

  cancelAddBtn.addEventListener("click", () => {
    addForm.classList.add("hidden");
    nameInput.value = "";
    tagsInput.value = "";
    promptInput.value = "";
  });

  saveNewBtn.addEventListener("click", async () => {
    const name = nameInput.value.trim();
    const positive_prompt = promptInput.value.trim();
    if (!name || !positive_prompt) {
      alert("Name and prompt are required.");
      return;
    }
    const tags = tagsInput.value.split(",").map(t => t.trim()).filter(Boolean);
    const data = await plFetch("/prompt_library/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, positive_prompt, tags }),
    });
    if (data.ok) {
      nameInput.value = "";
      tagsInput.value = "";
      promptInput.value = "";
      addForm.classList.add("hidden");
      await loadEntries();
    } else {
      alert(data.error || "Failed to save prompt.");
    }
  });

  saveEditBtn.addEventListener("click", async () => {
    if (!editingId) return;
    const name = editNameInput.value.trim();
    const positive_prompt = editPromptInput.value.trim();
    if (!name || !positive_prompt) { alert("Name and prompt are required."); return; }
    const tags = editTagsInput.value.split(",").map(t => t.trim()).filter(Boolean);
    const data = await plFetch("/prompt_library/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: editingId, name, positive_prompt, tags }),
    });
    if (data.ok) {
      if (selectedId === editingId) updateNodeWidget(positive_prompt);
      editingId = null;
      editForm.classList.add("hidden");
      await loadEntries();
    } else {
      alert(data.error || "Failed to update.");
    }
  });

  cancelEditBtn.addEventListener("click", () => {
    editForm.classList.add("hidden");
    editingId = null;
  });

  saveCurrentBtn.addEventListener("click", async () => {
    const currentPrompt = manualTextarea.value.trim();
    if (!currentPrompt) {
      alert("Type a prompt in the manual text area first, then click Save Current to add it to your library.");
      return;
    }
    const name = prompt("Name this prompt:");
    if (!name || !name.trim()) return;
    const tagsRaw = prompt("Tags (comma separated, optional):");
    const tags = tagsRaw ? tagsRaw.split(",").map(t => t.trim()).filter(Boolean) : [];
    const data = await plFetch("/prompt_library/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim(), positive_prompt: currentPrompt, tags }),
    });
    if (data.ok) {
      saveCurrentBtn.textContent = "✓ Saved!";
      setTimeout(() => { saveCurrentBtn.textContent = "💾 Save Current"; }, 2000);
      await loadEntries();
    } else {
      alert(data.error || "Failed to save.");
    }
  });
  searchInput.addEventListener("input", renderList);
  tagSelect.addEventListener("change", renderList);

  // Recompute output when manual text or position changes
  manualTextarea.addEventListener("input", () => {
    const entry = allEntries.find(e => e.id === selectedId);
    updateNodeWidget(entry?.positive_prompt || "");
    updateSelectedBar(entry || null);
    node.setDirtyCanvas(true, true);
  });
  positionBefore.addEventListener("change", () => {
    const entry = allEntries.find(e => e.id === selectedId);
    updateNodeWidget(entry?.positive_prompt || "");
  });
  positionAfter.addEventListener("change", () => {
    const entry = allEntries.find(e => e.id === selectedId);
    updateNodeWidget(entry?.positive_prompt || "");
  });

  // ── Refresh ───────────────────────────────────────────────────────────────
  refreshBtn.addEventListener("click", () => loadEntries());

  // ── Export ────────────────────────────────────────────────────────────────
  exportJsonBtn.addEventListener("click", () => {
    window.open("/prompt_library/export?format=json", "_blank");
  });
  exportCsvBtn.addEventListener("click", () => {
    window.open("/prompt_library/export?format=csv", "_blank");
  });

  // ── Mount widget ──────────────────────────────────────────────────────────
  const domWidget = node.addDOMWidget("prompt_library", "PLDOM", root, {
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

  node.size = [Math.max(node.size?.[0] || 0, 420), Math.max(node.size?.[1] || 0, 700)];

  // Set list height based on node canvas size — same approach as compare stage
  const setListHeight = () => {
    const totalH = node.size?.[1] || 700;
    const fixedH = 280; // topbar + search + forms + selected bar + manual textarea
    const listH = Math.max(120, totalH - fixedH);
    list.style.height = `${listH}px`;
    list.style.maxHeight = `${listH}px`;
    list.style.overflowY = "auto";
    list.style.flex = "none";
  };
  setListHeight();

  // Update on node resize
  const origOnResize = node.onResize;
  node.onResize = function(size) {
    setListHeight();
    return origOnResize?.apply(this, arguments);
  };

  // Initial load
  loadEntries();

  // Listen for updates from Gallery's "Save Prompt"
  api.addEventListener("prompt_library_updated", () => loadEntries());
}

app.registerExtension({
  name: PL_EXTENSION_NAME,

  async beforeRegisterNodeDef(nodeType) {
    if (nodeType.comfyClass !== PL_TARGET_CLASS && nodeType.ComfyClass !== PL_TARGET_CLASS) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);
      if (!this.__plMounted) {
        this.__plMounted = true;
        attachPlDom(this);
      }
      return result;
    };
  },
});
