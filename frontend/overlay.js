window.FalconOverlay = (() => {
  let terms = [];
  let viewport;
  let overlay;
  let video;
  let uploadedPreview;
  let documentScroller;
  let activePopover = null;

  function init() {
    viewport = document.querySelector("#viewport");
    overlay = document.querySelector("#overlay");
    video = document.querySelector("#video");
    uploadedPreview = document.querySelector("#uploadedPreview");
    documentScroller = document.querySelector("#documentScroller");
    document.addEventListener("pointerdown", (event) => {
      if (activePopover && !activePopover.contains(event.target) && !event.target.closest(".term-marker")) closePopover();
    });
  }

  function geometry(frameWidth, frameHeight) {
    const documentMode = documentScroller && !documentScroller.hidden;
    const media = documentMode ? uploadedPreview : video;
    const mediaRect = media.getBoundingClientRect();
    const viewRect = documentMode ? overlay.getBoundingClientRect() : viewport.getBoundingClientRect();
    const scale = Math.min(mediaRect.width / frameWidth, mediaRect.height / frameHeight);
    const drawnWidth = frameWidth * scale;
    const drawnHeight = frameHeight * scale;
    return {
      viewRect,
      scale,
      offsetX: documentMode ? 0 : (viewRect.width - drawnWidth) / 2,
      offsetY: documentMode ? 0 : (viewRect.height - drawnHeight) / 2,
    };
  }

  function render(items, frameWidth, frameHeight, textRegions = []) {
    terms = items;
    overlay.innerHTML = "";
    activePopover = null;
    const layout = geometry(frameWidth, frameHeight);
    renderSelectionLayer(textRegions, layout);
    renderMarkers(items, layout);
    renderList(items);
  }

  function renderMarkers(items, layout) {
    if (!items.length) return;
    const visible = [...items].sort((a, b) => b.confidence - a.confidence).slice(0, 3);
    const occupied = [];

    visible.forEach((item, index) => {
      const [x1, y1, x2, y2] = item.bbox;
      let left = layout.offsetX + x2 * layout.scale + 7;
      let top = layout.offsetY + ((y1 + y2) / 2) * layout.scale - 12;
      if (left > layout.viewRect.width - 34) left = layout.offsetX + x1 * layout.scale - 31;
      left = clamp(left, 7, layout.viewRect.width - 31);
      top = clamp(top, 46, layout.viewRect.height - 38);
      let attempts = 0;
      while (occupied.some((point) => Math.hypot(point.left - left, point.top - top) < 31) && attempts < 12) {
        top = clamp(top + 32, 46, layout.viewRect.height - 38);
        if (top >= layout.viewRect.height - 39) left = clamp(left - 34, 7, layout.viewRect.width - 31);
        attempts += 1;
      }
      occupied.push({ left, top });

      const marker = document.createElement("button");
      marker.className = "term-marker";
      marker.type = "button";
      marker.style.left = `${left}px`;
      marker.style.top = `${top}px`;
      marker.style.setProperty("--marker-delay", `${Math.min(index * 35, 350)}ms`);
      marker.setAttribute("aria-label", `Explain ${item.term}`);
      marker.innerHTML = `<span></span>`;
      let dragged = false;
      enableDrag(marker, layout, () => { dragged = true; });
      marker.onclick = (event) => {
        event.stopPropagation();
        if (dragged) {
          dragged = false;
          return;
        }
        openPopover(item, marker, layout);
      };
      overlay.appendChild(marker);
    });
  }

  function enableDrag(marker, layout, onDrag) {
    let start = null;
    marker.addEventListener("pointerdown", (event) => {
      start = {
        x: event.clientX,
        y: event.clientY,
        left: parseFloat(marker.style.left),
        top: parseFloat(marker.style.top),
        moved: false,
      };
      marker.setPointerCapture?.(event.pointerId);
    });
    marker.addEventListener("pointermove", (event) => {
      if (!start) return;
      const dx = event.clientX - start.x;
      const dy = event.clientY - start.y;
      if (Math.hypot(dx, dy) > 3) {
        start.moved = true;
        onDrag();
      }
      marker.style.left = `${clamp(start.left + dx, 5, layout.viewRect.width - 23)}px`;
      marker.style.top = `${clamp(start.top + dy, 5, layout.viewRect.height - 23)}px`;
    });
    const finish = () => { start = null; };
    marker.addEventListener("pointerup", finish);
    marker.addEventListener("pointercancel", finish);
  }

  function triggerDotAtText(event, region, layout) {
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed && selection.toString().trim()) return;
    const existingMarkers = [...overlay.querySelectorAll(".term-marker")];
    if (existingMarkers.length >= 3) {
      (overlay.querySelector(".term-marker.user-triggered") || existingMarkers[existingMarkers.length - 1]).remove();
    }
    const match = terms.find((item) =>
      item.bbox?.every((value, index) => Math.abs(value - region.bbox[index]) < 2)
      || String(region.text).toLowerCase().includes(String(item.term).toLowerCase())
    );
    const item = match || {
      term: String(region.text).trim().slice(0, 58),
      definition: "Select this phrase for a contextual summary and business meaning.",
      confidence: Math.min(.72, Number(region.confidence || .75) * .72),
      source: "ai_generated_unverified",
      source_label: "Document context · needs verification",
      category: "Document Context",
      related_terms: [],
      document_types: [],
      bbox: region.bbox,
    };
    const overlayRect = overlay.getBoundingClientRect();
    const marker = document.createElement("button");
    marker.className = "term-marker user-triggered";
    marker.type = "button";
    marker.style.left = `${clamp(event.clientX - overlayRect.left - 9, 5, layout.viewRect.width - 23)}px`;
    marker.style.top = `${clamp(event.clientY - overlayRect.top - 9, 5, layout.viewRect.height - 23)}px`;
    marker.setAttribute("aria-label", `Explain ${item.term}`);
    marker.innerHTML = "<span></span>";
    let dragged = false;
    enableDrag(marker, layout, () => { dragged = true; });
    marker.onclick = (clickEvent) => {
      clickEvent.stopPropagation();
      if (dragged) {
        dragged = false;
        return;
      }
      openPopover(item, marker, layout);
    };
    overlay.appendChild(marker);
  }

  function openPopover(item, marker, layout) {
    closePopover();
    marker.classList.add("active");
    const popover = document.createElement("article");
    popover.className = "term-popover";
    const markerLeft = parseFloat(marker.style.left);
    const markerTop = parseFloat(marker.style.top);
    const width = Math.min(286, layout.viewRect.width - 24);
    let left = markerLeft + 34;
    if (left + width > layout.viewRect.width - 8) left = markerLeft - width - 8;
    left = clamp(left, 8, layout.viewRect.width - width - 8);
    const top = clamp(markerTop - 18, 50, layout.viewRect.height - 170);
    popover.style.left = `${left}px`;
    popover.style.top = `${top}px`;
    popover.style.width = `${width}px`;
    popover.innerHTML = `<div class="popover-heading"><span class="callout-dot"></span><span class="callout-line"></span><strong>${escapeHtml(item.term)}</strong><small>${Math.round(item.confidence * 100)}%</small></div><p>${escapeHtml(item.definition)}</p><button type="button">Open full meaning</button>`;
    popover.querySelector("button").onclick = (event) => {
      event.stopPropagation();
      window.FalconFeedback.open(item);
    };
    popover.onclick = (event) => event.stopPropagation();
    overlay.appendChild(popover);
    activePopover = popover;
  }

  function closePopover() {
    if (activePopover) activePopover.remove();
    activePopover = null;
    overlay?.querySelectorAll(".term-marker.active").forEach((marker) => marker.classList.remove("active"));
  }

  function renderSelectionLayer(regions, layout) {
    if (!regions.length) return;
    const layer = document.createElement("div");
    layer.className = "selection-layer";
    regions.slice(0, 80).forEach((region) => {
      if (!region.text || !region.bbox) return;
      const [x1, y1, x2, y2] = region.bbox;
      const span = document.createElement("span");
      span.className = "selectable-region";
      span.textContent = region.text;
      span.style.left = `${layout.offsetX + x1 * layout.scale}px`;
      span.style.top = `${layout.offsetY + y1 * layout.scale}px`;
      span.style.width = `${Math.max(8, (x2 - x1) * layout.scale)}px`;
      span.style.height = `${Math.max(12, (y2 - y1) * layout.scale)}px`;
      span.style.fontSize = `${clamp((y2 - y1) * layout.scale * 0.72, 8, 24)}px`;
      span.addEventListener("click", (event) => triggerDotAtText(event, region, layout));
      layer.appendChild(span);
    });
    const explainSelection = () => {
      requestAnimationFrame(() => {
        const selection = window.getSelection();
        if (!selection || selection.isCollapsed || !layer.contains(selection.anchorNode)) return;
        const text = selection.toString().trim();
        if (text) window.FalconInsights.explain(text);
      });
    };
    layer.addEventListener("mouseup", explainSelection);
    layer.addEventListener("touchend", explainSelection);
    overlay.appendChild(layer);
  }

  function renderList(items) {
    const list = document.querySelector("#termsList");
    list.innerHTML = items.length
      ? '<div class="instruction-card"><strong>Insights are on the document</strong><p>Tap a dot for meaning, drag it to reveal text, or select multiple words for business context.</p></div>'
      : '<div class="empty-result">No readable text was detected. Try a sharper image or another page.</div>';
  }

  function clear() {
    terms = [];
    activePopover = null;
    if (overlay) overlay.innerHTML = "";
  }

  function clamp(value, minimum, maximum) {
    return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[character]);
  }

  return { init, render, clear };
})();
