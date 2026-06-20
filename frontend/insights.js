window.FalconInsights = (() => {
  const $ = (selector) => document.querySelector(selector);
  let pending = false;

  function init() {
    $("#insightClose").onclick = close;
    $("#insightModal").addEventListener("click", (event) => {
      if (event.target === $("#insightModal")) close();
    });
  }

  async function explain(text) {
    const selected = String(text || "").trim();
    if (!selected || pending) return;
    pending = true;
    openLoading(selected);
    try {
      const response = await fetch("/explain-selection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: selected, language_preference: $("#language").value }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Insight unavailable");
      $("#insightSummary").textContent = data.summary;
      $("#insightBusiness").textContent = data.business_meaning;
      $("#insightSource").textContent = data.source_label;
      const confPercent = Math.round(data.confidence * 100);
      const confEl = $("#insightConfidence");
      confEl.textContent = `${confPercent}% confidence`;
      confEl.className = 'confidence-score ' + (confPercent >= 90 ? 'conf-good' : confPercent >= 70 ? 'conf-neutral' : 'conf-bad');
      $("#insightTerms").innerHTML = (data.recognized_terms || []).map((item) => `<button type="button" data-term="${escapeHtml(item.term)}">${escapeHtml(item.term)}</button>`).join("");
      $("#insightTerms").querySelectorAll("button").forEach((button) => {
        button.onclick = () => {
          const item = data.recognized_terms.find((term) => term.term === button.dataset.term);
          if (item) window.FalconFeedback.open(item);
        };
      });
    } catch (error) {
      $("#insightSummary").textContent = error.message;
      $("#insightBusiness").textContent = "Try selecting a shorter phrase or a clearly recognized paragraph.";
    } finally {
      pending = false;
    }
  }

  function openLoading(text) {
    $("#insightSelection").textContent = text;
    $("#insightSummary").textContent = "Understanding your selection…";
    $("#insightBusiness").textContent = "Finding the relevant trade and clearance context.";
    $("#insightTerms").innerHTML = "";
    $("#insightSource").textContent = "Analyzing";
    $("#insightConfidence").textContent = "";
    $("#insightModal").classList.add("open");
    $("#insightModal").setAttribute("aria-hidden", "false");
  }

  function close() {
    $("#insightModal").classList.remove("open");
    $("#insightModal").setAttribute("aria-hidden", "true");
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[character]);
  }

  return { init, explain };
})();
