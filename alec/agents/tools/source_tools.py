"""Source tool JSON schemas for the Anthropic tool-use API."""

from typing import Any

SOURCE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "survey",
        "description": (
            "List top-level entry points for this source. Returns a list of resource "
            "references you can read or explore further. Use this first to understand "
            "the source's structure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_children",
        "description": (
            "List sub-resources of a specific resource. For filesystem: files in a "
            "directory. For Confluence: child pages. For GitHub: files in a directory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "The resource reference to list children of.",
                },
            },
            "required": ["ref"],
        },
    },
    {
        "name": "read",
        "description": (
            "Read the full content of a specific resource. Returns the resource as text. "
            "May be large — use list_children first to identify what to read."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "The resource reference to read.",
                },
            },
            "required": ["ref"],
        },
    },
    {
        "name": "search",
        "description": (
            "Search within this source for content matching a query. Returns a list of "
            "matching resource references with snippets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
            },
            "required": ["query"],
        },
    },
]
