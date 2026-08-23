"""
Run: uvicorn app.main:app --reload --port 8000
Then open dashboard/index.html in a browser (it calls localhost:8000).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.agent import RecoveryAgent
from data.generate_data import generate_batch

app = FastAPI(title="Revenue Recovery Agent (Adaptive)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()


@app.post("/api/run-round")
def run_round(n: int = 60):
    """
    Runs one round: generates a fresh synthetic batch, lets the current
    agent (with beliefs learned from all prior rounds) process it, and
    persists results. Call this repeatedly to watch the recovery rate
    improve round over round as beliefs update.
    """
    round_number = db.get_latest_round_number() + 1
    transactions = generate_batch(n)
    agent = RecoveryAgent(round_number=round_number)
    results = agent.run_batch(transactions)

    return {
        "round": round_number,
        "audit_log": results,
    }


@app.get("/api/rounds-summary")
def rounds_summary():
    """Recovery rate per round -- this is the 'agent gets better over time' evidence."""
    return db.get_round_summaries()


@app.get("/api/beliefs")
def beliefs():
    """Current learned belief (alpha/beta) for every (category, action) pair."""
    return db.get_all_beliefs()


@app.get("/api/learning-trajectory")
def learning_trajectory():
    """Historical Beta belief values reconstructed from persisted audit updates."""
    return db.get_learning_trajectory()


@app.get("/api/transactions")
def transactions():
    """Persisted transaction decision trails, newest round first."""
    return db.get_transactions()


@app.post("/api/reset")
def reset():
    """Wipes all learned beliefs and audit history -- useful for a clean demo run."""
    db.reset_all()
    return {"status": "reset"}


@app.get("/")
def root():
    return {
        "status": "Adaptive Revenue Recovery Agent is running.",
        "endpoints": ["/api/run-round", "/api/rounds-summary", "/api/beliefs", "/api/transactions", "/api/reset"],
    }
