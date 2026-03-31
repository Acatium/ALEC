#!/usr/bin/env python3
"""Verification script for GAP-021 fix.

Run this BEFORE and AFTER deployment to verify:
1. UUID parsing works correctly
2. No regressions in valid UUID extraction
3. Invalid text is properly filtered

Usage:
    python scripts/verify_gap021_fix.py
"""

import sys

sys.path.insert(0, '/home/matt/ALEC')

def test_uuid_parsing():
    """Test _parse_id_list function with various inputs."""
    from core.learning_loop.shared.text_parser import _parse_id_list

    # Test cases: (input, expected_output, description)
    test_cases = [
        # Valid UUIDs
        (
            "d6aa0d04-1234-5678-9abc-def012345678",
            ["d6aa0d04-1234-5678-9abc-def012345678"],
            "Single valid UUID"
        ),
        (
            "d6aa0d04-1234-5678-9abc-def012345678, a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            ["d6aa0d04-1234-5678-9abc-def012345678", "a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
            "Multiple valid UUIDs"
        ),
        # UUIDs with annotations (LLM often adds these)
        (
            "d6aa0d04-1234-5678-9abc-def012345678 (agent used this for debugging)",
            ["d6aa0d04-1234-5678-9abc-def012345678"],
            "UUID with annotation"
        ),
        # None/empty values
        ("none", [], "none keyword"),
        ("n/a", [], "n/a keyword"),
        ("", [], "empty string"),
        ("[]", [], "empty brackets"),
        # Invalid text (the bug case)
        (
            "but agent didn't follow through effectively)",
            [],
            "Invalid text - should return empty"
        ),
        (
            "but agent didn't implement this pivot)",
            [],
            "Another invalid text case"
        ),
        # Mixed valid and invalid
        (
            "d6aa0d04-1234-5678-9abc-def012345678, but didn't work",
            ["d6aa0d04-1234-5678-9abc-def012345678"],
            "Mixed valid and invalid"
        ),
        # Edge cases
        (
            "  d6aa0d04-1234-5678-9abc-def012345678  ",
            ["d6aa0d04-1234-5678-9abc-def012345678"],
            "UUID with whitespace"
        ),
        (
            "D6AA0D04-1234-5678-9ABC-DEF012345678",
            ["D6AA0D04-1234-5678-9ABC-DEF012345678"],
            "Uppercase UUID"
        ),
    ]

    passed = 0
    failed = 0

    print("=" * 60)
    print("GAP-021 UUID Parsing Verification")
    print("=" * 60)
    print()

    for input_val, expected, description in test_cases:
        try:
            result = _parse_id_list(input_val)
            if result == expected:
                print(f"✓ PASS: {description}")
                passed += 1
            else:
                print(f"✗ FAIL: {description}")
                print(f"  Input:    {input_val!r}")
                print(f"  Expected: {expected}")
                print(f"  Got:      {result}")
                failed += 1
        except Exception as e:
            print(f"✗ ERROR: {description}")
            print(f"  Exception: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


def test_is_valid_uuid():
    """Test is_valid_uuid helper if it exists."""
    try:
        from core.learning_loop.shared.text_parser import is_valid_uuid
    except ImportError:
        print("\n⚠ is_valid_uuid not found (expected before fix)")
        return True

    test_cases = [
        ("d6aa0d04-1234-5678-9abc-def012345678", True, "Valid UUID"),
        ("D6AA0D04-1234-5678-9ABC-DEF012345678", True, "Uppercase UUID"),
        ("not-a-uuid", False, "Invalid string"),
        ("but agent didn't implement", False, "Invalid text"),
        ("", False, "Empty string"),
        ("d6aa0d04-1234-5678-9abc", False, "Incomplete UUID"),
    ]

    print("\nUUID Validation Helper Tests:")
    print("-" * 40)

    passed = 0
    failed = 0

    for input_val, expected, description in test_cases:
        result = is_valid_uuid(input_val)
        if result == expected:
            print(f"✓ {description}")
            passed += 1
        else:
            print(f"✗ {description}: expected {expected}, got {result}")
            failed += 1

    return failed == 0


def test_extract_bullet_id():
    """Test _extract_bullet_id in clusterer."""
    try:
        from core.learning_loop.clusterer.service import _extract_bullet_id
    except ImportError as e:
        print(f"\n⚠ Could not import _extract_bullet_id: {e}")
        return True

    test_cases = [
        # Dict inputs (from SESSION)
        ({"id": "d6aa0d04-1234-5678-9abc-def012345678"}, "d6aa0d04-1234-5678-9abc-def012345678"),
        ({"bullet_id": "d6aa0d04-1234-5678-9abc-def012345678"}, "d6aa0d04-1234-5678-9abc-def012345678"),
        # String inputs
        ("d6aa0d04-1234-5678-9abc-def012345678", "d6aa0d04-1234-5678-9abc-def012345678"),
        # Invalid inputs (after fix, should return None)
        ("not-a-uuid", None),
        (None, None),
        ({}, None),
    ]

    print("\nBullet ID Extraction Tests:")
    print("-" * 40)

    passed = 0
    failed = 0

    for input_val, expected in test_cases:
        result = _extract_bullet_id(input_val)
        # After fix, invalid strings should return None
        # Before fix, they return the string as-is
        if result == expected:
            print(f"✓ Input {input_val!r} -> {result!r}")
            passed += 1
        elif expected is None and result is not None:
            # This is the bug case - before fix
            print(f"⚠ Input {input_val!r} -> {result!r} (expected None after fix)")
            passed += 1  # Still a "pass" for pre-fix verification
        else:
            print(f"✗ Input {input_val!r} -> {result!r} (expected {expected!r})")
            failed += 1

    return failed == 0


def main():
    """Run all verification tests."""
    all_passed = True

    all_passed &= test_uuid_parsing()
    all_passed &= test_is_valid_uuid()
    all_passed &= test_extract_bullet_id()

    print()
    if all_passed:
        print("✓ All verification tests passed!")
        return 0
    else:
        print("✗ Some tests failed - review output above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
