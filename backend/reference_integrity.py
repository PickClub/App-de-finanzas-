"""Transactional reference coordination; never creates or repairs a parent."""
from decimal import Decimal, InvalidOperation

from bson.decimal128 import Decimal128
from fastapi import HTTPException

if __package__:
    from .history_keys import strip_history_metadata
else:
    from history_keys import strip_history_metadata


HIDDEN = {"_reference_revision"}


async def guard_legacy_bill(db, user_id, bill_id, session):
    await _legacy_guard(db, user_id, session, bill_id=bill_id)


async def guard_legacy_recurring(db, user_id, recurring_id, session, due_date=None):
    await _legacy_guard(db, user_id, session, recurring_id=recurring_id,
                        original_due_date=due_date, whole_recurring=due_date is None)


async def guard_legacy_receipt(db, user_id, receipt, session):
    if any(key.startswith("_shared_") for key in receipt):
        raise HTTPException(409, "El registro conserva gestión R4; el flujo anterior está bloqueado.")
    if receipt.get("bill_id"):
        await guard_legacy_bill(db, user_id, receipt["bill_id"], session)
    if receipt.get("recurring_id"):
        await guard_legacy_recurring(db, user_id, receipt["recurring_id"], session, receipt.get("due_date"))
    if receipt.get("transaction_id"):
        await _legacy_guard(db, user_id, session, transaction_id=receipt["transaction_id"])


async def guard_legacy_movement(db, user_id, tx, session):
    await _legacy_guard(db, user_id, session, transaction_id=tx["id"])


async def _legacy_guard(db, user_id, session, **lookup):
    # Lazy import avoids the shared_obligations -> reference_integrity cycle.
    if __package__:
        from .shared_obligations import require_legacy_allowed
    else:
        from shared_obligations import require_legacy_allowed
    await require_legacy_allowed(db, effective_user=user_id, session=session, **lookup)


def preserve_references(fields, data, old, names, supplied=None):
    """Keep omitted / unchanged legacy values literally; don't fill absent keys.

    Edit routes pass the original field set because their effective model also
    contains inherited values. Explicit null still uses the existing semantics.
    """
    if old is None:
        return
    supplied = data.model_fields_set if supplied is None else supplied
    for field in names:
        if field not in supplied:
            if field in old:
                fields[field] = old[field]
            else:
                fields.pop(field, None)
        elif field in old and getattr(data, field) == old[field]:
            fields[field] = old[field]


def _same_amount(left, right):
    """Compare finite numeric representations without changing monetary values."""
    try:
        if isinstance(left, bool) or isinstance(right, bool):
            return False
        a = left.to_decimal() if isinstance(left, Decimal128) else Decimal(str(left))
        b = right.to_decimal() if isinstance(right, Decimal128) else Decimal(str(right))
        return a.is_finite() and b.is_finite() and a == b
    except (InvalidOperation, ValueError, TypeError):
        return False


def _same_optional_reference(left, right):
    # Record creation already represents optional empty references as null.
    # Compare that absence without rewriting either historical document.
    return (None if left in (None, "") else left) == (None if right in (None, "") else right)


def _matches_bill_movement(payment, tx):
    return bool(payment and tx
                and tx.get("id") == payment.get("transaction_id")
                and tx.get("bill_payment_id") == payment.get("id")
                and tx.get("bill_id") == payment.get("bill_id")
                and tx.get("account_id") == payment.get("account_id")
                and tx.get("type") == "expense"
                and _same_amount(tx.get("amount"), payment.get("amount")))


async def coordinate(db, user_id, payload, session, old=None):
    """Touch existing parents, reject new missing links, retain unchanged legacy links.

    A real increment conflicts with a concurrent parent deletion under snapshot
    isolation. The caller's transaction runner must retry the entire operation.
    """
    if session is None:
        raise RuntimeError("Reference coordination requires a transaction")
    parents = {
        "account_id": "accounts", "to_account_id": "accounts",
        "category_id": "categories", "parent_id": "categories",
        "source_transaction_id": "transactions",
        "recurring_payment_id": "recurring_payments", "recurring_id": "recurring_payments",
        "goal_id": "saving_goals", "debt_id": "debts", "bill_id": "bills",
    }
    seen = set()
    for field, collection in parents.items():
        value = payload.get(field)
        if value in (None, "") or (collection, value) in seen:
            continue
        seen.add((collection, value))
        result = await getattr(db, collection).update_one(
            {"id": value, "user_id": user_id},
            {"$inc": {"_reference_revision": 1}}, session=session,
        )
        if not result.matched_count and (old is None or old.get(field) != value):
            raise HTTPException(422, f"Referencia inexistente o no disponible: {field}.")


def public(doc):
    return strip_history_metadata({k: v for k, v in doc.items() if k not in HIDDEN and k != "_id"})


async def check_movement_references(db, user_id, tx, session, debt_payment_id=None):
    """Reject active inverse links before an ordinary write or a debt dispatch.

    Link creation on an existing movement writes that same movement (or its
    coordination revision). A concurrent edit/delete therefore conflicts and
    retries this read in its existing transaction, rather than committing an
    orphan. Historical retired receipts are deliberately excluded.
    """
    if session is None:
        raise RuntimeError("Inverse reference checks require a transaction")
    await _legacy_guard(db, user_id, session, transaction_id=tx["id"])
    query = {"transaction_id": tx["id"], "user_id": user_id, "deleted": {"$ne": True}}
    for collection in ("bill_payments", "recurring_payment_records", "goal_contributions", "debt_payments"):
        async for linked in getattr(db, collection).find(query, session=session):
            if (collection == "debt_payments" and debt_payment_id is not None
                    and linked.get("id") == debt_payment_id and tx.get("debt_payment_id") == debt_payment_id):
                continue
            raise HTTPException(409, "El movimiento tiene una referencia financiera activa; requiere conciliación antes de editar o borrar.")


async def check_goal_contribution(db, user_id, contribution, session):
    """Verify historical transfer direction without using today's goal account."""
    tx = None
    if contribution.get("transaction_id"):
        tx = await db.transactions.find_one(
            {"id": contribution["transaction_id"], "user_id": user_id}, session=session)
        kind = contribution.get("kind")
        endpoint = "account_id" if kind == "deposit" else "to_account_id"
        if (not tx or kind not in ("deposit", "withdrawal")
                or tx.get("id") != contribution["transaction_id"]
                or tx.get("goal_id") != contribution.get("goal_id")
                or tx.get("goal_contribution_id") != contribution.get("id")
                or tx.get("type") != "transfer"
                or not _same_amount(tx.get("amount"), contribution.get("amount"))
                or not tx.get("account_id") or not tx.get("to_account_id")
                or tx["account_id"] == tx["to_account_id"]
                or not contribution.get("account_id")
                or contribution["account_id"] != tx.get(endpoint)):
            raise HTTPException(409, "El aporte requiere conciliación con su transferencia.")
    elif contribution.get("real_movement"):
        raise HTTPException(409, "El aporte no tiene su transferencia verificable.")
    async for linked in db.transactions.find(
            {"goal_contribution_id": contribution["id"], "user_id": user_id}, session=session):
        if not tx or linked.get("id") != tx["id"]:
            raise HTTPException(409, "El aporte tiene movimientos adicionales incoherentes.")
    return tx


async def check_record(db, user_id, rec, session):
    """Check both ends before unlinking a recurring record or its expense."""
    tx = None
    if rec.get("transaction_id"):
        if rec.get("mode") not in ("expense", "link"):
            raise HTTPException(409, "El modo del registro no corresponde a su movimiento.")
        tx = await db.transactions.find_one({"id": rec["transaction_id"], "user_id": user_id}, session=session)
        if (not tx or tx.get("recurring_record_id") != rec["id"]
                or tx.get("recurring_payment_id") != rec["recurring_id"]
                or not _same_optional_reference(tx.get("account_id"), rec.get("account_id"))
                or not _same_optional_reference(tx.get("category_id"), rec.get("category_id"))
                or not _same_amount(tx.get("amount"), rec.get("amount")) or tx.get("type") != "expense"):
            raise HTTPException(409, "El registro recurrente requiere conciliación con su movimiento.")
    elif rec.get("mode") != "mark":
        raise HTTPException(409, "El registro recurrente no tiene su movimiento verificable.")
    async for linked in db.transactions.find({"recurring_record_id": rec["id"], "user_id": user_id}, session=session):
        if not tx or linked["id"] != tx["id"]:
            raise HTTPException(409, "El registro recurrente tiene movimientos adicionales incoherentes.")
    async for linked in db.bill_payments.find(
            {"recurring_record_id": rec["id"], "user_id": user_id, "deleted": {"$ne": True}}, session=session):
        if linked["id"] != rec.get("bill_payment_id"):
            raise HTTPException(409, "El vínculo inverso del registro con la factura es incoherente.")
    if rec.get("bill_payment_id"):
        if rec.get("mode") != "link":
            raise HTTPException(409, "Un registro compartido con factura debe conservar su gasto.")
        payment = await db.bill_payments.find_one(
            {"id": rec["bill_payment_id"], "user_id": user_id, "deleted": {"$ne": True}}, session=session)
        if (not payment or payment.get("recurring_record_id") != rec["id"]
                or payment.get("transaction_id") != rec.get("transaction_id")
                or not _matches_bill_movement(payment, tx)):
            raise HTTPException(409, "El registro recurrente requiere conciliación con su factura.")
    elif tx and tx.get("bill_payment_id"):
        raise HTTPException(409, "El vínculo del registro con la factura es incoherente.")
    return tx


async def check_bill_payment(db, user_id, payment, session):
    tx = await db.transactions.find_one(
        {"id": payment.get("transaction_id"), "user_id": user_id}, session=session)
    if not _matches_bill_movement(payment, tx):
        raise HTTPException(409, "El pago de factura requiere conciliación con su movimiento.")
    async for linked in db.transactions.find({"bill_payment_id": payment["id"], "user_id": user_id}, session=session):
        if linked["id"] != tx["id"]:
            raise HTTPException(409, "El pago tiene movimientos adicionales incoherentes.")
    async for linked in db.recurring_payment_records.find(
            {"bill_payment_id": payment["id"], "user_id": user_id, "deleted": {"$ne": True}}, session=session):
        if linked["id"] != payment.get("recurring_record_id"):
            raise HTTPException(409, "El vínculo inverso del pago con la recurrencia es incoherente.")
    if payment.get("recurring_record_id"):
        rec = await db.recurring_payment_records.find_one(
            {"id": payment["recurring_record_id"], "user_id": user_id, "deleted": {"$ne": True}}, session=session)
        if not rec or rec.get("bill_payment_id") != payment["id"]:
            raise HTTPException(409, "El pago de factura requiere conciliación con su registro recurrente.")
        await check_record(db, user_id, rec, session)
    elif tx.get("recurring_record_id"):
        raise HTTPException(409, "El vínculo del pago con la recurrencia es incoherente.")
    return tx


async def retire(db, collection, doc, user_id, session):
    """Keep keyed receipts as tombstones: a retry must never recreate an annulment."""
    target = getattr(db, collection)
    query = {"id": doc["id"], "user_id": user_id}
    await target.update_one(query, {"$set": {"deleted": True}}, session=session)
