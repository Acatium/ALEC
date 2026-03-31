"""Entry point for running learning loop validation."""

import argparse
import asyncio
import json
import logging
import os
import sys

from .validator_runner import ValidationRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def report_to_dict(report) -> dict:
    """Convert ValidationReport to dictionary."""
    return {
        "id": report.id,
        "timestamp": report.timestamp,
        "overall_status": report.overall_status,
        "duration_ms": report.duration_ms,
        "test_session_id": report.test_session_id,
        "steps": [
            {
                "name": step.name,
                "status": step.status,
                "duration_ms": step.duration_ms,
                "evidence": {
                    "description": step.evidence.description,
                    "data": step.evidence.data,
                },
                "error": step.error,
            }
            for step in report.steps
        ],
        "diagnostics": [
            {
                "step_number": d.step_number,
                "step_name": d.step_name,
                "component": d.component,
                "action": d.action,
                "expected_result": d.expected_result,
                "actual_result": d.actual_result,
                "assessment": d.assessment,
                "explanation": d.explanation,
            }
            for d in report.diagnostics
        ],
    }


async def run_validation(args) -> int:
    """Run learning loop validation."""
    runner = ValidationRunner(
        session_url=args.session_url,
        db_url=args.db_url,
        redis_url=args.redis_url,
    )

    try:
        report = await runner.run_validation(
            test_message=args.message,
        )

        if args.output == "json":
            print(json.dumps(report_to_dict(report), indent=2))
        else:
            # Text output
            print(f"\n{'='*60}")
            print("Learning Loop Validation Report")
            print(f"{'='*60}")
            print(f"Report ID: {report.id}")
            print(f"Status: {report.overall_status.upper()}")
            print(f"Duration: {report.duration_ms}ms")
            print(f"Test Session: {report.test_session_id}")
            print("\nSteps:")

            for step in report.steps:
                status_icon = "✓" if step.status == "passed" else "✗" if step.status == "failed" else "○"
                print(f"  {status_icon} {step.name}: {step.status} ({step.duration_ms}ms)")
                if step.error:
                    print(f"      Error: {step.error}")

            print(f"\nDiagnostics ({len(report.diagnostics)} steps):")
            passed = sum(1 for d in report.diagnostics if d.assessment == "pass")
            failed = sum(1 for d in report.diagnostics if d.assessment == "fail")
            skipped = sum(1 for d in report.diagnostics if d.assessment == "skip")
            print(f"  Passed: {passed}, Failed: {failed}, Skipped: {skipped}")

            if args.verbose:
                print("\nDetailed Diagnostics:")
                for d in report.diagnostics:
                    status_icon = "✓" if d.assessment == "pass" else "✗" if d.assessment == "fail" else "○"
                    print(f"  {d.step_number:2}. {status_icon} {d.step_name}")
                    print(f"       Component: {d.component}")
                    print(f"       Action: {d.action}")
                    print(f"       Result: {d.actual_result}")

            print(f"{'='*60}")

        # Exit code based on status
        return 0 if report.overall_status == "passed" else 1

    finally:
        await runner.close()


async def run_health(args) -> int:
    """Run health check."""
    runner = ValidationRunner(
        session_url=args.session_url,
        db_url=args.db_url,
        redis_url=args.redis_url,
    )

    try:
        health = await runner.get_health()

        if args.output == "json":
            print(json.dumps(health, indent=2))
        else:
            print(f"\n{'='*60}")
            print("System Health Check")
            print(f"{'='*60}")
            print(f"Overall Status: {health['overall_status'].upper()}")
            print(f"Timestamp: {health['timestamp']}")

            print("\nServices:")
            for service in health.get("services", []):
                status_icon = "✓" if service["status"] == "healthy" else "✗"
                print(f"  {status_icon} {service['name']}: {service['status']}")
                if service.get("error"):
                    print(f"      Error: {service['error']}")

            print("\nInfrastructure:")
            for name, info in health.get("infrastructure", {}).items():
                status_icon = "✓" if info["status"] == "connected" else "✗"
                print(f"  {status_icon} {name}: {info['status']}")

            print(f"{'='*60}")

        return 0 if health["overall_status"] == "healthy" else 1

    finally:
        await runner.close()


async def main():
    """Main entry point for the validation runner."""
    parser = argparse.ArgumentParser(
        description="ALEC Learning Loop Validation Runner"
    )

    parser.add_argument(
        "command",
        choices=["validate", "health"],
        help="Command to run: validate (full validation) or health (quick check)",
    )
    parser.add_argument(
        "--message",
        default="Help me understand Python list comprehensions",
        help="Test message to send for validation",
    )
    parser.add_argument(
        "--session-url",
        default=os.getenv("ALEC_SESSION_URL", "http://session:8008"),
        help="ALEC session service URL",
    )
    parser.add_argument(
        "--db-url",
        default=os.getenv(
            "DATABASE_URL",
            "postgresql://alec:alec-dev-password@postgres:5432/alec"
        ),
        help="Database URL",
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        help="Redis URL",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output with detailed diagnostics",
    )
    parser.add_argument(
        "--output", "-o",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )

    args = parser.parse_args()

    if args.command == "validate":
        return await run_validation(args)
    elif args.command == "health":
        return await run_health(args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
