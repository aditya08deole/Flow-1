import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class OfflineQueue:
    """SQLite-backed queue for IoT telemetry to prevent data loss when offline."""
    
    def __init__(self, db_path="offline_queue.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filepath TEXT NOT NULL,
                        meter_value REAL,
                        status_code INTEGER,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize SQLite queue: {e}")

    def prune_old_entries(self, days=30):
        """Remove entries older than `days` to prevent infinite SD card space exhaustion if the device goes permanently offline."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM queue WHERE timestamp < datetime('now', '-{} days')".format(days)
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to prune old entries: {e}")

    def push(self, filepath, meter_value, status_code):
        """Add an item to the backlog queue."""
        self.prune_old_entries(days=30)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO queue (filepath, meter_value, status_code) VALUES (?, ?, ?)',
                    (filepath, meter_value, status_code)
                )
                conn.commit()
            logger.info(f"Queued for later upload: {os.path.basename(filepath)}")
        except sqlite3.Error as e:
            logger.error(f"Failed to push to queue: {e}")

    def get_all_filepaths(self):
        """Retrieve all filepaths currently in the queue to protect them from cleanup."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT filepath FROM queue')
                rows = cursor.fetchall()
                return {row[0] for row in rows}
        except sqlite3.Error:
            return set()

    def pop_all(self):
        """Retrieve all items from the queue and delete them."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, filepath, meter_value, status_code, timestamp FROM queue ORDER BY timestamp ASC')
                rows = cursor.fetchall()
                
                if rows:
                    cursor.execute('DELETE FROM queue')
                    conn.commit()
                    
                items = []
                for row in rows:
                    items.append({
                        'id': row[0],
                        'filepath': row[1],
                        'meter_value': row[2],
                        'status_code': row[3],
                        'timestamp': row[4]
                    })
                return items
        except sqlite3.Error as e:
            logger.error(f"Failed to pop from queue: {e}")
            return []
