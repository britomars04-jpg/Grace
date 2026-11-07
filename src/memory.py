"""Persistent memory storage for cross-session user information."""

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class UserProfile:
    """User profile information stored across sessions."""

    user_id: str | None = None
    name: str | None = None
    email: str | None = None
    expertise_level: str | None = None  # beginner, intermediate, expert
    preferences: dict[str, Any] = field(default_factory=dict)
    conversation_summary: str | None = None
    last_interaction: str | None = None  # ISO timestamp
    additional_info: dict[str, Any] = field(default_factory=dict)


class MemoryStore:
    """Simple file-based memory store for user profiles."""

    def __init__(self, storage_path: str = ".agent_memory.json"):
        self.storage_path = Path(storage_path)
        self._lock = threading.Lock()
        self._ensure_storage_exists()

    def _ensure_storage_exists(self) -> None:
        """Create storage file if it doesn't exist."""
        if not self.storage_path.exists():
            self.storage_path.write_text("{}")

    def _load_all(self) -> dict[str, Any]:
        """Load all user data from storage."""
        try:
            with open(self.storage_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_all(self, data: dict[str, Any]) -> None:
        """Save all user data to storage."""
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_user(self, user_id: str) -> UserProfile | None:
        """Retrieve a user's profile from memory."""
        with self._lock:
            data = self._load_all()
            user_data = data.get(user_id)
            if user_data:
                return UserProfile(**user_data)
            return None

    def save_user(self, user_id: str, profile: UserProfile) -> None:
        """Save or update a user's profile."""
        with self._lock:
            data = self._load_all()
            profile.last_interaction = datetime.now().isoformat()
            data[user_id] = asdict(profile)
            self._save_all(data)

    def update_user_field(self, user_id: str, field_name: str, value: Any) -> None:
        """Update a specific field in the user's profile."""
        with self._lock:
            data = self._load_all()
            user_data = data.get(user_id, {})
            user_data[field_name] = value
            user_data["last_interaction"] = datetime.now().isoformat()
            data[user_id] = user_data
            self._save_all(data)

    def delete_user(self, user_id: str) -> bool:
        """Delete a user's profile. Returns True if deleted, False if not found."""
        with self._lock:
            data = self._load_all()
            if user_id in data:
                del data[user_id]
                self._save_all(data)
                return True
            return False

    def list_users(self) -> list[str]:
        """Get list of all user IDs in memory."""
        with self._lock:
            return list(self._load_all().keys())


# Global memory store instance
_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """Get the global memory store instance."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
