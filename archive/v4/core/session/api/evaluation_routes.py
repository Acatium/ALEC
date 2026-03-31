"""
Evaluation API endpoints - backward compatibility re-export.

This module has been refactored into the evaluation/ package:
- evaluation/models.py - Pydantic models
- evaluation/crud.py - CRUD endpoints
- evaluation/runner.py - Start/stop/stream endpoints
- evaluation/comparison.py - Comparison endpoints

Import from core.session.api.evaluation for new code.
"""

from core.session.api.evaluation import router

__all__ = ["router"]
