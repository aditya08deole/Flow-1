"""
ThingSpeak Status Reporter - Sends cycle status codes to ThingSpeak

Status Codes (sent to field1):
  1 = Upload successful WITH ArUco ROI extraction (best case)
  0 = Upload successful but ArUco NOT detected, full image sent
  2 = Error - no image captured, capture failure, or upload error

Edge Processing Fields:
  field4 = Detected water meter value (float, e.g. 1234.5)
  field5 = Flow rate (float, units/min)

Uses ThingSpeak Update API: https://api.thingspeak.com/update
"""

import requests
import time
import logging

logger = logging.getLogger(__name__)

# ThingSpeak API endpoint
THINGSPEAK_UPDATE_URL = "https://api.thingspeak.com/update"

# Status code constants
STATUS_ARUCO_SUCCESS = 1    # ArUco detected, ROI uploaded
STATUS_NO_ARUCO = 0         # No ArUco, full image uploaded
STATUS_ERROR = 2            # Capture/upload error


class ThingSpeakReporter:
    """Report cycle status to ThingSpeak channel."""
    
    TIMEOUT = 15  # seconds
    MAX_RETRIES = 2
    RETRY_DELAY = 3  # seconds
    
    # ThingSpeak rate limit: minimum 15 seconds between updates
    MIN_UPDATE_INTERVAL = 16  # seconds (15 + 1 safety margin)
    
    def __init__(self, channel_id, write_api_key):
        """
        Initialize ThingSpeak reporter.
        
        Args:
            channel_id: ThingSpeak channel ID (e.g., "3275001")
            write_api_key: ThingSpeak write API key (e.g., "FOU6A6Z5UPM99P2W")
        """
        self.channel_id = str(channel_id).strip()
        self.write_api_key = str(write_api_key).strip()
        self._last_update_time = 0
        
        if not self.channel_id or not self.write_api_key:
            raise ValueError("ThingSpeak channel_id and write_api_key are required")
        
        logger.info(f"✓ ThingSpeak: Channel {self.channel_id} configured")
    
    def send_status(self, status_code, field2_value=None, field3_value=None,
                    meter_value=None, flow_rate=None) -> bool:
        """
        Send status code to ThingSpeak field1.

        Args:
            status_code: Status code to send (0, 1, or 2)
            field2_value: Optional value for field2 (e.g., file size in KB)
            field3_value: Optional value for field3 (e.g., cycle duration in seconds)
            meter_value: Optional float — detected water meter reading (field4)
            flow_rate: Optional float — flow rate in units/min (field5)

        Returns:
            True if update was accepted by ThingSpeak, False otherwise
        """
        # Enforce ThingSpeak rate limit (15 seconds between updates)
        # Non-blocking: skip update instead of sleeping (cycle interval is 5 min)
        elapsed = time.time() - self._last_update_time
        if elapsed < self.MIN_UPDATE_INTERVAL:
            logger.info(
                f"ThingSpeak rate limit: update skipped — only {elapsed:.1f}s elapsed "
                f"(minimum {self.MIN_UPDATE_INTERVAL}s required). Not a failure."
            )
            return False
        
        # Build payload
        payload = {
            'api_key': self.write_api_key,
            'field1': status_code
        }
        
        if field2_value is not None:
            payload['field2'] = field2_value
        if field3_value is not None:
            payload['field3'] = field3_value
        if meter_value is not None:
            payload['field4'] = round(float(meter_value), 1)
        if flow_rate is not None:
            payload['field5'] = round(float(flow_rate), 3)
        
        # Send with retry
        for attempt in range(self.MAX_RETRIES):
            try:
                response = requests.get(
                    THINGSPEAK_UPDATE_URL,
                    params=payload,
                    timeout=self.TIMEOUT
                )
                
                self._last_update_time = time.time()
                
                # ThingSpeak returns the entry ID on success, or "0" on failure
                if response.status_code == 200:
                    entry_id = response.text.strip()
                    if entry_id != "0":
                        extra = ""
                        if meter_value is not None:
                            extra += f", meter={meter_value:.1f}"
                        if flow_rate is not None:
                            extra += f", flow={flow_rate:.3f}"
                        logger.info(
                            f"ThingSpeak: status={status_code}{extra} sent "
                            f"(entry #{entry_id}, channel {self.channel_id})"
                        )
                        return True
                    else:
                        logger.warning(
                            f"⚠️  ThingSpeak rejected update (returned 0) — "
                            f"possible rate limit or invalid API key"
                        )
                else:
                    logger.warning(
                        f"⚠️  ThingSpeak HTTP {response.status_code}: {response.text[:100]}"
                    )
                
                if attempt < self.MAX_RETRIES - 1:
                    logger.info(f"   Retrying in {self.RETRY_DELAY}s...")
                    time.sleep(self.RETRY_DELAY)
            
            except requests.Timeout:
                logger.error(f"❌ ThingSpeak timeout after {self.TIMEOUT}s")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY)
            except requests.ConnectionError:
                logger.error("❌ ThingSpeak connection error (network issue)")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY)
            except Exception as e:
                logger.error(f"❌ ThingSpeak error: {type(e).__name__}: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY)
        
        logger.error(f"❌ ThingSpeak update failed after {self.MAX_RETRIES} attempts")
        return False
    
    def report_aruco_success(self, file_size_kb=None, cycle_duration=None) -> bool:
        """Report: ArUco ROI detected and uploaded successfully (status=1)."""
        return self.send_status(STATUS_ARUCO_SUCCESS, file_size_kb, cycle_duration)
    
    def report_no_aruco(self, file_size_kb=None, cycle_duration=None) -> bool:
        """Report: No ArUco detected, full image uploaded (status=0)."""
        return self.send_status(STATUS_NO_ARUCO, file_size_kb, cycle_duration)
    
    def report_error(self, cycle_duration=None) -> bool:
        """Report: Capture/upload error (status=2)."""
        return self.send_status(STATUS_ERROR, field3_value=cycle_duration)
