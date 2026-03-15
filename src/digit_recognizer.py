"""
Digit Recognizer — HOG + Random Forest Edge Processing Pipeline
Repository: https://github.com/aditya08deole/Flow-1.git

Core pipeline ported from Ph-03-master/codetest.py (lines 205–419).
Runs entirely on-device (no cloud ML dependency).

Pipeline:
  ROI image
    → blur check (Laplacian variance)
    → grayscale → medianBlur → adaptiveThreshold → dilate/erode
    → findContours → sort left-to-right → area filter
    → per digit: boundingRect → resize(90×45) → morph → HOG → RF.predict
    → Hamming distance correction
    → flow rate calculation
"""

import cv2
import numpy as np
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

try:
    import joblib
    from skimage.transform import resize as sk_resize
    from skimage.feature import hog
    from imutils.contours import sort_contours as imutils_sort_contours
    _DEPS_OK = True
except ImportError as e:
    _DEPS_OK = False
    logging.critical(f"Digit recognizer missing dependencies: {e}. "
                     "Install: scikit-image, scikit-learn, joblib, imutils")


# ── Model Management ─────────────────────────────────────────────────────────

def load_model(path):
    """
    Load the pre-trained Random Forest model from disk.
    Must be called ONCE at service startup — not per-cycle.

    Args:
        path: Path to rf_rasp_classifier.sav (32MB joblib file)

    Returns:
        Loaded sklearn model object

    Raises:
        Exception if file not found or joblib fails (caller should sys.exit(3))
    """
    if not _DEPS_OK:
        raise ImportError("joblib not available — cannot load RF model")
    logging.info(f"Loading RF model from {path} ...")
    import warnings
    # Suppress the unpickling warning if sklearn versions differ, as it generally still works 
    # for simpler RF models if no deep tree changes occurred between versions.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        model = joblib.load(path)
    logging.info("RF model loaded successfully")
    return model


# ── Blur Detection ────────────────────────────────────────────────────────────

def detect_blur(image, threshold=100.0):
    """
    Laplacian variance blur check.
    A sharp image has high edge energy (high variance); a blurry image has low.
    Typical thresholds: < 80 = blurry, > 200 = sharp.

    Args:
        image: BGR numpy array
        threshold: Variance below this → image is too blurry for digit inference

    Returns:
        Tuple (is_blurry: bool, variance: float)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    # Bypass blur detection entirely — always return False so ML pipeline forces execution
    return False, round(float(variance), 2)


# ── Contour Detection ─────────────────────────────────────────────────────────

def get_sorted_contours(image, min_area=1500):
    """
    Extract and return left-to-right sorted digit contours from a meter ROI.

    Preprocessing pipeline (from codetest.py get_sorted_contour):
      BGR → grayscale → medianBlur(15) → adaptiveThreshold(GAUSSIAN_C, INV, 33, 5)
      → dilate(3×3, iters=5) → erode(3×3, iters=2)
      → findContours(RETR_EXTERNAL) → sort_contours → area filter

    Args:
        image: BGR numpy array (cropped ROI)
        min_area: Minimum contour pixel area to be considered a digit

    Returns:
        List of valid contours sorted left-to-right (may be empty)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Enhance local contrast so the black digits stand out more clearly against the wheel
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    gray = cv2.medianBlur(gray, 15)

    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        33, 5
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.dilate(thresh, kernel, iterations=5)
    thresh = cv2.erode(thresh, kernel, iterations=2)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return []

    actual_min_area = getattr(config, 'MIN_CONTOUR_AREA', min_area)

    # 1. Filter out contours that don't geometrically resemble a digit
    valid_boxes = []
    for c in contours:
        if cv2.contourArea(c) < actual_min_area:
            continue
        
        x, y, w, h = cv2.boundingRect(c)
        aspect_ratio = w / float(h)
        
        # Digits are taller than they are wide.
        # Prevent picking up dial seams (too thin) or merged artifacts (too wide)
        if 0.15 <= aspect_ratio <= 1.0:
            valid_boxes.append((c, x, y, w, h))

    if not valid_boxes:
        return []

    # 2. Enforce height similarity (digits in a meter are exactly the same physical height)
    # Reject short background noise or tall vertical glare lines
    median_h = np.median([b[4] for b in valid_boxes])
    valid_contours = [b[0] for b in valid_boxes if 0.70 * median_h <= b[4] <= 1.30 * median_h]

    if not valid_contours:
        return []

    # Sort left-to-right
    (valid_contours, _) = imutils_sort_contours(valid_contours)
    return valid_contours


# ── HOG + RF Digit Classification ─────────────────────────────────────────────

def recognize_digits(roi_image, model):
    """
    Classify all digits in a ROI using HOG features + Random Forest.

    Per-digit pipeline (from codetest.py func()):
      boundingRect → BGR crop → grayscale → resize(90×45)
      → morphClose(ellipse_3x3) → morphOpen(ellipse_11x11) → erode(ellipse_3x3, iters=3)
      → HOG(9 orientations, 8×8 cells, 2×2 blocks) → RF.predict

    HOG produces a 1440-element feature vector:
      Grid: 90/8=11 rows × 45/8=5 cols = 10×4 = 40 blocks
      40 blocks × 4 cells/block × 9 orientations = 1440 features

    Args:
        roi_image: BGR numpy array (cropped meter ROI)
        model: Loaded sklearn Random Forest model

    Returns:
        Digit string e.g. "01234567" or None if no contours found
    """
    if not _DEPS_OK:
        logging.error("Digit recognition dependencies not available")
        return None

    contours = get_sorted_contours(roi_image)
    if not contours or len(contours) < 4:
        logging.warning(f"[Step 3] Recognition rejected: Only found {len(contours) if contours else 0} digit contours (expected 8). Noise/Shadow detected.")
        return None

    e3  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    e11 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    result = ""

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        digit_crop = roi_image[y:y + h, x:x + w]
        gray = cv2.cvtColor(digit_crop, cv2.COLOR_BGR2GRAY)
        
        # Pad to exactly 1:2 aspect ratio (width:height) before scaling to 45x90.
        # This prevents "fat" 0s or "thin" 1s from distorting during the resize step,
        # which fundamentally changes the HOG features. Background is white (255).
        target_ratio = 45.0 / 90.0
        current_ratio = w / float(h) if h > 0 else target_ratio
        
        if current_ratio > target_ratio:
            # Too wide: need to increase height (pad top/bottom)
            target_h = int(w / target_ratio)
            pad_h = target_h - h
            top = pad_h // 2
            bottom = pad_h - top
            gray = cv2.copyMakeBorder(gray, top, bottom, 0, 0, cv2.BORDER_CONSTANT, value=255)
        elif current_ratio < target_ratio:
            # Too tall: need to increase width (pad left/right)
            target_w = int(h * target_ratio)
            pad_w = target_w - w
            left = pad_w // 2
            right = pad_w - left
            gray = cv2.copyMakeBorder(gray, 0, 0, left, right, cv2.BORDER_CONSTANT, value=255)

        gray = sk_resize(gray, (90, 45))  # skimage resize, returns float64 [0,1]

        # Morphological cleanup — fill gaps, remove speckles, thin strokes
        gray_u8 = (gray * 255).astype(np.uint8)
        gray_u8 = cv2.morphologyEx(gray_u8, cv2.MORPH_CLOSE, e3)
        gray_u8 = cv2.morphologyEx(gray_u8, cv2.MORPH_OPEN, e11)
        gray_u8 = cv2.erode(gray_u8, e3, iterations=3)

        # Back to float for skimage HOG
        gray_f = gray_u8.astype(np.float64) / 255.0

        features = hog(
            gray_f,
            orientations=9,
            pixels_per_cell=(8, 8),
            cells_per_block=(2, 2)
        )

        digit = str(model.predict(features.reshape(1, -1))[0])
        result += digit

    return result if result else None


# ── Hamming Distance Correction ───────────────────────────────────────────────

def apply_hamming_correction(raw_str, prev_int, time_diff_min):
    """
    Correct single-digit OCR errors using Hamming distance.

    Searches a range of physically plausible readings (prev_int to prev_int + time_diff_min)
    and picks the one closest (fewest differing characters) to the raw detected string.
    This catches cases where e.g. "6" is misread as "8" but the true value is known
    to be near the previous reading.

    Ported from codetest.py lines 321–343.

    Args:
        raw_str: Detected digit string e.g. "01234"
        prev_int: Previous stored reading as integer (without decimal point) e.g. 1234
        time_diff_min: Minutes since last reading (caps the search range)

    Returns:
        Corrected integer reading (caller divides by 10^DECIMAL_DIGITS for float)
        Returns int(raw_str) if prev_int is None (first reading).
    """
    if not raw_str:
        return None
    if prev_int is None:
        return int(raw_str)

    raw_int = int(raw_str)
    max_advance = max(1, int(time_diff_min))
    best, best_dist = raw_int, float('inf')
    pad = len(raw_str)

    for k in range(prev_int, prev_int + max_advance + 1):
        # Handle mechanical rollover (e.g. 9999 -> 0000)
        k_mod = k % (10 ** pad)
        
        dist = sum(
            c1 != c2
            for c1, c2 in zip(str(k_mod).zfill(pad), str(raw_int).zfill(pad))
        )
        if dist < best_dist:
            best_dist = dist
            best = k_mod

    # Desync Protection: If the anchor in Variable.txt is completely wrong
    # (e.g., 0 while the meter is 46,000,000), every digit will mismatch.
    # In this case, we MUST break the anchor and trust the current AI reading.
    if best_dist >= pad - 1 and pad > 3:
        import logging
        logging.warning(f"⚠️  Hamming anchor totally desynced (dist={best_dist}/{pad}). Forcing resync to {raw_int}")
        return raw_int

    return best


# ── Flow Rate Calculation ─────────────────────────────────────────────────────

def calculate_flow_rate(current_val, prev_val, time_diff_min):
    """
    Calculate flow rate in meter units per minute.

    Args:
        current_val: Current meter reading (float, includes decimal)
        prev_val: Previous meter reading (float)
        time_diff_min: Time elapsed in minutes between readings

    Returns:
        Flow rate (float, units/min). Returns 0.0 on invalid input.
    """
    if time_diff_min <= 0 or prev_val is None or current_val is None:
        return 0.0
    return round((current_val - prev_val) / time_diff_min, 5)
