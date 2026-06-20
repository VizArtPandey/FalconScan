# FalconScan task sheet

This sheet is the implementation baseline. A requirement is marked complete only when it exists in the code and has a verification path.

| # | Requirement | Implementation | Status | Verification |
|---:|---|---|---|---|
| 1 | Browser camera view | Live `getUserMedia` preview | Complete | Start camera on localhost or HTTPS |
| 2 | Browser-side frame stability | Motion, blur/focus, and lighting checks on a 96×72 canvas | Complete | Observe live status metrics |
| 3 | Stable/manual frame capture | 12 stable samples or Scan now | Complete | Hold document still or tap button |
| 4 | English and Arabic OCR | Lazy PaddleOCR service with boxes/confidence | Complete | Install full requirements and scan bilingual samples |
| 5 | Customs glossary matching | Exact, acronym, alias, phrase, Arabic, and fuzzy matching | Complete | Automated service tests |
| 6 | Clickable dot overlays | OCR coordinates mapped into contained camera video | Complete | Tap a detected dot |
| 7 | Bilingual definition sheet | English/Arabic, RTL, source, confidence, related terms | Complete | Switch header language and open a term |
| 8 | Feedback correction | Thumbs up/down, correction form, JSON persistence | Complete | Submit correction and repeat lookup |
| 9 | SME review workflow | Pending queue, accurate header count, approve/reject | Complete | Header badge equals `/admin/corrections` item count |
| 10 | Governed definition priority | SME → user correction → glossary → RAG → AI | Complete | Automated priority test |
| 11 | Optional AI/VLM | Explicitly gated and disabled safely when unconfigured | Complete boundary | Configure provider adapter for live inference |
| 12 | No image persistence | Only bounded OCR results and feedback are saved | Complete | Inspect `data/` after scan |
| 13 | Free CPU Space deployment | Docker Space metadata and Dockerfile | Complete | Deploy and run smoke tests |
| 14 | Architecture diagram + explanation | Mermaid diagram and textual explanation in project documentation; intentionally excluded from the operational scanning UI | Complete | View README architecture section |
| 15 | Mobile-first responsive design | Phone portrait baseline; touch targets, safe areas, bottom-sheet dialogs; tablet/desktop progressive layouts | Complete | Test 320, 390, 768, 900, and 1440px widths |
| 16 | Contextual Scan Status panel | Closed before scanning, manually toggleable, automatically opened after scan, responsive drawer behavior | Complete | Load app, scan, close and reopen details |
| 17 | Trust-building privacy note | Prominent note explains that frames are analyzed but captured images are not stored | Complete | View note above scanner and inspect storage behavior |
| 18 | Polished product UI | Restrained Apple-inspired hierarchy, translucent surfaces, system typography, purposeful motion, and reduced visual noise | Complete | Visual QA on phone and desktop |
| 19 | Document upload | Scan Details accepts JPG, PNG, WebP, PDF, and Word DOCX; renders a private preview and uses OCR or native text extraction | Complete | Upload each supported type under 15 MB |
| 20 | Readable detection callouts | Dots expand into one rectangular insight containing dot, divider, term, confidence, definition, and full-meaning action | Complete | Tap several dots and inspect inline insight readability |
| 21 | Adaptive detection dots | Page area and OCR complexity determine a readable marker budget; every matched term remains accessible in Scan Details | Complete | Upload simple and dense documents |
| 22 | Select/highlight insight | Select OCR text, a phrase, or paragraph to receive Summary and Business Meaning with governed source/confidence | Complete | Highlight text on an uploaded document preview |

## Newly fixed requirements

### Accurate header counting

- The SME review badge is sourced from `GET /admin/corrections`.
- Zero is not presented as a pending notification; the badge is hidden.
- Singular/plural accessible labels reflect the real count.
- A failed count request hides the badge instead of showing stale data.

### Mobile-first responsive behavior

- Base CSS targets 320px+ phone portrait screens.
- Camera content is ordered first and uses small-viewport height units.
- Controls meet touch-friendly sizing and use device safe-area insets.
- Definition/admin dialogs are mobile bottom sheets and centered dialogs on larger screens.
- Tablet enhances spacing and actions; desktop switches to a two-column scanner workspace.
- Technical architecture stays in the README so the scanning experience remains task-focused.

### Scan Status disclosure

- Scan Status starts closed so the camera remains the primary task surface.
- Users can open or close details at any time.
- A completed scan opens the details automatically and shows result count, quality, confidence, and actions.
- On phones the panel expands below the camera; on desktop it reveals as a right-side panel.

### Trust and visual polish

- Privacy is presented as a concise trust note beside the core workflow rather than as marketing decoration.
- Architecture remains in technical documentation and is not shown in the scanning UI.
- The visual system uses native system typography, calm neutral surfaces, selective translucency, large radii, and subtle motion.

### Upload and detection readability

- Scan Details includes private upload for JPG, PNG, WebP, PDF, and Word DOCX files up to 15 MB. Legacy binary `.doc` is rejected with a clear message; save it as DOCX first.
- PDFs use positioned page text when available and OCR for scanned first pages. DOCX paragraphs are rendered into a positioned preview. Images use PaddleOCR or the installed portable CPU fallback.
- Uploaded documents are previewed in the scanner and analyzed without being persisted.
- Expanded detection callouts contain the status dot, divider line, term, confidence, definition, and full-meaning action.
- Markers are collision-adjusted. Dense documents show the highest-confidence dots on the image while keeping every matched term in the details list.
- Dots now appear by default. Tapping one expands an inline term, confidence, and definition card; the full meaning remains one tap away.
- OCR/PDF/DOCX text regions form a selectable layer. Highlighting a word or paragraph opens a live Summary and Business Meaning insight.

## Current checkpoint

- Completed: Header count fix, consecutively numbered walkthrough, architecture documentation, mobile-first layout, contextual Scan Status drawer, trust note, and polished product UI.
- In progress: Representative-device validation with live camera permissions.
- Next: Enable full PaddleOCR and run English/Arabic document acceptance tests on a phone over HTTPS.
- Known external issue: The supplied screenshot is a proxy authentication prompt at `91.207.173.102:4433`; it is outside FalconScan. Use the localhost URL for local testing and do not enter credentials into an unknown proxy prompt.

## Mandatory release-gate checklist

Every item below must pass before FalconScan is marked ready for GitHub or Hugging Face deployment.

### Detection and overlay

- [x] A simple document with a known customs term shows at least one dot automatically.
- [x] A dense document uses an adaptive marker budget based on page area and OCR complexity.
- [x] Markers do not overlap; displaced or hidden terms remain available in Scan Details.
- [x] Multiple known terms on the same OCR line create separate detections.
- [x] Tapping a dot expands an inline card containing term, confidence, definition, dot, and divider.
- [x] Only one expanded inline card is shown at a time to preserve readability.
- [x] “Open full meaning” opens the complete bilingual definition and source information.
- [x] Resizing the viewport clears stale overlay coordinates before the next render.
- [x] When OCR succeeds but no governed glossary term matches, contextual dots appear with an explicit unverified label instead of a misleading empty result.
- [x] No more than three highest-confidence dots are shown on the page at once.
- [x] Dots use the reduced 18px control size and can be dragged to uncover document text.
- [x] A readable single-word OCR region can receive a contextual dot when it is not already represented by a verified term.
- [x] Clicking selectable document text creates a dot at the clicked location without exceeding the three-dot limit.

### Selection, highlight, and business insight

- [x] OCR/PDF/DOCX text regions are selectable without blocking detection dots.
- [x] Selecting a known word, phrase, or paragraph opens the Live Document Insight panel.
- [x] The panel returns both a Summary and Business Meaning.
- [x] Recognized concepts are shown as clickable term chips.
- [x] Known selections display verified glossary provenance and confidence.
- [x] Unknown selections are clearly labeled as needing expert verification.
- [x] Empty or collapsed selections do not trigger requests.
- [x] Selection supports multi-word phrases and paragraphs without maintaining a selection history in Scan Details.
- [x] A post-scan Info control summarizes the full recognized page using the same sourced Summary and Business Meaning panel.

### Supported documents

- [x] JPG upload is accepted and analyzed with positioned OCR results.
- [x] PNG upload is accepted and analyzed with positioned OCR results.
- [x] WebP upload is accepted and analyzed with positioned OCR results.
- [x] Text PDF first pages are rendered and analyzed using positioned PDF text.
- [x] Scanned PDF first pages fall back to OCR.
- [x] Word DOCX paragraphs are extracted, rendered, and mapped to positioned regions.
- [x] Unsupported legacy `.doc` files return a clear instruction to save as DOCX.
- [x] Files over 15 MB are rejected before analysis.
- [x] Uploaded document images and files are not persisted by default.
- [x] Uploaded document previews use a dedicated scroll container with visible native scrollbars.
- [x] Multi-page PDFs render into one continuous scroll surface with positioned text and dots across pages.
- [x] DOCX rendering grows with document content rather than stopping at the earlier fixed preview height.

### Camera and performance

- [x] Camera OCR runs only after a stable frame or explicit Scan now action.
- [x] Blur, motion, and lighting checks run locally in the browser.
- [x] Similar frames use the bounded OCR cache.
- [x] CPU OCR fallback works when PaddleOCR is unavailable.
- [x] VLM remains optional and does not block the glossary-first workflow.
- [x] Large uploaded images are resized to a maximum 1600px edge in the browser before transfer.
- [x] Small images avoid unnecessary recompression.
- [x] Portable CPU OCR is warmed in the background to reduce first-scan latency.
- [x] Uploaded images are preprocessed for contrast/sharpness at a bounded 1400px edge.
- [x] The last four document analyses are cached in memory for immediate repeat uploads.

### Responsive UI and accessibility

- [x] Scan Status starts closed and opens automatically after analysis.
- [x] Scan Status can be opened and closed manually.
- [x] Phone portrait is the primary layout at 320px and 390px widths.
- [x] Tablet and desktop layouts adapt without removing functionality.
- [x] Touch targets remain usable and safe-area insets are respected.
- [x] Arabic definitions render RTL.
- [x] Reduced-motion preferences are respected.
- [x] Pending SME count is accurate and hidden when zero or unavailable.
- [x] Scan Status uses concise state-specific instructions rather than exposing raw stability, lighting, OCR, or zero-count diagnostics.
- [x] Term-count badges are omitted from Scan Status; the result list itself communicates available concepts.
- [x] Scan Details does not retain or display a history of selected terms.

### Governance and trust

- [x] The privacy note states that frames are analyzed but captured images are not stored.
- [x] Every definition includes source type and confidence.
- [x] SME-approved definitions override pending user corrections.
- [x] Feedback and review actions preserve an audit history.
- [x] AI-generated or unmatched explanations are marked unverified.
- [x] Confidence combines recognition and knowledge signals using calibrated weighting rather than artificially multiplying scores downward.

### Automated verification recorded

- [x] Python/API suite: 15 tests passing.
- [x] JavaScript syntax checks: camera, overlay, feedback, and insights scripts passing.
- [x] DOM integration: two terms produced two dots.
- [x] DOM integration: dot click expanded the inline definition.
- [x] DOM integration: full-meaning action opened the governed definition.
- [x] DOM integration: text selection triggered the insight flow.
- [x] Live API: selection returned recognized terms, summary, business meaning, source, and confidence.
- [ ] Physical iPhone Safari camera and selection acceptance test.
- [ ] Physical Android Chrome camera and selection acceptance test.
- [ ] Deployed Hugging Face Space smoke test after remote synchronization.
- [ ] GitHub CI test run after repository push.
