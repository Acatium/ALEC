"""ALEC v5 entry point."""

from __future__ import annotations

import argparse
import asyncio
import sys

from alec.config.logging import configure_logging
from alec.config.settings import load_settings
from alec.runtime.supervisor import Supervisor


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="alec",
        description="ALEC v5 — Knowledge discovery through coordinated AI agents",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        required=True,
        help="Source to explore (repeatable). Examples: /path, web:https://..., https://...",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="Maximum coordinator cycles (default: 3)",
    )
    parser.add_argument(
        "--problem",
        default="",
        help="Problem statement describing what to discover",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path for HTML report output (default: alec-report-{id}.html)",
    )

    args = parser.parse_args()

    settings = load_settings()
    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
    )

    supervisor = Supervisor(settings)

    try:
        result = asyncio.run(
            supervisor.run(
                sources=args.sources,
                problem_statement=args.problem,
                max_cycles=args.cycles,
                report_path=args.output,
            )
        )
        print("\nDiscovery complete:")
        print(f"  Entities:      {result.get('entities', 0)}")
        print(f"  Relationships: {result.get('relationships', 0)}")
        print(f"  Observations:  {result.get('observations', 0)}")
        if result.get("report"):
            print(f"  Report:        {result['report']}")
    except KeyboardInterrupt:
        print("\nShutdown requested.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
