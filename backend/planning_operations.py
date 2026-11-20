"""Owner-scoped planning operations for the detached API."""
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import hashlib
import json
import math
import re
from typing import Literal, Optional
import uuid

from backend.movement_operations import versioned_movement_update
from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.history_keys import with_history_keys
from backend.obligation_operations import (
    CENT, ObligationOperations, Transaction, _bill_public, _bill_rp_due,
    _cal_dt, _cal_str_window, _local_tz, _parse_dt, _positive_money, _rp_day,
    _rp_month_states, _rp_today, new_id, now_iso,
)
from backend.reference_integrity import (
    check_goal_contribution, coordinate, preserve_references, public as reference_public, retire,
)
from backend.shared_obligations import (
    current_shared_view, public_financial_document as shared_public, read_database,
)

PROJ = {"_id": 0}
BUDGET_PERIODS = ("weekly", "monthly", "custom")
CAL_KINDS = ("income", "expense", "recurring", "bill", "debt", "goal", "other")
CAL_MAX_DAYS = 400
GOAL_HIDDEN = {"_id", "request_fingerprint", "_reference_revision"}


def _day_start(d, tz):
    d = d.astimezone(tz)
    return datetime(d.year, d.month, d.day, tzinfo=tz)


class Budget(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
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
    user_id: str
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


def _dec(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _month_bounds(year: int, month: int, tz):
    start = datetime(year, month, 1, tzinfo=tz)
    end = datetime(year + (month == 12), (month % 12) + 1, 1, tzinfo=tz)
    return start, end


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


def _overlaps(a_start, a_end, b_start, b_end):
    inf = datetime.max.replace(tzinfo=timezone.utc)
    return (a_start or datetime.min.replace(tzinfo=timezone.utc)) < (b_end or inf) and \
        (b_start or datetime.min.replace(tzinfo=timezone.utc)) < (a_end or inf)


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


def _public(row, with_tx=False):
    out = {k: v for k, v in row.items() if not k.startswith("_")}
    if with_tx:
        out["transactions"] = sorted(
            ({k: v for k, v in t.items() if k != "_dt"} for t in row["_matched"]),
            key=lambda t: t.get("date") or "", reverse=True,
        )
    return shared_public(out)


def _goal_clean(doc):
    return {k: v for k, v in doc.items() if k not in GOAL_HIDDEN}


def _goal_target_date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        raise HTTPException(422, "La fecha objetivo no es válida.")


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


def _cal_types(types: Optional[str]):
    if not types:
        return set(CAL_KINDS)
    sel = {t.strip() for t in types.split(",") if t.strip()}
    bad = sel - set(CAL_KINDS)
    if bad:
        raise HTTPException(422, "Tipo de evento no válido.")
    return sel


def _cal_summary(events, a: date, b: date):
    def acc(pred):
        s, n = Decimal(0), 0
        for e in events:
            if a.isoformat() <= e["date"] <= b.isoformat() and pred(e):
                s += Decimal(str(e["amount"]))
                n += 1
        return {"amount": float(s), "count": n}

    income = acc(lambda e: e["realized"] and e["source"] == "transaction" and e["flow"] == "income")
    payments = acc(lambda e: e["realized"] and e["source"] == "transaction" and e["flow"] in ("expense", "debt_payment"))
    planned_exp = acc(lambda e: not e["realized"] and e["flow"] == "planned_expense" and e["status"] in ("pending", "overdue"))
    planned_inc = acc(lambda e: not e["realized"] and e["flow"] == "planned_income" and e["status"] in ("pending", "overdue"))
    net = sum((Decimal(str(e["amount"])) * e["sign"] for e in events if e["counts_in_net"]
               and a.isoformat() <= e["date"] <= b.isoformat()), Decimal(0))
    return {
        "income": income, "payments": payments,
        "bills": {"amount": 0.0, "count": 0, "available": False},
        "planned_expenses": planned_exp, "planned_income": planned_inc, "net_real": float(net),
    }


class PlanningOperations:
    def __init__(self, database, owner, settings=None):
        self.db = database
        self.owner = owner
        self.settings = settings
        self.obligations = ObligationOperations(database, owner, settings)

    async def delete_budget(self, bid, *, session):
        await self.db.budgets.delete_one({"id": bid, "user_id": self.owner}, session=session)
        return {"ok": True}

    async def _compute_budgets(self, year: int, month: int, tz_offset: int, only_id: Optional[str] = None, *, now=None):
        tz = _local_tz(tz_offset)
        m_start, m_end = _month_bounds(year, month, tz)
        now = now or datetime.now(timezone.utc)
        q = {"user_id": self.owner}
        if only_id:
            q["id"] = only_id
        budgets = await self.db.budgets.find(q, {"_id": 0, "idempotency_key": 0, "request_fingerprint": 0}).to_list(1000)
        cats = await self.db.categories.find({"user_id": self.owner}, PROJ).to_list(2000)
        cats_by_id = {c["id"]: c for c in cats}
        txs = await self.db.transactions.find({"user_id": self.owner, "type": "expense"}, PROJ).to_list(20000)
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

    async def _validate_budget(self, data: BudgetCreate, replacing: Optional[str] = None, session=None, old=None) -> dict:
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
        cat = await self.db.categories.find_one({"id": payload["category_id"], "user_id": self.owner}, PROJ, session=session)
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
        q = {"user_id": self.owner, "category_id": payload["category_id"], "period": payload["period"]}
        if replacing:
            q["id"] = {"$ne": replacing}
        await coordinate(self.db, self.owner, payload, session, old)
        async for other in self.db.budgets.find(q, PROJ, session=session):
            if _overlaps(start, end, _parse_dt(other.get("start_date")), _parse_dt(other.get("end_date"))):
                raise HTTPException(409, "Ya existe un presupuesto para esta categoría y período en esas fechas.")
        return payload

    async def list_budgets(self):
        return await self.db.budgets.find({"user_id": self.owner}, {"_id": 0, "idempotency_key": 0, "request_fingerprint": 0}).sort("created_at", -1).to_list(500)

    async def budgets_overview(self, year: Optional[int] = None, month: Optional[int] = None, tz_offset: int = 0):
        now = datetime.now(_local_tz(tz_offset))
        year = year or now.year
        month = month or now.month
        if not (1 <= month <= 12) or not (1970 <= year <= 9999):
            raise HTTPException(422, "Mes o año inválido.")
        rows, cats_by_id, (m_start, m_end) = await self._compute_budgets(year, month, tz_offset)
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

    async def budget_detail(self, bid: str, year: Optional[int] = None, month: Optional[int] = None, tz_offset: int = 0):
        now = datetime.now(_local_tz(tz_offset))
        rows, cats_by_id, _ = await self._compute_budgets(year or now.year, month or now.month, tz_offset, only_id=bid)
        if not rows:
            raise HTTPException(404, "Presupuesto no encontrado.")
        out = _public(rows[0], with_tx=True)
        out["category"] = cats_by_id.get(rows[0].get("category_id"))
        return out

    async def recompute_goal(self, gid, session=None):
        g = await self.db.saving_goals.find_one({"id": gid, "user_id": self.owner}, PROJ, session=session)
        if not g:
            return None
        # Legacy goals (before contributions existed) stored the saved amount in current_amount.
        initial = Decimal(str(g["initial_amount"] if g.get("initial_amount") is not None else g.get("current_amount") or 0))
        total = initial
        pipeline = [
            {"$match": {"user_id": self.owner, "goal_id": gid, "deleted": {"$ne": True}}},
            {"$group": {"_id": "$kind", "s": {"$sum": {"$toDecimal": "$amount"}}}},
        ]
        async for row in self.db.goal_contributions.aggregate(pipeline, session=session):
            s = row["s"].to_decimal()
            total += s if row["_id"] == "deposit" else -s
        total = max(Decimal(0), total).quantize(CENT, rounding=ROUND_HALF_UP)
        completed = g["target_amount"] > 0 and total >= Decimal(str(g["target_amount"]))
        upd = {"current_amount": float(total), "initial_amount": float(initial)}
        if completed and not g.get("completed_at"):
            upd["completed_at"] = now_iso()
        elif not completed and g.get("completed_at"):
            upd["completed_at"] = None
        await self.db.saving_goals.update_one({"id": gid, "user_id": self.owner}, {"$set": upd}, session=session)
        g.update(upd)
        return g

    async def _validate_goal(self, data: SavingGoalCreate, replacing=None, session=None, old=None, supplied=None):
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
        if data.account_id and (old is None or data.account_id != old.get("account_id")) and not await self.db.accounts.find_one({"id": data.account_id, "user_id": self.owner}, PROJ, session=session):
            raise HTTPException(422, "La cuenta asociada no existe.")
        q = {"user_id": self.owner, "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}
        if replacing:
            q["id"] = {"$ne": replacing}
        if await self.db.saving_goals.find_one(q, PROJ, session=session):
            raise HTTPException(409, "Ya existe una meta con ese nombre.")
        fields = {
            "name": name, "target_amount": target, "target_date": _goal_target_date(data.target_date),
            "priority": data.priority, "color": data.color or "#29C4A9", "icon": data.icon or "flag-outline",
            "account_id": data.account_id or None,
        }
        preserve_references(fields, data, old, ("account_id",), supplied)
        await coordinate(self.db, self.owner, fields, session, old)
        return fields, initial

    async def _contributions_page(self, gid, limit, offset, session=None):
        limit = max(1, min(int(limit or 20), 100))
        offset = max(0, int(offset or 0))
        q = {"user_id": self.owner, "goal_id": gid, "deleted": {"$ne": True}}
        items = await self.db.goal_contributions.find(q, {"_id": 0, "request_fingerprint": 0}, session=session) \
            .sort([("date", -1), ("created_at", -1)]).skip(offset).limit(limit).to_list(limit)
        total = await self.db.goal_contributions.count_documents(q, session=session)
        return {"items": items, "total": total, "offset": offset, "limit": limit, "has_more": offset + len(items) < total}

    async def list_goals(self):
        goals = await self.db.saving_goals.find({"user_id": self.owner}, PROJ).sort("created_at", -1).to_list(500)
        today = datetime.now(timezone.utc).date()
        return [_goal_public(g, today) for g in goals]

    async def goals_overview(self):
        goals = await self.db.saving_goals.find({"user_id": self.owner}, PROJ).sort("created_at", -1).to_list(500)
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

    async def get_goal(self, gid: str, limit: int = 20):
        g = await self.db.saving_goals.find_one({"id": gid, "user_id": self.owner}, PROJ)
        if not g:
            raise HTTPException(404, "Meta no encontrada.")
        out = _goal_public(g)
        acc = await self.db.accounts.find_one({"id": g["account_id"], "user_id": self.owner}, {"_id": 0, "id": 1, "name": 1, "color": 1}) if g.get("account_id") else None
        out["account"] = acc
        out["contributions"] = await self._contributions_page(gid, limit, 0)
        return out

    async def list_goal_contributions(self, gid: str, limit: int = 20, offset: int = 0):
        if not await self.db.saving_goals.find_one({"id": gid, "user_id": self.owner}, {"_id": 0, "id": 1}):
            raise HTTPException(404, "Meta no encontrada.")
        return await self._contributions_page(gid, limit, offset)

    async def _cal_events(self, a: date, b: date, tz, today: date):
        U = self.owner
        accounts = {x["id"]: x for x in await read_database(self.db).accounts.find({"user_id": U}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)}
        cats = {x["id"]: x for x in await read_database(self.db).categories.find({"user_id": U}, {"_id": 0, "id": 1, "name": 1, "icon": 1, "color": 1}).to_list(5000)}
        goals = {x["id"]: x for x in await read_database(self.db).saving_goals.find({"user_id": U}, PROJ).to_list(1000)}
        debts = await read_database(self.db).debts.find({"user_id": U}, PROJ).to_list(2000)
        debt_by_id = {d["id"]: d for d in debts}
        rps = await read_database(self.db).recurring_payments.find({"user_id": U}, PROJ).to_list(1000)
        rp_by_id = {r["id"]: r for r in rps}
        lo, hi = _cal_str_window(a, b)
        events = []

        def acc_name(aid):
            return (accounts.get(aid) or {}).get("name") if aid else None

        # 1) Registered movements (real money).
        async for t in read_database(self.db).transactions.find({"user_id": U, "date": {"$gte": lo, "$lte": hi}}, PROJ):
            d, hm = _cal_dt(t.get("date"), tz)
            if not d or not (a <= d <= b):
                continue
            if t.get("goal_contribution_id"):
                continue  # represented by its goal contribution (single event, no duplicate)
            typ, amount = t.get("type"), float(t.get("amount") or 0)
            cat = cats.get(t.get("category_id")) or {}
            links = {}
            flow, sign, net = typ, 0, True
            if typ == "income":
                sign = 1
                if t.get("debt_payment_id") or t.get("debt_id"):
                    kind, sub = "debt", "debt_collection"
                    links["debt_id"] = t.get("debt_id")
                else:
                    kind, sub = "income", "income"
            elif typ == "expense":
                sign = -1
                if t.get("bill_payment_id"):
                    kind, sub = "bill", "bill_paid"
                    links["bill_id"] = t.get("bill_id")
                elif t.get("recurring_record_id"):
                    kind, sub = "recurring", "recurring_paid"
                    links["recurring_id"] = t.get("recurring_payment_id")
                else:
                    kind, sub = "expense", "expense"
            elif typ == "debt_payment":
                kind, sub, sign = "debt", "debt_payment", -1
                links["debt_id"] = t.get("debt_id")
            elif typ == "loan_given":
                kind, sub, sign = "debt", "loan_given", -1
            elif typ == "loan_received":
                kind, sub, sign = "debt", "loan_received", 1
            else:  # transfer between own accounts: neither income nor expense
                kind, sub, sign, net = "other", "transfer", 0, False
            rp = rp_by_id.get(links.get("recurring_id")) if links.get("recurring_id") else None
            debt = debt_by_id.get(links.get("debt_id")) if links.get("debt_id") else None
            detail = acc_name(t.get("account_id"))
            if typ == "transfer":
                src, dst = acc_name(t.get("account_id")), acc_name(t.get("to_account_id"))
                detail = " → ".join(x for x in (src, dst) if x) or None
            events.append({
                "id": f"tx:{t['id']}", "kind": kind, "subtype": sub, "source": "transaction", "ref_id": t["id"],
                "date": d.isoformat(), "time": hm, "title": t.get("name") or "", "account": detail,
                "category": cat.get("name"), "amount": amount, "sign": sign, "realized": True,
                "counts_in_net": net, "flow": flow, "status": "done",
                "icon": (rp or {}).get("icon") or cat.get("icon") or (debt or {}).get("icon"),
                "color": (rp or {}).get("color") or cat.get("color"), "links": links,
            })

        # 2) Goal contributions (tracking only -> never income/expense).
        async for c in read_database(self.db).goal_contributions.find({"user_id": U, "deleted": {"$ne": True}, "date": {"$gte": lo, "$lte": hi}}, {"_id": 0, "request_fingerprint": 0}):
            d, hm = _cal_dt(c.get("date"), tz)
            if not d or not (a <= d <= b):
                continue
            g = goals.get(c.get("goal_id")) or {}
            events.append({
                "id": f"gc:{c['id']}", "kind": "goal", "subtype": "goal_deposit" if c.get("kind") == "deposit" else "goal_withdrawal",
                "source": "goal", "ref_id": c.get("goal_id"), "date": d.isoformat(), "time": hm,
                "title": g.get("name") or "", "account": acc_name(c.get("account_id")), "category": None,
                "amount": float(c.get("amount") or 0), "sign": 0, "realized": bool(c.get("real_movement")),
                "counts_in_net": False, "flow": "goal", "status": "done", "icon": g.get("icon"), "color": g.get("color"),
                "links": {"goal_id": c.get("goal_id"), "contribution_id": c["id"], "transaction_id": c.get("transaction_id")},
            })

        # 3) Goal target dates (planned milestone, all-day).
        for g in goals.values():
            td = g.get("target_date")
            if not td:
                continue
            try:
                d = date.fromisoformat(str(td)[:10])
            except ValueError:
                continue
            if not (a <= d <= b):
                continue
            pub = _goal_public(g, today)
            status = "completed" if pub["completed"] else ("overdue" if d < today else "target")
            events.append({
                "id": f"goal:{g['id']}", "kind": "goal", "subtype": "goal_target", "source": "goal", "ref_id": g["id"],
                "date": d.isoformat(), "time": None, "title": g.get("name") or "", "account": acc_name(g.get("account_id")),
                "category": None, "amount": float(pub["remaining"]), "sign": 0, "realized": False, "counts_in_net": False,
                "flow": "goal", "status": status, "icon": g.get("icon"), "color": g.get("color"), "links": {"goal_id": g["id"]},
            })

        # 3b) Bill dues (planned). Paid bills are represented by their payment movements.
        #     Unpaid bills linked to a recurring payment hide that recurring due (single event).
        hide_rp = set()
        bills_in = await read_database(self.db).bills.find({"user_id": U, "due_date": {"$gte": a.isoformat(), "$lte": b.isoformat()}}, PROJ).to_list(5000)
        if bills_in:
            bpaid = await self.obligations._bill_paid_map([x["id"] for x in bills_in])
            for bl in bills_in:
                pub = _bill_public(bl, bpaid.get(bl["id"], Decimal(0)), today)
                if pub["status"] == "paid":
                    continue
                rp = rp_by_id.get(bl.get("recurring_payment_id")) if bl.get("recurring_payment_id") else None
                if rp:
                    view = current_shared_view(bill_id=bl["id"])
                    rd = view.obligation["original_due_date"] if view else _bill_rp_due(rp, bl["due_date"])
                    if rd:
                        hide_rp.add((rp["id"], rd))
                cat = cats.get(bl.get("category_id")) or {}
                events.append({
                    "id": f"bill:{bl['id']}", "kind": "bill", "subtype": "bill_due", "source": "bill", "ref_id": bl["id"],
                    "date": bl["due_date"], "time": None, "title": bl.get("name") or "",
                    "account": bl.get("provider") or acc_name(bl.get("account_id")), "category": cat.get("name"),
                    "amount": pub["remaining"], "sign": -1, "realized": False, "counts_in_net": False,
                    "flow": "planned_expense", "status": pub["status"], "partial": pub["partial"],
                    "icon": bl.get("icon") or cat.get("icon"), "color": bl.get("color") or cat.get("color"),
                    "links": {"bill_id": bl["id"]},
                })
        # Unpaid bills linked to a recurring payment whose due falls just outside the window.
        for bl in await read_database(self.db).bills.find({"user_id": U, "recurring_payment_id": {"$ne": None},
                                       "due_date": {"$gte": (a - timedelta(days=16)).isoformat(), "$lte": (b + timedelta(days=16)).isoformat()}}, PROJ).to_list(2000):
            rp = rp_by_id.get(bl.get("recurring_payment_id"))
            if not rp:
                continue
            paid_b = (await self.obligations._bill_paid_map([bl["id"]])).get(bl["id"], Decimal(0))
            if paid_b >= Decimal(str(bl["amount"])) - Decimal("0.001"):
                continue
            view = current_shared_view(bill_id=bl["id"])
            rd = view.obligation["original_due_date"] if view else _bill_rp_due(rp, bl["due_date"])
            if rd:
                hide_rp.add((rp["id"], rd))

        # 4) Recurring payment dues (planned). Paid dues settled by a movement are
        #    represented by that movement; tracking-only marks are shown as "marked".
        if rps:
            records = await self.obligations._rp_records(a=a, b=b)
            for rp in rps:
                for st in _rp_month_states(rp, a, b, records, today):
                    recs = st["records"]
                    cat = cats.get(rp.get("category_id")) or {}
                    base = {
                        "kind": "recurring", "source": "recurring", "ref_id": rp["id"], "date": st["due_date"], "time": None,
                        "title": rp.get("name") or "", "account": acc_name(rp.get("account_id")), "category": cat.get("name"),
                        "sign": -1, "realized": False, "counts_in_net": False, "flow": "planned_expense",
                        "icon": rp.get("icon"), "color": rp.get("color"), "links": {"recurring_id": rp["id"]},
                    }
                    if st["status"] == "paid":
                        if current_shared_view(recurring_id=rp["id"], due=st["due_date"]) is not None:
                            continue  # real shared money is already represented by its movement
                        marks = [r for r in recs if not r.get("transaction_id")]
                        if not marks:
                            continue  # fully represented by the linked movement(s)
                        amt = float(sum((Decimal(str(r["amount"])) for r in marks), Decimal(0)))
                        events.append({**base, "id": f"rp:{rp['id']}:{st['due_date']}", "subtype": "recurring_marked",
                                       "amount": amt, "status": "marked", "sign": 0})
                    else:
                        if (rp["id"], st["due_date"]) in hide_rp:
                            continue  # shown once, as the linked bill
                        events.append({**base, "id": f"rp:{rp['id']}:{st['due_date']}", "subtype": "recurring_due",
                                       "amount": st["remaining"], "status": st["status"], "partial": st["partial"],
                                       "expected": st["expected"]})

        # 5) Debt due dates (planned; payments are already real movements above).
        for dbt in debts:
            dd = dbt.get("due_date")
            if not dd or dbt.get("status") != "active" or float(dbt.get("remaining_amount") or 0) <= 0:
                continue
            try:
                d = date.fromisoformat(str(dd)[:10])
            except ValueError:
                continue
            if not (a <= d <= b):
                continue
            i_owe = dbt.get("direction") == "i_owe"
            events.append({
                "id": f"debt:{dbt['id']}", "kind": "debt", "subtype": "debt_due" if i_owe else "debt_due_collect",
                "source": "debt", "ref_id": dbt["id"], "date": d.isoformat(), "time": None, "title": dbt.get("name") or "",
                "account": dbt.get("person") or acc_name(dbt.get("account_id")), "category": None,
                "amount": float(dbt["remaining_amount"]), "sign": -1 if i_owe else 1, "realized": False,
                "counts_in_net": False, "flow": "planned_expense" if i_owe else "planned_income",
                "status": "overdue" if d < today else "pending", "icon": dbt.get("icon"), "color": dbt.get("color"),
                "links": {"debt_id": dbt["id"]},
            })

        # Timed events first (by time), all-day events after; stable by title.
        events.sort(key=lambda e: (e["date"], e["time"] is None, e["time"] or "", e["title"].lower()))
        return events

    async def calendar_events(self, start: str, end: str, tz_offset: int = 0, types: Optional[str] = None):
        a = _rp_day(start, "La fecha inicial no es válida.")
        b = _rp_day(end, "La fecha final no es válida.")
        if b < a:
            raise HTTPException(422, "La fecha final debe ser posterior a la inicial.")
        if (b - a).days > CAL_MAX_DAYS:
            raise HTTPException(422, "El intervalo es demasiado amplio.")
        sel = _cal_types(types)
        today = _rp_today(tz_offset)
        events = [e for e in await self._cal_events(a, b, _local_tz(tz_offset), today) if e["kind"] in sel]
        return {"start": a.isoformat(), "end": b.isoformat(), "today": today.isoformat(), "events": events}

    async def calendar_summary(self, year: Optional[int] = None, month: Optional[int] = None, tz_offset: int = 0, types: Optional[str] = None):
        today = _rp_today(tz_offset)
        year, month = year or today.year, month or today.month
        if not 1 <= month <= 12 or not 1900 <= year <= 3000:
            raise HTTPException(422, "Mes no válido.")
        sel = _cal_types(types)
        a, b = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        events = [e for e in await self._cal_events(a, b, _local_tz(tz_offset), today) if e["kind"] in sel]
        out = {"year": year, "month": month, "today": today.isoformat(), **_cal_summary(events, a, b)}
        # Bills due this month (full amount, paid or not). A separate concept from
        # "payments": never added to real spending totals.
        if "bill" in sel:
            s, n = Decimal(0), 0
            async for bl in read_database(self.db).bills.find({"user_id": self.owner, "due_date": {"$gte": a.isoformat(), "$lte": b.isoformat()}}, {"_id": 0, "amount": 1}):
                s += Decimal(str(bl["amount"]))
                n += 1
            out["bills"] = {"amount": float(s), "count": n, "available": True}
        return out

    async def calendar_upcoming(self, tz_offset: int = 0, limit: int = 5, offset: int = 0, days: int = 120, types: Optional[str] = None):
        today = _rp_today(tz_offset)
        limit, offset, days = max(1, min(int(limit), 50)), max(0, int(offset)), max(1, min(int(days), 365))
        sel = _cal_types(types)
        a, b = today - timedelta(days=CAL_MAX_DAYS - days), today + timedelta(days=days)
        events = await self._cal_events(a, b, _local_tz(tz_offset), today)
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

    async def create_budget(self, data, idempotency_key, *, session):
        bid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.owner}:budget:{idempotency_key}")) if idempotency_key else new_id()
        try:
            fingerprint = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest() if idempotency_key else None
        except (ValueError, TypeError):
            raise HTTPException(422, "La solicitud original no es válida.") from None
        if idempotency_key:
            # Include legacy random IDs; never adopt their current fields as an
            # original request. The native _id index serializes new keyed creates.
            matches = await self.db.budgets.find({"user_id": self.owner, "idempotency_key": idempotency_key}, session=session).to_list(2)
            if len(matches) > 1:
                raise HTTPException(409, "La clave tiene registros históricos ambiguos; requiere verificación.")
            if matches:
                existing = matches[0]
                if existing.get("request_fingerprint") != fingerprint:
                    raise HTTPException(409, "La clave tiene otra solicitud o no conserva una huella original verificable.")
                return shared_public(existing)
        payload = await self._validate_budget(data, session=session)
        b = Budget(id=bid, user_id=self.owner, **payload).model_dump()
        doc = {**b, "_id": bid, **({"idempotency_key": idempotency_key, "request_fingerprint": fingerprint} if idempotency_key else {})}
        await self.db.budgets.insert_one(doc, session=session)
        return reference_public(b)

    async def update_budget(self, bid, data, *, session):

        old = await self.db.budgets.find_one({"id": bid, "user_id": self.owner}, PROJ, session=session)
        if not old:
            raise HTTPException(404, "Presupuesto no encontrado.")
        effective = data.model_copy(update={"category_id": old.get("category_id")}) if "category_id" not in data.model_fields_set else data
        payload = await self._validate_budget(effective, replacing=bid, session=session, old=old)
        payload["updated_at"] = now_iso()
        await self.db.budgets.update_one({"id": bid, "user_id": self.owner}, {"$set": payload}, session=session)
        doc = await self.db.budgets.find_one({"id": bid, "user_id": self.owner}, PROJ, session=session)
        return shared_public(doc)

    async def create_goal(self, data, idempotency_key, *, session):
        gid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.owner}:goal:{idempotency_key}")) if idempotency_key else new_id()
        fingerprint = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest()
        previous = await self.db.saving_goals.find_one({"_id": gid, "user_id": self.owner}, session=session)
        if previous:
            if previous.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            return _goal_public(previous)
        fields, initial = await self._validate_goal(data, session=session)
        initial = initial or 0.0
        g = SavingGoal(id=gid, user_id=self.owner, current_amount=initial, initial_amount=initial, **fields).model_dump()
        if g["target_amount"] > 0 and initial >= g["target_amount"]:
            g["completed_at"] = now_iso()
        stored = dict(g, _id=gid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await self.db.saving_goals.insert_one(stored, session=session)
        return _goal_public(g)

    async def update_goal(self, gid, data, *, session):

        if not await self.db.saving_goals.find_one({"id": gid, "user_id": self.owner}, {"_id": 0, "id": 1}, session=session):
            raise HTTPException(404, "Meta no encontrada.")
        old = await self.db.saving_goals.find_one({"id": gid, "user_id": self.owner}, PROJ, session=session)
        effective = data.model_copy(update={"account_id": old.get("account_id")}) if "account_id" not in data.model_fields_set else data
        fields, initial = await self._validate_goal(effective, replacing=gid, session=session, old=old, supplied=data.model_fields_set)
        fields["updated_at"] = now_iso()
        if initial is not None:
            fields["initial_amount"] = initial
        await self.db.saving_goals.update_one({"id": gid, "user_id": self.owner}, {"$set": fields}, session=session)
        return _goal_public(await self.recompute_goal(gid, session=session))

    async def delete_goal(self, gid, *, session):

        g = await self.db.saving_goals.find_one({"id": gid, "user_id": self.owner}, {"_id": 0, "id": 1}, session=session)
        if not g:
            return {"ok": True}
        await coordinate(self.db, self.owner, {"goal_id": gid}, session)
        contributions = await self.db.goal_contributions.find({"goal_id": gid, "user_id": self.owner, "deleted": {"$ne": True}}, session=session).to_list(None)
        ids = {c["id"] for c in contributions}
        async for tx in self.db.transactions.find({"goal_id": gid, "user_id": self.owner}, PROJ, session=session):
            if tx.get("goal_contribution_id") not in ids:
                raise HTTPException(409, "La meta tiene movimientos sin un aporte verificable.")
        for contribution in contributions:
            await check_goal_contribution(self.db, self.owner, contribution, session)
            await retire(self.db, "goal_contributions", contribution, self.owner, session)
        # Real transfers already moved money between the user's accounts: keep them
        # (balances unchanged) and only remove the link to the deleted goal.
        await self.db.transactions.update_many(
            {"goal_id": gid, "user_id": self.owner},
            versioned_movement_update({"$unset": {"goal_id": "", "goal_contribution_id": ""}}), session=session,
        )
        await self.db.saving_goals.delete_one({"id": gid, "user_id": self.owner}, session=session)
        return {"ok": True}

    async def create_goal_contribution(self, gid, data, idempotency_key, *, session):
        cid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.owner}:goal-contribution:{gid}:{idempotency_key}")) if idempotency_key else new_id()
        tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"goal-contribution-movement:{cid}"))
        fingerprint = hashlib.sha256(json.dumps({"goal": gid, **data.model_dump()}, sort_keys=True, allow_nan=False).encode()).hexdigest()
        amount = _positive_money(data.amount, "El monto debe ser mayor que cero.")
        when = _parse_dt(data.date) if data.date else datetime.now(timezone.utc)
        if when is None:
            raise HTTPException(422, "La fecha no es válida.")
        notes = (data.notes or "").strip()[:200] or None

        previous = await self.db.goal_contributions.find_one({"_id": cid, "user_id": self.owner}, session=session)
        if previous:
            if previous.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            if previous.get("deleted"):
                raise HTTPException(409, "El aporte ya fue anulado; no se volverá a crear.")
            g = await self.db.saving_goals.find_one({"id": gid, "user_id": self.owner}, PROJ, session=session)
            return {"contribution": _goal_clean(previous), "goal": _goal_public(g) if g else None}
        g = await self.recompute_goal(gid, session=session)
        if not g:
            raise HTTPException(404, "Meta no encontrada.")
        if data.account_id and not await self.db.accounts.find_one({"id": data.account_id, "user_id": self.owner}, PROJ, session=session):
            raise HTTPException(422, "La cuenta seleccionada no existe.")
        await coordinate(self.db, self.owner, {"goal_id": gid, "account_id": data.account_id}, session)
        if data.kind == "withdrawal" and Decimal(str(amount)) > Decimal(str(g["current_amount"])):
            raise HTTPException(422, "El retiro supera el ahorro acumulado de la meta.")
        tx_id = None
        if data.real_movement:
            goal_acc = g.get("account_id")
            if not goal_acc or not await self.db.accounts.find_one({"id": goal_acc, "user_id": self.owner}, PROJ, session=session):
                raise HTTPException(422, "Para mover dinero real, la meta debe tener una cuenta asociada.")
            if not data.account_id:
                raise HTTPException(422, "Selecciona la cuenta para registrar el movimiento real.")
            if data.account_id == goal_acc:
                raise HTTPException(422, "La cuenta debe ser distinta de la cuenta asociada a la meta.")
            src, dst = (data.account_id, goal_acc) if data.kind == "deposit" else (goal_acc, data.account_id)
            tx = Transaction(
                id=tid, user_id=self.owner, amount=amount, type="transfer", date=when.isoformat(),
                name=(f"Ahorro: {g['name']}" if data.kind == "deposit" else f"Retiro de meta: {g['name']}"),
                account_id=src, to_account_id=dst, notes=notes,
            ).model_dump()
            tx.update(goal_id=gid, goal_contribution_id=cid)
            stored_movement = dict(tx, _id=tid)
            if getattr(self.settings, "history_keys_write_enabled", False):
                stored_movement = with_history_keys(stored_movement, self.settings.history_keys_generation)
            await self.db.transactions.insert_one(stored_movement, session=session)
            await self.obligations.recompute_account_balance(src, session=session)
            await self.obligations.recompute_account_balance(dst, session=session)
            tx_id = tid
        contribution = {
            "id": cid, "user_id": self.owner, "goal_id": gid, "kind": data.kind, "amount": amount,
            "date": when.isoformat(), "account_id": data.account_id or None, "notes": notes,
            "real_movement": bool(tx_id), "transaction_id": tx_id, "created_at": now_iso(),
        }
        stored = dict(contribution, _id=cid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await self.db.goal_contributions.insert_one(stored, session=session)
        g2 = await self.recompute_goal(gid, session=session)
        return {"contribution": contribution, "goal": _goal_public(g2)}
