# RecoverAI — Adaptive Revenue Recovery Agent

## Problem Statement

Failed payments do not all have the same cause. A temporary network or bank
error may be worth retrying, while insufficient funds, an OTP failure, a card
decline, or an abandoned checkout calls for a different customer action. Using
one recovery response for every failure can waste operational cost, miss
recoverable revenue, or contact customers unnecessarily.

RecoverAI processes synthetic failed-payment events and chooses a bounded,
cause-specific recovery action. It runs the action in a simulated payment
environment, records the decision and result, and uses observed outcomes to
adapt future choices.

## Solution

- Diagnoses each `failure_reason` into a root-cause category.
- Maps the category to candidate recovery actions.
- Chooses an action using sampled success probabilities and expected net value.
- Applies independent retry and customer-contact safety limits.
- Executes the selected action against the simulated environment.
- Records evidence, candidates, expected outcome, actual outcome, and recovery amount.
- Updates the belief for the selected category/action pair when an action runs.
- Persists round history, learned beliefs, and customer contact counts.
- Exposes the recovery engine through FastAPI.
- Provides a browser dashboard for metrics, activity, learning, and controls.

## Architecture

`data/generate_data.py` creates synthetic failed-payment events in memory when a
round is run. It can also be run directly to write `data/transactions.json`.
The API does not read that file: `POST /api/run-round` generates a fresh batch
of 60 events by default.

For each transaction, `app/agent.py` maps the failure reason, evaluates the
candidate actions, samples from the current Beta belief for each action, and
selects the highest expected net value. The action cost and, for customer
contact actions, a soft cost based on contacts already made that day are part
of this calculation. A hard safety check then runs before execution.

`app/environment.py` samples the outcome using fixed hidden success
probabilities. The agent sees only the resulting success or failure. Successful
actions update `app/db.py`, which stores beliefs and the complete audit trail
in SQLite. `app/main.py` serves the API, and `dashboard/index.html` fetches
that API from `http://localhost:8000`.

## Recovery Decision Model

### Failure categories and actions

| Failure reason | Root-cause category | Candidate recovery actions |
| --- | --- | --- |
| `network_timeout` | `transient` | `auto_retry_same_method`, `do_nothing` |
| `bank_server_error` | `transient` | `auto_retry_same_method`, `do_nothing` |
| `otp_failed` | `customer_retry_needed` | `prompt_retry_otp`, `do_nothing` |
| `insufficient_funds` | `customer_timing_issue` | `schedule_reminder_24h`, `do_nothing` |
| `card_declined` | `customer_action_needed` | `suggest_alternate_payment_method`, `do_nothing` |
| `checkout_abandoned` | `customer_disengaged` | `send_incentive_reminder`, `schedule_reminder_24h`, `do_nothing` |

`do_nothing` is always available. The configured action costs are INR-equivalent
costs used in the net-value calculation: 5 for an automatic retry or OTP
prompt, 20 for a 24-hour reminder, 10 for an alternate payment suggestion,
150 for an incentive reminder, and 0 for doing nothing.

### Adaptive learning

Each category/action pair has a Beta belief represented by `alpha` and `beta`.
The initial belief is Beta(1,1), an uninformed prior. `alpha` counts observed
success evidence and `beta` counts observed failure evidence, including the
prior value of 1 in each parameter. After a successful simulated action,
`alpha` increases by 1; after an unsuccessful action, `beta` increases by 1.

For each candidate, the agent samples a probability from its current Beta
belief using Thompson Sampling. It multiplies that sample by the transaction
amount and subtracts the action cost (and any soft contact cost), then chooses
the largest expected net value. As more outcomes are observed, the beliefs
shape future choices for that category/action pair. Safety-blocked decisions
do not execute and therefore do not update a belief.

## Safety Controls

The limits are independent of learned beliefs and cannot be overridden by the
selection policy:

- A transaction can be retried at most 2 times.
- A customer can be contacted at most 1 time per day.
- Contact actions are OTP prompts, 24-hour reminders, and incentive reminders.

When the selected action violates a hard limit, it is recorded as
`not_attempted` with `blocked_by_safety_limit` set to true and a safety reason.
No fallback action is attempted for that transaction, and no belief update is
made.

## Dashboard

Open `dashboard/index.html` while the FastAPI server is running. The current
dashboard provides:

- Performance metrics for amount at risk, recovered amount, recovery rate,
  processed transactions, and successful recoveries.
- A recovery-rate trend across persisted rounds.
- A latest-round summary with transaction, recovery, and safety-block counts.
- A paginated transaction-level recovery activity and audit trail.
- A paginated agent-learning table showing category/action beliefs, estimated
        success, and observations.
- The adaptive decision policy, identified as Thompson Sampling.
- Safety and controls showing the retry and contact ceilings and latest-round
        safety blocks.
- A reset control that clears persisted beliefs, audit history, and customer
        contact history.

The dashboard has controls to refresh the data and run the next round. It
expects the API at `http://localhost:8000` and uses browser requests enabled
by the backend's CORS configuration.

## API

The FastAPI application is defined in `app/main.py`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/run-round` | Generate and process a round; optional `n` query parameter sets the batch size and defaults to 60. |
| `GET` | `/api/rounds-summary` | Return amount, recovery, transaction, and safety-block summaries by round. |
| `GET` | `/api/beliefs` | Return current `alpha` and `beta` values for learned category/action pairs. |
| `GET` | `/api/transactions` | Return persisted transaction decision trails, newest round first. |
| `POST` | `/api/reset` | Delete all persisted beliefs, audit history, and customer contact counts. |
| `GET` | `/` | Return a running status message and the available endpoint list. |

## Persistence

The persistence layer uses SQLite at `data/recovery_agent.db`. It creates
three tables:

- `beliefs` stores `alpha` and `beta` for each category/action pair.
- `audit_log` stores the full per-transaction decision and outcome trail,
  including safety-block details and belief updates.
- `customer_contacts` stores contact counts by customer and date for the hard
  daily contact limit.

The database is initialized when `app.main` loads. The reset endpoint deletes
all rows from these tables. The optional `data/transactions.json` file is a
generated input artifact, not the source of round history.

## Running Locally

From the project root:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then open `dashboard/index.html` directly in a browser and use **Run Next
Round**. The API server must remain running while the dashboard is open.

To generate the optional standalone synthetic input file:

```bash
python data/generate_data.py
```

## Development Notes

The payment environment is deliberately simulated. Its hidden success
probabilities are defined in `app/environment.py`, and the agent learns only
from sampled outcomes. The decision explanation stored in the audit trail is
template-based and reports the selected action's sampled expected net value.
The current dependency list contains only FastAPI and Uvicorn.

## Why this is not a generic AI wrapper

RecoverAI's core is an adaptive decision and recovery engine. Its value comes
from cause-based actions, adaptive beliefs, expected-net-value selection, hard
safety constraints, simulated execution, SQLite persistence, and a
transaction-level audit trail. These components make the agent's behavior
observable and repeatable across rounds.
