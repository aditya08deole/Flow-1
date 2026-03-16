"""
RetroFit Image Capture Service v2.1 - Configuration
Cloud Processing Architecture (No Edge ML)
Repository: https://github.com/aditya08deole/Flow-1.git

Device-specific credentials loaded from credentials_store.csv
Device identity from config_WM.py (device-specific, not in git)

NO HARDCODED CREDENTIALS IN THIS FILE!
"""

# ============================================================
# CAMERA SETTINGS
# ============================================================

# GPIO Pin for LED/Relay Control
LED_PIN = 23

# Camera Resolution (optimized for Pi Zero W memory constraints)
# 1280x960 = native 4:3 binned mode, saves ~40% RAM vs 1640x1232
CAMERA_RESOLUTION = (1280, 960)  # Width x Height in pixels

# Camera Rotation (0, 90, 180, or 270 degrees)
CAMERA_ROTATION = 180  # Adjust based on physical camera orientation

# Camera Timing Sequence (seconds)
# Sequence: LED ON → WARMUP_DELAY → Camera starts → AE warmup → Capture → POST_CAPTURE_DELAY → LED OFF
WARMUP_DELAY = 1.0        # 1s delay after LED ON before camera starts — LED reaches full brightness,
                          # scene is fully lit before ISP meters exposure for AE convergence.
FOCUS_DELAY = 5.0         # Legacy picamera AE/AWB warmup — 5s in still mode for indoor lighting convergence.
POST_CAPTURE_DELAY = 1.0  # 1s LED stays ON after capture — ensures full sensor read-out completes
                          # before light is cut; prevents partial-frame exposure on next attempt.

# Image Quality
JPEG_QUALITY = 85  # 1-100, 85 gives ~40% smaller files vs 95, no visual diff for meter reading

# Camera Sharpness
CAMERA_SHARPNESS = 4.0    # picamera2: 1.0=default, 8.0=sharp, 16.0=max — legacy picamera: mapped to 0-100
                          # Reduced from 8.0: over-sharpening adds edge halos that
                          # hurt ArUco detection on borderline-sharp images.

# AE/AWB Convergence Wait (picamera2 only)
AE_LOCK_TIMEOUT = 2.0        # Fast-fail: IMX219/libcamera v0.5.x rarely sets AeLocked in preview mode
AE_LOCK_POLL_INTERVAL = 0.1  # How often to poll AE lock metadata (seconds)
AE_PREVIEW_DURATION = 5.0    # Seconds to stream in preview mode for AE/AWB to converge (fallback).
                              # ISP streams at ~30fps during this wait — convergence is reliable.
                              # 5.0s is more conservative for Pi Zero W in dim indoor lighting.


# ============================================================
# ARUCO MARKER SETTINGS
# ============================================================

# ArUco Dictionary
ARUCO_DICT = "DICT_4X4_50"

# Required Marker IDs (for ROI extraction)
ARUCO_MARKER_IDS = [0, 1, 2, 3]

# ROI Padding (percentage around detected markers)
# Positive values expand the box, Negative values shrink the box
# For example, to cut off markers on the right but keep the left intact:
ROI_PADDING = {
    "top": 0,     # Shrink top 
    "bottom": 0,  # Shrink bottom 
    "left": 0,    
    "right": 0    
}

# Post-Crop Exact Pixel Trimming
# This runs AFTER the ROI padding crop. It cuts an exact number of pixels off the final image edges.
# Use this for fine-tuning the borders regardless of how far the markers are placed.
POST_CROP_TRIM_PX = {
    "top": 0,     # Pixels to cut from the top
    "bottom": 0,  # Pixels to cut from the bottom
    "left": 4,    # Pixels to cut from the left (e.g., to shave off a visible marker line)
    "right": 4    # Pixels to cut from the right
}



# ============================================================
# DIGIT RECOGNITION SETTINGS
# ============================================================

# Blur gate — Laplacian variance below this threshold means the ROI is too blurry
# for reliable digit inference. Typical sharp images score > 200; blurry < 80.
BLUR_THRESHOLD = 10.0

# HOG feature extraction — must match what rf_rasp_classifier.sav was trained on
DIGIT_RESIZE_H = 90           # Resize height per digit crop (pixels)
DIGIT_RESIZE_W = 45           # Resize width per digit crop (pixels)
MIN_CONTOUR_AREA = 300        # Minimum contour pixel area to be classified as a digit

# Random Forest model (loaded once at service start, not per-cycle)
MODEL_PATH = "rf_rasp_classifier.sav"

# Meter reading interpretation
DECIMAL_DIGITS = 1            # Rightmost N digits are decimal places (e.g. 01234 → 123.4)
METER_READING_MAX_POWER = 100000000     # 99,999,999.99 for 8-digit meter
MAX_PLAUSIBLE_FLOW_DELTA = 500.0        # Max units (e.g. Liters) possible in 5 minutes
MAX_PLAUSIBLE_FALL_DELTA = 200.0        # Max units a reading can "drop" (OCR noise) before blocking
MAX_RECOGNITION_RETRIES = 3             # Number of times to retry if a spike is detected
STORED_READINGS_MAX = 5                 # Rolling window size for flow rate calculation


# ============================================================
# UPLOAD SETTINGS
# ============================================================

# Upload Retry Configuration
UPLOAD_MAX_RETRIES = 3
UPLOAD_RETRY_DELAYS = [2, 5, 10]  # Exponential backoff (seconds)
UPLOAD_TIMEOUT = 120  # Maximum time for single upload attempt (seconds)

# rclone Configuration
RCLONE_REMOTE_NAME = "gdrive"  # Must match 'rclone config' remote name
RCLONE_BANDWIDTH_LIMIT = "1M"  # Upload bandwidth cap — prevents WiFi saturation on Pi Zero W


# ============================================================
# THINGSPEAK STATUS REPORTING
# ============================================================

# ThingSpeak API URL
THINGSPEAK_UPDATE_URL = "https://api.thingspeak.com/update"

# Status codes sent to ThingSpeak field1 after each cycle:
#   1 = ArUco ROI detected, cropped image uploaded to GDrive successfully
#   0 = ArUco NOT detected, full image uploaded to GDrive successfully
#   2 = Error (capture failed, upload failed, or any other error)
THINGSPEAK_STATUS_ARUCO_SUCCESS = 1
THINGSPEAK_STATUS_NO_ARUCO = 0
THINGSPEAK_STATUS_ERROR = 2
THINGSPEAK_STATUS_RECOGNITION_ERROR = 3


# ============================================================
# SERVICE SETTINGS
# ============================================================

# Capture Interval
CAPTURE_INTERVAL_MINUTES = 5  # How often to capture images (minutes)

# Logging
ERROR_LOG = "error.log"
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR


# ============================================================
# CREDENTIAL MANAGEMENT
# ============================================================

# Credential Store (CSV file with device credentials)
CREDENTIAL_STORE_PATH = "credentials_store.csv"

# Device Identity File (created manually on each device, NOT in git)
CONFIG_WM_PATH = "config_WM.py"


# ============================================================
# CONFIG VALIDATION
# ============================================================

def validate_config():
    """
    Validate configuration parameters.
    Raises ValueError if any parameter is invalid.
    """
    errors = []
    
    # Camera settings
    if not isinstance(CAMERA_RESOLUTION, tuple) or len(CAMERA_RESOLUTION) != 2:
        errors.append("CAMERA_RESOLUTION must be a tuple of (width, height)")
    elif CAMERA_RESOLUTION[0] <= 0 or CAMERA_RESOLUTION[1] <= 0:
        errors.append("CAMERA_RESOLUTION values must be positive")
    
    if CAMERA_ROTATION not in [0, 90, 180, 270]:
        errors.append("CAMERA_ROTATION must be 0, 90, 180, or 270 degrees")
    
    if WARMUP_DELAY < 0 or FOCUS_DELAY < 0 or POST_CAPTURE_DELAY < 0:
        errors.append("Camera timing delays must be non-negative")
    
    if not (1 <= JPEG_QUALITY <= 100):
        errors.append("JPEG_QUALITY must be between 1 and 100")
    
    # Upload settings
    if UPLOAD_MAX_RETRIES < 1:
        errors.append("UPLOAD_MAX_RETRIES must be at least 1")
    
    if len(UPLOAD_RETRY_DELAYS) != UPLOAD_MAX_RETRIES:
        errors.append(f"UPLOAD_RETRY_DELAYS must have {UPLOAD_MAX_RETRIES} elements (one per retry)")
    
    if any(delay < 0 for delay in UPLOAD_RETRY_DELAYS):
        errors.append("UPLOAD_RETRY_DELAYS values must be non-negative")
    
    if UPLOAD_TIMEOUT < 10:
        errors.append("UPLOAD_TIMEOUT must be at least 10 seconds")
    
    # Service settings
    if CAPTURE_INTERVAL_MINUTES < 1:
        errors.append("CAPTURE_INTERVAL_MINUTES must be at least 1")
    
    if LOG_LEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
        errors.append("LOG_LEVEL must be one of: DEBUG, INFO, WARNING, ERROR")
    
    # ArUco Config Validation
    if not isinstance(ARUCO_MARKER_IDS, list) or len(ARUCO_MARKER_IDS) < 3:
        errors.append("ARUCO_MARKER_IDS must be a list with at least 3 marker IDs")
    
    expected_keys = {"top", "bottom", "left", "right"}
    if not isinstance(ROI_PADDING, dict) or not expected_keys.issubset(ROI_PADDING.keys()):
        errors.append("ROI_PADDING must be a dictionary containing 'top', 'bottom', 'left', 'right'")
    else:
        for key in expected_keys:
            val = ROI_PADDING[key]
            # Allow negative padding (up to -50% to prevent full collapse) and positive padding
            if not (-50 <= val <= 100):
                errors.append(f"ROI_PADDING '{key}' must be between -50 and 100")
                
    if not isinstance(POST_CROP_TRIM_PX, dict) or not expected_keys.issubset(POST_CROP_TRIM_PX.keys()):
        errors.append("POST_CROP_TRIM_PX must be a dictionary containing 'top', 'bottom', 'left', 'right'")
    else:
        for key in expected_keys:
            val = POST_CROP_TRIM_PX[key]
            if not isinstance(val, int) or val < 0:
                errors.append(f"POST_CROP_TRIM_PX '{key}' must be zero or a positive integer")
    
    # Raise error if any validation failed
    if errors:
        raise ValueError("Configuration validation failed:\n  - " + "\n  - ".join(errors))


# ============================================================
# REMOVED SETTINGS (No longer needed in v2.0)
# ============================================================
# - MODEL_PATH (no ML model)
# - CONFIDENCE_THRESHOLD (no classification)
# - ROI_WIDTH, ROI_HEIGHT, ROI_ZOOM (dynamic from ArUco)
# - FALLBACK_ROI_POINTS (no fallback, ArUco only)
# - MAX_FLOW_RATE, MIN_TIME_DIFF (no flow validation)
# - STATE_FILE (no meter state tracking)
# - MAX_RETRIES (replaced with UPLOAD_MAX_RETRIES)
# - CAPTURE_INTERVAL (replaced with CAPTURE_INTERVAL_MINUTES)
