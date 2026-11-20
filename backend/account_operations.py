"""Shared account operations with an explicit owner and transaction session."""
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel


class AccountCreate(BaseModel):
    name: str
    type: Literal["cash", "checking", "savings", "credit_card", "wallet", "other"] = "cash"
    initial_balance: float = 0.0
    color: str = "#4C83EA"
    icon: str = "wallet-outline"
    currency: str = "USD"


async def recompute_balance(db, owner, account_id, projection, session):
    """Recompute an account's current balance from its initial + transactions."""
    acc = await db.accounts.find_one({"id": account_id, "user_id": owner}, projection, session=session)
    if not acc:
        return
    balance = acc["initial_balance"]
    async for tx in db.transactions.find({"user_id": owner}, projection, session=session):
        t = tx["type"]
        amt = tx["amount"]
        if tx.get("account_id") == account_id:
            if t == "income" or t == "loan_received":
                balance += amt
            elif t == "expense" or t == "debt_payment" or t == "loan_given":
                balance -= amt
            elif t == "transfer":
                balance -= amt
        if tx.get("to_account_id") == account_id and t == "transfer":
            balance += amt
    await db.accounts.update_one({"id": account_id, "user_id": owner}, {"$set": {"current_balance": round(balance, 2)}}, session=session)



async def delete_owned_account(db, owner, account_id, projection, session):
    if await db.debt_payments.find_one({"user_id": owner, "account_id": account_id, "deleted": {"$ne": True}}, projection, session=session):
        raise HTTPException(409, "La cuenta tiene pagos vinculados. Anúlalos primero desde el historial de la deuda antes de borrar la cuenta.")
    for field in ("account_id", "to_account_id"):
        if await db.transactions.find_one({"user_id": owner, field: account_id}, projection, session=session):
            raise HTTPException(409, "Esta cuenta tiene movimientos vinculados. Elimina o resuelve primero sus movimientos; los pagos se anulan desde el historial de deuda.")
    for collection, fields, label in ((db.debts, ("account_id",), "deudas"),
                                      (db.recurring_templates, ("account_id", "to_account_id"), "plantillas recurrentes"),
                                      (db.bills, ("account_id",), "facturas"),
                                      (db.recurring_payments, ("account_id",), "pagos recurrentes"),
                                      (db.saving_goals, ("account_id",), "metas de ahorro"),
                                      (db.goal_contributions, ("account_id",), "aportes de ahorro")):
        for field in fields:
            if await collection.find_one({"user_id": owner, field: account_id, "deleted": {"$ne": True}}, projection, session=session):
                raise HTTPException(409, f"Esta cuenta está vinculada a {label}. Resuelve ese vínculo antes de eliminarla.")
    for collection in (db.bill_payments, db.recurring_payment_records):
        if await collection.find_one({"user_id": owner, "account_id": account_id, "deleted": {"$ne": True}}, projection, session=session):
            raise HTTPException(409, "La cuenta tiene registros financieros activos vinculados.")
    await db.accounts.delete_one({"id": account_id, "user_id": owner}, session=session)
    return {"ok": True}
