"""
rclone-based Google Drive Uploader with Upload Verification
Pure rclone implementation - no Python SDK dependencies

Optimized for Pi Zero W: subprocess isolation, zombie prevention,
lightweight verification via exit code (no folder listing).
"""

import subprocess
import shutil
import logging
import os
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class RcloneUploader:
    """
    Google Drive image uploader using rclone subprocess.

    Features:
    - Upload with automatic retry (3 attempts, exponential backoff)
    - Lightweight verification via rclone exit code (no folder listing)
    - Process isolation (failures don't crash main service)
    - Zombie-safe subprocess handling with explicit kill on timeout
    """

    MAX_RETRIES = 3
    RETRY_DELAYS = [2, 5, 10]  # seconds

    def __init__(self, remote_name='gdrive', timeout=120, bwlimit='1M'):
        self.remote_name = remote_name
        self.timeout = timeout
        self.bwlimit = bwlimit
        self.is_configured = self._validate_setup()

    def _validate_setup(self):
        """Verify rclone is installed and remote is configured."""
        try:
            rclone_path = shutil.which('rclone')
            if rclone_path is None:
                logger.error("rclone not installed. Run: curl https://rclone.org/install.sh | sudo bash")
                return False

            # Check version
            ver = subprocess.run(
                ['rclone', 'version'],
                capture_output=True, text=True, timeout=15
            )
            if ver.returncode == 0:
                logger.info(f"✓ {ver.stdout.split(chr(10))[0]}")

            # Check remote exists
            result = subprocess.run(
                ['rclone', 'listremotes'],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                logger.error(f"rclone command failed: {result.stderr}")
                return False

            remotes = [r.rstrip(':') for r in result.stdout.strip().split('\n') if r]
            if self.remote_name in remotes:
                logger.info(f"✓ rclone remote '{self.remote_name}' configured")
                return True
            else:
                logger.error(
                    f"rclone remote '{self.remote_name}' not found. "
                    f"Available: {remotes}. Run: rclone config"
                )
                return False

        except FileNotFoundError:
            logger.error("rclone binary not found")
            return False
        except Exception as e:
            logger.error(f"rclone validation error: {e}")
            return False

    def _build_remote_path(self, folder_id):
        """Build rclone remote path. Always use curly braces for folder IDs."""
        # Google Drive folder IDs are always alphanumeric+hyphens+underscores
        # Using {folder_id} syntax always works and is simpler than heuristics
        return f"{self.remote_name}:{{{folder_id}}}"

    def upload_with_verification(self, local_path: str, folder_id: str) -> bool:
        """
        Upload file to Google Drive with retry.

        Verification: We trust rclone's exit code 0 as definitive proof
        of successful upload. This avoids the expensive `rclone lsf`
        folder listing which is slow on large folders.

        Returns True if upload succeeded, False otherwise.
        """
        if not self.is_configured:
            logger.error("rclone not configured — upload skipped")
            return False

        if not folder_id or folder_id.lower() in ('nan', 'none', ''):
            logger.error("No folder_id provided — upload skipped")
            return False

        if not os.path.exists(local_path):
            logger.error(f"File not found: {local_path}")
            return False

        filename = os.path.basename(local_path)
        remote_path = self._build_remote_path(folder_id)

        for attempt in range(self.MAX_RETRIES):
            try:
                success = self._upload_single(local_path, remote_path, filename)

                if success:
                    return True

                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(
                        f"Upload failed (attempt {attempt + 1}/{self.MAX_RETRIES}), "
                        f"retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Upload failed after {self.MAX_RETRIES} attempts")

            except Exception as e:
                logger.error(f"Upload error (attempt {attempt + 1}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAYS[attempt])

        return False

    def _upload_single(self, local_path, remote_path, filename):
        """
        Single upload attempt. Returns True on rclone exit code 0.

        Uses subprocess.Popen for explicit process lifecycle control
        to prevent zombie processes on timeout.
        """
        cmd = [
            'rclone', 'copy',
            local_path, remote_path,
            '--timeout', f'{self.timeout}s',
            '--contimeout', '10s',
            '--no-traverse',
            '--stats', '0',
            '--quiet',
            '--bwlimit', self.bwlimit,
        ]

        start = datetime.now()
        logger.info(f"Uploading {filename} to Drive...")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            stdout, stderr = proc.communicate(timeout=self.timeout + 10)
            elapsed = (datetime.now() - start).total_seconds()

            if proc.returncode == 0:
                logger.info(f"✓ Upload completed in {elapsed:.1f}s")
                return True
            else:
                error_msg = self._parse_error(proc.returncode, stderr.decode(errors='replace'))
                logger.error(f"Upload failed (exit {proc.returncode}): {error_msg}")
                return False

        except subprocess.TimeoutExpired:
            # Kill the process to prevent zombie
            proc.kill()
            proc.wait()
            logger.error(f"Upload timeout after {self.timeout}s — process killed")
            return False

    def _parse_error(self, exit_code, stderr):
        """Parse rclone exit code into human-readable message."""
        error_map = {
            1: "Syntax error",
            2: "File not found",
            3: "Directory not found — verify folder_id",
            4: "File not in destination",
            5: "Temporary network error",
            6: "Less serious error",
            7: "Fatal error — check rclone config",
            8: "Transfer limit exceeded",
            9: "No files transferred — check permissions",
        }
        desc = error_map.get(exit_code, "Unknown error")
        detail = stderr.strip()[:200] if stderr else "No details"
        return f"{desc}: {detail}"

    def is_available(self):
        return self.is_configured
