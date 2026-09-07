/* File Tool frontend: collects input, calls the backend, shows the result.
   No file processing happens here - every operation is a POST to the API. */

const TARGET_LABELS = { png: "PNG", jpg: "JPG", pdf: "PDF" };

const el = {
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  addInput: document.getElementById("add-input"),
  addButton: document.getElementById("add-button"),
  fileMeta: document.getElementById("file-meta"),
  message: document.getElementById("message"),
  pdfPanel: document.getElementById("pdf-panel"),
  pageList: document.getElementById("page-list"),
  applyButton: document.getElementById("apply-button"),
  undoButton: document.getElementById("undo-button"),
  redoButton: document.getElementById("redo-button"),
  pdfNote: document.getElementById("pdf-note"),
  pdfExpand: document.getElementById("pdf-expand"),
  convertPanel: document.getElementById("convert-panel"),
  convertHint: document.getElementById("convert-hint"),
  imageFrame: document.getElementById("image-preview-frame"),
  imagePreview: document.getElementById("image-preview"),
  imageList: document.getElementById("image-list"),
  targetOptions: document.getElementById("target-options"),
  convertButton: document.getElementById("convert-button"),
  imageUndo: document.getElementById("image-undo"),
  imageRedo: document.getElementById("image-redo"),
  convertNote: document.getElementById("convert-note"),
  imageExpand: document.getElementById("image-expand"),
  resultPanel: document.getElementById("result-panel"),
  resultMeta: document.getElementById("result-meta"),
  downloadButton: document.getElementById("download-button"),
  previewDialog: document.getElementById("preview-dialog"),
  previewTitle: document.getElementById("preview-title"),
  previewNote: document.getElementById("preview-note"),
  previewBody: document.getElementById("preview-body"),
  previewClose: document.getElementById("preview-close"),
  previewUndo: document.getElementById("preview-undo"),
  previewRedo: document.getElementById("preview-redo"),
};

const state = {
  format: null,
  // Every uploaded file of the current format, in the order it arrived:
  // { file, name, size, pages, targets, multiTargets, url }.
  documents: [],
  // The document being built, as references into `documents`: { doc, page }.
  // Removing a page drops its reference, moving one swaps two of them.
  order: [],
  result: null, // { blob, name }
  busy: false,
  urls: [], // object URLs handed to image cards, revoked when the session restarts
  history: [], // editing steps, oldest first; see snapshot()
  step: -1, // position in history; everything after it is redoable
};

// Cards are reused across renders so the browser never re-decodes a preview
// image; the caches are dropped whenever the documents behind them change.
const cards = { panel: new Map(), expanded: new Map(), builtFor: null };

/* ---------- input ---------- */

el.fileInput.addEventListener("change", () => {
  if (el.fileInput.files.length) startWith([...el.fileInput.files]);
  el.fileInput.value = "";
});

el.addInput.addEventListener("change", () => {
  if (el.addInput.files.length) addFiles([...el.addInput.files]);
  el.addInput.value = "";
});

el.addButton.addEventListener("click", () => el.addInput.click());

["dragenter", "dragover"].forEach((type) =>
  el.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    el.dropzone.classList.add("dragover");
  })
);

["dragleave", "drop"].forEach((type) =>
  el.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    el.dropzone.classList.remove("dragover");
  })
);

el.dropzone.addEventListener("drop", (event) => {
  const files = [...event.dataTransfer.files];
  if (files.length) startWith(files);
});

// The dropzone starts a new session; "+ Add file" extends the current one.
async function startWith(files) {
  reset();
  await addFiles(files);
}

async function addFiles(files) {
  setBusy(true);
  const opening = state.documents.length === 0;
  try {
    for (const file of files) await addDocument(file);
    clearMessage();
    if (opening) startHistory();
    else recordStep();
  } catch (error) {
    showError(error.message);
    // Whatever loaded before the failure stays, as a step of its own.
    if (!state.documents.length) reset();
    else if (opening) startHistory();
    else recordStep();
  } finally {
    setBusy(false);
  }
  render();
}

async function addDocument(file) {
  const body = new FormData();
  body.append("file", file, file.name || "file");
  const info = await postJson("/api/load", body);
  if (state.format && info.format !== state.format) {
    throw new Error(
      `${info.name} is a ${TARGET_LABELS[info.format]} file — ` +
      `only ${TARGET_LABELS[state.format]} files can be added to this one.`
    );
  }

  state.format = info.format;
  const document_ = {
    file,
    name: info.name,
    size: info.size,
    pages: info.pages,
    targets: info.targets,
    multiTargets: info.multi_targets,
    url: null,
  };
  if (info.format !== "pdf") {
    document_.url = URL.createObjectURL(file);
    state.urls.push(document_.url);
  }

  const index = state.documents.push(document_) - 1;
  // A PDF contributes all of its pages; an image is a single page of its own.
  const entries = info.format === "pdf" ? info.pages.map((page) => page.index) : [0];
  entries.forEach((page) => state.order.push({ doc: index, page }));
}

/* ---------- backend calls ---------- */

async function applyChanges() {
  if (!isDirty()) return;
  setBusy(true);
  try {
    const { body, files } = composeBody();
    const merged = files > 1;
    const result = await postFile("/api/pdf/compose", body);

    // The composed document becomes the working file, so edits can be stacked.
    const pages = state.order.length;
    await replaceDocuments(result);
    setResult(result);
    recordStep();
    showInfo(merged
      ? `Merged ${files} files into one ${pages} page PDF.`
      : `Applied the changes: ${pages} page${pages > 1 ? "s" : ""} left.`);
  } catch (error) {
    showError(error.message);
    // A failure while swapping in the composed document leaves nothing loaded;
    // fall back to the step that was being edited.
    if (!state.documents.length && state.step >= 0) restoreStep(state.step);
  } finally {
    setBusy(false);
    render();
  }
}

async function convert() {
  const target = el.targetOptions.querySelector("input:checked");
  if (!target) return;
  setBusy(true);
  try {
    const { body } = composeBody();
    body.append("target", target.value);
    setResult(await postFile("/api/convert", body));
    recordStep();
    const count = state.order.length;
    showInfo(count > 1
      ? `Merged ${count} images into one ${TARGET_LABELS[target.value]}.`
      : `Converted to ${TARGET_LABELS[target.value]}.`);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
    render();
  }
}

/** The files still referenced by the order, plus the order itself as `doc:page`. */
function composeBody() {
  const used = [...new Set(state.order.map((ref) => ref.doc))];
  const body = new FormData();
  used.forEach((index) => {
    const document_ = state.documents[index];
    body.append("file", document_.file, document_.name);
  });
  state.order.forEach((ref) => body.append("pages", `${used.indexOf(ref.doc)}:${ref.page}`));
  return { body, files: used.length };
}

/** Load a freshly composed document and make it the only one being worked on. */
async function replaceDocuments(result) {
  state.documents = [];
  state.order = [];
  state.format = null;
  await addDocument(new File([result.blob], result.name, { type: result.blob.type }));
}

async function postJson(url, body) {
  const response = await fetch(url, { method: "POST", body });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "The server rejected the request.");
  return payload;
}

async function postFile(url, body) {
  const response = await fetch(url, { method: "POST", body });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "The server rejected the request.");
  }
  return {
    blob: await response.blob(),
    name: filenameFrom(response.headers.get("Content-Disposition")) || state.documents[0].name,
  };
}

function filenameFrom(disposition) {
  const match = disposition && disposition.match(/filename="([^"]+)"/);
  return match ? match[1] : null;
}

/* ---------- editing ---------- */

function removeEntry(position) {
  if (state.busy || state.order.length <= 1) return;
  state.order.splice(position, 1);
  recordStep();
  render();
}

function moveEntry(position, offset) {
  const target = position + offset;
  if (state.busy || target < 0 || target >= state.order.length) return;
  const [entry] = state.order.splice(position, 1);
  state.order.splice(target, 0, entry);
  recordStep();
  render();
}

/** Is there anything the backend has not been told about yet? */
function isDirty() {
  const document_ = state.documents[0];
  if (!document_) return false;
  if (state.documents.length > 1) return true;
  const pages = state.format === "pdf" ? document_.pages.length : 1;
  if (state.order.length !== pages) return true;
  return state.order.some((ref, position) => ref.doc !== 0 || ref.page !== position);
}

function isReordered() {
  const kept = naturalKeys().filter((key) => orderKeys().includes(key));
  return kept.join("|") !== orderKeys().join("|");
}

function naturalKeys() {
  return state.documents.flatMap((document_, index) =>
    (state.format === "pdf" ? document_.pages.map((page) => page.index) : [0])
      .map((page) => `${index}:${page}`)
  );
}

function orderKeys() {
  return state.order.map((ref) => `${ref.doc}:${ref.page}`);
}

/* ---------- rendering ---------- */

function render() {
  if (cards.builtFor !== state.documents) {
    cards.panel.clear();
    cards.expanded.clear();
    cards.builtFor = state.documents;
  }

  const loaded = state.documents.length > 0;
  el.addButton.hidden = !loaded;
  el.pdfPanel.hidden = !loaded || state.format !== "pdf";
  el.convertPanel.hidden = !loaded || state.format === "pdf";
  showMeta(describe(state.documents[0]));

  if (loaded && state.format === "pdf") renderList(el.pageList, cards.panel);
  else if (loaded) renderConvert();
  if (el.previewDialog.open) renderExpanded();
  updateActions();
}

function renderList(container, cache) {
  container.replaceChildren(...state.order.map((ref, position) => {
    const card = cardFor(ref, cache);
    describeCard(card, ref, position);
    return card;
  }));
}

function renderConvert() {
  const single = state.order.length === 1;
  el.imageFrame.hidden = !single;
  el.imageList.hidden = single;
  el.convertHint.hidden = single;
  if (single) el.imagePreview.src = sourceOf(state.order[0]);
  else renderList(el.imageList, cards.panel);
  renderTargets(single ? state.documents[0].targets : state.documents[0].multiTargets);
}

function renderTargets(targets) {
  const chosen = el.targetOptions.querySelector("input:checked");
  const keep = chosen && targets.includes(chosen.value) ? chosen.value : targets[0];
  el.targetOptions.replaceChildren(...targets.map((target) => {
    const option = document.createElement("label");
    option.className = "target-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "target";
    input.value = target;
    input.checked = target === keep;
    input.addEventListener("change", updateActions);
    option.append(input, document.createTextNode(TARGET_LABELS[target] || target.toUpperCase()));
    return option;
  }));
}

function cardFor(ref, cache) {
  const key = `${ref.doc}:${ref.page}`;
  const cached = cache.get(key);
  if (cached) return cached;
  const card = cache === cards.expanded ? buildLargeCard(ref) : buildCard(ref);
  cache.set(key, card);
  return card;
}

function buildCard(ref) {
  const card = document.createElement("div");
  card.className = "page-card";
  card.append(cardImage(ref), cardLabel(), controls());
  return card;
}

function buildLargeCard(ref) {
  const card = document.createElement("figure");
  card.className = "preview-page";

  const frame = document.createElement("div");
  frame.className = "preview-frame";
  frame.append(capped(cardImage(ref), card, pageOf(ref)), controls());

  const caption = document.createElement("figcaption");
  caption.append(cardLabel());

  card.append(frame, caption);
  return card;
}

function cardImage(ref) {
  const image = document.createElement("img");
  image.src = sourceOf(ref);
  image.alt = "";
  return image;
}

/** Keep an expanded card from scaling its source up beyond its real size.
   PDF pages know their render size (Config.PREVIEW_DPI); images report theirs
   once the browser has decoded them. */
function capped(image, card, page) {
  if (page) card.style.maxWidth = `${page.width}px`;
  else image.addEventListener("load", () => { card.style.maxWidth = `${image.naturalWidth}px`; });
  return image;
}

function cardLabel() {
  const label = document.createElement("span");
  label.className = "page-label";
  const title = document.createElement("span");
  title.className = "page-title";
  const detail = document.createElement("span");
  detail.className = "page-detail";
  label.append(title, detail);
  return label;
}

function controls() {
  const group = document.createElement("div");
  group.className = "page-controls";
  group.append(
    control("move-up", "↑", "Move this page up"),
    control("move-down", "↓", "Move this page down"),
    control("remove", "−", "Remove this page")
  );
  return group;
}

function control(role, glyph, title) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `round-button ${role}`;
  button.textContent = glyph;
  button.title = title;
  return button;
}

/** Position dependent parts of a card: its label and what its buttons do.
   Labels count the current order, so moving a page renumbers what follows. */
function describeCard(card, ref, position) {
  const document_ = state.documents[ref.doc];
  const page = pageOf(ref);
  const title = card.querySelector(".page-title");
  const detail = card.querySelector(".page-detail");
  const last = state.order.length - 1;

  if (state.format === "pdf") {
    title.textContent = `Page ${position + 1}`;
    detail.textContent = state.documents.length > 1
      ? `${document_.name}, page ${ref.page + 1} — ${page.width} × ${page.height} px`
      : `${page.width} × ${page.height} px`;
  } else {
    title.textContent = `${position + 1}. ${document_.name}`;
    detail.textContent = formatSize(document_.size);
  }

  const up = card.querySelector(".move-up");
  const down = card.querySelector(".move-down");
  const remove = card.querySelector(".remove");
  up.onclick = () => moveEntry(position, -1);
  down.onclick = () => moveEntry(position, 1);
  remove.onclick = () => removeEntry(position);
  up.disabled = state.busy || position === 0;
  down.disabled = state.busy || position === last;
  remove.disabled = state.busy || state.order.length <= 1;
  remove.title = state.order.length <= 1
    ? "The last one cannot be removed"
    : state.format === "pdf" ? "Remove this page" : "Remove this file";
}

function sourceOf(ref) {
  const document_ = state.documents[ref.doc];
  return state.format === "pdf" ? document_.pages[ref.page].image : document_.url;
}

function pageOf(ref) {
  const document_ = state.documents[ref.doc];
  return state.format === "pdf" ? document_.pages[ref.page] : null;
}

function updateActions() {
  const dirty = isDirty();
  const files = new Set(state.order.map((ref) => ref.doc)).size;

  el.applyButton.textContent = files > 1 ? "Merge & apply changes" : "Apply changes";
  el.applyButton.disabled = state.busy || !dirty;
  el.convertButton.textContent = files > 1 ? "Merge & convert" : "Convert";
  el.convertButton.disabled = state.busy || !el.targetOptions.querySelector("input:checked");

  const note = noteText();
  el.pdfNote.textContent = note;
  el.convertNote.textContent = note;
  el.previewNote.textContent = note;

  const canUndo = !state.busy && state.step > 0;
  const canRedo = !state.busy && state.step < state.history.length - 1;
  [el.undoButton, el.imageUndo, el.previewUndo].forEach((button) => (button.disabled = !canUndo));
  [el.redoButton, el.imageRedo, el.previewRedo].forEach((button) => (button.disabled = !canRedo));
}

function noteText() {
  if (!state.documents.length) return "";
  const parts = [];
  const added = state.documents.length - 1;
  const dropped = naturalKeys().length - state.order.length;
  const unit = state.format === "pdf" ? "page" : "file";
  if (added > 0) parts.push(`${added} file${added > 1 ? "s" : ""} added`);
  if (dropped > 0) parts.push(`${dropped} ${unit}${dropped > 1 ? "s" : ""} removed`);
  if (isReordered()) parts.push("order changed");
  return parts.length ? `${parts.join(", ")} — not applied yet.` : "";
}

/* ---------- history ---------- */

// A step is the whole editable state: the documents in play, the page order built
// from them, and the download that produced it.
function snapshot() {
  return {
    format: state.format,
    documents: [...state.documents],
    order: state.order.map((ref) => ({ ...ref })),
    result: state.result,
  };
}

function startHistory() {
  state.history = [snapshot()];
  state.step = 0;
}

function recordStep() {
  state.history = state.history.slice(0, state.step + 1);
  state.history.push(snapshot());
  state.step = state.history.length - 1;
}

function undo() {
  if (state.busy || state.step <= 0) return;
  restoreStep(state.step - 1);
}

function redo() {
  if (state.busy || state.step >= state.history.length - 1) return;
  restoreStep(state.step + 1);
}

function restoreStep(step) {
  const entry = state.history[step];
  state.step = step;
  state.format = entry.format;
  state.documents = [...entry.documents];
  state.order = entry.order.map((ref) => ({ ...ref }));

  if (entry.result) setResult(entry.result);
  else resetResult();
  clearMessage();
  render();
}

/* ---------- expanded preview ---------- */

// A larger rendering of whatever the panel already shows, with the same controls.
function openExpanded() {
  if (!state.documents.length) return;
  renderExpanded();
  if (!el.previewDialog.open) {
    el.previewBody.scrollTop = 0;
    el.previewDialog.showModal();
  }
}

function renderExpanded() {
  const single = state.format !== "pdf" && state.order.length === 1;
  if (single) {
    const image = document.createElement("img");
    image.className = "preview-image";
    image.src = sourceOf(state.order[0]);
    image.alt = state.documents[0].name;
    el.previewBody.replaceChildren(image);
  } else {
    renderList(el.previewBody, cards.expanded);
  }
  const count = state.order.length;
  const unit = state.format === "pdf" ? "page" : "file";
  el.previewTitle.textContent = `${state.documents[0].name} — ${count} ${unit}${count > 1 ? "s" : ""}`;
}

function closePreview() {
  if (el.previewDialog.open) el.previewDialog.close();
  el.previewBody.replaceChildren();
  cards.expanded.clear();
}

/* ---------- result and reset ---------- */

function setResult(result) {
  state.result = result;
  el.resultMeta.textContent = `${result.name} — ${formatSize(result.blob.size)}`;
  el.resultPanel.hidden = false;
  el.downloadButton.disabled = false;
}

function resetResult() {
  state.result = null;
  el.resultPanel.hidden = true;
  el.downloadButton.disabled = true;
}

function reset() {
  state.urls.forEach((url) => URL.revokeObjectURL(url));
  state.urls = [];
  state.format = null;
  state.documents = [];
  state.order = [];
  state.history = [];
  state.step = -1;
  closePreview();
  cards.panel.clear();
  el.pageList.replaceChildren();
  el.imageList.replaceChildren();
  el.targetOptions.replaceChildren();
  el.fileMeta.hidden = true;
  resetResult();
  render();
}

function describe(document_) {
  if (!document_) return "";
  const total = state.documents.reduce((sum, entry) => sum + entry.size, 0);
  const names = state.documents.length > 1
    ? `${document_.name} +${state.documents.length - 1} more`
    : document_.name;
  const pages = naturalKeys().length;
  return `${names} — ${TARGET_LABELS[state.format]}, ${formatSize(total)}` +
    (state.format === "pdf" ? `, ${pages} page${pages > 1 ? "s" : ""}` : "");
}

/* ---------- messages ---------- */

function showMeta(text) {
  el.fileMeta.textContent = text;
  el.fileMeta.hidden = !text;
}

function showError(text) {
  el.message.textContent = text;
  el.message.className = "message";
  el.message.hidden = false;
}

function showInfo(text) {
  el.message.textContent = text;
  el.message.className = "message info";
  el.message.hidden = false;
}

function clearMessage() {
  el.message.hidden = true;
}

function setBusy(busy) {
  state.busy = busy;
  updateActions();
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ---------- actions ---------- */

el.applyButton.addEventListener("click", applyChanges);
el.convertButton.addEventListener("click", convert);
el.pdfExpand.addEventListener("click", openExpanded);
el.imageExpand.addEventListener("click", openExpanded);
[el.undoButton, el.imageUndo, el.previewUndo].forEach((b) => b.addEventListener("click", undo));
[el.redoButton, el.imageRedo, el.previewRedo].forEach((b) => b.addEventListener("click", redo));
el.previewClose.addEventListener("click", closePreview);
el.previewDialog.addEventListener("close", () => el.previewBody.replaceChildren());
// Clicking the backdrop (the dialog itself, outside its content) closes the preview.
el.previewDialog.addEventListener("click", (event) => {
  if (event.target === el.previewDialog) closePreview();
});

document.addEventListener("keydown", (event) => {
  if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "z") return;
  if (!state.documents.length) return;
  event.preventDefault();
  if (event.shiftKey) redo();
  else undo();
});

el.downloadButton.addEventListener("click", () => {
  if (!state.result) return;
  const url = URL.createObjectURL(state.result.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = state.result.name;
  link.click();
  URL.revokeObjectURL(url);
});
