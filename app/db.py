"""
Persistence layer. Two tables:
  - beliefs: Beta distribution parameters per (category, action) pair,
    persisted across rounds so the agent actually gets better over time.
  - audit_log: full decision trail per transaction per round.
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "recovery_agent.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS beliefs (
            category TEXT NOT NULL,
            action TEXT NOT NULL,
            alpha REAL NOT NULL DEFAULT 1.0,
            beta REAL NOT NULL DEFAULT 1.0,
            PRIMARY KEY (category, action)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round INTEGER NOT NULL,
            transaction_id TEXT,
            customer_id TEXT,
            amount REAL,
            failure_reason TEXT,
            category TEXT,
            chosen_action TEXT,
            evidence TEXT,
            candidates_considered TEXT,
            expected_outcome TEXT,
            actual_outcome TEXT,
            recovered_amount REAL,
            blocked_by_safety_limit INTEGER,
            safety_reason TEXT,
            explanation TEXT,
            belief_update TEXT,
            timestamp TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_contacts (
            customer_id TEXT,
            date TEXT,
            contact_count INTEGER DEFAULT 0,
            PRIMARY KEY (customer_id, date)
        )
    """)
    conn.commit()
    conn.close()


def get_belief(category, action):
    conn = get_conn()
    row = conn.execute(
        "SELECT alpha, beta FROM beliefs WHERE category=? AND action=?",
        (category, action),
    ).fetchone()
    conn.close()
    if row is None:
        return 1.0, 1.0  # uninformed Beta(1,1) prior
    return row["alpha"], row["beta"]


def update_belief(category, action, success: bool):
    alpha, beta = get_belief(category, action)
    if success:
        alpha += 1
    else:
        beta += 1
    conn = get_conn()
    conn.execute(
        """INSERT INTO beliefs (category, action, alpha, beta) VALUES (?, ?, ?, ?)
           ON CONFLICT(category, action) DO UPDATE SET alpha=excluded.alpha, beta=excluded.beta""",
        (category, action, alpha, beta),
    )
    conn.commit()
    conn.close()
    return alpha, beta


def get_all_beliefs():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM beliefs").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_transactions():
    conn = get_conn()
    rows = conn.execute("""
        SELECT transaction_id, customer_id, amount, failure_reason, category,
               chosen_action, actual_outcome, recovered_amount, round,
               blocked_by_safety_limit, safety_reason, explanation, timestamp
        FROM audit_log
        ORDER BY round DESC, id DESC
    """).fetchall()
    conn.close()
    transactions = []
    for row in rows:
        transaction = dict(row)
        transaction["blocked_by_safety_limit"] = bool(transaction["blocked_by_safety_limit"])
        transactions.append(transaction)
    return transactions


def get_contact_count(customer_id, date):
    conn = get_conn()
    row = conn.execute(
        "SELECT contact_count FROM customer_contacts WHERE customer_id=? AND date=?",
        (customer_id, date),
    ).fetchone()
    conn.close()
    return row["contact_count"] if row else 0


def increment_contact_count(customer_id, date):
    conn = get_conn()
    conn.execute(
        """INSERT INTO customer_contacts (customer_id, date, contact_count) VALUES (?, ?, 1)
           ON CONFLICT(customer_id, date) DO UPDATE SET contact_count = contact_count + 1""",
        (customer_id, date),
    )
    conn.commit()
    conn.close()


def insert_audit_entry(entry: dict):
    conn = get_conn()
    conn.execute(
        """INSERT INTO audit_log
        (round, transaction_id, customer_id, amount, failure_reason, category,
         chosen_action, evidence, candidates_considered, expected_outcome,
         actual_outcome, recovered_amount, blocked_by_safety_limit, safety_reason,
         explanation, belief_update, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entry["round"], entry["transaction_id"], entry["customer_id"], entry["amount"],
            entry["failure_reason"], entry["category"], entry["chosen_action"],
            json.dumps(entry["evidence"]), json.dumps(entry["candidates_considered"]),
            json.dumps(entry["expected_outcome"]), entry["actual_outcome"],
            entry["recovered_amount"], int(entry["blocked_by_safety_limit"]),
            entry.get("safety_reason"), entry["explanation"],
            json.dumps(entry.get("belief_update")), entry["timestamp"],
        ),
    )
    conn.commit()
    conn.close()


def get_round_summaries():
    conn = get_conn()
    rows = conn.execute("""
        SELECT round,
               COUNT(*) as total_transactions,
               SUM(amount) as amount_at_risk,
               SUM(recovered_amount) as amount_recovered,
               SUM(blocked_by_safety_limit) as blocked_count
        FROM audit_log GROUP BY round ORDER BY round
    """).fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["recovery_rate_pct"] = round(
            (d["amount_recovered"] / d["amount_at_risk"] * 100) if d["amount_at_risk"] else 0, 2
        )
        results.append(d)
    return results


def get_latest_round_number():
    conn = get_conn()
    row = conn.execute("SELECT MAX(round) as m FROM audit_log").fetchone()
    conn.close()
    return (row["m"] or 0)


def reset_all():
    conn = get_conn()
    conn.execute("DELETE FROM beliefs")
    conn.execute("DELETE FROM audit_log")
    conn.execute("DELETE FROM customer_contacts")
    conn.commit()
    conn.close()
