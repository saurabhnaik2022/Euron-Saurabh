"""
Project SENTINEL: Supabase -> Neo4j graph loader

Loads up to 5,000 transactions (or more if configured), joins labels and
dimension tables in Supabase, and idempotently creates:
    (:Customer)-[:USED_DEVICE {transaction_id, time}]->(:Device)
    (:Customer)-[:PAID {
        transaction_id, amount, time, fraud_label
    }]->(:Merchant)

Required environment variables:
    SUPABASE_URL
    SUPABASE_KEY
    NEO4J_URI
    NEO4JUSER
    NEO4JPASSWORD

Install:
    pip install supabase neo4j python-dotenv

Run:
    python load_sentinel_graph.py
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List

from dotenv import load_dotenv
from neo4j import GraphDatabase
from supabase import Client, create_client

load_dotenv()

# The assignment asks for a sample of at least 5,000 transactions.
# Set TRANSACTION_LIMIT=0 to load every transaction (use pagination).
TRANSACTION_LIMIT = int(os.getenv("TRANSACTION_LIMIT", "5000"))
PAGE_SIZE = 1000
LOOKUP_BATCH_SIZE = 400
NEO4J_BATCH_SIZE = 1000


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def connect_to_supabase() -> Client:
    client = create_client(
        required_env("SUPABASE_URL"),
        required_env("SUPABASE_KEY"),
    )
    print("Connected to Supabase successfully.")
    return client


def connect_to_neo4j():
    driver = GraphDatabase.driver(
        required_env("NEO4J_URI"),
        auth=(required_env("NEO4JUSER"), required_env("NEO4JPASSWORD")),
    )
    driver.verify_connectivity()
    print("Connected to Neo4j successfully.")
    return driver


def fetch_table(
    supabase: Client,
    table_name: str,
    limit: int = 0,
    order_column: str | None = None,
) -> List[Dict[str, Any]]:
    """Fetch a table in pages; limit=0 means fetch all rows."""
    rows: List[Dict[str, Any]] = []
    start = 0

    while True:
        query = supabase.table(table_name).select("*")
        if order_column:
            query = query.order(order_column)
        end = start + PAGE_SIZE - 1
        response = query.range(start, end).execute()
        page = response.data or []
        rows.extend(page)

        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE

        if limit and len(rows) >= limit:
            break

    return rows[:limit] if limit else rows


def fetch_by_ids(
    supabase: Client,
    table_name: str,
    id_column: str,
    ids: Iterable[str],
) -> List[Dict[str, Any]]:
    """Fetch matching dimension/label records in manageable IN-query batches."""
    unique_ids = sorted({value for value in ids if value})
    rows: List[Dict[str, Any]] = []

    for offset in range(0, len(unique_ids), LOOKUP_BATCH_SIZE):
        batch = unique_ids[offset : offset + LOOKUP_BATCH_SIZE]
        response = (
            supabase.table(table_name)
            .select("*")
            .in_(id_column, batch)
            .execute()
        )
        rows.extend(response.data or [])

    return rows


def parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "t", "1", "yes", "y"}


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def chunks(items: List[Dict[str, Any]], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def create_constraints(driver) -> None:
    statements = [
        """
        CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
        FOR (n:Customer) REQUIRE n.customer_id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT device_id_unique IF NOT EXISTS
        FOR (n:Device) REQUIRE n.device_id IS UNIQUE
        """,
        """
        CREATE CONSTRAINT merchant_id_unique IF NOT EXISTS
        FOR (n:Merchant) REQUIRE n.merchant_id IS UNIQUE
        """,
    ]
    with driver.session() as session:
        for statement in statements:
            session.run(statement).consume()
    print("Uniqueness constraints verified/created.")


def build_node_rows(
    transactions: List[Dict[str, Any]],
    customers: List[Dict[str, Any]],
    devices: List[Dict[str, Any]],
    merchants: List[Dict[str, Any]],
):
    customer_by_id = {r["customer_id"]: r for r in customers if r.get("customer_id")}
    device_by_id = {r["device_id"]: r for r in devices if r.get("device_id")}
    merchant_by_id = {r["merchant_id"]: r for r in merchants if r.get("merchant_id")}

    customer_ids = sorted({r["customer_id"] for r in transactions if r.get("customer_id")})
    device_ids = sorted({r["device_id"] for r in transactions if r.get("device_id")})
    merchant_ids = sorted({r["merchant_id"] for r in transactions if r.get("merchant_id")})

    customer_rows = []
    for customer_id in customer_ids:
        source = customer_by_id.get(customer_id, {})
        customer_rows.append({
            "customer_id": customer_id,
            "props": {
                "created_at": source.get("created_at"),
                "customer_age": parse_int(source.get("customer_age")),
                "home_city": source.get("home_city"),
                "region": source.get("region"),
                "is_synthetic": parse_bool(source.get("is_synthetic")),
            },
        })

    device_rows = []
    for device_id in device_ids:
        source = device_by_id.get(device_id, {})
        device_rows.append({
            "device_id": device_id,
            "props": {
                "device_kind": source.get("device_kind"),
                "is_synthetic": parse_bool(source.get("is_synthetic")),
            },
        })

    merchant_rows = []
    for merchant_id in merchant_ids:
        source = merchant_by_id.get(merchant_id, {})
        location = source.get("merchant_location") or {}
        if isinstance(location, str):
            try:
                location = json.loads(location)
            except json.JSONDecodeError:
                location = {}

        merchant_rows.append({
            "merchant_id": merchant_id,
            "props": {
                "name": source.get("synthetic_name"),
                "merchant_category": source.get("merchant_category"),
                "city": location.get("city") if isinstance(location, dict) else None,
                "latitude": parse_float(location.get("lat")) if isinstance(location, dict) else None,
                "longitude": parse_float(location.get("lon")) if isinstance(location, dict) else None,
                "is_synthetic": parse_bool(source.get("is_synthetic")),
            },
        })

    missing = {
        "customers": len(set(customer_ids) - set(customer_by_id)),
        "devices": len(set(device_ids) - set(device_by_id)),
        "merchants": len(set(merchant_ids) - set(merchant_by_id)),
    }
    return customer_rows, device_rows, merchant_rows, missing


def load_nodes(driver, label: str, id_property: str, rows: List[Dict[str, Any]]) -> None:
    query = f"""
    UNWIND $rows AS row
    MERGE (n:{label} {{{id_property}: row.{id_property}}})
    SET n += row.props
    """
    with driver.session() as session:
        for batch in chunks(rows, NEO4J_BATCH_SIZE):
            session.run(query, rows=batch).consume()


def build_relationship_rows(
    transactions: List[Dict[str, Any]],
    labels: List[Dict[str, Any]],
):
    label_by_tx = {
        row["transaction_id"]: row
        for row in labels
        if row.get("transaction_id")
    }

    used_device_rows = []
    paid_rows = []
    missing_labels = 0
    missing_devices = 0

    for tx in transactions:
        tx_id = tx.get("transaction_id")
        customer_id = tx.get("customer_id")
        device_id = tx.get("device_id")
        merchant_id = tx.get("merchant_id")
        tx_time = tx.get("transaction_time")

        if not all([tx_id, customer_id, merchant_id, tx_time]):
            continue

        label_row = label_by_tx.get(tx_id)
        fraud_label = None
        if label_row is None:
            missing_labels += 1
        else:
            fraud_label = parse_int(label_row.get("fraud_label"))

        # The same transaction_id is used as the MERGE key on both
        # relationship types, making repeated runs idempotent.
        if device_id:
            used_device_rows.append({
                "transaction_id": tx_id,
                "customer_id": customer_id,
                "device_id": device_id,
                "time": tx_time,
            })
        else:
            missing_devices += 1

        # amount_paise is retained as an additional exact-value property.
        # amount is transaction_amount in rupees, as requested in the task.
        amount = parse_float(tx.get("transaction_amount"))
        if amount is None and tx.get("amount_paise") is not None:
            amount = parse_float(tx.get("amount_paise")) / 100.0

        paid_rows.append({
            "transaction_id": tx_id,
            "customer_id": customer_id,
            "merchant_id": merchant_id,
            "amount": amount,
            "amount_paise": parse_int(tx.get("amount_paise")),
            "time": tx_time,
            "fraud_label": fraud_label,
            "label_source": label_row.get("label_source") if label_row else None,
            "split": label_row.get("split") if label_row else tx.get("split"),
        })

    return used_device_rows, paid_rows, missing_labels, missing_devices


def load_relationships(driver, used_device_rows, paid_rows) -> None:
    used_device_query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (d:Device {device_id: row.device_id})
    MERGE (c)-[r:USED_DEVICE {transaction_id: row.transaction_id}]->(d)
    SET r.time = row.time
    """

    paid_query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (m:Merchant {merchant_id: row.merchant_id})
    MERGE (c)-[r:PAID {transaction_id: row.transaction_id}]->(m)
    SET r.amount = row.amount,
        r.amount_paise = row.amount_paise,
        r.time = row.time,
        r.fraud_label = row.fraud_label,
        r.label_source = row.label_source,
        r.split = row.split
    """

    with driver.session() as session:
        for batch in chunks(used_device_rows, NEO4J_BATCH_SIZE):
            session.run(used_device_query, rows=batch).consume()
        for batch in chunks(paid_rows, NEO4J_BATCH_SIZE):
            session.run(paid_query, rows=batch).consume()


def print_graph_counts(driver) -> None:
    queries = {
        "Customer nodes": "MATCH (n:Customer) RETURN count(n) AS count",
        "Device nodes": "MATCH (n:Device) RETURN count(n) AS count",
        "Merchant nodes": "MATCH (n:Merchant) RETURN count(n) AS count",
        "USED_DEVICE relationships": "MATCH ()-[r:USED_DEVICE]->() RETURN count(r) AS count",
        "PAID relationships": "MATCH ()-[r:PAID]->() RETURN count(r) AS count",
        "Fraud-labelled PAID relationships": (
            "MATCH ()-[r:PAID {fraud_label: 1}]->() RETURN count(r) AS count"
        ),
    }
    print("\nNeo4j graph counts:")
    with driver.session() as session:
        for description, query in queries.items():
            count = session.run(query).single()["count"]
            print(f"  {description}: {count:,}")


def main() -> None:
    supabase = connect_to_supabase()
    driver = connect_to_neo4j()

    try:
        print("\nFetching transactions from Supabase...")
        transactions = fetch_table(
            supabase,
            "transactions",
            limit=TRANSACTION_LIMIT,
            order_column="transaction_time",
        )
        if len(transactions) < 5000:
            raise RuntimeError(
                f"Only {len(transactions)} transactions were fetched; "
                "the assignment requires at least 5,000."
            )
        print(f"Fetched {len(transactions):,} transactions.")

        customer_ids = {r.get("customer_id") for r in transactions}
        device_ids = {r.get("device_id") for r in transactions}
        merchant_ids = {r.get("merchant_id") for r in transactions}
        transaction_ids = {r.get("transaction_id") for r in transactions}

        print("Fetching labels and dimension records...")
        labels = fetch_by_ids(supabase, "labels", "transaction_id", transaction_ids)
        customers = fetch_by_ids(supabase, "customers", "customer_id", customer_ids)
        devices = fetch_by_ids(supabase, "devices", "device_id", device_ids)
        merchants = fetch_by_ids(supabase, "merchants", "merchant_id", merchant_ids)

        print(
            f"Fetched {len(labels):,} labels, {len(customers):,} customers, "
            f"{len(devices):,} devices and {len(merchants):,} merchants."
        )

        customer_rows, device_rows, merchant_rows, missing_dimensions = build_node_rows(
            transactions, customers, devices, merchants
        )
        used_device_rows, paid_rows, missing_labels, missing_device_transactions = (
            build_relationship_rows(transactions, labels)
        )

        create_constraints(driver)

        print("\nLoading nodes with MERGE...")
        load_nodes(driver, "Customer", "customer_id", customer_rows)
        load_nodes(driver, "Device", "device_id", device_rows)
        load_nodes(driver, "Merchant", "merchant_id", merchant_rows)

        print("Loading relationships with MERGE...")
        load_relationships(driver, used_device_rows, paid_rows)

        print("\nLoad summary:")
        print(f"  Transactions selected: {len(transactions):,}")
        print(f"  Customer nodes prepared: {len(customer_rows):,}")
        print(f"  Device nodes prepared: {len(device_rows):,}")
        print(f"  Merchant nodes prepared: {len(merchant_rows):,}")
        print(f"  USED_DEVICE relationships prepared: {len(used_device_rows):,}")
        print(f"  PAID relationships prepared: {len(paid_rows):,}")
        print(f"  Transactions without a device: {missing_device_transactions:,}")
        print(f"  Transactions without a matching label: {missing_labels:,}")
        print(f"  Missing dimension records: {missing_dimensions}")

        print_graph_counts(driver)
        print("\nGraph load completed. Re-running this script will MERGE existing IDs.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
