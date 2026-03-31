"""LLM prompts for ADVISOR service.

ADVISOR uses a single LLM call per session (turn 1) to normalize
the task description into a "When [X]..." format that matches
how bullets are stored.
"""

TASK_TO_SITUATION_SYSTEM = """Convert the task description into a general situation statement.

Output format: "When [general problem description]"

Guidelines:
- Keep it abstract (no specific names, IDs, or app-specific details)
- Focus on the TYPE of problem, not the specific instance
- One sentence only, starting with "When"

Examples:
- Task: "Reset friends on venmo to be the same as my friends in my phone"
  Output: When synchronizing contacts between payment and communication apps

- Task: "Find the least played song by my favorite artist on Spotify"
  Output: When finding items with minimum values from a filtered music collection

- Task: "Delete all emails from john@example.com older than 30 days"
  Output: When filtering and removing messages based on sender and date criteria

- Task: "Calculate the total cost of all orders placed last month"
  Output: When aggregating financial data across time-filtered records
"""

TASK_TO_SITUATION_USER = """Task: {task_text}

Output the situation statement:"""
