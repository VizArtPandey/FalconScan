(() => {
  const $ = (selector) => document.querySelector(selector);
  let stream = null;
  let processing = false;
  let lastAutoScan = 0;
  let previous = null;
  let stableFrames = 0;
  let currentDocumentText = "";

  const sample = document.createElement("canvas");
  const context = sample.getContext("2d", { willReadFrequently: true });
  sample.width = 96;
  sample.height = 72;

  function setDetails(open) {
    const shell = $("#scannerShell");
    shell.classList.toggle("details-open", open);
    shell.classList.toggle("details-closed", !open);
    $("#scanDetails").setAttribute("aria-hidden", String(!open));
    $("#detailsToggle").setAttribute("aria-expanded", String(open));
  }

  async function start() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      $("#video").srcObject = stream;
      await $("#video").play();
      $("#video").hidden = false;
      $("#documentScroller").hidden = true;
      $("#viewport").appendChild($("#overlay"));
      $("#documentInfo").hidden = true;
      $("#emptyState").classList.add("hidden");
      $("#viewport").classList.add("active");
      $("#statusPill").classList.add("live");
      $("#statusPill span").textContent = "Live · private preview";
      $("#captureButton").disabled = false;
      setStatus("Camera ready", "Position the document inside the frame and hold still. Capture starts automatically when the page is clear.");
      requestAnimationFrame(monitor);
    } catch (error) {
      setStatus(
        "Camera unavailable",
        error.name === "NotAllowedError"
          ? "Camera permission was denied. Allow access and try again."
          : "Use HTTPS or localhost and make sure a camera is connected.",
      );
      setDetails(true);
    }
  }

  function monitor() {
    if (!stream) return;
    const video = $("#video");
    if (video.readyState >= 2) {
      context.drawImage(video, 0, 0, sample.width, sample.height);
      const data = context.getImageData(0, 0, sample.width, sample.height).data;
      let brightness = 0;
      let motion = 0;
      let edges = 0;
      const gray = new Uint8Array(sample.width * sample.height);

      for (let source = 0, target = 0; source < data.length; source += 4, target += 1) {
        gray[target] = data[source] * 0.299 + data[source + 1] * 0.587 + data[source + 2] * 0.114;
        brightness += gray[target];
        if (previous) motion += Math.abs(gray[target] - previous[target]);
        if (target > sample.width) edges += Math.abs(gray[target] - gray[target - sample.width]);
      }

      brightness /= gray.length;
      motion = previous ? motion / gray.length : 99;
      edges /= gray.length;
      previous = gray;

      const lightOkay = brightness > 42 && brightness < 220;
      const sharp = edges > 5.2;
      const still = motion < 3.8;
      stableFrames = lightOkay && sharp && still ? stableFrames + 1 : 0;

      $("#qualityPill").textContent = !lightOkay
        ? brightness < 42 ? "More light needed" : "Reduce glare"
        : !sharp ? "Move closer / focus"
        : !still ? "Hold steady"
        : stableFrames < 12 ? "Almost stable…" : "Frame stable";

      if (stableFrames >= 12 && !processing && Date.now() - lastAutoScan > 8000) {
        lastAutoScan = Date.now();
        analyze();
      }
    }
    requestAnimationFrame(monitor);
  }

  async function analyze() {
    if (processing || !stream) return;
    const video = $("#video");
    const canvas = $("#captureCanvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    await analyzeCanvas(canvas, "camera");
  }

  async function analyzeCanvas(canvas, source) {
    if (processing) return;
    processing = true;
    stableFrames = 0;
    setStatus("Finding document terms", source === "upload" ? "Reading the uploaded page securely." : "Reading one clear camera frame.");
    showProgress("Recognizing text and matching business terminology…");
    const payload = {
      image_base64: canvas.toDataURL("image/jpeg", 0.75),
      frame_width: canvas.width,
      frame_height: canvas.height,
      language_preference: $("#language").value,
    };

    try {
      const response = await fetch("/analyze-frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Scan failed");

      if (!data.ocr_available) {
        setStatus("Recognition unavailable", `${data.message}. Install the full requirements to enable document recognition.`);
        toast("The interface is ready. OCR needs the PaddleOCR dependency.");
      } else {
        renderAnalysis(data, canvas.width, canvas.height);
      }
    } catch (error) {
      setStatus("Couldn’t scan this page", error.message);
    } finally {
      processing = false;
      setDetails(true);
    }
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const extension = file.name.split(".").pop()?.toLowerCase();
    const supported = ["jpg", "jpeg", "png", "webp", "pdf", "docx"];
    if (!supported.includes(extension)) {
      toast("Please choose JPG, PNG, WebP, PDF, or Word DOCX.");
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      toast("Choose a document smaller than 15 MB.");
      return;
    }
    processing = true;
    setStatus("Preparing document", "Creating a private preview and finding useful business terms.");
    showProgress("Opening and reading the document…");
    setDetails(true);
    try {
      const prepared = await prepareUpload(file);
      const response = await fetch("/analyze-document", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_base64: prepared.base64,
          filename: prepared.filename,
          language_preference: $("#language").value,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Document analysis failed");
      const preview = $("#uploadedPreview");
      await loadPreview(preview, data.preview_base64);
      $("#documentStage").appendChild($("#overlay"));
      $("#documentScroller").hidden = false;
      $("#documentScroller").scrollTo({ top: 0, left: 0, behavior: "instant" });
      $("#video").hidden = true;
      $("#emptyState").classList.add("hidden");
      $("#viewport").classList.remove("active");
      $("#statusPill").classList.add("live");
      $("#statusPill span").textContent = "Uploaded · not stored";
      $("#qualityPill").textContent = file.name;
      $("#captureButton").disabled = true;
      renderAnalysis(data, data.frame_width, data.frame_height);
    } catch (error) {
      setStatus("Couldn’t read this document", error.message);
      toast(error.message);
    } finally {
      processing = false;
      setDetails(true);
    }
  }

  function renderAnalysis(data, frameWidth, frameHeight) {
    const terms = data.detected_terms || [];
    $("#resultTitle").textContent = terms.length ? "Document ready" : "No useful terms found";
    $("#statusMessage").textContent = terms.length
      ? "Tap a dot on the document to open its live definition. Drag a dot if it covers important text."
      : data.unknown_terms?.length
        ? "Text was found, but no glossary terms matched. Try a clearer document."
          : "Try a sharper image or a page containing customs, freight, or shipping terminology.";
    window.FalconOverlay.render(terms, frameWidth, frameHeight, data.ocr_items || []);
    currentDocumentText = (data.ocr_items || []).map((item) => item.text || "").filter(Boolean).join(" ").slice(0, 5000);
    $("#documentInfo").hidden = !currentDocumentText;
    $("#selectionHint").hidden = !(data.ocr_items || []).length;
    $("#vlmButton").disabled = !data.suggest_vlm;
    $("#vlmButton").title = data.vlm_reasons?.join(", ") || "";
  }

  async function prepareUpload(file) {
    if (!file.type.startsWith("image/")) {
      return { base64: await readBase64(file), filename: file.name };
    }
    const objectUrl = URL.createObjectURL(file);
    try {
      const image = await loadImage(objectUrl);
      const maxEdge = 1400;
      const scale = Math.min(1, maxEdge / Math.max(image.naturalWidth, image.naturalHeight));
      if (scale === 1 && file.size < 2 * 1024 * 1024) {
        return { base64: await readBase64(file), filename: file.name };
      }
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.70));
      return { base64: await readBase64(blob), filename: "optimized-upload.jpg" };
    } finally {
      URL.revokeObjectURL(objectUrl);
    }
  }

  function readBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
      reader.onerror = () => reject(new Error("The document could not be read"));
      reader.readAsDataURL(file);
    });
  }

  function loadImage(source) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("The image could not be prepared"));
      image.src = source;
    });
  }

  function showProgress(message) {
    $("#termsList").innerHTML = `<div class="analysis-progress"><i aria-hidden="true"></i><span>${message}</span></div>`;
  }

  function loadPreview(element, source) {
    return new Promise((resolve, reject) => {
      element.onload = resolve;
      element.onerror = () => reject(new Error("The document preview could not be rendered"));
      element.src = source;
    });
  }

  async function analyzeVlm() {
    $("#vlmButton").disabled = true;
    const data = await fetch("/analyze-document-vlm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_requested: true }),
    }).then((response) => response.json());
    toast(data.message);
    setTimeout(() => { $("#vlmButton").disabled = false; }, 1200);
  }

  function setStatus(title, message) {
    $("#resultTitle").textContent = title;
    $("#statusMessage").textContent = message;
  }

  function toast(message) {
    const element = $("#toast");
    element.textContent = message;
    element.classList.add("show");
    setTimeout(() => element.classList.remove("show"), 3500);
  }

  document.addEventListener("DOMContentLoaded", () => {
    window.FalconOverlay.init();
    window.FalconFeedback.init();
    window.FalconInsights.init();
    setDetails(false);
    $("#startCamera").onclick = start;
    $("#captureButton").onclick = analyze;
    $("#vlmButton").onclick = analyzeVlm;
    $("#detailsToggle").onclick = () => setDetails(!$("#scannerShell").classList.contains("details-open"));
    $("#detailsClose").onclick = () => setDetails(false);
    $("#uploadButton").onclick = () => $("#documentUpload").click();
    $("#documentUpload").onchange = handleUpload;
    $("#documentInfo").onclick = () => {
      if (currentDocumentText) window.FalconInsights.explain(currentDocumentText);
    };
    $("#language").onchange = () => { document.documentElement.lang = $("#language").value; };
    window.addEventListener("resize", () => window.FalconOverlay.clear());
  });

  window.addEventListener("beforeunload", () => stream?.getTracks().forEach((track) => track.stop()));
})();
