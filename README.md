# Revenue Recovery Agent

Built for Razorpay's AI Builder Internship — **AI Revenue Recovery** track.

## Problem statement

When a payment fails, most systems just log it and move on. But not every
failure is the same: a network timeout is not the same problem as
insufficient funds, and treating them identically wastes money and annoys
customers. This agent looks at a batch of failed payments, figures out
*why* each one failed, picks a bounded recovery action for that specific
cause, executes it, and reports exactly how much revenue it recovered —
with a full audit trail and anti-spam stopping rules.

## Architecture

```
data/generate_data.py   -> synthetic batch of failed payment events
        |
        v
app/agent.py             -> RecoveryAgent
   1. diagnose()   failure_reason -> root_cause_category
   2. decide()     category -> action (via ACTION_POLICY)
   3. stopping rules check (max retries, max reminders/day)
   4. execute()    simulated outcome (swap for real Razorpay APIs)
   5. audit_log.append(...)  full reasoning + outcome per transaction
        |
        v
app/main.py (FastAPI)   -> GET /api/run  returns summary + audit log
        |
        v
dashboard/index.html    -> shows ₹ at risk, ₹ recovered, recovery rate,
                            and the full audit trail per transaction
```

## Root-cause categories -> actions

| failure_reason      | category                | action                          |
|----------------------|--------------------------|----------------------------------|
| network_timeout      | transient                | auto-retry same method           |
| bank_server_error    | transient                | auto-retry same method           |
| otp_failed            | customer_retry_needed    | prompt OTP retry                 |
| insufficient_funds    | customer_timing_issue    | scheduled reminder (+24h)        |
| card_declined         | customer_action_needed   | suggest alternate payment method |
| checkout_abandoned    | customer_disengaged      | one incentive reminder           |

## Stopping rules (so the agent can't run wild)

- Max 2 retries per transaction
- Max 1 reminder per customer per day
- Every blocked action is logged with why it was blocked

## Run it

```bash
pip install -r requirements.txt
python data/generate_data.py        # generates data/transactions.json
uvicorn app.main:app --reload --port 8000
# open dashboard/index.html in your browser, click "Run batch"
```

## What broke during development

*(Fill this in as you build — this is the section Razorpay actually cares
about. Example prompts to answer honestly:)*

- What was your first, wrong assumption about how to map failure reasons to actions?
- Did your stopping rules ever block too aggressively or not enough? How did you tune them?
- If you add a real LLM call in `agent.py::explain()`, what went wrong the first time you tried it (bad prompt, cost, latency, hallucinated numbers)?
- Any issue swapping simulated execution for a real Razorpay test-mode API call?

## Ideas to make this stronger before submitting

1. Replace `explain()` with a real Claude API call (stub is already there) so decisions come with genuine natural-language reasoning — this is what "explainable" means in the track's bar.
2. Replace simulated `success_prob` sampling with real Razorpay test-mode retry/notification API calls.
3. Add a second batch run and show recovery rate *improving* after you tune the policy — a before/after number is very convincing on camera.
4. Add a tiny SQLite log so re-running doesn't lose history, and you can show a trend line over multiple batches.
