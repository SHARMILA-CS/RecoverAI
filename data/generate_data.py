"""
Generates a synthetic batch of failed/abandoned payment events.
This stands in for real Razorpay test-mode transaction data.
Run: python data/generate_data.py  -> writes data/transactions.json
"""
import json
import random
import uuid
from datetime import datetime, timedelta

FAILURE_REASONS = [
    "insufficient_funds",
    "card_declined",
    "network_timeout",
    "bank_server_error",
    "checkout_abandoned",
    "otp_failed",
]

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]

def random_time(days_back=7):
    return (datetime.now() - timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )).isoformat()

def generate_batch(n=60):
    transactions = []
    for _ in range(n):
        reason = random.choices(
            FAILURE_REASONS,
            weights=[20, 20, 15, 10, 25, 10],  # roughly realistic mix
        )[0]
        txn = {
            "transaction_id": str(uuid.uuid4())[:8],
            "merchant_id": f"merchant_{random.randint(1, 5)}",
            "customer_id": f"cust_{random.randint(1000, 1200)}",
            "amount": round(random.uniform(199, 15000), 2),
            "currency": "INR",
            "payment_method": random.choice(PAYMENT_METHODS),
            "failure_reason": reason,
            "retry_count": 0,
            "timestamp": random_time(),
        }
        transactions.append(txn)
    return transactions

if __name__ == "__main__":
    batch = generate_batch(60)
    with open("data/transactions.json", "w") as f:
        json.dump(batch, f, indent=2)
    print(f"Generated {len(batch)} synthetic failed-payment events -> data/transactions.json")

