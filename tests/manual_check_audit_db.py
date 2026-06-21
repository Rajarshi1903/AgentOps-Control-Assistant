import sqlite3
from pathlib import Path

db_path = Path("data/audit_logs.db")

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

rows = conn.execute(
    """
    SELECT
        event_id,
        run_id,
        timestamp,
        final_decision,
        policy_decision,
        risk_score,
        risk_level,
        approval_required,
        approval_status
    FROM audit_events
    ORDER BY timestamp DESC
    LIMIT 10;
    """
).fetchall()

for row in rows:
    print(dict(row))

conn.close()