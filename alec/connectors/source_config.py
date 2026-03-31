"""Source specification parsing — converts CLI strings into typed source specs."""

from __future__ import annotations

from dataclasses import dataclass

from alec.errors import ConfigError


@dataclass
class SourceSpec:
    """Parsed source specification."""

    source_type: str
    config: dict[str, str]


def parse_source_spec(spec: str) -> SourceSpec:
    """Parse a source spec string into a SourceSpec.

    Supported formats:
        "/path/to/dir"              → local_files with base_path
        "local_files:/path/to/dir"  → local_files with base_path
        "web:https://example.com"   → web with seed_url
        "https://example.com"       → web with seed_url (inferred)
        "http://example.com"        → web with seed_url (inferred)
    """
    spec = spec.strip().strip("\"'")
    if not spec:
        raise ConfigError("Empty source specification")

    # Check for typed prefix
    if ":" in spec:
        prefix, _, rest = spec.partition(":")
        # URL-like prefixes: infer web
        if prefix in ("http", "https"):
            return SourceSpec(source_type="web", config={"seed_url": spec})
        # Explicit type prefix
        if prefix and rest:
            if prefix == "local_files":
                return SourceSpec(source_type="local_files", config={"base_path": rest})
            if prefix == "web":
                return SourceSpec(source_type="web", config={"seed_url": rest})
            # Single letter prefix = Windows drive letter (e.g. C:\path)
            if len(prefix) == 1 and prefix.isalpha():
                return SourceSpec(source_type="local_files", config={"base_path": spec})
            # Unknown type — pass through
            return SourceSpec(source_type=prefix, config={"ref": rest})

    # Bare path — infer local_files
    return SourceSpec(source_type="local_files", config={"base_path": spec})
