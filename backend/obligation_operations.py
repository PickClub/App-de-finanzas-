"""Owner-scoped bill and recurring operations for the detached R3 API."""
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
import re
from typing import Literal, Optional
import uuid

from backend.movement_operations import versioned_movement_update
from fastapi import HTTPException
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from backend.account_operations import recompute_balance
from backend.history_keys import with_history_keys
from backend.reference_integrity import (
    check_bill_payment, check_record, coordinate, guard_legacy_bill,
    guard_legacy_movement, guard_legacy_receipt, guard_legacy_recurring,
    preserve_references, retire,
)
from backend.shared_obligations import (
    current_shared_periods, current_shared_view, dispatch_shared_change,
    dispatch_shared_payment, edit_shared_bill, edit_shared_recurring,
    guard_shared_state_change, public_financial_document as shared_public,
    read_database, shared_bill_public, shared_link_candidates,
    shared_paid_events, shared_parent_context, shared_recurring_public,
)

PROJ = {"_id": 0}
CENT = Decimal("0.01")

RP_FREQS = {
    "daily": ("d", 1), "weekly": ("d", 7), "biweekly": ("d", 14), "monthly": ("m", 1),
    "bimonthly": ("m", 2), "quarterly": ("m", 3), "semiannual": ("m", 6), "annual": ("m", 12),
}
RP_REMINDERS = {None, 0, 1, 3, 7}
RP_LINK_FIELDS = ("recurring_record_id", "goal_contribution_id", "debt_payment_id", "debt_id", "bill_payment_id")
BILL_REMINDERS = (None, 1, 3, 7)


def new_id():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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


def _positive_money(value, msg):
    if value is None or not math.isfinite(value) or value <= 0:
        raise HTTPException(422, msg)
    return float(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP))


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


def _rp_day(value, msg):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        raise HTTPException(422, msg)


def _rp_today(tz_offset: int = 0):
    return datetime.now(_local_tz(tz_offset)).date()


def _rp_dates(ver, a: date, b: date):
    """Due dates of one schedule version inside [a, b] (inclusive)."""
    s = date.fromisoformat(ver["start_date"])
    lo = max(a, s)
    if lo > b:
        return []
    kind, step = RP_FREQS[ver["frequency"]]
    out = []
    if kind == "d":
        n = -(-(lo - s).days // step)
        d = s + timedelta(days=n * step)
        while d <= b:
            out.append(d)
            d += timedelta(days=step)
        return out
    # Month based: the configured day is kept; short months use their last day
    # for that period only (31 -> 30 Apr -> 28/29 Feb -> 31 Mar).
    day = ver.get("due_day") or s.day
    start_idx = s.year * 12 + s.month - 1
    n = max(0, ((lo.year * 12 + lo.month - 1) - start_idx) // step - 1)
    while True:
        y, m0 = divmod(start_idx + n * step, 12)
        m = m0 + 1
        d = date(y, m, min(day, calendar.monthrange(y, m)[1]))
        if d > b:
            break
        if d >= lo:
            out.append(d)
        n += 1
    return out


def _rp_paused(rp, d: date):
    for p in rp.get("pauses") or []:
        if p["start"] <= d.isoformat() and (not p.get("end") or d.isoformat() < p["end"]):
            return True
    return False


def _rp_occurrences(rp, a: date, b: date):
    """{due_date_iso: expected_amount} for the recurrence inside [a, b]."""
    vers = rp.get("versions") or []
    if rp.get("end_date"):
        b = min(b, date.fromisoformat(rp["end_date"]))
    out = {}
    for i, v in enumerate(vers):
        vf = date.fromisoformat(v["valid_from"])
        vt = date.fromisoformat(vers[i + 1]["valid_from"]) - timedelta(days=1) if i + 1 < len(vers) else b
        lo, hi = max(a, vf), min(b, vt)
        if lo > hi:
            continue
        for d in _rp_dates(v, lo, hi):
            if not _rp_paused(rp, d):
                out[d.isoformat()] = float(v["amount"])
    return out


def _rp_state(rp, due_iso, expected, recs, today):
    paid = sum((Decimal(str(r["amount"])) for r in recs), Decimal(0))
    if expected is None:
        expected = recs[0].get("expected_amount", 0) if recs else 0
    exp = Decimal(str(expected))
    settled = any(r.get("settles") for r in recs)
    is_paid = bool(recs) and (settled or paid >= exp)
    remaining = Decimal(0) if is_paid else max(Decimal(0), exp - paid)
    status = "paid" if is_paid else ("overdue" if due_iso < today.isoformat() else "pending")
    result = {
        "due_date": due_iso, "expected": float(exp), "paid": float(paid), "remaining": float(remaining),
        "status": status, "partial": (not is_paid and paid > 0), "overpaid": float(max(Decimal(0), paid - exp)) if is_paid else 0.0,
        "records": [shared_public(r) for r in sorted(recs, key=lambda r: r.get("created_at", ""))],
    }
    return shared_recurring_public(result, current_shared_view(recurring_id=rp.get("id"), due=due_iso), today)


def _rp_state_name(rp, today):
    if rp.get("end_date") and rp["end_date"] < today.isoformat():
        return "ended"
    return rp.get("state") or "active"


def _rp_current(rp):
    return (rp.get("versions") or [{}])[-1]


def _rp_public(rp, today):
    v = _rp_current(rp)
    out = {k: val for k, val in rp.items() if k not in ("_id", "request_fingerprint", "versions", "pauses", "_reference_revision")}
    out.update(amount=v.get("amount"), frequency=v.get("frequency"), start_date=v.get("start_date"),
               due_day=v.get("due_day"), state=_rp_state_name(rp, today))
    return shared_public(out)


def _rp_month_states(rp, a, b, records, today):
    occ = _rp_occurrences(rp, a, b)
    for (rid, due), _ in records.items():
        if rid == rp["id"] and due not in occ and a.isoformat() <= due <= b.isoformat():
            occ[due] = None  # paid occurrence that no longer matches the current schedule
    for due in current_shared_periods(rp["id"]):
        if a.isoformat() <= due <= b.isoformat():
            occ.setdefault(due, None)
    return [_rp_state(rp, d, occ[d], records.get((rp["id"], d), []), today) for d in sorted(occ)]


def _rp_next_due(rp, records, today, horizon_days=800):
    hi = today + timedelta(days=horizon_days)
    occurrences = _rp_occurrences(rp, today, hi)
    for due in current_shared_periods(rp["id"]):
        if today.isoformat() <= due <= hi.isoformat():
            occurrences.setdefault(due, None)
    for d, exp in sorted(occurrences.items()):
        st = _rp_state(rp, d, exp, records.get((rp["id"], d), []), today)
        if st["status"] != "paid":
            return st
    return None


def _bill_add_period(d: date, freq: str, anchor_day: int) -> date:
    if freq == "weekly":
        return d + timedelta(days=7)
    step = {"monthly": 1, "quarterly": 3, "yearly": 12}[freq]
    idx = d.year * 12 + d.month - 1 + step
    y, m0 = divmod(idx, 12)
    return date(y, m0 + 1, min(anchor_day, calendar.monthrange(y, m0 + 1)[1]))


def _bill_rp_due(rp, bill_due: str):
    """Occurrence of the linked recurring payment that matches this bill period."""
    d = date.fromisoformat(bill_due)
    occ = _rp_occurrences(rp, d - timedelta(days=16), d + timedelta(days=16))
    if not occ:
        return None
    return min(occ.keys(), key=lambda k: (abs((date.fromisoformat(k) - d).days), k))


def _bill_public(b, paid: Decimal, today: date, cats=None, accounts=None):
    amount = Decimal(str(b["amount"]))
    is_paid = paid >= amount - Decimal("0.001")
    remaining = Decimal(0) if is_paid else amount - paid
    status = "paid" if is_paid else ("overdue" if b["due_date"] < today.isoformat() else "pending")
    days_left = (date.fromisoformat(b["due_date"]) - today).days
    cat = (cats or {}).get(b.get("category_id")) or {}
    acc = (accounts or {}).get(b.get("account_id")) or {}
    rem = b.get("reminder_days")
    out = {k: v for k, v in b.items() if k not in ("_id", "request_fingerprint", "_payment_revision", "_reference_revision")}
    out.update(
        paid_amount=float(paid), remaining=float(remaining), status=status, partial=(not is_paid and paid > 0),
        progress=float(min(Decimal(1), paid / amount)) if amount > 0 else 0.0, days_left=days_left,
        reminder_active=bool(rem is not None and not is_paid and 0 <= days_left <= rem),
        category_name=cat.get("name"), category_icon=cat.get("icon"), category_color=cat.get("color"),
        account_name=acc.get("name"),
    )
    return shared_bill_public(out, current_shared_view(bill_id=b["id"]), today)


class Transaction(BaseModel):
    id: str = Field(default_factory=new_id)
    user_id: str
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


class ObligationOperations:
    def __init__(self, database, owner, settings=None):
        self.db = database
        self.owner = owner
        self.settings = settings

    async def recompute_account_balance(self, account_id, session=None):
        await recompute_balance(self.db, self.owner, account_id, PROJ, session)

    async def _rp_records(self, rid=None, a=None, b=None, session=None):
        q = {"user_id": self.owner, "deleted": {"$ne": True}}
        if rid:
            q["recurring_id"] = rid
        if a or b:
            q["due_date"] = {}
            if a:
                q["due_date"]["$gte"] = a.isoformat()
            if b:
                q["due_date"]["$lte"] = b.isoformat()
        grouped = {}
        async for r in read_database(self.db).recurring_payment_records.find(q, {"_id": 0, "request_fingerprint": 0}, session=session):
            grouped.setdefault((r["recurring_id"], r["due_date"]), []).append(r)
        return grouped

    async def _rp_validate(self, data: RecurringPaymentCreate, session=None, old=None, supplied=None):
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
            cat = await self.db.categories.find_one({"id": data.category_id, "user_id": self.owner}, PROJ, session=session)
            if not cat or cat.get("type") != "expense" or cat.get("is_group"):
                raise HTTPException(422, "La categoría debe ser una categoría de gasto existente.")
        if data.account_id and (old is None or data.account_id != old.get("account_id")) and not await self.db.accounts.find_one({"id": data.account_id, "user_id": self.owner}, PROJ, session=session):
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
        await coordinate(self.db, self.owner, fields, session, old)
        return fields, version

    async def _rp_get(self, rid, session=None):
        rp = await read_database(self.db).recurring_payments.find_one({"id": rid, "user_id": self.owner}, PROJ, session=session)
        if not rp:
            raise HTTPException(404, "Pago recurrente no encontrado.")
        return rp

    async def _bill_validate(self, data: BillIn, session=None, old=None, supplied=None, shared=False):
        name = (data.name or "").strip()
        if not name:
            raise HTTPException(422, "El nombre de la factura es obligatorio.")
        amount = _positive_money(data.amount, "El monto debe ser mayor que cero.")
        due = _rp_day(data.due_date, "La fecha de vencimiento no es válida.").isoformat()
        if data.reminder_days not in BILL_REMINDERS:
            raise HTTPException(422, "El recordatorio no es válido.")
        if data.category_id and (old is None or data.category_id != old.get("category_id")):
            cat = await self.db.categories.find_one({"id": data.category_id, "user_id": self.owner}, PROJ, session=session)
            if not cat or cat.get("type") != "expense" or cat.get("is_group"):
                raise HTTPException(422, "La categoría debe ser una categoría de gasto existente.")
        if data.account_id and (old is None or data.account_id != old.get("account_id")) and not await self.db.accounts.find_one({"id": data.account_id, "user_id": self.owner}, PROJ, session=session):
            raise HTTPException(422, "La cuenta seleccionada no existe.")
        if data.recurring_payment_id and (old is None or data.recurring_payment_id != old.get("recurring_payment_id")) and not await self.db.recurring_payments.find_one(
                {"id": data.recurring_payment_id, "user_id": self.owner}, {"_id": 0, "id": 1}, session=session):
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
            await guard_legacy_recurring(self.db, self.owner, fields["recurring_payment_id"], session, due)
        preserve_references(fields, data, old, ("account_id", "category_id", "recurring_payment_id"), supplied)
        await coordinate(self.db, self.owner, fields, session, old)
        return fields

    async def _bill_paid_map(self, bill_ids=None, session=None):
        q = {"user_id": self.owner, "deleted": {"$ne": True}}
        if bill_ids is not None:
            q["bill_id"] = {"$in": list(bill_ids)}
        out = {}
        async for p in read_database(self.db).bill_payments.find(q, {"_id": 0, "bill_id": 1, "amount": 1}, session=session):
            out[p["bill_id"]] = out.get(p["bill_id"], Decimal(0)) + Decimal(str(p["amount"]))
        return out

    async def _bill_for_write(self, bid, session):
        await guard_legacy_bill(self.db, self.owner, bid, session)
        # Every payment/amount edit must write this shared document before reading
        # the paid total. A real increment (not a no-op) forces concurrent snapshots
        # to conflict and revalidate through the existing transaction runner.
        bill = await self.db.bills.find_one_and_update(
            {"id": bid, "user_id": self.owner},
            {"$inc": {"_payment_revision": 1}},
            projection=PROJ, return_document=ReturnDocument.AFTER, session=session,
        )
        if not bill:
            raise HTTPException(404, "Factura no encontrada.")
        return bill

    async def _bill_lookups(self):
        cats = {c["id"]: c for c in await read_database(self.db).categories.find({"user_id": self.owner}, {"_id": 0, "id": 1, "name": 1, "icon": 1, "color": 1}).to_list(5000)}
        accs = {a["id"]: a for a in await read_database(self.db).accounts.find({"user_id": self.owner}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)}
        return cats, accs

    async def list_recurring_payments(self, tz_offset: int = 0):
        today = _rp_today(tz_offset)
        rps = await read_database(self.db).recurring_payments.find({"user_id": self.owner}, PROJ).sort("created_at", -1).to_list(500)
        return [_rp_public(rp, today) for rp in rps]

    async def recurring_overview(self, year: Optional[int] = None, month: Optional[int] = None, tz_offset: int = 0):
        today = _rp_today(tz_offset)
        year, month = year or today.year, month or today.month
        if not 1 <= month <= 12 or not 1900 <= year <= 3000:
            raise HTTPException(422, "Mes no válido.")
        a = date(year, month, 1)
        b = date(year, month, calendar.monthrange(year, month)[1])
        rps = await read_database(self.db).recurring_payments.find({"user_id": self.owner}, PROJ).sort("created_at", -1).to_list(500)
        rem_hi = today + timedelta(days=7)
        records = await self._rp_records(a=min(a, today - timedelta(days=400)), b=max(b, rem_hi + timedelta(days=800)))
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

    async def get_recurring_payment(self, rid: str, tz_offset: int = 0):
        today = _rp_today(tz_offset)
        rp = await self._rp_get(rid)
        records = await self._rp_records(rid=rid)
        out = _rp_public(rp, today)
        out["next_due"] = _rp_next_due(rp, records, today) if out["state"] == "active" else None
        views = current_shared_periods(rid)
        ordinary = [r for (_, due), rs in records.items() if due not in views for r in rs]
        out["paid_total"] = float(sum((Decimal(str(r["amount"])) for r in ordinary), Decimal(0))
                                  + sum((v.summary.paid for v in views.values()), Decimal(0)))
        out["payments_count"] = len(ordinary) + len(shared_paid_events(views.values()))
        out["account"] = await read_database(self.db).accounts.find_one({"id": rp.get("account_id"), "user_id": self.owner}, {"_id": 0, "id": 1, "name": 1, "color": 1}) if rp.get("account_id") else None
        out["category"] = await read_database(self.db).categories.find_one({"id": rp.get("category_id"), "user_id": self.owner}, {"_id": 0, "id": 1, "name": 1, "icon": 1, "color": 1}) if rp.get("category_id") else None
        return shared_public(out)

    async def recurring_occurrences(self, rid: str, offset: int = 0, limit: int = 20, tz_offset: int = 0):
        today = _rp_today(tz_offset)
        rp = await self._rp_get(rid)
        limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
        records = await self._rp_records(rid=rid)
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

    async def recurring_link_candidates(self, rid: str, due_date: str):
        rp = await self._rp_get(rid)
        d = _rp_day(due_date, "Fecha no válida.")
        view = current_shared_view(recurring_id=rid, due=d.isoformat())
        if view is not None:
            return await shared_link_candidates(view)
        lo = datetime.combine(d - timedelta(days=15), datetime.min.time(), timezone.utc).isoformat()
        hi = datetime.combine(d + timedelta(days=16), datetime.min.time(), timezone.utc).isoformat()
        q = {"user_id": self.owner, "type": "expense", "date": {"$gte": lo, "$lt": hi}}
        for f in RP_LINK_FIELDS:
            q[f] = None
        txs = await read_database(self.db).transactions.find(q, PROJ).sort("date", -1).to_list(200)
        txs = [tx for tx in txs if not any(key.startswith("_shared_") for key in tx)]
        target = _rp_current(rp).get("amount") or 0
        txs.sort(key=lambda t: (abs(t["amount"] - target), 0 if t.get("category_id") == rp.get("category_id") else 1))
        return shared_public(txs[:10])

    async def list_bills(self, status: str = "all", tz_offset: int = 0):
        if status not in ("all", "pending", "paid", "overdue"):
            raise HTTPException(422, "Filtro no válido.")
        today = _rp_today(tz_offset)
        bills = await read_database(self.db).bills.find({"user_id": self.owner}, PROJ).sort("due_date", 1).to_list(5000)
        paid = await self._bill_paid_map([b["id"] for b in bills])
        cats, accs = await self._bill_lookups()
        items = [_bill_public(b, paid.get(b["id"], Decimal(0)), today, cats, accs) for b in bills]
        counts = {"all": len(items)}
        for s in ("pending", "paid", "overdue"):
            counts[s] = sum(1 for i in items if i["status"] == s)
        if status != "all":
            items = [i for i in items if i["status"] == status]
        items.sort(key=lambda i: (i["due_date"], i["name"].lower()))
        return {"today": today.isoformat(), "items": items, "counts": counts}

    async def bills_summary(self, tz_offset: int = 0, year: Optional[int] = None, month: Optional[int] = None):
        today = _rp_today(tz_offset)
        year, month = year or today.year, month or today.month
        if not 1 <= month <= 12 or not 1900 <= year <= 3000:
            raise HTTPException(422, "Mes no válido.")
        tz = _local_tz(tz_offset)
        bills = await read_database(self.db).bills.find({"user_id": self.owner}, PROJ).to_list(5000)
        paid = await self._bill_paid_map([b["id"] for b in bills])
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
        async for p in read_database(self.db).bill_payments.find({"user_id": self.owner, "deleted": {"$ne": True}, "date": {"$gte": lo, "$lte": hi}}, {"_id": 0, "bill_id": 1, "amount": 1, "date": 1}):
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

    async def get_bill(self, bid: str, tz_offset: int = 0):
        b = await read_database(self.db).bills.find_one({"id": bid, "user_id": self.owner}, PROJ)
        if not b:
            raise HTTPException(404, "Factura no encontrada.")
        today = _rp_today(tz_offset)
        pays = await read_database(self.db).bill_payments.find({"bill_id": bid, "user_id": self.owner, "deleted": {"$ne": True}}, {"_id": 0, "request_fingerprint": 0}).sort("date", -1).to_list(500)
        paid = sum((Decimal(str(p["amount"])) for p in pays), Decimal(0))
        cats, accs = await self._bill_lookups()
        out = _bill_public(b, paid, today, cats, accs)
        for p in pays:
            p["account_name"] = (accs.get(p.get("account_id")) or {}).get("name")
        out["payments"] = pays
        rp = await read_database(self.db).recurring_payments.find_one({"id": b.get("recurring_payment_id"), "user_id": self.owner}, {"_id": 0, "id": 1, "name": 1}) if b.get("recurring_payment_id") else None
        out["recurring_payment_name"] = (rp or {}).get("name")
        return shared_public(out)

    async def create_recurring_payment(self, data, idempotency_key, *, session):
        rid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.owner}:recurring-payment:{idempotency_key}")) if idempotency_key else new_id()
        fingerprint = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest()
        today = _rp_today()
        await guard_legacy_recurring(self.db, self.owner, rid, session)
        prev = await self.db.recurring_payments.find_one({"_id": rid, "user_id": self.owner}, session=session)
        if prev:
            if prev.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            return _rp_public(prev, today)
        fields, version = await self._rp_validate(data, session=session)
        now = now_iso()
        rp = {
            "id": rid, "user_id": self.owner, **fields, "state": "active" if data.active else "paused",
            "versions": [{**version, "valid_from": version["start_date"]}],
            "pauses": [] if data.active else [{"start": min(today, date.fromisoformat(version["start_date"])).isoformat(), "end": None}],
            "created_at": now, "updated_at": None,
        }
        stored = dict(rp, _id=rid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await self.db.recurring_payments.insert_one(stored, session=session)
        return _rp_public(rp, today)

    async def update_recurring_payment(self, rid, data, *, session):
        today = _rp_today()

        context = await shared_parent_context(self.db, self.settings, origin="recurring", parent_id=rid,
            effective_user=self.owner, session=session)
        if context is not None:
            rp = context[1][0][3]
            effective = data.model_copy(update={f: rp.get(f) for f in ("account_id", "category_id", "end_date", "variable") if f not in data.model_fields_set})
            fields, version = await self._rp_validate(effective, session, old=rp, supplied=data.model_fields_set)
            if "end_date" not in data.model_fields_set:
                fields["end_date"] = rp.get("end_date")
            result = await edit_shared_recurring(self.db, context, fields, version, session=session, today=today,
                occurrences=_rp_occurrences, add_period=_bill_add_period)
            return _rp_public(result, today)
        await guard_legacy_recurring(self.db, self.owner, rid, session)
        rp = await self._rp_get(rid, session)
        effective = data.model_copy(update={f: rp.get(f) for f in ("account_id", "category_id") if f not in data.model_fields_set})
        fields, version = await self._rp_validate(effective, session, old=rp, supplied=data.model_fields_set)
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
        await self.db.recurring_payments.update_one({"id": rid, "user_id": self.owner}, {"$set": fields}, session=session)
        return _rp_public(await self._rp_get(rid, session), today)

    async def _rp_set_state(self, rid, action, *, session):
        today = _rp_today()
        context = await shared_parent_context(self.db, self.settings, origin="recurring", parent_id=rid,
            effective_user=self.owner, session=session)
        if context is None:
            await guard_legacy_recurring(self.db, self.owner, rid, session)
        rp = await self._rp_get(rid, session)
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
            await guard_shared_state_change(self.db, context, upd, session=session, today=today,
                occurrences=_rp_occurrences, add_period=_bill_add_period)
        await self.db.recurring_payments.update_one({"id": rid, "user_id": self.owner}, {"$set": upd}, session=session)
        return _rp_public(await self._rp_get(rid, session), today)

    async def delete_recurring_payment(self, rid, *, session):

        await guard_legacy_recurring(self.db, self.owner, rid, session)
        if not await self.db.recurring_payments.find_one({"id": rid, "user_id": self.owner}, PROJ, session=session):
            return {"ok": True}
        await coordinate(self.db, self.owner, {"recurring_id": rid}, session)
        records = await self.db.recurring_payment_records.find({"recurring_id": rid, "user_id": self.owner, "deleted": {"$ne": True}}, session=session).to_list(None)
        ids = {r["id"] for r in records}
        async for tx in self.db.transactions.find({"recurring_payment_id": rid, "user_id": self.owner}, PROJ, session=session):
            if tx.get("recurring_record_id") not in ids:
                raise HTTPException(409, "La recurrencia tiene movimientos sin un registro verificable.")
        for rec in records:
            await check_record(self.db, self.owner, rec, session)
            if rec.get("bill_payment_id"):
                payment = await self.db.bill_payments.find_one({"id": rec["bill_payment_id"], "user_id": self.owner}, PROJ, session=session)
                await self._bill_for_write(payment["bill_id"], session)
                await self.db.bill_payments.update_one({"id": payment["id"], "user_id": self.owner}, {"$set": {"recurring_record_id": None}}, session=session)
            await retire(self.db, "recurring_payment_records", rec, self.owner, session)
        await self.db.bills.update_many({"recurring_payment_id": rid, "user_id": self.owner}, {"$set": {"recurring_payment_id": None}}, session=session)
        # Keep expenses and bill payments; remove both sides of the recurring link.
        await self.db.transactions.update_many({"recurring_payment_id": rid, "user_id": self.owner}, versioned_movement_update({"$unset": {"recurring_payment_id": "", "recurring_record_id": ""}}), session=session)
        await self.db.recurring_payments.delete_one({"id": rid, "user_id": self.owner}, session=session)
        return {"ok": True}

    async def create_recurring_record(self, rid, data, idempotency_key, *, session):
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.owner}:recurring-record:{rid}:{idempotency_key}")) if idempotency_key else new_id()
        tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"recurring-record-movement:{pid}"))
        fingerprint = hashlib.sha256(json.dumps({"rid": rid, **data.model_dump()}, sort_keys=True, allow_nan=False).encode()).hexdigest()
        due = _rp_day(data.due_date, "La fecha de vencimiento no es válida.").isoformat()
        when = _parse_dt(data.date) if data.date else datetime.now(timezone.utc)
        if when is None:
            raise HTTPException(422, "La fecha efectiva no es válida.")
        notes = (data.notes or "").strip()[:200] or None
        today = _rp_today()

        shared = await dispatch_shared_payment(self.db, self.settings, origin="recurring",
            parent_id=rid, receipt_id=pid, transaction_id=tid, payload=data.model_dump(),
            effective_user=self.owner, session=session, occurrences=_rp_occurrences,
            add_period=_bill_add_period, recompute_account_balance=self.recompute_account_balance,
            effective_date=when.isoformat(), normalized_due=due)
        if shared is not None:
            return shared
        await guard_legacy_recurring(self.db, self.owner, rid, session, due)
        prev = await self.db.recurring_payment_records.find_one({"_id": pid, "user_id": self.owner}, session=session)
        if prev:
            if prev.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            if prev.get("deleted"):
                raise HTTPException(409, "La operación ya fue anulada; no se volverá a crear.")
            return {k: v for k, v in prev.items() if k not in ("_id", "request_fingerprint", "_reference_revision")}
        rp = await self._rp_get(rid, session)
        await coordinate(self.db, self.owner, {"recurring_id": rid}, session)
        d = date.fromisoformat(due)
        # A linked bill owns settlement for the matched recurring period.
        async for bill in self.db.bills.find(
            {"user_id": self.owner, "recurring_payment_id": rid}, PROJ, session=session
        ):
            if _bill_rp_due(rp, bill["due_date"]) == due:
                raise HTTPException(409, "Settle this period through its linked bill")
        occ = _rp_occurrences(rp, d, d)
        records = await self._rp_records(rid=rid, a=d, b=d, session=session)
        existing = records.get((rid, due), [])
        if due not in occ and not existing:
            raise HTTPException(422, "La fecha no corresponde a un vencimiento de este pago.")
        st = _rp_state(rp, due, occ.get(due), existing, today)
        expected = Decimal(str(st["expected"]))
        tx = None
        if data.mode == "link":
            if not data.transaction_id:
                raise HTTPException(422, "Selecciona el movimiento a vincular.")
            tx = await self.db.transactions.find_one({"id": data.transaction_id, "user_id": self.owner}, PROJ, session=session)
            if not tx or tx.get("type") != "expense":
                raise HTTPException(422, "El movimiento a vincular debe ser un gasto existente.")
            if any(tx.get(f) for f in RP_LINK_FIELDS):
                raise HTTPException(409, "Ese movimiento ya está vinculado a otro registro.")
            await guard_legacy_movement(self.db, self.owner, tx, session)
            amount = float(tx["amount"])
        else:
            amount = _positive_money(data.amount, "El monto pagado debe ser mayor que cero.")
        if data.account_id and not await self.db.accounts.find_one({"id": data.account_id, "user_id": self.owner}, PROJ, session=session):
            raise HTTPException(422, "La cuenta seleccionada no existe.")
        cat_id = data.category_id or rp.get("category_id")
        if data.category_id:
            cat = await self.db.categories.find_one({"id": data.category_id, "user_id": self.owner}, PROJ, session=session)
            if not cat or cat.get("type") != "expense" or cat.get("is_group"):
                raise HTTPException(422, "La categoría debe ser una categoría de gasto existente.")
        await coordinate(self.db, self.owner, {"account_id": tx.get("account_id") if tx else data.account_id,
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
                id=tid, user_id=self.owner, name=rp["name"], amount=amount, type="expense",
                date=when.isoformat(), category_id=cat_id, account_id=data.account_id, notes=notes,
            ).model_dump()
            new_tx.update(link)
            stored_movement = dict(new_tx, _id=tid)
            if getattr(self.settings, "history_keys_write_enabled", False):
                stored_movement = with_history_keys(stored_movement, self.settings.history_keys_generation)
            await self.db.transactions.insert_one(stored_movement, session=session)
            await self.recompute_account_balance(data.account_id, session=session)
            tx_id = tid
        elif data.mode == "link":
            await self.db.transactions.update_one({"id": tx["id"], "user_id": self.owner}, versioned_movement_update({"$set": link}), session=session)
            tx_id = tx["id"]
        else:
            tx_id = None
        record = {
            "id": pid, "user_id": self.owner, "recurring_id": rid, "due_date": due, "mode": data.mode,
            "amount": amount, "expected_amount": float(expected), "date": (tx["date"] if tx else when.isoformat()),
            "account_id": (tx.get("account_id") if tx else data.account_id) or None, "category_id": (tx.get("category_id") if tx else cat_id) or None,
            "notes": notes, "transaction_id": tx_id, "settles": bool(settles), "created_at": now_iso(),
        }
        stored = dict(record, _id=pid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await self.db.recurring_payment_records.insert_one(stored, session=session)
        return record

    async def delete_recurring_record(self, pid, *, session):
        rec = await self.db.recurring_payment_records.find_one({"id": pid, "user_id": self.owner}, session=session)
        shared = await dispatch_shared_change(self.db, self.settings, origin="recurring",
            receipt=rec, effective_user=self.owner, session=session,
            recompute_account_balance=self.recompute_account_balance)
        if shared is not None:
            return shared
        if rec:
            await guard_legacy_receipt(self.db, self.owner, rec, session)
        if not rec or rec.get("deleted"):
            return {"ok": True}
        await coordinate(self.db, self.owner, {"recurring_id": rec["recurring_id"]}, session)
        tx = await check_record(self.db, self.owner, rec, session)
        if rec.get("bill_payment_id"):
            payment = await self.db.bill_payments.find_one({"id": rec["bill_payment_id"], "user_id": self.owner}, PROJ, session=session)
            await self._bill_for_write(payment["bill_id"], session)
            await self.db.bill_payments.update_one({"id": payment["id"], "user_id": self.owner}, {"$set": {"recurring_record_id": None}}, session=session)
        if tx and rec["mode"] == "expense":
            if await self.db.recurring_templates.find_one({"source_transaction_id": tx["id"], "user_id": self.owner}, PROJ, session=session):
                raise HTTPException(409, "El movimiento es origen de una plantilla recurrente.")
            await self.db.transactions.delete_one({"id": tx["id"], "user_id": self.owner}, session=session)
            if tx.get("account_id"):
                await self.recompute_account_balance(tx["account_id"], session=session)
        elif tx:
            await self.db.transactions.update_one({"id": tx["id"], "user_id": self.owner}, versioned_movement_update({"$unset": {"recurring_payment_id": "", "recurring_record_id": ""}}), session=session)
        await retire(self.db, "recurring_payment_records", rec, self.owner, session)
        return {"ok": True}

    async def create_bill(self, data, idempotency_key, *, session):
        bid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.owner}:bill:{idempotency_key}")) if idempotency_key else new_id()
        try:
            fingerprint = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True, allow_nan=False).encode()).hexdigest() if idempotency_key else None
        except (ValueError, TypeError):
            raise HTTPException(422, "La solicitud original no es válida.") from None
        await guard_legacy_bill(self.db, self.owner, bid, session)
        prev = await self.db.bills.find_one({"_id": bid, "user_id": self.owner}, session=session)
        if prev:
            if prev.get("user_id") != self.owner or prev.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La clave tiene otra solicitud o no conserva una huella original verificable.")
            return shared_public(prev)
        fields = await self._bill_validate(data, session=session)
        now = now_iso()
        doc = {"id": bid, "user_id": self.owner, **fields, "series_id": bid,
               "anchor_day": int(fields["due_date"][8:10]), "next_bill_id": None, "created_at": now, "updated_at": now}
        if idempotency_key:
            doc["request_fingerprint"] = fingerprint
        await self.db.bills.insert_one(dict(doc, _id=bid), session=session)
        return doc

    async def update_bill(self, bid, data, *, session):

        context = await shared_parent_context(self.db, self.settings, origin="bill", parent_id=bid,
            effective_user=self.owner, session=session)
        if context is not None:
            b = context[1][0][2]
            if "recurring_payment_id" in data.model_fields_set and data.recurring_payment_id != b.get("recurring_payment_id"):
                raise HTTPException(409, "La factura reservada no permite reasignar su recurrencia.")
            effective = data.model_copy(update={f: b.get(f) for f in ("account_id", "category_id", "recurring_payment_id", "frequency") if f not in data.model_fields_set})
            fields = await self._bill_validate(effective, session, old=b, supplied=data.model_fields_set, shared=True)
            return await edit_shared_bill(self.db, context, fields, session=session, occurrences=_rp_occurrences, add_period=_bill_add_period)
        b = await self._bill_for_write(bid, session)
        effective = data.model_copy(update={f: b.get(f) for f in ("account_id", "category_id", "recurring_payment_id") if f not in data.model_fields_set})
        fields = await self._bill_validate(effective, session, old=b, supplied=data.model_fields_set)
        paid = (await self._bill_paid_map([bid], session=session)).get(bid, Decimal(0))
        if Decimal(str(fields["amount"])) < paid - Decimal("0.001"):
            raise HTTPException(422, f"El monto no puede ser menor que lo ya pagado ({float(paid):.2f}).")
        upd = dict(fields, updated_at=now_iso())
        if fields["due_date"] != b["due_date"]:
            upd["anchor_day"] = int(fields["due_date"][8:10])
        await self.db.bills.update_one({"id": bid, "user_id": self.owner}, {"$set": upd}, session=session)
        return await self.db.bills.find_one({"id": bid, "user_id": self.owner}, {"_id": 0, "_payment_revision": 0, "_reference_revision": 0}, session=session)

    async def delete_bill(self, bid, *, session):

        await guard_legacy_bill(self.db, self.owner, bid, session)
        if not await self.db.bills.find_one({"id": bid, "user_id": self.owner}, PROJ, session=session):
            return {"ok": True}
        await self._bill_for_write(bid, session)
        payments = await self.db.bill_payments.find({"bill_id": bid, "user_id": self.owner, "deleted": {"$ne": True}}, session=session).to_list(None)
        ids = {p["id"] for p in payments}
        async for tx in self.db.transactions.find({"bill_id": bid, "user_id": self.owner}, PROJ, session=session):
            if tx.get("bill_payment_id") not in ids:
                raise HTTPException(409, "La factura tiene movimientos sin un pago verificable.")
        for payment in payments:
            await check_bill_payment(self.db, self.owner, payment, session)
            if payment.get("recurring_record_id"):
                await coordinate(self.db, self.owner, {"recurring_id": (await self.db.recurring_payment_records.find_one({"id": payment["recurring_record_id"], "user_id": self.owner}, PROJ, session=session))["recurring_id"]}, session)
                await self.db.recurring_payment_records.update_one({"id": payment["recurring_record_id"], "user_id": self.owner}, {"$unset": {"bill_payment_id": ""}}, session=session)
            await retire(self.db, "bill_payments", payment, self.owner, session)
        # Keep actual expenses and any independent recurring tracking; no refund.
        await self.db.transactions.update_many({"bill_id": bid, "user_id": self.owner}, versioned_movement_update({"$unset": {"bill_id": "", "bill_payment_id": ""}}), session=session)
        await self.db.bills.update_many({"next_bill_id": bid, "user_id": self.owner}, {"$set": {"next_bill_id": None}}, session=session)
        await self.db.bills.delete_one({"id": bid, "user_id": self.owner}, session=session)
        return {"ok": True}

    async def pay_bill(self, bid, data, idempotency_key, *, session):
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.owner}:bill-payment:{bid}:{idempotency_key}")) if idempotency_key else new_id()
        tid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"bill-payment-movement:{pid}"))
        fingerprint = hashlib.sha256(json.dumps({"bid": bid, **data.model_dump()}, sort_keys=True, allow_nan=False).encode()).hexdigest()
        amount = _positive_money(data.amount, "El monto pagado debe ser mayor que cero.")
        when = _parse_dt(data.date) if data.date else datetime.now(timezone.utc)
        if when is None:
            raise HTTPException(422, "La fecha del pago no es válida.")
        notes = (data.notes or "").strip()[:200] or None
        today = _rp_today()

        shared = await dispatch_shared_payment(self.db, self.settings, origin="bill",
            parent_id=bid, receipt_id=pid, transaction_id=tid, payload=data.model_dump(),
            effective_user=self.owner, session=session, occurrences=_rp_occurrences,
            add_period=_bill_add_period, recompute_account_balance=self.recompute_account_balance,
            effective_date=when.isoformat())
        if shared is not None:
            return shared
        await guard_legacy_bill(self.db, self.owner, bid, session)
        prev = await self.db.bill_payments.find_one({"_id": pid, "user_id": self.owner}, session=session)
        if prev:
            if prev.get("request_fingerprint") != fingerprint:
                raise HTTPException(409, "La Idempotency-Key ya se utilizó con otros datos.")
            if prev.get("deleted"):
                raise HTTPException(409, "La operación ya fue anulada; no se volverá a crear.")
            return {k: v for k, v in prev.items() if k not in ("_id", "request_fingerprint", "_reference_revision")}
        b = await self._bill_for_write(bid, session)
        if not await self.db.accounts.find_one({"id": data.account_id, "user_id": self.owner}, PROJ, session=session):
            raise HTTPException(422, "La cuenta seleccionada no existe.")
        await coordinate(self.db, self.owner, {"account_id": data.account_id, "category_id": b.get("category_id")}, session)
        paid = (await self._bill_paid_map([bid], session=session)).get(bid, Decimal(0))
        remaining = Decimal(str(b["amount"])) - paid
        if remaining <= Decimal("0.001"):
            raise HTTPException(409, "Esta factura ya está pagada.")
        if Decimal(str(amount)) > remaining + Decimal("0.001"):
            raise HTTPException(422, f"El monto supera lo pendiente ({float(remaining):.2f}).")
        tx = Transaction(
            id=tid, user_id=self.owner, name=b["name"], amount=amount, type="expense", date=when.isoformat(),
            category_id=b.get("category_id"), account_id=data.account_id, notes=notes,
        ).model_dump()
        tx.update(bill_id=bid, bill_payment_id=pid)
        # Optional shared record with a linked recurring payment (same movement, no second charge).
        rec_id = None
        rp = await self.db.recurring_payments.find_one({"id": b.get("recurring_payment_id"), "user_id": self.owner}, PROJ, session=session) if b.get("recurring_payment_id") else None
        if b.get("recurring_payment_id") and not rp:
            raise HTTPException(404, "Not found")
        if rp:
            await coordinate(self.db, self.owner, {"recurring_payment_id": rp["id"]}, session)
        rp_due = _bill_rp_due(rp, b["due_date"]) if rp else None
        if rp_due:
            await guard_legacy_recurring(self.db, self.owner, rp["id"], session, rp_due)
        if rp and rp_due:
            d = date.fromisoformat(rp_due)
            recs = (await self._rp_records(rid=rp["id"], a=d, b=d, session=session)).get((rp["id"], rp_due), [])
            if any(record.get("transaction_id") and not record.get("bill_payment_id")
                   for record in recs):
                raise HTTPException(409, "The linked period already has an independent expense")
            for record in recs:
                if record.get("bill_payment_id") and not await self.db.bill_payments.find_one(
                    {"id": record["bill_payment_id"], "bill_id": bid, "user_id": self.owner,
                     "deleted": {"$ne": True}}, session=session
                ):
                    raise HTTPException(409, "The linked period already belongs to another bill")
            st = _rp_state(rp, rp_due, _rp_occurrences(rp, d, d).get(rp_due), recs, today)
            if st["status"] != "paid":
                rec_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"bill-rp-record:{pid}"))
                await self.db.recurring_payment_records.insert_one({
                    "_id": rec_id, "id": rec_id, "user_id": self.owner, "recurring_id": rp["id"], "due_date": rp_due,
                    "mode": "link", "amount": amount, "expected_amount": st["expected"], "date": when.isoformat(),
                    "account_id": data.account_id, "category_id": b.get("category_id"), "notes": notes,
                    "transaction_id": tid, "settles": False, "created_at": now_iso(), "bill_payment_id": pid,
                }, session=session)
                tx.update(recurring_payment_id=rp["id"], recurring_record_id=rec_id)
        stored_movement = dict(tx, _id=tid)
        if getattr(self.settings, "history_keys_write_enabled", False):
            stored_movement = with_history_keys(stored_movement, self.settings.history_keys_generation)
        await self.db.transactions.insert_one(stored_movement, session=session)
        await self.recompute_account_balance(data.account_id, session=session)
        payment = {
            "id": pid, "user_id": self.owner, "bill_id": bid, "series_id": b.get("series_id") or bid,
            "amount": amount, "date": when.isoformat(), "account_id": data.account_id, "notes": notes,
            "transaction_id": tid, "recurring_record_id": rec_id, "created_at": now_iso(),
        }
        stored = dict(payment, _id=pid)
        if idempotency_key:
            stored["request_fingerprint"] = fingerprint
        await self.db.bill_payments.insert_one(stored, session=session)
        # Fully paid recurring bill -> next period, created once.
        next_id = None
        if b.get("frequency", "once") != "once" and paid + Decimal(str(amount)) >= Decimal(str(b["amount"])) - Decimal("0.001") and not b.get("next_bill_id"):
            nd = _bill_add_period(date.fromisoformat(b["due_date"]), b["frequency"], int(b.get("anchor_day") or b["due_date"][8:10])).isoformat()
            existing = await self.db.bills.find_one({"user_id": self.owner, "series_id": b.get("series_id") or bid, "due_date": nd}, PROJ, session=session)
            if existing:
                next_id = existing["id"]
            else:
                next_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"bill-next:{bid}"))
                if not await self.db.bills.find_one({"_id": next_id, "user_id": self.owner}, session=session):
                    now = now_iso()
                    keep = ("name", "provider", "amount", "category_id", "account_id", "frequency", "reminder_days",
                            "description", "recurring_payment_id", "icon", "color", "anchor_day")
                    await coordinate(self.db, self.owner, {k: b.get(k) for k in keep}, session)
                    await self.db.bills.insert_one(dict({k: b.get(k) for k in keep}, _id=next_id, id=next_id, user_id=self.owner,
                                                   series_id=b.get("series_id") or bid, due_date=nd, next_bill_id=None,
                                                   created_at=now, updated_at=now), session=session)
            await self.db.bills.update_one({"id": bid, "user_id": self.owner}, {"$set": {"next_bill_id": next_id}}, session=session)
        return dict(payment, next_bill_id=next_id)

    async def delete_bill_payment(self, pid, *, session):
        p = await self.db.bill_payments.find_one({"id": pid, "user_id": self.owner}, session=session)
        shared = await dispatch_shared_change(self.db, self.settings, origin="bill",
            receipt=p, effective_user=self.owner, session=session,
            recompute_account_balance=self.recompute_account_balance)
        if shared is not None:
            return shared
        if p:
            await guard_legacy_receipt(self.db, self.owner, p, session)
        if not p or p.get("deleted"):
            return {"ok": True}
        await self._bill_for_write(p["bill_id"], session)
        tx = await check_bill_payment(self.db, self.owner, p, session)
        if await self.db.recurring_templates.find_one({"source_transaction_id": tx["id"], "user_id": self.owner}, PROJ, session=session):
            raise HTTPException(409, "El movimiento es origen de una plantilla recurrente.")
        if p.get("recurring_record_id"):
            rec = await self.db.recurring_payment_records.find_one({"id": p["recurring_record_id"], "user_id": self.owner}, session=session)
            await coordinate(self.db, self.owner, {"recurring_id": rec["recurring_id"]}, session)
            await retire(self.db, "recurring_payment_records", rec, self.owner, session)
        await self.db.transactions.delete_one({"id": tx["id"], "user_id": self.owner}, session=session)
        if tx.get("account_id"):
            await self.recompute_account_balance(tx["account_id"], session=session)
        await retire(self.db, "bill_payments", p, self.owner, session)
        # Keep a generated future period; series_id is a grouping key, not a FK.
        return {"ok": True}
