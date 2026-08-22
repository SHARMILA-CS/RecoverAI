"""
The Recovery Agent — adaptive version.

For each failed payment it:
  1. Diagnoses a root-cause category from the failure_reason
  2. Considers every candidate action for that category and, for each,
     SAMPLES an expected success probability from its current belief
     (Thompson Sampling) -> picks the action with the best expected
     net value (expected_recovery - action_cost)
  3. Checks HARD SAFETY LIMITS -- these are independent of the learned
     policy and can NEVER be overridden by what the agent has learned.
     This is deliberate: a bandit that mis-learns early should still not
     be able to spam a customer.
  4. Executes the action in the SIMULATED environment (app/environment.py)
     and observes an outcome
  5. Updates its belief for that (category, action) pair based on the
     observed outcome
  6. Logs a full decision trail: evidence, candidates considered,
     expected outcome, actual outcome, and the belief update

All outcomes here come from a simulated environment, not real payment
data -- see app/environment.py for how to swap in real Razorpay
test-mode calls later.
"""
import random
from datetime import datetime

from app import db
from app.environment import (
    ROOT_CAUSE_MAP,
    CANDIDATE_ACTIONS,
    ACTION_COST,
    CUSTOMER_CONTACT_ACTIONS,
    simulate_outcome,
)

# --- Hard safety limits (NOT learned, NOT overridable) ----------------------
MAX_RETRIES_PER_TXN = 2
MAX_CUSTOMER_CONTACTS_PER_DAY = 1


def explain(txn, category, chosen_action, expected_value, evidence):
    """
    Plain-English explanation of the decision, for the audit trail.
    Template-based by default. To make this a real LLM call:

        import anthropic
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY env var
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            messages=[{"role": "user", "content":
                f"In one sentence, explain why we chose '{chosen_action}' "
                f"for a {category} payment failure of amount {txn['amount']}, "
                f"given evidence: {evidence}."}]
        )
        return resp.content[0].text
    """
    return (
        f"Chosen '{chosen_action}' for category '{category}' because it had the "
        f"highest sampled expected net value (₹{expected_value:.2f}) among candidates "
        f"considered, based on outcomes observed so far in the simulated environment."
    )


class RecoveryAgent:
    def __init__(self, round_number: int):
        self.round_number = round_number

    def _spam_cost(self, contact_count_today: int) -> float:
        """
        Cost grows with how many times we've already contacted this
        customer today -- this is the OPTIMIZATION side of spam avoidance.
        It nudges the agent away from over-contacting even before the
        hard safety limit kicks in.
        """
        return 30 * (contact_count_today ** 2)

    def _hard_safety_block(self, txn, action, today: str):
        """
        Independent, non-learned safety check. Returns a block reason
        string if this action must be refused outright, else None.
        This check runs regardless of what the bandit has learned and
        cannot be bypassed by expected-value calculations.
        """
        if action == "auto_retry_same_method" and txn["retry_count"] >= MAX_RETRIES_PER_TXN:
            return f"HARD LIMIT: max retries ({MAX_RETRIES_PER_TXN}) reached for this transaction."

        if action in CUSTOMER_CONTACT_ACTIONS:
            count = db.get_contact_count(txn["customer_id"], today)
            if count >= MAX_CUSTOMER_CONTACTS_PER_DAY:
                return f"HARD LIMIT: customer already contacted {count} time(s) today (ceiling={MAX_CUSTOMER_CONTACTS_PER_DAY})."

        return None

    def choose_action(self, category: str, txn, today: str):
        """
        Thompson Sampling over candidate actions for this category.
        For each candidate: sample a success probability from its Beta
        belief, compute expected net value, and additionally penalize
        actions that would contact an already-contacted customer today
        (the soft, optimization-driven spam cost).
        """
        candidates = []
        contact_count_today = db.get_contact_count(txn["customer_id"], today)

        for action in CANDIDATE_ACTIONS[category]:
            alpha, beta = db.get_belief(category, action)
            sampled_prob = random.betavariate(alpha, beta)
            cost = ACTION_COST[action]
            if action in CUSTOMER_CONTACT_ACTIONS:
                cost += self._spam_cost(contact_count_today)

            expected_value = sampled_prob * txn["amount"] - cost
            candidates.append({
                "action": action,
                "belief_alpha": round(alpha, 2),
                "belief_beta": round(beta, 2),
                "sampled_success_prob": round(sampled_prob, 3),
                "cost": round(cost, 2),
                "expected_value": round(expected_value, 2),
            })

        candidates.sort(key=lambda c: c["expected_value"], reverse=True)
        return candidates

    def process_transaction(self, txn):
        category = ROOT_CAUSE_MAP[txn["failure_reason"]]
        today = datetime.now().strftime("%Y-%m-%d")

        candidates = self.choose_action(category, txn, today)
        chosen = candidates[0]
        action = chosen["action"]

        evidence = {
            "amount": txn["amount"],
            "failure_reason": txn["failure_reason"],
            "retry_count_so_far": txn["retry_count"],
            "customer_contacts_today": db.get_contact_count(txn["customer_id"], today),
        }

        block_reason = self._hard_safety_block(txn, action, today)

        entry = {
            "round": self.round_number,
            "transaction_id": txn["transaction_id"],
            "customer_id": txn["customer_id"],
            "amount": txn["amount"],
            "failure_reason": txn["failure_reason"],
            "category": category,
            "chosen_action": action,
            "evidence": evidence,
            "candidates_considered": candidates,
            "expected_outcome": {
                "sampled_success_prob": chosen["sampled_success_prob"],
                "expected_value": chosen["expected_value"],
            },
            "timestamp": datetime.now().isoformat(),
        }

        if block_reason:
            # Hard safety limit wins, no matter how good the expected value looked.
            entry["blocked_by_safety_limit"] = True
            entry["safety_reason"] = block_reason
            entry["actual_outcome"] = "not_attempted"
            entry["recovered_amount"] = 0.0
            entry["belief_update"] = None
            entry["explanation"] = (
                f"Wanted to try '{action}' (expected value ₹{chosen['expected_value']:.2f}) "
                f"but blocked by a hard safety limit: {block_reason}"
            )
        else:
            if action in CUSTOMER_CONTACT_ACTIONS:
                db.increment_contact_count(txn["customer_id"], today)
            if action == "auto_retry_same_method":
                txn["retry_count"] += 1

            success = simulate_outcome(category, action)
            new_alpha, new_beta = db.update_belief(category, action, success)

            entry["blocked_by_safety_limit"] = False
            entry["safety_reason"] = None
            entry["actual_outcome"] = "recovered" if success else "not_recovered"
            entry["recovered_amount"] = txn["amount"] if success else 0.0
            entry["belief_update"] = {
                "action": action,
                "new_alpha": round(new_alpha, 2),
                "new_beta": round(new_beta, 2),
                "observed_success": success,
            }
            entry["explanation"] = explain(txn, category, action, chosen["expected_value"], evidence)

        db.insert_audit_entry(entry)
        return entry

    def run_batch(self, transactions):
        return [self.process_transaction(t) for t in transactions]
