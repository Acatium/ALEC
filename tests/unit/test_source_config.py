"""Tests for source spec parsing."""

from __future__ import annotations

import pytest

from alec.connectors.source_config import SourceSpec, parse_source_spec
from alec.errors import ConfigError


def test_bare_path():
    spec = parse_source_spec("/home/user/docs")
    assert spec == SourceSpec(source_type="local_files", config={"base_path": "/home/user/docs"})


def test_typed_local_files():
    spec = parse_source_spec("local_files:/home/user/docs")
    assert spec == SourceSpec(source_type="local_files", config={"base_path": "/home/user/docs"})


def test_typed_web():
    spec = parse_source_spec("web:https://example.com/page")
    assert spec == SourceSpec(source_type="web", config={"seed_url": "https://example.com/page"})


def test_https_url_infers_web():
    spec = parse_source_spec("https://en.wikipedia.org/wiki/Test")
    assert spec.source_type == "web"
    assert spec.config["seed_url"] == "https://en.wikipedia.org/wiki/Test"


def test_http_url_infers_web():
    spec = parse_source_spec("http://example.com")
    assert spec.source_type == "web"
    assert spec.config["seed_url"] == "http://example.com"


def test_empty_raises():
    with pytest.raises(ConfigError, match="Empty source"):
        parse_source_spec("")


def test_whitespace_only_raises():
    with pytest.raises(ConfigError, match="Empty source"):
        parse_source_spec("   ")


def test_whitespace_stripped():
    spec = parse_source_spec("  /some/path  ")
    assert spec.config["base_path"] == "/some/path"


def test_unknown_type_passes_through():
    spec = parse_source_spec("confluence:space/page")
    assert spec.source_type == "confluence"
    assert spec.config["ref"] == "space/page"
