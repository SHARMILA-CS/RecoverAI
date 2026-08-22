"""
This module represents the SIMULATED payment environment. It holds the
ground-truth success probabilities the agent is trying to learn — the
agent never reads these directly, it only observes sampled outcomes,
exactly like it would with real Razorpay data.

IMPORTANT: these are simulated outcomes, not real ones. Swap
`simulate_outcome()` for a real Razorpay test-mode API call once you're
ready to connect this to real data — until then, every "learned" result
in this project reflects the simulated environment defined here, not
real customer behavior.
"""
import random

ROOT_CAUSE_MAP = {
    "network_timeout": "transient",
    "bank_server_error": "transient",
    "otp_failed": "customer_retry_needed",
    "insufficient_funds": "customer_timing_issue",
    "card_declined": "customer_action_needed",
    "checkout_abandoned": "customer_disengaged",
}

# Candidate actions the agent may choose between, per category.
# do_nothing is always an option so the agent can learn "acting isn't worth it".
CANDIDATE_ACTIONS = {
    "transient": ["auto_retry_same_method", "do_nothing"],
    "customer_retry_needed": ["prompt_retry_otp", "do_nothing"],
    "customer_timing_issue": ["schedule_reminder_24h", "do_nothing"],
    "customer_action_needed": ["suggest_alternate_payment_method", "do_nothing"],
    "customer_disengaged": ["send_incentive_reminder", "schedule_reminder_24h", "do_nothing"],
}

# Simulated operational/goodwill cost of taking each action (INR-equivalent).
# This is what makes the agent optimize net revenue, not just recovery count.
ACTION_COST = {
    "auto_retry_same_method": 5,
    "prompt_retry_otp": 5,
    "schedule_reminder_24h": 20,
    "suggest_alternate_payment_method": 10,
    "send_incentive_reminder": 150,  # e.g. discount cost
    "do_nothing": 0,
}

# Actions that count as "contacting the customer" — these are the ones
# the hard safety ceiling applies to, regardless of what the agent learns.
CUSTOMER_CONTACT_ACTIONS = {
    "prompt_retry_otp",
    "schedule_reminder_24h",
    "send_incentive_reminder",
}

# HIDDEN ground truth — the agent never sees this dict directly.
_TRUE_SUCCESS_PROB = {
    ("transient", "auto_retry_same_method"): 0.65,
    ("transient", "do_nothing"): 0.05,
    ("customer_retry_needed", "prompt_retry_otp"): 0.55,
    ("customer_retry_needed", "do_nothing"): 0.05,
    ("customer_timing_issue", "schedule_reminder_24h"): 0.35,
    ("customer_timing_issue", "do_nothing"): 0.05,
    ("customer_action_needed", "suggest_alternate_payment_method"): 0.40,
    ("customer_action_needed", "do_nothing"): 0.05,
    ("customer_disengaged", "send_incentive_reminder"): 0.30,
    ("customer_disengaged", "schedule_reminder_24h"): 0.20,
    ("customer_disengaged", "do_nothing"): 0.05,
}


def simulate_outcome(category: str, action: str) -> bool:
    """
    Samples whether the action 'succeeded' in the simulated environment.
    This stands in for a real payment retry / notification response.
    Replace with a real Razorpay test-mode API call to move from
    simulated to real outcomes.
    """
    prob = _TRUE_SUCCESS_PROB.get((category, action), 0.05)
    return random.random() < prob
