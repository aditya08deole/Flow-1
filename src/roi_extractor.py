"""
ROI Extractor - ArUco Marker-based Region of Interest Extraction
Extracts meter display region using ArUco markers only (no fallback)

Pinned to OpenCV 4.5.x Legacy ArUco API for ARMv6 compatibility.
"""

import cv2
import numpy as np
import logging
import config

# Resolve ArUco module once at import time (not every call)
_aruco = getattr(cv2, 'aruco', None)
if _aruco is None:
    try:
        import cv2.aruco as _aruco
    except ImportError:
        _aruco = None

if _aruco is None:
    logging.critical("ArUco module not found. OpenCV-contrib is not installed correctly.")


def _preprocess_for_aruco(gray):
    """
    Apply CLAHE + unsharp mask to a grayscale image to enhance ArUco marker edges on blurry images.
    Returns the enhanced grayscale image. Used only for detection — the ROI crop uses the original image.
    """
    # CLAHE enhances local contrast so marker borders become detectable even when image is dim
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Unsharp mask: emphasise edges by subtracting a blurred version
    blurred = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=2.0)
    sharpened = cv2.addWeighted(enhanced, 1.6, blurred, -0.6, 0)

    return sharpened


def extract_roi(image, cached_pts=None):
    """
    Extract ROI from image using ArUco markers or cached coordinates.

    Looks for 4 ArUco markers (IDs 0-3) defining the meter display corners.
    If all 4 are found, extracts and perspective-corrects the region.
    If markers are not found, falls back to `cached_pts` if provided.

    Args:
        image: Input image (numpy array in BGR format)
        cached_pts: Optional np.float32 array containing cached (TL, TR, BR, BL) source points.

    Returns:
        tuple (roi: numpy.ndarray, source_pts: numpy.ndarray, is_cached: bool)
        Returns (None, None, False) if markers not found and no valid cache provided.

    Marker Layout:
        ID 1 (TL) -------- ID 3 (TR)
           |                  |
           |   METER DISPLAY  |
           |                  |
        ID 2 (BL) -------- ID 0 (BR)
    """
    if image is None or image.size == 0:
        logging.error("Invalid input image for ROI extraction")
        return None, None, False

    if _aruco is None:
        logging.error("ArUco module unavailable — cannot extract ROI")
        return None, None, False

    try:
        # Convert to grayscale for marker detection
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray_enhanced = _preprocess_for_aruco(gray)

        # 5 detection profiles: first 2 run on CLAHE-enhanced image, last 3 on raw grayscale
        # This catches markers on blurry images where raw thresholding fails
        corners, ids = None, None
        aruco_dict = _aruco.Dictionary_get(_aruco.DICT_4X4_50)

        detection_images = [gray_enhanced, gray_enhanced, gray, gray, gray]
        profiles = [
            # (adaptThreshMin, adaptThreshMax, adaptStep, minPerim, adaptConst, polyApprox)
            (3, 23, 10, 0.03, 7,   0.05),   # Profile 1: enhanced + relaxed
            (3, 53, 10, 0.02, 7,   0.05),   # Profile 2: enhanced + very relaxed window
            (3, 23, 10, 0.03, 7,   0.05),   # Profile 3: raw + relaxed
            (5, 53,  4, 0.02, 10,  0.08),   # Profile 4: raw + large adaptive windows
            (3, 23, 10, 0.01, 5,   0.10),   # Profile 5: raw + minimal size filter
        ]

        for idx, (det_image, prof) in enumerate(zip(detection_images, profiles), start=1):
            parameters = _aruco.DetectorParameters_create()
            parameters.adaptiveThreshWinSizeMin    = prof[0]
            parameters.adaptiveThreshWinSizeMax    = prof[1]
            parameters.adaptiveThreshWinSizeStep   = prof[2]
            parameters.minMarkerPerimeterRate      = prof[3]
            parameters.adaptiveThreshConstant      = prof[4]
            parameters.polygonalApproxAccuracyRate = prof[5]
            try:
                parameters.cornerRefinementMethod = _aruco.CORNER_REFINE_SUBPIX
            except AttributeError:
                pass  # Not available on all OpenCV builds

            c, i, _ = _aruco.detectMarkers(det_image, aruco_dict, parameters=parameters)

            if i is not None and len(i) >= 4:
                found_ids = set(i.flatten())
                if all(req_id in found_ids for req_id in [0, 1, 2, 3]):
                    src = 'enhanced' if idx <= 2 else 'raw'
                    logging.info(f"   -> [Step 2.2] ArUco SUCCESS (Profile {idx}, {src})")
                    corners, ids = c, i
                    break
                else:
                    logging.info(f"   -> [Step 2.1] Profile {idx}: found {len(i)} markers, missing required IDs")
            else:
                detected = len(i) if i is not None else 0
                logging.info(f"   -> [Step 2.1] Profile {idx}: found {detected}/4 markers")

        # Free grayscale copies immediately
        del gray
        del gray_enhanced

        # If after 5 attempts, we still don't have enough markers, check cache
        if ids is None or len(ids) < 4:
            detected = 0 if ids is None else len(ids)
            logging.warning(f"ArUco detection: found {detected}/4 markers after 5 profiles")
            
            if cached_pts is not None:
                logging.info("Falling back to cached ROI coordinates.")
                pts_source = cached_pts
                is_cached = True
            else:
                return None, None, False
        else:
            # Use the inner corner of each marker (the corner pointing INTO the meter area)
            # This gives a tighter, more stable crop than averaging all 4 corners to a center point.
            #   ID 1 (TL) → bottom-right corner (index 2) — faces meter
            #   ID 3 (TR) → bottom-left corner  (index 3) — faces meter
            #   ID 0 (BR) → top-left corner     (index 0) — faces meter
            #   ID 2 (BL) → top-right corner    (index 1) — faces meter
            INNER_CORNER_IDX = {1: 2, 3: 3, 0: 0, 2: 1}

            found = {}
            for corner_arr, mid in zip(corners, ids.flatten()):
                mid = int(mid)
                if mid in INNER_CORNER_IDX:
                    cidx = INNER_CORNER_IDX[mid]
                    pt = corner_arr[0][cidx]  # corner_arr shape: (1, 4, 2)
                    found[mid] = [float(pt[0]), float(pt[1])]

            # Verify all 4 required markers exist
            required = [0, 1, 2, 3]
            if not all(m in found for m in required):
                missing = [m for m in required if m not in found]
                logging.warning(f"Missing ArUco markers: {missing}")

                if cached_pts is not None:
                    logging.info("Falling back to cached ROI coordinates.")
                    pts_source = cached_pts
                    is_cached = True
                else:
                    return None, None, False
            else:
                # Map: TL=1, TR=3, BR=0, BL=2 (inner corners)
                pts_source = np.float32([
                    found[1],  # Top-left inner corner
                    found[3],  # Top-right inner corner
                    found[0],  # Bottom-right inner corner
                    found[2],  # Bottom-left inner corner
                ])
                is_cached = False

        # Map: TL=1, TR=3, BR=0, BL=2
        # pts_source is [TL, TR, BR, BL]
        
        # Calculate maximum width (Euclidean distance between TL/TR or BL/BR)
        w_top = np.sqrt(((pts_source[1][0] - pts_source[0][0]) ** 2) + ((pts_source[1][1] - pts_source[0][1]) ** 2))
        w_bot = np.sqrt(((pts_source[2][0] - pts_source[3][0]) ** 2) + ((pts_source[2][1] - pts_source[3][1]) ** 2))
        roi_w = max(int(w_top), int(w_bot))

        # Calculate maximum height (Euclidean distance between TR/BR or TL/BL)
        h_right = np.sqrt(((pts_source[2][0] - pts_source[1][0]) ** 2) + ((pts_source[2][1] - pts_source[1][1]) ** 2))
        h_left  = np.sqrt(((pts_source[3][0] - pts_source[0][0]) ** 2) + ((pts_source[3][1] - pts_source[0][1]) ** 2))
        roi_h = max(int(h_right), int(h_left))

        # Non-uniform Padding (positive expands, negative shrinks)
        pad_top = int(roi_h * (config.ROI_PADDING.get("top", 0) / 100.0))
        pad_bottom = int(roi_h * (config.ROI_PADDING.get("bottom", 0) / 100.0))
        pad_left = int(roi_w * (config.ROI_PADDING.get("left", 0) / 100.0))
        pad_right = int(roi_w * (config.ROI_PADDING.get("right", 0) / 100.0))

        # Destination points with padding applied independently
        # pts_dst maps to: [TL, TR, BR, BL]
        pts_dst = np.float32([
            [-pad_left, -pad_top],                       # Top-left
            [roi_w + pad_right, -pad_top],               # Top-right
            [roi_w + pad_right, roi_h + pad_bottom],     # Bottom-right
            [-pad_left, roi_h + pad_bottom],             # Bottom-left
        ])

        # Perspective transform (output size based on padding adjustments)
        out_w = roi_w + pad_left + pad_right
        out_h = roi_h + pad_top + pad_bottom
        matrix = cv2.getPerspectiveTransform(pts_source, pts_dst)
        roi = cv2.warpPerspective(image, matrix, (out_w, out_h))

        # --- Post-Crop Exact Pixel Trimming ---
        trim = config.POST_CROP_TRIM_PX
        t_top, t_bot, t_left, t_right = trim.get("top", 0), trim.get("bottom", 0), trim.get("left", 0), trim.get("right", 0)
        
        # Verifytrim amounts won't completely collapse the image
        if t_top + t_bot < out_h and t_left + t_right < out_w:
            y1 = t_top
            y2 = out_h - t_bot if t_bot > 0 else out_h
            x1 = t_left
            x2 = out_w - t_right if t_right > 0 else out_w
            
            roi = roi[y1:y2, x1:x2]
            out_w = roi.shape[1]
            out_h = roi.shape[0]
        else:
            logging.warning(f"POST_CROP_TRIM_PX ({t_top},{t_bot},{t_left},{t_right}) exceeds image dims ({out_w}x{out_h}). Skipping trim.")

        logging.debug(f"ROI extracted: {out_w}x{out_h} px from {'cached' if is_cached else 'fresh'} markers")
        return roi, pts_source, is_cached

    except Exception as e:
        logging.error(f"ROI extraction failed: {e}")
        return None, None, False
