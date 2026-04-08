from __future__ import annotations
import json
import os
import threading
import time
import logging
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_FRAMEWORK_VERSION = "2.0.0"


class SnapshotManager:
    """Manages state snapshots for interruption recovery.

    Snapshots capture the current state of:
    - Component states (via params)
    - Pending messages in channels
    - Cache contents

    Snapshots can be saved to disk and restored later.
    """

    def __init__(self, storage_dir: Optional[str] = None) -> None:
        self._storage_dir = storage_dir or os.path.join(os.getcwd(), ".snapshots")
        self._lock = threading.Lock()
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        os.makedirs(self._storage_dir, exist_ok=True)

    def capture(
        self,
        snapshot_id: str,
        components: Optional[Dict[str, Any]] = None,
        pending_messages: Optional[list] = None,
        cache_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        snapshot = {
            "components": components or {},
            "pending_messages": pending_messages or [],
            "cache_data": cache_data or {},
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                "framework_version": _FRAMEWORK_VERSION,
            },
        }
        if metadata:
            snapshot["metadata"].update(metadata)
        with self._lock:
            self._snapshots[snapshot_id] = snapshot
        return snapshot_id

    def restore(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if snapshot is not None:
                return snapshot
        return self.load(snapshot_id)

    def list_snapshots(self) -> Dict[str, Dict[str, Any]]:
        result = {}
        with self._lock:
            for sid, snapshot in self._snapshots.items():
                result[sid] = {
                    "timestamp": snapshot.get("metadata", {}).get(
                        "timestamp", "unknown"
                    ),
                    "component_count": len(snapshot.get("components", {})),
                    "has_messages": bool(snapshot.get("pending_messages")),
                    "has_cache": bool(snapshot.get("cache_data")),
                }
        for filename in os.listdir(self._storage_dir):
            if filename.endswith(".json"):
                sid = filename[:-5]
                if sid not in result:
                    filepath = os.path.join(self._storage_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        result[sid] = {
                            "timestamp": data.get("metadata", {}).get(
                                "timestamp", "unknown"
                            ),
                            "component_count": len(data.get("components", {})),
                            "has_messages": bool(data.get("pending_messages")),
                            "has_cache": bool(data.get("cache_data")),
                        }
                    except (json.JSONDecodeError, OSError) as e:
                        log.warning("SnapshotManager: failed to list '%s': %s", sid, e)
        return result

    def delete(self, snapshot_id: str) -> bool:
        existed = False
        with self._lock:
            if snapshot_id in self._snapshots:
                del self._snapshots[snapshot_id]
                existed = True
        filepath = os.path.join(self._storage_dir, f"{snapshot_id}.json")
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                existed = True
            except OSError as e:
                log.warning("SnapshotManager: failed to delete '%s': %s", filepath, e)
        return existed

    def persist(self, snapshot_id: str) -> bool:
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if snapshot is None:
                log.warning(
                    "SnapshotManager: snapshot '%s' not found for persist", snapshot_id
                )
                return False
        filepath = os.path.join(self._storage_dir, f"{snapshot_id}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str)
            return True
        except (TypeError, OSError) as e:
            log.warning("SnapshotManager: failed to persist '%s': %s", snapshot_id, e)
            return False

    def load(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        filepath = os.path.join(self._storage_dir, f"{snapshot_id}.json")
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._snapshots[snapshot_id] = data
            return data
        except (json.JSONDecodeError, OSError) as e:
            log.warning("SnapshotManager: failed to load '%s': %s", snapshot_id, e)
            return None
