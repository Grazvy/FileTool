/* File Tool frontend: collects input, calls the backend, shows the result.
   No file processing happens here - every operation is a POST to the API. */

const TARGET_LABELS = { png: "PNG", jpg: "JPG", pdf: "PDF" };

const el = {
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  fileMeta: document.getElementById("file-meta"),
  message: document.getElementById("message"),
  pdfPanel: document.getElementById("pdf-panel"),
  pageList: document.getElementById("page-list"),
  applyButton: document.getElementById("apply-button"),
  pdfNote: document.getElementById("pdf-note"),
  convertPanel: document.getElementById("convert-panel"),
  imagePreview: document.getElementById("image-preview"),
  targetOptions: document.getElementById("target-options"),
  convertButton: document.getElementById("convert-button"),
  resultPanel: document.getElementById("result-panel"),
  resultMeta: document.getElementById("result-meta"),
  downloadButton: document.getElementById("download-button"),
};

const state = {
  file: null, // the file currently being worked on (a File or a Blob)
  name: "",
  format: null,
  marked: new Set(), // page indices marked for removal
  result: null, // { blob, name }
  previewUrl: null,
  busy: false,
};

/* ---------- input ---------- */

el.fileInput.addEventListener("change", () => {
  if (el.fileInput.files.length) loadFile(el.fileInput.files[0]);
});

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
  const file = event.dataTransfer.files[0];
  if (file) loadFile(file);
});

async function loadFile(file) {
  resetResult();
  state.file = file;
  state.name = file.name || "file";
  state.marked.clear();
  await inspect();
}

/* ---------- backend calls ---------- */

async function inspect() {
  setBusy(true);
  try {
    const body = new FormData();
    body.append("file", state.file, state.name);
    const info = await postJson("/api/load", body);

    state.format = info.format;
    state.name = info.name;
    showMeta(`${info.name} — ${TARGET_LABELS[info.format]}, ${formatSize(info.size)}` +
      (info.pages.length ? `, ${info.pages.length} page${info.pages.length > 1 ? "s" : ""}` : ""));

    if (info.format === "pdf") showPdf(info.pages);
    else showConvert(info.targets);
    clearMessage();
  } catch (error) {
    reset();
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

async function applyPageRemoval() {
  if (!state.marked.size) return;
  setBusy(true);
  try {
    const body = new FormData();
    body.append("file", state.file, state.name);
    [...state.marked].sort((a, b) => a - b).forEach((index) => body.append("pages", index));
    const removed = state.marked.size;
    const result = await postFile("/api/pdf/remove-pages", body);

    // The edited document becomes the working file, so edits can be stacked.
    state.file = result.blob;
    state.name = result.name;
    state.marked.clear();
    setResult(result);
    await inspect();
    showInfo(`Removed ${removed} page${removed > 1 ? "s" : ""}.`);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

async function convert() {
  const target = el.targetOptions.querySelector("input:checked");
  if (!target) return;
  setBusy(true);
  try {
    const body = new FormData();
    body.append("file", state.file, state.name);
    body.append("target", target.value);
    setResult(await postFile("/api/convert", body));
    showInfo(`Converted to ${TARGET_LABELS[target.value]}.`);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
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
    name: filenameFrom(response.headers.get("Content-Disposition")) || state.name,
  };
}

function filenameFrom(disposition) {
  const match = disposition && disposition.match(/filename="([^"]+)"/);
  return match ? match[1] : null;
}

/* ---------- rendering ---------- */

function showPdf(pages) {
  el.pageList.replaceChildren(...pages.map(renderPage));
  el.pdfPanel.hidden = false;
  el.convertPanel.hidden = true;
  updateApplyButton();
}

function renderPage(page) {
  const card = document.createElement("div");
  card.className = "page-card";

  const image = document.createElement("img");
  image.src = page.image;
  image.alt = `Page ${page.index + 1}`;

  const label = document.createElement("span");
  label.className = "page-label";
  label.textContent = `Page ${page.index + 1}`;
  const dimensions = document.createElement("span");
  dimensions.className = "page-dimensions";
  dimensions.textContent = `${page.width} × ${page.height} px`;
  label.append(dimensions);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "remove-button";
  remove.textContent = "−";
  remove.title = "Mark this page for removal";
  remove.addEventListener("click", () => togglePage(page.index, card));

  card.append(image, label, remove);
  return card;
}

function togglePage(index, card) {
  if (state.marked.has(index)) state.marked.delete(index);
  else state.marked.add(index);
  card.classList.toggle("marked", state.marked.has(index));
  updateApplyButton();
}

function updateApplyButton() {
  const marked = state.marked.size;
  const pages = el.pageList.childElementCount;
  const keepsAPage = marked < pages;
  el.applyButton.disabled = state.busy || marked === 0 || !keepsAPage;
  if (!marked) el.pdfNote.textContent = "";
  else if (!keepsAPage) el.pdfNote.textContent = "A PDF must keep at least one page.";
  else el.pdfNote.textContent = `${marked} page${marked > 1 ? "s" : ""} marked for removal.`;
}

function showConvert(targets) {
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = URL.createObjectURL(state.file);
  el.imagePreview.src = state.previewUrl;

  el.targetOptions.replaceChildren(...targets.map((target, position) => {
    const option = document.createElement("label");
    option.className = "target-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "target";
    input.value = target;
    input.checked = position === 0;
    input.addEventListener("change", () => { el.convertButton.disabled = state.busy; });
    option.append(input, document.createTextNode(TARGET_LABELS[target] || target.toUpperCase()));
    return option;
  }));

  el.convertButton.disabled = state.busy || targets.length === 0;
  el.convertPanel.hidden = false;
  el.pdfPanel.hidden = true;
}

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
  state.file = null;
  state.format = null;
  state.marked.clear();
  el.pdfPanel.hidden = true;
  el.convertPanel.hidden = true;
  el.fileMeta.hidden = true;
  resetResult();
}

function showMeta(text) {
  el.fileMeta.textContent = text;
  el.fileMeta.hidden = false;
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
  el.convertButton.disabled = busy || !el.targetOptions.querySelector("input:checked");
  updateApplyButton();
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ---------- actions ---------- */

el.applyButton.addEventListener("click", applyPageRemoval);
el.convertButton.addEventListener("click", convert);
el.downloadButton.addEventListener("click", () => {
  if (!state.result) return;
  const url = URL.createObjectURL(state.result.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = state.result.name;
  link.click();
  URL.revokeObjectURL(url);
});
