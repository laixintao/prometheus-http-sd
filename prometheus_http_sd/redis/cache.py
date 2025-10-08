import json
import logging
import redis
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self._redis_client = None
        self._connected = False
    
    def _connect(self):
        if not self._connected:
            try:
                self._redis_client = redis.from_url(self.redis_url, decode_responses=True)
                # Test connection
                self._redis_client.ping()
                self._connected = True
                logger.info(f"Connected to Redis at {self.redis_url}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
    
    def is_available(self) -> bool:
        try:
            if not self._connected:
                self._connect()
            return self._redis_client.ping()
        except Exception:
            return False
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            if not self._connected:
                self._connect()
            
            data = self._redis_client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Failed to get cache data for key {key}: {e}")
            return None
    
    def set(self, key: str, data: Dict[str, Any], expire_seconds: int = 300) -> bool:
        try:
            if not self._connected:
                self._connect()
            
            json_data = json.dumps(data)
            result = self._redis_client.setex(key, expire_seconds, json_data)
            logger.debug(f"Cached data for key {key} with {expire_seconds}s expiration")
            return result
        except Exception as e:
            logger.error(f"Failed to set cache data for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete cached data for a key."""
        try:
            if not self._connected:
                self._connect()
            
            result = self._redis_client.delete(key)
            logger.debug(f"Deleted cache data for key {key}")
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to delete cache data for key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        try:
            if not self._connected:
                self._connect()
            
            return bool(self._redis_client.exists(key))
        except Exception as e:
            logger.error(f"Failed to check existence of key {key}: {e}")
            return False
