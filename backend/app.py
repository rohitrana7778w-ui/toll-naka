"""
TOLLNET — Smart Toll Collection System
Backend: app.py  (Flask API — v7)

Key changes from v6:
  - Toll deduction now works by TOLL ID (3 letters + 3 digits, e.g. QYP299)
    in addition to vehicle number scan (OCR/manual still works; backend
    resolves vehicle from toll_id internally)
  - /process-by-toll-id   : Deduct toll using Toll ID
  - /recharge-status      : Now accepts toll_id OR vehicle_number
  - /recharge-request     : Now accepts toll_id OR vehicle_number
  - /vehicle-by-toll-id   : Look up vehicle details by toll_id
  - Pre-registered vehicles already have toll_ids assigned in database.json
  - New registrations get 3-letter + 3-digit toll_id (e.g. TRF847)
"""

import os, io, re, json, uuid, random, string
import numpy as np, cv2
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from ocr import extract_vehicle_id

app = Flask(__name__)
CORS(app, supports_credentials=True)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, "database.json")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

TOLL_RATES   = {"car": 100, "truck": 150, "bus": 150, "bike": 50}
DEFAULT_TOLL = 100

# ── DB helpers ────────────────────────────────────────────────────────────────

def load_db():
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)

def generate_receipt_id():
    return f"TN-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

def generate_toll_id(db):
    """Generate unique Toll ID: 3 uppercase letters + 3 digits, e.g. TRF847"""
    used = {v.get("toll_id", "") for v in db.get("vehicles", [])}
    for _ in range(1000):
        letters = ''.join(random.choices(string.ascii_uppercase, k=3))
        digits  = ''.join(random.choices(string.digits, k=3))
        tid = letters + digits
        if tid not in used:
            return tid
    raise RuntimeError("Cannot generate unique toll ID")

def find_vehicle_by_toll_id(db, toll_id):
    """Find vehicle and its index by toll_id (case-insensitive)."""
    tid = toll_id.strip().upper()
    for i, v in enumerate(db["vehicles"]):
        if v.get("toll_id", "").upper() == tid:
            return v, i
    return None, None

def find_vehicle_by_number(db, vehicle_number):
    vn = vehicle_number.strip().upper()
    for i, v in enumerate(db["vehicles"]):
        if v["vehicle_number"].upper() == vn:
            return v, i
    return None, None

# ── PDF receipt ───────────────────────────────────────────────────────────────

def generate_receipt_pdf(receipt_data):
    from reportlab.lib.pagesizes import A5
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer, HRFlowable)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A5,
        rightMargin=15*mm, leftMargin=15*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    def ps(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)
    story = []
    story.append(Paragraph("TOLLNET", ps("T", fontSize=22, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1a1a2e"), alignment=1, spaceAfter=2)))
    story.append(Paragraph("Smart Toll Collection System", ps("S", fontSize=9,
        textColor=colors.HexColor("#666666"), alignment=1, spaceAfter=6)))
    story.append(HRFlowable(width="100%", thickness=1.5,
        color=colors.HexColor("#2563eb"), spaceAfter=8))
    story.append(Paragraph("RECEIPT NUMBER", ps("RL", fontSize=8, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#888888"), alignment=1, spaceAfter=2)))
    story.append(Paragraph(receipt_data["receipt_id"], ps("RI", fontSize=12,
        fontName="Helvetica-Bold", textColor=colors.HexColor("#2563eb"), alignment=1, spaceAfter=4)))
    story.append(Paragraph(f"Date &amp; Time: {receipt_data['date_time']}", ps("DT", fontSize=8,
        textColor=colors.HexColor("#555555"), alignment=1, spaceAfter=10)))
    story.append(HRFlowable(width="100%", thickness=0.5,
        color=colors.HexColor("#dddddd"), spaceAfter=8))
    lbl = ps("L", fontSize=9, textColor=colors.HexColor("#666666"))
    val = ps("V", fontSize=9, fontName="Helvetica-Bold",
             textColor=colors.HexColor("#1a1a2e"), alignment=2)
    rows = [
        [Paragraph("Toll ID",         lbl), Paragraph(receipt_data.get("toll_id","—"), val)],
        [Paragraph("Vehicle Number",  lbl), Paragraph(receipt_data["vehicle_number"], val)],
        [Paragraph("Owner Name",      lbl), Paragraph(receipt_data["owner_name"], val)],
        [Paragraph("Vehicle Type",    lbl), Paragraph(receipt_data["vehicle_type"], val)],
        [Paragraph("Remaining Balance", lbl), Paragraph(f"Rs. {receipt_data['remaining_balance']}", val)],
    ]
    tbl = Table(rows, colWidths=["50%", "50%"])
    tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#f8f9fa"), colors.white]),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 10))
    toll_rows = [[
        Paragraph("TOLL AMOUNT DEDUCTED", ps("TL", fontSize=9, fontName="Helvetica-Bold",
            textColor=colors.HexColor("#15803d"))),
        Paragraph(f"Rs. {receipt_data['toll_amount']}", ps("TV", fontSize=14,
            fontName="Helvetica-Bold", textColor=colors.HexColor("#16a34a"), alignment=2)),
    ]]
    toll_tbl = Table(toll_rows, colWidths=["55%", "45%"])
    toll_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f0fdf4")),
        ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 10), ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("BOX", (0,0), (-1,-1), 1.5, colors.HexColor("#16a34a")),
    ]))
    story.append(toll_tbl)
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.5,
        color=colors.HexColor("#dddddd"), spaceAfter=8))
    story.append(Paragraph("Thank you for using TOLLNET  |  Safe Journey!", ps("F", fontSize=7.5,
        textColor=colors.HexColor("#888888"), alignment=1)))
    story.append(Paragraph("This is a computer-generated receipt.", ps("F2", fontSize=7.5,
        textColor=colors.HexColor("#aaaaaa"), alignment=1)))
    doc.build(story)
    buffer.seek(0)
    return buffer

# ── Core deduction logic (shared) ─────────────────────────────────────────────

def _deduct_toll(db, vehicle, v_index):
    """Deduct toll from vehicle balance. Returns (response_dict, http_code)."""
    v_type   = vehicle.get("vehicle_type", "car").lower()
    toll_amt = TOLL_RATES.get(v_type, DEFAULT_TOLL)
    balance  = vehicle["balance"]
    toll_id  = vehicle.get("toll_id", "—")

    if balance < toll_amt:
        return {
            "status": "insufficient_balance",
            "message": (f"Insufficient balance for {vehicle['owner_name']}. "
                        f"Available: Rs.{balance}, Required: Rs.{toll_amt}. "
                        f"Please recharge your FASTag."),
            "toll_id": toll_id,
            "vehicle_number": vehicle["vehicle_number"], "owner_name": vehicle["owner_name"],
            "vehicle_type": v_type.capitalize(), "toll_amount": toll_amt,
            "remaining_balance": balance, "receipt_id": None, "date_time": None, "pdf_url": None,
        }, 200

    new_balance = balance - toll_amt
    db["vehicles"][v_index]["balance"] = new_balance
    db["admin_stats"]["vehicle_count"] += 1
    db["admin_stats"]["total_revenue"]  += toll_amt

    receipt_id = generate_receipt_id()
    date_time  = datetime.now().strftime("%d %b %Y, %I:%M %p")

    db["transactions"].insert(0, {
        "receipt_id":        receipt_id,
        "date_time":         date_time,
        "toll_id":           toll_id,
        "vehicle_number":    vehicle["vehicle_number"],
        "owner_name":        vehicle["owner_name"],
        "vehicle_type":      v_type.capitalize(),
        "toll_amount":       toll_amt,
        "remaining_balance": new_balance,
    })
    db["transactions"] = db["transactions"][:200]
    save_db(db)

    from urllib.parse import quote
    pdf_url = (
        f"/download-receipt"
        f"?receipt_id={quote(receipt_id)}"
        f"&toll_id={quote(toll_id)}"
        f"&vehicle_number={quote(vehicle['vehicle_number'])}"
        f"&owner_name={quote(vehicle['owner_name'])}"
        f"&vehicle_type={quote(v_type.capitalize())}"
        f"&toll_amount={toll_amt}"
        f"&remaining_balance={new_balance}"
        f"&date_time={quote(date_time)}"
    )

    return {
        "status": "success",
        "message": f"Toll of Rs.{toll_amt} deducted. Safe journey!",
        "toll_id": toll_id,
        "vehicle_number": vehicle["vehicle_number"], "owner_name": vehicle["owner_name"],
        "vehicle_type": v_type.capitalize(), "toll_amount": toll_amt,
        "remaining_balance": new_balance, "receipt_id": receipt_id,
        "date_time": date_time, "pdf_url": pdf_url,
    }, 200


def process_vehicle_number(vehicle_number):
    """Legacy: look up by vehicle number plate (used by OCR/manual entry)."""
    try:
        db = load_db()
    except Exception as e:
        return {"status": "failed", "message": f"Database error: {e}"}, 500

    vehicle, v_index = find_vehicle_by_number(db, vehicle_number)
    if vehicle is None:
        return {
            "status": "not_found",
            "message": f"Vehicle '{vehicle_number}' is not registered.",
            "toll_id": None,
            "vehicle_number": vehicle_number, "owner_name": None, "vehicle_type": None,
            "toll_amount": None, "remaining_balance": None,
            "receipt_id": None, "date_time": None, "pdf_url": None,
        }, 200

    try:
        result, code = _deduct_toll(db, vehicle, v_index)
    except Exception as e:
        return {"status": "failed", "message": f"DB write error: {e}"}, 500
    return result, code

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "TOLLNET backend is running."})

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required."}), 400
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500
    for user in db["users"]:
        if user["username"].lower() == username and user["password"] == password:
            return jsonify({"success": True, "role": user["role"],
                            "name": user["name"], "username": user["username"]}), 200
    return jsonify({"success": False, "message": "Invalid username or password."}), 401

@app.route("/admin/stats", methods=["GET"])
def admin_stats():
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    stats  = db.get("admin_stats", {"vehicle_count": 0, "total_revenue": 0})
    recent = db.get("transactions", [])[:10]
    return jsonify({"vehicle_count": stats["vehicle_count"],
                    "total_revenue": stats["total_revenue"],
                    "recent_transactions": recent}), 200

@app.route("/admin/transactions", methods=["GET"])
def admin_transactions():
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"transactions": db.get("transactions", []),
                    "total": len(db.get("transactions", []))}), 200

@app.route("/admin/recharge-requests", methods=["GET"])
def admin_recharge_requests():
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"requests": db.get("recharge_requests", [])}), 200

@app.route("/admin/recharge-request/<req_id>/action", methods=["POST"])
def admin_recharge_action(req_id):
    data   = request.get_json(silent=True) or {}
    action = data.get("action", "").lower()
    if action not in ("accept", "reject"):
        return jsonify({"success": False, "message": "Action must be 'accept' or 'reject'."}), 400
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500

    req_obj = req_idx = None
    for i, r in enumerate(db.get("recharge_requests", [])):
        if r["id"] == req_id:
            req_obj = r; req_idx = i; break
    if req_obj is None:
        return jsonify({"success": False, "message": "Request not found."}), 404
    if req_obj["status"] != "PENDING":
        return jsonify({"success": False, "message": f"Request already {req_obj['status']}."}), 400

    if action == "accept":
        # Find vehicle by toll_id first, fall back to vehicle_number
        vehicle = None
        if req_obj.get("toll_id"):
            vehicle, _ = find_vehicle_by_toll_id(db, req_obj["toll_id"])
        if vehicle is None:
            vehicle, _ = find_vehicle_by_number(db, req_obj.get("vehicle_number", ""))
        if vehicle is None:
            return jsonify({"success": False, "message": "Vehicle not found."}), 404
        vehicle["balance"] += req_obj["amount"]
        db["recharge_requests"][req_idx]["status"] = "APPROVED"
        msg = f"Recharge of Rs.{req_obj['amount']} approved."
    else:
        db["recharge_requests"][req_idx]["status"] = "REJECTED"
        msg = "Recharge request rejected."

    db["recharge_requests"][req_idx]["resolved_at"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    try:
        save_db(db)
    except Exception as e:
        return jsonify({"success": False, "message": f"DB write error: {e}"}), 500
    return jsonify({"success": True, "message": msg,
                    "status": db["recharge_requests"][req_idx]["status"]}), 200

# ── NEW: Process toll by Toll ID ──────────────────────────────────────────────

@app.route("/process-by-toll-id", methods=["POST"])
def process_by_toll_id():
    """Deduct toll using Toll ID (primary method for booths)."""
    data    = request.get_json(silent=True) or {}
    toll_id = re.sub(r"[^A-Za-z0-9]", "", data.get("toll_id", "")).upper()
    if len(toll_id) != 6:
        return jsonify({
            "status": "failed",
            "message": "Invalid Toll ID. Must be 6 characters (3 letters + 3 digits).",
            "toll_id": toll_id, "vehicle_number": None, "owner_name": None,
            "vehicle_type": None, "toll_amount": None, "remaining_balance": None,
            "receipt_id": None, "date_time": None, "pdf_url": None,
        }), 400
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"status": "failed", "message": f"Database error: {e}"}), 500

    vehicle, v_index = find_vehicle_by_toll_id(db, toll_id)
    if vehicle is None:
        return jsonify({
            "status": "not_found",
            "message": f"No vehicle registered with Toll ID '{toll_id}'.",
            "toll_id": toll_id, "vehicle_number": None, "owner_name": None,
            "vehicle_type": None, "toll_amount": None, "remaining_balance": None,
            "receipt_id": None, "date_time": None, "pdf_url": None,
        }), 200

    try:
        result, code = _deduct_toll(db, vehicle, v_index)
    except Exception as e:
        return jsonify({"status": "failed", "message": f"DB write error: {e}"}), 500
    return jsonify(result), code

# ── Recharge request (accepts toll_id OR vehicle_number) ─────────────────────

@app.route("/recharge-request", methods=["POST"])
def submit_recharge_request():
    data      = request.get_json(silent=True) or {}
    toll_id_r = re.sub(r"[^A-Za-z0-9]", "", data.get("toll_id", "")).upper()
    vnum_r    = re.sub(r"[^A-Za-z0-9]", "", data.get("vehicle_number", "")).upper()
    amount_raw = data.get("amount", 0)

    if not toll_id_r and not vnum_r:
        return jsonify({"success": False, "message": "Toll ID or vehicle number is required."}), 400
    try:
        amount = int(amount_raw)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Amount must be a valid number."}), 400
    if amount <= 0:
        return jsonify({"success": False, "message": "Amount must be > 0."}), 400
    if amount > 10000:
        return jsonify({"success": False, "message": "Max recharge is Rs.10,000."}), 400

    try:
        db = load_db()
    except Exception as e:
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500

    # Resolve vehicle
    vehicle = None
    if toll_id_r:
        vehicle, _ = find_vehicle_by_toll_id(db, toll_id_r)
    if vehicle is None and vnum_r:
        vehicle, _ = find_vehicle_by_number(db, vnum_r)
    if vehicle is None:
        return jsonify({"success": False, "message": "Vehicle not found. Check your Toll ID or vehicle number."}), 404

    canonical_toll_id = vehicle.get("toll_id", "")
    canonical_vnum    = vehicle["vehicle_number"]

    # Check no existing pending request
    existing_pending = any(
        r.get("toll_id") == canonical_toll_id and r["status"] == "PENDING"
        for r in db.get("recharge_requests", [])
    )
    if existing_pending:
        return jsonify({"success": False, "message": "A recharge request is already pending for this Toll ID."}), 400

    req_id     = "RCH-" + uuid.uuid4().hex[:8].upper()
    created_at = datetime.now().strftime("%d %b %Y, %I:%M %p")

    if "recharge_requests" not in db:
        db["recharge_requests"] = []

    db["recharge_requests"].insert(0, {
        "id":             req_id,
        "toll_id":        canonical_toll_id,
        "vehicle_number": canonical_vnum,
        "owner_name":     vehicle.get("owner_name", "—"),
        "amount":         amount,
        "status":         "PENDING",
        "created_at":     created_at,
        "resolved_at":    None,
    })
    db["recharge_requests"] = db["recharge_requests"][:500]

    try:
        save_db(db)
    except Exception as e:
        return jsonify({"success": False, "message": f"DB write error: {e}"}), 500

    return jsonify({
        "success":        True,
        "message":        f"Recharge request of Rs.{amount} submitted.",
        "request_id":     req_id,
        "toll_id":        canonical_toll_id,
        "vehicle_number": canonical_vnum,
        "status":         "PENDING",
        "created_at":     created_at,
    }), 200

# ── Recharge status (accepts toll_id OR vehicle_number) ──────────────────────

@app.route("/recharge-status", methods=["GET"])
def recharge_status():
    """
    Query recharge requests by toll_id or vehicle_number.
    Optional: hours=N  → only return requests created within the last N hours.
    """
    toll_id_r = re.sub(r"[^A-Za-z0-9]", "", request.args.get("toll_id", "")).upper()
    vnum_r    = re.sub(r"[^A-Za-z0-9]", "", request.args.get("vehicle_number", "")).upper()
    hours_raw = request.args.get("hours", "")

    if not toll_id_r and not vnum_r:
        return jsonify({"success": False, "message": "toll_id or vehicle_number is required."}), 400

    try:
        db = load_db()
    except Exception as e:
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500

    # Resolve canonical toll_id
    canonical_toll_id = toll_id_r
    if not canonical_toll_id and vnum_r:
        v, _ = find_vehicle_by_number(db, vnum_r)
        if v:
            canonical_toll_id = v.get("toll_id", "")

    # If toll_id given but not found in vehicles, still search requests by it
    all_reqs = db.get("recharge_requests", [])
    matched = [
        r for r in all_reqs
        if r.get("toll_id", "").upper() == canonical_toll_id
        or (not canonical_toll_id and r.get("vehicle_number", "").upper() == vnum_r)
    ]

    # Apply time window filter if requested
    if hours_raw:
        try:
            hours = int(hours_raw)
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(hours=hours)
            def parse_dt(s):
                # Format stored: "02 May 2026, 02:27 PM"
                try:
                    return datetime.strptime(s, "%d %b %Y, %I:%M %p")
                except Exception:
                    return datetime.min
            matched = [r for r in matched if parse_dt(r.get("created_at", "")) >= cutoff]
        except (ValueError, TypeError):
            pass  # ignore bad hours param

    return jsonify({"success": True, "requests": matched,
                    "toll_id": canonical_toll_id}), 200

# ── Vehicle by Toll ID ────────────────────────────────────────────────────────

@app.route("/vehicle-by-toll-id", methods=["GET"])
def vehicle_by_toll_id():
    toll_id = re.sub(r"[^A-Za-z0-9]", "", request.args.get("toll_id", "")).upper()
    if not toll_id:
        return jsonify({"success": False, "message": "toll_id is required."}), 400
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500
    vehicle, _ = find_vehicle_by_toll_id(db, toll_id)
    if vehicle is None:
        return jsonify({"success": False, "message": f"No vehicle found with Toll ID '{toll_id}'."}), 404
    aadhaar_raw = vehicle.get("aadhaar", "")
    aadhaar_masked = ("XXXX-XXXX-" + aadhaar_raw[-4:]) if len(aadhaar_raw) == 12 else "—"
    return jsonify({
        "success":        True,
        "toll_id":        vehicle.get("toll_id", "—"),
        "vehicle_number": vehicle["vehicle_number"],
        "owner_name":     vehicle.get("owner_name", "—"),
        "vehicle_type":   vehicle.get("vehicle_type", "—").capitalize(),
        "balance":        vehicle.get("balance", 0),
        "phone":          vehicle.get("phone", "—"),
        "dob":            vehicle.get("dob", "—"),
        "aadhaar":        aadhaar_masked,
        "registered_at":  vehicle.get("registered_at", "—"),
    }), 200

# ── Vehicle details (by vehicle number) ──────────────────────────────────────

@app.route("/vehicle-details", methods=["GET"])
def vehicle_details():
    vnum = re.sub(r"[^A-Za-z0-9]", "", request.args.get("vehicle_number", "")).upper()
    if not vnum:
        return jsonify({"success": False, "message": "vehicle_number is required."}), 400
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500
    vehicle, _ = find_vehicle_by_number(db, vnum)
    if vehicle is None:
        return jsonify({"success": False, "message": f"Vehicle '{vnum}' not found."}), 404
    aadhaar_raw = vehicle.get("aadhaar", "")
    aadhaar_masked = ("XXXX-XXXX-" + aadhaar_raw[-4:]) if len(aadhaar_raw) == 12 else "—"
    return jsonify({
        "success":        True,
        "toll_id":        vehicle.get("toll_id", "—"),
        "vehicle_number": vehicle["vehicle_number"],
        "owner_name":     vehicle.get("owner_name", "—"),
        "vehicle_type":   vehicle.get("vehicle_type", "—").capitalize(),
        "balance":        vehicle.get("balance", 0),
        "phone":          vehicle.get("phone", "—"),
        "dob":            vehicle.get("dob", "—"),
        "aadhaar":        aadhaar_masked,
        "registered_at":  vehicle.get("registered_at", "—"),
    }), 200

# ── Admin: Register vehicle ───────────────────────────────────────────────────

@app.route("/admin/register-vehicle", methods=["POST"])
def register_vehicle():
    data           = request.get_json(silent=True) or {}
    name           = data.get("name", "").strip()
    aadhaar        = data.get("aadhaar", "").strip()
    phone          = data.get("phone", "").strip()
    dob            = data.get("dob", "").strip()
    vehicle_number = re.sub(r"[^A-Za-z0-9]", "", data.get("vehicle_number", "")).upper()
    vehicle_type   = data.get("vehicle_type", "car").strip().lower()

    if not name:
        return jsonify({"success": False, "message": "Name is required."}), 400
    if not re.fullmatch(r"\d{12}", aadhaar):
        return jsonify({"success": False, "message": "Aadhaar must be exactly 12 digits."}), 400
    if not re.fullmatch(r"\d{10}", phone):
        return jsonify({"success": False, "message": "Phone must be exactly 10 digits."}), 400
    if not dob:
        return jsonify({"success": False, "message": "Date of birth is required."}), 400
    if len(vehicle_number) < 4:
        return jsonify({"success": False, "message": "Vehicle number is invalid."}), 400
    if vehicle_type not in TOLL_RATES:
        vehicle_type = "car"

    try:
        db = load_db()
    except Exception as e:
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500

    for v in db["vehicles"]:
        if v["vehicle_number"].upper() == vehicle_number:
            return jsonify({"success": False, "message": f"Vehicle '{vehicle_number}' already registered."}), 400

    toll_id       = generate_toll_id(db)
    registered_at = datetime.now().strftime("%d %b %Y, %I:%M %p")

    db["vehicles"].append({
        "vehicle_number": vehicle_number,
        "owner_name":     name,
        "vehicle_type":   vehicle_type,
        "balance":        0,
        "toll_id":        toll_id,
        "aadhaar":        aadhaar,
        "phone":          phone,
        "dob":            dob,
        "registered_at":  registered_at,
    })
    try:
        save_db(db)
    except Exception as e:
        return jsonify({"success": False, "message": f"DB write error: {e}"}), 500

    return jsonify({
        "success":        True,
        "message":        f"Vehicle '{vehicle_number}' registered. Toll ID: {toll_id}",
        "toll_id":        toll_id,
        "vehicle_number": vehicle_number,
        "owner_name":     name,
        "registered_at":  registered_at,
    }), 201

# ── Image / manual processing ─────────────────────────────────────────────────

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
    vehicle_number = extract_vehicle_id(img_cv)
    if not vehicle_number:
        return jsonify({
            "status": "failed", "message": "Could not read vehicle number from image.",
            "toll_id": None, "vehicle_number": None, "owner_name": None, "vehicle_type": None,
            "toll_amount": None, "remaining_balance": None, "receipt_id": None,
            "date_time": None, "pdf_url": None,
        }), 200
    result, code = process_vehicle_number(vehicle_number)
    return jsonify(result), code

@app.route("/process-manual", methods=["POST"])
def process_manual():
    """
    Accept either:
      - toll_id   (6-char: 3 letters + 3 digits)  → deduct by toll_id
      - vehicle_number                              → deduct by vehicle number (legacy)
    Frontend manual-entry tab now sends toll_id.
    """
    data = request.get_json(silent=True) or {}
    raw_input  = data.get("vehicle_number", data.get("toll_id", "")).strip()
    cleaned    = re.sub(r"[^A-Za-z0-9]", "", raw_input).upper()

    if not cleaned:
        return jsonify({
            "status": "failed", "message": "Toll ID or vehicle number is required.",
            "toll_id": None, "vehicle_number": None, "owner_name": None, "vehicle_type": None,
            "toll_amount": None, "remaining_balance": None, "receipt_id": None,
            "date_time": None, "pdf_url": None,
        }), 400

    try:
        db = load_db()
    except Exception as e:
        return jsonify({"status": "failed", "message": f"Database error: {e}"}), 500

    # If input looks like a Toll ID (6 chars, 3 alpha + 3 digit), try toll_id first
    is_toll_id_format = len(cleaned) == 6 and cleaned[:3].isalpha() and cleaned[3:].isdigit()
    vehicle = v_index = None

    if is_toll_id_format:
        vehicle, v_index = find_vehicle_by_toll_id(db, cleaned)

    # Fall back to vehicle number lookup
    if vehicle is None:
        vehicle, v_index = find_vehicle_by_number(db, cleaned)

    if vehicle is None:
        return jsonify({
            "status": "not_found",
            "message": f"No vehicle found for '{cleaned}'. Check the Toll ID or vehicle number.",
            "toll_id": cleaned if is_toll_id_format else None,
            "vehicle_number": cleaned, "owner_name": None, "vehicle_type": None,
            "toll_amount": None, "remaining_balance": None, "receipt_id": None,
            "date_time": None, "pdf_url": None,
        }), 200

    try:
        result, code = _deduct_toll(db, vehicle, v_index)
    except Exception as e:
        return jsonify({"status": "failed", "message": f"DB write error: {e}"}), 500
    return jsonify(result), code

@app.route("/download-receipt", methods=["GET"])
def download_receipt():
    receipt_data = {
        "receipt_id":        request.args.get("receipt_id", "N/A"),
        "toll_id":           request.args.get("toll_id", "—"),
        "vehicle_number":    request.args.get("vehicle_number", "N/A"),
        "owner_name":        request.args.get("owner_name", "N/A"),
        "vehicle_type":      request.args.get("vehicle_type", "N/A"),
        "toll_amount":       request.args.get("toll_amount", "0"),
        "remaining_balance": request.args.get("remaining_balance", "0"),
        "date_time":         request.args.get("date_time", "N/A"),
    }
    try:
        pdf_buffer = generate_receipt_pdf(receipt_data)
    except Exception as e:
        return jsonify({"status": "failed", "message": f"PDF error: {e}"}), 500
    return send_file(pdf_buffer, mimetype="application/pdf",
        as_attachment=True, download_name=f"receipt_{receipt_data['receipt_id']}.pdf")

if __name__ == "__main__":
    print("=" * 60)
    print("  TOLLNET Backend v7 — http://127.0.0.1:5001")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=True)
