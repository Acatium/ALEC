"""Integration tests for ConfigStore with real PostgreSQL.

Tests actual database operations to catch schema mismatches and SQL errors.

Test Philosophy: "All correct" - fix errors, don't alter tests unless proven inaccurate.
"""

from uuid import uuid4

import pytest

# ============================================================================
# Test: SQL Query Validation (EXPLAIN)
# ============================================================================


class TestConfigStoreSQLValidation:
    """Validate SQL queries against real schema using EXPLAIN."""

    @pytest.mark.asyncio
    async def test_service_configs_table_exists(self, db_conn):
        """service_configs table should exist with expected columns."""
        result = await db_conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'service_configs'
        """)

        columns = {row["column_name"] for row in result}

        # Required columns for ConfigStore
        assert "service_name" in columns
        assert "parameter_name" in columns
        assert "parameter_value" in columns

    @pytest.mark.asyncio
    async def test_prompts_table_exists(self, db_conn):
        """service_prompts table should exist with expected columns."""
        result = await db_conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'service_prompts'
        """)

        columns = {row["column_name"] for row in result}

        # Required columns for ConfigStore prompt loading
        assert "service_name" in columns
        assert "prompt_name" in columns
        assert "prompt_content" in columns
        assert "is_active" in columns

    @pytest.mark.asyncio
    async def test_config_select_query_syntax(self, db_conn):
        """ConfigStore SELECT query should be valid SQL."""
        # This is the actual query from config_store.py
        query = """
            EXPLAIN SELECT service_name, parameter_name, parameter_value
            FROM service_configs
            WHERE parameter_name IN ('model', 'temperature', 'max_tokens')
        """
        # Should not raise - validates syntax and column names
        await db_conn.fetch(query)

    @pytest.mark.asyncio
    async def test_prompts_select_query_syntax(self, db_conn):
        """ConfigStore prompts SELECT query should be valid SQL."""
        query = """
            EXPLAIN SELECT service_name, prompt_content
            FROM service_prompts
            WHERE prompt_name = 'system_prompt' AND is_active = true
        """
        await db_conn.fetch(query)


# ============================================================================
# Test: Real Database Operations
# ============================================================================


class TestConfigStoreRealOperations:
    """Test ConfigStore with real database operations."""

    @pytest.mark.asyncio
    async def test_load_configs_from_empty_table(self, db_conn):
        """Should handle empty service_configs table gracefully."""
        # Query actual data
        result = await db_conn.fetch("""
            SELECT service_name, parameter_name, parameter_value
            FROM service_configs
            WHERE parameter_name IN ('model', 'temperature', 'max_tokens')
        """)

        # Should return list (possibly empty)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_insert_and_read_config(self, db_conn, clean_test_configs):
        """Should insert and read config from real database."""
        test_service = f"test_service_{uuid4().hex[:8]}"
        clean_test_configs.append(test_service)

        # Insert test config (include all required NOT NULL columns)
        await db_conn.execute("""
            INSERT INTO service_configs (service_name, parameter_name, parameter_value, default_value, data_type)
            VALUES ($1, 'model', '"test-model-123"', '"test-model-123"', 'string')
        """, test_service)

        # Read it back
        result = await db_conn.fetchrow("""
            SELECT parameter_value FROM service_configs
            WHERE service_name = $1 AND parameter_name = 'model'
        """, test_service)

        assert result is not None
        assert result["parameter_value"] == "test-model-123"

    @pytest.mark.asyncio
    async def test_temperature_stored_as_string(self, db_conn, clean_test_configs):
        """Temperature should be stored as string and convertible to float."""
        test_service = f"test_service_{uuid4().hex[:8]}"
        clean_test_configs.append(test_service)

        # Insert temperature (include all required NOT NULL columns)
        await db_conn.execute("""
            INSERT INTO service_configs (service_name, parameter_name, parameter_value, default_value, data_type)
            VALUES ($1, 'temperature', '0.7', '0.7', 'number')
        """, test_service)

        result = await db_conn.fetchrow("""
            SELECT parameter_value FROM service_configs
            WHERE service_name = $1 AND parameter_name = 'temperature'
        """, test_service)

        # Should be convertible to float
        temp = float(result["parameter_value"])
        assert temp == 0.7

    @pytest.mark.asyncio
    async def test_max_tokens_stored_as_string(self, db_conn, clean_test_configs):
        """max_tokens should be stored as string and convertible to int."""
        test_service = f"test_service_{uuid4().hex[:8]}"
        clean_test_configs.append(test_service)

        await db_conn.execute("""
            INSERT INTO service_configs (service_name, parameter_name, parameter_value, default_value, data_type)
            VALUES ($1, 'max_tokens', '4096', '4096', 'number')
        """, test_service)

        result = await db_conn.fetchrow("""
            SELECT parameter_value FROM service_configs
            WHERE service_name = $1 AND parameter_name = 'max_tokens'
        """, test_service)

        # Should be convertible to int
        tokens = int(result["parameter_value"])
        assert tokens == 4096


# ============================================================================
# Test: ConfigStore Class Integration
# ============================================================================


class TestConfigStoreClassIntegration:
    """Test actual ConfigStore class with real database."""

    @pytest.mark.asyncio
    async def test_initialize_connects_to_real_db(self, db_pool):
        """ConfigStore.initialize should connect to real database."""
        from core.llm_gateway.infrastructure.config_store import ConfigStore

        store = ConfigStore()

        # Get connection string from pool (reuse existing connection)
        import os
        _default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        db_url = f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"

        await store.initialize(db_url)

        # Should have loaded configs
        assert len(store._configs) > 0
        await store.close()

    @pytest.mark.asyncio
    async def test_reload_loads_default_services(self, db_pool):
        """reload_configs should load default service configs."""
        from core.llm_gateway.infrastructure.config_store import DEFAULT_CONFIGS, ConfigStore

        store = ConfigStore()

        import os
        _default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        db_url = f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"

        await store.initialize(db_url)

        # Should have all default services
        for service_name in DEFAULT_CONFIGS:
            config = store.get_config(service_name)
            assert config is not None, f"Missing config for {service_name}"

        await store.close()

    @pytest.mark.asyncio
    async def test_get_config_returns_none_for_unknown(self, db_pool):
        """get_config should return None for unknown service."""
        from core.llm_gateway.infrastructure.config_store import ConfigStore

        store = ConfigStore()

        import os
        _default_host = "postgres" if os.path.exists("/.dockerenv") else "localhost"
        db_url = f"postgresql://alec:alec-dev-password@{_default_host}:5432/alec"

        await store.initialize(db_url)

        config = store.get_config("nonexistent_service_12345")
        assert config is None

        await store.close()
