"""Debt and payment operations using an explicit owner and one transaction."""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Literal, Optional
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.account_operations import recompute_balance
from backend.history_keys import history_update_fields, with_history_keys
from backend.movement_operations import TransactionCreate, edit_payload, validate_movement
from backend.reference_integrity import check_movement_references, coordinate, public as reference_public

PROJ = {"_id": 0}
INTERNAL_PROJ = PROJ


def new_id():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Debt(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    name: str
    direction: Literal["i_owe", "they_owe"]
    person: Optional[str] = None
    original_amount: float
    remaining_amount: float
    total_paid: float = 0.0
    start_date: str = Field(default_factory=now_iso)
    due_date: Optional[str] = None
    minimum_payment: float = 0.0
    payment_frequency: Literal["weekly", "biweekly", "monthly", "none"] = "monthly"
    interest_rate: float = 0.0
    status: Literal["active", "paid"] = "active"
    notes: Optional[str] = None
    color: str = "#F5B83B"
    icon: str = "cash-outline"
    account_id: Optional[str] = None
    category_id: Optional[str] = None


class DebtCreate(BaseModel):
    name: str
    direction: str
    person: Optional[str] = None
    original_amount: float
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    minimum_payment: float = 0.0
    payment_frequency: str = "monthly"
    interest_rate: float = 0.0
    notes: Optional[str] = None
    color: str = "#F5B83B"
    icon: str = "cash-outline"
    account_id: Optional[str] = None
    category_id: Optional[str] = None


class DebtPayment(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
    debt_id: str
    amount: float
    date: str = Field(default_factory=now_iso)
    account_id: Optional[str] = None
    notes: Optional[str] = None
    transaction_id: Optional[str] = None
    settlement_source: Literal["account", "external"] | None = None


class DebtPaymentCreate(BaseModel):
    settlement_source: Literal["account", "external"] | None = None
    debt_id: str
    amount: float = Field(gt=0, allow_inf_nan=False)
    date: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("amount", mode="before")
    @classmethod
    def serializable_invalid_amount(cls, value):
        # Keep NaN/Infinity out of FastAPI's JSON validation-error response.
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        return value


async def recompute_debt(db, owner, debt_id: str, session):
    d = await db.debts.find_one({"id": debt_id, "user_id": owner}, PROJ, session=session)
    if not d:
        return
    total_paid = 0.0
    async for p in db.debt_payments.find({"debt_id": debt_id, "user_id": owner, "deleted": {"$ne": True}}, PROJ, session=session):
        total_paid += p["amount"]
    remaining = max(0.0, d["original_amount"] - total_paid)
    status = "paid" if remaining <= 0.0001 else "active"
    await db.debts.update_one(
        {"id": debt_id, "user_id": owner},
        {"$set": {"total_paid": round(total_paid, 2), "remaining_amount": round(remaining, 2), "status": status}},
        session=session,
    )



async def validate_payment(db, owner, debt_id, amount, account_id, session, replacing=None):
    if not math.isfinite(amount) or amount <= 0:
        raise HTTPException(422, "El importe debe ser positivo y finito.")
    debt = await db.debts.find_one({"id": debt_id, "user_id": owner}, PROJ, session=session)
    if not debt:
        raise HTTPException(404, "Debt not found")
    if debt["direction"] not in ("i_owe", "they_owe") or not math.isfinite(debt["original_amount"]):
        raise HTTPException(409, "La deuda requiere revisión antes de registrar pagos.")
    if account_id is not None:
        account = await db.accounts.find_one({"id": account_id, "user_id": owner, "deleted": {"$ne": True}}, PROJ, session=session)
        if not account:
            raise HTTPException(404, "Account not found")
    paid = 0.0
    async for payment in db.debt_payments.find({"debt_id": debt_id, "user_id": owner, "deleted": {"$ne": True}}, PROJ, session=session):
        if payment["id"] != replacing:
            paid += payment["amount"]
    if amount > debt["original_amount"] - paid + 1e-9:
        raise HTTPException(422, "El pago supera el saldo pendiente.")
    return debt


async def payment_movement(db, owner, payment, session):
    """Legacy records have no reliable one-to-one link; never guess by amount."""
    tid = payment.get("transaction_id")
    if not tid:
        raise HTTPException(409, "Pago antiguo sin vínculo individual: requiere conciliación antes de editar o borrar.")
    tx = await db.transactions.find_one({"id": tid, "user_id": owner}, PROJ, session=session)
    if not tx or tx.get("debt_payment_id") != payment["id"] or any(
        tx.get(field) != payment.get(field) for field in ("debt_id", "amount", "account_id", "settlement_source")
    ):
        raise HTTPException(409, "El vínculo del pago requiere conciliación.")
    debt = await db.debts.find_one({"id": payment["debt_id"], "user_id": owner}, PROJ, session=session)
    if not debt:
        raise HTTPException(409, "La deuda del pago no existe; requiere conciliación.")
    expected_type = "debt_payment" if debt["direction"] == "i_owe" else "income"
    if debt["direction"] not in ("i_owe", "they_owe") or tx["type"] != expected_type or tx.get("to_account_id"):
        raise HTTPException(409, "El tipo del movimiento no coincide con su deuda.")
    if payment.get("account_id") and not await db.accounts.find_one({"id": payment["account_id"], "user_id": owner}, PROJ, session=session):
        raise HTTPException(409, "La cuenta del pago no existe; requiere conciliación.")
    return tx


async def remove_payment(db, owner, pid, session):
    payment = await db.debt_payments.find_one({"id": pid, "user_id": owner}, PROJ, session=session)
    if not payment or payment.get("deleted"):
        return {"ok": True}
    tx = await payment_movement(db, owner, payment, session)
    if await db.recurring_templates.find_one({"source_transaction_id": tx["id"], "user_id": owner}, PROJ, session=session):
        raise HTTPException(409, "El movimiento de este pago es origen de una recurrencia. Elimina primero esa configuración de recurrencia.")
    await db.transactions.delete_one({"id": tx["id"], "user_id": owner}, session=session)
    if payment.get("request_fingerprint"):
        # Retain a tombstone so a delayed POST retry cannot resurrect a payment.
        await db.debt_payments.update_one({"id": pid, "user_id": owner}, {"$set": {"deleted": True}}, session=session)
    else:
        await db.debt_payments.delete_one({"id": pid, "user_id": owner}, session=session)
    await recompute_debt(db, owner, payment["debt_id"], session=session)
    if payment.get("account_id"):
        await recompute_balance(db, owner, payment["account_id"], PROJ, session)
    return {"ok": True}



def payment_id(owner, key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{owner}:debt-payment:{key}"))


def payment_request(data):
    payload = data.model_dump()
    # Preserve fingerprints of original requests issued before source selection.
    if payload.get("settlement_source") is None:
        payload.pop("settlement_source", None)
    return payload


def payment_fingerprint(data):
    return hashlib.sha256(json.dumps(payment_request(data), sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_settlement(source, account_id):
    if source not in ("account", "external"):
        raise HTTPException(422, "Choose an account or an external settlement.")
    if (source == "account" and (not isinstance(account_id, str) or not account_id.strip())) or (
        source == "external" and account_id is not None
    ):
        raise HTTPException(422, "Settlement source and account must agree.")



async def create_debt(db, owner, data, session):
    payload = data.model_dump()
    payload["start_date"] = data.start_date or now_iso()
    record = Debt(user_id=owner, remaining_amount=data.original_amount, **payload).model_dump()
    await coordinate(db, owner, payload, session)
    await db.debts.insert_one(record.copy(), session=session)
    return reference_public(record)


async def update_debt(db, owner, did, data, session):
    old = await db.debts.find_one({"id": did, "user_id": owner}, PROJ, session=session)
    if not old:
        raise HTTPException(404, "Debt not found")
    payments = db.debt_payments.find({"debt_id": did, "user_id": owner, "deleted": {"$ne": True}}, PROJ, session=session)
    paid, has_payments = 0.0, False
    async for payment in payments:
        paid += payment["amount"]
        has_payments = True
    if has_payments and data.direction != old["direction"]:
        raise HTTPException(409, "No se puede cambiar la dirección de una deuda con pagos.")
    if not math.isfinite(data.original_amount) or data.original_amount < paid or data.original_amount < 0:
        raise HTTPException(422, "El importe de la deuda no puede ser menor que lo pagado.")
    payload = data.model_dump()
    for field in ("account_id", "category_id"):
        if field not in data.model_fields_set:
            payload[field] = old.get(field)
    await coordinate(db, owner, payload, session, old)
    payload["start_date"] = data.start_date or old["start_date"]
    await db.debts.update_one({"id": did, "user_id": owner}, {"$set": payload}, session=session)
    await recompute_debt(db, owner, did, session=session)
    return await db.debts.find_one({"id": did, "user_id": owner}, PROJ, session=session)


async def delete_debt(db, owner, did, session):
    if await db.debt_payments.find_one({"debt_id": did, "user_id": owner, "deleted": {"$ne": True}}, PROJ, session=session) or await db.transactions.find_one({"debt_id": did, "user_id": owner}, PROJ, session=session):
        raise HTTPException(409, "La deuda tiene pagos o movimientos vinculados; anúlalos antes de borrarla.")
    await db.debts.delete_one({"id": did, "user_id": owner}, session=session)
    return {"ok": True}


async def create_payment(db, owner, data, key, session, history_generation=None, *, unkeyed_id=None, now=None):
    pid = payment_id(owner, key) if key else unkeyed_id or new_id()
    now = now or now_iso()
    tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"debt-payment-movement:{pid}"))
    fingerprint = payment_fingerprint(data)
    payload = payment_request(data)
    payload["date"] = data.date or now
    previous = await db.debt_payments.find_one({"_id": pid, "user_id": owner}, session=session)
    if previous:
        if previous.get("request_fingerprint") != fingerprint:
            raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
        if previous.get("deleted"):
            raise HTTPException(409, "La operación ya fue anulada; no se volverá a crear.")
        return DebtPayment(**previous).model_dump()
    # R3 models expose the explicit contract; the legacy development adapter
    # keeps its original schema and semantics.
    if hasattr(data, "settlement_source"):
        validate_settlement(data.settlement_source, data.account_id)
    debt = await validate_payment(db, owner, data.debt_id, data.amount, data.account_id, session)
    # Existing recomputations write the debt/account parents in this session.
    payment = DebtPayment(id=pid, transaction_id=tid, user_id=owner, **payload).model_dump()
    tx = {
        "id": tid, "debt_payment_id": pid, "user_id": owner, "name": f"Pago: {debt['name']}",
        "amount": data.amount, "type": "debt_payment" if debt["direction"] == "i_owe" else "income",
        "date": payload["date"], "account_id": data.account_id, "debt_id": data.debt_id,
        "notes": data.notes, "to_account_id": None, "category_id": None, "created_at": now,
    }
    if payload.get("settlement_source") is not None:
        tx["settlement_source"] = payload["settlement_source"]
    # MongoDB's existing unique _id index also arbitrates concurrent retries.
    stored_payment = dict(payment, _id=pid)
    if key:
        stored_payment["request_fingerprint"] = fingerprint
    await db.debt_payments.insert_one(stored_payment, session=session)
    stored_movement = dict(tx, _id=tid)
    if history_generation is not None:
        stored_movement = with_history_keys(stored_movement, history_generation)
    await db.transactions.insert_one(stored_movement, session=session)
    await recompute_debt(db, owner, data.debt_id, session=session)
    if data.account_id:
        await recompute_balance(db, owner, data.account_id, PROJ, session)
    return payment


async def reconcile_payment(db, owner, data, key, session):
    pid = payment_id(owner, key)
    fingerprint = payment_fingerprint(data)
    original = payment_request(data)

    def response(status, reason=None, **extra):
        return {"status": status, "reason": reason, "payment_id": pid,
                "retry_requires_original_key_and_payload": True, **extra}

    payment = await db.debt_payments.find_one({"_id": pid, "user_id": owner}, session=session)
    if not payment:
        return response("not_found", "No existe un registro visible para esta clave en este snapshot; no autoriza una clave nueva.")
    stored_hash = payment.get("request_fingerprint")
    if payment.get("id") != pid or not isinstance(stored_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", stored_hash):
        return response("unverifiable", "La identidad o huella original no es verificable.")
    if stored_hash != fingerprint:
        return response("discrepancy", "La clave corresponde a otra solicitud original.",
                        original_request_matches=False, annulled=payment.get("deleted") is True)
    if payment.get("deleted") is True:
        if await db.transactions.find_one({"debt_payment_id": pid, "user_id": owner}, PROJ, session=session):
            return response("unverifiable", "El pago anulado conserva un movimiento; requiere revisión.")
        return response("cancelled", original_request_matches=True)
    if payment.get("deleted") is not None and type(payment["deleted"]) is not bool:
        return response("unverifiable", "El estado de anulación es inválido.")
    if (not isinstance(payment.get("amount"), (int, float)) or isinstance(payment.get("amount"), bool)
            or not math.isfinite(payment["amount"]) or payment["amount"] <= 0
            or not isinstance(payment.get("date"), str) or not payment["date"]
            or not payment.get("transaction_id")):
        return response("unverifiable", "El estado actual del pago requiere revisión.")
    try:
        movement = await payment_movement(db, owner, payment, session)
    except HTTPException:
        return response("unverifiable", "No se puede verificar el vínculo financiero actual.")
    if any(movement.get(field) != payment.get(field) for field in ("date", "notes")):
        return response("unverifiable", "El movimiento y el pago tienen datos actuales diferentes.")
    changed = [field for field in ("debt_id", "amount", "account_id", "notes", "settlement_source")
               if payment.get(field) != original.get(field)]
    if original["date"] is not None and payment["date"] != original["date"]:
        changed.append("date")
    # Date=None was an original request value, not the server-generated date.
    # Its original hash is fully verifiable; later changes to the generated
    # date cannot be inferred from the retained records.
    current = {field: payment.get(field) for field in
               ("id", "user_id", "debt_id", "amount", "date", "account_id", "notes", "transaction_id", "settlement_source")}
    return response("matched", original_request_matches=True, current_payment=current,
                    changed_fields=changed, generated_date_history_verifiable=original["date"] is not None,
                    current_submission_matches=(False if changed else True if original["date"] is not None else None))


async def edit_payment(db, owner, tid, data, session, history_generation=None):
    old = await db.transactions.find_one({"id": tid, "user_id": owner}, INTERNAL_PROJ, session=session)
    if not old:
        raise HTTPException(404, "Not found")
    payment = await db.debt_payments.find_one({"id": old.get("debt_payment_id"), "user_id": owner, "deleted": {"$ne": True}}, PROJ, session=session)
    if not payment or (await payment_movement(db, owner, payment, session))["id"] != tid:
        raise HTTPException(409, "El movimiento requiere conciliación con su pago.")
    await check_movement_references(db, owner, old, session, debt_payment_id=payment["id"])
    payload = edit_payload(data, old, now_iso())
    if "settlement_source" not in data.model_fields_set and "settlement_source" not in old:
        payload.pop("settlement_source", None)
    source = payload.get("settlement_source")
    if hasattr(data, "settlement_source") and (
        source is not None or "settlement_source" in data.model_fields_set
        or payload.get("account_id") != old.get("account_id")
    ):
        validate_settlement(source, payload.get("account_id"))
    effective = TransactionCreate(**payload)
    if effective.debt_id not in (None, payment["debt_id"]) or effective.type != old["type"] or effective.to_account_id is not None:
        raise HTTPException(409, "No se puede cambiar la deuda ni el tipo de un pago vinculado.")
    await validate_payment(db, owner, payment["debt_id"], effective.amount, effective.account_id, session, replacing=payment["id"])
    await validate_movement(db, owner, PROJ, payload, old, session)
    payload.update(debt_id=payment["debt_id"], date=effective.date or old["date"])
    changes = dict(payload)
    if history_generation is not None:
        final = {**old, **payload}
        changes.update(history_update_fields(old, final, history_generation))
    await db.transactions.update_one({"id": tid, "user_id": owner}, {"$set": changes}, session=session)
    payment_changes = {field: payload[field] for field in ("amount", "date", "account_id", "notes")}
    if "settlement_source" in payload:
        payment_changes["settlement_source"] = payload["settlement_source"]
    await db.debt_payments.update_one({"id": payment["id"], "user_id": owner},
                                    {"$set": payment_changes}, session=session)
    await recompute_debt(db, owner, payment["debt_id"], session=session)
    for aid in sorted({payment.get("account_id"), effective.account_id} - {None}):
        await recompute_balance(db, owner, aid, PROJ, session)
    return await db.transactions.find_one({"id": tid, "user_id": owner}, PROJ, session=session)
