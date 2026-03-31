"""Task runner for executing AppWorld tasks through ALEC.

This module is intentionally decoupled from ALEC internals - it only
communicates via the session HTTP API. No Kafka, no Redis, no core imports.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from appworld import AppWorld

from .alec_client import ALECClient, ALECClientError

logger = logging.getLogger(__name__)

# Loop detection disabled - let turns_per_task be the only limit
# These thresholds were causing premature exits on challenging tasks
# LOOP_IDENTICAL_CODE_THRESHOLD = int(os.getenv("LOOP_IDENTICAL_CODE_THRESHOLD", "3"))
# LOOP_SAME_ERROR_THRESHOLD = int(os.getenv("LOOP_SAME_ERROR_THRESHOLD", "3"))
# LOOP_NO_PROGRESS_THRESHOLD = int(os.getenv("LOOP_NO_PROGRESS_THRESHOLD", "4"))


@dataclass
class TaskResult:
    """Result from running a single AppWorld task through ALEC."""

    task_id: str
    session_id: str
    success: bool
    iterations: int
    tokens_used: int
    duration_ms: int
    bullets_used: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None
    test_results: dict[str, Any] | None = None
    task_description: str | None = None  # Truncated for display (150 chars)
    full_instruction: str | None = None  # Full instruction for embedding/learning
    final_response: str | None = None


class TaskRunner:
    """Runs AppWorld tasks through ALEC with iterative error correction."""

    def __init__(
        self,
        alec_url: str = "http://localhost:8008",
        turns_per_task: int = 25,
        experiment_name: str = "alec_eval",
    ):
        """Initialize task runner.

        Args:
            alec_url: Base URL for the ALEC session service.
            turns_per_task: Max conversation turns per task (0 = until success, default 25).
            experiment_name: Name for the AppWorld experiment outputs.

        Note: Learning is controlled via service toggles on /agents page,
        not per-request parameters.
        """
        self.alec_url = alec_url
        self.turns_per_task = turns_per_task if turns_per_task > 0 else 100  # 0 = until success (with safety cap)
        self.experiment_name = experiment_name

        logger.info(f"TaskRunner initialized with turns_per_task={self.turns_per_task}")

    async def run_task(self, task_id: str) -> TaskResult:
        """Run a single AppWorld task through ALEC.

        Args:
            task_id: The AppWorld task ID to run.

        Returns:
            TaskResult with metrics and evaluation results.
        """
        start_time = time.time()
        session_id = ""
        iterations = 0
        tokens_used = 0
        bullets_used: dict[str, Any] = {}
        error_message: str | None = None
        test_results: dict[str, Any] | None = None
        task_description: str | None = None
        full_instruction: str | None = None  # Full instruction for learning
        final_response: str | None = None

        # Track test states and completion attempts
        test_states: dict[str, bool] = {}  # requirement string -> passed
        completion_attempts: list[str] = []  # Track answers from completion attempts

        # Loop detection disabled - variables kept for reference but unused
        # previous_codes: list[str] = []
        # consecutive_identical: int = 0
        # consecutive_errors: int = 0
        # last_error_type: str | None = None
        # no_progress_turns: int = 0
        # last_pass_count: int = 0

        try:
            # Initialize AppWorld environment for this task
            with AppWorld(
                task_id=task_id,
                experiment_name=self.experiment_name,
                raise_on_failure=False,  # Don't raise on API errors
            ) as world:
                # Extract task description (truncate to 150 chars for display, full for learning)
                if hasattr(world, 'task') and hasattr(world.task, 'instruction'):
                    instruction = world.task.instruction
                    task_description = instruction[:150] + "..." if len(instruction) > 150 else instruction
                    full_instruction = instruction  # Full instruction for embedding/learning

                # Build the prompt with task instruction and API docs
                initial_prompt = self._build_initial_prompt(world)

                async with ALECClient(base_url=self.alec_url) as client:
                    # Create ALEC session with the task
                    metadata = {
                        "experiment_name": self.experiment_name,
                    }
                    session_response = await client.create_session(
                        first_message=initial_prompt,
                        metadata=metadata,
                    )

                    session_id = session_response.get("session_id", "")
                    response_text = session_response.get("message", "")
                    tokens_used += self._extract_token_count(session_response)

                    # Collect bullets_used from each response (session API returns list of dicts)
                    all_bullets: list[dict[str, Any]] = []
                    turn_bullets = session_response.get("bullets_used", [])
                    seen_ids: set[str] = set()
                    for bullet in turn_bullets:
                        if isinstance(bullet, dict):
                            bullet_id = bullet.get("bullet_id", "")
                            if bullet_id and bullet_id not in seen_ids:
                                all_bullets.append({
                                    "bullet_id": bullet_id,
                                    "content": bullet.get("content", ""),
                                    "category": bullet.get("category", ""),
                                })
                                seen_ids.add(bullet_id)
                        elif isinstance(bullet, str) and bullet not in seen_ids:
                            all_bullets.append({
                                "bullet_id": bullet,
                                "content": "",
                                "category": "",
                            })
                            seen_ids.add(bullet)

                    # Conversation loop - turns_per_task controls limit
                    for iteration in range(self.turns_per_task):
                        iterations = iteration + 1

                        # Extract code from ALEC's response
                        code = self._extract_code(response_text)

                        # Loop detection disabled - let turns_per_task be the only limit

                        if not code:
                            # No code found, ask ALEC to provide code
                            logger.warning(
                                f"No code found in response for task {task_id}, iteration {iterations}"
                            )
                            response = await client.send_message(
                                session_id=session_id,
                                message="Please provide Python code to complete the task. "
                                "Use the apis and requester objects that are available.",
                            )
                            response_text = response.get("message", "")
                            tokens_used += self._extract_token_count(response)
                            # Collect bullets from this turn
                            for bullet in response.get("bullets_used", []):
                                if isinstance(bullet, dict):
                                    bullet_id = bullet.get("bullet_id", "")
                                    if bullet_id and bullet_id not in seen_ids:
                                        all_bullets.append({
                                            "bullet_id": bullet_id,
                                            "content": bullet.get("content", ""),
                                            "category": bullet.get("category", ""),
                                        })
                                        seen_ids.add(bullet_id)
                                elif isinstance(bullet, str) and bullet not in seen_ids:
                                    all_bullets.append({
                                        "bullet_id": bullet,
                                        "content": "",
                                        "category": "",
                                    })
                                    seen_ids.add(bullet)
                            continue

                        # Execute code in AppWorld
                        execution_result = world.execute(code)

                        # Check if task is completed AND ground truth passes
                        if world.task_completed():
                            # Verify with ground truth before breaking
                            test_tracker = world.evaluate(suppress_errors=True)

                            # Check for test state transitions and emit events
                            test_results_dict = test_tracker.to_dict(stats_only=False)
                            logger.info(f"Task {task_id} iteration {iterations}: test_results_dict = {test_results_dict}")

                            # Extract passes and failures from AppWorld schema
                            passes = test_results_dict.get("passes", [])
                            failures = test_results_dict.get("failures", [])

                            # Track test state transitions (for internal use only)
                            # NOTE: Event emission to Kafka removed as part of learning loop refactor
                            # Learning now extracts signals from conversation content, not direct events
                            for test_idx, pass_result in enumerate(passes):
                                req = pass_result.get("requirement", f"Test {test_idx + 1}")
                                test_states[req] = True

                            for test_idx, fail_result in enumerate(failures):
                                req = fail_result.get("requirement", f"Test {test_idx + 1}")
                                test_states[req] = False

                            # Loop detection disabled - let turns_per_task be the only limit

                            if test_tracker.success:
                                logger.info(
                                    f"Task {task_id} completed successfully after {iterations} iterations"
                                )
                                # Capture the successful response for bullet extraction
                                final_response = response_text
                                break

                            # Agent thinks done but ground truth failed - continue trying
                            # NOTE: We don't expose test details to ALEC (black-box principle)
                            logger.info(
                                f"Task {task_id}: Agent signaled done but ground truth failed, continuing..."
                            )

                            # Track completion attempt
                            completion_attempts.append(response_text[:200])

                            # Build feedback for completion attempt that failed ground truth
                            # Don't show "Task completed successfully!" as it contradicts the feedback
                            feedback_message = self._build_completion_retry_feedback(
                                iteration=iterations,
                                test_results=test_results_dict,
                                completion_attempts=len(completion_attempts)
                            )
                            response = await client.send_message(
                                session_id=session_id,
                                message=feedback_message,
                            )
                            response_text = response.get("message", "")
                            tokens_used += self._extract_token_count(response)
                            # Collect bullets from this turn
                            for bullet in response.get("bullets_used", []):
                                if isinstance(bullet, dict):
                                    bullet_id = bullet.get("bullet_id", "")
                                    if bullet_id and bullet_id not in seen_ids:
                                        all_bullets.append({
                                            "bullet_id": bullet_id,
                                            "content": bullet.get("content", ""),
                                            "category": bullet.get("category", ""),
                                        })
                                        seen_ids.add(bullet_id)
                                elif isinstance(bullet, str) and bullet not in seen_ids:
                                    all_bullets.append({
                                        "bullet_id": bullet,
                                        "content": "",
                                        "category": "",
                                    })
                                    seen_ids.add(bullet)
                            continue

                        # Check if execution was successful (no error)
                        if self._is_execution_successful(execution_result):
                            # Successful execution but task not complete
                            # NOTE: Don't run ground truth here - no test internals exposed
                            feedback_message = self._build_success_feedback(
                                execution_result,
                                iteration + 1
                            )
                            response = await client.send_message(
                                session_id=session_id,
                                message=feedback_message,
                            )
                            response_text = response.get("message", "")
                            tokens_used += self._extract_token_count(response)
                            # Collect bullets from this turn
                            for bullet in response.get("bullets_used", []):
                                if isinstance(bullet, dict):
                                    bullet_id = bullet.get("bullet_id", "")
                                    if bullet_id and bullet_id not in seen_ids:
                                        all_bullets.append({
                                            "bullet_id": bullet_id,
                                            "content": bullet.get("content", ""),
                                            "category": bullet.get("category", ""),
                                        })
                                        seen_ids.add(bullet_id)
                                elif isinstance(bullet, str) and bullet not in seen_ids:
                                    all_bullets.append({
                                        "bullet_id": bullet,
                                        "content": "",
                                        "category": "",
                                    })
                                    seen_ids.add(bullet)
                        else:
                            # Execution failed - send error feedback to ALEC for retry
                            # Loop detection disabled - let turns_per_task be the only limit
                            error_feedback = self._build_error_feedback(
                                execution_result, iteration + 1
                            )
                            response = await client.send_message(
                                session_id=session_id,
                                message=error_feedback,
                            )
                            response_text = response.get("message", "")
                            tokens_used += self._extract_token_count(response)
                            # Collect bullets from this turn
                            for bullet in response.get("bullets_used", []):
                                if isinstance(bullet, dict):
                                    bullet_id = bullet.get("bullet_id", "")
                                    if bullet_id and bullet_id not in seen_ids:
                                        all_bullets.append({
                                            "bullet_id": bullet_id,
                                            "content": bullet.get("content", ""),
                                            "category": bullet.get("category", ""),
                                        })
                                        seen_ids.add(bullet_id)
                                elif isinstance(bullet, str) and bullet not in seen_ids:
                                    all_bullets.append({
                                        "bullet_id": bullet,
                                        "content": "",
                                        "category": "",
                                    })
                                    seen_ids.add(bullet)

                    # Store all collected bullets from all turns
                    # Structure: list of dicts with bullet_id, content, and category
                    bullets_used = all_bullets

                # Evaluate task results using AppWorld ground truth
                test_tracker = world.evaluate(suppress_errors=True)
                test_results = test_tracker.to_dict(stats_only=False)
                success = test_tracker.success

        except ALECClientError as e:
            error_message = f"ALEC client error: {str(e)}"
            logger.error(f"Task {task_id} failed: {error_message}")
            success = False
        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
            logger.error(f"Task {task_id} failed: {error_message}")
            success = False

        duration_ms = int((time.time() - start_time) * 1000)

        return TaskResult(
            task_id=task_id,
            session_id=session_id,
            success=success,
            iterations=iterations,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            bullets_used=bullets_used,
            error_message=error_message,
            test_results=test_results,
            task_description=task_description,
            full_instruction=full_instruction,
            final_response=final_response,
        )

    def _build_initial_prompt(self, world: AppWorld) -> str:
        """Build the initial prompt with task instruction and API documentation.

        Args:
            world: The AppWorld instance for the task.

        Returns:
            The formatted prompt string.
        """
        task = world.task

        # Build API documentation summary
        app_names = list(task.app_descriptions.keys())
        api_docs_str = self._format_api_docs(task.api_docs, app_names)

        # Build app descriptions
        app_descriptions = "\n".join(
            f"- {app}: {desc}" for app, desc in task.app_descriptions.items()
        )

        prompt = f"""You are an AI agent that completes tasks by writing Python code.

## Task
{task.instruction}

## User Information
- Name: {task.supervisor.first_name} {task.supervisor.last_name}
- Email: {task.supervisor.email}
- Phone: {task.supervisor.phone_number}

## Available Apps
{app_descriptions}

## API Documentation
{api_docs_str}

## Available Objects
You have access to:
- `apis`: An ApiCollection object for making API calls
- `requester`: A Requester object for lower-level API requests

## Authentication Pattern
Most APIs require authentication. Use the Supervisor app to get passwords:

```python
# Step 1: Get passwords from Supervisor (returns a LIST of account dicts)
passwords = requester.request("supervisor", "show_account_passwords")
# Returns: [{{"account_name": "spotify", "password": "xyz"}}, {{"account_name": "gmail", "password": "abc"}}, ...]

# Step 2: Find the password for your target app
app_password = next(
    (p["password"] for p in passwords if p["account_name"] == "app_name"),
    None
)

# Step 3: Login to get access token
auth_response = requester.request("app_name", "login",
    email="user_email", password=app_password)
access_token = auth_response["access_token"]

# Step 4: Use token in subsequent requests
result = requester.request("app_name", "api_name",
    access_token=access_token, **other_params)
```

**Important:** The passwords endpoint returns a LIST of dicts with "account_name" and "password" keys. Iterate to find the correct app.

## Signaling Task Completion

When your code successfully completes the task, you must signal completion:

1. **For tasks that produce an answer** (e.g., "How many songs?", "What is the total?"):
   ```python
   apis.supervisor.complete_task(answer=your_answer)
   ```

2. **For tasks that perform an action** (e.g., "Delete the playlist", "Send a message"):
   ```python
   apis.supervisor.complete_task()
   ```

**Important:** Only call `complete_task()` when you believe the task is fully complete. If your solution is incorrect, you'll receive feedback about which requirements aren't met and can provide corrected code.

## Instructions
1. Write Python code to complete the task
2. Use the requester to call APIs: `requester.request(app_name, api_name, **params)`
3. Always authenticate first using the pattern above - get password from Supervisor, then login
4. Print relevant results for verification
5. Handle errors appropriately
6. Call `apis.supervisor.complete_task()` when done (with `answer=` if the task asks for a value)

Provide your code in a Python code block like:
```python
# Your code here
```
"""
        return prompt

    def _format_api_docs(self, api_docs: Any, app_names: list[str]) -> str:
        """Format API documentation for the prompt.

        Args:
            api_docs: The API documentation collection.
            app_names: List of app names to document.

        Returns:
            Formatted API docs string.
        """
        docs_parts = []

        # api_docs is an ApiDocCollection - access by app name
        for app_name in app_names:
            app_docs = api_docs.get(app_name)
            docs_parts.append(f"\n### {app_name}")

            # app_docs is a Munch dict: {api_name: api_doc}
            for api_name, api_doc in app_docs.items():
                params_str = ", ".join(
                    f"{p['name']}: {p['type']}" + (f" = {p['default']}" if p.get('default') else "")
                    for p in api_doc.get("parameters", [])
                )
                docs_parts.append(
                    f"- **{api_doc['api_name']}**({params_str}): {api_doc['description']}"
                )

        return "\n".join(docs_parts)

    def _extract_code(self, response: str) -> str:
        """Extract Python code from ALEC's response.

        Args:
            response: The LLM response text.

        Returns:
            Extracted Python code or empty string if not found.
        """
        # Look for code blocks with flexible whitespace handling
        patterns = [
            r"```python\s*\n(.*?)```",  # Python code block (allow trailing whitespace)
            r"```\s*python\s*\n(.*?)```",  # Flexible python marker (space before/after)
            r"```\n(.*?)```",  # Generic code block
        ]

        for pattern in patterns:
            matches = re.findall(pattern, response, re.DOTALL)
            if matches:
                # Return the last code block (most likely the complete solution)
                return matches[-1].strip()

        return ""

    def _is_execution_successful(self, result: str) -> bool:
        """Check if execution was successful.

        Args:
            result: The execution result string.

        Returns:
            True if successful, False if error occurred.
        """
        return not result.startswith("Execution failed.")

    def _is_code_identical_to_previous(self, code: str, previous_codes: list[str]) -> bool:
        """Check if code is identical to the last submission (whitespace-normalized).

        Args:
            code: Current code submission.
            previous_codes: List of previous code submissions.

        Returns:
            True if identical to last submission, False otherwise.
        """
        if not previous_codes:
            return False
        # Normalize whitespace for comparison
        current = re.sub(r'\s+', ' ', code).strip()
        last = re.sub(r'\s+', ' ', previous_codes[-1]).strip()
        return current == last

    def _extract_error_type(self, execution_result: str) -> str | None:
        """Extract error type from execution result.

        Looks for common Python error patterns like 'KeyError', 'TypeError', etc.

        Args:
            execution_result: The execution result string.

        Returns:
            Error type string if found, None otherwise.
        """
        if not execution_result:
            return None
        lines = execution_result.strip().split('\n')
        for line in lines:
            # Look for Python exception patterns
            if 'Error' in line or 'Exception' in line:
                # Return first 100 chars of error line for comparison
                return line.strip()[:100]
        # Fall back to first line if no error pattern found
        return lines[0][:100] if lines else None

    def _build_success_feedback(self, result: str, iteration: int) -> str:
        """Build feedback message for successful execution.

        Args:
            result: The execution result.
            iteration: Current iteration number.

        Returns:
            Feedback message for ALEC.
        """
        return f"""## Execution Result (Iteration {iteration})

The code executed successfully:

```
{result}
```

The task is not yet complete. Please continue with the next step to complete the task.
Provide your code in a Python code block.
"""

    def _build_completion_retry_feedback(
        self,
        iteration: int,
        test_results: dict[str, Any],
        completion_attempts: int
    ) -> str:
        """Build feedback when agent signals completion but ground truth fails.

        Per black-box principle: don't reveal expected answers, but show which tests
        are passing/failing to help agent focus debugging effort.

        Args:
            iteration: Current iteration number.
            test_results: Test results from AppWorld evaluation.
            completion_attempts: Number of completion attempts so far.

        Returns:
            Feedback message for ALEC.
        """
        feedback_parts = [f"## Execution Result (Iteration {iteration})", ""]

        # Extract test status from AppWorld schema: passes/failures lists
        passes = test_results.get("passes", [])
        failures = test_results.get("failures", [])
        num_tests = test_results.get("num_tests", len(passes) + len(failures))
        num_passed = len(passes)
        num_failed = len(failures)

        # If we don't have test results, provide generic feedback
        if num_tests == 0:
            logger.warning(f"Iteration {iteration}: test_results has no tests: {test_results}")
            feedback_parts.append("You called complete_task(), but the task is not yet complete.")
            feedback_parts.append("")
            feedback_parts.append("The task verification failed. Please review your code and try again.")
        else:
            feedback_parts.append(f"You called complete_task(), but {num_failed}/{num_tests} tests are still failing.")
            feedback_parts.append("")
            feedback_parts.append("**Test Results:**")

            # Build unified test list from passes and failures
            all_tests = [
                {"passed": True, "requirement": p.get("requirement", f"Test {i+1}")}
                for i, p in enumerate(passes)
            ] + [
                {"passed": False, "requirement": f.get("requirement", f"Test {len(passes)+i+1}"), "trace": f.get("trace", "")}
                for i, f in enumerate(failures)
            ]

            # Show per-test status with full assertion trace for debugging
            # (AppWorld's official evaluator shows both values - this is benchmark-compliant)
            for test_idx, test_result in enumerate(all_tests):
                test_num = test_idx + 1
                test_passed = test_result["passed"]
                status_icon = "✓ PASSED" if test_passed else "✗ FAILED"

                # Get test description from requirement field
                test_name = test_result.get("requirement", f"Test {test_num}")
                if len(test_name) > 100:
                    test_name = test_name[:100] + "..."

                feedback_parts.append(f"- Test {test_num}/{num_tests}: {status_icon}")
                if not test_passed:
                    if test_name:
                        feedback_parts.append(f"  Description: {test_name}")
                    # Show full assertion trace to enable debugging
                    trace = test_result.get("trace", "")
                    if trace:
                        feedback_parts.append(f"  Trace: {trace}")

        feedback_parts.append("")

        # Add hints based on completion attempts
        if completion_attempts >= 3:
            feedback_parts.append(f"**Note**: This is attempt #{completion_attempts} at completion.")
            feedback_parts.append("Consider:")
            feedback_parts.append("- Are you computing the right metric or value?")
            feedback_parts.append("- Are you using the correct data source?")
            feedback_parts.append("- Are you handling all required cases?")
            feedback_parts.append("")

        feedback_parts.append("Please analyze the failing tests and provide corrected code in a Python code block.")

        return "\n".join(feedback_parts)

    # NOTE: _emit_test_passed_event and _emit_test_failed_event methods REMOVED
    # as part of learning loop refactor. Learning now extracts signals from
    # conversation content, not direct Kafka events. This ensures ALEC learns
    # only from signals visible in the message thread (Agent0 principle).

    def _build_error_feedback(self, error: str, iteration: int) -> str:
        """Build feedback message for failed execution.

        Args:
            error: The error message from execution.
            iteration: Current iteration number (unused, kept for API compatibility).

        Returns:
            Error feedback message for ALEC.
        """
        # NOTE: Don't expose iteration counts or remaining turns to ALEC (black-box principle)
        return f"""## Execution Error

{error}

Please analyze the error and provide corrected Python code to complete the task.
Make sure to:
1. Fix the issue that caused the error
2. Use proper API parameters
3. Handle authentication if needed (use Supervisor to get passwords)

Provide your corrected code in a Python code block.
"""

    def _extract_token_count(self, response: dict[str, Any]) -> int:
        """Extract token count from response.

        Args:
            response: The API response.

        Returns:
            Number of tokens used.
        """
        # Check for token_usage field (ALEC session service format)
        token_usage = response.get("token_usage", {})
        if token_usage:
            return token_usage.get("total_tokens", 0)

        # Check for usage field (alternative format)
        usage = response.get("usage", {})
        if usage:
            return usage.get("total_tokens", 0)

        # Check for token_count field (legacy format)
        return response.get("token_count", 0)
