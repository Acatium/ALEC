"""Worker drift detection — deduplication, retry limiting, and scope drift flags."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class WorkerLoopState:
    """Tracks a single worker's tool-use loop for degenerate behaviour."""

    tool_call_cache: dict[str, str] = field(default_factory=dict)
    tool_error_counts: dict[str, int] = field(default_factory=dict)
    duplicate_calls_skipped: int = 0
    retries_exhausted: int = 0
    drift_detected: bool = False
    entity_types_discovered: dict[str, int] = field(default_factory=dict)
    tool_call_count: int = 0


def hash_tool_call(name: str, params: dict[str, object]) -> str:
    """Deterministic SHA-256 hash of tool name + sorted JSON params."""
    payload = name + json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def check_drift(
    state: WorkerLoopState,
    directive_scope: str,
    threshold: float = 0.5,
) -> bool:
    """Check if the worker is drifting from its directive scope.

    Returns True if more than `threshold` fraction of discovered entity types
    are outside the directive scope (case-insensitive substring match).

    Returns False if no entity types have been discovered yet.
    """
    if not state.entity_types_discovered:
        return False

    scope_lower = directive_scope.lower()
    total = 0
    out_of_scope = 0

    for entity_type, count in state.entity_types_discovered.items():
        total += count
        # Check if any scope keyword matches the entity type
        if scope_lower not in entity_type.lower() and entity_type.lower() not in scope_lower:
            out_of_scope += count

    if total == 0:
        return False

    return (out_of_scope / total) > threshold
