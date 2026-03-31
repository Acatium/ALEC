-- Example Queries for Evaluation Task Outcomes Analysis
-- Phase 0.4: Evaluation-Side Tracking

-- =============================================================================
-- Example 1: Overall Success Rate by Experiment
-- =============================================================================
-- Shows top-level metrics for each experiment
SELECT
    e.name,
    e.experiment_type,
    e.dataset_split,
    COUNT(o.outcome_id) as total_tasks,
    SUM(CASE WHEN o.success THEN 1 ELSE 0 END) as successful_tasks,
    ROUND(AVG(CASE WHEN o.success THEN 1.0 ELSE 0.0 END) * 100, 2) as success_rate_pct,
    ROUND(AVG(o.total_turns), 1) as avg_total_turns,
    ROUND(AVG(CASE WHEN o.success THEN o.turns_to_success ELSE NULL END), 1) as avg_turns_when_successful
FROM evaluation_experiments e
LEFT JOIN evaluation_task_outcomes o ON e.id = o.experiment_id
WHERE e.status = 'completed'
GROUP BY e.id, e.name, e.experiment_type, e.dataset_split
ORDER BY e.started_at DESC;

-- =============================================================================
-- Example 2: Cross-Session Learning Evidence
-- =============================================================================
-- Compares first variant vs. later variants to measure learning
-- Shows if ALEC learns from previous attempts on similar problems
SELECT
    problem_signature,
    total_variants,
    ROUND((first_variant_success_rate * 100)::numeric, 0) || '%' as first_success,
    ROUND((later_variant_success_rate * 100)::numeric, 0) || '%' as later_success,
    ROUND((later_variant_success_rate - first_variant_success_rate) * 100, 0) as improvement_pct,
    ROUND(first_variant_avg_turns::numeric, 1) as first_turns,
    ROUND(later_variant_avg_turns::numeric, 1) as later_turns
FROM cross_session_learning_analysis
WHERE experiment_id = '<EXPERIMENT_ID>'  -- Replace with actual experiment ID
ORDER BY improvement_pct DESC;

-- =============================================================================
-- Example 3: Learning Curve Over Time
-- =============================================================================
-- Shows success rate evolution as experiment progresses
-- Rolling average smooths out variance
SELECT
    task_sequence,
    task_id,
    CASE WHEN success THEN '✓' ELSE '✗' END as result,
    COALESCE(turns_to_success, total_turns) as turns,
    ROUND(rolling_success_rate_10::numeric, 2) as rolling_avg_10_tasks
FROM learning_curve_view
WHERE experiment_id = '<EXPERIMENT_ID>'  -- Replace with actual experiment ID
ORDER BY task_sequence;

-- =============================================================================
-- Example 4: Problem Difficulty Analysis
-- =============================================================================
-- Identifies hardest problems (lowest success rate, highest turns)
SELECT
    problem_signature,
    total_variants,
    successful_variants,
    ROUND(success_rate_pct, 1) as success_rate_pct,
    ROUND(avg_total_turns, 1) as avg_total_turns,
    ROUND(avg_turns_when_successful, 1) as avg_turns_successful
FROM problem_signature_performance
WHERE experiment_id = '<EXPERIMENT_ID>'  -- Replace with actual experiment ID
ORDER BY success_rate_pct ASC, avg_total_turns DESC
LIMIT 20;

-- =============================================================================
-- Example 5: Failure Analysis
-- =============================================================================
-- Examines failed tasks to identify patterns
SELECT
    o.task_id,
    o.problem_signature,
    o.total_turns,
    o.execution_log->'test_results'->>'num_tests' as total_tests,
    jsonb_array_length(COALESCE(o.execution_log->'test_results'->'passes', '[]'::jsonb)) as tests_passed,
    o.execution_log->>'error_message' as error_message
FROM evaluation_task_outcomes o
WHERE o.experiment_id = '<EXPERIMENT_ID>'  -- Replace with actual experiment ID
  AND o.success = false
ORDER BY o.total_turns DESC;

-- =============================================================================
-- Example 6: Variant Performance Comparison
-- =============================================================================
-- Compares performance across variants of the same problem
SELECT
    o.problem_signature,
    o.task_id,
    o.success,
    o.turns_to_success,
    o.total_turns,
    ROW_NUMBER() OVER (PARTITION BY o.problem_signature ORDER BY o.created_at) as variant_order
FROM evaluation_task_outcomes o
WHERE o.experiment_id = '<EXPERIMENT_ID>'  -- Replace with actual experiment ID
  AND o.problem_signature IN (
      -- Find problems with multiple variants
      SELECT problem_signature
      FROM evaluation_task_outcomes
      WHERE experiment_id = '<EXPERIMENT_ID>'
      GROUP BY problem_signature
      HAVING COUNT(*) > 1
  )
ORDER BY o.problem_signature, variant_order;

-- =============================================================================
-- Example 7: Experiment Comparison (A/B Testing)
-- =============================================================================
-- Compares metrics across experiments (e.g., baseline vs. learning enabled)
-- Note: Learning is now controlled via /agents service toggles, not learning_mode
SELECT
    e.name,
    e.experiment_type,
    COUNT(o.outcome_id) as total_tasks,
    ROUND(AVG(CASE WHEN o.success THEN 1.0 ELSE 0.0 END) * 100, 2) as success_rate_pct,
    ROUND(AVG(o.total_turns), 1) as avg_total_turns,
    ROUND(AVG(CASE WHEN o.success THEN o.turns_to_success ELSE NULL END), 1) as avg_turns_successful
FROM evaluation_experiments e
LEFT JOIN evaluation_task_outcomes o ON e.id = o.experiment_id
WHERE e.dataset_split = 'test_normal'  -- Compare same dataset
  AND e.status = 'completed'
GROUP BY e.id, e.name, e.experiment_type
ORDER BY success_rate_pct DESC;

-- =============================================================================
-- Example 8: Session-Level Details
-- =============================================================================
-- Retrieves full execution history for a specific task
SELECT
    o.task_id,
    o.session_id,
    o.success,
    o.turns_to_success,
    o.total_turns,
    o.problem_signature,
    o.execution_log,
    o.created_at
FROM evaluation_task_outcomes o
WHERE o.task_id = '<TASK_ID>'  -- Replace with specific task ID
ORDER BY o.created_at DESC;

-- =============================================================================
-- Example 9: Efficiency Metrics
-- =============================================================================
-- Measures how efficiently ALEC solves problems (turns vs. success)
SELECT
    CASE
        WHEN o.total_turns <= 3 THEN '1-3 turns'
        WHEN o.total_turns <= 5 THEN '4-5 turns'
        WHEN o.total_turns <= 7 THEN '6-7 turns'
        WHEN o.total_turns <= 10 THEN '8-10 turns'
        ELSE '10+ turns'
    END as turn_bucket,
    COUNT(*) as task_count,
    SUM(CASE WHEN o.success THEN 1 ELSE 0 END) as successful_count,
    ROUND(AVG(CASE WHEN o.success THEN 1.0 ELSE 0.0 END) * 100, 2) as success_rate_pct
FROM evaluation_task_outcomes o
WHERE o.experiment_id = '<EXPERIMENT_ID>'  -- Replace with actual experiment ID
GROUP BY turn_bucket
ORDER BY MIN(o.total_turns);
