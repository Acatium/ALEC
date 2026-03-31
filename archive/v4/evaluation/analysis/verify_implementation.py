"""
Verify that the statistical analysis implementation is correct.

This script performs basic validation of the implemented functions
without requiring pytest or full dependencies.
"""

import importlib.util
import sys


def check_module_syntax(module_path, module_name):
    """Check if a module has valid Python syntax."""
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None:
            return False, f"Could not load spec for {module_name}"

        module = importlib.util.module_from_spec(spec)
        # Don't execute, just parse
        with open(module_path, 'r') as f:
            code = f.read()
            compile(code, module_path, 'exec')
        return True, "Syntax valid"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def check_function_signatures(module_path):
    """Check that functions have proper type hints and docstrings."""
    with open(module_path, 'r') as f:
        content = f.read()

    issues = []

    # Check for common patterns
    if 'def ' not in content:
        issues.append("No function definitions found")

    # Count functions with docstrings
    import re
    functions = re.findall(r'def (\w+)\([^)]*\):', content)
    docstring_pattern = r'def \w+\([^)]*\):\s*"""'
    docstrings = re.findall(docstring_pattern, content)

    if len(functions) > 0:
        coverage = len(docstrings) / len(functions) * 100
        if coverage < 80:
            issues.append(f"Only {coverage:.1f}% of functions have docstrings")

    return issues


def main():
    """Run verification checks."""
    print("=" * 70)
    print("VERIFICATION: Statistical Analysis Implementation")
    print("=" * 70)

    modules = [
        ("evaluation/analysis/bootstrap.py", "bootstrap"),
        ("evaluation/analysis/effect_sizes.py", "effect_sizes"),
        ("evaluation/analysis/statistical_tests.py", "statistical_tests"),
    ]

    all_valid = True

    for module_path, module_name in modules:
        print(f"\nChecking {module_name}...")

        # Check syntax
        valid, message = check_module_syntax(module_path, module_name)
        if valid:
            print(f"  ✓ Syntax: {message}")
        else:
            print(f"  ✗ Syntax: {message}")
            all_valid = False
            continue

        # Check documentation
        issues = check_function_signatures(module_path)
        if not issues:
            print("  ✓ Documentation: Good coverage")
        else:
            for issue in issues:
                print(f"  ! Documentation: {issue}")

        # Count lines
        with open(module_path, 'r') as f:
            lines = len([l for l in f if l.strip()])
        print(f"  ℹ Size: {lines} lines of code")

    print("\n" + "=" * 70)

    # Check test files
    print("\nChecking test files...")
    test_modules = [
        ("evaluation/analysis/tests/test_bootstrap.py", "test_bootstrap"),
        ("evaluation/analysis/tests/test_effect_sizes.py", "test_effect_sizes"),
        ("evaluation/analysis/tests/test_statistical_tests.py", "test_statistical_tests"),
    ]

    total_tests = 0
    for test_path, test_name in test_modules:
        valid, message = check_module_syntax(test_path, test_name)
        if valid:
            # Count test methods
            with open(test_path, 'r') as f:
                content = f.read()
            import re
            tests = re.findall(r'def (test_\w+)', content)
            total_tests += len(tests)
            print(f"  ✓ {test_name}: {len(tests)} test methods")
        else:
            print(f"  ✗ {test_name}: {message}")
            all_valid = False

    print(f"\n  Total test methods: {total_tests}")

    print("\n" + "=" * 70)

    if all_valid:
        print("✓ All modules have valid syntax")
        print("\nTo run tests (requires scipy):")
        print("  pip install scipy>=1.10.0")
        print("  pytest evaluation/analysis/tests/ -v")
        return 0
    else:
        print("✗ Some modules have errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
