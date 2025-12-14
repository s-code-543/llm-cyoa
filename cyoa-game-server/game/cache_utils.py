"""
Cache utilities for synchronizing dual-model responses.
"""
import hashlib
import json
import threading
import time
from typing import Optional


class ResponseCache:
    """
    Thread-safe in-memory cache for synchronizing base and moderated responses.
    """
    
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
    
    def generate_key(self, messages, system_prompt=None):
        """
        Generate a session-based cache key.
        
        Uses a hash of the first user message (to identify the game session)
        plus the turn number (message count).
        
        This gives session isolation without complex full-chain hashing.
        
        Args:
            messages: List of message dicts
            system_prompt: Optional system prompt string (ignored)
        
        Returns:
            String key in format "session_hash-turn_number"
        """
        # Get first user message to identify the session
        first_msg = messages[0].get('content', '') if messages else ''
        session_hash = hashlib.sha256(first_msg.encode()).hexdigest()[:8]
        
        # Turn number is just message count
        turn = len(messages)
        
        key = f"{session_hash}-{turn}"
        print(f"[CACHE] Key = {key} (session: {session_hash}, turn: {turn})")
        return key
    
    def set(self, key, value):
        """Store a value in the cache."""
        with self._lock:
            self._cache[key] = {
                'value': value,
                'timestamp': time.time()
            }
            print(f"[CACHE] \u2713 Stored (cache now has {len(self._cache)} entries)")
    
    def get(self, key) -> Optional[str]:
        """Get a value from the cache if it exists and hasn't expired."""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                # Check if expired (30 second TTL)
                age = time.time() - entry['timestamp']
                if age > 30:
                    print(f"[CACHE] ✗ Entry {key} expired ({age:.1f}s old)")
                    del self._cache[key]
                    return None
                return entry['value']
            return None
    
    def wait_for(self, key, timeout=30.0, poll_interval=1.0) -> Optional[str]:
        """
        Wait for a key to appear in the cache.
        
        Args:
            key: Cache key to wait for
            timeout: Maximum seconds to wait (default: 30)
            poll_interval: Seconds between checks (default: 1.0)
        
        Returns:
            Cached value if found, None if timeout
        """
        start_time = time.time()
        attempts = 0
        
        while (time.time() - start_time) < timeout:
            attempts += 1
            elapsed = time.time() - start_time
            value = self.get(key)
            if value is not None:
                print(f"[CACHE] ✓ Found after {elapsed:.1f}s ({attempts} attempts)")
                return value
            if attempts % 5 == 0:  # Log every 5 seconds
                print(f"[CACHE] Still waiting... {elapsed:.1f}s elapsed")
            time.sleep(poll_interval)
        
        print(f"[CACHE] ✗ Timeout after {timeout}s ({attempts} attempts)")
        return None
    
    def cleanup_old_entries(self, max_age=300):
        """
        Remove cache entries older than max_age seconds.
        
        Args:
            max_age: Maximum age in seconds (default: 5 minutes)
        """
        with self._lock:
            current_time = time.time()
            keys_to_delete = [
                key for key, data in self._cache.items()
                if (current_time - data['timestamp']) > max_age
            ]
            for key in keys_to_delete:
                del self._cache[key]


# Global cache instance
response_cache = ResponseCache()
