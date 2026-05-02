"""
TOLLNET — Smart Toll Collection System
Backend: app.py (Flask API)

Endpoint: POST /process-image
  - Receives an image from the frontend
  - Passes it to the OCR module to extract a Vehicle ID
  - Looks up the Vehicle ID in database.json
  - Deducts toll if vehicle found and has sufficient balance
  - Returns a JSON response
"""

import os
import json
import numpy as np
import cv2
from flask import Flask, request, jsonify
from flask_cors import CORS

# Import our custom OCR module
from ocr import extract_vehicle_id

# ─── App Setup ──────────────────────────────────────────────────
app = Flask(__name__)

# Enable CORS so the browser frontend (served from a different origin)
# can send requests to this Flask server
CORS(app)

# ─── Paths ──────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, "database.json")
UPLOAD_DIR  = os.path.join(BASE_DIR, "uploads")

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ─── Helper: Load Database ──────────────────────────────────────
def load_database():
    """Read the vehicle database from disk and return as a list."""
    with open(DB_PATH, "r") as f:
        return json.load(f)


# ─── Helper: Save Database ──────────────────────────────────────
def save_database(data):
    """Persist the updated vehicle database back to disk."""
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ─── Route: Health Check ────────────────────────────────────────
@app.route("/", methods=["GET"])
def health_check():
    """Simple health-check endpoint to verify the server is running."""
    return jsonify({"status": "ok", "message": "TOLLNET backend is running."})


# ─── Route: Process Image ────────────────────────────────────────
@app.route("/process-image", methods=["POST"])
def process_image():
    """
    Main endpoint.
    Expects a multipart/form-data POST with an 'image' file field.
    Returns JSON with transaction details.
    """

    # ── Step 1: Validate request ──────────────────────────────
    if "image" not in request.files:
        return jsonify({
            "status":    "failed",
            "message":   "No image file received. Send a file with key 'image'.",
            "vehicle_id": None,
            "owner":      None,
            "toll_deducted": None,
            "remaining_balance": None
        }), 400

    image_file = request.files["image"]

    # ── Step 2: Read image bytes → OpenCV format ──────────────
    try:
        file_bytes = np.frombuffer(image_file.read(), dtype=np.uint8)
        img_cv = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

        if img_cv is None:
            raise ValueError("OpenCV could not decode the image.")
    except Exception as e:
        return jsonify({
            "status":  "failed",
            "message": f"Image processing error: {str(e)}",
            "vehicle_id": None, "owner": None,
            "toll_deducted": None, "remaining_balance": None
        }), 422

    # ── Step 3: Run OCR to extract Vehicle ID ─────────────────
    vehicle_id = extract_vehicle_id(img_cv)

    if not vehicle_id:
        return jsonify({
            "status":    "failed",
            "message":   "Could not read a Vehicle ID from the image. "
                         "Ensure the ID card is clearly visible and well-lit.",
            "vehicle_id": None,
            "owner":      None,
            "toll_deducted": None,
            "remaining_balance": None
        }), 200

    # ── Step 4: Look up vehicle in database ───────────────────
    try:
        db = load_database()
    except Exception as e:
        return jsonify({
            "status":  "failed",
            "message": f"Database read error: {str(e)}",
            "vehicle_id": vehicle_id, "owner": None,
            "toll_deducted": None, "remaining_balance": None
        }), 500

    # Search for vehicle (case-insensitive match)
    vehicle = None
    vehicle_index = None
    for i, v in enumerate(db):
        if v["vehicle_id"].strip().upper() == vehicle_id.upper():
            vehicle = v
            vehicle_index = i
            break

    # ── Step 5: Vehicle not registered ───────────────────────
    if vehicle is None:
        return jsonify({
            "status":    "not_found",
            "message":   f"Vehicle ID '{vehicle_id}' is not registered in the system.",
            "vehicle_id": vehicle_id,
            "owner":      None,
            "toll_deducted": None,
            "remaining_balance": None
        }), 200

    # ── Step 6: Check balance ─────────────────────────────────
    balance   = vehicle["balance"]
    toll_rate = vehicle["toll_rate"]

    if balance < toll_rate:
        return jsonify({
            "status":    "insufficient_balance",
            "message":   (f"Insufficient balance for {vehicle['owner']}. "
                          f"Available: ₹{balance}, Required: ₹{toll_rate}. "
                          f"Please recharge your account."),
            "vehicle_id":        vehicle["vehicle_id"],
            "owner":             vehicle["owner"],
            "toll_deducted":     0,
            "remaining_balance": balance
        }), 200

    # ── Step 7: Deduct toll & save ────────────────────────────
    new_balance = balance - toll_rate
    db[vehicle_index]["balance"] = new_balance

    try:
        save_database(db)
    except Exception as e:
        return jsonify({
            "status":  "failed",
            "message": f"Database write error: {str(e)}",
            "vehicle_id": vehicle["vehicle_id"], "owner": vehicle["owner"],
            "toll_deducted": None, "remaining_balance": None
        }), 500

    # ── Step 8: Return success response ──────────────────────
    return jsonify({
        "status":            "success",
        "message":           (f"Toll of ₹{toll_rate} successfully deducted for "
                              f"{vehicle['owner']}. Safe journey!"),
        "vehicle_id":        vehicle["vehicle_id"],
        "owner":             vehicle["owner"],
        "toll_deducted":     toll_rate,
        "remaining_balance": new_balance
    }), 200


# ─── Run ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  TOLLNET Backend Starting...")
    print("  Endpoint: http://127.0.0.1:5000/process-image")
    print("=" * 50)
    # debug=True gives useful error messages during development.
    # Set debug=False for production.
    app.run(host="0.0.0.0", port=5001, debug=True)