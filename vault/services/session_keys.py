import threading
import time


_LOCK = threading.Lock()
_KEYS = {}
DEFAULT_TTL = 45 * 60


def _purge_expired(now=None):
  now = time.monotonic() if now is None else now
  expired = [session_id for session_id, (until, _) in _KEYS.items() if until <= now]
  for session_id in expired:
    _KEYS.pop(session_id, None)


def store_vault_key(session_id, vault_key, ttl=DEFAULT_TTL):
  if not session_id or not isinstance(vault_key, bytes):
    raise ValueError("A valid session and vault key are required")
  with _LOCK:
    _purge_expired()
    _KEYS[session_id] = (time.monotonic() + ttl, vault_key)


def get_vault_key(session_id):
  if not session_id:
    return None
  with _LOCK:
    _purge_expired()
    item = _KEYS.get(session_id)
    return item[1] if item else None


def clear_vault_key(session_id):
  if not session_id:
    return
  with _LOCK:
    _KEYS.pop(session_id, None)

