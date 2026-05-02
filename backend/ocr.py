"""
TOLLNET — Smart Toll Collection System
OCR Module: ocr.py

Responsibilities:
  - Preprocess an OpenCV image for best OCR accuracy
  - Run Tesseract OCR to extract text
  - Clean and return only the Vehicle ID string
"""

import re
import cv2
import numpy as np
import pytesseract

# ─── Tesseract Path (Windows users only) ────────────────────────
# If you are on Windows, uncomment and set the correct path below:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
#
# On Linux/macOS this line is usually not needed if Tesseract
# is installed via apt / brew and is on your PATH.


# ─── Main Function ──────────────────────────────────────────────
def extract_vehicle_id(img_cv):
    """
    Given an OpenCV BGR image, preprocess it and run Tesseract OCR.
    Returns a cleaned Vehicle ID string, or None if nothing useful found.

    Parameters:
        img_cv (numpy.ndarray): Image in BGR format (from cv2.imdecode)

    Returns:
        str | None: Uppercase alphanumeric Vehicle ID, e.g. "ABC123"
    """

    # ── 1. Convert to grayscale ───────────────────────────────
    # OCR works better on grayscale images
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

    # ── 2. Resize if too small ────────────────────────────────
    # Tesseract accuracy improves when the image is at least ~300 DPI.
    # We scale up small images to give OCR more pixel data.
    h, w = gray.shape
    if w < 800:
        scale = 800 / w
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # ── 3. Denoise ────────────────────────────────────────────
    # Remove salt-and-pepper noise while keeping edges sharp
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    # ── 4. Adaptive Thresholding ──────────────────────────────
    # Works well for uneven lighting (common in real-world captures)
    thresh = cv2.adaptiveThreshold(
        denoised,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,
        C=10
    )

    # ── 5. Morphological cleanup ──────────────────────────────
    # Close small gaps in characters so OCR reads them as whole letters
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # ── 6. Run Tesseract ──────────────────────────────────────
    # PSM 6  = assume a single uniform block of text
    # PSM 8  = treat the image as a single word (good for short IDs)
    # PSM 11 = sparse text, find as much as possible
    #
    # We try PSM 6 first (good for multi-character IDs on a label/card),
    # then fall back to PSM 8 if nothing alphanumeric is found.
    #
    # oem 3 = default OCR Engine Mode (LSTM + Legacy)

    config_block = "--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    config_word  = "--oem 3 --psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    raw_block = pytesseract.image_to_string(cleaned, config=config_block)
    vehicle_id = _clean_ocr_output(raw_block)

    if not vehicle_id:
        # Fall back to single-word mode
        raw_word = pytesseract.image_to_string(cleaned, config=config_word)
        vehicle_id = _clean_ocr_output(raw_word)

    # ── 7. Validate format ────────────────────────────────────
    # A valid Vehicle ID must have at least 3 characters (letters + digits)
    if vehicle_id and len(vehicle_id) >= 3:
        return vehicle_id.upper()

    return None  # Nothing useful found


# ─── Helper: Clean OCR Output ───────────────────────────────────
def _clean_ocr_output(raw_text):
    """
    Remove all non-alphanumeric characters from the OCR result,
    strip whitespace, and return the first meaningful token.

    Example:  " AB C-12 3\n " → "ABC123"
    """
    if not raw_text:
        return None

    # Remove everything except letters and digits
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_text)

    return cleaned.strip().upper() if cleaned.strip() else None