"""Integration tests for the Learning Loop.

These tests validate SQL queries and database operations against
the real PostgreSQL schema to catch column mismatches, JOIN errors,
and other issues that mocked tests cannot detect.

Test markers:
- @pytest.mark.sql_validation: SQL syntax validation (EXPLAIN-based)
- @pytest.mark.db_integration: Tests with real data
- @pytest.mark.pipeline: End-to-end pipeline tests
"""
