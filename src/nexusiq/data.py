import csv
import hashlib
import json
import random
from pathlib import Path
from .config import DATA

REGIONS = ("APAC", "EMEA", "AMER")
PLANS = ("Starter", "Growth", "Enterprise")
PRICES = {"Starter": 29, "Growth": 99, "Enterprise": 299}

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def write_csv(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def seed_data(destination=DATA, seed=42):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    corpus = destination / "documents"
    corpus.mkdir(exist_ok=True)
    rng = random.Random(seed)
    customers, subscriptions, orders, tickets = [], [], [], []
    for i in range(1, 201):
        cid = f"C{i:04d}"
        region, plan = rng.choice(REGIONS), rng.choice(PLANS)
        product = {"Starter": "AC-ST", "Growth": "AC-GR", "Enterprise": "AC-EN"}[plan]
        customers.append(dict(customer_id=cid, tenant_id="atlascloud", region=region, plan=plan, join_date=f"2025-{rng.randint(1,12):02d}-01"))
        subscriptions.append(dict(customer_id=cid, product_id=product, status="active", monthly_price=PRICES[plan], snapshot_date="2026-07-01"))
        for month in range(1, 7):
            orders.append(dict(order_id=f"O{i:04d}-{month}", customer_id=cid, product_id=product, order_date=f"2026-{month:02d}-01", revenue=PRICES[plan]))
        for n in range(rng.randint(0, 4)):
            tickets.append(dict(ticket_id=f"T{i:04d}-{n}", customer_id=cid, opened_at=f"2026-{rng.randint(1,6):02d}-{rng.randint(1,28):02d}", category=rng.choice(["billing", "outage", "onboarding"]), resolution_hours=rng.randint(1, 72)))
    for name, rows in [("customers", customers), ("subscriptions", subscriptions), ("orders", orders), ("tickets", tickets)]:
        write_csv(destination / f"{name}.csv", rows)
    documents, questions = [], []
    for region in REGIONS:
        for plan in PLANS:
            window = {"Starter": 7, "Growth": 14, "Enterprise": 30}[plan]
            response = {"Starter": 24, "Growth": 8, "Enterprise": 2}[plan]
            policies = {
                "refund": f"{plan} customers in {region} can request a refund within {window} calendar days of their first invoice. Renewals are excluded. Approved refunds return to the original payment method.",
                "support": f"{plan} accounts in {region} receive an initial response to critical incidents within {response} hours. Open a support ticket and include the affected product code. Resolution time is not guaranteed.",
                "retention": f"For {region} {plan} accounts, retention discounts require a documented renewal conversation. An analyst may recommend a discount but Finance must approve it before an offer is sent. Discounts expire after 90 days.",
                "security": f"{region} {plan} accounts must enable multi-factor authentication for all administrators. Access reviews occur every 90 days. Security incidents must be escalated to the security team within 4 hours.",
            }
            for topic, body in policies.items():
                docid = f"{region.lower()}-{plan.lower()}-{topic}-v1"
                title = f"{region} {plan} {topic.title()} Policy"
                text = f"# {title}\n\n## Scope\nApplies to AtlasCloud {plan} customers in {region}. Effective 2026-07-01. Version 1.0.\n\n## Rules\n{body}\n\n## Ownership\nPolicy owner: Customer Operations. Escalate disputed interpretations to the policy owner.\n"
                path = corpus / f"{docid}.md"
                path.write_text(text)
                documents.append(dict(document_id=docid, title=title, tenant_id="atlascloud", roles=["analyst"], region=region, plan=plan, effective_date="2026-07-01", version="1.0", path=f"documents/{docid}.md", sha256=digest(text)))
                if topic in ("refund", "support"):
                    query = f"What is the {plan} refund window in {region}?" if topic == "refund" else f"How quickly does critical support respond for {region} {plan} accounts?"
                    questions.append(dict(id=f"q{len(questions)+1:03d}", query=query, relevant_document_ids=[docid], filters=dict(region=region, plan=plan), expected_fact=f"{window} calendar days" if topic == "refund" else f"{response} hours"))
    for query in ["What is the CEO home address?", "What is the policy for Antarctica accounts?", "What is AtlasCloud's stock price?", "What is the medical insurance policy?", "What is the quantum processor warranty?", "What is the spaceship refund window?"]:
        questions.append(dict(id=f"q{len(questions)+1:03d}", query=query, relevant_document_ids=[], expected_fact=None, unanswerable=True))
    table_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.glob("*.csv"))}
    payload = dict(dataset_version="atlascloud-v1", seed=seed, snapshot_date="2026-07-01", documents=documents, tables=table_hashes, counts=dict(customers=len(customers), subscriptions=len(subscriptions), orders=len(orders), tickets=len(tickets), documents=len(documents)))
    payload["dataset_sha256"] = digest(json.dumps(payload, sort_keys=True))
    (destination / "manifest.json").write_text(json.dumps(payload, indent=2))
    (destination / "golden_seed.jsonl").write_text("".join(json.dumps(q)+"\n" for q in questions))
    return payload
