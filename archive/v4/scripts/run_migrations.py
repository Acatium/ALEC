#!/usr/bin/env python3
"""
Database migration runner for ALEC.

Checks schema_migrations table and applies any pending migrations from docker/init/.
Run this on startup or manually to ensure schema is up to date.

Usage:
    python scripts/run_migrations.py [--dry-run]
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

import asyncpg


async def get_applied_migrations(conn) -> set[str]:
    """Get set of already-applied migration names."""
    rows = await conn.fetch("SELECT migration_name FROM schema_migrations")
    return {row["migration_name"] for row in rows}


async def apply_migration(conn, migration_path: Path, dry_run: bool = False) -> bool:
    """Apply a single migration file."""
    migration_name = migration_path.name

    # Calculate checksum
    content = migration_path.read_text()
    checksum = hashlib.sha256(content.encode()).hexdigest()[:16]

    if dry_run:
        print(f"  [DRY-RUN] Would apply: {migration_name}")
        return True

    try:
        # Run migration in transaction
        async with conn.transaction():
            await conn.execute(content)
            await conn.execute(
                """
                INSERT INTO schema_migrations (migration_name, checksum)
                VALUES ($1, $2)
                ON CONFLICT (migration_name) DO UPDATE SET checksum = $2
                """,
                migration_name,
                checksum,
            )
        print(f"  ✓ Applied: {migration_name}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {migration_name} - {e}")
        return False


async def run_migrations(database_url: str, dry_run: bool = False) -> int:
    """Run all pending migrations."""
    # Find migration files
    migrations_dir = Path(__file__).parent.parent / "docker" / "init"
    if not migrations_dir.exists():
        print(f"Error: Migrations directory not found: {migrations_dir}")
        return 1

    # Get all .sql files, sorted by name (numeric prefix ensures order)
    migration_files = sorted(migrations_dir.glob("*.sql"))

    # Skip archive directory
    migration_files = [f for f in migration_files if "archive" not in str(f)]

    if not migration_files:
        print("No migration files found.")
        return 0

    print(f"Found {len(migration_files)} migration files")

    # Connect to database
    try:
        conn = await asyncpg.connect(database_url)
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return 1

    try:
        # Ensure schema_migrations table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                migration_name VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                checksum VARCHAR(64)
            )
        """)

        # Get already-applied migrations
        applied = await get_applied_migrations(conn)
        print(f"Already applied: {len(applied)} migrations")

        # Find pending migrations
        pending = [f for f in migration_files if f.name not in applied]

        if not pending:
            print("Schema is up to date.")
            return 0

        print(f"Pending migrations: {len(pending)}")

        # Apply pending migrations in order
        failed = 0
        for migration_path in pending:
            success = await apply_migration(conn, migration_path, dry_run)
            if not success:
                failed += 1

        if failed > 0:
            print(f"\n{failed} migration(s) failed.")
            return 1

        print(f"\nSuccessfully applied {len(pending)} migration(s).")
        return 0

    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be applied without making changes",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql://alec:alec-dev-password@localhost:5432/alec"
        ),
        help="Database connection URL",
    )
    args = parser.parse_args()

    import asyncio
    exit_code = asyncio.run(run_migrations(args.database_url, args.dry_run))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
