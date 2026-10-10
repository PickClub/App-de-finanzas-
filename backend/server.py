from fastapi import FastAPI, APIRouter, Header, HTTPException
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import logging, uuid, hashlib, json, math, re
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
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
    # Hierarchy (additive, backward compatible). is_group=True marks a main
    # category (accordion header); parent_id links a subcategory to its group.
    parent_id: Optional[str] = None
    is_group: bool = False


class CategoryCreate(BaseModel):
    name: str
    type: str = "expense"
    icon: str = "pricetag-outline"
    color: str = "#FF8A3D"
    parent_id: Optional[str] = None
    is_group: bool = False


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
    # Additive (backward compatible) alert settings + audit fields.
    alerts_enabled: bool = True
    alert_threshold: int = 80
    created_at: str = Field(default_factory=now_iso)
    updated_at: Optional[str] = None


class BudgetCreate(BaseModel):
    name: Optional[str] = None
    amount_limit: float
    period: str = "monthly"
    category_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    alerts_enabled: bool = True
    alert_threshold: int = 80


class SavingGoal(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str = DEFAULT_USER_ID
    name: str
    target_amount: float
    # current_amount = initial_amount + deposits - withdrawals (cached, recomputed).
    current_amount: float = 0.0
    initial_amount: float = 0.0
    target_date: Optional[str] = None
    priority: Literal["low", "medium", "high"] = "medium"
    color: str = "#29C4A9"
    icon: str = "flag-outline"
    account_id: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: Optional[str] = None


class SavingGoalCreate(BaseModel):
    name: str = ""
    target_amount: float
    initial_amount: Optional[float] = None
    # Legacy alias: older clients sent the initial saved amount as current_amount.
    current_amount: Optional[float] = None
    target_date: Optional[str] = None
    priority: Literal["low", "medium", "high"] = "medium"
    color: str = "#29C4A9"
    icon: str = "flag-outline"
    account_id: Optional[str] = None


class GoalContributionCreate(BaseModel):
    kind: Literal["deposit", "withdrawal"] = "deposit"
    amount: float
    date: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None
    # Only when True AND the goal has a linked account, a real transfer is recorded.
    real_movement: bool = False


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
        return {key: value for key, value in user.items() if key != "_id"}
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
    if await db.recurring_templates.find_one({"source_transaction_id": tx["id"]}, PROJ, session=session):
        raise HTTPException(409, "El movimiento de este pago es origen de una recurrencia. Elimina primero esa configuración de recurrencia.")
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
        if await db.debt_payments.find_one({"account_id": account_id, "deleted": {"$ne": True}}, PROJ, session=session):
            raise HTTPException(409, "La cuenta tiene pagos vinculados. Anúlalos primero desde el historial de la deuda antes de borrar la cuenta.")
        for field in ("account_id", "to_account_id"):
            if await db.transactions.find_one({field: account_id}, PROJ, session=session):
                raise HTTPException(409, "Esta cuenta tiene movimientos vinculados. Elimina o resuelve primero sus movimientos; los pagos se anulan desde el historial de deuda.")
        for collection, fields, label in ((db.debts, ("account_id",), "deudas"),
                                          (db.recurring_templates, ("account_id", "to_account_id"), "recurrencias")):
            for field in fields:
                if await collection.find_one({field: account_id}, PROJ, session=session):
                    raise HTTPException(409, f"Esta cuenta está vinculada a {label}. Resuelve ese vínculo antes de eliminarla.")
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
    # exclude_unset keeps hierarchy fields (parent_id/is_group) intact when a
    # client sends only {name,type,icon,color}; never wipes existing links.
    await db.categories.update_one({"id": cid}, {"$set": data.model_dump(exclude_unset=True)})
    return await db.categories.find_one({"id": cid}, PROJ)


@api.delete("/categories/{cid}")
async def delete_category(cid: str):
    async def operation(session):
        for collection, label in ((db.transactions, "movimientos"), (db.budgets, "presupuestos"),
                                  (db.debts, "deudas"), (db.recurring_templates, "recurrencias")):
            if await collection.find_one({"category_id": cid}, PROJ, session=session):
                raise HTTPException(409, f"Esta categoría está utilizada por {label}. Resuelve sus referencias antes de eliminarla.")
        await db.categories.delete_one({"id": cid}, session=session)
        return {"ok": True}
    return await payment_transaction(operation)


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

# New leaf subcategories introduced by the grouped layout (empty by design;
# existing transactions are NEVER moved into them). (name, type, icon, color)
NEW_SUBCATEGORIES = [
    ("Electronics", "expense", "hardware-chip-outline", "#5C7CFA"),
    ("Home", "expense", "bed-outline", "#C08457"),
    ("Beauty", "expense", "rose-outline", "#EC5F94"),
]

# Main category groups (accordion headers). English canonical names are stored;
# the client localises labels. Each tuple: (name, icon, color, [child names]).
# Child names reference EXISTING leaf categories by their stored English name.
EXPENSE_GROUPS = [
    ("Food & Dining", "fast-food-outline", "#FF7A59", ["Food", "Groceries", "Restaurants"]),
    ("Home & Housing", "home-outline", "#7C6CF0", ["Housing", "Rent", "Utilities"]),
    ("Transport & Auto", "bus-outline", "#4C9AFF", ["Transportation", "Fuel", "Car"]),
    ("Shopping & Goods", "bag-handle-outline", "#FF8ACC", ["Shopping", "Clothing", "Electronics", "Home", "Gifts", "Beauty"]),
    ("Health & Wellness", "medkit-outline", "#FF6B6B", ["Health", "Pharmacy", "Personal Care", "Fitness"]),
    ("Entertainment & Leisure", "film-outline", "#9B6BFA", ["Entertainment", "Subscriptions", "Travel"]),
    ("Finance", "wallet-outline", "#51B7B0", ["Taxes", "Loans", "Credit Cards", "Insurance"]),
    ("Other & Misc", "ellipsis-horizontal-outline", "#9AA0A6", ["Pets", "Family", "Education", "Technology", "Other"]),
]
INCOME_GROUPS = [
    ("Work", "briefcase-outline", "#2FB67C", ["Salary", "Freelance", "Business", "Tips"]),
    ("Investing", "trending-up-outline", "#7C6CF0", ["Investments", "Interest"]),
    ("Selling", "pricetags-outline", "#FF9F43", ["Sales"]),
    ("Other Earnings", "ellipsis-horizontal-outline", "#9AA0A6", ["Refunds", "Gifts", "Other Income"]),
]


@api.post("/categories/init-defaults")
async def init_default_categories():
    """Idempotently ensure the default catalog AND the grouped hierarchy exist.
    Only inserts what is missing (matched by name+type). Never deletes, renames
    or duplicates; never moves existing transactions; never touches balances.
    Safe to run multiple times (used by 'Restaurar predeterminadas')."""
    await ensure_user()

    async def ensure_leaf(name, typ, icon, color):
        existing = await db.categories.find_one({"user_id": DEFAULT_USER_ID, "name": name, "type": typ}, PROJ)
        if existing:
            return existing, 0
        c = Category(user_id=DEFAULT_USER_ID, name=name, type=typ, icon=icon, color=color).model_dump()
        await db.categories.insert_one(c)
        return {k: v for k, v in c.items() if k != "_id"}, 1

    created = 0
    # 1) default leaf catalog
    for name, icon, color in DEFAULT_EXPENSE_CATEGORIES:
        _, n = await ensure_leaf(name, "expense", icon, color)
        created += n
    for name, icon, color in DEFAULT_INCOME_CATEGORIES:
        _, n = await ensure_leaf(name, "income", icon, color)
        created += n
    # 2) new (empty) subcategories
    for name, typ, icon, color in NEW_SUBCATEGORIES:
        _, n = await ensure_leaf(name, typ, icon, color)
        created += n

    groups_created = 0
    links = 0
    # 3) groups + 4) parent links (idempotent)
    for groups, typ in ((EXPENSE_GROUPS, "expense"), (INCOME_GROUPS, "income")):
        for gname, gicon, gcolor, children in groups:
            g = await db.categories.find_one(
                {"user_id": DEFAULT_USER_ID, "name": gname, "type": typ, "is_group": True}, PROJ)
            if not g:
                g = Category(user_id=DEFAULT_USER_ID, name=gname, type=typ, icon=gicon,
                             color=gcolor, is_group=True).model_dump()
                await db.categories.insert_one(g)
                g = {k: v for k, v in g.items() if k != "_id"}
                groups_created += 1
            gid = g["id"]
            for child_name in children:
                child = await db.categories.find_one(
                    {"user_id": DEFAULT_USER_ID, "name": child_name, "type": typ, "is_group": {"$ne": True}}, PROJ)
                if child and child.get("parent_id") != gid:
                    await db.categories.update_one({"id": child["id"]}, {"$set": {"parent_id": gid}})
                    links += 1

    total = await db.categories.count_documents({"user_id": DEFAULT_USER_ID})
    return {"ok": True, "created": created, "groups_created": groups_created, "links": links, "total": total}


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
    if old.get("goal_contribution_id"):
        raise HTTPException(409, "Este movimiento está vinculado a un aporte de una meta de ahorro; adminístralo desde Metas de ahorro.")
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
    if old and old.get("goal_contribution_id"):
        raise HTTPException(409, "Este movimiento está vinculado a un aporte de una meta de ahorro; adminístralo desde Metas de ahorro.")
    if old and await db.recurring_templates.find_one({"source_transaction_id": tid}, PROJ):
        raise HTTPException(409, "Este movimiento es origen de una recurrencia. Elimina primero esa configuración de recurrencia.")
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
# ---------------------------------------------------------------------------
# Spending is ALWAYS derived on demand from real transactions (never stored),
# so history is preserved, a new period naturally starts at 0 and editing /
# deleting a movement is reflected immediately. Only type == "expense" counts:
# income, transfers, debt_payment and loan_* movements are excluded, which also
# prevents double counting debt payments. Recurring templates are config-only
# and never counted unless a real expense transaction exists.
# Money math uses Decimal (cents) to avoid floating point drift.
BUDGET_PERIODS = ("weekly", "monthly", "custom")


def _dec(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_dt(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _local_tz(tz_offset: int):
    # tz_offset follows JS Date.getTimezoneOffset() (minutes, UTC - local).
    return timezone(timedelta(minutes=-int(tz_offset or 0)))


def _month_bounds(year: int, month: int, tz):
    start = datetime(year, month, 1, tzinfo=tz)
    end = datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=tz)
    return start, end


def _day_start(d, tz):
    d = d.astimezone(tz)
    return datetime(d.year, d.month, d.day, tzinfo=tz)


def _budget_window(b, m_start, m_end, tz, now):
    """Period window [start, end) of a budget for the selected month, or None if inactive."""
    b_start = _parse_dt(b.get("start_date"))
    b_start = _day_start(b_start, tz) if b_start else None
    b_end = _parse_dt(b.get("end_date"))
    b_end = _day_start(b_end, tz) + timedelta(days=1) if b_end else None  # inclusive end date
    period = b.get("period", "monthly")
    if period == "custom":
        if not b_start or not b_end:
            return None
        if b_start >= m_end or b_end <= m_start:
            return None
        return b_start, b_end
    if period == "weekly":
        # Reference day: today when viewing the current month, else the last day of the month.
        ref = now.astimezone(tz)
        if not (m_start <= ref < m_end):
            ref = m_end - timedelta(days=1)
        ws = _day_start(ref, tz) - timedelta(days=ref.weekday())  # weeks start on Monday
        we = ws + timedelta(days=7)
    else:
        ws, we = m_start, m_end
    if b_start and b_start >= we:
        return None
    if b_end and b_end <= ws:
        return None
    return ws, we


def _scope_ids(category_id, cats_by_id):
    """A main group includes itself + its subcategories; a leaf only itself."""
    if not category_id:
        return set()
    cat = cats_by_id.get(category_id)
    ids = {category_id}
    if cat and cat.get("is_group"):
        ids |= {c["id"] for c in cats_by_id.values() if c.get("parent_id") == category_id}
    return ids


def _status(spent: Decimal, limit: Decimal, threshold: int) -> str:
    if limit <= 0:
        return "normal"
    if spent > limit:
        return "exceeded"
    if spent == limit:
        return "reached"
    if spent * 100 >= limit * Decimal(threshold):
        return "warning"
    return "normal"


async def _compute_budgets(year: int, month: int, tz_offset: int, only_id: Optional[str] = None):
    tz = _local_tz(tz_offset)
    m_start, m_end = _month_bounds(year, month, tz)
    now = datetime.now(timezone.utc)
    q = {"user_id": DEFAULT_USER_ID}
    if only_id:
        q["id"] = only_id
    budgets = await db.budgets.find(q, {"_id": 0, "idempotency_key": 0}).to_list(1000)
    cats = await db.categories.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(2000)
    cats_by_id = {c["id"]: c for c in cats}
    txs = await db.transactions.find({"user_id": DEFAULT_USER_ID, "type": "expense"}, PROJ).to_list(20000)
    for t in txs:
        t["_dt"] = _parse_dt(t.get("date"))

    rows = []
    for b in budgets:
        win = _budget_window(b, m_start, m_end, tz, now)
        scope = _scope_ids(b.get("category_id"), cats_by_id)
        matched = []
        if win:
            ws, we = win
            matched = [t for t in txs if t["_dt"] and t.get("category_id") in scope and ws <= t["_dt"] < we]
        spent = sum((_dec(t["amount"]) for t in matched), Decimal("0.00"))
        limit = _dec(b.get("amount_limit"))
        threshold = int(b.get("alert_threshold") or 80)
        status = _status(spent, limit, threshold)
        pct = float((spent * 100 / limit).quantize(Decimal("0.1"))) if limit > 0 else None
        rows.append({
            **b,
            "active": bool(win),
            "window_start": win[0].isoformat() if win else None,
            "window_end": (win[1] - timedelta(microseconds=1)).isoformat() if win else None,
            "spent": float(spent),
            "available": float(limit - spent),
            "pct": pct,
            "status": status,
            "alert": bool(win) and bool(b.get("alerts_enabled", True)) and status != "normal",
            "tx_count": len(matched),
            "_matched": matched,
            "_scope": scope,
        })
    return rows, cats_by_id, (m_start, m_end)


def _public(row, with_tx=False):
    out = {k: v for k, v in row.items() if not k.startswith("_")}
    if with_tx:
        out["transactions"] = sorted(
            ({k: v for k, v in t.items() if k != "_dt"} for t in row["_matched"]),
            key=lambda t: t.get("date") or "", reverse=True,
        )
    return out


def _overlaps(a_start, a_end, b_start, b_end):
    inf = datetime.max.replace(tzinfo=timezone.utc)
    return (a_start or datetime.min.replace(tzinfo=timezone.utc)) < (b_end or inf) and \
        (b_start or datetime.min.replace(tzinfo=timezone.utc)) < (a_end or inf)


async def _validate_budget(data: BudgetCreate, replacing: Optional[str] = None) -> dict:
    payload = data.model_dump()
    try:
        limit = _dec(payload["amount_limit"])
    except Exception:
        raise HTTPException(422, "El límite debe ser un número válido.")
    if not limit.is_finite() or limit <= 0:
        raise HTTPException(422, "El límite debe ser mayor que cero.")
    payload["amount_limit"] = float(limit)
    if payload["period"] not in BUDGET_PERIODS:
        raise HTTPException(422, "Período inválido.")
    thr = payload.get("alert_threshold")
    if thr is None or not (1 <= int(thr) <= 100):
        raise HTTPException(422, "El porcentaje de alerta debe estar entre 1 y 100.")
    payload["alert_threshold"] = int(thr)
    if not payload.get("category_id"):
        raise HTTPException(422, "Selecciona una categoría.")
    cat = await db.categories.find_one({"id": payload["category_id"], "user_id": DEFAULT_USER_ID}, PROJ)
    if not cat or cat.get("type") != "expense":
        raise HTTPException(422, "La categoría no existe o no es de gastos.")
    start = _parse_dt(payload.get("start_date")) if payload.get("start_date") else datetime.now(timezone.utc)
    if not start:
        raise HTTPException(422, "Fecha de inicio inválida.")
    payload["start_date"] = start.isoformat()
    end = None
    if payload.get("end_date"):
        end = _parse_dt(payload["end_date"])
        if not end:
            raise HTTPException(422, "Fecha de finalización inválida.")
        if end < start:
            raise HTTPException(422, "La fecha de finalización debe ser posterior a la de inicio.")
        payload["end_date"] = end.isoformat()
    else:
        payload["end_date"] = None
    if payload["period"] == "custom" and not end:
        raise HTTPException(422, "Un período personalizado requiere fecha de finalización.")
    if not (payload.get("name") or "").strip():
        payload["name"] = cat["name"]
    # Duplicate guard: same category + same period type with overlapping dates.
    q = {"user_id": DEFAULT_USER_ID, "category_id": payload["category_id"], "period": payload["period"]}
    if replacing:
        q["id"] = {"$ne": replacing}
    async for other in db.budgets.find(q, PROJ):
        if _overlaps(start, end, _parse_dt(other.get("start_date")), _parse_dt(other.get("end_date"))):
            raise HTTPException(409, "Ya existe un presupuesto para esta categoría y período en esas fechas.")
    return payload


@api.get("/budgets")
async def list_budgets():
    return await db.budgets.find({"user_id": DEFAULT_USER_ID}, {"_id": 0, "idempotency_key": 0}).sort("created_at", -1).to_list(500)


@api.get("/budgets/overview")
async def budgets_overview(year: Optional[int] = None, month: Optional[int] = None, tz_offset: int = 0):
    now = datetime.now(_local_tz(tz_offset))
    year = year or now.year
    month = month or now.month
    if not (1 <= month <= 12) or not (1970 <= year <= 9999):
        raise HTTPException(422, "Mes o año inválido.")
    rows, cats_by_id, (m_start, m_end) = await _compute_budgets(year, month, tz_offset)
    active = [r for r in rows if r["active"]]
    # Totals without double counting: a budget whose category is a subcategory of
    # another ACTIVE budget's main group is already covered by that group budget.
    group_ids = {r["category_id"] for r in active if cats_by_id.get(r["category_id"], {}).get("is_group")}
    for r in rows:
        parent = cats_by_id.get(r.get("category_id"), {}).get("parent_id")
        r["counted_in_total"] = r["active"] and not (parent and parent in group_ids)
    counted = [r for r in rows if r["counted_in_total"]]
    budgeted = sum((_dec(r["amount_limit"]) for r in counted), Decimal("0.00"))
    seen, spent = set(), Decimal("0.00")
    for r in counted:
        for t in r["_matched"]:
            if t["id"] not in seen:
                seen.add(t["id"])
                spent += _dec(t["amount"])
    pct = float((spent * 100 / budgeted).quantize(Decimal("0.1"))) if budgeted > 0 else None
    alerts = [r for r in active if r["alert"]]
    return {
        "year": year,
        "month": month,
        "period_start": m_start.isoformat(),
        "period_end": (m_end - timedelta(microseconds=1)).isoformat(),
        "totals": {
            "budgeted": float(budgeted),
            "spent": float(spent),
            "available": float(budgeted - spent),
            "pct": pct,
        },
        "active_count": len(active),
        "alerts_count": len(alerts),
        "exceeded_count": len([r for r in alerts if r["status"] == "exceeded"]),
        "budgets": [_public(r) for r in rows],
    }


@api.get("/budgets/{bid}/detail")
async def budget_detail(bid: str, year: Optional[int] = None, month: Optional[int] = None, tz_offset: int = 0):
    now = datetime.now(_local_tz(tz_offset))
    rows, cats_by_id, _ = await _compute_budgets(year or now.year, month or now.month, tz_offset, only_id=bid)
    if not rows:
        raise HTTPException(404, "Presupuesto no encontrado.")
    out = _public(rows[0], with_tx=True)
    out["category"] = cats_by_id.get(rows[0].get("category_id"))
    return out


@api.post("/budgets")
async def create_budget(data: BudgetCreate, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    if idempotency_key:
        existing = await db.budgets.find_one({"user_id": DEFAULT_USER_ID, "idempotency_key": idempotency_key}, PROJ)
        if existing:
            return {k: v for k, v in existing.items() if k != "idempotency_key"}
    payload = await _validate_budget(data)
    b = Budget(user_id=DEFAULT_USER_ID, **payload).model_dump()
    doc = {**b, **({"idempotency_key": idempotency_key} if idempotency_key else {})}
    await db.budgets.insert_one(doc)
    return {k: v for k, v in b.items() if k != "_id"}


@api.put("/budgets/{bid}")
async def update_budget(bid: str, data: BudgetCreate):
    if not await db.budgets.find_one({"id": bid, "user_id": DEFAULT_USER_ID}, PROJ):
        raise HTTPException(404, "Presupuesto no encontrado.")
    payload = await _validate_budget(data, replacing=bid)
    payload["updated_at"] = now_iso()
    await db.budgets.update_one({"id": bid, "user_id": DEFAULT_USER_ID}, {"$set": payload})
    doc = await db.budgets.find_one({"id": bid, "user_id": DEFAULT_USER_ID}, PROJ)
    return {k: v for k, v in doc.items() if k != "idempotency_key"}


@api.delete("/budgets/{bid}")
async def delete_budget(bid: str):
    await db.budgets.delete_one({"id": bid, "user_id": DEFAULT_USER_ID})
    return {"ok": True}


# ---------- Saving Goals ----------
# Rules:
# * A goal's saved amount = initial_amount + deposits - withdrawals (Decimal math).
# * Tracking contributions NEVER touch account balances or transactions.
# * A "real movement" contribution is recorded ONLY when explicitly requested and the
#   goal has a linked account: it creates ONE transfer (source -> goal account, or the
#   reverse for withdrawals). Transfers are neither income nor expense, so no fictitious
#   income/expense is created and total money is never duplicated.
# * Contribution history is append-only (withdrawals are stored as their own records).
GOAL_HIDDEN = {"_id", "request_fingerprint"}
CENT = Decimal("0.01")


def _goal_clean(doc):
    return {k: v for k, v in doc.items() if k not in GOAL_HIDDEN}


def _goal_target_date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        raise HTTPException(422, "La fecha objetivo no es válida.")


def _positive_money(value, msg):
    if value is None or not math.isfinite(value) or value <= 0:
        raise HTTPException(422, msg)
    return float(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP))


def _goal_public(g, today=None):
    today = today or datetime.now(timezone.utc).date()
    target = Decimal(str(g.get("target_amount") or 0))
    saved = Decimal(str(g.get("current_amount") or 0))
    remaining = max(Decimal(0), target - saved)
    pct = float((saved / target * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if target > 0 else None
    completed = target > 0 and saved >= target
    recommended, days_left, overdue = None, None, False
    td = g.get("target_date")
    if td:
        try:
            d = date.fromisoformat(str(td)[:10])
        except ValueError:
            d = None
        if d:
            days_left = (d - today).days
            if remaining > 0:
                if days_left < 0:
                    overdue = True
                else:
                    # Partial months count proportionally; anything under a month needs
                    # the whole remaining amount this month.
                    months = max(Decimal(1), Decimal(days_left + 1) / Decimal("30.436875"))
                    recommended = int((remaining / months).to_integral_value(rounding=ROUND_CEILING))
    out = _goal_clean(g)
    out.update(
        current_amount=float(saved), remaining=float(remaining), pct=pct, completed=completed,
        status="completed" if completed else "active", monthly_recommended=recommended,
        days_left=days_left, overdue=overdue,
    )
    return out


async def recompute_goal(gid, session=None):
    g = await db.saving_goals.find_one({"id": gid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    if not g:
        return None
    # Legacy goals (before contributions existed) stored the saved amount in current_amount.
    initial = Decimal(str(g["initial_amount"] if g.get("initial_amount") is not None else g.get("current_amount") or 0))
    total = initial
    pipeline = [
        {"$match": {"user_id": DEFAULT_USER_ID, "goal_id": gid}},
        {"$group": {"_id": "$kind", "s": {"$sum": {"$toDecimal": "$amount"}}}},
    ]
    async for row in db.goal_contributions.aggregate(pipeline, session=session):
        s = row["s"].to_decimal()
        total += s if row["_id"] == "deposit" else -s
    total = max(Decimal(0), total).quantize(CENT, rounding=ROUND_HALF_UP)
    completed = g["target_amount"] > 0 and total >= Decimal(str(g["target_amount"]))
    upd = {"current_amount": float(total), "initial_amount": float(initial)}
    if completed and not g.get("completed_at"):
        upd["completed_at"] = now_iso()
    elif not completed and g.get("completed_at"):
        upd["completed_at"] = None
    await db.saving_goals.update_one({"id": gid, "user_id": DEFAULT_USER_ID}, {"$set": upd}, session=session)
    g.update(upd)
    return g


async def _validate_goal(data: SavingGoalCreate, replacing=None, session=None):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(422, "El nombre de la meta es obligatorio.")
    if len(name) > 60:
        raise HTTPException(422, "El nombre de la meta es demasiado largo (máx. 60).")
    target = _positive_money(data.target_amount, "El monto objetivo debe ser mayor que cero.")
    initial = data.initial_amount if data.initial_amount is not None else data.current_amount
    if initial is not None:
        if not math.isfinite(initial) or initial < 0:
            raise HTTPException(422, "El monto inicial no puede ser negativo.")
        initial = float(Decimal(str(initial)).quantize(CENT, rounding=ROUND_HALF_UP))
    if data.account_id and not await db.accounts.find_one({"id": data.account_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
        raise HTTPException(422, "La cuenta asociada no existe.")
    q = {"user_id": DEFAULT_USER_ID, "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    if replacing:
        q["id"] = {"$ne": replacing}
    if await db.saving_goals.find_one(q, PROJ, session=session):
        raise HTTPException(409, "Ya existe una meta con ese nombre.")
    return {
        "name": name, "target_amount": target, "target_date": _goal_target_date(data.target_date),
        "priority": data.priority, "color": data.color or "#29C4A9", "icon": data.icon or "flag-outline",
        "account_id": data.account_id or None,
    }, initial


async def _contributions_page(gid, limit, offset, session=None):
    limit = max(1, min(int(limit or 20), 100))
    offset = max(0, int(offset or 0))
    q = {"user_id": DEFAULT_USER_ID, "goal_id": gid}
    items = await db.goal_contributions.find(q, {"_id": 0, "request_fingerprint": 0}, session=session) \
        .sort([("date", -1), ("created_at", -1)]).skip(offset).limit(limit).to_list(limit)
    total = await db.goal_contributions.count_documents(q, session=session)
    return {"items": items, "total": total, "offset": offset, "limit": limit, "has_more": offset + len(items) < total}


@api.get("/goals")
async def list_goals():
    goals = await db.saving_goals.find({"user_id": DEFAULT_USER_ID}, PROJ).sort("created_at", -1).to_list(500)
    today = datetime.now(timezone.utc).date()
    return [_goal_public(g, today) for g in goals]


@api.get("/goals/overview")
async def goals_overview():
    goals = await db.saving_goals.find({"user_id": DEFAULT_USER_ID}, PROJ).sort("created_at", -1).to_list(500)
    today = datetime.now(timezone.utc).date()
    rows = [_goal_public(g, today) for g in goals]
    saved = sum((Decimal(str(r["current_amount"])) for r in rows), Decimal(0))
    target = sum((Decimal(str(r["target_amount"])) for r in rows), Decimal(0))
    # Per-goal remaining: surplus in one goal never reduces another goal's remaining.
    remaining = sum((Decimal(str(r["remaining"])) for r in rows), Decimal(0))
    pct = float((saved / target * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if target > 0 else None
    return {
        "totals": {"saved": float(saved), "target": float(target), "remaining": float(remaining), "pct": pct},
        "active_count": sum(1 for r in rows if not r["completed"]),
        "completed_count": sum(1 for r in rows if r["completed"]),
        "goals": rows,
    }


@api.get("/goals/{gid}")
async def get_goal(gid: str, limit: int = 20):
    g = await db.saving_goals.find_one({"id": gid, "user_id": DEFAULT_USER_ID}, PROJ)
    if not g:
        raise HTTPException(404, "Meta no encontrada.")
    out = _goal_public(g)
    acc = await db.accounts.find_one({"id": g["account_id"], "user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1, "name": 1, "color": 1}) if g.get("account_id") else None
    out["account"] = acc
    out["contributions"] = await _contributions_page(gid, limit, 0)
    return out


@api.get("/goals/{gid}/contributions")
async def list_goal_contributions(gid: str, limit: int = 20, offset: int = 0):
    if not await db.saving_goals.find_one({"id": gid, "user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Meta no encontrada.")
    return await _contributions_page(gid, limit, offset)


@api.post("/goals")
async def create_goal(
    data: SavingGoalCreate,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=128),
):
    gid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEFAULT_USER_ID}:goal:{idempotency_key}")) if idempotency_key else new_id()
    fingerprint = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest()
    previous = await db.saving_goals.find_one({"_id": gid, "user_id": DEFAULT_USER_ID})
    if previous:
        if previous.get("request_fingerprint") != fingerprint:
            raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
        return _goal_public(previous)
    fields, initial = await _validate_goal(data)
    initial = initial or 0.0
    g = SavingGoal(id=gid, user_id=DEFAULT_USER_ID, current_amount=initial, initial_amount=initial, **fields).model_dump()
    if g["target_amount"] > 0 and initial >= g["target_amount"]:
        g["completed_at"] = now_iso()
    stored = dict(g, _id=gid)
    if idempotency_key:
        stored["request_fingerprint"] = fingerprint
    try:
        await db.saving_goals.insert_one(stored)
    except DuplicateKeyError:
        previous = await db.saving_goals.find_one({"_id": gid, "user_id": DEFAULT_USER_ID})
        if previous and previous.get("request_fingerprint") == fingerprint:
            return _goal_public(previous)
        raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
    return _goal_public(g)


@api.put("/goals/{gid}")
async def update_goal(gid: str, data: SavingGoalCreate):
    async def operation(session):
        if not await db.saving_goals.find_one({"id": gid, "user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1}, session=session):
            raise HTTPException(404, "Meta no encontrada.")
        fields, initial = await _validate_goal(data, replacing=gid, session=session)
        fields["updated_at"] = now_iso()
        if initial is not None:
            fields["initial_amount"] = initial
        await db.saving_goals.update_one({"id": gid, "user_id": DEFAULT_USER_ID}, {"$set": fields}, session=session)
        return _goal_public(await recompute_goal(gid, session=session))

    return await payment_transaction(operation)


@api.delete("/goals/{gid}")
async def delete_goal(gid: str):
    async def operation(session):
        g = await db.saving_goals.find_one({"id": gid, "user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1}, session=session)
        if not g:
            return {"ok": True}
        await db.goal_contributions.delete_many({"goal_id": gid, "user_id": DEFAULT_USER_ID}, session=session)
        # Real transfers already moved money between the user's accounts: keep them
        # (balances unchanged) and only remove the link to the deleted goal.
        await db.transactions.update_many(
            {"goal_id": gid, "user_id": DEFAULT_USER_ID},
            {"$unset": {"goal_id": "", "goal_contribution_id": ""}}, session=session,
        )
        await db.saving_goals.delete_one({"id": gid, "user_id": DEFAULT_USER_ID}, session=session)
        return {"ok": True}

    return await payment_transaction(operation)


@api.post("/goals/{gid}/contributions")
async def create_goal_contribution(
    gid: str,
    data: GoalContributionCreate,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=128),
):
    cid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEFAULT_USER_ID}:goal-contribution:{gid}:{idempotency_key}")) if idempotency_key else new_id()
    tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"goal-contribution-movement:{cid}"))
    fingerprint = hashlib.sha256(json.dumps({"goal": gid, **data.model_dump()}, sort_keys=True, allow_nan=False).encode()).hexdigest()
    amount = _positive_money(data.amount, "El monto debe ser mayor que cero.")
    when = _parse_dt(data.date) if data.date else datetime.now(timezone.utc)
    if when is None:
        raise HTTPException(422, "La fecha no es válida.")
    notes = (data.notes or "").strip()[:200] or None

    async def operation(session):
        previous = await db.goal_contributions.find_one({"_id": cid, "user_id": DEFAULT_USER_ID}, session=session)
        if previous:
            if previous.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            g = await db.saving_goals.find_one({"id": gid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
            return {"contribution": _goal_clean(previous), "goal": _goal_public(g) if g else None}
        g = await recompute_goal(gid, session=session)
        if not g:
            raise HTTPException(404, "Meta no encontrada.")
        if data.account_id and not await db.accounts.find_one({"id": data.account_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            raise HTTPException(422, "La cuenta seleccionada no existe.")
        if data.kind == "withdrawal" and Decimal(str(amount)) > Decimal(str(g["current_amount"])):
            raise HTTPException(422, "El retiro supera el ahorro acumulado de la meta.")
        tx_id = None
        if data.real_movement:
            goal_acc = g.get("account_id")
            if not goal_acc or not await db.accounts.find_one({"id": goal_acc, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
                raise HTTPException(422, "Para mover dinero real, la meta debe tener una cuenta asociada.")
            if not data.account_id:
                raise HTTPException(422, "Selecciona la cuenta para registrar el movimiento real.")
            if data.account_id == goal_acc:
                raise HTTPException(422, "La cuenta debe ser distinta de la cuenta asociada a la meta.")
            src, dst = (data.account_id, goal_acc) if data.kind == "deposit" else (goal_acc, data.account_id)
            tx = Transaction(
                id=tid, user_id=DEFAULT_USER_ID, amount=amount, type="transfer", date=when.isoformat(),
                name=(f"Ahorro: {g['name']}" if data.kind == "deposit" else f"Retiro de meta: {g['name']}"),
                account_id=src, to_account_id=dst, notes=notes,
            ).model_dump()
            tx.update(goal_id=gid, goal_contribution_id=cid)
            await db.transactions.insert_one(dict(tx, _id=tid), session=session)
            await recompute_account_balance(src, session=session)
            await recompute_account_balance(dst, session=session)
            tx_id = tid
        contribution = {
            "id": cid, "user_id": DEFAULT_USER_ID, "goal_id": gid, "kind": data.kind, "amount": amount,
            "date": when.isoformat(), "account_id": data.account_id or None, "notes": notes,
            "real_movement": bool(tx_id), "transaction_id": tx_id, "created_at": now_iso(),
        }
        stored = dict(contribution, _id=cid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await db.goal_contributions.insert_one(stored, session=session)
        g2 = await recompute_goal(gid, session=session)
        return {"contribution": contribution, "goal": _goal_public(g2)}

    return await payment_transaction(operation)


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


@app.on_event("startup")
async def goal_indexes():
    try:
        await db.saving_goals.create_index([("user_id", 1), ("created_at", -1)])
        await db.goal_contributions.create_index([("user_id", 1), ("goal_id", 1), ("date", -1), ("created_at", -1)])
    except PyMongoError:
        logger.warning("Could not ensure saving-goal indexes")


@app.on_event("shutdown")
async def shutdown():
    client.close()
