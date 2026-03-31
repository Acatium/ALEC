-- A/B Testing Framework Tables
-- Phase 2: Support for designing, executing, and analyzing A/B tests

-- ============================================================================
-- Test Designs
-- ============================================================================

CREATE TABLE IF NOT EXISTS ab_test_designs (
    test_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Task assignments
    control_task_ids TEXT[] NOT NULL,
    treatment_task_ids TEXT[] NOT NULL,

    -- Experiment configurations
    control_config JSONB NOT NULL,
    treatment_config JSONB NOT NULL,

    -- Sample size planning
    planned_sample_size_per_group INTEGER,
    expected_baseline_rate NUMERIC(5, 4),
    minimum_detectable_effect NUMERIC(5, 4),
    target_alpha NUMERIC(5, 4) DEFAULT 0.05,
    target_power NUMERIC(5, 4) DEFAULT 0.80,

    -- Stratification metadata
    stratification_method VARCHAR(50),  -- 'stratified', 'blocked', 'sequential'
    stratification_seed INTEGER,
    domain_distribution JSONB,  -- {'control': {...}, 'treatment': {...}}
    balance_score NUMERIC(5, 4),

    -- Status tracking
    status VARCHAR(50) DEFAULT 'planned',  -- 'planned', 'running', 'completed', 'cancelled'
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_by VARCHAR(100)
);

CREATE INDEX idx_ab_test_designs_status ON ab_test_designs(status);
CREATE INDEX idx_ab_test_designs_created_at ON ab_test_designs(created_at DESC);

COMMENT ON TABLE ab_test_designs IS 'A/B test experimental designs with task assignments and configurations';
COMMENT ON COLUMN ab_test_designs.control_task_ids IS 'Array of task IDs assigned to control group';
COMMENT ON COLUMN ab_test_designs.treatment_task_ids IS 'Array of task IDs assigned to treatment group';
COMMENT ON COLUMN ab_test_designs.control_config IS 'Configuration for control experiment (task_limit, turns_per_task, etc)';
COMMENT ON COLUMN ab_test_designs.treatment_config IS 'Configuration for treatment experiment';
COMMENT ON COLUMN ab_test_designs.balance_score IS 'Domain balance score (1.0 = perfect balance)';


-- ============================================================================
-- Test Results
-- ============================================================================

CREATE TABLE IF NOT EXISTS ab_test_results (
    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id UUID NOT NULL REFERENCES ab_test_designs(test_id) ON DELETE CASCADE,

    -- Linked experiments
    control_experiment_id UUID,  -- References evaluation_experiments(experiment_id)
    treatment_experiment_id UUID,

    -- Sample sizes and outcomes
    n_control INTEGER NOT NULL,
    n_treatment INTEGER NOT NULL,
    control_successes INTEGER NOT NULL,
    control_success_rate NUMERIC(5, 4) NOT NULL,
    treatment_successes INTEGER NOT NULL,
    treatment_success_rate NUMERIC(5, 4) NOT NULL,

    -- Statistical tests
    bootstrap_ci_lower NUMERIC(6, 5),
    bootstrap_ci_upper NUMERIC(6, 5),
    bootstrap_p_value NUMERIC(10, 9),
    fishers_p_value NUMERIC(10, 9),
    fishers_interpretation VARCHAR(50),

    -- Paired analysis (if applicable)
    mcnemar_p_value NUMERIC(10, 9),
    mcnemar_interpretation VARCHAR(50),
    success_both INTEGER,
    success_control_only INTEGER,
    success_treatment_only INTEGER,
    failure_both INTEGER,

    -- Effect sizes
    cohens_h NUMERIC(6, 5),
    cohens_h_interpretation VARCHAR(50),
    odds_ratio NUMERIC(8, 4),
    odds_ratio_ci_lower NUMERIC(8, 4),
    odds_ratio_ci_upper NUMERIC(8, 4),
    relative_risk NUMERIC(8, 4),
    relative_risk_ci_lower NUMERIC(8, 4),
    relative_risk_ci_upper NUMERIC(8, 4),

    -- Secondary metrics
    median_iterations_control NUMERIC(6, 2),
    median_iterations_treatment NUMERIC(6, 2),
    iterations_ci_lower NUMERIC(6, 2),
    iterations_ci_upper NUMERIC(6, 2),
    iterations_p_value NUMERIC(10, 9),

    -- Full statistical analysis (JSON for flexibility)
    statistical_analysis JSONB,

    -- Conclusions
    conclusion TEXT NOT NULL,
    recommendation TEXT NOT NULL,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    analyzed_by VARCHAR(100)
);

CREATE INDEX idx_ab_test_results_test_id ON ab_test_results(test_id);
CREATE INDEX idx_ab_test_results_created_at ON ab_test_results(created_at DESC);
CREATE INDEX idx_ab_test_results_bootstrap_p ON ab_test_results(bootstrap_p_value);

COMMENT ON TABLE ab_test_results IS 'Statistical analysis results for A/B tests';
COMMENT ON COLUMN ab_test_results.bootstrap_ci_lower IS 'Lower bound of 95% CI for treatment - control difference';
COMMENT ON COLUMN ab_test_results.bootstrap_ci_upper IS 'Upper bound of 95% CI for treatment - control difference';
COMMENT ON COLUMN ab_test_results.cohens_h IS 'Cohen''s h effect size for proportion difference';
COMMENT ON COLUMN ab_test_results.statistical_analysis IS 'Full statistical analysis including raw outcomes, task-level data';


-- ============================================================================
-- Task-Level Results (for detailed analysis)
-- ============================================================================

CREATE TABLE IF NOT EXISTS ab_test_task_results (
    task_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id UUID NOT NULL REFERENCES ab_test_results(result_id) ON DELETE CASCADE,

    task_id VARCHAR(100) NOT NULL,
    task_domain VARCHAR(100),
    group_assignment VARCHAR(20) NOT NULL,  -- 'control' or 'treatment'

    -- Outcome
    success BOOLEAN NOT NULL,
    iterations INTEGER,
    tokens_used INTEGER,
    duration_ms INTEGER,

    -- Bullets used (for learning analysis)
    bullets_used JSONB,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_ab_test_task_results_result_id ON ab_test_task_results(result_id);
CREATE INDEX idx_ab_test_task_results_task_id ON ab_test_task_results(task_id);
CREATE INDEX idx_ab_test_task_results_group ON ab_test_task_results(group_assignment);
CREATE INDEX idx_ab_test_task_results_success ON ab_test_task_results(success);

COMMENT ON TABLE ab_test_task_results IS 'Task-level results for A/B tests enabling detailed analysis';
COMMENT ON COLUMN ab_test_task_results.group_assignment IS 'Whether task was in control or treatment group';


-- ============================================================================
-- Views for Analysis
-- ============================================================================

-- Summary of all A/B tests
CREATE OR REPLACE VIEW ab_test_summary AS
SELECT
    d.test_id,
    d.name,
    d.description,
    d.status,
    d.created_at,
    d.completed_at,

    -- Sample sizes
    COALESCE(array_length(d.control_task_ids, 1), 0) AS n_control_tasks,
    COALESCE(array_length(d.treatment_task_ids, 1), 0) AS n_treatment_tasks,

    -- Planning metrics
    d.expected_baseline_rate,
    d.minimum_detectable_effect,
    d.target_alpha,
    d.target_power,
    d.balance_score,

    -- Results (if completed)
    r.control_success_rate,
    r.treatment_success_rate,
    r.treatment_success_rate - r.control_success_rate AS rate_difference,
    r.bootstrap_p_value,
    r.cohens_h,
    r.cohens_h_interpretation,
    r.conclusion,
    r.recommendation
FROM ab_test_designs d
LEFT JOIN ab_test_results r ON d.test_id = r.test_id
ORDER BY d.created_at DESC;

COMMENT ON VIEW ab_test_summary IS 'Summary view of all A/B tests with key metrics';


-- Domain-level analysis
CREATE OR REPLACE VIEW ab_test_domain_analysis AS
SELECT
    tr.result_id,
    d.name AS test_name,
    tr.task_domain,
    tr.group_assignment,

    COUNT(*) AS n_tasks,
    SUM(CASE WHEN tr.success THEN 1 ELSE 0 END) AS n_successes,
    AVG(CASE WHEN tr.success THEN 1.0 ELSE 0.0 END) AS success_rate,
    AVG(tr.iterations) AS avg_iterations,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY tr.iterations) AS median_iterations
FROM ab_test_task_results tr
JOIN ab_test_results r ON tr.result_id = r.result_id
JOIN ab_test_designs d ON r.test_id = d.test_id
WHERE tr.task_domain IS NOT NULL
GROUP BY tr.result_id, d.name, tr.task_domain, tr.group_assignment
ORDER BY test_name, task_domain, group_assignment;

COMMENT ON VIEW ab_test_domain_analysis IS 'Domain-stratified analysis of A/B test results';


-- Significant tests (p < 0.05)
CREATE OR REPLACE VIEW ab_test_significant_results AS
SELECT
    d.test_id,
    d.name,
    d.created_at,

    r.n_control,
    r.n_treatment,
    r.control_success_rate,
    r.treatment_success_rate,
    r.treatment_success_rate - r.control_success_rate AS rate_difference,

    r.bootstrap_p_value,
    r.fishers_p_value,
    r.cohens_h,
    r.cohens_h_interpretation,
    r.odds_ratio,
    r.relative_risk,

    r.conclusion,
    r.recommendation
FROM ab_test_designs d
JOIN ab_test_results r ON d.test_id = r.test_id
WHERE r.bootstrap_p_value < 0.05
ORDER BY r.bootstrap_p_value ASC;

COMMENT ON VIEW ab_test_significant_results IS 'A/B tests with statistically significant results (p < 0.05)';


-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to validate test design balance
CREATE OR REPLACE FUNCTION check_ab_test_balance(
    p_test_id UUID
) RETURNS TABLE (
    domain TEXT,
    n_control BIGINT,
    n_treatment BIGINT,
    balance_ratio NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH task_assignments AS (
        SELECT
            unnest(control_task_ids) AS task_id,
            'control' AS group_type
        FROM ab_test_designs
        WHERE test_id = p_test_id

        UNION ALL

        SELECT
            unnest(treatment_task_ids) AS task_id,
            'treatment' AS group_type
        FROM ab_test_designs
        WHERE test_id = p_test_id
    ),
    domain_counts AS (
        SELECT
            ta.group_type,
            tr.task_domain AS domain,
            COUNT(*) AS n_tasks
        FROM task_assignments ta
        LEFT JOIN ab_test_task_results tr ON ta.task_id = tr.task_id
        WHERE tr.task_domain IS NOT NULL
        GROUP BY ta.group_type, tr.task_domain
    )
    SELECT
        dc_control.domain::TEXT,
        dc_control.n_tasks,
        COALESCE(dc_treatment.n_tasks, 0),
        CASE
            WHEN dc_control.n_tasks = 0 THEN NULL
            ELSE ROUND(
                LEAST(dc_control.n_tasks, COALESCE(dc_treatment.n_tasks, 0))::NUMERIC /
                GREATEST(dc_control.n_tasks, COALESCE(dc_treatment.n_tasks, 0))::NUMERIC,
                4
            )
        END AS balance_ratio
    FROM domain_counts dc_control
    LEFT JOIN domain_counts dc_treatment
        ON dc_control.domain = dc_treatment.domain
        AND dc_treatment.group_type = 'treatment'
    WHERE dc_control.group_type = 'control'
    ORDER BY dc_control.domain;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION check_ab_test_balance IS 'Check domain balance for A/B test design (1.0 = perfect balance)';
