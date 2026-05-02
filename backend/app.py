"""
TOLLNET — Smart Toll Collection System
Backend: app.py (Flask API) — v2 with File Upload + Receipt

Endpoints:
  GET  /                  → health check
  POST /process-image     → camera capture (original feature)
  POST /upload-plate      → file upload (image or PDF) — NEW
"""

import os
import json
import uuid
import numpy as np
import cv2
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

from ocr import extract_vehicle_id

# ─── App Setup ──────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, "database.json")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ─── Toll Rate Table (by vehicle_type from DB) ──────────────────
TOLL_RATES = {
    "car":   100,
    "truck": 150,
    "bus":   150,
    "bike":  50,
}
DEFAULT_TOLL = 100  # fallback for unknown types

# ─── DB Helpers ─────────────────────────────────────────────────
def load_database():
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_database(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)

# ─── Receipt Generator ──────────────────────────────────────────
def generate_receipt_id():
    """Returns a short unique receipt ID like TN-20240512-A3F7."""
    date_part = datetime.now().strftime("%Y%m%d")
    unique    = uuid.uuid4().hex[:4].upper()
    return f"TN-{date_part}-{unique}"

# ─── PDF → Image converter ──────────────────────────────────────
def pdf_to_image(pdf_bytes):
    """
    Convert the first page of a PDF (bytes) to an OpenCV BGR image.
    Requires: pip install pdf2image + poppler installed on system.
    """
    try:
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(pdf_bytes, dpi=200)
        if not pages:
            return None
        pil_img = pages[0]
        img_np  = np.array(pil_img.convert("RGB"))
        img_cv  = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        return img_cv
    except ImportError:
        raise RuntimeError(
            "pdf2image is not installed. Run: pip install pdf2image\n"
            "Also install poppler: brew install poppler (macOS) "
            "or sudo apt install poppler-utils (Linux)"
        )

# ─── Core Processing Logic (shared by both routes) ──────────────
def process_vehicle_image(img_cv):
    """
    Given an OpenCV image:
    1. Run OCR → extract vehicle number
    2. Match in DB
    3. Deduct toll based on vehicle_type
    4. Generate receipt
    5. Return (response_dict, http_status_code)
    """

    # Step 1: OCR
    vehicle_number = extract_vehicle_id(img_cv)
    if not vehicle_number:
        return {
            "status":            "failed",
            "message":           "Could not read a vehicle number from the image. "
                                 "Ensure the number plate is clearly visible and well-lit.",
            "vehicle_number":    None,
            "owner_name":        None,
            "vehicle_type":      None,
            "toll_amount":       None,
            "remaining_balance": None,
            "receipt_id":        None,
            "date_time":         None,
        }, 200

    # Step 2: Load DB & match
    try:
        db = load_database()
    except Exception as e:
        return {"status": "failed", "message": f"Database error: {e}"}, 500

    vehicle = None
    v_index = None
    for i, v in enumerate(db):
        if v["vehicle_number"].strip().upper() == vehicle_number.upper():
            vehicle = v
            v_index = i
            break

    # Step 3: Not found
    if vehicle is None:
        return {
            "status":            "not_found",
            "message":           f"Vehicle '{vehicle_number}' is not registered in the system.",
            "vehicle_number":    vehicle_number,
            "owner_name":        None,
            "vehicle_type":      None,
            "toll_amount":       None,
            "remaining_balance": None,
            "receipt_id":        None,
            "date_time":         None,
        }, 200

    # Step 4: Toll rate from vehicle_type in DB
    v_type   = vehicle.get("vehicle_type", "car").lower()
    toll_amt = TOLL_RATES.get(v_type, DEFAULT_TOLL)
    balance  = vehicle["balance"]

    # Step 5: Insufficient balance
    if balance < toll_amt:
        return {
            "status":            "insufficient_balance",
            "message":           (f"Insufficient balance for {vehicle['owner_name']}. "
                                  f"Available: ₹{balance}, Required: ₹{toll_amt}. "
                                  f"Please recharge your FASTag."),
            "vehicle_number":    vehicle["vehicle_number"],
            "owner_name":        vehicle["owner_name"],
            "vehicle_type":      v_type.capitalize(),
            "toll_amount":       toll_amt,
            "remaining_balance": balance,
            "receipt_id":        None,
            "date_time":         None,
        }, 200

    # Step 6: Deduct & save
    new_balance = balance - toll_amt
    db[v_index]["balance"] = new_balance
    try:
        save_database(db)
    except Exception as e:
        return {"status": "failed", "message": f"DB write error: {e}"}, 500

    # Step 7: Receipt
    receipt_id = generate_receipt_id()
    date_time  = datetime.now().strftime("%d %b %Y, %I:%M %p")

    return {
        "status":            "success",
        "message":           f"Toll of ₹{toll_amt} deducted successfully. Safe journey!",
        "vehicle_number":    vehicle["vehicle_number"],
        "owner_name":        vehicle["owner_name"],
        "vehicle_type":      v_type.capitalize(),
        "toll_amount":       toll_amt,
        "remaining_balance": new_balance,
        "receipt_id":        receipt_id,
        "date_time":         date_time,
    }, 200


# ─── Route: Health Check ────────────────────────────────────────
@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "TOLLNET backend is running."})


# ─── Route: Camera Capture (original, kept intact) ──────────────
@app.route("/process-image", methods=["POST"])
def process_image():
    if "image" not in request.files:
        return jsonify({"status": "failed", "message": "No image received."}), 400
    try:
        file_bytes = np.frombuffer(request.files["image"].read(), dtype=np.uint8)
        img_cv = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img_cv is None:
            raise ValueError("Cannot decode image.")
    except Exception as e:
        return jsonify({"status": "failed", "message": str(e)}), 422
    result, code = process_vehicle_image(img_cv)
    return jsonify(result), code


# ─── Route: File Upload — NEW ────────────────────────────────────
@app.route("/upload-plate", methods=["POST"])
def upload_plate():
    """
    Accepts an uploaded image (JPG/PNG/BMP) or PDF of a number plate.
    Extracts vehicle number via OCR, matches DB, deducts toll, returns receipt.
    """
    if "file" not in request.files:
        return jsonify({"status": "failed", "message": "No file uploaded. Use key 'file'."}), 400

    uploaded  = request.files["file"]
    filename  = (uploaded.filename or "").lower()
    raw_bytes = uploaded.read()

    if not raw_bytes:
        return jsonify({"status": "failed", "message": "Uploaded file is empty."}), 400

    img_cv = None

    if filename.endswith(".pdf"):
        try:
            img_cv = pdf_to_image(raw_bytes)
        except RuntimeError as e:
            return jsonify({"status": "failed", "message": str(e)}), 500
        if img_cv is None:
            return jsonify({"status": "failed", "message": "Could not extract page from PDF."}), 422
    else:
        file_bytes = np.frombuffer(raw_bytes, dtype=np.uint8)
        img_cv = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img_cv is None:
            return jsonify({
                "status":  "failed",
                "message": "Could not decode the uploaded file. "
                           "Supported formats: JPG, PNG, BMP, WEBP, PDF."
            }), 422

    result, code = process_vehicle_image(img_cv)
    return jsonify(result), code


# ─── Run ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  TOLLNET Backend v2 Starting...")
    print("  Camera : POST /process-image")
    print("  Upload : POST /upload-plate")
    print("  URL    : http://127.0.0.1:5001")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5001, debug=True)