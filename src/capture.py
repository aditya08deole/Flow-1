"""
Camera Capture Module - PiCamera/PiCamera2 with GPIO LED Control

Supports both:
  - picamera  (legacy camera stack, RPi OS Buster/Bullseye-legacy)
  - picamera2 (libcamera stack, RPi OS Bullseye/Bookworm)

Optimized for Pi Zero W: no JPEG round-trip, direct numpy capture.
"""

import time
import logging
import atexit
import numpy as np
import cv2

# Load config at module level (no lazy imports)
try:
    import config as _cfg
    _RESOLUTION = _cfg.CAMERA_RESOLUTION
    _ROTATION = _cfg.CAMERA_ROTATION
    _WARMUP_DELAY = _cfg.WARMUP_DELAY
    _FOCUS_DELAY = _cfg.FOCUS_DELAY
    _POST_CAPTURE_DELAY = _cfg.POST_CAPTURE_DELAY
    _JPEG_QUALITY = _cfg.JPEG_QUALITY
    _LED_PIN = _cfg.LED_PIN
    _SHARPNESS = _cfg.CAMERA_SHARPNESS
    _AE_LOCK_TIMEOUT = _cfg.AE_LOCK_TIMEOUT
    _AE_LOCK_POLL_INTERVAL = _cfg.AE_LOCK_POLL_INTERVAL
    _AE_WARMUP_FRAMES = _cfg.AE_WARMUP_FRAMES
except Exception:
    _RESOLUTION = (1280, 960)
    _ROTATION = 180
    _WARMUP_DELAY = 0.5
    _FOCUS_DELAY = 3.0
    _POST_CAPTURE_DELAY = 3.0
    _JPEG_QUALITY = 85
    _LED_PIN = 23
    _SHARPNESS = 8.0
    _AE_LOCK_TIMEOUT = 5.0
    _AE_LOCK_POLL_INTERVAL = 0.1
    _AE_WARMUP_FRAMES = 7

# Auto-detect camera library
USE_PICAMERA2 = False
try:
    from picamera2 import Picamera2
    USE_PICAMERA2 = True
    logging.info("Using picamera2 (libcamera stack)")
except ImportError:
    try:
        from picamera import PiCamera
        logging.info("Using picamera (legacy stack)")
    except ImportError:
        logging.error("No camera library found! Install picamera or picamera2.")

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False
    logging.warning("RPi.GPIO not available (not running on Raspberry Pi?)")


# GPIO state
_GPIO_INITIALIZED = False


def _init_gpio():
    """Initialize GPIO once."""
    global _GPIO_INITIALIZED
    if not HAS_GPIO or _GPIO_INITIALIZED:
        return
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(_LED_PIN, GPIO.OUT)
    GPIO.output(_LED_PIN, GPIO.LOW)
    _GPIO_INITIALIZED = True
    # Register cleanup at process exit for safety (prevents stuck LED)
    atexit.register(cleanup_gpio)


def _led_on():
    if HAS_GPIO and _GPIO_INITIALIZED:
        GPIO.output(_LED_PIN, GPIO.HIGH)


def _led_off():
    if HAS_GPIO and _GPIO_INITIALIZED:
        GPIO.output(_LED_PIN, GPIO.LOW)


def _capture_with_picamera2():
    """Capture image using picamera2 — direct numpy array, no JPEG round-trip."""
    picam2 = Picamera2()
    try:
        # Build transform for rotation
        transform = None
        if _ROTATION in [90, 180, 270]:
            try:
                from libcamera import Transform
                if _ROTATION == 180:
                    transform = Transform(hflip=True, vflip=True)
                elif _ROTATION == 90:
                    transform = Transform(hflip=False, vflip=True, transpose=True)
                elif _ROTATION == 270:
                    transform = Transform(hflip=True, vflip=False, transpose=True)
            except ImportError:
                logging.warning("libcamera.Transform not available — rotation skipped")

        # Pass transform during configuration (NOT after via set_controls)
        config_kwargs = {"main": {"size": _RESOLUTION, "format": "RGB888"}}
        if transform is not None:
            config_kwargs["transform"] = transform

        capture_config = picam2.create_still_configuration(**config_kwargs)
        picam2.configure(capture_config)

        picam2.start()

        # Set sharpness before capture (default 1.0 is too soft; 8.0 produces sharp output)
        try:
            picam2.set_controls({"Sharpness": _SHARPNESS})
        except Exception:
            pass  # Older picamera2 versions may not support this control

        # Wait for AE/AWB to converge before capturing (prevents blurry/dark frames)
        # ── Strategy: try metadata polling first; if the camera doesn't report AeLocked
        #    (common on libcamera v0.5.x in still mode), fall back to frame-discard warmup.
        #    Each capture_array() forces the ISP to run one full AE/AWB adjustment cycle.
        _ae_locked = False
        _deadline = time.time() + _AE_LOCK_TIMEOUT
        while time.time() < _deadline:
            try:
                _meta = picam2.capture_metadata()
                if _meta.get('AeLocked', False) or _meta.get('AwbConverged', False):
                    _ae_locked = True
                    break
            except Exception:
                pass
            time.sleep(_AE_LOCK_POLL_INTERVAL)

        if not _ae_locked:
            # Metadata polling timed out (normal on IMX219/libcamera v0.5.x in still mode).
            # Discard warmup frames so ISP can converge AE before the real capture.
            logging.warning("AE metadata poll did not confirm lock — running frame-discard warmup")
            for _i in range(_AE_WARMUP_FRAMES):
                try:
                    picam2.capture_array()
                except Exception:
                    pass
            logging.info(f"   -> Frame-discard warmup complete ({_AE_WARMUP_FRAMES} frames)")
        else:
            _elapsed = _AE_LOCK_TIMEOUT - max(0.0, _deadline - time.time())
            logging.info(f"   -> AE/AWB converged after {_elapsed:.1f}s")

        # Lock exposure before capture for consistent result
        try:
            picam2.set_controls({"AeEnable": False, "AwbEnable": False})
            time.sleep(0.1)  # Brief settle after locking
        except Exception:
            pass  # Some camera modules don't support lock controls — continue anyway

        image_rgb = picam2.capture_array()
        picam2.stop()

        # Convert RGB to BGR for OpenCV
        return cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    finally:
        picam2.close()


def _capture_with_picamera():
    """
    Capture image using picamera (legacy) — direct numpy array capture.

    Uses picamera's capture-to-array to avoid the JPEG encode→decode round-trip.
    This saves ~500ms and ~4MB of RAM on Pi Zero W.
    """
    camera = PiCamera()
    try:
        camera.resolution = _RESOLUTION
        camera.rotation = _ROTATION
        camera.sharpness = int(_SHARPNESS * 6.25)  # Map 0–16 range → 0–100 for legacy picamera
        camera.awb_mode = 'auto'
        camera.exposure_mode = 'auto'
        camera.iso = 0  # Auto ISO

        # Wait for auto-exposure/white balance
        time.sleep(_FOCUS_DELAY)

        # Capture directly to numpy array (BGR format via OpenCV convention)
        # picamera outputs RGB, so we capture as RGB then convert.
        image = np.empty((_RESOLUTION[1], _RESOLUTION[0], 3), dtype=np.uint8)
        camera.capture(image, format='rgb', use_video_port=False)
        camera.close()
        camera = None

        # Convert RGB to BGR for OpenCV compatibility
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        if image is None or image.size == 0:
            raise ValueError("Captured image is empty")

        return image
    finally:
        if camera:
            try:
                camera.close()
            except Exception:
                pass


def capture_image(max_retries=2):
    """
    Capture high-resolution image with strict timing sequence.

    Sequence: LED ON → warmup → capture → post-delay → LED OFF

    Args:
        max_retries: Number of capture attempts (default 2)

    Returns:
        numpy.ndarray: Captured image in BGR format, or None if failed
    """
    _init_gpio()

    for attempt in range(max_retries):
        try:
            logging.info(f"   -> [Step 1.1] LED ON (Pin {_LED_PIN})")
            _led_on()
            time.sleep(_WARMUP_DELAY)

            logging.info(f"   -> [Step 1.2] Initializing Camera (Attempt {attempt + 1})")
            if USE_PICAMERA2:
                image = _capture_with_picamera2()
            else:
                image = _capture_with_picamera()

            if image is None or image.size == 0:
                raise ValueError("Captured image is None or empty")

            logging.info(f"   -> [Step 1.3] Capture successful ({image.shape[1]}x{image.shape[0]} px)")
            time.sleep(_POST_CAPTURE_DELAY)
            
            logging.info("   -> [Step 1.4] LED OFF")
            _led_off()

            return image

        except Exception as e:
            _led_off()  # Always turn off LED on failure
            if attempt < max_retries - 1:
                logging.warning(f"Capture attempt {attempt + 1}/{max_retries} failed: {e}, retrying...")
                time.sleep(2)
            else:
                logging.error(f"Capture failed after {max_retries} attempts: {e}")

    return None


def cleanup_gpio():
    """Clean up GPIO resources safely."""
    global _GPIO_INITIALIZED
    if not HAS_GPIO:
        return
    try:
        # Force LED off before cleanup
        GPIO.output(_LED_PIN, GPIO.LOW)
        GPIO.cleanup()
        _GPIO_INITIALIZED = False
        logging.info("GPIO cleaned up")
    except Exception:
        pass
