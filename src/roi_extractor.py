"""
ROI Extractor - ArUco Marker-based Region of Interest Extraction
Extracts meter display region using ArUco markers only (no fallback)

Pinned to OpenCV 4.5.x Legacy ArUco API for ARMv6 compatibility.
"""

import cv2
import numpy as np
import logging
import config

# Resolve ArUco module once at import time
_aruco = getattr(cv2, 'aruco', None)
if _aruco is None:
    try:
        import cv2.aruco as _aruco
    except ImportError:
        _aruco = None

if _aruco is None:
    logging.critical("ArUco module not found. OpenCV-contrib is not installed correctly.")


def _preprocess_for_aruco(gray):
    """CLAHE + unsharp mask for better marker detection."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=2.0)
    sharpened = cv2.addWeighted(enhanced, 1.6, blurred, -0.6, 0)
    return sharpened


def extract_roi(image, cached_pts=None):
    """Extract ROI using ArUco markers or cached coordinates."""
    if image is None or image.size == 0:
        logging.error("Invalid input image for ROI extraction")
        return None, None, False

    if _aruco is None:
        logging.error("ArUco module unavailable")
        return None, None, False

    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray_enhanced = _preprocess_for_aruco(gray)

        corners, ids = None, None
        aruco_dict = _aruco.Dictionary_get(_aruco.DICT_4X4_50)

        detection_images = [gray_enhanced, gray_enhanced, gray, gray, gray]
        profiles = [
            (3, 23, 10, 0.03, 7,   0.05),
            (3, 53, 10, 0.02, 7,   0.05),
            (3, 23, 10, 0.03, 7,   0.05),
            (5, 53,  4, 0.02, 10,  0.08),
            (3, 23, 10, 0.01, 5,   0.10),
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
                pass

            c, i, _ = _aruco.detectMarkers(det_image, aruco_dict, parameters=parameters)

            if i is not None and len(i) >= 4:
                found_ids = set(i.flatten())
                if all(req_id in found_ids for req_id in [0, 1, 2, 3]):
                    corners, ids = c, i
                    break

        # Cleanup
        del gray
        del gray_enhanced

        is_cached = False
        pts_source = None

        if ids is not None and len(ids) >= 4:
            # Use inner corners FACING the meter
            # IDs: 1=TL, 3=TR, 0=BR, 2=BL
            INNER_CORNER_IDX = {1: 2, 3: 3, 0: 0, 2: 1}
            found = {}
            for corner_arr, mid in zip(corners, ids.flatten()):
                mid = int(mid)
                if mid in INNER_CORNER_IDX:
                    found[mid] = corner_arr[0][INNER_CORNER_IDX[mid]].astype(float).tolist()

            if len(found) == 4:
                # pts_source order: [TL, TR, BR, BL]
                pts_source = np.float32([found[1], found[3], found[0], found[2]])
            else:
                ids = None # Force cache fallback

        if ids is None or pts_source is None:
            if cached_pts is not None:
                logging.info("Falling back to cached ROI.")
                pts_source = cached_pts
                is_cached = True
            else:
                return None, None, False

        # Perspective Warp
        w_top = np.linalg.norm(pts_source[1] - pts_source[0])
        w_bot = np.linalg.norm(pts_source[2] - pts_source[3])
        roi_w = int((w_top + w_bot) / 2)

        h_right = np.linalg.norm(pts_source[2] - pts_source[1])
        h_left  = np.linalg.norm(pts_source[3] - pts_source[0])
        roi_h = int((h_right + h_left) / 2)

        pts_dst = np.float32([
            [0, 0], [roi_w, 0], [roi_w, roi_h], [0, roi_h]
        ])

        # Apply Padding from config
        pad = config.ROI_PADDING
        pt_top, pt_bot = pad.get("top", 0), pad.get("bottom", 0)
        pt_left, pt_right = pad.get("left", 0), pad.get("right", 0)

        # Non-uniform expand/shrink
        p_t = int(roi_h * (pt_top / 100.0))
        p_b = int(roi_h * (pt_bot / 100.0))
        p_l = int(roi_w * (pt_left / 100.0))
        p_r = int(roi_w * (pt_right / 100.0))

        pts_dst_padded = np.float32([
            [-p_l, -p_t], [roi_w + p_r, -p_t],
            [roi_w + p_r, roi_h + p_b], [-p_l, roi_h + p_b]
        ])

        final_w = roi_w + p_l + p_r
        final_h = roi_h + p_t + p_b

        matrix = cv2.getPerspectiveTransform(pts_source, pts_dst_padded)
        roi = cv2.warpPerspective(image, matrix, (final_w, final_h))

        # Trimming
        trim = config.POST_CROP_TRIM_PX
        t_t, t_b = trim.get("top", 0), trim.get("bottom", 0)
        t_l, t_r = trim.get("left", 0), trim.get("right", 0)

        if t_t + t_b < final_h and t_l + t_r < final_w:
            roi = roi[t_t:final_h-t_b, t_l:final_w-t_r]

        # Normalize to fixed canonical size — the RF model was trained on 540×215 px ROI.
        # ArUco warp produces variable dimensions each frame; this resize makes every
        # ROI identical in size so digit contours and HOG features match training exactly.
        roi = cv2.resize(roi, (540, 215), interpolation=cv2.INTER_LINEAR)

        return roi, pts_source, is_cached

    except Exception as e:
        logging.error(f"ROI error: {e}")
        return None, None, False
