/**
 * TOLLNET v3 — Frontend Script
 * Features: Camera scan + Manual Entry + PDF Receipt download
 */

const BACKEND_CAMERA = "http://127.0.0.1:5001/process-image";
const BACKEND_MANUAL = "http://127.0.0.1:5001/process-manual";
const BACKEND_BASE   = "http://127.0.0.1:5001";

// ─── DOM refs ────────────────────────────────────
const videoFeed       = document.getElementById("videoFeed");
const captureCanvas   = document.getElementById("captureCanvas");
const cameraOverlay   = document.getElementById("cameraOverlay");
const capturedSection = document.getElementById("capturedSection");
const capturedImage   = document.getElementById("capturedImage");
const btnStart        = document.getElementById("btnStart");
const btnCapture      = document.getElementById("btnCapture");
const loadingBar      = document.getElementById("loadingBar");
const loadingFill     = document.getElementById("loadingFill");
const loadingLabel    = document.getElementById("loadingLabel");
const resultIdle      = document.getElementById("resultIdle");
const resultData      = document.getElementById("resultData");
const statusBanner    = document.getElementById("statusBanner");
const statusIcon      = document.getElementById("statusIcon");
const statusText      = document.getElementById("statusText");
const receiptBox      = document.getElementById("receiptBox");

// ─── State ───────────────────────────────────────
let cameraStream = null;
let activeTab    = "camera";

// ════════════════════════════════════════════════
// TAB SWITCHING
// ════════════════════════════════════════════════
function switchTab(tab) {
  activeTab = tab;
  document.getElementById("tabCamera").classList.toggle("active", tab === "camera");
  document.getElementById("tabManual").classList.toggle("active", tab === "manual");
  document.getElementById("cameraTab").style.display = tab === "camera" ? "block" : "none";
  document.getElementById("manualTab").style.display = tab === "manual" ? "block" : "none";
}

// ════════════════════════════════════════════════
// CAMERA
// ════════════════════════════════════════════════
async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    alert("Your browser does not support camera access.");
    return;
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false
    });
    videoFeed.srcObject = cameraStream;
    videoFeed.play();
    cameraOverlay.classList.add("hidden");
    btnCapture.disabled = false;
    btnStart.disabled   = true;
    btnStart.textContent = "✓ Camera Active";
  } catch (err) {
    if (err.name === "NotAllowedError")
      alert("Camera permission denied. Please allow camera access.");
    else if (err.name === "NotFoundError")
      alert("No camera found.");
    else
      alert("Camera error: " + err.message);
  }
}

async function captureAndProcess() {
  if (!cameraStream) { alert("Start the camera first."); return; }

  const ctx = captureCanvas.getContext("2d");
  captureCanvas.width  = videoFeed.videoWidth  || 640;
  captureCanvas.height = videoFeed.videoHeight || 480;
  ctx.drawImage(videoFeed, 0, 0, captureCanvas.width, captureCanvas.height);

  capturedImage.src = captureCanvas.toDataURL("image/png");
  capturedSection.style.display = "block";

  captureCanvas.toBlob(async (blob) => {
    const formData = new FormData();
    formData.append("image", blob, "capture.png");
    setLoading(true);
    btnCapture.disabled = true;
    const result = await sendToBackend(BACKEND_CAMERA, formData, "form");
    setLoading(false);
    btnCapture.disabled = false;
    if (result) renderResult(result);
  }, "image/png");
}

// ════════════════════════════════════════════════
// MANUAL ENTRY
// ════════════════════════════════════════════════
function onManualInput() {
  const input   = document.getElementById("manualVehicleInput");
  const preview = document.getElementById("manualPreview");
  const btn     = document.getElementById("btnManual");
  const cleaned = input.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6);
  input.value = cleaned;
  preview.textContent = cleaned.length > 0 ? `→ ${cleaned}` : "";
  // Enable when exactly 6 chars (valid toll ID) or a longer vehicle number
  btn.disabled = cleaned.length < 3;
}

function onManualKeydown(event) {
  if (event.key === "Enter") {
    const btn = document.getElementById("btnManual");
    if (!btn.disabled) processManual();
  }
}

async function processManual() {
  const input = document.getElementById("manualVehicleInput");
  const raw   = input.value.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (!raw) { showError("Please enter a Toll ID."); return; }

  const btn = document.getElementById("btnManual");
  setLoading(true);
  btn.disabled = true;
  // Send as vehicle_number; backend auto-detects toll_id format
  const result = await sendToBackend(BACKEND_MANUAL, { vehicle_number: raw }, "json");
  setLoading(false);
  btn.disabled = false;
  if (result) renderResult(result);
}

// ════════════════════════════════════════════════
// SHARED: Send to Backend
// ════════════════════════════════════════════════
async function sendToBackend(url, payload, type) {
  try {
    let options;
    if (type === "json") {
      options = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      };
    } else {
      options = { method: "POST", body: payload };
    }
    const response = await fetch(url, options);
    return await response.json();
  } catch (err) {
    const msg = err.message.includes("Failed to fetch")
      ? "Cannot connect to backend. Make sure Flask is running on http://127.0.0.1:5001"
      : "Network error: " + err.message;
    showError(msg);
    return null;
  }
}

// ════════════════════════════════════════════════
// RENDER RESULT
// ════════════════════════════════════════════════
function renderResult(data) {
  // Use page-level showResult if defined (employee.html defines its own)
  if (typeof showResult === "function") { showResult(data); return; }

  resultIdle.style.display = "none";
  resultData.style.display = "block";

  const tollIdEl = document.getElementById("resTollId");
  if (tollIdEl) tollIdEl.textContent = data.toll_id || "—";

  document.getElementById("resVehicleNum").textContent  = data.vehicle_number  || "N/A";
  document.getElementById("resOwner").textContent       = data.owner_name      || "—";
  document.getElementById("resVehicleType").textContent = data.vehicle_type    || "—";
  document.getElementById("resToll").textContent        = data.toll_amount     != null ? `₹ ${data.toll_amount}` : "—";
  document.getElementById("resBalance").textContent     = data.remaining_balance != null ? `₹ ${data.remaining_balance}` : "—";
  document.getElementById("msgText").textContent        = data.message || "—";

  statusBanner.className = "status-banner";
  if (data.status === "success") {
    statusBanner.classList.add("success");
    statusIcon.textContent = "✓";
    statusText.textContent = "Transaction Successful";
  } else if (data.status === "insufficient_balance") {
    statusBanner.classList.add("warning");
    statusIcon.textContent = "⚠";
    statusText.textContent = "Insufficient Balance";
  } else {
    statusBanner.classList.add("failed");
    statusIcon.textContent = "✕";
    statusText.textContent = data.status === "not_found" ? "Vehicle Not Found" : "Transaction Failed";
  }

  if (data.status === "success" && data.receipt_id) {
    receiptBox.style.display = "block";
    const rcptTollIdEl = document.getElementById("rcptTollId"); if (rcptTollIdEl) rcptTollIdEl.textContent = data.toll_id || "—";
    document.getElementById("rcptId").textContent      = data.receipt_id;
    document.getElementById("rcptDate").textContent    = data.date_time;
    document.getElementById("rcptVehicle").textContent = data.vehicle_number;
    document.getElementById("rcptOwner").textContent   = data.owner_name;
    document.getElementById("rcptType").textContent    = data.vehicle_type;
    document.getElementById("rcptToll").textContent    = `₹ ${data.toll_amount}`;
    document.getElementById("rcptBalance").textContent = `₹ ${data.remaining_balance}`;

    const btnPdf = document.getElementById("btnDownloadPdf");
    if (data.pdf_url) {
      btnPdf.href = BACKEND_BASE + data.pdf_url;
      btnPdf.style.display = "flex";
    } else {
      btnPdf.style.display = "none";
    }
  } else {
    receiptBox.style.display = "none";
    document.getElementById("btnDownloadPdf").style.display = "none";
  }
}

// ════════════════════════════════════════════════
// UTILITIES
// ════════════════════════════════════════════════
function showError(message) {
  resultIdle.style.display = "none";
  resultData.style.display = "block";
  statusBanner.className   = "status-banner failed";
  statusIcon.textContent   = "✕";
  statusText.textContent   = "Error";
  document.getElementById("resVehicleNum").textContent  = "—";
  document.getElementById("resOwner").textContent       = "—";
  document.getElementById("resVehicleType").textContent = "—";
  document.getElementById("resToll").textContent        = "—";
  document.getElementById("resBalance").textContent     = "—";
  document.getElementById("msgText").textContent        = message;
  receiptBox.style.display = "none";
  document.getElementById("btnDownloadPdf").style.display = "none";
}

function setLoading(active) {
  if (active) {
    loadingBar.classList.add("active");
    loadingLabel.style.display = "block";
    loadingFill.style.width = "0%";
    setTimeout(() => { loadingFill.style.width = "30%"; }, 50);
    setTimeout(() => { loadingFill.style.width = "65%"; }, 400);
    setTimeout(() => { loadingFill.style.width = "85%"; }, 900);
  } else {
    loadingFill.style.width = "100%";
    setTimeout(() => {
      loadingBar.classList.remove("active");
      loadingLabel.style.display = "none";
      loadingFill.style.width = "0%";
    }, 400);
  }
}

function resetUI() {
  resultData.style.display = "none";
  resultIdle.style.display = "block";
  capturedSection.style.display = "none";
  capturedImage.src = "";
  const input = document.getElementById("manualVehicleInput");
  if (input) input.value = "";
  const preview = document.getElementById("manualPreview");
  if (preview) preview.textContent = "";
  const btnManual = document.getElementById("btnManual");
  if (btnManual) btnManual.disabled = true;
}

window.addEventListener("beforeunload", () => {
  if (cameraStream) cameraStream.getTracks().forEach(t => t.stop());
});