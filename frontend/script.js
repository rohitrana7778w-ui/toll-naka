/**
 * TOLLNET v2 — Frontend Script
 * Features: Camera scan + File Upload + Receipt display
 */

const BACKEND_CAMERA = "http://127.0.0.1:5001/process-image";
const BACKEND_UPLOAD = "http://127.0.0.1:5001/upload-plate";

// ─── DOM refs ────────────────────────────────────
const videoFeed       = document.getElementById("videoFeed");
const captureCanvas   = document.getElementById("captureCanvas");
const cameraOverlay   = document.getElementById("cameraOverlay");
const capturedSection = document.getElementById("capturedSection");
const capturedImage   = document.getElementById("capturedImage");
const btnStart        = document.getElementById("btnStart");
const btnCapture      = document.getElementById("btnCapture");
const btnUpload       = document.getElementById("btnUpload");
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
let cameraStream  = null;
let selectedFile  = null;
let activeTab     = "camera";

// ════════════════════════════════════════════════
// TAB SWITCHING
// ════════════════════════════════════════════════
function switchTab(tab) {
  activeTab = tab;
  document.getElementById("tabCamera").classList.toggle("active", tab === "camera");
  document.getElementById("tabUpload").classList.toggle("active", tab === "upload");
  document.getElementById("cameraTab").style.display = tab === "camera" ? "block" : "none";
  document.getElementById("uploadTab").style.display = tab === "upload" ? "block" : "none";
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

  // Draw frame to canvas
  const ctx = captureCanvas.getContext("2d");
  captureCanvas.width  = videoFeed.videoWidth  || 640;
  captureCanvas.height = videoFeed.videoHeight || 480;
  ctx.drawImage(videoFeed, 0, 0, captureCanvas.width, captureCanvas.height);

  // Show preview
  capturedImage.src = captureCanvas.toDataURL("image/png");
  capturedSection.style.display = "block";

  // Convert to Blob and send
  captureCanvas.toBlob(async (blob) => {
    const formData = new FormData();
    formData.append("image", blob, "capture.png");
    setLoading(true);
    btnCapture.disabled = true;
    const result = await sendToBackend(BACKEND_CAMERA, formData);
    setLoading(false);
    btnCapture.disabled = false;
    if (result) renderResult(result);
  }, "image/png");
}

// ════════════════════════════════════════════════
// FILE UPLOAD
// ════════════════════════════════════════════════
function handleFileSelect(event) {
  const file = event.target.files[0];
  if (file) setFile(file);
}

function handleDragOver(event) {
  event.preventDefault();
  document.getElementById("dropzone").classList.add("drag-over");
}

function handleDragLeave(event) {
  document.getElementById("dropzone").classList.remove("drag-over");
}

function handleDrop(event) {
  event.preventDefault();
  document.getElementById("dropzone").classList.remove("drag-over");
  const file = event.dataTransfer.files[0];
  if (file) setFile(file);
}

function setFile(file) {
  // Validate type
  const allowed = ["image/jpeg","image/png","image/bmp","image/webp","application/pdf"];
  if (!allowed.includes(file.type) && !file.name.toLowerCase().endsWith(".pdf")) {
    alert("Unsupported file type. Please upload JPG, PNG, BMP, WEBP, or PDF.");
    return;
  }
  // Validate size (10 MB)
  if (file.size > 10 * 1024 * 1024) {
    alert("File is too large. Maximum size is 10 MB.");
    return;
  }

  selectedFile = file;

  // Show file info
  document.getElementById("filePreview").style.display = "block";
  document.getElementById("fileName").textContent = file.name;
  document.getElementById("fileSize").textContent = formatBytes(file.size);
  document.getElementById("fileThumb").textContent = file.type === "application/pdf" ? "📄" : "🖼️";
  btnUpload.disabled = false;

  // Show image preview (not for PDFs)
  const imgPrev = document.getElementById("imagePreview");
  if (file.type.startsWith("image/")) {
    const reader = new FileReader();
    reader.onload = (e) => {
      imgPrev.src = e.target.result;
      imgPrev.style.display = "block";
    };
    reader.readAsDataURL(file);
  } else {
    imgPrev.style.display = "none";
  }
}

function clearFile() {
  selectedFile = null;
  document.getElementById("fileInput").value = "";
  document.getElementById("filePreview").style.display = "none";
  document.getElementById("imagePreview").style.display = "none";
  btnUpload.disabled = true;
}

async function uploadAndProcess() {
  if (!selectedFile) { alert("Please select a file first."); return; }

  const formData = new FormData();
  formData.append("file", selectedFile, selectedFile.name);

  setLoading(true);
  btnUpload.disabled = true;
  const result = await sendToBackend(BACKEND_UPLOAD, formData);
  setLoading(false);
  btnUpload.disabled = false;

  if (result) renderResult(result);
}

// ════════════════════════════════════════════════
// SHARED: Send to Backend
// ════════════════════════════════════════════════
async function sendToBackend(url, formData) {
  try {
    const response = await fetch(url, { method: "POST", body: formData });
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
  resultIdle.style.display = "none";
  resultData.style.display = "block";

  // Vehicle info
  document.getElementById("resVehicleNum").textContent  = data.vehicle_number  || "N/A";
  document.getElementById("resOwner").textContent       = data.owner_name      || "—";
  document.getElementById("resVehicleType").textContent = data.vehicle_type    || "—";
  document.getElementById("resToll").textContent        = data.toll_amount != null ? `₹ ${data.toll_amount}` : "—";
  document.getElementById("resBalance").textContent     = data.remaining_balance != null ? `₹ ${data.remaining_balance}` : "—";
  document.getElementById("msgText").textContent        = data.message || "—";

  // Status banner
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

  // Receipt (only on success)
  if (data.status === "success" && data.receipt_id) {
    receiptBox.style.display = "block";
    document.getElementById("rcptId").textContent      = data.receipt_id;
    document.getElementById("rcptDate").textContent    = data.date_time;
    document.getElementById("rcptVehicle").textContent = data.vehicle_number;
    document.getElementById("rcptOwner").textContent   = data.owner_name;
    document.getElementById("rcptType").textContent    = data.vehicle_type;
    document.getElementById("rcptToll").textContent    = `₹ ${data.toll_amount}`;
    document.getElementById("rcptBalance").textContent = `₹ ${data.remaining_balance}`;
  } else {
    receiptBox.style.display = "none";
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
  clearFile();
}

function formatBytes(bytes) {
  if (bytes < 1024)       return bytes + " B";
  if (bytes < 1048576)    return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

window.addEventListener("beforeunload", () => {
  if (cameraStream) cameraStream.getTracks().forEach(t => t.stop());
});