from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os, logging, uuid
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

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


class DebtPaymentCreate(BaseModel):
    debt_id: str
    amount: float
    date: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None


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


async def recompute_account_balance(account_id: str):
    """Recompute an account's current balance from its initial + transactions."""
    acc = await db.accounts.find_one({"id": account_id}, PROJ)
    if not acc:
        return
    balance = acc["initial_balance"]
    async for tx in db.transactions.find({"user_id": DEFAULT_USER_ID}, PROJ):
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
    await db.accounts.update_one({"id": account_id}, {"$set": {"current_balance": round(balance, 2)}})


async def recompute_debt(debt_id: str):
    d = await db.debts.find_one({"id": debt_id}, PROJ)
    if not d:
        return
    total_paid = 0.0
    async for p in db.debt_payments.find({"debt_id": debt_id}, PROJ):
        total_paid += p["amount"]
    remaining = max(0.0, d["original_amount"] - total_paid)
    status = "paid" if remaining <= 0.0001 else "active"
    await db.debts.update_one(
        {"id": debt_id},
        {"$set": {"total_paid": round(total_paid, 2), "remaining_amount": round(remaining, 2), "status": status}},
    )


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
    await db.accounts.delete_one({"id": account_id})
    return {"ok": True}


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


# Transactions
@api.get("/transactions")
async def list_transactions(limit: int = 500):
    return await db.transactions.find({"user_id": DEFAULT_USER_ID}, PROJ).sort("date", -1).to_list(limit)


@api.post("/transactions")
async def create_transaction(data: TransactionCreate):
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
    await db.debts.update_one({"id": did}, {"$set": data.model_dump()})
    await recompute_debt(did)
    return await db.debts.find_one({"id": did}, PROJ)


@api.delete("/debts/{did}")
async def delete_debt(did: str):
    await db.debts.delete_one({"id": did})
    await db.debt_payments.delete_many({"debt_id": did})
    return {"ok": True}


# Debt Payments
@api.get("/debts/{did}/payments")
async def list_debt_payments(did: str):
    return await db.debt_payments.find({"debt_id": did}, PROJ).sort("date", -1).to_list(500)


@api.post("/debt-payments")
async def create_debt_payment(data: DebtPaymentCreate):
    debt = await db.debts.find_one({"id": data.debt_id}, PROJ)
    if not debt:
        raise HTTPException(404, "Debt not found")
    payload = data.model_dump()
    if not payload.get("date"):
        payload["date"] = now_iso()
    p = DebtPayment(user_id=DEFAULT_USER_ID, **payload).model_dump()
    await db.debt_payments.insert_one(p)

    # Create a transaction entry
    if debt["direction"] == "i_owe":
        tx_type = "debt_payment"
    else:
        tx_type = "income"
    tx = Transaction(
        user_id=DEFAULT_USER_ID,
        name=f"Pago: {debt['name']}",
        amount=payload["amount"],
        type=tx_type,
        date=payload["date"],
        account_id=payload.get("account_id"),
        debt_id=data.debt_id,
        notes=payload.get("notes"),
    ).model_dump()
    await db.transactions.insert_one(tx)
    if payload.get("account_id"):
        await recompute_account_balance(payload["account_id"])
    await recompute_debt(data.debt_id)
    return {k: v for k, v in p.items() if k != "_id"}


@api.delete("/debt-payments/{pid}")
async def delete_debt_payment(pid: str):
    p = await db.debt_payments.find_one({"id": pid}, PROJ)
    if p:
        await db.debt_payments.delete_one({"id": pid})
        await recompute_debt(p["debt_id"])
        if p.get("account_id"):
            await recompute_account_balance(p["account_id"])
    return {"ok": True}


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
    async for p in db.debt_payments.find({"user_id": DEFAULT_USER_ID}, PROJ):
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


# Seed demo
@api.post("/seed")
async def seed():
    await ensure_user()
    # Clean
    await db.accounts.delete_many({"user_id": DEFAULT_USER_ID})
    await db.categories.delete_many({"user_id": DEFAULT_USER_ID})
    await db.transactions.delete_many({"user_id": DEFAULT_USER_ID})
    await db.debts.delete_many({"user_id": DEFAULT_USER_ID})
    await db.debt_payments.delete_many({"user_id": DEFAULT_USER_ID})
    await db.budgets.delete_many({"user_id": DEFAULT_USER_ID})
    await db.saving_goals.delete_many({"user_id": DEFAULT_USER_ID})

    accounts_data = [
        {"name": "Chase Checking", "type": "checking", "initial_balance": 2450, "color": "#4C83EA", "icon": "card-outline"},
        {"name": "Efectivo", "type": "cash", "initial_balance": 350, "color": "#2FA47C", "icon": "cash-outline"},
        {"name": "Ahorros", "type": "savings", "initial_balance": 8000, "color": "#29C4A9", "icon": "wallet-outline"},
    ]
    accounts = []
    for a in accounts_data:
        acc = Account(user_id=DEFAULT_USER_ID, current_balance=a["initial_balance"], **a).model_dump()
        await db.accounts.insert_one(acc)
        accounts.append(acc)

    cats_data = [
        ("Comida", "expense", "restaurant-outline", "#FF8A3D"),
        ("Supermercado", "expense", "cart-outline", "#F5B83B"),
        ("Restaurantes", "expense", "pizza-outline", "#FF654A"),
        ("Transporte", "expense", "car-outline", "#4C83EA"),
        ("Gasolina", "expense", "flame-outline", "#D95345"),
        ("Casa", "expense", "home-outline", "#8F5BE8"),
        ("Servicios", "expense", "flash-outline", "#F5B83B"),
        ("Teléfono", "expense", "call-outline", "#29C4A9"),
        ("Internet", "expense", "wifi-outline", "#4C83EA"),
        ("Entretenimiento", "expense", "musical-notes-outline", "#8F5BE8"),
        ("Compras", "expense", "bag-outline", "#FF8A3D"),
        ("Salud", "expense", "medkit-outline", "#D95345"),
        ("Trabajo", "expense", "briefcase-outline", "#27221F"),
        ("Educación", "expense", "school-outline", "#4C83EA"),
        ("Viajes", "expense", "airplane-outline", "#29C4A9"),
        ("Salario", "income", "cash-outline", "#2FA47C"),
        ("Propinas", "income", "star-outline", "#F5B83B"),
        ("Otros", "expense", "ellipsis-horizontal-outline", "#8E8883"),
    ]
    cats = []
    for name, typ, icon, color in cats_data:
        c = Category(user_id=DEFAULT_USER_ID, name=name, type=typ, icon=icon, color=color).model_dump()
        await db.categories.insert_one(c)
        cats.append(c)

    cat_by = {c["name"]: c["id"] for c in cats}

    txs = [
        ("Salario", 600, "income", cat_by["Salario"], accounts[0]["id"]),
        ("Supermercado semanal", 82.50, "expense", cat_by["Supermercado"], accounts[0]["id"]),
        ("Café", 4.50, "expense", cat_by["Restaurantes"], accounts[1]["id"]),
        ("Gasolina", 45.00, "expense", cat_by["Gasolina"], accounts[0]["id"]),
        ("Netflix", 15.99, "expense", cat_by["Entretenimiento"], accounts[0]["id"]),
    ]
    for name, amt, typ, cid, aid in txs:
        tx = Transaction(
            user_id=DEFAULT_USER_ID, name=name, amount=amt, type=typ,
            category_id=cid, account_id=aid,
        ).model_dump()
        await db.transactions.insert_one(tx)

    # Debts
    debts_data = [
        {"name": "Tarjeta Chase", "direction": "i_owe", "person": "Chase Bank",
         "original_amount": 2500, "minimum_payment": 200, "due_date": "2026-06-15T00:00:00+00:00",
         "color": "#D95345", "icon": "card-outline"},
        {"name": "Préstamo automóvil", "direction": "i_owe", "person": "Toyota Financial",
         "original_amount": 12000, "minimum_payment": 350, "due_date": "2026-06-25T00:00:00+00:00",
         "color": "#8F5BE8", "icon": "car-outline"},
        {"name": "Carlos me debe", "direction": "they_owe", "person": "Carlos",
         "original_amount": 1000, "minimum_payment": 100, "due_date": "2026-07-10T00:00:00+00:00",
         "color": "#F5B83B", "icon": "person-outline"},
    ]
    for d in debts_data:
        debt = Debt(user_id=DEFAULT_USER_ID, remaining_amount=d["original_amount"], **d).model_dump()
        await db.debts.insert_one(debt)

    # Sample payments
    all_debts = await db.debts.find({"user_id": DEFAULT_USER_ID}, PROJ).to_list(10)
    chase = next(x for x in all_debts if x["name"] == "Tarjeta Chase")
    p = DebtPayment(debt_id=chase["id"], amount=700, account_id=accounts[0]["id"]).model_dump()
    await db.debt_payments.insert_one(p)
    car = next(x for x in all_debts if x["name"] == "Préstamo automóvil")
    p2 = DebtPayment(debt_id=car["id"], amount=3600, account_id=accounts[0]["id"]).model_dump()
    await db.debt_payments.insert_one(p2)
    carlos = next(x for x in all_debts if x["name"] == "Carlos me debe")
    p3 = DebtPayment(debt_id=carlos["id"], amount=300, account_id=accounts[1]["id"]).model_dump()
    await db.debt_payments.insert_one(p3)

    for d in all_debts:
        await recompute_debt(d["id"])

    # Budgets
    budgets_data = [
        {"name": "Restaurantes", "amount_limit": 400, "period": "monthly", "category_id": cat_by["Restaurantes"]},
        {"name": "Supermercado", "amount_limit": 500, "period": "monthly", "category_id": cat_by["Supermercado"]},
        {"name": "Entretenimiento", "amount_limit": 150, "period": "monthly", "category_id": cat_by["Entretenimiento"]},
    ]
    for b in budgets_data:
        bud = Budget(user_id=DEFAULT_USER_ID, start_date=now_iso(), **b).model_dump()
        await db.budgets.insert_one(bud)

    # Goals
    goals_data = [
        {"name": "PC nueva", "target_amount": 3000, "current_amount": 1500, "priority": "medium", "color": "#4C83EA", "icon": "desktop-outline"},
        {"name": "Viaje", "target_amount": 2000, "current_amount": 900, "priority": "medium", "color": "#29C4A9", "icon": "airplane-outline"},
        {"name": "Fondo de emergencia", "target_amount": 10000, "current_amount": 4000, "priority": "high", "color": "#FF654A", "icon": "shield-checkmark-outline"},
    ]
    for g in goals_data:
        goal = SavingGoal(user_id=DEFAULT_USER_ID, **g).model_dump()
        await db.saving_goals.insert_one(goal)

    for a in accounts:
        await recompute_account_balance(a["id"])

    return {"ok": True, "seeded": True}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown():
    client.close()
