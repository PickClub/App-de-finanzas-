from fastapi import FastAPI, APIRouter, Header, HTTPException
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import logging, uuid, hashlib, json, math
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import datetime, timezone
from pymongo import ReadPreference
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

if __package__:
    from .config import load_settings
else:
    from config import load_settings

settings = load_settings()
client = AsyncIOMotorClient(settings.mongo_url)
db = client[settings.db_name]

app = FastAPI(title="MoneyFlow API")
api = APIRouter(prefix="/api")

DEFAULT_USER_ID = "default-user"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return str(uuid.uuid4())


# ---------- Models ----------
class User(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str = "Usuario"
    email: Optional[str] = None
    profile_photo: Optional[str] = None
    currency: str = "USD"


class Account(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = DEFAULT_USER_ID
    name: str
    type: Literal["cash", "checking", "savings", "credit_card", "wallet", "other"] = "cash"
    initial_balance: float = 0.0
    current_balance: float = 0.0
    color: str = "#4C83EA"
    icon: str = "wallet-outline"
    currency: str = "USD"
    created_at: str = Field(default_factory=now_iso)


class AccountCreate(BaseModel):
    name: str
    type: str = "cash"
    initial_balance: float = 0.0
    color: str = "#4C83EA"
    icon: str = "wallet-outline"
    currency: str = "USD"


class Category(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = DEFAULT_USER_ID
    name: str
    type: Literal["income", "expense"] = "expense"
    icon: str = "pricetag-outline"
    color: str = "#FF8A3D"


class CategoryCreate(BaseModel):
    name: str
    type: str = "expense"
    icon: str = "pricetag-outline"
    color: str = "#FF8A3D"


class Transaction(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = DEFAULT_USER_ID
    name: str
    amount: float
    type: Literal["income", "expense", "transfer", "debt_payment", "loan_given", "loan_received"]
    date: str = Field(default_factory=now_iso)
    category_id: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    debt_id: Optional[str] = None
    debt_payment_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)


class TransactionCreate(BaseModel):
    name: str
    amount: float
    type: str
    date: Optional[str] = None
    category_id: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    debt_id: Optional[str] = None
    notes: Optional[str] = None


class RecurringTemplate(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = DEFAULT_USER_ID
    source_transaction_id: Optional[str] = None
    name: str
    amount: float
    type: str
    category_id: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    notes: Optional[str] = None
    frequency: Literal["weekly", "biweekly", "monthly", "custom"] = "monthly"
    interval_days: Optional[int] = None
    start_date: str = Field(default_factory=now_iso)
    end_date: Optional[str] = None
    active: bool = True
    created_at: str = Field(default_factory=now_iso)


class RecurringCreate(BaseModel):
    source_transaction_id: Optional[str] = None
    name: str
    amount: float
    type: str
    category_id: Optional[str] = None
    account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    notes: Optional[str] = None
    frequency: str = "monthly"
    interval_days: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class Budget(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = DEFAULT_USER_ID
    name: str
    amount_limit: float
    period: Literal["weekly", "monthly", "custom"] = "monthly"
    start_date: str = Field(default_factory=now_iso)
    end_date: Optional[str] = None
    category_id: Optional[str] = None


class BudgetCreate(BaseModel):
    name: str
    amount_limit: float
    period: str = "monthly"
    category_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class SavingGoal(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = DEFAULT_USER_ID
    name: str
    target_amount: float
    current_amount: float = 0.0
    target_date: Optional[str] = None
    priority: Literal["low", "medium", "high"] = "medium"
    color: str = "#29C4A9"
    icon: str = "flag-outline"


class SavingGoalCreate(BaseModel):
    name: str
    target_amount: float
    current_amount: float = 0.0
    target_date: Optional[str] = None
    priority: str = "medium"
    color: str = "#29C4A9"
    icon: str = "flag-outline"


class Debt(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = DEFAULT_USER_ID
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
    user_id: str = DEFAULT_USER_ID
    debt_id: str
    amount: float
    date: str = Field(default_factory=now_iso)
    account_id: Optional[str] = None
    notes: Optional[str] = None
    transaction_id: Optional[str] = None


class DebtPaymentCreate(BaseModel):
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


class UserUpdate(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None
    profile_photo: Optional[str] = None


PROJ = {"_id": 0}


# ---------- Utilities ----------
async def ensure_user():
    u = await db.users.find_one({"id": DEFAULT_USER_ID}, PROJ)
    if not u:
        user = User(id=DEFAULT_USER_ID, name="Usuario").model_dump()
        await db.users.insert_one(user)
        return user
    return u


async def recompute_account_balance(account_id: str, session=None):
    """Recompute an account's current balance from its initial + transactions."""
    acc = await db.accounts.find_one({"id": account_id}, PROJ, session=session)
    if not acc:
        return
    balance = acc["initial_balance"]
    async for tx in db.transactions.find({"user_id": DEFAULT_USER_ID}, PROJ, session=session):
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
    await db.accounts.update_one({"id": account_id}, {"$set": {"current_balance": round(balance, 2)}}, session=session)


async def recompute_debt(debt_id: str, session=None):
    d = await db.debts.find_one({"id": debt_id}, PROJ, session=session)
    if not d:
        return
    total_paid = 0.0
    async for p in db.debt_payments.find({"debt_id": debt_id, "deleted": {"$ne": True}}, PROJ, session=session):
        total_paid += p["amount"]
    remaining = max(0.0, d["original_amount"] - total_paid)
    status = "paid" if remaining <= 0.0001 else "active"
    await db.debts.update_one(
        {"id": debt_id},
        {"$set": {"total_paid": round(total_paid, 2), "remaining_amount": round(remaining, 2), "status": status}},
        session=session,
    )


async def payment_transaction(operation):
    """Never fall back to partial writes on a standalone/unavailable MongoDB."""
    for attempt in range(2):
        try:
            async with await client.start_session() as session:
                return await session.with_transaction(
                    operation,
                    read_concern=ReadConcern("snapshot"),
                    write_concern=WriteConcern("majority"),
                    read_preference=ReadPreference.PRIMARY,
                )
        except DuplicateKeyError:
            # A concurrent request may have committed the same idempotency key.
            if attempt == 0:
                continue
            raise HTTPException(409, "Conflicto de operación; reintenta con la misma clave.")
        except PyMongoError:
            # A lost commit response can mean all writes committed. Do not claim
            # rollback here: callers must reuse their Idempotency-Key on retry.
            raise HTTPException(503, "No se pudo confirmar la operación atómica. MongoDB debe admitir transacciones; reintenta con la misma Idempotency-Key.")


async def validate_payment(debt_id, amount, account_id, session, replacing=None):
    if not math.isfinite(amount) or amount <= 0:
        raise HTTPException(422, "El importe debe ser positivo y finito.")
    debt = await db.debts.find_one({"id": debt_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    if not debt:
        raise HTTPException(404, "Debt not found")
    if debt["direction"] not in ("i_owe", "they_owe") or not math.isfinite(debt["original_amount"]):
        raise HTTPException(409, "La deuda requiere revisión antes de registrar pagos.")
    if account_id is not None:
        account = await db.accounts.find_one({"id": account_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
        if not account:
            raise HTTPException(404, "Account not found")
    paid = 0.0
    async for payment in db.debt_payments.find({"debt_id": debt_id, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, PROJ, session=session):
        if payment["id"] != replacing:
            paid += payment["amount"]
    if amount > debt["original_amount"] - paid + 1e-9:
        raise HTTPException(422, "El pago supera el saldo pendiente.")
    return debt


async def payment_movement(payment, session):
    """Legacy records have no reliable one-to-one link; never guess by amount."""
    tid = payment.get("transaction_id")
    if not tid:
        raise HTTPException(409, "Pago antiguo sin vínculo individual: requiere conciliación antes de editar o borrar.")
    tx = await db.transactions.find_one({"id": tid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    if not tx or tx.get("debt_payment_id") != payment["id"] or any(
        tx.get(field) != payment.get(field) for field in ("debt_id", "amount", "account_id")
    ):
        raise HTTPException(409, "El vínculo del pago requiere conciliación.")
    debt = await db.debts.find_one({"id": payment["debt_id"], "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    if not debt:
        raise HTTPException(409, "La deuda del pago no existe; requiere conciliación.")
    expected_type = "debt_payment" if debt["direction"] == "i_owe" else "income"
    if debt["direction"] not in ("i_owe", "they_owe") or tx["type"] != expected_type or tx.get("to_account_id"):
        raise HTTPException(409, "El tipo del movimiento no coincide con su deuda.")
    if payment.get("account_id") and not await db.accounts.find_one({"id": payment["account_id"], "user_id": DEFAULT_USER_ID}, PROJ, session=session):
        raise HTTPException(409, "La cuenta del pago no existe; requiere conciliación.")
    return tx


async def remove_payment(pid, session):
    payment = await db.debt_payments.find_one({"id": pid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    if not payment or payment.get("deleted"):
        return {"ok": True}
    tx = await payment_movement(payment, session)
    await db.transactions.delete_one({"id": tx["id"], "user_id": DEFAULT_USER_ID}, session=session)
    if payment.get("request_fingerprint"):
        # Retain a tombstone so a delayed POST retry cannot resurrect a payment.
        await db.debt_payments.update_one({"id": pid, "user_id": DEFAULT_USER_ID}, {"$set": {"deleted": True}}, session=session)
    else:
        await db.debt_payments.delete_one({"id": pid, "user_id": DEFAULT_USER_ID}, session=session)
    await recompute_debt(payment["debt_id"], session=session)
    if payment.get("account_id"):
        await recompute_account_balance(payment["account_id"], session=session)
    return {"ok": True}


async def edit_payment_movement(tid, data):
    async def operation(session):
        old = await db.transactions.find_one({"id": tid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
        if not old:
            raise HTTPException(404, "Not found")
        payment = await db.debt_payments.find_one({"id": old.get("debt_payment_id"), "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, PROJ, session=session)
        if not payment or (await payment_movement(payment, session))["id"] != tid:
            raise HTTPException(409, "El movimiento requiere conciliación con su pago.")
        if data.debt_id not in (None, payment["debt_id"]) or data.type != old["type"] or data.to_account_id is not None:
            raise HTTPException(409, "No se puede cambiar la deuda ni el tipo de un pago vinculado.")
        await validate_payment(payment["debt_id"], data.amount, data.account_id, session, replacing=payment["id"])
        payload = data.model_dump()
        payload.update(debt_id=payment["debt_id"], date=data.date or old["date"])
        await db.transactions.update_one({"id": tid, "user_id": DEFAULT_USER_ID}, {"$set": payload}, session=session)
        await db.debt_payments.update_one({"id": payment["id"], "user_id": DEFAULT_USER_ID}, {"$set": {
            field: payload[field] for field in ("amount", "date", "account_id", "notes")
        }}, session=session)
        await recompute_debt(payment["debt_id"], session=session)
        for aid in sorted({payment.get("account_id"), data.account_id} - {None}):
            await recompute_account_balance(aid, session=session)
        return await db.transactions.find_one({"id": tid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    return await payment_transaction(operation)


# ---------- Routes ----------
@api.get("/")
async def root():
    return {"message": "MoneyFlow API"}


# User
@api.get("/user")
async def get_user():
    u = await ensure_user()
    return u


@api.put("/user")
async def update_user(data: UserUpdate):
    await ensure_user()
    upd = {k: v for k, v in data.model_dump().items() if v is not None}
    if upd:
        await db.users.update_one({"id": DEFAULT_USER_ID}, {"$set": upd})
    return await db.users.find_one({"id": DEFAULT_USER_ID}, PROJ)


# Accounts
@api.get("/accounts")
async def list_accounts():
    return await db.accounts.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(500)


@api.post("/accounts")
async def create_account(data: AccountCreate):
    acc = Account(user_id=DEFAULT_USER_ID, current_balance=data.initial_balance, **data.model_dump()).model_dump()
    await db.accounts.insert_one(acc)
    return {k: v for k, v in acc.items() if k != "_id"}


@api.put("/accounts/{account_id}")
async def update_account(account_id: str, data: AccountCreate):
    await db.accounts.update_one({"id": account_id}, {"$set": data.model_dump()})
    await recompute_account_balance(account_id)
    return await db.accounts.find_one({"id": account_id}, PROJ)


@api.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    async def operation(session):
        if await db.debt_payments.find_one({"account_id": account_id, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, PROJ, session=session):
            raise HTTPException(409, "La cuenta tiene pagos vinculados; anúlalos antes de borrarla.")
        if await db.transactions.find_one({"account_id": account_id, "user_id": DEFAULT_USER_ID, "debt_id": {"$ne": None}}, PROJ, session=session):
            raise HTTPException(409, "La cuenta tiene movimientos de deuda; requieren conciliación antes de borrarla.")
        await db.accounts.delete_one({"id": account_id, "user_id": DEFAULT_USER_ID}, session=session)
        return {"ok": True}
    return await payment_transaction(operation)


# Categories
@api.get("/categories")
async def list_categories():
    return await db.categories.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(500)


@api.post("/categories")
async def create_category(data: CategoryCreate):
    cat = Category(user_id=DEFAULT_USER_ID, **data.model_dump()).model_dump()
    await db.categories.insert_one(cat)
    return {k: v for k, v in cat.items() if k != "_id"}


@api.put("/categories/{cid}")
async def update_category(cid: str, data: CategoryCreate):
    await db.categories.update_one({"id": cid}, {"$set": data.model_dump()})
    return await db.categories.find_one({"id": cid}, PROJ)


@api.delete("/categories/{cid}")
async def delete_category(cid: str):
    await db.categories.delete_one({"id": cid})
    return {"ok": True}


# Default category catalog (name, icon, soft color). Additive only — this does
# NOT touch transactions, accounts, balances or any calculation logic.
DEFAULT_EXPENSE_CATEGORIES = [
    ("Food", "fast-food-outline", "#FF7A59"),
    ("Groceries", "cart-outline", "#F5A623"),
    ("Restaurants", "restaurant-outline", "#FF5E7E"),
    ("Housing", "home-outline", "#7C6CF0"),
    ("Rent", "business-outline", "#5B8DEF"),
    ("Utilities", "bulb-outline", "#F2B84B"),
    ("Transportation", "bus-outline", "#4C9AFF"),
    ("Fuel", "flame-outline", "#E8603C"),
    ("Car", "car-sport-outline", "#6C8AE4"),
    ("Shopping", "bag-handle-outline", "#FF8ACC"),
    ("Clothing", "shirt-outline", "#C86BFA"),
    ("Entertainment", "film-outline", "#9B6BFA"),
    ("Subscriptions", "repeat-outline", "#7B61FF"),
    ("Health", "medkit-outline", "#FF6B6B"),
    ("Pharmacy", "medical-outline", "#34C6A8"),
    ("Fitness", "barbell-outline", "#2FB67C"),
    ("Education", "school-outline", "#4C83EA"),
    ("Travel", "airplane-outline", "#22B8CF"),
    ("Pets", "paw-outline", "#C08457"),
    ("Family", "people-outline", "#FF9F68"),
    ("Gifts", "gift-outline", "#F06595"),
    ("Personal Care", "sparkles-outline", "#EC5F94"),
    ("Technology", "hardware-chip-outline", "#5C7CFA"),
    ("Insurance", "shield-checkmark-outline", "#51B7B0"),
    ("Taxes", "document-text-outline", "#B0A08F"),
    ("Loans", "cash-outline", "#E0A64B"),
    ("Credit Cards", "card-outline", "#8E7CC3"),
    ("Other", "ellipsis-horizontal-outline", "#9AA0A6"),
]

DEFAULT_INCOME_CATEGORIES = [
    ("Salary", "wallet-outline", "#2FB67C"),
    ("Freelance", "laptop-outline", "#3BC9B0"),
    ("Business", "briefcase-outline", "#5B8DEF"),
    ("Tips", "cash-outline", "#F2B84B"),
    ("Investments", "trending-up-outline", "#7C6CF0"),
    ("Interest", "stats-chart-outline", "#22B8CF"),
    ("Refunds", "arrow-undo-outline", "#63C77A"),
    ("Gifts", "gift-outline", "#F06595"),
    ("Sales", "pricetags-outline", "#FF9F43"),
    ("Other Income", "ellipsis-horizontal-outline", "#9AA0A6"),
]


@api.post("/categories/init-defaults")
async def init_default_categories():
    """Idempotently ensure the default Expense/Income category catalog exists.
    Only inserts categories missing by (name, type). Never deletes and never
    touches transactions, accounts, balances or any calculations."""
    await ensure_user()
    existing = await db.categories.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(1000)
    have = {(c.get("name"), c.get("type")) for c in existing}
    created = 0
    for name, icon, color in DEFAULT_EXPENSE_CATEGORIES:
        if (name, "expense") not in have:
            c = Category(user_id=DEFAULT_USER_ID, name=name, type="expense", icon=icon, color=color).model_dump()
            await db.categories.insert_one(c)
            created += 1
    for name, icon, color in DEFAULT_INCOME_CATEGORIES:
        if (name, "income") not in have:
            c = Category(user_id=DEFAULT_USER_ID, name=name, type="income", icon=icon, color=color).model_dump()
            await db.categories.insert_one(c)
            created += 1
    total = await db.categories.count_documents({"user_id": DEFAULT_USER_ID})
    return {"ok": True, "created": created, "total": total}


# Transactions
@api.get("/transactions")
async def list_transactions(limit: int = 500):
    return await db.transactions.find({"user_id": DEFAULT_USER_ID}, PROJ).sort("date", -1).to_list(limit)


@api.post("/transactions")
async def create_transaction(data: TransactionCreate):
    if data.debt_id or data.type == "debt_payment":
        raise HTTPException(409, "Registra los pagos mediante /api/debt-payments para mantener su vínculo.")
    payload = data.model_dump()
    if not payload.get("date"):
        payload["date"] = now_iso()
    tx = Transaction(user_id=DEFAULT_USER_ID, **payload).model_dump()
    await db.transactions.insert_one(tx)
    if tx.get("account_id"):
        await recompute_account_balance(tx["account_id"])
    if tx.get("to_account_id"):
        await recompute_account_balance(tx["to_account_id"])
    return {k: v for k, v in tx.items() if k != "_id"}


@api.put("/transactions/{tid}")
async def update_transaction(tid: str, data: TransactionCreate):
    old = await db.transactions.find_one({"id": tid}, PROJ)
    if not old:
        raise HTTPException(404, "Not found")
    if old.get("debt_payment_id"):
        return await edit_payment_movement(tid, data)
    if old.get("debt_id") or data.debt_id or data.type == "debt_payment":
        raise HTTPException(409, "El movimiento requiere un vínculo individual con su pago antes de editarlo.")
    payload = data.model_dump()
    if not payload.get("date"):
        payload["date"] = old.get("date", now_iso())
    await db.transactions.update_one({"id": tid}, {"$set": payload})
    for aid in {old.get("account_id"), old.get("to_account_id"), payload.get("account_id"), payload.get("to_account_id")}:
        if aid:
            await recompute_account_balance(aid)
    return await db.transactions.find_one({"id": tid}, PROJ)


@api.delete("/transactions/{tid}")
async def delete_transaction(tid: str):
    old = await db.transactions.find_one({"id": tid}, PROJ)
    if old and old.get("debt_payment_id"):
        async def operation(session):
            current = await db.transactions.find_one({"id": tid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
            if not current:
                return {"ok": True}
            payment = await db.debt_payments.find_one({"id": current["debt_payment_id"], "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, PROJ, session=session)
            if not payment or payment.get("transaction_id") != tid:
                raise HTTPException(409, "El movimiento requiere conciliación con su pago.")
            return await remove_payment(payment["id"], session)
        return await payment_transaction(operation)
    if old and old.get("debt_id"):
        raise HTTPException(409, "Movimiento antiguo sin vínculo individual: requiere conciliación antes de borrar.")
    if old:
        await db.transactions.delete_one({"id": tid})
        for aid in {old.get("account_id"), old.get("to_account_id")}:
            if aid:
                await recompute_account_balance(aid)
    return {"ok": True}


# Recurring templates (MVP: stores configuration only; does NOT auto-create
# future transactions and does NOT touch balances or transaction calculations)
@api.get("/recurring")
async def list_recurring():
    return await db.recurring_templates.find({"user_id": DEFAULT_USER_ID}, PROJ).sort("created_at", -1).to_list(500)


@api.post("/recurring")
async def create_recurring(data: RecurringCreate):
    payload = data.model_dump()
    if not payload.get("start_date"):
        payload.pop("start_date", None)
    rt = RecurringTemplate(user_id=DEFAULT_USER_ID, **payload).model_dump()
    await db.recurring_templates.insert_one(rt)
    return {k: v for k, v in rt.items() if k != "_id"}


@api.delete("/recurring/{rid}")
async def delete_recurring(rid: str):
    await db.recurring_templates.delete_many({"id": rid, "user_id": DEFAULT_USER_ID})
    return {"ok": True}


# Budgets
@api.get("/budgets")
async def list_budgets():
    return await db.budgets.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(500)


@api.post("/budgets")
async def create_budget(data: BudgetCreate):
    payload = data.model_dump()
    if not payload.get("start_date"):
        payload["start_date"] = now_iso()
    b = Budget(user_id=DEFAULT_USER_ID, **payload).model_dump()
    await db.budgets.insert_one(b)
    return {k: v for k, v in b.items() if k != "_id"}


@api.put("/budgets/{bid}")
async def update_budget(bid: str, data: BudgetCreate):
    await db.budgets.update_one({"id": bid}, {"$set": data.model_dump()})
    return await db.budgets.find_one({"id": bid}, PROJ)


@api.delete("/budgets/{bid}")
async def delete_budget(bid: str):
    await db.budgets.delete_one({"id": bid})
    return {"ok": True}


# Saving Goals
@api.get("/goals")
async def list_goals():
    return await db.saving_goals.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(500)


@api.post("/goals")
async def create_goal(data: SavingGoalCreate):
    g = SavingGoal(user_id=DEFAULT_USER_ID, **data.model_dump()).model_dump()
    await db.saving_goals.insert_one(g)
    return {k: v for k, v in g.items() if k != "_id"}


@api.put("/goals/{gid}")
async def update_goal(gid: str, data: SavingGoalCreate):
    await db.saving_goals.update_one({"id": gid}, {"$set": data.model_dump()})
    return await db.saving_goals.find_one({"id": gid}, PROJ)


@api.delete("/goals/{gid}")
async def delete_goal(gid: str):
    await db.saving_goals.delete_one({"id": gid})
    return {"ok": True}


# Debts
@api.get("/debts")
async def list_debts():
    return await db.debts.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(500)


@api.get("/debts/{did}")
async def get_debt(did: str):
    d = await db.debts.find_one({"id": did}, PROJ)
    if not d:
        raise HTTPException(404, "Not found")
    return d


@api.post("/debts")
async def create_debt(data: DebtCreate):
    payload = data.model_dump()
    if not payload.get("start_date"):
        payload["start_date"] = now_iso()
    d = Debt(
        user_id=DEFAULT_USER_ID,
        remaining_amount=payload["original_amount"],
        **payload,
    ).model_dump()
    await db.debts.insert_one(d)
    return {k: v for k, v in d.items() if k != "_id"}


@api.put("/debts/{did}")
async def update_debt(did: str, data: DebtCreate):
    async def operation(session):
        old = await db.debts.find_one({"id": did, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
        if not old:
            raise HTTPException(404, "Debt not found")
        payments = db.debt_payments.find({"debt_id": did, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, PROJ, session=session)
        paid, has_payments = 0.0, False
        async for payment in payments:
            paid += payment["amount"]
            has_payments = True
        if has_payments and data.direction != old["direction"]:
            raise HTTPException(409, "No se puede cambiar la dirección de una deuda con pagos.")
        if not math.isfinite(data.original_amount) or data.original_amount < paid or data.original_amount < 0:
            raise HTTPException(422, "El importe de la deuda no puede ser menor que lo pagado.")
        payload = data.model_dump()
        payload["start_date"] = data.start_date or old["start_date"]
        await db.debts.update_one({"id": did, "user_id": DEFAULT_USER_ID}, {"$set": payload}, session=session)
        await recompute_debt(did, session=session)
        return await db.debts.find_one({"id": did, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    return await payment_transaction(operation)


@api.delete("/debts/{did}")
async def delete_debt(did: str):
    async def operation(session):
        if await db.debt_payments.find_one({"debt_id": did, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, PROJ, session=session) or await db.transactions.find_one({"debt_id": did, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            raise HTTPException(409, "La deuda tiene pagos o movimientos vinculados; anúlalos antes de borrarla.")
        await db.debts.delete_one({"id": did, "user_id": DEFAULT_USER_ID}, session=session)
        return {"ok": True}
    return await payment_transaction(operation)


# Debt Payments
@api.get("/debts/{did}/payments")
async def list_debt_payments(did: str):
    payments = await db.debt_payments.find({"debt_id": did, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, PROJ).sort("date", -1).to_list(500)
    return [DebtPayment(**payment).model_dump() for payment in payments]


@api.post("/debt-payments")
async def create_debt_payment(
    data: DebtPaymentCreate,
    idempotency_key: Optional[str] = Header(default=None, min_length=1, max_length=128),
):
    # IDs and request fingerprint stay stable across transaction retries.
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEFAULT_USER_ID}:debt-payment:{idempotency_key}")) if idempotency_key else new_id()
    tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"debt-payment-movement:{pid}"))
    fingerprint = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest()
    payload = data.model_dump()
    payload["date"] = data.date or now_iso()

    async def operation(session):
        previous = await db.debt_payments.find_one({"_id": pid, "user_id": DEFAULT_USER_ID}, session=session)
        if previous:
            if previous.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            if previous.get("deleted"):
                raise HTTPException(409, "La operación ya fue anulada; no se volverá a crear.")
            return DebtPayment(**previous).model_dump()
        debt = await validate_payment(data.debt_id, data.amount, data.account_id, session)
        payment = DebtPayment(id=pid, transaction_id=tid, user_id=DEFAULT_USER_ID, **payload).model_dump()
        tx = Transaction(
            id=tid, debt_payment_id=pid, user_id=DEFAULT_USER_ID,
            name=f"Pago: {debt['name']}", amount=data.amount,
            type="debt_payment" if debt["direction"] == "i_owe" else "income",
            date=payload["date"], account_id=data.account_id,
            debt_id=data.debt_id, notes=data.notes,
        ).model_dump()
        # MongoDB's existing unique _id index also arbitrates concurrent retries.
        stored_payment = dict(payment, _id=pid)
        if idempotency_key:
            stored_payment["request_fingerprint"] = fingerprint
        await db.debt_payments.insert_one(stored_payment, session=session)
        await db.transactions.insert_one(dict(tx, _id=tid), session=session)
        await recompute_debt(data.debt_id, session=session)
        if data.account_id:
            await recompute_account_balance(data.account_id, session=session)
        return payment

    return await payment_transaction(operation)


@api.delete("/debt-payments/{pid}")
async def delete_debt_payment(pid: str):
    return await payment_transaction(lambda session: remove_payment(pid, session))


# Reports summary
@api.get("/summary")
async def summary():
    accounts = await db.accounts.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(500)
    total_balance = sum(a["current_balance"] for a in accounts)

    txs = await db.transactions.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(2000)
    now = datetime.now(timezone.utc)
    month_income = 0.0
    month_expense = 0.0
    for t in txs:
        try:
            d = datetime.fromisoformat(t["date"].replace("Z", "+00:00"))
        except Exception:
            continue
        if d.year == now.year and d.month == now.month:
            if t["type"] == "income":
                month_income += t["amount"]
            elif t["type"] in ("expense", "debt_payment"):
                month_expense += t["amount"]

    debts = await db.debts.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(500)
    i_owe = sum(d["remaining_amount"] for d in debts if d["direction"] == "i_owe")
    they_owe = sum(d["remaining_amount"] for d in debts if d["direction"] == "they_owe")
    paid_this_month = 0.0
    async for p in db.debt_payments.find({"user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, PROJ):
        try:
            d = datetime.fromisoformat(p["date"].replace("Z", "+00:00"))
            if d.year == now.year and d.month == now.month:
                paid_this_month += p["amount"]
        except Exception:
            continue

    next_pay = None
    upcoming = sorted(
        [d for d in debts if d["direction"] == "i_owe" and d.get("due_date") and d["status"] == "active"],
        key=lambda x: x["due_date"],
    )
    if upcoming:
        next_pay = {"date": upcoming[0]["due_date"], "amount": upcoming[0]["minimum_payment"], "name": upcoming[0]["name"]}

    return {
        "total_balance": round(total_balance, 2),
        "month_income": round(month_income, 2),
        "month_expense": round(month_expense, 2),
        "debts": {
            "i_owe": round(i_owe, 2),
            "they_owe": round(they_owe, 2),
            "paid_this_month": round(paid_this_month, 2),
            "next_payment": next_pay,
        },
        "accounts_count": len(accounts),
    }


# Demo loading stays disabled until it has an isolated data store.
@api.post("/seed")
async def seed():
    raise HTTPException(
        status_code=403,
        detail="La carga de datos demo está deshabilitada para proteger tus datos.",
    )


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown():
    client.close()
