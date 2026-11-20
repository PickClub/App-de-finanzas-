"""Shared validation for ordinary movement writes."""
import math

from fastapi import HTTPException
from pydantic import BaseModel

from backend.reference_integrity import coordinate


class TransactionCreate(BaseModel):
    name: str
    amount: float
    type: str
    date: str | None = None
    category_id: str | None = None
    account_id: str | None = None
    to_account_id: str | None = None
    debt_id: str | None = None
    notes: str | None = None


async def validate_movement(db, owner, projection, payload, old=None, session=None):
    """Validate writes without revalidating unchanged legacy financial fields."""
    def changed(field):
        return old is None or payload.get(field) != old.get(field)

    if changed("type") and payload["type"] not in (
        "income", "expense", "transfer", "debt_payment", "loan_given", "loan_received"
    ):
        raise HTTPException(422, "Tipo de movimiento desconocido.")
    if changed("amount") and (not math.isfinite(payload["amount"]) or payload["amount"] <= 0):
        raise HTTPException(422, "El importe debe ser positivo y finito.")
    if payload["type"] == "expense":
        source = payload.get("account_id")
        if not isinstance(source, str) or not source.strip() or not await db.accounts.find_one(
            {"id": source, "user_id": owner, "deleted": {"$ne": True}}, projection, session=session
        ):
            raise HTTPException(422, "Select a valid source account for this expense.")
    for field, collection in (("account_id", db.accounts), ("to_account_id", db.accounts),
                              ("category_id", db.categories)):
        value = payload.get(field)
        if changed(field) and value is not None:
            if not await collection.find_one({"id": value, "user_id": owner}, projection, session=session):
                raise HTTPException(422, f"Referencia inválida: {field}.")
    # A transfer is one relationship: changing either endpoint or its type must
    # leave the whole relationship valid, even when the other endpoint is legacy.
    if payload["type"] == "transfer" and any(changed(f) for f in ("type", "account_id", "to_account_id")):
        source, target = payload.get("account_id"), payload.get("to_account_id")
        if not source or not target or source == target:
            raise HTTPException(422, "La transferencia requiere dos cuentas diferentes.")
        for aid in (source, target):
            if not await db.accounts.find_one({"id": aid, "user_id": owner}, projection, session=session):
                raise HTTPException(422, "La transferencia requiere cuentas existentes.")
    elif payload["type"] != "transfer" and payload.get("to_account_id") is not None and (
        changed("type") or changed("to_account_id")
    ):
        raise HTTPException(422, "La cuenta destino solo corresponde a transferencias.")
    # R1 already writes both accounts during balance recomputation; debt edits
    # also write their debt. Only the category was previously a read-only parent.
    await coordinate(db, owner, {"category_id": payload.get("category_id")}, session, old)


def edit_payload(data, old, now, *, preserve_missing_date=False):
    """Preserve omitted fields and distinguish them from explicit nulls."""
    payload = data.model_dump()
    supplied = data.model_fields_set
    for field in payload:
        if field not in supplied and field in old:
            payload[field] = old[field]
    if preserve_missing_date and "date" not in supplied and "date" not in old:
        del payload["date"]
    elif not payload.get("date"):
        payload["date"] = old.get("date", now)
    return payload


def versioned_movement_update(update):
    """Advance the edit revision in the same write as the movement mutation."""
    return {**update, "$inc": {**update.get("$inc", {}), "revision": 1}}
