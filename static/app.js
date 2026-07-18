const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const DEFAULT_SETTINGS = { filenameSuffix: "押印済み", batchCollision: "rename" };
const STAMP_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "svg", "pdf"]);
const PREVIEW_DROP_STAMP_MAX_MM = 50;
const state = {
  document: null,
  stamp: null,
  page: 0,
  placements: [],
  selectedId: null,
  templates: [],
  templatesLoaded: false,
  registeredStamps: [],
  registeredStampsLoaded: false,
  fonts: [],
  fontsLoaded: false,
  fontsLoading: false,
  fontStatusTimer: null,
  settings: { ...DEFAULT_SETTINGS },
  batchFiles: [],
  studio: {
    timer: null, version: 0, previewUrl: null, glyphTransforms: {}, companyGlyphTransforms: {}, selectedGlyph: 0, glyphTarget: "body",
    globalTextSettings: { body: { scaleX: 1, scaleY: 1, lineSpacing: 0, letterSpacing: 0, scaleLocked: false }, company: { scaleX: 1, scaleY: 1, lineSpacing: 0, letterSpacing: 0, scaleLocked: false } },
    svgAssets: [], selectedSvgAssetId: null,
  },
};

const elements = {
  editorView: $("#editorView"), studioView: $("#studioView"), tabs: $$("[data-view]"),
  pdfInput: $("#pdfInput"), pdfPicker: $("#pdfPicker"), stampInput: $("#stampInput"), stampPicker: $("#stampPicker"), documentName: $("#documentName"),
  stampName: $("#stampName"), registeredStampSelect: $("#registeredStampSelect"), registerStamp: $("#registerStamp"), deleteRegisteredStamp: $("#deleteRegisteredStamp"), addStamp: $("#addStamp"), removeStamp: $("#removeStamp"),
  width: $("#widthInput"), height: $("#heightInput"), x: $("#xInput"), y: $("#yInput"), rotation: $("#rotationInput"), rotationValue: $("#rotationValue"), pageSelect: $("#pageSelect"),
  title: $("#previewTitle"), status: $("#status"), empty: $("#emptyState"), scroll: $("#previewScroll"), workspace: $("#previewWorkspace"),
  stage: $("#pageStage"), preview: $("#pagePreview"), template: $("#templateSelect"),
  applyTemplate: $("#applyTemplate"), saveTemplate: $("#saveTemplate"), deleteTemplate: $("#deleteTemplate"), export: $("#exportPdf"), embedStampMetadata: $("#embedStampMetadata"),
  batchInput: $("#batchInput"), batchPicker: $("#batchPicker"), batchName: $("#batchName"), exportBatch: $("#exportBatch"),
  filenameSuffix: $("#filenameSuffix"), batchCollision: $("#batchCollision"),
  studioText: $("#studioText"), studioCompanyName: $("#studioCompanyName"), studioRoleText: $("#studioRoleText"), studioSquareText: $("#studioSquareText"), studioStampText: $("#studioStampText"),
  personalStampFields: $("#personalStampFields"), companyStampFields: $("#companyStampFields"), squareStampFields: $("#squareStampFields"), stampStampFields: $("#stampStampFields"), studioDirectionField: $("#studioDirectionField"), studioRepresentationField: $("#studioRepresentationField"), studioSize: $("#studioSize"),
  studioFontFilter: $("#studioFontFilter"), studioFontFamily: $("#studioFontFamily"), studioFont: $("#studioFont"),
  studioFrame: $("#studioFrame"), studioFrameField: $("#studioFrameField"), studioColor: $("#studioColor"),
  studioFrameWidth: $("#studioFrameWidth"), studioPadding: $("#studioPadding"), studioPaddingField: $("#studioPaddingField"), studioCompanyEndGap: $("#studioCompanyEndGap"), studioCompanyEndGapField: $("#studioCompanyEndGapField"), studioCompanyRingOffset: $("#studioCompanyRingOffset"), studioCompanyRingOffsetField: $("#studioCompanyRingOffsetField"), studioCornerRadius: $("#studioCornerRadius"), studioCornerRadiusField: $("#studioCornerRadiusField"), studioLineWidth: $("#studioLineWidth"), studioLineWidthField: $("#studioLineWidthField"), studioLineAngleSnap: $("#studioLineAngleSnap"), studioLineAngleSnapField: $("#studioLineAngleSnapField"),
  frameWidthValue: $("#frameWidthValue"), paddingValue: $("#paddingValue"), companyEndGapValue: $("#companyEndGapValue"), companyRingOffsetValue: $("#companyRingOffsetValue"), cornerRadiusValue: $("#cornerRadiusValue"), lineWidthValue: $("#lineWidthValue"), lineAngleSnapValue: $("#lineAngleSnapValue"), colorQuickPicks: $("#colorQuickPicks"), studioEmbedMetadata: $("#studioEmbedMetadata"),
  studioGlyphTargetField: $("#studioGlyphTargetField"), studioGlyphTarget: $("#studioGlyphTarget"), studioGlyphList: $("#studioGlyphList"), studioGlyphX: $("#studioGlyphX"), studioGlyphY: $("#studioGlyphY"), studioGlyphScaleX: $("#studioGlyphScaleX"), studioGlyphScaleY: $("#studioGlyphScaleY"),
  glyphXValue: $("#glyphXValue"), glyphYValue: $("#glyphYValue"), glyphScaleXValue: $("#glyphScaleXValue"), glyphScaleYValue: $("#glyphScaleYValue"), glyphXLabel: $("#glyphXLabel"), glyphYLabel: $("#glyphYLabel"), glyphScaleXLabel: $("#glyphScaleXLabel"), glyphScaleYLabel: $("#glyphScaleYLabel"), glyphEditorHint: $("#glyphEditorHint"), studioGlyphScaleLock: $("#studioGlyphScaleLock"), resetSelectedGlyph: $("#resetSelectedGlyph"), resetAllGlyphs: $("#resetAllGlyphs"),
  studioGlobalScaleX: $("#studioGlobalScaleX"), studioGlobalScaleY: $("#studioGlobalScaleY"), studioGlobalScaleLock: $("#studioGlobalScaleLock"), studioGlobalLineSpacing: $("#studioGlobalLineSpacing"), studioGlobalLineSpacingField: $("#studioGlobalLineSpacingField"), studioGlobalLetterSpacing: $("#studioGlobalLetterSpacing"), studioGlobalLetterSpacingField: $("#studioGlobalLetterSpacingField"), globalScaleXValue: $("#globalScaleXValue"), globalScaleYValue: $("#globalScaleYValue"), globalScaleXLabel: $("#globalScaleXLabel"), globalScaleYLabel: $("#globalScaleYLabel"), globalLineSpacingValue: $("#globalLineSpacingValue"), globalLetterSpacingValue: $("#globalLetterSpacingValue"), globalTextHint: $("#globalTextHint"), resetGlobalText: $("#resetGlobalText"),
  studioSvgInput: $("#studioSvgInput"), studioSvgPicker: $("#studioSvgPicker"), studioSvgAssetList: $("#studioSvgAssetList"), studioSvgAssetControls: $("#studioSvgAssetControls"), studioSvgAssetX: $("#studioSvgAssetX"), studioSvgAssetY: $("#studioSvgAssetY"), studioSvgAssetSize: $("#studioSvgAssetSize"), studioSvgColorFill: $("#studioSvgColorFill"), studioSvgColorStroke: $("#studioSvgColorStroke"), studioSvgColorInherited: $("#studioSvgColorInherited"), svgAssetXValue: $("#svgAssetXValue"), svgAssetYValue: $("#svgAssetYValue"), svgAssetSizeValue: $("#svgAssetSizeValue"), removeStudioSvgAsset: $("#removeStudioSvgAsset"),
  studioPreview: $("#studioPreview"), studioPreviewPaper: $("#studioPreviewPaper"), studioSvgPreviewAssets: $("#studioSvgPreviewAssets"), studioFontLoading: $("#studioFontLoading"), studioFontLoadingLabel: $("#studioFontLoadingLabel"), studioFontLoadingBar: $("#studioFontLoadingBar"), studioFontLoadingDetail: $("#studioFontLoadingDetail"), studioCaption: $("#studioCaption"), studioFormatBadge: $("#studioFormatBadge"), studioStatus: $("#studioStatus"), useStudioStamp: $("#useStudioStamp"), downloadStudioSvg: $("#downloadStudioSvg"),
  help: $("#helpDialog"), openHelp: $("#openHelp"), closeHelp: $("#closeHelp"), about: $("#aboutDialog"), openAbout: $("#openAbout"), closeAbout: $("#closeAbout"),
};

function setStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("error", isError);
}

function setStudioStatus(message, isError = false) {
  elements.studioStatus.textContent = message;
  elements.studioStatus.classList.toggle("error", isError);
}

async function readError(response) {
  try {
    const payload = await response.json();
    return payload.detail || "処理に失敗しました。";
  } catch {
    return "処理に失敗しました。";
  }
}

async function upload(file, endpoint) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(endpoint, { method: "POST", body: form });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

async function loadTemplates() {
  try {
    const response = await fetch("/api/templates");
    if (!response.ok) throw new Error(await readError(response));
    const templates = await response.json();
    state.templates = Array.isArray(templates) ? templates : [];
  } catch (error) {
    setStatus(`テンプレートを読み込めませんでした: ${error.message}`, true);
  } finally {
    state.templatesLoaded = true;
    renderAll();
  }
}

async function persistTemplates() {
  const response = await fetch("/api/templates", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state.templates),
  });
  if (!response.ok) throw new Error(await readError(response));
  state.templates = await response.json();
  renderTemplates();
}

async function loadRegisteredStamps() {
  try {
    const response = await fetch("/api/registered-stamps");
    if (!response.ok) throw new Error(await readError(response));
    const payload = await response.json();
    state.registeredStamps = Array.isArray(payload.stamps) ? payload.stamps : [];
  } catch (error) {
    state.registeredStamps = [];
    setStatus(`登録済み印影を読み込めませんでした: ${error.message}`, true);
  } finally {
    state.registeredStampsLoaded = true;
    renderRegisteredStamps();
  }
}

async function loadSettings() {
  try {
    const response = await fetch("/api/settings");
    if (!response.ok) throw new Error(await readError(response));
    state.settings = await response.json();
  } catch (error) {
    state.settings = { ...DEFAULT_SETTINGS };
    setStatus(`書き出し設定を読み込めませんでした: ${error.message}`, true);
  }
  renderSettings();
}

async function updateSettings() {
  const previous = { ...state.settings };
  const next = { filenameSuffix: elements.filenameSuffix.value.trim(), batchCollision: elements.batchCollision.value };
  try {
    const response = await fetch("/api/settings", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(next),
    });
    if (!response.ok) throw new Error(await readError(response));
    state.settings = await response.json();
    renderSettings();
    setStatus("書き出し設定をこのPCに保存しました。");
  } catch (error) {
    state.settings = previous;
    renderSettings();
    setStatus(error.message, true);
  }
}

async function loadFonts() {
  if (state.fontsLoaded || state.fontsLoading) return;
  state.fontsLoading = true;
  startFontProgressPolling();
  setStudioStatus("フォントを準備しています…");
  try {
    let response;
    do {
      response = await fetch("/api/fonts");
      if (response.status === 202) await new Promise((resolve) => window.setTimeout(resolve, 350));
    } while (response.status === 202);
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    state.fonts = Array.isArray(data.fonts) ? data.fonts : [];
    state.fontsLoaded = true;
  } catch (error) {
    setStudioStatus(`フォント一覧を読み込めませんでした: ${error.message}`, true);
  } finally {
    state.fontsLoading = false;
    stopFontProgressPolling();
    renderStudioFonts();
  }
}

function updateFontLoading(status) {
  const show = status.platform === "win32" && status.frozen && ["checking_cache", "scanning", "finalizing"].includes(status.state);
  elements.studioFontLoading.hidden = !show;
  if (!show) return;
  const completed = Number(status.completed) || 0;
  const total = Number(status.total) || 0;
  const progress = total ? Math.max(2, Math.min(100, completed / total * 100)) : 2;
  elements.studioFontLoadingLabel.textContent = status.state === "checking_cache"
    ? "前回のフォント一覧を確認しています…"
    : status.state === "finalizing"
      ? "フォント一覧を整理しています…"
      : "Windows のフォントを読み込んでいます…";
  elements.studioFontLoadingBar.style.width = `${progress}%`;
  const count = status.state === "finalizing"
    ? "メニューを準備しています…"
    : total ? `${completed} / ${total} ファイル` : "フォントファイルを数えています…";
  elements.studioFontLoadingDetail.textContent = status.current ? `${count}\n${status.current}` : count;
}

async function refreshFontProgress() {
  try {
    const response = await fetch("/api/font-status");
    if (response.ok) updateFontLoading(await response.json());
  } catch {
    // 表示補助用のポーリングなので、通信失敗はフォント取得本体のエラー表示へ任せる。
  }
}

function startFontProgressPolling() {
  if (state.fontStatusTimer !== null) return;
  void refreshFontProgress();
  state.fontStatusTimer = window.setInterval(() => { void refreshFontProgress(); }, 350);
}

function stopFontProgressPolling() {
  if (state.fontStatusTimer !== null) window.clearInterval(state.fontStatusTimer);
  state.fontStatusTimer = null;
  elements.studioFontLoading.hidden = true;
}

function currentPageInfo() {
  return state.document?.pages[state.page] || null;
}

function newPlacement() {
  const page = currentPageInfo();
  if (!page || !state.stamp) return;
  const preferredWidth = Number(state.stamp.defaultWidthMm || state.stamp.defaultSizeMm) || 9.5;
  const preferredHeight = Number(state.stamp.defaultHeightMm || state.stamp.defaultSizeMm) || 9.5;
  const scale = Math.min(1, page.widthMm / preferredWidth, page.heightMm / preferredHeight);
  const widthMm = preferredWidth * scale;
  const heightMm = preferredHeight * scale;
  const placement = {
    id: crypto.randomUUID(), stampId: state.stamp.id, page: state.page, widthMm, heightMm, rotationDegrees: 0,
    xMm: Math.max(0, (page.widthMm - widthMm) / 2), yMm: Math.max(0, (page.heightMm - heightMm) / 2),
  };
  state.placements.push(placement);
  state.selectedId = placement.id;
  renderAll();
  setStatus("印影を追加しました。紙面上でドラッグして位置を決めてください。");
}

function selectedPlacement() {
  return state.placements.find((placement) => placement.id === state.selectedId) || null;
}

function clearSelectedPlacement() {
  if (!selectedPlacement()) return false;
  state.selectedId = null;
  renderAll();
  return true;
}

function removeSelectedPlacement() {
  const placement = selectedPlacement();
  if (!placement) return false;
  state.placements = state.placements.filter((item) => item.id !== placement.id);
  state.selectedId = state.placements.find((item) => item.page === state.page)?.id || null;
  renderAll();
  setStatus("印影を削除しました。");
  return true;
}

function rotatedPlacementSize(widthMm, heightMm, rotationDegrees) {
  const radians = Number(rotationDegrees || 0) * Math.PI / 180;
  return {
    widthMm: Math.abs(widthMm * Math.cos(radians)) + Math.abs(heightMm * Math.sin(radians)),
    heightMm: Math.abs(widthMm * Math.sin(radians)) + Math.abs(heightMm * Math.cos(radians)),
  };
}

function clampPlacement(placement) {
  const page = state.document?.pages[placement.page];
  if (!page) return;
  placement.widthMm = Math.max(0.1, Math.min(500, Number(placement.widthMm ?? placement.sizeMm) || 9.5));
  placement.heightMm = Math.max(0.1, Math.min(500, Number(placement.heightMm ?? placement.sizeMm) || 9.5));
  placement.rotationDegrees = Math.max(-90, Math.min(90, Math.round((Number(placement.rotationDegrees) || 0) / 5) * 5));
  let bounding = rotatedPlacementSize(placement.widthMm, placement.heightMm, placement.rotationDegrees);
  const scale = Math.min(1, page.widthMm / bounding.widthMm, page.heightMm / bounding.heightMm);
  if (scale < 1) {
    placement.widthMm *= scale;
    placement.heightMm *= scale;
    bounding = rotatedPlacementSize(placement.widthMm, placement.heightMm, placement.rotationDegrees);
  }
  const minX = Math.max(0, bounding.widthMm / 2 - placement.widthMm / 2);
  const minY = Math.max(0, bounding.heightMm / 2 - placement.heightMm / 2);
  const maxX = Math.max(minX, page.widthMm - bounding.widthMm / 2 - placement.widthMm / 2);
  const maxY = Math.max(minY, page.heightMm - bounding.heightMm / 2 - placement.heightMm / 2);
  placement.xMm = Math.max(minX, Math.min(maxX, Number(placement.xMm) || 0));
  placement.yMm = Math.max(minY, Math.min(maxY, Number(placement.yMm) || 0));
}

function renderEditor() {
  const placement = selectedPlacement();
  const enabled = Boolean(placement);
  [elements.width, elements.height, elements.x, elements.y, elements.rotation, elements.removeStamp].forEach((element) => { element.disabled = !enabled; });
  if (!placement) return;
  elements.width.value = round(placement.widthMm);
  elements.height.value = round(placement.heightMm);
  elements.x.value = round(placement.xMm);
  elements.y.value = round(placement.yMm);
  elements.rotation.value = placement.rotationDegrees;
  elements.rotationValue.value = `${placement.rotationDegrees}°`;
}

function renderPageSelect() {
  elements.pageSelect.replaceChildren();
  if (!state.document) {
    elements.pageSelect.disabled = true;
    return;
  }
  state.document.pages.forEach((_, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${index + 1} / ${state.document.pages.length}`;
    option.selected = index === state.page;
    elements.pageSelect.append(option);
  });
  elements.pageSelect.disabled = false;
}

function renderOverlays() {
  elements.stage.querySelectorAll(".stamp-overlay").forEach((node) => node.remove());
  if (!state.document) return;
  const page = currentPageInfo();
  state.placements.filter((placement) => placement.page === state.page).forEach((placement) => {
    const overlay = document.createElement("button");
    overlay.type = "button";
    overlay.className = `stamp-overlay${placement.id === state.selectedId ? " selected" : ""}`;
    overlay.setAttribute("aria-label", "印影を移動");
    overlay.style.left = `${(placement.xMm / page.widthMm) * 100}%`;
    overlay.style.top = `${(placement.yMm / page.heightMm) * 100}%`;
    overlay.style.width = `${(placement.widthMm / page.widthMm) * 100}%`;
    overlay.style.height = `${(placement.heightMm / page.heightMm) * 100}%`;
    overlay.style.transform = `rotate(${placement.rotationDegrees || 0}deg)`;
    const image = document.createElement("img");
    image.alt = "";
    image.src = `/api/stamps/${placement.stampId}/preview`;
    overlay.append(image);
    overlay.addEventListener("pointerdown", (event) => beginDrag(event, placement));
    overlay.addEventListener("click", (event) => {
      event.stopPropagation();
      state.selectedId = placement.id;
      renderAll();
    });
    elements.stage.append(overlay);
  });
}

function beginDrag(event, placement) {
  event.preventDefault();
  state.selectedId = placement.id;
  const page = currentPageInfo();
  const stageRect = elements.stage.getBoundingClientRect();
  const offsetX = ((event.clientX - stageRect.left) / stageRect.width) * page.widthMm - placement.xMm;
  const offsetY = ((event.clientY - stageRect.top) / stageRect.height) * page.heightMm - placement.yMm;
  event.currentTarget.setPointerCapture(event.pointerId);
  const move = (pointerEvent) => {
    placement.xMm = ((pointerEvent.clientX - stageRect.left) / stageRect.width) * page.widthMm - offsetX;
    placement.yMm = ((pointerEvent.clientY - stageRect.top) / stageRect.height) * page.heightMm - offsetY;
    clampPlacement(placement);
    renderOverlays();
    renderEditor();
  };
  const end = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", end);
  renderAll();
}

function renderTemplates() {
  const oldValue = elements.template.value;
  elements.template.replaceChildren();
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = state.templates.length ? "テンプレートを選択" : "保存済みテンプレートはありません";
  elements.template.append(empty);
  state.templates.forEach((template) => {
    const option = document.createElement("option");
    option.value = template.id;
    option.textContent = template.name;
    elements.template.append(option);
  });
  elements.template.value = state.templates.some((template) => template.id === oldValue) ? oldValue : "";
  elements.template.disabled = !state.templatesLoaded || !state.templates.length;
  elements.applyTemplate.disabled = !state.templatesLoaded || !state.document || !state.stamp || !elements.template.value;
  elements.deleteTemplate.disabled = !state.templatesLoaded || !elements.template.value;
  elements.saveTemplate.disabled = !state.templatesLoaded || !state.document || !state.placements.length;
}

function renderRegisteredStamps() {
  const activeId = state.stamp?.registered ? state.stamp.id : "";
  elements.registeredStampSelect.replaceChildren();
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = state.registeredStamps.length ? "登録済み印影を選択" : "登録済み印影はありません";
  elements.registeredStampSelect.append(empty);
  state.registeredStamps.forEach((stamp) => {
    const option = document.createElement("option");
    option.value = stamp.id;
    option.textContent = stamp.filename;
    elements.registeredStampSelect.append(option);
  });
  elements.registeredStampSelect.value = state.registeredStamps.some((stamp) => stamp.id === activeId) ? activeId : "";
  elements.registeredStampSelect.disabled = !state.registeredStampsLoaded || !state.registeredStamps.length;
  elements.registerStamp.disabled = !state.stamp || Boolean(state.stamp.registered);
  elements.deleteRegisteredStamp.disabled = !state.stamp?.registered;
}

function renderSettings() {
  elements.filenameSuffix.value = state.settings.filenameSuffix || DEFAULT_SETTINGS.filenameSuffix;
  elements.batchCollision.value = state.settings.batchCollision || DEFAULT_SETTINGS.batchCollision;
}

function renderBatch() {
  const count = state.batchFiles.length;
  elements.batchName.textContent = count ? `${count}件のPDFを選択中` : "一括処理するPDFは未選択です";
  elements.exportBatch.disabled = !state.document || !state.placements.length || !count;
}

function renderAll({ refreshPreview = false } = {}) {
  renderPageSelect();
  renderEditor();
  renderTemplates();
  renderRegisteredStamps();
  renderBatch();
  elements.addStamp.disabled = !state.document || !state.stamp;
  elements.export.disabled = !state.document || !state.placements.length;
  if (!state.document) return;
  elements.empty.hidden = true;
  elements.scroll.hidden = false;
  elements.title.textContent = state.document.filename;
  if (refreshPreview || !elements.preview.src.includes(`/api/documents/${state.document.id}/pages/${state.page}`)) {
    elements.preview.src = `/api/documents/${state.document.id}/pages/${state.page}?r=${Date.now()}`;
  }
  renderOverlays();
}

function currentStudioFormat() {
  return $("input[name='stampFormat']:checked").value;
}

function studioBodyText() {
  const format = currentStudioFormat();
  if (format === "company") return elements.studioRoleText.value;
  if (format === "company_square") return elements.studioSquareText.value;
  if (format === "stamp") return elements.studioStampText.value;
  return elements.studioText.value;
}

function charactersIn(text) {
  return [...text].filter((character) => character !== "\n" && character !== "\r");
}

function studioBodyCharacters() {
  return charactersIn(studioBodyText());
}

function studioCharacters() {
  if (currentStudioFormat() === "company" && state.studio.glyphTarget === "company") return charactersIn(elements.studioCompanyName.value);
  return studioBodyCharacters();
}

function activeGlyphTransforms() {
  return currentStudioFormat() === "company" && state.studio.glyphTarget === "company" ? state.studio.companyGlyphTransforms : state.studio.glyphTransforms;
}

function editingCompanyRing() {
  return currentStudioFormat() === "company" && state.studio.glyphTarget === "company";
}

function activeGlobalTextSettings() {
  return editingCompanyRing() ? state.studio.globalTextSettings.company : state.studio.globalTextSettings.body;
}

function blankGlobalTextSettings() {
  return { scaleX: 1, scaleY: 1, lineSpacing: 0, letterSpacing: 0, scaleLocked: false };
}

function blankGlyphTransform() {
  return { x: 0, y: 0, scaleX: 1, scaleY: 1 };
}

function selectedGlyphTransform() {
  return activeGlyphTransforms()[state.studio.selectedGlyph] || blankGlyphTransform();
}

function updateGlyphControlValues() {
  const characters = studioCharacters();
  const enabled = Boolean(characters.length);
  const companyRing = editingCompanyRing();
  const transform = selectedGlyphTransform();
  [elements.studioGlyphX, elements.studioGlyphY, elements.studioGlyphScaleX, elements.studioGlyphScaleY, elements.studioGlyphScaleLock, elements.resetSelectedGlyph].forEach((input) => { input.disabled = !enabled; });
  elements.resetAllGlyphs.disabled = !enabled || !Object.keys(activeGlyphTransforms()).length;
  elements.studioGlyphX.value = transform.x;
  elements.studioGlyphY.value = transform.y;
  elements.studioGlyphScaleX.value = transform.scaleX;
  elements.studioGlyphScaleY.value = transform.scaleY;
  elements.glyphXValue.value = transform.x;
  elements.glyphYValue.value = transform.y;
  elements.glyphScaleXValue.value = Number(transform.scaleX).toFixed(2);
  elements.glyphScaleYValue.value = Number(transform.scaleY).toFixed(2);
  elements.glyphXLabel.textContent = companyRing ? "接線方向の位置" : "横位置";
  elements.glyphYLabel.textContent = companyRing ? "法線方向の位置" : "縦位置";
  elements.glyphScaleXLabel.textContent = companyRing ? "接線方向倍率" : "横倍率";
  elements.glyphScaleYLabel.textContent = companyRing ? "法線方向倍率" : "縦倍率";
  elements.studioGlyphX.setAttribute("aria-label", companyRing ? "選択中の外周文字の接線方向位置" : "選択中の文字の横位置");
  elements.studioGlyphY.setAttribute("aria-label", companyRing ? "選択中の外周文字の法線方向位置" : "選択中の文字の縦位置");
  elements.studioGlyphScaleX.setAttribute("aria-label", companyRing ? "選択中の外周文字の接線方向倍率" : "選択中の文字の横倍率");
  elements.studioGlyphScaleY.setAttribute("aria-label", companyRing ? "選択中の外周文字の法線方向倍率" : "選択中の文字の縦倍率");
  elements.glyphEditorHint.textContent = companyRing
    ? "接線方向は円周に沿って、法線方向は円の内外へ移動します。倍率を変えても文字中心は円周上に保たれます。"
    : "編集する文字を選び、枠に触れる位置まで移動・拡大できます。";
}

function updateGlobalTextControlValues() {
  const settings = activeGlobalTextSettings();
  const companyRing = editingCompanyRing();
  elements.studioGlobalScaleX.value = settings.scaleX;
  elements.studioGlobalScaleY.value = settings.scaleY;
  elements.studioGlobalScaleLock.checked = settings.scaleLocked;
  elements.studioGlobalLineSpacing.value = settings.lineSpacing;
  elements.studioGlobalLetterSpacing.value = settings.letterSpacing;
  elements.globalScaleXValue.value = Number(settings.scaleX).toFixed(2);
  elements.globalScaleYValue.value = Number(settings.scaleY).toFixed(2);
  elements.globalLineSpacingValue.value = Number(settings.lineSpacing).toFixed(2);
  elements.globalLetterSpacingValue.value = Number(settings.letterSpacing).toFixed(2);
  elements.studioCompanyEndGapField.hidden = !companyRing;
  elements.studioCompanyRingOffsetField.hidden = !companyRing;
  elements.studioGlobalLineSpacingField.hidden = companyRing;
  elements.studioGlobalLetterSpacingField.hidden = companyRing;
  elements.globalScaleXLabel.textContent = companyRing ? "全体の接線方向倍率" : "全体の横倍率";
  elements.globalScaleYLabel.textContent = companyRing ? "全体の法線方向倍率" : "全体の縦倍率";
  elements.globalTextHint.textContent = companyRing
    ? "外周文字の始終余白・内円からの距離と、接線・法線方向の全体倍率を調整します。"
    : "個別文字を調整する前の、全体の倍率・行間・文字間です。";
}

function renderGlyphEditor() {
  const characters = studioCharacters();
  if (state.studio.selectedGlyph >= characters.length) state.studio.selectedGlyph = Math.max(0, characters.length - 1);
  const transforms = activeGlyphTransforms();
  Object.keys(transforms).forEach((index) => {
    if (Number(index) >= characters.length) delete transforms[index];
  });
  elements.studioGlyphList.replaceChildren();
  characters.forEach((character, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `glyph-button${index === state.studio.selectedGlyph ? " is-active" : ""}`;
    const space = character === " " ? "半角スペース" : character === "　" ? "全角スペース" : character;
    button.textContent = character === " " ? "␠" : character === "　" ? "□" : character;
    button.setAttribute("aria-label", `${index + 1}文字目「${space}」を編集`);
    button.addEventListener("click", () => {
      state.studio.selectedGlyph = index;
      renderGlyphEditor();
    });
    elements.studioGlyphList.append(button);
  });
  updateGlyphControlValues();
  updateGlobalTextControlValues();
}

function matchingFontFamilies() {
  const keyword = elements.studioFontFilter.value.trim().toLocaleLowerCase();
  const families = new Map();
  state.fonts.forEach((font) => {
    const searchable = `${font.family} ${font.familyEnglish} ${font.name} ${font.nameEnglish} ${font.style} ${font.styleEnglish}`.toLocaleLowerCase();
    if (keyword && !searchable.includes(keyword)) return;
    if (!families.has(font.familyId)) families.set(font.familyId, { id: font.familyId, name: font.family, english: font.familyEnglish, faces: [] });
    families.get(font.familyId).faces.push(font);
  });
  return [...families.values()];
}

function renderStudioFontFaces(preferredFaceId = "") {
  const oldValue = preferredFaceId || elements.studioFont.value;
  const family = matchingFontFamilies().find((item) => item.id === elements.studioFontFamily.value);
  const faces = family?.faces || [];
  elements.studioFont.replaceChildren();
  if (!faces.length) {
    const option = document.createElement("option");
    option.textContent = "利用できるウェイトがありません";
    elements.studioFont.append(option);
    elements.studioFont.disabled = true;
    return;
  }
  faces.forEach((font) => {
    const option = document.createElement("option");
    option.value = font.id;
    const style = font.style || font.styleEnglish || "Regular";
    option.textContent = `${style}（ウェイト ${font.weight}）`;
    option.title = font.name;
    elements.studioFont.append(option);
  });
  const regular = [...faces].sort((a, b) => Math.abs(a.weight - 400) - Math.abs(b.weight - 400))[0];
  elements.studioFont.value = faces.some((font) => font.id === oldValue) ? oldValue : regular.id;
  elements.studioFont.disabled = false;
  scheduleStudioPreview();
}

function renderStudioFonts() {
  const oldFamily = elements.studioFontFamily.value;
  const oldFace = elements.studioFont.value;
  const families = matchingFontFamilies();
  elements.studioFontFamily.replaceChildren();
  if (!families.length) {
    const option = document.createElement("option");
    option.textContent = elements.studioFontFilter.value.trim() ? "一致する書体がありません" : "利用可能なフォントがありません";
    elements.studioFontFamily.append(option);
    elements.studioFontFamily.disabled = true;
    elements.studioFont.replaceChildren();
    elements.studioFont.disabled = true;
    return;
  }
  families.forEach((family) => {
    const option = document.createElement("option");
    option.value = family.id;
    option.textContent = family.name === family.english ? family.name : `${family.name} / ${family.english}`;
    elements.studioFontFamily.append(option);
  });
  const preferred = families.find((family) => family.name === "ヒラギノ角ゴシック" || family.english === "Hiragino Sans")
    || families.find((family) => /ヒラギノ角ゴ|游ゴシック|Yu Gothic/i.test(`${family.name} ${family.english}`)) || families[0];
  elements.studioFontFamily.value = families.some((family) => family.id === oldFamily) ? oldFamily : preferred.id;
  elements.studioFontFamily.disabled = false;
  renderStudioFontFaces(oldFace);
}

function glyphTransformsPayload(transforms, count) {
  return Object.entries(transforms)
    .map(([index, transform]) => ({ index: Number(index), ...transform }))
    .filter((item) => item.index < count);
}

function studioPayload() {
  const format = currentStudioFormat();
  const bodySettings = state.studio.globalTextSettings.body;
  const companySettings = state.studio.globalTextSettings.company;
  return {
    format, sizeMm: Number(elements.studioSize.value),
    text: elements.studioText.value, squareText: elements.studioSquareText.value, stampText: elements.studioStampText.value, stampLengthMm: Number(elements.studioSize.value), stampOrientation: $("input[name='stampOrientation']:checked").value, companyName: elements.studioCompanyName.value, roleText: elements.studioRoleText.value,
    fontId: elements.studioFont.value,
    direction: $("input[name='direction']:checked").value,
    representation: format === "stamp" ? "outline" : $("input[name='representation']:checked").value,
    frame: elements.studioFrame.value, color: elements.studioColor.value,
    frameWidth: Number(elements.studioFrameWidth.value), padding: Number(elements.studioPadding.value), companyRingOffsetMm: Number(elements.studioCompanyRingOffset.value), companyEndGapMm: Number(elements.studioCompanyEndGap.value), cornerRadiusMm: Number(elements.studioCornerRadius.value),
    lineWidth: Number(elements.studioLineWidth.value), lineAngleSnap: Number(elements.studioLineAngleSnap.value), lineDetail: 240,
    textScaleX: bodySettings.scaleX, textScaleY: bodySettings.scaleY, lineSpacing: bodySettings.lineSpacing, letterSpacing: bodySettings.letterSpacing,
    companyTextScaleX: companySettings.scaleX, companyTextScaleY: companySettings.scaleY,
    embedMetadata: elements.studioEmbedMetadata.checked,
    glyphTransforms: glyphTransformsPayload(state.studio.glyphTransforms, studioBodyCharacters().length),
    companyGlyphTransforms: glyphTransformsPayload(state.studio.companyGlyphTransforms, charactersIn(elements.studioCompanyName.value).length),
    svgAssets: state.studio.svgAssets.map(({ id, xPercent, yPercent, sizePercent, colorTargets }) => ({ assetId: id, xPercent, yPercent, sizePercent, colorTargets })),
  };
}

function renderStudioFormat() {
  const format = currentStudioFormat();
  const company = format === "company";
  const square = format === "company_square";
  const stamp = format === "stamp";
  elements.personalStampFields.hidden = format !== "personal";
  elements.companyStampFields.hidden = !company;
  elements.squareStampFields.hidden = !square;
  elements.stampStampFields.hidden = !stamp;
  elements.studioDirectionField.hidden = stamp;
  elements.studioRepresentationField.hidden = stamp;
  elements.studioFrameField.hidden = format !== "personal";
  elements.studioPaddingField.hidden = company;
  elements.studioCornerRadiusField.hidden = !square && !stamp;
  elements.studioGlyphTargetField.hidden = !company;
  if (!company) state.studio.glyphTarget = "body";
  elements.studioGlyphTarget.value = state.studio.glyphTarget;
  if (stamp) $("input[name='representation'][value='outline']").checked = true;
  const oldSize = elements.studioSize.value;
  elements.studioFrameWidth.min = stamp ? "0" : "6";
  if (!stamp && Number(elements.studioFrameWidth.value) < 6) elements.studioFrameWidth.value = "22";
  const sizes = company
    ? [["18", "18mm・会社認印（標準）"], ["16.5", "16.5mm・会社認印（小さめ）"]]
    : square
      ? [["21", "21mm・会社角印（標準）"], ["24", "24mm・会社角印（大きめ）"]]
      : stamp
        ? [["27", "13 × 27mm・標準"], ["42", "13 × 42mm・大きめ"]]
        : [["9.5", "9.5mm・ネーム印"], ["10.5", "10.5mm・標準"], ["12", "12mm・大きめ"]];
  elements.studioSize.replaceChildren();
  sizes.forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    elements.studioSize.append(option);
  });
  elements.studioSize.value = sizes.some(([value]) => value === oldSize) ? oldSize : sizes[0][0];
  renderGlyphEditor();
  renderSvgAssets();
}

function renderStudioControls() {
  elements.frameWidthValue.value = elements.studioFrameWidth.value;
  elements.paddingValue.value = elements.studioPadding.value;
  elements.companyEndGapValue.value = `${Number(elements.studioCompanyEndGap.value).toFixed(1)}mm`;
  elements.companyRingOffsetValue.value = `${Number(elements.studioCompanyRingOffset.value).toFixed(1)}mm`;
  elements.cornerRadiusValue.value = `${Number(elements.studioCornerRadius.value).toFixed(1)}mm`;
  elements.lineWidthValue.value = elements.studioLineWidth.value;
  const format = currentStudioFormat();
  const stamp = format === "stamp";
  elements.lineAngleSnapValue.value = Number(elements.studioLineAngleSnap.value) ? `±${elements.studioLineAngleSnap.value}°` : "補正なし";
  const geometric = !stamp && $("input[name='representation']:checked").value === "geometric";
  elements.studioLineWidthField.hidden = !geometric;
  elements.studioLineAngleSnapField.hidden = !geometric;
  elements.studioLineWidth.disabled = !geometric;
  elements.studioLineAngleSnap.disabled = !geometric;
  const company = format === "company";
  const body = studioBodyText().replaceAll("\n", "／") || "文字なし";
  const companyName = elements.studioCompanyName.value || "文字なし";
  elements.studioCaption.textContent = company ? `［${companyName}｜${body}］` : `［${body}］`;
  const formatName = format === "company" ? "会社認印" : format === "company_square" ? "会社角印" : stamp ? "スタンプ" : "個人丸印";
  const orientation = $("input[name='stampOrientation']:checked").value;
  const stampDimensions = stamp ? (orientation === "horizontal" ? `${elements.studioSize.value} × 13mm・横型` : `13 × ${elements.studioSize.value}mm・縦型`) : `${elements.studioSize.value}mm`;
  elements.studioFormatBadge.textContent = `${formatName}・${stampDimensions}`;
  elements.studioPreviewPaper.style.aspectRatio = stamp
    ? (orientation === "horizontal" ? `${elements.studioSize.value} / 13` : `13 / ${elements.studioSize.value}`)
    : "1 / 1";
  renderColorQuickPicks();
}

function renderColorQuickPicks() {
  const palette = currentStudioFormat() === "stamp"
    ? [
      ["#e70013", "赤", "RGB 231, 0, 19"], ["#000000", "黒", "RGB 0, 0, 0"],
      ["#0097e1", "藍", "RGB 0, 151, 225"], ["#009946", "緑", "RGB 0, 153, 70"],
      ["#ed6d00", "朱", "RGB 237, 109, 0"], ["#4d4499", "紫", "RGB 77, 68, 153"],
    ]
    : [
      ["#d94236", "JIS標準", "RGB 217, 66, 54"], ["#ca3833", "深紅", "RGB 202, 56, 51"], ["#e94709", "朱色", "RGB 233, 71, 9"],
    ];
  elements.colorQuickPicks.replaceChildren();
  palette.forEach(([color, label, rgb]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `color-quick-pick${color === elements.studioColor.value.toLowerCase() ? " is-active" : ""}`;
    button.dataset.stampColor = color;
    button.style.setProperty("--stamp-color", color);
    button.setAttribute("aria-label", `${label}（${rgb}）`);
    button.textContent = label;
    button.addEventListener("click", () => { elements.studioColor.value = color; scheduleStudioPreview(); });
    elements.colorQuickPicks.append(button);
  });
}

function scheduleStudioPreview() {
  renderStudioControls();
  const version = ++state.studio.version;
  clearTimeout(state.studio.timer);
  elements.useStudioStamp.disabled = true;
  elements.downloadStudioSvg.disabled = true;
  if (elements.studioFont.disabled || !elements.studioFont.value) return;
  setStudioStatus("プレビューを更新しています…");
  state.studio.timer = window.setTimeout(() => { void refreshStudioPreview(version); }, 180);
}

function selectedSvgAsset() {
  return state.studio.svgAssets.find((asset) => asset.id === state.studio.selectedSvgAssetId) || null;
}

function clearSelectedStudioSvgAsset() {
  if (!selectedSvgAsset()) return false;
  state.studio.selectedSvgAssetId = null;
  renderSvgAssets();
  return true;
}

function removeSelectedStudioSvgAsset() {
  const asset = selectedSvgAsset();
  if (!asset) return false;
  state.studio.svgAssets = state.studio.svgAssets.filter((item) => item.id !== asset.id);
  state.studio.selectedSvgAssetId = state.studio.svgAssets.at(-1)?.id || null;
  renderSvgAssets();
  scheduleStudioPreview();
  setStudioStatus("選択中のSVGを削除しました。");
  return true;
}

function renderSvgAssets() {
  const asset = selectedSvgAsset();
  elements.studioSvgAssetList.replaceChildren();
  state.studio.svgAssets.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `svg-asset-button${item.id === state.studio.selectedSvgAssetId ? " is-active" : ""}`;
    button.textContent = `${index + 1}. ${item.filename}`;
    button.title = item.filename;
    button.addEventListener("click", () => { state.studio.selectedSvgAssetId = item.id; renderSvgAssets(); });
    elements.studioSvgAssetList.append(button);
  });
  elements.studioSvgAssetControls.hidden = !asset;
  if (asset) {
    elements.studioSvgAssetX.value = asset.xPercent;
    elements.studioSvgAssetY.value = asset.yPercent;
    elements.studioSvgAssetSize.value = asset.sizePercent;
    elements.studioSvgColorFill.checked = asset.colorTargets.fill;
    elements.studioSvgColorStroke.checked = asset.colorTargets.stroke;
    elements.studioSvgColorInherited.checked = asset.colorTargets.inherited;
    elements.svgAssetXValue.value = `${asset.xPercent}%`;
    elements.svgAssetYValue.value = `${asset.yPercent}%`;
    elements.svgAssetSizeValue.value = `${asset.sizePercent}%`;
  }
  renderStudioSvgPreviewAssets();
}

function studioCanvasDimensions() {
  if (currentStudioFormat() !== "stamp") return { width: 1000, height: 1000 };
  const longSide = Number(elements.studioSize.value);
  const horizontal = $("input[name='stampOrientation']:checked").value === "horizontal";
  return horizontal ? { width: 1000 * longSide / 13, height: 1000 } : { width: 1000 * 13 / longSide, height: 1000 };
}

function studioSvgPreviewBounds(asset) {
  const dimensions = studioCanvasDimensions();
  const viewBox = Array.isArray(asset.viewBox) ? asset.viewBox.map(Number) : [];
  const sourceWidth = viewBox[2] > 0 ? viewBox[2] : 1;
  const sourceHeight = viewBox[3] > 0 ? viewBox[3] : 1;
  const longSide = Math.min(dimensions.width, dimensions.height) * asset.sizePercent / 100;
  const width = sourceWidth >= sourceHeight ? longSide : longSide * sourceWidth / sourceHeight;
  const height = sourceWidth >= sourceHeight ? longSide * sourceHeight / sourceWidth : longSide;
  return {
    left: dimensions.width * asset.xPercent / 100 - width / 2,
    top: dimensions.height * asset.yPercent / 100 - height / 2,
    width,
    height,
    canvasWidth: dimensions.width,
    canvasHeight: dimensions.height,
  };
}

function renderStudioSvgPreviewAssets() {
  elements.studioSvgPreviewAssets.replaceChildren();
  state.studio.svgAssets.forEach((asset, index) => {
    const bounds = studioSvgPreviewBounds(asset);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `studio-svg-preview-asset${asset.id === state.studio.selectedSvgAssetId ? " is-active" : ""}`;
    button.setAttribute("aria-label", `${index + 1}. ${asset.filename}を選択`);
    button.title = `${index + 1}. ${asset.filename}`;
    button.style.left = `${bounds.left / bounds.canvasWidth * 100}%`;
    button.style.top = `${bounds.top / bounds.canvasHeight * 100}%`;
    button.style.width = `${bounds.width / bounds.canvasWidth * 100}%`;
    button.style.height = `${bounds.height / bounds.canvasHeight * 100}%`;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      state.studio.selectedSvgAssetId = asset.id;
      renderSvgAssets();
      setStudioStatus(`${index + 1}. ${asset.filename}を選択しました。Delete／Backspaceで削除できます。`);
    });
    elements.studioSvgPreviewAssets.append(button);
  });
}

async function loadStudioSvgAsset(file) {
  if (!file || !/\.svg$/i.test(file.name) && file.type !== "image/svg+xml") {
    setStudioStatus("配置できるのはSVGファイルだけです。", true);
    return;
  }
  setStudioStatus("SVGを読み込んでいます…");
  try {
    const asset = await upload(file, "/api/stamp-design-assets");
    state.studio.svgAssets.push({ id: asset.id, filename: asset.filename, viewBox: asset.viewBox, xPercent: 50, yPercent: 50, sizePercent: 30, colorTargets: { fill: false, stroke: false, inherited: false } });
    state.studio.selectedSvgAssetId = asset.id;
    renderSvgAssets();
    scheduleStudioPreview();
  } catch (error) {
    setStudioStatus(error.message, true);
  }
}

async function refreshStudioPreview(version) {
  try {
    const response = await fetch("/api/stamp-designs/preview", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(studioPayload()),
    });
    if (!response.ok) throw new Error(await readError(response));
    const svg = await response.blob();
    if (version !== state.studio.version) return;
    if (state.studio.previewUrl) URL.revokeObjectURL(state.studio.previewUrl);
    state.studio.previewUrl = URL.createObjectURL(svg);
    elements.studioPreview.src = state.studio.previewUrl;
    elements.useStudioStamp.disabled = false;
    elements.downloadStudioSvg.disabled = false;
    const lineBased = currentStudioFormat() !== "stamp" && $("input[name='representation']:checked").value === "geometric";
    setStudioStatus(lineBased ? "文字の中心線をSVGパス化したプレビューです。線幅と傾き吸着を調整できます。" : "SVGの輪郭プレビューです。設定をさらに調整できます。");
  } catch (error) {
    if (version !== state.studio.version) return;
    setStudioStatus(error.message, true);
  }
}

function showView(view) {
  const studio = view === "studio";
  elements.editorView.hidden = studio;
  elements.studioView.hidden = !studio;
  elements.tabs.forEach((tab) => tab.classList.toggle("is-active", tab.dataset.view === view));
  if (studio) {
    void loadFonts();
    scheduleStudioPreview();
  }
}

function round(value) { return Math.round(value * 10) / 10; }

function isStampFile(file) {
  const extension = file?.name?.split(".").at(-1)?.toLowerCase();
  return Boolean(extension && STAMP_EXTENSIONS.has(extension));
}

function stampFitsPreviewDrop(stamp) {
  const maximumSize = Math.max(Number(stamp.defaultWidthMm) || 0, Number(stamp.defaultHeightMm) || 0);
  return !stamp.sizeDetected || maximumSize <= PREVIEW_DROP_STAMP_MAX_MM;
}

function useStamp(stamp, label, { addToPage = true } = {}) {
  state.stamp = stamp;
  elements.stampName.textContent = label;
  if (state.document && addToPage) newPlacement(); else renderAll();
}

async function loadDocument(file) {
  setStatus("PDFを読み込んでいます…");
  try {
    state.document = await upload(file, "/api/documents");
    state.page = 0;
    state.placements = [];
    state.selectedId = null;
    elements.documentName.textContent = file.name;
    renderAll({ refreshPreview: true });
    setStatus(`${state.document.pages.length}ページのPDFを読み込みました。`);
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadStamp(file) {
  setStatus("印影を読み込んでいます…");
  try {
    const stamp = await upload(file, "/api/stamps");
    const maximumSize = Math.max(Number(stamp.defaultWidthMm) || 0, Number(stamp.defaultHeightMm) || 0);
    if (stamp.sizeDetected && maximumSize > PREVIEW_DROP_STAMP_MAX_MM && !window.confirm(`このファイルから ${round(stamp.defaultWidthMm)} × ${round(stamp.defaultHeightMm)}mm のサイズを検出しました。印影ファイルとして使用しますか？`)) {
      setStatus("印影の読み込みを取り消しました。");
      return;
    }
    useStamp(stamp, file.name);
    setStatus(state.document ? "印影を追加しました。位置を調整してください。" : "印影を読み込みました。次にPDFを選択してください。");
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function loadPreviewDrop(file) {
  if (!state.document || !isStampFile(file)) {
    await loadDocument(file);
    return;
  }
  setStatus("ドロップしたファイルを確認しています…");
  try {
    const stamp = await upload(file, "/api/stamps");
    if (stampFitsPreviewDrop(stamp)) {
      useStamp(stamp, file.name);
      setStatus("印影を追加しました。位置を調整してください。");
      return;
    }
  } catch (error) {
    if (!/\.pdf$/i.test(file.name)) {
      setStatus(error.message, true);
      return;
    }
  }
  await loadDocument(file);
}

async function registerCurrentStamp() {
  if (!state.stamp || state.stamp.registered) return;
  elements.registerStamp.disabled = true;
  try {
    const response = await fetch(`/api/stamps/${state.stamp.id}/register`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: state.stamp.filename || elements.stampName.textContent }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const stamp = await response.json();
    state.registeredStamps = [stamp, ...state.registeredStamps];
    useStamp(stamp, `登録済み印影：${stamp.filename}`, { addToPage: false });
    setStatus(`「${stamp.filename}」をこのPCへ登録しました。`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    renderRegisteredStamps();
  }
}

async function createStudioStamp(action) {
  const button = action === "use" ? elements.useStudioStamp : elements.downloadStudioSvg;
  button.disabled = true;
  setStudioStatus(action === "use" ? "SVG印影を作成しています…" : "SVGを書き出す準備をしています…");
  try {
    const response = await fetch("/api/stamps/generated", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(studioPayload()),
    });
    if (!response.ok) throw new Error(await readError(response));
    const stamp = await response.json();
    if (action === "use") {
      const format = currentStudioFormat();
      const label = format === "company" ? elements.studioCompanyName.value : studioBodyText().replaceAll("\n", "／");
      useStamp(stamp, `作成したSVG印影：${label}`);
      showView("editor");
      setStatus(state.document ? "作成したSVG印影を追加しました。位置を調整してください。" : "SVG印影を作成しました。次にPDFを選択してください。");
    } else {
      const saved = await saveStudioSvg(stamp);
      setStudioStatus(saved ? "SVGを保存しました。" : "SVGの保存を取り消しました。");
    }
  } catch (error) {
    setStudioStatus(error.message, true);
  } finally {
    if (state.studio.version) {
      elements.useStudioStamp.disabled = false;
      elements.downloadStudioSvg.disabled = false;
    }
  }
}

async function saveStudioSvg(stamp) {
  const nativeSave = window.pywebview?.api?.save_stamp_source;
  if (window.pywebview) {
    if (!nativeSave) throw new Error("SVG保存機能を初期化できませんでした。アプリを再起動してから、もう一度お試しください。");
    const result = await nativeSave(stamp.id, stamp.filename);
    return Boolean(result?.saved);
  }
  const link = document.createElement("a");
  link.href = stamp.downloadUrl;
  link.download = stamp.filename;
  document.body.append(link);
  link.click();
  link.remove();
  return true;
}

function bindFilePicker(picker, input, loadFile) {
  input.addEventListener("change", () => {
    const file = input.files[0];
    input.value = "";
    if (file) void loadFile(file);
  });
  bindDropTarget(picker, (files) => { if (files[0]) void loadFile(files[0]); });
}

function bindDropTarget(picker, receiveFiles) {
  let dragDepth = 0;
  picker.addEventListener("dragenter", (event) => {
    event.preventDefault();
    dragDepth += 1;
    picker.classList.add("is-dragging");
  });
  picker.addEventListener("dragover", (event) => event.preventDefault());
  picker.addEventListener("dragleave", (event) => {
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) picker.classList.remove("is-dragging");
  });
  picker.addEventListener("drop", (event) => {
    event.preventDefault();
    dragDepth = 0;
    picker.classList.remove("is-dragging");
    receiveFiles([...(event.dataTransfer?.files || [])]);
  });
}

function loadBatchFiles(files) {
  state.batchFiles = files;
  renderBatch();
  setStatus(files.length ? `${files.length}件を一括処理用に選択しました。` : "一括処理するPDFを選択してください。");
}

function bindBatchPicker() {
  elements.batchInput.addEventListener("change", () => {
    const files = [...elements.batchInput.files];
    elements.batchInput.value = "";
    loadBatchFiles(files);
  });
  bindDropTarget(elements.batchPicker, loadBatchFiles);
}

window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => {
  if (!event.target.closest("[data-file-picker], #previewWorkspace, #studioPreviewPaper")) {
    event.preventDefault();
    setStatus("PDFまたは印影の枠へファイルをドロップしてください。", true);
  }
});

bindFilePicker(elements.pdfPicker, elements.pdfInput, loadDocument);
bindFilePicker(elements.stampPicker, elements.stampInput, loadStamp);
bindFilePicker(elements.studioSvgPicker, elements.studioSvgInput, loadStudioSvgAsset);
bindDropTarget(elements.workspace, (files) => { if (files[0]) void loadPreviewDrop(files[0]); });
bindDropTarget(elements.studioPreviewPaper, (files) => { if (files[0]) void loadStudioSvgAsset(files[0]); });
bindBatchPicker();

elements.stage.addEventListener("click", (event) => {
  if (event.target instanceof Element && event.target.closest(".stamp-overlay")) return;
  clearSelectedPlacement();
});
elements.studioPreviewPaper.addEventListener("click", (event) => {
  if (event.target instanceof Element && event.target.closest(".studio-svg-preview-asset")) return;
  clearSelectedStudioSvgAsset();
});

elements.tabs.forEach((tab) => tab.addEventListener("click", () => showView(tab.dataset.view)));
elements.studioFontFilter.addEventListener("input", renderStudioFonts);
elements.studioFontFamily.addEventListener("change", () => renderStudioFontFaces());
$$('input[name="stampFormat"]').forEach((input) => input.addEventListener("change", () => {
  state.studio.glyphTransforms = {};
  state.studio.companyGlyphTransforms = {};
  state.studio.globalTextSettings = { body: blankGlobalTextSettings(), company: blankGlobalTextSettings() };
  state.studio.selectedGlyph = 0;
  state.studio.glyphTarget = "body";
  const format = currentStudioFormat();
  const direction = format === "stamp" ? $("input[name='stampOrientation']:checked").value : format === "personal" ? "horizontal" : "vertical";
  $(`input[name="direction"][value="${direction}"]`).checked = true;
  if (format === "stamp") {
    $("input[name='representation'][value='outline']").checked = true;
    elements.studioColor.value = "#e70013";
  }
  renderStudioFormat();
  scheduleStudioPreview();
}));
$$('input[name="stampOrientation"]').forEach((input) => input.addEventListener("change", () => {
  $(`input[name="direction"][value="${input.value}"]`).checked = true;
  renderStudioFormat();
  scheduleStudioPreview();
}));
elements.studioGlyphTarget.addEventListener("change", () => {
  state.studio.glyphTarget = elements.studioGlyphTarget.value;
  state.studio.selectedGlyph = 0;
  renderGlyphEditor();
});
[elements.studioText, elements.studioRoleText, elements.studioSquareText, elements.studioStampText].forEach((input) => input.addEventListener("input", () => {
  state.studio.glyphTransforms = {};
  state.studio.selectedGlyph = 0;
  renderGlyphEditor();
  scheduleStudioPreview();
}));
elements.studioCompanyName.addEventListener("input", () => {
  state.studio.companyGlyphTransforms = {};
  state.studio.selectedGlyph = 0;
  if (state.studio.glyphTarget === "company") renderGlyphEditor();
  scheduleStudioPreview();
});
[
  elements.studioSize, elements.studioFont, elements.studioFrame, elements.studioColor,
  elements.studioFrameWidth, elements.studioPadding, elements.studioCompanyEndGap, elements.studioCompanyRingOffset, elements.studioCornerRadius, elements.studioLineWidth, elements.studioLineAngleSnap, elements.studioEmbedMetadata,
  ...$$('input[name="direction"]'), ...$$('input[name="representation"]'),
].forEach((input) => {
  input.addEventListener("input", scheduleStudioPreview);
  input.addEventListener("change", scheduleStudioPreview);
});
[elements.studioGlyphX, elements.studioGlyphY, elements.studioGlyphScaleX, elements.studioGlyphScaleY].forEach((input) => {
  input.addEventListener("input", () => {
    if (elements.studioGlyphScaleLock.checked && input === elements.studioGlyphScaleX) elements.studioGlyphScaleY.value = input.value;
    if (elements.studioGlyphScaleLock.checked && input === elements.studioGlyphScaleY) elements.studioGlyphScaleX.value = input.value;
    activeGlyphTransforms()[state.studio.selectedGlyph] = {
      x: Number(elements.studioGlyphX.value), y: Number(elements.studioGlyphY.value),
      scaleX: Number(elements.studioGlyphScaleX.value), scaleY: Number(elements.studioGlyphScaleY.value),
    };
    updateGlyphControlValues();
    scheduleStudioPreview();
  });
});
elements.studioGlobalScaleLock.addEventListener("change", () => {
  activeGlobalTextSettings().scaleLocked = elements.studioGlobalScaleLock.checked;
});
[elements.studioGlobalScaleX, elements.studioGlobalScaleY, elements.studioGlobalLineSpacing, elements.studioGlobalLetterSpacing].forEach((input) => {
  input.addEventListener("input", () => {
    const settings = activeGlobalTextSettings();
    if (settings.scaleLocked && input === elements.studioGlobalScaleX) elements.studioGlobalScaleY.value = input.value;
    if (settings.scaleLocked && input === elements.studioGlobalScaleY) elements.studioGlobalScaleX.value = input.value;
    settings.scaleX = Number(elements.studioGlobalScaleX.value);
    settings.scaleY = Number(elements.studioGlobalScaleY.value);
    settings.lineSpacing = Number(elements.studioGlobalLineSpacing.value);
    settings.letterSpacing = Number(elements.studioGlobalLetterSpacing.value);
    updateGlobalTextControlValues();
    scheduleStudioPreview();
  });
});
elements.resetGlobalText.addEventListener("click", () => {
  state.studio.globalTextSettings[editingCompanyRing() ? "company" : "body"] = blankGlobalTextSettings();
  if (editingCompanyRing()) {
    elements.studioCompanyEndGap.value = elements.studioCompanyEndGap.defaultValue;
    elements.studioCompanyRingOffset.value = elements.studioCompanyRingOffset.defaultValue;
  }
  updateGlobalTextControlValues();
  scheduleStudioPreview();
});
elements.resetSelectedGlyph.addEventListener("click", () => {
  delete activeGlyphTransforms()[state.studio.selectedGlyph];
  updateGlyphControlValues();
  scheduleStudioPreview();
});
elements.resetAllGlyphs.addEventListener("click", () => {
  const transforms = activeGlyphTransforms();
  Object.keys(transforms).forEach((index) => { delete transforms[index]; });
  updateGlyphControlValues();
  scheduleStudioPreview();
});
[
  elements.studioSvgAssetX, elements.studioSvgAssetY, elements.studioSvgAssetSize,
].forEach((input) => input.addEventListener("input", () => {
  const asset = selectedSvgAsset();
  if (!asset) return;
  asset.xPercent = Number(elements.studioSvgAssetX.value);
  asset.yPercent = Number(elements.studioSvgAssetY.value);
  asset.sizePercent = Number(elements.studioSvgAssetSize.value);
  renderSvgAssets();
  scheduleStudioPreview();
}));
elements.removeStudioSvgAsset.addEventListener("click", () => {
  removeSelectedStudioSvgAsset();
});
[
  elements.studioSvgColorFill, elements.studioSvgColorStroke, elements.studioSvgColorInherited,
].forEach((input) => input.addEventListener("change", () => {
  const asset = selectedSvgAsset();
  if (!asset) return;
  asset.colorTargets = {
    fill: elements.studioSvgColorFill.checked,
    stroke: elements.studioSvgColorStroke.checked,
    inherited: elements.studioSvgColorInherited.checked,
  };
  scheduleStudioPreview();
}));
elements.useStudioStamp.addEventListener("click", () => { void createStudioStamp("use"); });
elements.downloadStudioSvg.addEventListener("click", () => { void createStudioStamp("download"); });

elements.addStamp.addEventListener("click", newPlacement);
elements.registerStamp.addEventListener("click", () => { void registerCurrentStamp(); });
elements.registeredStampSelect.addEventListener("change", () => {
  const stamp = state.registeredStamps.find((item) => item.id === elements.registeredStampSelect.value);
  if (!stamp) return;
  useStamp(stamp, `登録済み印影：${stamp.filename}`, { addToPage: false });
  setStatus(`登録済み印影「${stamp.filename}」を選択しました。`);
});
elements.deleteRegisteredStamp.addEventListener("click", async () => {
  const stamp = state.stamp;
  if (!stamp?.registered || !window.confirm(`登録済み印影「${stamp.filename}」を削除しますか？`)) return;
  try {
    const response = await fetch(`/api/registered-stamps/${stamp.id}`, { method: "DELETE" });
    if (!response.ok) throw new Error(await readError(response));
    state.registeredStamps = state.registeredStamps.filter((item) => item.id !== stamp.id);
    state.placements = state.placements.filter((placement) => placement.stampId !== stamp.id);
    state.selectedId = state.placements.find((placement) => placement.page === state.page)?.id || null;
    state.stamp = null;
    elements.stampName.textContent = "印影は未選択です";
    renderAll();
    setStatus("登録済み印影を削除しました。");
  } catch (error) {
    setStatus(error.message, true);
  }
});
elements.removeStamp.addEventListener("click", () => {
  removeSelectedPlacement();
});

[elements.width, elements.height, elements.x, elements.y, elements.rotation].forEach((input) => {
  input.addEventListener("input", () => {
    const placement = selectedPlacement();
    if (!placement) return;
    placement.widthMm = Number(elements.width.value);
    placement.heightMm = Number(elements.height.value);
    placement.xMm = Number(elements.x.value);
    placement.yMm = Number(elements.y.value);
    placement.rotationDegrees = Number(elements.rotation.value);
    clampPlacement(placement);
    renderAll();
  });
});

elements.pageSelect.addEventListener("change", () => {
  state.page = Number(elements.pageSelect.value);
  state.selectedId = state.placements.find((item) => item.page === state.page)?.id || null;
  renderAll({ refreshPreview: true });
});

elements.template.addEventListener("change", renderTemplates);
elements.saveTemplate.addEventListener("click", async () => {
  const name = window.prompt("テンプレート名を入力してください", "A4・請求書右上");
  if (!name?.trim()) return;
  const beforeSave = state.templates;
  const template = {
    id: crypto.randomUUID(), name: name.trim(),
    placements: state.placements.map(({ page, xMm, yMm, widthMm, heightMm, rotationDegrees }) => ({ page, xMm, yMm, widthMm, heightMm, rotationDegrees })),
  };
  state.templates = [template, ...state.templates];
  try {
    await persistTemplates();
    elements.template.value = template.id;
    renderTemplates();
    setStatus(`「${name.trim()}」をこのPCに保存しました。`);
  } catch (error) {
    state.templates = beforeSave;
    renderTemplates();
    setStatus(error.message, true);
  }
});

elements.applyTemplate.addEventListener("click", () => {
  const template = state.templates.find((item) => item.id === elements.template.value);
  if (!template || !state.document || !state.stamp) return;
  const applicable = template.placements.filter((item) => item.page < state.document.pages.length);
  state.placements = applicable.map((item) => {
    const placement = { ...item, widthMm: item.widthMm ?? item.sizeMm, heightMm: item.heightMm ?? item.sizeMm, rotationDegrees: item.rotationDegrees ?? 0, id: crypto.randomUUID(), stampId: state.stamp.id };
    clampPlacement(placement);
    return placement;
  });
  state.page = state.placements[0]?.page || 0;
  state.selectedId = state.placements[0]?.id || null;
  renderAll({ refreshPreview: true });
  setStatus(`${applicable.length}個の印影位置をテンプレートから適用しました。`);
});

elements.deleteTemplate.addEventListener("click", async () => {
  const template = state.templates.find((item) => item.id === elements.template.value);
  if (!template || !window.confirm(`「${template.name}」を削除しますか？`)) return;
  const beforeDelete = state.templates;
  state.templates = state.templates.filter((item) => item.id !== template.id);
  try {
    await persistTemplates();
    setStatus("テンプレートを削除しました。");
  } catch (error) {
    state.templates = beforeDelete;
    renderTemplates();
    setStatus(error.message, true);
  }
});

elements.filenameSuffix.addEventListener("change", () => { void updateSettings(); });
elements.batchCollision.addEventListener("change", () => { void updateSettings(); });

async function saveExport(exportInfo) {
  const nativeSave = window.pywebview?.api?.save_export;
  if (window.pywebview) {
    if (!nativeSave) throw new Error("保存機能を初期化できませんでした。アプリを再起動してから、もう一度お試しください。");
    const result = await nativeSave(exportInfo.id, exportInfo.filename);
    return Boolean(result?.saved);
  }
  const link = document.createElement("a");
  link.href = exportInfo.downloadUrl;
  link.download = exportInfo.filename;
  document.body.append(link);
  link.click();
  link.remove();
  return true;
}

async function saveBatchExport(batchInfo) {
  const nativeSave = window.pywebview?.api?.save_batch;
  if (window.pywebview) {
    if (!nativeSave) throw new Error("一括保存機能を初期化できませんでした。アプリを再起動してから、もう一度お試しください。");
    const result = await nativeSave(batchInfo.id, state.settings.batchCollision);
    if (result?.reason === "conflict") throw new Error("保存先に同名のPDFがあります。設定を変更するか、保存先を変更してください。");
    return result || { saved: false, count: 0 };
  }
  batchInfo.files.forEach((filename, index) => {
    const link = document.createElement("a");
    link.href = `/api/batches/${batchInfo.id}/files/${index}`;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
  });
  return { saved: true, count: batchInfo.files.length };
}

elements.export.addEventListener("click", async () => {
  if (!state.document || !state.placements.length) return;
  elements.export.disabled = true;
  setStatus("PDFに印影を配置して書き出しています…");
  try {
    const response = await fetch("/api/export", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ documentId: state.document.id, placements: state.placements, embedStampMetadata: elements.embedStampMetadata.checked }),
    });
    if (!response.ok) throw new Error(await readError(response));
    const exportInfo = await response.json();
    setStatus("保存先を選んでください…");
    setStatus(await saveExport(exportInfo) ? "押印済みPDFを保存しました。" : "保存を取り消しました。");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    elements.export.disabled = false;
  }
});

elements.exportBatch.addEventListener("click", async () => {
  if (!state.document || !state.placements.length || !state.batchFiles.length) return;
  elements.exportBatch.disabled = true;
  setStatus("PDFを一括書き出ししています…");
  try {
    const form = new FormData();
    state.batchFiles.forEach((file) => form.append("files", file));
    form.append("reference_document_id", state.document.id);
    form.append("placements_json", JSON.stringify(state.placements));
    form.append("embed_stamp_metadata", String(elements.embedStampMetadata.checked));
    const response = await fetch("/api/batches", { method: "POST", body: form });
    if (!response.ok) throw new Error(await readError(response));
    const batchInfo = await response.json();
    setStatus("保存先フォルダを選んでください…");
    const result = await saveBatchExport(batchInfo);
    setStatus(result.saved ? `${result.count}件の押印済みPDFを保存しました。` : "保存を取り消しました。");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    renderBatch();
  }
});

elements.openHelp.addEventListener("click", () => elements.help.showModal());
elements.closeHelp.addEventListener("click", () => elements.help.close());
elements.help.addEventListener("click", (event) => { if (event.target === elements.help) elements.help.close(); });
elements.openAbout.addEventListener("click", () => elements.about.showModal());
elements.closeAbout.addEventListener("click", () => elements.about.close());
elements.about.addEventListener("click", (event) => { if (event.target === elements.about) elements.about.close(); });
window.addEventListener("keydown", (event) => {
  if (event.isComposing || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key !== "Delete" && event.key !== "Backspace") return;
  if (event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable='true']")) return;
  if (!elements.studioView.hidden) {
    if (removeSelectedStudioSvgAsset()) event.preventDefault();
    return;
  }
  if (!elements.editorView.hidden && removeSelectedPlacement()) event.preventDefault();
});

renderAll();
renderStudioFormat();
renderStudioControls();
renderSvgAssets();
void Promise.all([loadTemplates(), loadRegisteredStamps(), loadSettings()]);
