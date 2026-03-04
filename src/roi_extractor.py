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

        # Attempt up to 3 detection profiles
        corners, ids = None, None
        
        for attempt in range(1, 4):
            parameters = _aruco.DetectorParameters_create()
            
            # Profile 1: Default
            if attempt == 2:
                # Profile 2: Relaxed adaptive thresholding
                parameters.adaptiveThreshWinSizeMin = 3
                parameters.adaptiveThreshWinSizeMax = 23
                parameters.adaptiveThreshWinSizeStep = 10
                parameters.minMarkerPerimeterRate = 0.03
            elif attempt == 3:
                # Profile 3: Further relaxed thresholds
                parameters.adaptiveThreshConstant = 7
                parameters.polygonalApproxAccuracyRate = 0.05
                parameters.adaptiveThreshWinSizeMin = 3
                parameters.adaptiveThreshWinSizeMax = 23
                parameters.adaptiveThreshWinSizeStep = 10
                parameters.minMarkerPerimeterRate = 0.03

            aruco_dict = _aruco.Dictionary_get(_aruco.DICT_4X4_50)
            c, i, _ = _aruco.detectMarkers(gray, aruco_dict, parameters=parameters)
            
            # Check if we found all 4 required markers
            if i is not None and len(i) >= 4:
                found_ids = set(i.flatten())
                if all(req_id in found_ids for req_id in [0, 1, 2, 3]):
                    corners, ids = c, i
                    logging.debug(f"ArUco detection succeeded on attempt {attempt}")
                    break
                    
        # Free grayscale immediately
        del gray

        # If after 3 attempts, we still don't have enough markers, check cache
        if ids is None or len(ids) < 4:
            detected = 0 if ids is None else len(ids)
            logging.warning(f"ArUco detection: found {detected}/4 markers after 3 attempts")
            
            if cached_pts is not None:
                logging.info("Falling back to cached ROI coordinates.")
                pts_source = cached_pts
                is_cached = True
            else:
                return None, None, False
        else:
            # Build marker center map
            found = {}
            for corner, mid in zip(corners, ids.flatten()):
                c = corner[0]
                found[mid] = [int(c[:, 0].mean()), int(c[:, 1].mean())]

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
                # Map: TL=1, TR=3, BR=0, BL=2
                pts_source = np.float32([
                    found[1],  # Top-left
                    found[3],  # Top-right
                    found[0],  # Bottom-right
                    found[2],  # Bottom-left
                ])
                is_cached = False

        # Calculate ROI dimensions
        x_coords = pts_source[:, 0]
        y_coords = pts_source[:, 1]
        roi_w = int(x_coords.max() - x_coords.min())
        roi_h = int(y_coords.max() - y_coords.min())

        # Padding
        pad_frac = config.ROI_PADDING_PERCENT / 100.0
        pad_w = int(roi_w * pad_frac)
        pad_h = int(roi_h * pad_frac)

        # Destination points with padding
        pts_dst = np.float32([
            [-pad_w, -pad_h],
            [roi_w + pad_w, -pad_h],
            [roi_w + pad_w, roi_h + pad_h],
            [-pad_w, roi_h + pad_h],
        ])

        # Perspective transform
        out_w = roi_w + 2 * pad_w
        out_h = roi_h + 2 * pad_h
        matrix = cv2.getPerspectiveTransform(pts_source, pts_dst)
        roi = cv2.warpPerspective(image, matrix, (out_w, out_h))

        logging.debug(f"ROI extracted: {out_w}x{out_h} px from {'cached' if is_cached else 'fresh'} markers")
        return roi, pts_source, is_cached

    except Exception as e:
        logging.error(f"ROI extraction failed: {e}")
        return None, None, False
