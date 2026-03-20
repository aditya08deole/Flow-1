"""
Digit Recognizer — HOG + Random Forest Edge Processing Pipeline
Compatible with Pi Zero W / ARMv6.
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
    
    gray = cv2.medianBlur(gray, 15)

    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        33, 5
    )

    kernel = np.ones((3, 3), np.uint8)
    thresh = cv2.dilate(thresh, kernel, iterations=5)
    thresh = cv2.erode(thresh, kernel, iterations=2)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return []

    actual_min_area = getattr(config, 'MIN_CONTOUR_AREA', 1200)

    # Legacy Logic: Simple area filter only. 
    # Do not filter by height or aspect ratio as night shadows vary these too much.
    valid_contours = [c for c in contours if cv2.contourArea(c) >= actual_min_area]

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

    # Internal Chop Rule: Only process the first 7 digits (stable range).
    # We use a proportional crop (~83% of width) to accommodate natural ROI sizes.
    w = roi_image.shape[1]
    roi_image = roi_image[:, :int(w * 0.8307)]

    contours = get_sorted_contours(roi_image)
    if not contours:
        logging.warning("[Step 3] Recognition rejected: No digit contours found.")
        return None
    
    if len(contours) < 8:
        logging.info(f"[Step 3] Found {len(contours)} digits (Meter has 8). Proceeding with partial recognition.")

    e3  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    e11 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    result = ""

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        digit_crop = roi_image[y:y + h, x:x + w]
        gray = cv2.cvtColor(digit_crop, cv2.COLOR_BGR2GRAY)
        
        # Legacy Matching: Direct resize (squish).
        # The AI model was trained on distorted/squished images in codetest.py.
        # Do not use padding as it changes the HOG features from the training set.
        gray = sk_resize(gray, (90, 45))  # skimage resize, returns float64 [0,1]

        e3  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        e11 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        
        # Morphological cleanup — bit-perfect match with Ph-03-master/codetest.py
        # Training ran morphology on Float64 [0,1] from resize()
        gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, e3)
        gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, e11)
        gray = cv2.erode(gray, e3, iterations=3)

        features = hog(
            gray,
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

    str_prev = str(prev_int)
    pad = len(str_prev)
    raw_len = len(raw_str)

    if raw_len > pad + 1:
        logging.warning(f"⚠️  Length mismatch: OCR saw {raw_len} digits but history is {pad}. Resetting.")
        return int(raw_str)

    raw_int = int(raw_str)
    max_advance = max(1, int(time_diff_min))
    best, best_dist = raw_int, float('inf')

    # Ensure length parity for comparison
    raw_str_compare = str(raw_int).zfill(pad)
    if len(raw_str_compare) > pad:
        raw_str_compare = raw_str_compare[-pad:] # Compare rightmost digits

    for k in range(prev_int, prev_int + max_advance + 1):
        # Handle mechanical rollover (e.g. 9999 -> 0000)
        k_mod = k % (10 ** pad)
        str_k = str(k_mod).zfill(pad)
        
        dist = sum(c1 != c2 for c1, c2 in zip(str_k, raw_str_compare))
        
        if dist < best_dist:
            best_dist = dist
            best = k_mod

    # Desync Protection: If the best match still differs by more than 3 digits, 
    # force a resync to the raw detection. This allows the system to escape
    # long-term drift while ignoring short-term OCR flips.
    if best_dist >= 4 and pad > 1:
        logging.warning(f"⚠️  Hamming anchor desynced (dist={best_dist}/{pad}). Escaping ratchet, reset to raw: {raw_int}")
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
    return (current_val - prev_val) / time_diff_min
