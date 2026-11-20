from fastapi import FastAPI, APIRouter, Header, HTTPException, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import logging, uuid, hashlib, json, math, re, calendar
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal, Annotated
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from pymongo import ReadPreference, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

if __package__:
    from .history_keys import PUBLIC_PROJECTION as HISTORY_PUBLIC_PROJECTION, with_history_keys, history_update_fields
    from .transaction_history import read_page as read_transaction_page, read_detail as read_transaction_detail
    from .shared_obligations import public_financial_document as shared_public, read_shared_view, shared_bill_public, shared_recurring_public, shared_read_route, read_database, current_shared_view, current_shared_periods, shared_paid_events, dispatch_shared_payment, shared_parent_context, edit_shared_bill, edit_shared_recurring, guard_shared_state_change, dispatch_shared_change, shared_link_candidates, reconcile_payment_intent
    from .config import load_settings
    from .financial_context import get_financial_context, verify_payment_context
    from .reference_integrity import coordinate, public as reference_public, check_record, check_bill_payment, retire, preserve_references, check_movement_references, check_goal_contribution, guard_legacy_bill, guard_legacy_recurring, guard_legacy_receipt, guard_legacy_movement
else:
    from history_keys import PUBLIC_PROJECTION as HISTORY_PUBLIC_PROJECTION, with_history_keys, history_update_fields
    from transaction_history import read_page as read_transaction_page, read_detail as read_transaction_detail
    from shared_obligations import public_financial_document as shared_public, read_shared_view, shared_bill_public, shared_recurring_public, shared_read_route, read_database, current_shared_view, current_shared_periods, shared_paid_events, dispatch_shared_payment, shared_parent_context, edit_shared_bill, edit_shared_recurring, guard_shared_state_change, dispatch_shared_change, shared_link_candidates, reconcile_payment_intent
    from config import load_settings
    from financial_context import get_financial_context, verify_payment_context
    from reference_integrity import coordinate, public as reference_public, check_record, check_bill_payment, retire, preserve_references, check_movement_references, check_goal_contribution, guard_legacy_bill, guard_legacy_recurring, guard_legacy_receipt, guard_legacy_movement

settings = load_settings()
if settings.app_env == "production":
    raise RuntimeError("The legacy MoneyFlow API cannot run in production.")
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
    type: Literal["cash", "checking", "savings", "credit_card", "wallet", "other"] = "cash"
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


def transaction_edit_payload(data, old):
    from backend.movement_operations import edit_payload

    return edit_payload(data, old, now_iso(), preserve_missing_date=True)


async def validate_transaction(payload, old=None, session=None):
    from backend.movement_operations import validate_movement

    await validate_movement(db, DEFAULT_USER_ID, PROJ, payload, old, session)


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


INTERNAL_PROJ = {"_id": 0, "_reference_revision": 0}
PROJ = {**INTERNAL_PROJ, **HISTORY_PUBLIC_PROJECTION}


# ---------- Utilities ----------
async def ensure_user():
    u = await db.users.find_one({"id": DEFAULT_USER_ID}, PROJ)
    if not u:
        user = User(id=DEFAULT_USER_ID, name="Usuario").model_dump()
        await db.users.insert_one(user)
        return {key: value for key, value in user.items() if key != "_id"}
    return u


async def recompute_account_balance(account_id: str, session=None):
    from backend.account_operations import recompute_balance

    await recompute_balance(db, DEFAULT_USER_ID, account_id, PROJ, session)


async def recompute_debt(debt_id: str, session=None):
    from backend import debt_operations as operations

    await operations.recompute_debt(db, DEFAULT_USER_ID, debt_id, session)


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


async def ordinary_transaction(operation):
    """Retry only aborted transient transactions, never an uncertain commit."""
    for attempt in range(3):
        try:
            async with await client.start_session() as session:
                async with session.start_transaction(
                    read_concern=ReadConcern("snapshot"),
                    write_concern=WriteConcern("majority"),
                    read_preference=ReadPreference.PRIMARY,
                ):
                    return await operation(session)
        except PyMongoError as error:
            if error.has_error_label("UnknownTransactionCommitResult"):
                raise HTTPException(503, "No se pudo confirmar el resultado. Comprueba el estado antes de repetir la operación; puede haberse guardado.")
            if error.has_error_label("TransientTransactionError"):
                if attempt < 2:
                    continue
                raise HTTPException(409, "Conflicto concurrente; la operación no se guardó. Reintenta más tarde.")
            raise HTTPException(503, "No se pudo confirmar la operación atómica. MongoDB debe admitir transacciones; comprueba el estado antes de repetirla.")


async def validate_payment(debt_id, amount, account_id, session, replacing=None):
    from backend import debt_operations as operations

    return await operations.validate_payment(db, DEFAULT_USER_ID, debt_id, amount, account_id, session, replacing)


async def payment_movement(payment, session):
    from backend import debt_operations as operations

    return await operations.payment_movement(db, DEFAULT_USER_ID, payment, session)


async def remove_payment(pid, session):
    from backend import debt_operations as operations

    return await operations.remove_payment(db, DEFAULT_USER_ID, pid, session)


async def edit_payment_movement(tid, data):
    from backend import debt_operations as operations

    generation = settings.history_keys_generation if getattr(settings, "history_keys_write_enabled", False) else None
    return shared_public(await payment_transaction(
        lambda session: operations.edit_payment(db, DEFAULT_USER_ID, tid, data, session, generation)
    ))


# ---------- Routes ----------
@api.get("/")
async def root():
    return {"message": "MoneyFlow API"}


@api.get("/financial-context")
async def financial_context():
    return await get_financial_context(db, settings.expected_financial_environment_id, DEFAULT_USER_ID)


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
    async def operation(session):
        await db.accounts.update_one({"id": account_id}, {"$set": data.model_dump()}, session=session)
        await recompute_account_balance(account_id, session=session)
        return await db.accounts.find_one({"id": account_id}, PROJ, session=session)
    return await ordinary_transaction(operation)


@api.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    from backend.account_operations import delete_owned_account

    async def operation(session):
        return await delete_owned_account(db, DEFAULT_USER_ID, account_id, PROJ, session)
    return await payment_transaction(operation)


# Categories
@api.get("/categories")
async def list_categories():
    return await db.categories.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(500)


@api.post("/categories")
async def create_category(data: CategoryCreate):
    cat = Category(user_id=DEFAULT_USER_ID, **data.model_dump()).model_dump()
    async def operation(session):
        await coordinate(db, DEFAULT_USER_ID, cat, session)
        await db.categories.insert_one(cat.copy(), session=session)
        return reference_public(cat)
    return await payment_transaction(operation)


@api.put("/categories/{cid}")
async def update_category(cid: str, data: CategoryCreate):
    async def operation(session):
        old = await db.categories.find_one({"id": cid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
        if not old:
            return None
        payload = data.model_dump(exclude_unset=True)
        await coordinate(db, DEFAULT_USER_ID, {**old, **payload}, session, old)
        await db.categories.update_one({"id": cid, "user_id": DEFAULT_USER_ID}, {"$set": payload}, session=session)
        return await db.categories.find_one({"id": cid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    return await payment_transaction(operation)


@api.delete("/categories/{cid}")
async def delete_category(cid: str):
    async def operation(session):
        for collection, label in ((db.transactions, "movimientos"), (db.budgets, "presupuestos"),
                                  (db.debts, "deudas"), (db.recurring_templates, "recurrencias"),
                                  (db.bills, "facturas"), (db.recurring_payments, "pagos recurrentes")):
            if await collection.find_one({"category_id": cid}, PROJ, session=session):
                raise HTTPException(409, f"Esta categoría está utilizada por {label}. Resuelve sus referencias antes de eliminarla.")
        if await db.recurring_payment_records.find_one({"category_id": cid, "deleted": {"$ne": True}}, PROJ, session=session):
            raise HTTPException(409, "La categoría está utilizada por registros recurrentes activos.")
        if await db.categories.find_one({"parent_id": cid}, PROJ, session=session):
            raise HTTPException(409, "La categoría tiene subcategorías vinculadas.")
        await db.categories.delete_one({"id": cid, "user_id": DEFAULT_USER_ID}, session=session)
        return {"ok": True}
    return await payment_transaction(operation)


@api.post("/categories/init-defaults")
async def init_default_categories():
    from backend.catalog_operations import initialize_categories

    await ensure_user()
    return await payment_transaction(lambda session: initialize_categories(db, DEFAULT_USER_ID, session))


# Transactions
@api.get("/transactions/page")
async def transaction_page(
    account_id: Annotated[Optional[str], Query(min_length=1, max_length=256)] = None,
    category_id: Annotated[Optional[str], Query(min_length=1, max_length=256)] = None,
    types: Annotated[Optional[List[str]], Query(alias="type")] = None,
    start: Optional[str] = None, end: Optional[str] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    order: Literal["recent", "oldest", "high", "low"] = "recent",
    cursor: Annotated[Optional[str], Query(min_length=1, max_length=2048)] = None,
):
    return await read_transaction_page(
        db, DEFAULT_USER_ID, PROJ, shared_public,
        context=[settings.mongo_url, settings.db_name, settings.expected_financial_environment_id],
        account_id=account_id, category_id=category_id, types=types,
        start=start, end=end, limit=limit, order=order, cursor=cursor)


@api.get("/transactions/{tid}")
async def get_transaction(tid: str):
    return await read_transaction_detail(db, DEFAULT_USER_ID, tid, PROJ, shared_public)


@api.get("/transactions")
async def list_transactions(limit: int = 500):
    return shared_public(await db.transactions.find({"user_id": DEFAULT_USER_ID}, PROJ).sort("date", -1).to_list(limit))


@api.post("/transactions")
async def create_transaction(data: TransactionCreate):
    if data.debt_id or data.type == "debt_payment":
        raise HTTPException(409, "Registra los pagos mediante /api/debt-payments para mantener su vínculo.")
    payload = data.model_dump()
    if not payload.get("date"):
        payload["date"] = now_iso()
    # Identity/date stay stable across retries of an aborted transaction.
    tid = new_id()
    async def operation(session):
        await validate_transaction(payload, session=session)
        tx = Transaction(id=tid, user_id=DEFAULT_USER_ID, **payload).model_dump()
        stored = dict(tx, _id=tid)
        if getattr(settings, "history_keys_write_enabled", False):
            stored = with_history_keys(stored, settings.history_keys_generation)
        await db.transactions.insert_one(stored, session=session)
        for aid in sorted({tx.get("account_id"), tx.get("to_account_id")} - {None}):
            await recompute_account_balance(aid, session=session)
        return tx
    return shared_public(await ordinary_transaction(operation))


@api.put("/transactions/{tid}")
async def update_transaction(tid: str, data: TransactionCreate):
    old = await db.transactions.find_one({"id": tid}, PROJ)
    if not old:
        raise HTTPException(404, "Not found")
    if old.get("goal_contribution_id"):
        raise HTTPException(409, "Este movimiento está vinculado a un aporte de una meta de ahorro; adminístralo desde Metas de ahorro.")
    if old.get("bill_payment_id"):
        raise HTTPException(409, "Este movimiento está vinculado a una factura; adminístralo desde Facturas.")
    if old.get("recurring_record_id"):
        raise HTTPException(409, "Este movimiento está vinculado a un pago recurrente; adminístralo desde Pagos recurrentes.")
    if old.get("debt_payment_id"):
        return await edit_payment_movement(tid, data)
    if old.get("debt_id") or data.debt_id or data.type == "debt_payment":
        raise HTTPException(409, "El movimiento requiere un vínculo individual con su pago antes de editarlo.")
    async def operation(session):
        current = await db.transactions.find_one({"id": tid}, INTERNAL_PROJ, session=session)
        if not current:
            raise HTTPException(404, "Not found")
        # The initial read only selects the existing payment route. Recheck
        # financial links against the same snapshot as the ordinary writes.
        for field in ("goal_contribution_id", "bill_payment_id", "recurring_record_id", "debt_payment_id", "debt_id"):
            if current.get(field):
                raise HTTPException(409, "Este movimiento está vinculado; adminístralo desde su operación financiera.")
        await check_movement_references(db, DEFAULT_USER_ID, current, session)
        payload = transaction_edit_payload(data, current)
        await validate_transaction(payload, current, session=session)
        changes = dict(payload)
        if getattr(settings, "history_keys_write_enabled", False):
            final = {**current, **payload}
            changes.update(history_update_fields(current, final, settings.history_keys_generation))
        await db.transactions.update_one({"id": tid}, {"$set": changes}, session=session)
        for aid in sorted({current.get("account_id"), current.get("to_account_id"), payload.get("account_id"), payload.get("to_account_id")} - {None}):
            await recompute_account_balance(aid, session=session)
        return await db.transactions.find_one({"id": tid}, PROJ, session=session)
    return shared_public(await ordinary_transaction(operation))


@api.delete("/transactions/{tid}")
async def delete_transaction(tid: str):
    old = await db.transactions.find_one({"id": tid}, PROJ)
    if old and old.get("goal_contribution_id"):
        raise HTTPException(409, "Este movimiento está vinculado a un aporte de una meta de ahorro; adminístralo desde Metas de ahorro.")
    if old and old.get("bill_payment_id"):
        raise HTTPException(409, "Este movimiento está vinculado a una factura; adminístralo desde Facturas.")
    if old and old.get("recurring_record_id"):
        raise HTTPException(409, "Este movimiento está vinculado a un pago recurrente; adminístralo desde Pagos recurrentes.")
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
            await check_movement_references(db, DEFAULT_USER_ID, current, session, debt_payment_id=payment["id"])
            return await remove_payment(payment["id"], session)
        return await payment_transaction(operation)
    if old and old.get("debt_id"):
        raise HTTPException(409, "Movimiento antiguo sin vínculo individual: requiere conciliación antes de borrar.")
    async def operation(session):
        current = await db.transactions.find_one({"id": tid}, PROJ, session=session)
        if current:
            for field in ("goal_contribution_id", "bill_payment_id", "recurring_record_id", "debt_payment_id", "debt_id"):
                if current.get(field):
                    raise HTTPException(409, "Este movimiento está vinculado; adminístralo desde su operación financiera.")
            if await db.recurring_templates.find_one({"source_transaction_id": tid}, PROJ, session=session):
                raise HTTPException(409, "Este movimiento es origen de una recurrencia. Elimina primero esa configuración de recurrencia.")
            await check_movement_references(db, DEFAULT_USER_ID, current, session)
            await db.transactions.delete_one({"id": tid}, session=session)
            for aid in sorted({current.get("account_id"), current.get("to_account_id")} - {None}):
                await recompute_account_balance(aid, session=session)
        return {"ok": True}
    return await ordinary_transaction(operation)


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
    async def operation(session):
        await coordinate(db, DEFAULT_USER_ID, payload, session)
        await db.recurring_templates.insert_one(rt.copy(), session=session)
        return reference_public(rt)
    return await payment_transaction(operation)


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
    from backend.planning_operations import _budget_window as calculate

    return calculate(b, m_start, m_end, tz, now)


def _scope_ids(category_id, cats_by_id):
    from backend.planning_operations import _scope_ids as calculate

    return calculate(category_id, cats_by_id)


def _status(spent: Decimal, limit: Decimal, threshold: int) -> str:
    from backend.planning_operations import _status as calculate

    return calculate(spent, limit, threshold)


async def _compute_budgets(year: int, month: int, tz_offset: int, only_id: Optional[str] = None):
    from backend.planning_operations import PlanningOperations

    return await PlanningOperations(db, DEFAULT_USER_ID)._compute_budgets(
        year, month, tz_offset, only_id, now=datetime.now(timezone.utc)
    )


def _public(row, with_tx=False):
    out = {k: v for k, v in row.items() if not k.startswith("_")}
    if with_tx:
        out["transactions"] = sorted(
            ({k: v for k, v in t.items() if k != "_dt"} for t in row["_matched"]),
            key=lambda t: t.get("date") or "", reverse=True,
        )
    return shared_public(out)


def _overlaps(a_start, a_end, b_start, b_end):
    inf = datetime.max.replace(tzinfo=timezone.utc)
    return (a_start or datetime.min.replace(tzinfo=timezone.utc)) < (b_end or inf) and \
        (b_start or datetime.min.replace(tzinfo=timezone.utc)) < (a_end or inf)


async def _validate_budget(data: BudgetCreate, replacing: Optional[str] = None, session=None, old=None) -> dict:
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
    cat = await db.categories.find_one({"id": payload["category_id"], "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    if (not cat or cat.get("type") != "expense") and (old is None or old.get("category_id") != payload["category_id"]):
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
        payload["name"] = cat["name"] if cat else old.get("name", "")
    # Duplicate guard: same category + same period type with overlapping dates.
    q = {"user_id": DEFAULT_USER_ID, "category_id": payload["category_id"], "period": payload["period"]}
    if replacing:
        q["id"] = {"$ne": replacing}
    await coordinate(db, DEFAULT_USER_ID, payload, session, old)
    async for other in db.budgets.find(q, PROJ, session=session):
        if _overlaps(start, end, _parse_dt(other.get("start_date")), _parse_dt(other.get("end_date"))):
            raise HTTPException(409, "Ya existe un presupuesto para esta categoría y período en esas fechas.")
    return payload


@api.get("/budgets")
async def list_budgets():
    return await db.budgets.find({"user_id": DEFAULT_USER_ID}, {"_id": 0, "idempotency_key": 0, "request_fingerprint": 0}).sort("created_at", -1).to_list(500)


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
    bid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEFAULT_USER_ID}:budget:{idempotency_key}")) if idempotency_key else new_id()
    try:
        fingerprint = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest() if idempotency_key else None
    except (ValueError, TypeError):
        raise HTTPException(422, "La solicitud original no es válida.") from None
    async def operation(session):
        if idempotency_key:
            # Include legacy random IDs; never adopt their current fields as an
            # original request. The native _id index serializes new keyed creates.
            matches = await db.budgets.find({"user_id": DEFAULT_USER_ID, "idempotency_key": idempotency_key}, session=session).to_list(2)
            if len(matches) > 1:
                raise HTTPException(409, "La clave tiene registros históricos ambiguos; requiere verificación.")
            if matches:
                existing = matches[0]
                if existing.get("request_fingerprint") != fingerprint:
                    raise HTTPException(409, "La clave tiene otra solicitud o no conserva una huella original verificable.")
                return shared_public(existing)
        payload = await _validate_budget(data, session=session)
        b = Budget(id=bid, user_id=DEFAULT_USER_ID, **payload).model_dump()
        doc = {**b, "_id": bid, **({"idempotency_key": idempotency_key, "request_fingerprint": fingerprint} if idempotency_key else {})}
        await db.budgets.insert_one(doc, session=session)
        return reference_public(b)
    return await payment_transaction(operation)


@api.put("/budgets/{bid}")
async def update_budget(bid: str, data: BudgetCreate):
    async def operation(session):
        old = await db.budgets.find_one({"id": bid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
        if not old:
            raise HTTPException(404, "Presupuesto no encontrado.")
        effective = data.model_copy(update={"category_id": old.get("category_id")}) if "category_id" not in data.model_fields_set else data
        payload = await _validate_budget(effective, replacing=bid, session=session, old=old)
        payload["updated_at"] = now_iso()
        await db.budgets.update_one({"id": bid, "user_id": DEFAULT_USER_ID}, {"$set": payload}, session=session)
        doc = await db.budgets.find_one({"id": bid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
        return shared_public(doc)
    return await payment_transaction(operation)


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
GOAL_HIDDEN = {"_id", "request_fingerprint", "_reference_revision"}
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
    from backend.planning_operations import _goal_public as calculate

    return calculate(g, today)


async def recompute_goal(gid, session=None):
    from backend.planning_operations import PlanningOperations

    return await PlanningOperations(db, DEFAULT_USER_ID).recompute_goal(gid, session)


async def _validate_goal(data: SavingGoalCreate, replacing=None, session=None, old=None, supplied=None):
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
    if data.account_id and (old is None or data.account_id != old.get("account_id")) and not await db.accounts.find_one({"id": data.account_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
        raise HTTPException(422, "La cuenta asociada no existe.")
    q = {"user_id": DEFAULT_USER_ID, "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
    if replacing:
        q["id"] = {"$ne": replacing}
    if await db.saving_goals.find_one(q, PROJ, session=session):
        raise HTTPException(409, "Ya existe una meta con ese nombre.")
    fields = {
        "name": name, "target_amount": target, "target_date": _goal_target_date(data.target_date),
        "priority": data.priority, "color": data.color or "#29C4A9", "icon": data.icon or "flag-outline",
        "account_id": data.account_id or None,
    }
    preserve_references(fields, data, old, ("account_id",), supplied)
    await coordinate(db, DEFAULT_USER_ID, fields, session, old)
    return fields, initial


async def _contributions_page(gid, limit, offset, session=None):
    limit = max(1, min(int(limit or 20), 100))
    offset = max(0, int(offset or 0))
    q = {"user_id": DEFAULT_USER_ID, "goal_id": gid, "deleted": {"$ne": True}}
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
    async def operation(session):
        previous = await db.saving_goals.find_one({"_id": gid, "user_id": DEFAULT_USER_ID}, session=session)
        if previous:
            if previous.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            return _goal_public(previous)
        fields, initial = await _validate_goal(data, session=session)
        initial = initial or 0.0
        g = SavingGoal(id=gid, user_id=DEFAULT_USER_ID, current_amount=initial, initial_amount=initial, **fields).model_dump()
        if g["target_amount"] > 0 and initial >= g["target_amount"]:
            g["completed_at"] = now_iso()
        stored = dict(g, _id=gid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await db.saving_goals.insert_one(stored, session=session)
        return _goal_public(g)
    return await payment_transaction(operation)


@api.put("/goals/{gid}")
async def update_goal(gid: str, data: SavingGoalCreate):
    async def operation(session):
        if not await db.saving_goals.find_one({"id": gid, "user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1}, session=session):
            raise HTTPException(404, "Meta no encontrada.")
        old = await db.saving_goals.find_one({"id": gid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
        effective = data.model_copy(update={"account_id": old.get("account_id")}) if "account_id" not in data.model_fields_set else data
        fields, initial = await _validate_goal(effective, replacing=gid, session=session, old=old, supplied=data.model_fields_set)
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
        await coordinate(db, DEFAULT_USER_ID, {"goal_id": gid}, session)
        contributions = await db.goal_contributions.find({"goal_id": gid, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, session=session).to_list(None)
        ids = {c["id"] for c in contributions}
        async for tx in db.transactions.find({"goal_id": gid, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            if tx.get("goal_contribution_id") not in ids:
                raise HTTPException(409, "La meta tiene movimientos sin un aporte verificable.")
        for contribution in contributions:
            await check_goal_contribution(db, DEFAULT_USER_ID, contribution, session)
            await retire(db, "goal_contributions", contribution, DEFAULT_USER_ID, session)
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
            if previous.get("deleted"):
                raise HTTPException(409, "El aporte ya fue anulado; no se volverá a crear.")
            g = await db.saving_goals.find_one({"id": gid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
            return {"contribution": _goal_clean(previous), "goal": _goal_public(g) if g else None}
        g = await recompute_goal(gid, session=session)
        if not g:
            raise HTTPException(404, "Meta no encontrada.")
        if data.account_id and not await db.accounts.find_one({"id": data.account_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            raise HTTPException(422, "La cuenta seleccionada no existe.")
        await coordinate(db, DEFAULT_USER_ID, {"goal_id": gid, "account_id": data.account_id}, session)
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
            stored_movement = dict(tx, _id=tid)
            if getattr(settings, "history_keys_write_enabled", False):
                stored_movement = with_history_keys(stored_movement, settings.history_keys_generation)
            await db.transactions.insert_one(stored_movement, session=session)
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
    from backend import debt_operations as operations

    return await payment_transaction(lambda session: operations.create_debt(db, DEFAULT_USER_ID, data, session))


@api.put("/debts/{did}")
async def update_debt(did: str, data: DebtCreate):
    from backend import debt_operations as operations

    return shared_public(await payment_transaction(lambda session: operations.update_debt(db, DEFAULT_USER_ID, did, data, session)))


@api.delete("/debts/{did}")
async def delete_debt(did: str):
    from backend import debt_operations as operations

    return await payment_transaction(lambda session: operations.delete_debt(db, DEFAULT_USER_ID, did, session))


# Debt Payments
@api.get("/debts/{did}/payments")
async def list_debt_payments(did: str):
    payments = await db.debt_payments.find({"debt_id": did, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, PROJ).sort("date", -1).to_list(500)
    return [DebtPayment(**payment).model_dump() for payment in payments]


@api.post("/debt-payments")
async def create_debt_payment(
    data: DebtPaymentCreate,
    idempotency_key: Optional[str] = Header(default=None, min_length=1, max_length=128),
    expected_environment: Optional[str] = Header(default=None, alias="MoneyFlow-Environment-ID", min_length=1, max_length=36),
    expected_user: Optional[str] = Header(default=None, alias="MoneyFlow-User-ID", min_length=1, max_length=128),
):
    from backend import debt_operations as operations

    if (expected_environment is None) != (expected_user is None):
        raise HTTPException(422, "Envía ambas cabeceras de contexto o ninguna.")

    unkeyed_id, now = new_id(), now_iso()

    async def operation(session):
        if expected_environment is not None:
            await verify_payment_context(db, settings.expected_financial_environment_id, DEFAULT_USER_ID,
                                         expected_environment, expected_user, session)
        generation = settings.history_keys_generation if getattr(settings, "history_keys_write_enabled", False) else None
        return await operations.create_payment(
            db, DEFAULT_USER_ID, data, idempotency_key, session, generation,
            unkeyed_id=unkeyed_id, now=now,
        )

    return await payment_transaction(operation)


@api.post("/debt-payments/reconcile")
async def reconcile_debt_payment(
    data: DebtPaymentCreate,
    idempotency_key: str = Header(min_length=1, max_length=128),
    expected_environment: Optional[str] = Header(default=None, alias="MoneyFlow-Environment-ID", min_length=1, max_length=36),
    expected_user: Optional[str] = Header(default=None, alias="MoneyFlow-User-ID", min_length=1, max_length=128),
):
    from backend import debt_operations as operations

    if (expected_environment is None) != (expected_user is None):
        raise HTTPException(422, "Envía ambas cabeceras de contexto o ninguna.")

    async def operation(session):
        if expected_environment is not None:
            await verify_payment_context(db, settings.expected_financial_environment_id, DEFAULT_USER_ID,
                                         expected_environment, expected_user, session)
        return await operations.reconcile_payment(db, DEFAULT_USER_ID, data, idempotency_key, session)

    try:
        return await ordinary_transaction(operation)
    except HTTPException as error:
        if error.status_code != 503:
            raise
        return {"status": "unverifiable",
                "reason": "No se pudo verificar el contexto o completar la lectura consistente.",
                "payment_id": operations.payment_id(DEFAULT_USER_ID, idempotency_key),
                "retry_requires_original_key_and_payload": True}


@api.delete("/debt-payments/{pid}")
async def delete_debt_payment(pid: str):
    return await payment_transaction(lambda session: remove_payment(pid, session))


# Reports summary
@api.get("/summary")
async def summary():
    import asyncio

    from backend.financial_summary import summarize

    async def snapshot():
        session = await client.start_session()
        try:
            async with session.start_transaction(
                read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority"),
                max_commit_time_ms=10000,
            ):
                return await summarize(db, DEFAULT_USER_ID, session, now=datetime.now(timezone.utc))
        finally:
            try:
                await asyncio.wait_for(session.end_session(), 1)
            except (PyMongoError, TimeoutError):
                logger.warning("Could not close read-only summary session")

    try:
        return await asyncio.wait_for(snapshot(), 10)
    except (PyMongoError, TimeoutError):
        raise HTTPException(503, "No se pudo completar el resumen. Reintenta; no se devolvieron totales parciales.") from None

# Demo loading stays disabled until it has an isolated data store.
@api.post("/seed")
async def seed():
    raise HTTPException(
        status_code=403,
        detail="La carga de datos demo está deshabilitada para proteger tus datos.",
    )


# ---------- Recurring payments (bills / subscriptions) ----------
# Independent from /api/recurring (config-only templates attached to movements),
# which stays untouched. Design:
# * A recurrence stores schedule "versions"; each version applies to due dates
#   >= its valid_from, so editing amount/frequency/dates never rewrites the past.
# * Due dates (occurrences) are computed on demand from the schedule (no stored
#   placeholders -> repeated queries or restarts can never duplicate them).
# * Payments are stored as records keyed by (recurring_id, due_date):
#     mark    -> tracking only, no movement, balances untouched
#     expense -> creates ONE expense movement (atomic, Mongo transaction)
#     link    -> links an existing expense movement (no new movement)
# * Nothing is created automatically when a due date arrives.
RP_FREQS = {
    "daily": ("d", 1), "weekly": ("d", 7), "biweekly": ("d", 14), "monthly": ("m", 1),
    "bimonthly": ("m", 2), "quarterly": ("m", 3), "semiannual": ("m", 6), "annual": ("m", 12),
}
RP_REMINDERS = {None, 0, 1, 3, 7}
RP_LINK_FIELDS = ("recurring_record_id", "goal_contribution_id", "debt_payment_id", "debt_id", "bill_payment_id")


class RecurringPaymentCreate(BaseModel):
    name: str = ""
    amount: float
    variable: bool = False
    category_id: Optional[str] = None
    account_id: Optional[str] = None
    frequency: str = "monthly"
    start_date: str
    end_date: Optional[str] = None
    due_day: Optional[int] = None
    icon: str = "receipt-outline"
    color: str = "#2FA47C"
    notes: Optional[str] = None
    reminder_days: Optional[int] = None
    active: bool = True


class RecurringPayRecordCreate(BaseModel):
    due_date: str
    mode: Literal["mark", "expense", "link"] = "mark"
    amount: Optional[float] = None
    date: Optional[str] = None
    account_id: Optional[str] = None
    category_id: Optional[str] = None
    notes: Optional[str] = None
    transaction_id: Optional[str] = None
    # None -> automatic (variable bills settle with the real amount; fixed ones when fully covered).
    settles: Optional[bool] = None
    allow_overpay: bool = False


def _rp_day(value, msg):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        raise HTTPException(422, msg)


def _rp_today(tz_offset: int = 0):
    return datetime.now(_local_tz(tz_offset)).date()


def _rp_dates(ver, a: date, b: date):
    from backend.obligation_operations import _rp_dates as project

    return project(ver, a, b)


def _rp_paused(rp, d: date):
    from backend.obligation_operations import _rp_paused as project

    return project(rp, d)


def _rp_occurrences(rp, a: date, b: date):
    from backend.obligation_operations import _rp_occurrences as project

    return project(rp, a, b)


def _shared_reader(endpoint):
    return shared_read_route(lambda: db, lambda: client,
        lambda: settings.expected_financial_environment_id, lambda: DEFAULT_USER_ID)(endpoint)


def _rp_state(rp, due_iso, expected, recs, today):
    from backend.obligation_operations import _rp_state as project

    return project(rp, due_iso, expected, recs, today)


def _rp_state_name(rp, today):
    from backend.obligation_operations import _rp_state_name as project

    return project(rp, today)


def _rp_current(rp):
    from backend.obligation_operations import _rp_current as project

    return project(rp)


def _rp_public(rp, today):
    from backend.obligation_operations import _rp_public as project

    return project(rp, today)


async def _rp_records(rid=None, a=None, b=None, session=None):
    q = {"user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}
    if rid:
        q["recurring_id"] = rid
    if a or b:
        q["due_date"] = {}
        if a:
            q["due_date"]["$gte"] = a.isoformat()
        if b:
            q["due_date"]["$lte"] = b.isoformat()
    grouped = {}
    async for r in read_database(db).recurring_payment_records.find(q, {"_id": 0, "request_fingerprint": 0}, session=session):
        grouped.setdefault((r["recurring_id"], r["due_date"]), []).append(r)
    return grouped


def _rp_month_states(rp, a, b, records, today):
    from backend.obligation_operations import _rp_month_states as project

    return project(rp, a, b, records, today)


def _rp_next_due(rp, records, today, horizon_days=800):
    from backend.obligation_operations import _rp_next_due as project

    return project(rp, records, today, horizon_days)


async def _rp_validate(data: RecurringPaymentCreate, session=None, old=None, supplied=None):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(422, "El nombre del pago es obligatorio.")
    if len(name) > 60:
        raise HTTPException(422, "El nombre es demasiado largo (máx. 60).")
    amount = _positive_money(data.amount, "El monto previsto debe ser mayor que cero.")
    if data.frequency not in RP_FREQS:
        raise HTTPException(422, "Frecuencia no válida.")
    start = _rp_day(data.start_date, "La fecha de inicio no es válida.")
    end = _rp_day(data.end_date, "La fecha de finalización no es válida.") if data.end_date else None
    if end and end < start:
        raise HTTPException(422, "La fecha de finalización debe ser posterior a la de inicio.")
    due_day = None
    if RP_FREQS[data.frequency][0] == "m":
        due_day = start.day if data.due_day is None else data.due_day
        if not 1 <= due_day <= 31:
            raise HTTPException(422, "El día de vencimiento debe estar entre 1 y 31.")
    if data.reminder_days not in RP_REMINDERS:
        raise HTTPException(422, "Recordatorio no válido.")
    if data.category_id and (old is None or data.category_id != old.get("category_id")):
        cat = await db.categories.find_one({"id": data.category_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
        if not cat or cat.get("type") != "expense" or cat.get("is_group"):
            raise HTTPException(422, "La categoría debe ser una categoría de gasto existente.")
    if data.account_id and (old is None or data.account_id != old.get("account_id")) and not await db.accounts.find_one({"id": data.account_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
        raise HTTPException(422, "La cuenta asociada no existe.")
    color = data.color if re.fullmatch(r"#[0-9a-fA-F]{6}", data.color or "") else "#2FA47C"
    fields = {
        "name": name, "variable": bool(data.variable), "category_id": data.category_id or None,
        "account_id": data.account_id or None, "end_date": end.isoformat() if end else None,
        "icon": (data.icon or "receipt-outline")[:40], "color": color,
        "notes": (data.notes or "").strip()[:200] or None, "reminder_days": data.reminder_days,
    }
    version = {"frequency": data.frequency, "start_date": start.isoformat(), "due_day": due_day, "amount": amount}
    preserve_references(fields, data, old, ("account_id", "category_id"), supplied)
    await coordinate(db, DEFAULT_USER_ID, fields, session, old)
    return fields, version


async def _rp_get(rid, session=None):
    rp = await read_database(db).recurring_payments.find_one({"id": rid, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
    if not rp:
        raise HTTPException(404, "Pago recurrente no encontrado.")
    return rp


@api.get("/recurring-payments")
@_shared_reader
async def list_recurring_payments(tz_offset: int = 0):
    today = _rp_today(tz_offset)
    rps = await read_database(db).recurring_payments.find({"user_id": DEFAULT_USER_ID}, PROJ).sort("created_at", -1).to_list(500)
    return [_rp_public(rp, today) for rp in rps]


@api.get("/recurring-payments/overview")
@_shared_reader
async def recurring_overview(year: Optional[int] = None, month: Optional[int] = None, tz_offset: int = 0):
    today = _rp_today(tz_offset)
    year, month = year or today.year, month or today.month
    if not 1 <= month <= 12 or not 1900 <= year <= 3000:
        raise HTTPException(422, "Mes no válido.")
    a = date(year, month, 1)
    b = date(year, month, calendar.monthrange(year, month)[1])
    rps = await read_database(db).recurring_payments.find({"user_id": DEFAULT_USER_ID}, PROJ).sort("created_at", -1).to_list(500)
    rem_hi = today + timedelta(days=7)
    records = await _rp_records(a=min(a, today - timedelta(days=400)), b=max(b, rem_hi + timedelta(days=800)))
    tot = {"expected": Decimal(0), "paid": Decimal(0), "pending": Decimal(0)}
    counts = {"total": 0, "paid": 0, "pending": 0, "overdue": 0}
    items, reminders = [], []
    for rp in rps:
        pub = _rp_public(rp, today)
        states = _rp_month_states(rp, a, b, records, today)
        for st in states:
            counts["total"] += 1
            tot["expected"] += Decimal(str(st["expected"]))
            tot["paid"] += Decimal(str(st["paid"]))
            tot["pending"] += Decimal(str(st["remaining"]))
            if st["status"] == "paid":
                counts["paid"] += 1
            else:
                counts["pending"] += 1
                if st["status"] == "overdue":
                    counts["overdue"] += 1
        if states:
            unpaid = [s for s in states if s["status"] != "paid"]
            focus = unpaid[0] if unpaid else states[-1]
            card_status = "overdue" if any(s["status"] == "overdue" for s in states) else ("pending" if unpaid else "paid")
        elif pub["state"] in ("active", "paused"):
            focus = _rp_next_due(rp, records, today) if pub["state"] == "active" else None
            card_status = "paused" if pub["state"] == "paused" else "upcoming"
        else:
            continue  # ended and nothing due this month
        items.append({
            **pub, "card_status": card_status, "due_date": focus["due_date"] if focus else None,
            "due_expected": focus["expected"] if focus else pub["amount"], "due_paid": focus["paid"] if focus else 0,
            "due_remaining": focus["remaining"] if focus else 0, "partial": bool(focus and focus["partial"]),
            "month_count": len(states), "month_paid_count": sum(1 for s in states if s["status"] == "paid"),
            "month_expected": float(sum((Decimal(str(s["expected"])) for s in states), Decimal(0))),
            "month_paid": float(sum((Decimal(str(s["paid"])) for s in states), Decimal(0))),
        })
        # In-app reminders (independent from the selected month).
        if pub["state"] == "active" and rp.get("reminder_days") is not None:
            reminder_dues = _rp_occurrences(rp, today, rem_hi)
            for due in current_shared_periods(rp["id"]):
                if today.isoformat() <= due <= rem_hi.isoformat():
                    reminder_dues.setdefault(due, None)
            for d, exp in sorted(reminder_dues.items()):
                left = (date.fromisoformat(d) - today).days
                st = _rp_state(rp, d, exp, records.get((rp["id"], d), []), today)
                if st["status"] != "paid" and left <= rp["reminder_days"]:
                    reminders.append({"id": rp["id"], "name": rp["name"], "icon": rp.get("icon"), "color": rp.get("color"),
                                      "due_date": d, "days_left": left, "remaining": st["remaining"]})
                    break
    settled_base = tot["paid"] + tot["pending"]
    pct = float((tot["paid"] / settled_base * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if settled_base > 0 else None
    return {
        "year": year, "month": month, "today": today.isoformat(),
        "totals": {"expected": float(tot["expected"]), "paid": float(tot["paid"]), "pending": float(tot["pending"]), "paid_pct": pct},
        "counts": counts, "items": items, "reminders": sorted(reminders, key=lambda r: r["due_date"]),
    }


@api.get("/recurring-payments/{rid}")
@_shared_reader
async def get_recurring_payment(rid: str, tz_offset: int = 0):
    today = _rp_today(tz_offset)
    rp = await _rp_get(rid)
    records = await _rp_records(rid=rid)
    out = _rp_public(rp, today)
    out["next_due"] = _rp_next_due(rp, records, today) if out["state"] == "active" else None
    views = current_shared_periods(rid)
    ordinary = [r for (_, due), rs in records.items() if due not in views for r in rs]
    out["paid_total"] = float(sum((Decimal(str(r["amount"])) for r in ordinary), Decimal(0))
                              + sum((v.summary.paid for v in views.values()), Decimal(0)))
    out["payments_count"] = len(ordinary) + len(shared_paid_events(views.values()))
    out["account"] = await read_database(db).accounts.find_one({"id": rp.get("account_id"), "user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1, "name": 1, "color": 1}) if rp.get("account_id") else None
    out["category"] = await read_database(db).categories.find_one({"id": rp.get("category_id"), "user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1, "name": 1, "icon": 1, "color": 1}) if rp.get("category_id") else None
    return shared_public(out)


@api.get("/recurring-payments/{rid}/occurrences")
@_shared_reader
async def recurring_occurrences(rid: str, offset: int = 0, limit: int = 20, tz_offset: int = 0):
    today = _rp_today(tz_offset)
    rp = await _rp_get(rid)
    limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
    records = await _rp_records(rid=rid)
    first = min((date.fromisoformat(v["start_date"]) for v in rp.get("versions") or []), default=today)
    nxt = _rp_next_due(rp, records, today)
    hi = max(date(today.year, today.month, calendar.monthrange(today.year, today.month)[1]),
             date.fromisoformat(nxt["due_date"]) if nxt else today)
    occ = _rp_occurrences(rp, first, hi)
    for (_, due) in records:
        occ.setdefault(due, None)
    for due in current_shared_periods(rid):
        occ.setdefault(due, None)
    dues = sorted(occ, reverse=True)
    page = dues[offset:offset + limit]
    items = [_rp_state(rp, d, occ[d], records.get((rid, d), []), today) for d in page]
    return {"items": items, "total": len(dues), "offset": offset, "limit": limit, "has_more": offset + len(page) < len(dues)}


@api.get("/recurring-payments/{rid}/link-candidates")
@_shared_reader
async def recurring_link_candidates(rid: str, due_date: str):
    rp = await _rp_get(rid)
    d = _rp_day(due_date, "Fecha no válida.")
    view = current_shared_view(recurring_id=rid, due=d.isoformat())
    if view is not None:
        return await shared_link_candidates(view)
    lo = datetime.combine(d - timedelta(days=15), datetime.min.time(), timezone.utc).isoformat()
    hi = datetime.combine(d + timedelta(days=16), datetime.min.time(), timezone.utc).isoformat()
    q = {"user_id": DEFAULT_USER_ID, "type": "expense", "date": {"$gte": lo, "$lt": hi}}
    for f in RP_LINK_FIELDS:
        q[f] = None
    txs = await read_database(db).transactions.find(q, PROJ).sort("date", -1).to_list(200)
    txs = [tx for tx in txs if not any(key.startswith("_shared_") for key in tx)]
    target = _rp_current(rp).get("amount") or 0
    txs.sort(key=lambda t: (abs(t["amount"] - target), 0 if t.get("category_id") == rp.get("category_id") else 1))
    return shared_public(txs[:10])


@api.post("/recurring-payments")
async def create_recurring_payment(
    data: RecurringPaymentCreate,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=128),
):
    rid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEFAULT_USER_ID}:recurring-payment:{idempotency_key}")) if idempotency_key else new_id()
    fingerprint = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest()
    today = _rp_today()
    async def operation(session):
        await guard_legacy_recurring(db, DEFAULT_USER_ID, rid, session)
        prev = await db.recurring_payments.find_one({"_id": rid, "user_id": DEFAULT_USER_ID}, session=session)
        if prev:
            if prev.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            return _rp_public(prev, today)
        fields, version = await _rp_validate(data, session=session)
        now = now_iso()
        rp = {
            "id": rid, "user_id": DEFAULT_USER_ID, **fields, "state": "active" if data.active else "paused",
            "versions": [{**version, "valid_from": version["start_date"]}],
            "pauses": [] if data.active else [{"start": min(today, date.fromisoformat(version["start_date"])).isoformat(), "end": None}],
            "created_at": now, "updated_at": None,
        }
        stored = dict(rp, _id=rid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await db.recurring_payments.insert_one(stored, session=session)
        return _rp_public(rp, today)
    return shared_public(await payment_transaction(operation))


@api.put("/recurring-payments/{rid}")
async def update_recurring_payment(rid: str, data: RecurringPaymentCreate):
    today = _rp_today()

    async def operation(session):
        context = await shared_parent_context(db, globals().get("settings"), origin="recurring", parent_id=rid,
            effective_user=DEFAULT_USER_ID, session=session)
        if context is not None:
            rp = context[1][0][3]
            effective = data.model_copy(update={f: rp.get(f) for f in ("account_id", "category_id", "end_date", "variable") if f not in data.model_fields_set})
            fields, version = await _rp_validate(effective, session, old=rp, supplied=data.model_fields_set)
            if "end_date" not in data.model_fields_set:
                fields["end_date"] = rp.get("end_date")
            result = await edit_shared_recurring(db, context, fields, version, session=session, today=today,
                occurrences=_rp_occurrences, add_period=_bill_add_period)
            return _rp_public(result, today)
        await guard_legacy_recurring(db, DEFAULT_USER_ID, rid, session)
        rp = await _rp_get(rid, session)
        effective = data.model_copy(update={f: rp.get(f) for f in ("account_id", "category_id") if f not in data.model_fields_set})
        fields, version = await _rp_validate(effective, session, old=rp, supplied=data.model_fields_set)
        cur = _rp_current(rp)
        vers = rp.get("versions") or []
        if any(cur.get(k) != version[k] for k in ("frequency", "start_date", "due_day", "amount")):
            first_start = min((v["start_date"] for v in vers), default=version["start_date"])
            if first_start >= today.isoformat():
                vers = [{**version, "valid_from": version["start_date"]}]
            else:
                # Past due dates keep the previous schedule/amount; the new one applies from today.
                cutoff = today.isoformat()
                vers = [v for v in vers if v["valid_from"] < cutoff] + [{**version, "valid_from": cutoff}]
        fields.update(versions=vers, updated_at=now_iso())
        await db.recurring_payments.update_one({"id": rid, "user_id": DEFAULT_USER_ID}, {"$set": fields}, session=session)
        return _rp_public(await _rp_get(rid, session), today)

    return shared_public(await payment_transaction(operation))


async def _rp_set_state(rid, action):
    today = _rp_today()
    async def operation(session):
        context = await shared_parent_context(db, globals().get("settings"), origin="recurring", parent_id=rid,
            effective_user=DEFAULT_USER_ID, session=session)
        if context is None:
            await guard_legacy_recurring(db, DEFAULT_USER_ID, rid, session)
        rp = await _rp_get(rid, session)
        state = _rp_state_name(rp, today)
        pauses = rp.get("pauses") or []
        upd = {"updated_at": now_iso()}
        if action == "pause":
            if state != "active":
                raise HTTPException(409, "Solo se puede pausar un pago activo.")
            upd.update(state="paused", pauses=pauses + [{"start": today.isoformat(), "end": None}])
        elif action == "resume":
            if state != "paused":
                raise HTTPException(409, "Solo se puede reactivar un pago pausado.")
            upd.update(state="active", pauses=[dict(p, end=p.get("end") or today.isoformat()) for p in pauses])
        else:
            if state == "ended":
                raise HTTPException(409, "La recurrencia ya está finalizada.")
            end = today.isoformat()
            if rp.get("end_date") and rp["end_date"] < end:
                end = rp["end_date"]
            upd.update(state="ended", end_date=end, pauses=[dict(p, end=p.get("end") or today.isoformat()) for p in pauses])
        if context is not None:
            await guard_shared_state_change(db, context, upd, session=session, today=today,
                occurrences=_rp_occurrences, add_period=_bill_add_period)
        await db.recurring_payments.update_one({"id": rid, "user_id": DEFAULT_USER_ID}, {"$set": upd}, session=session)
        return _rp_public(await _rp_get(rid, session), today)

    return shared_public(await payment_transaction(operation))


@api.post("/recurring-payments/{rid}/pause")
async def pause_recurring_payment(rid: str):
    return await _rp_set_state(rid, "pause")


@api.post("/recurring-payments/{rid}/resume")
async def resume_recurring_payment(rid: str):
    return await _rp_set_state(rid, "resume")


@api.post("/recurring-payments/{rid}/end")
async def end_recurring_payment(rid: str):
    return await _rp_set_state(rid, "end")


@api.delete("/recurring-payments/{rid}")
async def delete_recurring_payment(rid: str):
    async def operation(session):
        await guard_legacy_recurring(db, DEFAULT_USER_ID, rid, session)
        if not await db.recurring_payments.find_one({"id": rid, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            return {"ok": True}
        await coordinate(db, DEFAULT_USER_ID, {"recurring_id": rid}, session)
        records = await db.recurring_payment_records.find({"recurring_id": rid, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, session=session).to_list(None)
        ids = {r["id"] for r in records}
        async for tx in db.transactions.find({"recurring_payment_id": rid, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            if tx.get("recurring_record_id") not in ids:
                raise HTTPException(409, "La recurrencia tiene movimientos sin un registro verificable.")
        for rec in records:
            await check_record(db, DEFAULT_USER_ID, rec, session)
            if rec.get("bill_payment_id"):
                payment = await db.bill_payments.find_one({"id": rec["bill_payment_id"]}, PROJ, session=session)
                await _bill_for_write(payment["bill_id"], session)
                await db.bill_payments.update_one({"id": payment["id"], "user_id": DEFAULT_USER_ID}, {"$set": {"recurring_record_id": None}}, session=session)
            await retire(db, "recurring_payment_records", rec, DEFAULT_USER_ID, session)
        await db.bills.update_many({"recurring_payment_id": rid, "user_id": DEFAULT_USER_ID}, {"$set": {"recurring_payment_id": None}}, session=session)
        # Keep expenses and bill payments; remove both sides of the recurring link.
        await db.transactions.update_many({"recurring_payment_id": rid, "user_id": DEFAULT_USER_ID}, {"$unset": {"recurring_payment_id": "", "recurring_record_id": ""}}, session=session)
        await db.recurring_payments.delete_one({"id": rid, "user_id": DEFAULT_USER_ID}, session=session)
        return {"ok": True}
    return shared_public(await payment_transaction(operation))


@api.post("/recurring-payments/{rid}/payments")
async def create_recurring_record(
    rid: str,
    data: RecurringPayRecordCreate,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=128),
    expected_environment: Optional[str] = Header(default=None, alias="MoneyFlow-Environment-ID", min_length=1, max_length=36),
    expected_user: Optional[str] = Header(default=None, alias="MoneyFlow-User-ID", min_length=1, max_length=128),
):
    if (expected_environment is None) != (expected_user is None):
        raise HTTPException(422, "Envía ambas cabeceras de contexto o ninguna.")
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEFAULT_USER_ID}:recurring-record:{rid}:{idempotency_key}")) if idempotency_key else new_id()
    tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"recurring-record-movement:{pid}"))
    fingerprint = hashlib.sha256(json.dumps({"rid": rid, **data.model_dump()}, sort_keys=True, allow_nan=False).encode()).hexdigest()
    due = _rp_day(data.due_date, "La fecha de vencimiento no es válida.").isoformat()
    when = _parse_dt(data.date) if data.date else datetime.now(timezone.utc)
    if when is None:
        raise HTTPException(422, "La fecha efectiva no es válida.")
    notes = (data.notes or "").strip()[:200] or None
    today = _rp_today()

    async def operation(session):
        if expected_environment is not None:
            await verify_payment_context(db, settings.expected_financial_environment_id, DEFAULT_USER_ID,
                expected_environment, expected_user, session)
        shared = await dispatch_shared_payment(db, globals().get("settings"), origin="recurring",
            parent_id=rid, receipt_id=pid, transaction_id=tid, payload=data.model_dump(),
            effective_user=DEFAULT_USER_ID, session=session, occurrences=_rp_occurrences,
            add_period=_bill_add_period, recompute_account_balance=recompute_account_balance,
            effective_date=when.isoformat(), normalized_due=due)
        if shared is not None:
            return shared
        await guard_legacy_recurring(db, DEFAULT_USER_ID, rid, session, due)
        prev = await db.recurring_payment_records.find_one({"_id": pid, "user_id": DEFAULT_USER_ID}, session=session)
        if prev:
            if prev.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            if prev.get("deleted"):
                raise HTTPException(409, "La operación ya fue anulada; no se volverá a crear.")
            return {k: v for k, v in prev.items() if k not in ("_id", "request_fingerprint", "_reference_revision")}
        rp = await _rp_get(rid, session)
        await coordinate(db, DEFAULT_USER_ID, {"recurring_id": rid}, session)
        d = date.fromisoformat(due)
        occ = _rp_occurrences(rp, d, d)
        records = await _rp_records(rid=rid, a=d, b=d, session=session)
        existing = records.get((rid, due), [])
        if due not in occ and not existing:
            raise HTTPException(422, "La fecha no corresponde a un vencimiento de este pago.")
        st = _rp_state(rp, due, occ.get(due), existing, today)
        expected = Decimal(str(st["expected"]))
        tx = None
        if data.mode == "link":
            if not data.transaction_id:
                raise HTTPException(422, "Selecciona el movimiento a vincular.")
            tx = await db.transactions.find_one({"id": data.transaction_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
            if not tx or tx.get("type") != "expense":
                raise HTTPException(422, "El movimiento a vincular debe ser un gasto existente.")
            if any(tx.get(f) for f in RP_LINK_FIELDS):
                raise HTTPException(409, "Ese movimiento ya está vinculado a otro registro.")
            await guard_legacy_movement(db, DEFAULT_USER_ID, tx, session)
            amount = float(tx["amount"])
        else:
            amount = _positive_money(data.amount, "El monto pagado debe ser mayor que cero.")
        if data.account_id and not await db.accounts.find_one({"id": data.account_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            raise HTTPException(422, "La cuenta seleccionada no existe.")
        cat_id = data.category_id or rp.get("category_id")
        if data.category_id:
            cat = await db.categories.find_one({"id": data.category_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
            if not cat or cat.get("type") != "expense" or cat.get("is_group"):
                raise HTTPException(422, "La categoría debe ser una categoría de gasto existente.")
        await coordinate(db, DEFAULT_USER_ID, {"account_id": tx.get("account_id") if tx else data.account_id,
                                               "category_id": tx.get("category_id") if tx else cat_id}, session)
        if not rp.get("variable") and not data.allow_overpay:
            if st["status"] == "paid":
                raise HTTPException(409, "Este vencimiento ya está pagado.")
            if Decimal(str(amount)) > Decimal(str(st["remaining"])) + Decimal("0.001"):
                raise HTTPException(422, f"El monto supera lo pendiente ({st['remaining']:.2f}). Confirma el sobrepago para continuar.")
        settles = data.settles if data.settles is not None else bool(rp.get("variable"))
        link = {"recurring_payment_id": rid, "recurring_record_id": pid}
        if data.mode == "expense":
            if not data.account_id:
                raise HTTPException(422, "Selecciona la cuenta de origen para registrar el gasto.")
            new_tx = Transaction(
                id=tid, user_id=DEFAULT_USER_ID, name=rp["name"], amount=amount, type="expense",
                date=when.isoformat(), category_id=cat_id, account_id=data.account_id, notes=notes,
            ).model_dump()
            new_tx.update(link)
            stored_movement = dict(new_tx, _id=tid)
            if getattr(settings, "history_keys_write_enabled", False):
                stored_movement = with_history_keys(stored_movement, settings.history_keys_generation)
            await db.transactions.insert_one(stored_movement, session=session)
            await recompute_account_balance(data.account_id, session=session)
            tx_id = tid
        elif data.mode == "link":
            await db.transactions.update_one({"id": tx["id"], "user_id": DEFAULT_USER_ID}, {"$set": link}, session=session)
            tx_id = tx["id"]
        else:
            tx_id = None
        record = {
            "id": pid, "user_id": DEFAULT_USER_ID, "recurring_id": rid, "due_date": due, "mode": data.mode,
            "amount": amount, "expected_amount": float(expected), "date": (tx["date"] if tx else when.isoformat()),
            "account_id": (tx.get("account_id") if tx else data.account_id) or None, "category_id": (tx.get("category_id") if tx else cat_id) or None,
            "notes": notes, "transaction_id": tx_id, "settles": bool(settles), "created_at": now_iso(),
        }
        stored = dict(record, _id=pid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await db.recurring_payment_records.insert_one(stored, session=session)
        return record

    return shared_public(await payment_transaction(operation))


@api.delete("/recurring-payments/payments/{pid}")
async def delete_recurring_record(
    pid: str,
    expected_environment: Optional[str] = Header(default=None, alias="MoneyFlow-Environment-ID", min_length=1, max_length=36),
    expected_user: Optional[str] = Header(default=None, alias="MoneyFlow-User-ID", min_length=1, max_length=128),
):
    if (expected_environment is None) != (expected_user is None):
        raise HTTPException(422, "Envía ambas cabeceras de contexto o ninguna.")
    async def operation(session):
        if expected_environment is not None:
            await verify_payment_context(db, settings.expected_financial_environment_id, DEFAULT_USER_ID,
                expected_environment, expected_user, session)
        rec = await db.recurring_payment_records.find_one({"id": pid, "user_id": DEFAULT_USER_ID}, session=session)
        shared = await dispatch_shared_change(db, globals().get("settings"), origin="recurring",
            receipt=rec, effective_user=DEFAULT_USER_ID, session=session,
            recompute_account_balance=recompute_account_balance)
        if shared is not None:
            return shared
        if rec:
            await guard_legacy_receipt(db, DEFAULT_USER_ID, rec, session)
        if not rec or rec.get("deleted"):
            return {"ok": True}
        await coordinate(db, DEFAULT_USER_ID, {"recurring_id": rec["recurring_id"]}, session)
        tx = await check_record(db, DEFAULT_USER_ID, rec, session)
        if rec.get("bill_payment_id"):
            payment = await db.bill_payments.find_one({"id": rec["bill_payment_id"]}, PROJ, session=session)
            await _bill_for_write(payment["bill_id"], session)
            await db.bill_payments.update_one({"id": payment["id"], "user_id": DEFAULT_USER_ID}, {"$set": {"recurring_record_id": None}}, session=session)
        if tx and rec["mode"] == "expense":
            if await db.recurring_templates.find_one({"source_transaction_id": tx["id"]}, PROJ, session=session):
                raise HTTPException(409, "El movimiento es origen de una plantilla recurrente.")
            await db.transactions.delete_one({"id": tx["id"], "user_id": DEFAULT_USER_ID}, session=session)
            if tx.get("account_id"):
                await recompute_account_balance(tx["account_id"], session=session)
        elif tx:
            await db.transactions.update_one({"id": tx["id"], "user_id": DEFAULT_USER_ID}, {"$unset": {"recurring_payment_id": "", "recurring_record_id": ""}}, session=session)
        await retire(db, "recurring_payment_records", rec, DEFAULT_USER_ID, session)
        return {"ok": True}
    return shared_public(await payment_transaction(operation))


# ---------- Bills (Facturas) ----------
# Each period is its own bill document linked to its series (series_id). Payments
# always create ONE real expense movement (atomic, idempotent) and update the
# account balance once. Fully paying a recurring bill creates the next period once
# (deterministic id -> no duplicates). An optional link to an existing recurring
# payment makes the SAME movement settle that recurring due (shared record).
BILL_FREQS = ("once", "weekly", "monthly", "quarterly", "yearly")
BILL_REMINDERS = (None, 1, 3, 7)


class BillIn(BaseModel):
    name: str
    provider: Optional[str] = None
    amount: float
    category_id: Optional[str] = None
    account_id: Optional[str] = None
    due_date: str
    frequency: Literal["once", "weekly", "monthly", "quarterly", "yearly"] = "once"
    reminder_days: Optional[int] = None
    description: Optional[str] = None
    recurring_payment_id: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class BillPayIn(BaseModel):
    amount: float
    account_id: str
    date: Optional[str] = None
    notes: Optional[str] = None


class PaymentReconciliation(BaseModel):
    version: Literal[1] = 1
    status: Literal["matched", "cancelled", "tracking_removed", "not_found", "discrepancy", "unverifiable"]
    financial_state: Literal["active", "annulled", "none", "unknown"]
    original_request_matches: Optional[bool]
    environment_id: str
    user_id: str
    origin: Literal["bill", "recurring"]
    parent_id: str
    original_due_date: Optional[str]
    receipt: Optional[dict]


async def _reconcile_payment(origin, parent_id, payload, key, expected_environment, expected_user):
    # This is a read-only snapshot, not the financial transaction runner. No
    # activation, coordination increments, provisioning or nested transaction.
    try:
        async with await client.start_session() as session:
            async with session.start_transaction(read_concern=ReadConcern("snapshot"), read_preference=ReadPreference.PRIMARY):
                await verify_payment_context(db, settings.expected_financial_environment_id, DEFAULT_USER_ID,
                                             expected_environment, expected_user, session)
                return await reconcile_payment_intent(db, origin=origin, parent_id=parent_id, key=key,
                    payload=payload, expected_environment_id=settings.expected_financial_environment_id,
                    effective_user=DEFAULT_USER_ID, session=session)
    except PyMongoError:
        raise HTTPException(503, "No se pudo verificar la intención. Conserva su clave y payload originales.") from None


@api.post("/bills/{bid}/payments/reconcile", response_model=PaymentReconciliation)
async def reconcile_bill_payment(
    bid: str, data: BillPayIn,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    expected_environment: str = Header(alias="MoneyFlow-Environment-ID", min_length=1, max_length=36),
    expected_user: str = Header(alias="MoneyFlow-User-ID", min_length=1, max_length=128),
):
    return await _reconcile_payment("bill", bid, data.model_dump(), idempotency_key, expected_environment, expected_user)


@api.post("/recurring-payments/{rid}/payments/reconcile", response_model=PaymentReconciliation)
async def reconcile_recurring_payment(
    rid: str, data: RecurringPayRecordCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    expected_environment: str = Header(alias="MoneyFlow-Environment-ID", min_length=1, max_length=36),
    expected_user: str = Header(alias="MoneyFlow-User-ID", min_length=1, max_length=128),
):
    return await _reconcile_payment("recurring", rid, data.model_dump(), idempotency_key, expected_environment, expected_user)


def _bill_add_period(d: date, freq: str, anchor_day: int) -> date:
    from backend.obligation_operations import _bill_add_period as project

    return project(d, freq, anchor_day)


def _bill_rp_due(rp, bill_due: str):
    from backend.obligation_operations import _bill_rp_due as project

    return project(rp, bill_due)


async def _bill_validate(data: BillIn, session=None, old=None, supplied=None, shared=False):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(422, "El nombre de la factura es obligatorio.")
    amount = _positive_money(data.amount, "El monto debe ser mayor que cero.")
    due = _rp_day(data.due_date, "La fecha de vencimiento no es válida.").isoformat()
    if data.reminder_days not in BILL_REMINDERS:
        raise HTTPException(422, "El recordatorio no es válido.")
    if data.category_id and (old is None or data.category_id != old.get("category_id")):
        cat = await db.categories.find_one({"id": data.category_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session)
        if not cat or cat.get("type") != "expense" or cat.get("is_group"):
            raise HTTPException(422, "La categoría debe ser una categoría de gasto existente.")
    if data.account_id and (old is None or data.account_id != old.get("account_id")) and not await db.accounts.find_one({"id": data.account_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
        raise HTTPException(422, "La cuenta seleccionada no existe.")
    if data.recurring_payment_id and (old is None or data.recurring_payment_id != old.get("recurring_payment_id")) and not await db.recurring_payments.find_one(
            {"id": data.recurring_payment_id, "user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1}, session=session):
        raise HTTPException(422, "El pago recurrente vinculado no existe.")
    fields = {
        "name": name[:60], "provider": ((data.provider or "").strip()[:60] or None), "amount": amount,
        "category_id": data.category_id or None, "account_id": data.account_id or None, "due_date": due,
        "frequency": data.frequency, "reminder_days": data.reminder_days,
        "description": ((data.description or "").strip()[:200] or None),
        "recurring_payment_id": data.recurring_payment_id or None,
        "icon": (data.icon or None), "color": (data.color or None),
    }
    if fields.get("recurring_payment_id") and not shared:
        await guard_legacy_recurring(db, DEFAULT_USER_ID, fields["recurring_payment_id"], session, due)
    preserve_references(fields, data, old, ("account_id", "category_id", "recurring_payment_id"), supplied)
    await coordinate(db, DEFAULT_USER_ID, fields, session, old)
    return fields


async def _bill_paid_map(bill_ids=None, session=None):
    q = {"user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}
    if bill_ids is not None:
        q["bill_id"] = {"$in": list(bill_ids)}
    out = {}
    async for p in read_database(db).bill_payments.find(q, {"_id": 0, "bill_id": 1, "amount": 1}, session=session):
        out[p["bill_id"]] = out.get(p["bill_id"], Decimal(0)) + Decimal(str(p["amount"]))
    return out


async def _bill_for_write(bid, session):
    await guard_legacy_bill(db, DEFAULT_USER_ID, bid, session)
    # Every payment/amount edit must write this shared document before reading
    # the paid total. A real increment (not a no-op) forces concurrent snapshots
    # to conflict and revalidate through the existing transaction runner.
    bill = await db.bills.find_one_and_update(
        {"id": bid, "user_id": DEFAULT_USER_ID},
        {"$inc": {"_payment_revision": 1}},
        projection=PROJ, return_document=ReturnDocument.AFTER, session=session,
    )
    if not bill:
        raise HTTPException(404, "Factura no encontrada.")
    return bill


def _bill_public(b, paid: Decimal, today: date, cats=None, accounts=None):
    from backend.obligation_operations import _bill_public as project

    return project(b, paid, today, cats, accounts)


async def _shared_bill_read(bill, paid, today, *, session, cats=None, accounts=None):
    """Prepared 2D.1 reader; no endpoint dispatches here while R4 is inactive."""
    view = await read_shared_view(db, bill_id=bill["id"], effective_user=DEFAULT_USER_ID,
                                  expected_environment_id=settings.expected_financial_environment_id,
                                  session=session)
    return shared_bill_public(_bill_public(bill, paid, today, cats, accounts), view, today)


async def _shared_recurring_read(rp, due, expected, records, today, *, session):
    """Prepared per-period projection for detail, overview and calendar readers."""
    view = await read_shared_view(db, recurring_id=rp["id"], original_due_date=due,
                                  effective_user=DEFAULT_USER_ID,
                                  expected_environment_id=settings.expected_financial_environment_id,
                                  session=session)
    return shared_recurring_public(_rp_state(rp, due, expected, records, today), view, today)


async def _bill_lookups():
    cats = {c["id"]: c for c in await read_database(db).categories.find({"user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1, "name": 1, "icon": 1, "color": 1}).to_list(5000)}
    accs = {a["id"]: a for a in await read_database(db).accounts.find({"user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)}
    return cats, accs


@api.get("/bills")
@_shared_reader
async def list_bills(status: str = "all", tz_offset: int = 0):
    if status not in ("all", "pending", "paid", "overdue"):
        raise HTTPException(422, "Filtro no válido.")
    today = _rp_today(tz_offset)
    bills = await read_database(db).bills.find({"user_id": DEFAULT_USER_ID}, PROJ).sort("due_date", 1).to_list(5000)
    paid = await _bill_paid_map([b["id"] for b in bills])
    cats, accs = await _bill_lookups()
    items = [_bill_public(b, paid.get(b["id"], Decimal(0)), today, cats, accs) for b in bills]
    counts = {"all": len(items)}
    for s in ("pending", "paid", "overdue"):
        counts[s] = sum(1 for i in items if i["status"] == s)
    if status != "all":
        items = [i for i in items if i["status"] == status]
    items.sort(key=lambda i: (i["due_date"], i["name"].lower()))
    return {"today": today.isoformat(), "items": items, "counts": counts}


@api.get("/bills/summary")
@_shared_reader
async def bills_summary(tz_offset: int = 0, year: Optional[int] = None, month: Optional[int] = None):
    today = _rp_today(tz_offset)
    year, month = year or today.year, month or today.month
    if not 1 <= month <= 12 or not 1900 <= year <= 3000:
        raise HTTPException(422, "Mes no válido.")
    tz = _local_tz(tz_offset)
    bills = await read_database(db).bills.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(5000)
    paid = await _bill_paid_map([b["id"] for b in bills])
    pend, pend_n, over, over_n, nxt = Decimal(0), 0, Decimal(0), 0, None
    for b in bills:
        pub = _bill_public(b, paid.get(b["id"], Decimal(0)), today)
        if pub["status"] == "paid":
            continue
        rem = Decimal(str(pub["remaining"]))
        pend += rem
        pend_n += 1
        if pub["status"] == "overdue":
            over += rem
            over_n += 1
        elif nxt is None or (b["due_date"], b["name"]) < (nxt["due_date"], nxt["name"]):
            nxt = {"id": b["id"], "name": b["name"], "due_date": b["due_date"], "remaining": float(rem)}
    a, z = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    lo, hi = _cal_str_window(a, z)
    pm, pm_n = Decimal(0), 0
    async for p in read_database(db).bill_payments.find({"user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}, "date": {"$gte": lo, "$lte": hi}}, {"_id": 0, "bill_id": 1, "amount": 1, "date": 1}):
        if current_shared_view(bill_id=p.get("bill_id")) is not None:
            continue
        d, _ = _cal_dt(p.get("date"), tz)
        if d and a <= d <= z:
            pm += Decimal(str(p["amount"]))
            pm_n += 1
    views = [current_shared_view(bill_id=b["id"]) for b in bills]
    for tx in shared_paid_events(views):
        d, _ = _cal_dt(tx.get("date"), tz)
        if d and a <= d <= z:
            pm += Decimal(str(tx["amount"]))
            pm_n += 1
    return {
        "today": today.isoformat(), "year": year, "month": month,
        "pending": {"amount": float(pend), "count": pend_n},
        "paid_month": {"amount": float(pm), "count": pm_n},
        "next_due": nxt,
        "overdue": {"amount": float(over), "count": over_n},
    }


@api.get("/bills/{bid}")
@_shared_reader
async def get_bill(bid: str, tz_offset: int = 0):
    b = await read_database(db).bills.find_one({"id": bid, "user_id": DEFAULT_USER_ID}, PROJ)
    if not b:
        raise HTTPException(404, "Factura no encontrada.")
    today = _rp_today(tz_offset)
    pays = await read_database(db).bill_payments.find({"bill_id": bid, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, {"_id": 0, "request_fingerprint": 0}).sort("date", -1).to_list(500)
    paid = sum((Decimal(str(p["amount"])) for p in pays), Decimal(0))
    cats, accs = await _bill_lookups()
    out = _bill_public(b, paid, today, cats, accs)
    for p in pays:
        p["account_name"] = (accs.get(p.get("account_id")) or {}).get("name")
    out["payments"] = pays
    rp = await read_database(db).recurring_payments.find_one({"id": b.get("recurring_payment_id"), "user_id": DEFAULT_USER_ID}, {"_id": 0, "id": 1, "name": 1}) if b.get("recurring_payment_id") else None
    out["recurring_payment_name"] = (rp or {}).get("name")
    return shared_public(out)


@api.post("/bills")
async def create_bill(data: BillIn, idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=128)):
    bid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEFAULT_USER_ID}:bill:{idempotency_key}")) if idempotency_key else new_id()
    try:
        fingerprint = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest() if idempotency_key else None
    except (ValueError, TypeError):
        raise HTTPException(422, "La solicitud original no es válida.") from None
    async def operation(session):
        await guard_legacy_bill(db, DEFAULT_USER_ID, bid, session)
        prev = await db.bills.find_one({"_id": bid}, session=session)
        if prev:
            if prev.get("user_id") != DEFAULT_USER_ID or prev.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La clave tiene otra solicitud o no conserva una huella original verificable.")
            return shared_public(prev)
        fields = await _bill_validate(data, session=session)
        now = now_iso()
        doc = {"id": bid, "user_id": DEFAULT_USER_ID, **fields, "series_id": bid,
               "anchor_day": int(fields["due_date"][8:10]), "next_bill_id": None, "created_at": now, "updated_at": now}
        if idempotency_key:
            doc["request_fingerprint"] = fingerprint
        await db.bills.insert_one(dict(doc, _id=bid), session=session)
        return doc
    return shared_public(await payment_transaction(operation))


@api.put("/bills/{bid}")
async def update_bill(bid: str, data: BillIn):
    async def operation(session):
        context = await shared_parent_context(db, globals().get("settings"), origin="bill", parent_id=bid,
            effective_user=DEFAULT_USER_ID, session=session)
        if context is not None:
            b = context[1][0][2]
            if "recurring_payment_id" in data.model_fields_set and data.recurring_payment_id != b.get("recurring_payment_id"):
                raise HTTPException(409, "La factura reservada no permite reasignar su recurrencia.")
            effective = data.model_copy(update={f: b.get(f) for f in ("account_id", "category_id", "recurring_payment_id", "frequency") if f not in data.model_fields_set})
            fields = await _bill_validate(effective, session, old=b, supplied=data.model_fields_set, shared=True)
            return await edit_shared_bill(db, context, fields, session=session, occurrences=_rp_occurrences, add_period=_bill_add_period)
        b = await _bill_for_write(bid, session)
        effective = data.model_copy(update={f: b.get(f) for f in ("account_id", "category_id", "recurring_payment_id") if f not in data.model_fields_set})
        fields = await _bill_validate(effective, session, old=b, supplied=data.model_fields_set)
        paid = (await _bill_paid_map([bid], session=session)).get(bid, Decimal(0))
        if Decimal(str(fields["amount"])) < paid - Decimal("0.001"):
            raise HTTPException(422, f"El monto no puede ser menor que lo ya pagado ({float(paid):.2f}).")
        upd = dict(fields, updated_at=now_iso())
        if fields["due_date"] != b["due_date"]:
            upd["anchor_day"] = int(fields["due_date"][8:10])
        await db.bills.update_one({"id": bid, "user_id": DEFAULT_USER_ID}, {"$set": upd}, session=session)
        return await db.bills.find_one({"id": bid}, {"_id": 0, "_payment_revision": 0, "_reference_revision": 0}, session=session)

    return shared_public(await payment_transaction(operation))


@api.delete("/bills/{bid}")
async def delete_bill(bid: str):
    async def operation(session):
        await guard_legacy_bill(db, DEFAULT_USER_ID, bid, session)
        if not await db.bills.find_one({"id": bid, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            return {"ok": True}
        await _bill_for_write(bid, session)
        payments = await db.bill_payments.find({"bill_id": bid, "user_id": DEFAULT_USER_ID, "deleted": {"$ne": True}}, session=session).to_list(None)
        ids = {p["id"] for p in payments}
        async for tx in db.transactions.find({"bill_id": bid, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            if tx.get("bill_payment_id") not in ids:
                raise HTTPException(409, "La factura tiene movimientos sin un pago verificable.")
        for payment in payments:
            await check_bill_payment(db, DEFAULT_USER_ID, payment, session)
            if payment.get("recurring_record_id"):
                await coordinate(db, DEFAULT_USER_ID, {"recurring_id": (await db.recurring_payment_records.find_one({"id": payment["recurring_record_id"]}, PROJ, session=session))["recurring_id"]}, session)
                await db.recurring_payment_records.update_one({"id": payment["recurring_record_id"], "user_id": DEFAULT_USER_ID}, {"$unset": {"bill_payment_id": ""}}, session=session)
            await retire(db, "bill_payments", payment, DEFAULT_USER_ID, session)
        # Keep actual expenses and any independent recurring tracking; no refund.
        await db.transactions.update_many({"bill_id": bid, "user_id": DEFAULT_USER_ID}, {"$unset": {"bill_id": "", "bill_payment_id": ""}}, session=session)
        await db.bills.update_many({"next_bill_id": bid, "user_id": DEFAULT_USER_ID}, {"$set": {"next_bill_id": None}}, session=session)
        await db.bills.delete_one({"id": bid, "user_id": DEFAULT_USER_ID}, session=session)
        return {"ok": True}
    return shared_public(await payment_transaction(operation))


@api.post("/bills/{bid}/payments")
async def pay_bill(bid: str, data: BillPayIn,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", min_length=1, max_length=128),
    expected_environment: Optional[str] = Header(default=None, alias="MoneyFlow-Environment-ID", min_length=1, max_length=36),
    expected_user: Optional[str] = Header(default=None, alias="MoneyFlow-User-ID", min_length=1, max_length=128),
):
    if (expected_environment is None) != (expected_user is None):
        raise HTTPException(422, "Envía ambas cabeceras de contexto o ninguna.")
    pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEFAULT_USER_ID}:bill-payment:{bid}:{idempotency_key}")) if idempotency_key else new_id()
    tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"bill-payment-movement:{pid}"))
    fingerprint = hashlib.sha256(json.dumps({"bid": bid, **data.model_dump()}, sort_keys=True, allow_nan=False).encode()).hexdigest()
    amount = _positive_money(data.amount, "El monto pagado debe ser mayor que cero.")
    when = _parse_dt(data.date) if data.date else datetime.now(timezone.utc)
    if when is None:
        raise HTTPException(422, "La fecha del pago no es válida.")
    notes = (data.notes or "").strip()[:200] or None
    today = _rp_today()

    async def operation(session):
        if expected_environment is not None:
            await verify_payment_context(db, settings.expected_financial_environment_id, DEFAULT_USER_ID,
                expected_environment, expected_user, session)
        shared = await dispatch_shared_payment(db, globals().get("settings"), origin="bill",
            parent_id=bid, receipt_id=pid, transaction_id=tid, payload=data.model_dump(),
            effective_user=DEFAULT_USER_ID, session=session, occurrences=_rp_occurrences,
            add_period=_bill_add_period, recompute_account_balance=recompute_account_balance,
            effective_date=when.isoformat())
        if shared is not None:
            return shared
        await guard_legacy_bill(db, DEFAULT_USER_ID, bid, session)
        prev = await db.bill_payments.find_one({"_id": pid, "user_id": DEFAULT_USER_ID}, session=session)
        if prev:
            if prev.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            if prev.get("deleted"):
                raise HTTPException(409, "La operación ya fue anulada; no se volverá a crear.")
            return {k: v for k, v in prev.items() if k not in ("_id", "request_fingerprint", "_reference_revision")}
        b = await _bill_for_write(bid, session)
        if not await db.accounts.find_one({"id": data.account_id, "user_id": DEFAULT_USER_ID}, PROJ, session=session):
            raise HTTPException(422, "La cuenta seleccionada no existe.")
        await coordinate(db, DEFAULT_USER_ID, {"account_id": data.account_id, "category_id": b.get("category_id")}, session)
        paid = (await _bill_paid_map([bid], session=session)).get(bid, Decimal(0))
        remaining = Decimal(str(b["amount"])) - paid
        if remaining <= Decimal("0.001"):
            raise HTTPException(409, "Esta factura ya está pagada.")
        if Decimal(str(amount)) > remaining + Decimal("0.001"):
            raise HTTPException(422, f"El monto supera lo pendiente ({float(remaining):.2f}).")
        tx = Transaction(
            id=tid, user_id=DEFAULT_USER_ID, name=b["name"], amount=amount, type="expense", date=when.isoformat(),
            category_id=b.get("category_id"), account_id=data.account_id, notes=notes,
        ).model_dump()
        tx.update(bill_id=bid, bill_payment_id=pid)
        # Optional shared record with a linked recurring payment (same movement, no second charge).
        rec_id = None
        rp = await db.recurring_payments.find_one({"id": b.get("recurring_payment_id"), "user_id": DEFAULT_USER_ID}, PROJ, session=session) if b.get("recurring_payment_id") else None
        # An unused missing legacy reference stays on the old bill. A new
        # shared record (or copied next period) still requires a valid parent.
        if rp:
            await coordinate(db, DEFAULT_USER_ID, {"recurring_payment_id": rp["id"]}, session)
        rp_due = _bill_rp_due(rp, b["due_date"]) if rp else None
        if rp_due:
            await guard_legacy_recurring(db, DEFAULT_USER_ID, rp["id"], session, rp_due)
        if rp and rp_due:
            d = date.fromisoformat(rp_due)
            recs = (await _rp_records(rid=rp["id"], a=d, b=d, session=session)).get((rp["id"], rp_due), [])
            st = _rp_state(rp, rp_due, _rp_occurrences(rp, d, d).get(rp_due), recs, today)
            if st["status"] != "paid":
                rec_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"bill-rp-record:{pid}"))
                await db.recurring_payment_records.insert_one({
                    "_id": rec_id, "id": rec_id, "user_id": DEFAULT_USER_ID, "recurring_id": rp["id"], "due_date": rp_due,
                    "mode": "link", "amount": amount, "expected_amount": st["expected"], "date": when.isoformat(),
                    "account_id": data.account_id, "category_id": b.get("category_id"), "notes": notes,
                    "transaction_id": tid, "settles": False, "created_at": now_iso(), "bill_payment_id": pid,
                }, session=session)
                tx.update(recurring_payment_id=rp["id"], recurring_record_id=rec_id)
        stored_movement = dict(tx, _id=tid)
        if getattr(settings, "history_keys_write_enabled", False):
            stored_movement = with_history_keys(stored_movement, settings.history_keys_generation)
        await db.transactions.insert_one(stored_movement, session=session)
        await recompute_account_balance(data.account_id, session=session)
        payment = {
            "id": pid, "user_id": DEFAULT_USER_ID, "bill_id": bid, "series_id": b.get("series_id") or bid,
            "amount": amount, "date": when.isoformat(), "account_id": data.account_id, "notes": notes,
            "transaction_id": tid, "recurring_record_id": rec_id, "created_at": now_iso(),
        }
        stored = dict(payment, _id=pid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await db.bill_payments.insert_one(stored, session=session)
        # Fully paid recurring bill -> next period, created once.
        next_id = None
        if b.get("frequency", "once") != "once" and paid + Decimal(str(amount)) >= Decimal(str(b["amount"])) - Decimal("0.001") and not b.get("next_bill_id"):
            nd = _bill_add_period(date.fromisoformat(b["due_date"]), b["frequency"], int(b.get("anchor_day") or b["due_date"][8:10])).isoformat()
            existing = await db.bills.find_one({"user_id": DEFAULT_USER_ID, "series_id": b.get("series_id") or bid, "due_date": nd}, PROJ, session=session)
            if existing:
                next_id = existing["id"]
            else:
                next_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"bill-next:{bid}"))
                if not await db.bills.find_one({"_id": next_id}, session=session):
                    now = now_iso()
                    keep = ("name", "provider", "amount", "category_id", "account_id", "frequency", "reminder_days",
                            "description", "recurring_payment_id", "icon", "color", "anchor_day")
                    await coordinate(db, DEFAULT_USER_ID, {k: b.get(k) for k in keep}, session)
                    await db.bills.insert_one(dict({k: b.get(k) for k in keep}, _id=next_id, id=next_id, user_id=DEFAULT_USER_ID,
                                                   series_id=b.get("series_id") or bid, due_date=nd, next_bill_id=None,
                                                   created_at=now, updated_at=now), session=session)
            await db.bills.update_one({"id": bid, "user_id": DEFAULT_USER_ID}, {"$set": {"next_bill_id": next_id}}, session=session)
        return dict(payment, next_bill_id=next_id)

    return shared_public(await payment_transaction(operation))


@api.delete("/bills/payments/{pid}")
async def delete_bill_payment(
    pid: str,
    expected_environment: Optional[str] = Header(default=None, alias="MoneyFlow-Environment-ID", min_length=1, max_length=36),
    expected_user: Optional[str] = Header(default=None, alias="MoneyFlow-User-ID", min_length=1, max_length=128),
):
    if (expected_environment is None) != (expected_user is None):
        raise HTTPException(422, "Envía ambas cabeceras de contexto o ninguna.")
    async def operation(session):
        if expected_environment is not None:
            await verify_payment_context(db, settings.expected_financial_environment_id, DEFAULT_USER_ID,
                expected_environment, expected_user, session)
        p = await db.bill_payments.find_one({"id": pid, "user_id": DEFAULT_USER_ID}, session=session)
        shared = await dispatch_shared_change(db, globals().get("settings"), origin="bill",
            receipt=p, effective_user=DEFAULT_USER_ID, session=session,
            recompute_account_balance=recompute_account_balance)
        if shared is not None:
            return shared
        if p:
            await guard_legacy_receipt(db, DEFAULT_USER_ID, p, session)
        if not p or p.get("deleted"):
            return {"ok": True}
        await _bill_for_write(p["bill_id"], session)
        tx = await check_bill_payment(db, DEFAULT_USER_ID, p, session)
        if await db.recurring_templates.find_one({"source_transaction_id": tx["id"]}, PROJ, session=session):
            raise HTTPException(409, "El movimiento es origen de una plantilla recurrente.")
        if p.get("recurring_record_id"):
            rec = await db.recurring_payment_records.find_one({"id": p["recurring_record_id"]}, session=session)
            await coordinate(db, DEFAULT_USER_ID, {"recurring_id": rec["recurring_id"]}, session)
            await retire(db, "recurring_payment_records", rec, DEFAULT_USER_ID, session)
        await db.transactions.delete_one({"id": tx["id"], "user_id": DEFAULT_USER_ID}, session=session)
        if tx.get("account_id"):
            await recompute_account_balance(tx["account_id"], session=session)
        await retire(db, "bill_payments", p, DEFAULT_USER_ID, session)
        # Keep a generated future period; series_id is a grouping key, not a FK.
        return {"ok": True}
    return shared_public(await payment_transaction(operation))


# ---------- Financial calendar (READ-ONLY aggregation layer) ----------
# Builds calendar events on demand from the existing collections (transactions,
# recurring payments + records, debts, saving goals + contributions). Nothing is
# copied, stored or generated: every event keeps a reference to its source record.
# Integrity rules:
# * realized=True  -> money that really moved (registered movements).
# * realized=False -> planned/expected obligations (never touch balances or totals
#   of real money). Pending recurring dues show only their REMAINING amount, and a
#   due already paid through a movement is represented by that movement (no double count).
# * Transfers and goal tracking contributions are never income nor expense.
# * "bill" (Facturas) has no data source yet -> always empty, never invented.
CAL_KINDS = ("income", "expense", "recurring", "bill", "debt", "goal", "other")
CAL_MAX_DAYS = 400


def _cal_types(types: Optional[str]):
    if not types:
        return set(CAL_KINDS)
    sel = {t.strip() for t in types.split(",") if t.strip()}
    bad = sel - set(CAL_KINDS)
    if bad:
        raise HTTPException(422, "Tipo de evento no válido.")
    return sel


def _cal_dt(value, tz):
    """(local_date, 'HH:MM' | None). Date-only values have no time (all-day)."""
    s = str(value or "")
    if len(s) <= 10:
        try:
            return date.fromisoformat(s[:10]), None
        except ValueError:
            return None, None
    dt = _parse_dt(s)
    if not dt:
        return None, None
    loc = dt.astimezone(tz)
    return loc.date(), loc.strftime("%H:%M")


def _cal_str_window(a: date, b: date):
    # Stored dates are ISO strings; widen by 2 days so any UTC offset is covered,
    # then the exact local-date filter is applied in Python.
    return (a - timedelta(days=2)).isoformat(), (b + timedelta(days=2)).isoformat() + "\uffff"


async def _cal_events(a: date, b: date, tz, today: date):
    from backend.planning_operations import PlanningOperations

    return await PlanningOperations(db, DEFAULT_USER_ID)._cal_events(a, b, tz, today)


def _cal_summary(events, a: date, b: date):
    from backend.planning_operations import _cal_summary as calculate

    return calculate(events, a, b)


@api.get("/calendar/events")
@_shared_reader
async def calendar_events(start: str, end: str, tz_offset: int = 0, types: Optional[str] = None):
    a = _rp_day(start, "La fecha inicial no es válida.")
    b = _rp_day(end, "La fecha final no es válida.")
    if b < a:
        raise HTTPException(422, "La fecha final debe ser posterior a la inicial.")
    if (b - a).days > CAL_MAX_DAYS:
        raise HTTPException(422, "El intervalo es demasiado amplio.")
    sel = _cal_types(types)
    today = _rp_today(tz_offset)
    events = [e for e in await _cal_events(a, b, _local_tz(tz_offset), today) if e["kind"] in sel]
    return {"start": a.isoformat(), "end": b.isoformat(), "today": today.isoformat(), "events": events}


@api.get("/calendar/summary")
@_shared_reader
async def calendar_summary(year: Optional[int] = None, month: Optional[int] = None, tz_offset: int = 0, types: Optional[str] = None):
    today = _rp_today(tz_offset)
    year, month = year or today.year, month or today.month
    if not 1 <= month <= 12 or not 1900 <= year <= 3000:
        raise HTTPException(422, "Mes no válido.")
    sel = _cal_types(types)
    a, b = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    events = [e for e in await _cal_events(a, b, _local_tz(tz_offset), today) if e["kind"] in sel]
    out = {"year": year, "month": month, "today": today.isoformat(), **_cal_summary(events, a, b)}
    # Bills due this month (full amount, paid or not). A separate concept from
    # "payments": never added to real spending totals.
    if "bill" in sel:
        s, n = Decimal(0), 0
        async for bl in read_database(db).bills.find({"user_id": DEFAULT_USER_ID, "due_date": {"$gte": a.isoformat(), "$lte": b.isoformat()}}, {"_id": 0, "amount": 1}):
            s += Decimal(str(bl["amount"]))
            n += 1
        out["bills"] = {"amount": float(s), "count": n, "available": True}
    return out


@api.get("/calendar/upcoming")
@_shared_reader
async def calendar_upcoming(tz_offset: int = 0, limit: int = 5, offset: int = 0, days: int = 120, types: Optional[str] = None):
    today = _rp_today(tz_offset)
    limit, offset, days = max(1, min(int(limit), 50)), max(0, int(offset)), max(1, min(int(days), 365))
    sel = _cal_types(types)
    a, b = today - timedelta(days=CAL_MAX_DAYS - days), today + timedelta(days=days)
    events = await _cal_events(a, b, _local_tz(tz_offset), today)
    # Only active commitments: pending/overdue dues and open goal targets. Cancelled
    # (ended) or paused recurrences produce no dues, paid items are excluded.
    items = [
        {**e, "days_left": (date.fromisoformat(e["date"]) - today).days}
        for e in events
        if e["kind"] in sel and not e["realized"] and e["status"] in ("pending", "overdue", "target")
        and (e["status"] == "overdue" or e["date"] >= today.isoformat())
    ]
    items.sort(key=lambda e: (e["date"], e["title"].lower()))
    page = items[offset:offset + limit]
    return {"today": today.isoformat(), "items": page, "total": len(items), "offset": offset, "limit": limit,
            "has_more": offset + len(page) < len(items)}


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
        await db.recurring_payments.create_index([("user_id", 1), ("created_at", -1)])
        await db.recurring_payment_records.create_index([("user_id", 1), ("recurring_id", 1), ("due_date", -1)])
        await db.recurring_payment_records.create_index([("user_id", 1), ("due_date", 1)])
        # Calendar range queries (non-destructive, additive indexes).
        await db.transactions.create_index([("user_id", 1), ("date", 1)])
        await db.goal_contributions.create_index([("user_id", 1), ("date", 1)])
        await db.bills.create_index([("user_id", 1), ("due_date", 1)])
        await db.bills.create_index([("user_id", 1), ("series_id", 1), ("due_date", 1)])
        await db.bill_payments.create_index([("user_id", 1), ("bill_id", 1)])
        await db.bill_payments.create_index([("user_id", 1), ("date", 1)])
    except PyMongoError:
        logger.warning("Could not ensure saving-goal indexes")


@app.on_event("shutdown")
async def shutdown():
    client.close()
