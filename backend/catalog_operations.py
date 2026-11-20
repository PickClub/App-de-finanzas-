"""Owner-scoped category catalog and recurring template operations."""
from typing import Literal, Optional
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.obligation_operations import new_id, now_iso
from backend.reference_integrity import coordinate, public


class Category(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
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


class RecurringTemplate(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
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


class UserUpdate(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None
    profile_photo: Optional[str] = None


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


NEW_SUBCATEGORIES = [
    ("Electronics", "expense", "hardware-chip-outline", "#5C7CFA"),
    ("Home", "expense", "bed-outline", "#C08457"),
    ("Beauty", "expense", "rose-outline", "#EC5F94"),
]


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


def catalog_id(owner, kind, name, role):
    return str(uuid5(NAMESPACE_URL, f"moneyflow:catalog:{owner}:{kind}:{role}:{name}"))


async def validate_category_parent(db, owner, category_id, parent_id, session):
    seen = {category_id}
    while parent_id:
        if parent_id in seen or len(seen) > 100:
            raise HTTPException(409, "Invalid category hierarchy")
        seen.add(parent_id)
        parent = await db.categories.find_one(
            {"id": parent_id, "user_id": owner}, {"_id": 0, "parent_id": 1}, session=session
        )
        if parent is None:
            raise HTTPException(404, "Not found")
        parent_id = parent.get("parent_id")


async def initialize_categories(db, owner, session):
    """Materialize only the static catalog; use deterministic IDs for concurrent retries."""
    async def ensure_leaf(name, typ, icon, color):
        existing = await db.categories.find_one({"user_id": owner, "name": name, "type": typ, "is_group": {"$ne": True}}, {"_id": 0}, session=session)
        if existing:
            return existing, 0
        c = Category(id=catalog_id(owner, typ, name, "leaf"), user_id=owner, name=name, type=typ, icon=icon, color=color).model_dump()
        await db.categories.insert_one(dict(c, _id=c["id"]), session=session)
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
                {"user_id": owner, "name": gname, "type": typ, "is_group": True}, {"_id": 0}, session=session)
            if not g:
                g = Category(id=catalog_id(owner, typ, gname, "group"), user_id=owner, name=gname, type=typ, icon=gicon,
                             color=gcolor, is_group=True).model_dump()
                await db.categories.insert_one(dict(g, _id=g["id"]), session=session)
                g = {k: v for k, v in g.items() if k != "_id"}
                groups_created += 1
            gid = g["id"]
            for child_name in children:
                child = await db.categories.find_one(
                    {"user_id": owner, "name": child_name, "type": typ, "is_group": {"$ne": True}}, {"_id": 0}, session=session)
                if child and child.get("parent_id") != gid:
                    await validate_category_parent(db, owner, child["id"], gid, session)
                    await coordinate(db, owner, {"parent_id": gid}, session)
                    await db.categories.update_one({"id": child["id"], "user_id": owner}, {"$set": {"parent_id": gid}}, session=session)
                    links += 1

    total = await db.categories.count_documents({"user_id": owner}, session=session)
    return {"ok": True, "created": created, "groups_created": groups_created, "links": links, "total": total}

async def delete_owned_category(db, owner, cid, session):
    scope = {"user_id": owner}
    for name in ("transactions", "budgets", "debts", "recurring_templates", "bills",
                 "recurring_payments", "recurring_payment_records"):
        query = {**scope, "category_id": cid}
        if name == "recurring_payment_records":
            query["deleted"] = {"$ne": True}
        if await getattr(db, name).find_one(query, {"_id": 0}, session=session):
            raise HTTPException(409, "Category is still referenced")
    if await db.categories.find_one({**scope, "parent_id": cid}, {"_id": 0}, session=session):
        raise HTTPException(409, "Category has linked children")
    await db.categories.delete_one({**scope, "id": cid}, session=session)
    return {"ok": True}


async def create_template(db, owner, data, session):
    payload = data.model_dump()
    if not payload.get("start_date"):
        payload.pop("start_date", None)
    record = RecurringTemplate(user_id=owner, **payload).model_dump()
    await coordinate(db, owner, payload, session)
    await db.recurring_templates.insert_one(dict(record, _id=record["id"]), session=session)
    return public(record)
