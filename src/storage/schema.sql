CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_name TEXT,
    action_type TEXT,
    dataset_accessed TEXT,
    tool_called TEXT,
    input_summary TEXT,
    output_summary TEXT,
    triggered_policies TEXT,
    policy_decision TEXT,
    risk_score INTEGER,
    risk_level TEXT,
    approval_status TEXT,
    source_files TEXT,
    final_decision TEXT
);

CREATE TABLE IF NOT EXISTS approval_queue (
    approval_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    approval_required INTEGER,
    approval_status TEXT,
    requested_by_agent TEXT,
    reviewer_role TEXT,
    action_under_review TEXT,
    decision_options TEXT,
    created_at TEXT,
    decision_at TEXT,
    reviewer_comments TEXT
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    user_query TEXT,
    user_role TEXT,
    product_id TEXT,
    product_name TEXT,
    region TEXT,
    intent TEXT,
    final_decision TEXT,
    created_at TEXT,
    completed_at TEXT
);