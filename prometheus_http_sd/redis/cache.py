import json
import logging
import redis
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self._redis_client = redis.from_url(
            self.redis_url, decode_responses=True
        )

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        data = self._redis_client.get(key)
        if data:
            return json.loads(data)
        return None

    def set(
        self, key: str, data: Dict[str, Any], expire_seconds: int = 300
    ) -> bool:
        json_data = json.dumps(data)
        result = self._redis_client.setex(key, expire_seconds, json_data)
        logger.debug(
            f"Cached data for key {key} with {expire_seconds}s expiration"
        )
        return result

    def delete(self, key: str) -> bool:
        """Delete cached data for a key."""
        result = self._redis_client.delete(key)
        logger.debug(f"Deleted cache data for key {key}")
        return bool(result)

    def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        return bool(self._redis_client.exists(key))
