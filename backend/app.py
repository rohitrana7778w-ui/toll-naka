"""
TOLLNET — Smart Toll Collection System
Backend: app.py  (Flask API — v6)
"""

import os, io, re, json, uuid, numpy as np, cv2
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

TOLL_RATES  = {"car": 100, "truck": 150, "bus": 150, "bike": 50}
DEFAULT_TOLL = 100

def load_db():
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)

def generate_receipt_id():
    return f"TN-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

def generate_toll_id(vehicle_number):
    clean = re.sub(r"[^A-Z0-9]", "", vehicle_number.upper())[:10]
    return f"TOLL-{clean}-{uuid.uuid4().hex[:4].upper()}"

def generate_receipt_pdf(receipt_data):
    from reportlab.lib.pagesizes import A5
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
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
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=8))
    story.append(Paragraph("RECEIPT NUMBER", ps("RL", fontSize=8, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#888888"), alignment=1, spaceAfter=2)))
    story.append(Paragraph(receipt_data["receipt_id"], ps("RI", fontSize=12,
        fontName="Helvetica-Bold", textColor=colors.HexColor("#2563eb"), alignment=1, spaceAfter=4)))
    story.append(Paragraph(f"Date &amp; Time: {receipt_data['date_time']}", ps("DT", fontSize=8,
        textColor=colors.HexColor("#555555"), alignment=1, spaceAfter=10)))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd"), spaceAfter=8))
    lbl = ps("L", fontSize=9, textColor=colors.HexColor("#666666"))
    val = ps("V", fontSize=9, fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a2e"), alignment=2)
    rows = [
        [Paragraph("Vehicle Number", lbl), Paragraph(receipt_data["vehicle_number"], val)],
        [Paragraph("Owner Name", lbl), Paragraph(receipt_data["owner_name"], val)],
        [Paragraph("Vehicle Type", lbl), Paragraph(receipt_data["vehicle_type"], val)],
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
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd"), spaceAfter=8))
    story.append(Paragraph("Thank you for using TOLLNET  |  Safe Journey!", ps("F", fontSize=7.5,
        textColor=colors.HexColor("#888888"), alignment=1)))
    story.append(Paragraph("This is a computer-generated receipt.", ps("F2", fontSize=7.5,
        textColor=colors.HexColor("#aaaaaa"), alignment=1)))
    doc.build(story)
    buffer.seek(0)
    return buffer

def process_vehicle_number(vehicle_number):
    try:
        db = load_db()
    except Exception as e:
        return {"status": "failed", "message": f"Database error: {e}"}, 500
    vehicle = None
    v_index = None
    for i, v in enumerate(db["vehicles"]):
        if v["vehicle_number"].strip().upper() == vehicle_number.upper():
            vehicle = v; v_index = i; break
    if vehicle is None:
        return {"status": "not_found", "message": f"Vehicle '{vehicle_number}' is not registered.",
            "vehicle_number": vehicle_number, "owner_name": None, "vehicle_type": None,
            "toll_amount": None, "remaining_balance": None, "receipt_id": None, "date_time": None, "pdf_url": None}, 200
    v_type = vehicle.get("vehicle_type", "car").lower()
    toll_amt = TOLL_RATES.get(v_type, DEFAULT_TOLL)
    balance = vehicle["balance"]
    if balance < toll_amt:
        return {"status": "insufficient_balance",
            "message": f"Insufficient balance for {vehicle['owner_name']}. Available: Rs.{balance}, Required: Rs.{toll_amt}. Please recharge.",
            "vehicle_number": vehicle["vehicle_number"], "owner_name": vehicle["owner_name"],
            "vehicle_type": v_type.capitalize(), "toll_amount": toll_amt,
            "remaining_balance": balance, "receipt_id": None, "date_time": None, "pdf_url": None}, 200
    new_balance = balance - toll_amt
    db["vehicles"][v_index]["balance"] = new_balance
    db["admin_stats"]["vehicle_count"] += 1
    db["admin_stats"]["total_revenue"]  += toll_amt
    receipt_id = generate_receipt_id()
    date_time  = datetime.now().strftime("%d %b %Y, %I:%M %p")
    db["transactions"].insert(0, {"receipt_id": receipt_id, "date_time": date_time,
        "vehicle_number": vehicle["vehicle_number"], "owner_name": vehicle["owner_name"],
        "vehicle_type": v_type.capitalize(), "toll_amount": toll_amt, "remaining_balance": new_balance})
    db["transactions"] = db["transactions"][:200]
    try:
        save_db(db)
    except Exception as e:
        return {"status": "failed", "message": f"DB write error: {e}"}, 500
    from urllib.parse import quote
    pdf_url = (f"/download-receipt?receipt_id={quote(receipt_id)}"
        f"&vehicle_number={quote(vehicle['vehicle_number'])}&owner_name={quote(vehicle['owner_name'])}"
        f"&vehicle_type={quote(v_type.capitalize())}&toll_amount={toll_amt}"
        f"&remaining_balance={new_balance}&date_time={quote(date_time)}")
    return {"status": "success", "message": f"Toll of Rs.{toll_amt} deducted. Safe journey!",
        "vehicle_number": vehicle["vehicle_number"], "owner_name": vehicle["owner_name"],
        "vehicle_type": v_type.capitalize(), "toll_amount": toll_amt,
        "remaining_balance": new_balance, "receipt_id": receipt_id, "date_time": date_time, "pdf_url": pdf_url}, 200

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
            return jsonify({"success": True, "role": user["role"], "name": user["name"], "username": user["username"]}), 200
    return jsonify({"success": False, "message": "Invalid username or password."}), 401

@app.route("/admin/stats", methods=["GET"])
def admin_stats():
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    stats  = db.get("admin_stats", {"vehicle_count": 0, "total_revenue": 0})
    recent = db.get("transactions", [])[:10]
    return jsonify({"vehicle_count": stats["vehicle_count"], "total_revenue": stats["total_revenue"],
                    "recent_transactions": recent}), 200

@app.route("/admin/transactions", methods=["GET"])
def admin_transactions():
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    transactions = db.get("transactions", [])
    return jsonify({"transactions": transactions, "total": len(transactions)}), 200

@app.route("/admin/recharge-requests", methods=["GET"])
def admin_recharge_requests():
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"requests": db.get("recharge_requests", [])}), 200

@app.route("/admin/recharge-request/<req_id>/action", methods=["POST"])
def admin_recharge_action(req_id):
    data = request.get_json(silent=True) or {}
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
        found = False
        for v in db["vehicles"]:
            if v["vehicle_number"].upper() == req_obj["vehicle_number"].upper():
                v["balance"] += req_obj["amount"]; found = True; break
        if not found:
            return jsonify({"success": False, "message": f"Vehicle not found."}), 404
        db["recharge_requests"][req_idx]["status"] = "APPROVED"
        msg = f"Recharge of Rs.{req_obj['amount']} approved."
    else:
        db["recharge_requests"][req_idx]["status"] = "REJECTED"
        msg = f"Recharge request rejected."
    db["recharge_requests"][req_idx]["resolved_at"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
    try:
        save_db(db)
    except Exception as e:
        return jsonify({"success": False, "message": f"DB write error: {e}"}), 500
    return jsonify({"success": True, "message": msg, "status": db["recharge_requests"][req_idx]["status"]}), 200

@app.route("/recharge-request", methods=["POST"])
def submit_recharge_request():
    data = request.get_json(silent=True) or {}
    vehicle_number = data.get("vehicle_number", "").strip().upper()
    amount_raw = data.get("amount", 0)
    if not vehicle_number:
        return jsonify({"success": False, "message": "Vehicle number is required."}), 400
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
    if not any(v["vehicle_number"].upper() == vehicle_number for v in db["vehicles"]):
        return jsonify({"success": False, "message": f"Vehicle '{vehicle_number}' not registered."}), 404
    if any(r["vehicle_number"].upper() == vehicle_number and r["status"] == "PENDING"
           for r in db.get("recharge_requests", [])):
        return jsonify({"success": False, "message": "A recharge request is already pending."}), 400
    req_id = "RCH-" + uuid.uuid4().hex[:8].upper()
    created_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
    if "recharge_requests" not in db:
        db["recharge_requests"] = []
    db["recharge_requests"].insert(0, {"id": req_id, "vehicle_number": vehicle_number,
        "amount": amount, "status": "PENDING", "created_at": created_at, "resolved_at": None})
    db["recharge_requests"] = db["recharge_requests"][:500]
    try:
        save_db(db)
    except Exception as e:
        return jsonify({"success": False, "message": f"DB write error: {e}"}), 500
    return jsonify({"success": True, "message": f"Recharge request of Rs.{amount} submitted.",
        "request_id": req_id, "status": "PENDING", "created_at": created_at}), 200

@app.route("/recharge-status", methods=["GET"])
def recharge_status():
    vehicle_number = request.args.get("vehicle_number", "").strip().upper()
    if not vehicle_number:
        return jsonify({"success": False, "message": "vehicle_number is required."}), 400
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500
    user_requests = [r for r in db.get("recharge_requests", [])
                     if r["vehicle_number"].upper() == vehicle_number]
    return jsonify({"success": True, "requests": user_requests}), 200

# ── NEW: Register vehicle ─────────────────────────────────────────────────────

@app.route("/admin/register-vehicle", methods=["POST"])
def register_vehicle():
    data = request.get_json(silent=True) or {}
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

    toll_id       = generate_toll_id(vehicle_number)
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

    return jsonify({"success": True,
        "message": f"Vehicle '{vehicle_number}' registered successfully.",
        "toll_id": toll_id, "vehicle_number": vehicle_number,
        "owner_name": name, "registered_at": registered_at}), 201

# ── NEW: Vehicle details lookup ───────────────────────────────────────────────

@app.route("/vehicle-details", methods=["GET"])
def vehicle_details():
    vehicle_number = re.sub(r"[^A-Za-z0-9]", "", request.args.get("vehicle_number", "")).upper()
    if not vehicle_number:
        return jsonify({"success": False, "message": "vehicle_number is required."}), 400
    try:
        db = load_db()
    except Exception as e:
        return jsonify({"success": False, "message": f"Database error: {e}"}), 500
    for v in db["vehicles"]:
        if v["vehicle_number"].upper() == vehicle_number:
            aadhaar_raw = v.get("aadhaar", "")
            aadhaar_masked = ("XXXX-XXXX-" + aadhaar_raw[-4:]) if len(aadhaar_raw) == 12 else "—"
            return jsonify({"success": True,
                "vehicle_number": v["vehicle_number"],
                "owner_name":     v.get("owner_name", "—"),
                "vehicle_type":   v.get("vehicle_type", "—").capitalize(),
                "balance":        v.get("balance", 0),
                "toll_id":        v.get("toll_id", "Legacy — no Toll ID assigned"),
                "phone":          v.get("phone", "—"),
                "dob":            v.get("dob", "—"),
                "aadhaar":        aadhaar_masked,
                "registered_at":  v.get("registered_at", "—"),
            }), 200
    return jsonify({"success": False, "message": f"Vehicle '{vehicle_number}' not found."}), 404

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
        return jsonify({"status": "failed", "message": "Could not read vehicle number from image.",
            "vehicle_number": None, "owner_name": None, "vehicle_type": None,
            "toll_amount": None, "remaining_balance": None, "receipt_id": None, "date_time": None, "pdf_url": None}), 200
    result, code = process_vehicle_number(vehicle_number)
    return jsonify(result), code

@app.route("/process-manual", methods=["POST"])
def process_manual():
    data = request.get_json(silent=True) or {}
    raw_number = data.get("vehicle_number", "").strip()
    if not raw_number:
        return jsonify({"status": "failed", "message": "Vehicle number is required.",
            "vehicle_number": None, "owner_name": None, "vehicle_type": None,
            "toll_amount": None, "remaining_balance": None, "receipt_id": None, "date_time": None, "pdf_url": None}), 400
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_number).upper()
    if len(cleaned) < 3:
        return jsonify({"status": "failed", "message": "Invalid vehicle number.",
            "vehicle_number": raw_number, "owner_name": None, "vehicle_type": None,
            "toll_amount": None, "remaining_balance": None, "receipt_id": None, "date_time": None, "pdf_url": None}), 400
    result, code = process_vehicle_number(cleaned)
    return jsonify(result), code

@app.route("/download-receipt", methods=["GET"])
def download_receipt():
    receipt_data = {
        "receipt_id":        request.args.get("receipt_id", "N/A"),
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
        return jsonify({"status": "failed", "message": f"PDF generation error: {e}"}), 500
    return send_file(pdf_buffer, mimetype="application/pdf",
        as_attachment=True, download_name=f"receipt_{receipt_data['receipt_id']}.pdf")

if __name__ == "__main__":
    print("=" * 60)
    print("  TOLLNET Backend v6 — http://127.0.0.1:5001")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=True)
