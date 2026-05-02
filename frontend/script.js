/**
 * TOLLNET — Smart Toll Collection System
 * Frontend Script (script.js)
 *
 * Responsibilities:
 *  - Request camera permission & stream video
 *  - Capture a frame from the video feed
 *  - Send the frame to the Flask backend via fetch
 *  - Render the API response in the result panel
 */

// ─── Configuration ───────────────────────────────
// Change this if your Flask server runs on a different host/port
const BACKEND_URL = "http://127.0.0.1:5001/process-image";

// ─── DOM References ──────────────────────────────
const videoFeed      = document.getElementById("videoFeed");
const captureCanvas  = document.getElementById("captureCanvas");
const cameraOverlay  = document.getElementById("cameraOverlay");
const capturedSection= document.getElementById("capturedSection");
const capturedImage  = document.getElementById("capturedImage");

const btnStart   = document.getElementById("btnStart");
const btnCapture = document.getElementById("btnCapture");

const loadingBar   = document.getElementById("loadingBar");
const loadingFill  = document.getElementById("loadingFill");
const loadingLabel = document.getElementById("loadingLabel");

const resultIdle = document.getElementById("resultIdle");
const resultData = document.getElementById("resultData");

const statusBanner = document.getElementById("statusBanner");
const statusIcon   = document.getElementById("statusIcon");
const statusText   = document.getElementById("statusText");

const resVehicleId = document.getElementById("resVehicleId");
const resOwner     = document.getElementById("resOwner");
const resToll      = document.getElementById("resToll");
const resBalance   = document.getElementById("resBalance");
const msgText      = document.getElementById("msgText");

// ─── State ───────────────────────────────────────
let cameraStream = null; // holds the MediaStream object

// ─── 1. Start Camera ─────────────────────────────
async function startCamera() {
  // Check if browser supports getUserMedia
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("❌ Your browser does not support camera access.\nPlease use Chrome, Firefox, or Edge.");
    return;
  }

  try {
    // Request camera permission (prefer back camera on mobile)
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false
    });

    // Attach stream to the video element
    videoFeed.srcObject = cameraStream;
    videoFeed.play();

    // Hide the "camera not started" overlay
    cameraOverlay.classList.add("hidden");

    // Enable the capture button & disable start button to prevent double-click
    btnCapture.disabled = false;
    btnStart.disabled   = true;
    btnStart.textContent = "✓ Camera Active";

  } catch (err) {
    // Handle common errors
    if (err.name === "NotAllowedError") {
      alert("❌ Camera permission denied.\nPlease allow camera access in your browser settings and reload the page.");
    } else if (err.name === "NotFoundError") {
      alert("❌ No camera found.\nPlease connect a camera and try again.");
    } else {
      alert("❌ Camera error: " + err.message);
    }
    console.error("Camera error:", err);
  }
}

// ─── 2. Capture & Process ────────────────────────
async function captureAndProcess() {
  // Safety check: camera must be running
  if (!cameraStream) {
    alert("Please start the camera first.");
    return;
  }

  // ── 2a. Draw current video frame onto canvas ──
  const ctx = captureCanvas.getContext("2d");
  captureCanvas.width  = videoFeed.videoWidth  || 640;
  captureCanvas.height = videoFeed.videoHeight || 480;
  ctx.drawImage(videoFeed, 0, 0, captureCanvas.width, captureCanvas.height);

  // ── 2b. Show captured image preview ───────────
  const dataURL = captureCanvas.toDataURL("image/png");
  capturedImage.src = dataURL;
  capturedSection.style.display = "block";

  // ── 2c. Convert canvas to Blob (for fetch) ────
  captureCanvas.toBlob(async (blob) => {
    if (!blob) {
      showError("Failed to capture image from camera.");
      return;
    }

    // Build FormData to send as multipart/form-data
    const formData = new FormData();
    formData.append("image", blob, "capture.png");

    // ── 2d. Show loading state ─────────────────
    setLoading(true);
    btnCapture.disabled = true;

    try {
      // ── 2e. Send to backend ────────────────────
      const response = await fetch(BACKEND_URL, {
        method: "POST",
        body: formData
        // NOTE: Do NOT set Content-Type header manually;
        // fetch sets it automatically with the correct boundary.
      });

      // Parse JSON response
      const data = await response.json();

      // ── 2f. Display result ─────────────────────
      setLoading(false);
      renderResult(data);

    } catch (err) {
      setLoading(false);
      // Network error (backend not running, CORS issue, etc.)
      if (err.name === "TypeError" && err.message.includes("Failed to fetch")) {
        showError("Cannot connect to backend. Make sure Flask is running on http://127.0.0.1:5000");
      } else {
        showError("Network error: " + err.message);
      }
      console.error("Fetch error:", err);
    }

    btnCapture.disabled = false;

  }, "image/png");
}

// ─── 3. Render Result ────────────────────────────
function renderResult(data) {
  // Hide idle screen, show data panel
  resultIdle.style.display = "none";
  resultData.style.display = "block";

  // ── Populate fields ───────────────────────────
  resVehicleId.textContent = data.vehicle_id    || "N/A";
  resOwner.textContent     = data.owner         || "—";
  resToll.textContent      = data.toll_deducted != null ? `₹ ${data.toll_deducted}` : "—";
  resBalance.textContent   = data.remaining_balance != null ? `₹ ${data.remaining_balance}` : "—";
  msgText.textContent      = data.message        || "—";

  // ── Status banner ─────────────────────────────
  // Remove previous classes
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
    // "failed", "not_found", or any other error
    statusBanner.classList.add("failed");
    statusIcon.textContent = "✕";
    statusText.textContent = "Transaction Failed";
  }
}

// ─── 4. Show Error ───────────────────────────────
function showError(message) {
  resultIdle.style.display = "none";
  resultData.style.display = "block";

  statusBanner.className = "status-banner failed";
  statusIcon.textContent = "✕";
  statusText.textContent = "Error";

  resVehicleId.textContent = "—";
  resOwner.textContent     = "—";
  resToll.textContent      = "—";
  resBalance.textContent   = "—";
  msgText.textContent      = message;
}

// ─── 5. Loading State ────────────────────────────
function setLoading(active) {
  if (active) {
    loadingBar.classList.add("active");
    loadingLabel.style.display = "block";

    // Animate fill bar in stages to simulate progress
    loadingFill.style.width = "0%";
    setTimeout(() => { loadingFill.style.width = "30%"; }, 50);
    setTimeout(() => { loadingFill.style.width = "65%"; }, 400);
    setTimeout(() => { loadingFill.style.width = "85%"; }, 900);
  } else {
    // Jump to 100% then hide
    loadingFill.style.width = "100%";
    setTimeout(() => {
      loadingBar.classList.remove("active");
      loadingLabel.style.display = "none";
      loadingFill.style.width = "0%";
    }, 400);
  }
}

// ─── 6. Reset UI ────────────────────────────────
function resetUI() {
  // Hide result panel, show idle
  resultData.style.display = "none";
  resultIdle.style.display = "block";

  // Clear captured image preview
  capturedSection.style.display = "none";
  capturedImage.src = "";
}

// ─── 7. Cleanup on page leave ───────────────────
window.addEventListener("beforeunload", () => {
  if (cameraStream) {
    cameraStream.getTracks().forEach(track => track.stop());
  }
});