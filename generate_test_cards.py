"""
TOLLNET — Test ID Card Generator
generate_test_cards.py

Run this script to create printable PNG images of all vehicle IDs
in database.json. Print them and hold them in front of the camera
to test the toll system without a real vehicle.

Usage:
    python generate_test_cards.py
"""

import json
import os

# Use PIL/Pillow to draw the cards
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "backend", "database.json")
OUT_DIR  = os.path.join(BASE_DIR, "test_cards")

os.makedirs(OUT_DIR, exist_ok=True)

# Card dimensions (pixels at 150 DPI → ~5 × 3 inches)
CARD_W, CARD_H = 750, 450

# Load database
with open(DB_PATH) as f:
    vehicles = json.load(f)

for v in vehicles:
    img  = Image.new("RGB", (CARD_W, CARD_H), color="#0b0f1a")
    draw = ImageDraw.Draw(img)

    # Try to use a system monospace font; fall back to default
    try:
        id_font   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 80)
        info_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        label_font= ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except OSError:
        id_font = info_font = label_font = ImageFont.load_default()

    # Border
    draw.rectangle([8, 8, CARD_W-8, CARD_H-8], outline="#f5a623", width=3)

    # Header bar
    draw.rectangle([0, 0, CARD_W, 60], fill="#111827")
    draw.text((20, 14), "⬡  TOLLNET VEHICLE ID CARD", font=label_font, fill="#00d4aa")

    # Vehicle ID (large, centered)
    id_text = v["vehicle_id"]
    bbox = draw.textbbox((0, 0), id_text, font=id_font)
    tw = bbox[2] - bbox[0]
    draw.text(((CARD_W - tw) / 2, 110), id_text, font=id_font, fill="#f5a623")

    # Owner & balance info
    draw.text((40, 240), f"Owner    :  {v['owner']}", font=info_font, fill="#e8edf5")
    draw.text((40, 285), f"Balance  :  ₹ {v['balance']}", font=info_font, fill="#e8edf5")
    draw.text((40, 330), f"Toll Rate:  ₹ {v['toll_rate']} per crossing", font=info_font, fill="#8a9bb5")

    # Footer
    draw.rectangle([0, CARD_H-50, CARD_W, CARD_H], fill="#111827")
    draw.text((20, CARD_H-36), "Hold this card in front of the camera to test the system.",
              font=label_font, fill="#3d5070")

    filename = os.path.join(OUT_DIR, f"card_{v['vehicle_id']}.png")
    img.save(filename)
    print(f"  ✓ Saved: {filename}")

print(f"\nAll test cards saved to: {OUT_DIR}/")
print("Print them or show them on screen to test the toll system.")