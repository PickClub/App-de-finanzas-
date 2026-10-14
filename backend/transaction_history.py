"""Read-only history pagination. No startup, writes, migrations or index creation."""
import base64
from bisect import insort
from datetime import datetime, timezone
import hashlib
import json
import re
import asyncio
import math
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from bson import BSON
from bson.decimal128 import Decimal128
from bson.errors import BSONError

from fastapi import HTTPException
from pymongo.errors import PyMongoError

TYPES = {"income", "expense", "transfer", "debt_payment", "loan_given", "loan_received"}


@dataclass(frozen=True)
class ReadBudget:
    seconds: float = 10.0
    documents: int = 100000
    bytes: int = 33554432


def exact_amount(value):
    try:
        if value is None or value == "": value = 0
        if type(value) is bool: raise ValueError()
        amount = value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))
        if not amount.is_finite(): raise ValueError()
        return amount
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(409, "Importe histórico no verificable.") from None


def amount_cursor(scope, amount, when, identifier):
    value = {"v": 2, "scope": scope, "amount": str(amount), "date": iso(when), "id": identifier}
    token = base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")
    if len(token) > 2048:
        raise HTTPException(409, "Importe histórico demasiado extenso para un cursor seguro.")
    return token


def decode_amount_cursor(token, scope, order):
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 2048 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
            raise ValueError()
        raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        value = json.loads(raw)
        if set(value) != {"v", "scope", "amount", "date", "id"} or type(value["v"]) is not int or value["v"] != 2 or value["scope"] != scope:
            raise ValueError()
        if type(value["amount"]) is not str or not isinstance(value["id"], str) or not 1 <= len(value["id"]) <= 256:
            raise ValueError()
        amount = exact_amount(value["amount"])
        when = parse_instant(value["date"])
        if amount_cursor(scope, amount, when, value["id"]) != token:
            raise ValueError()
        return (amount if order == "high" else amount.copy_negate(), when, value["id"])
    except (ValueError, TypeError, KeyError, UnicodeError, HTTPException):
        raise HTTPException(422, "Cursor inválido o incompatible con los filtros y el contexto.") from None


async def reject_duplicate_ids(db, user, milliseconds):
    pipeline = [{"$match": {"user_id": user}},
                {"$group": {"_id": "$id", "n": {"$sum": 1}}},
                {"$match": {"n": {"$gt": 1}}}, {"$limit": 1},
                {"$project": {"_id": 0, "duplicate": {"$literal": True}}}]
    cursor = db.transactions.aggregate(pipeline, allowDiskUse=False, maxTimeMS=milliseconds,
                                       collation={"locale": "simple"}, batchSize=1)
    try:
        if await cursor.to_list(1):
            raise HTTPException(409, "Identificadores históricos duplicados; no se puede paginar con seguridad.")
    finally:
        await asyncio.wait_for(cursor.close(), 1)


def parse_instant(value, *, stored=False):
    try:
        if not isinstance(value, str) or not value:
            raise ValueError()
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not stored and ("T" not in value or parsed.tzinfo is None):
            raise ValueError()
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(409 if stored else 422, "Fecha histórica no verificable." if stored else "La fecha debe ser un instante ISO con zona horaria.") from None


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def scope_hash(context, filters):
    return hashlib.sha256(json.dumps([context, filters], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def encode_cursor(scope, key):
    value = {"v": 1, "scope": scope, "date": iso(key[0]), "id": key[1]}
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(token, scope):
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 2048 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
            raise ValueError()
        raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
        value = json.loads(raw)
        if not isinstance(value, dict) or set(value) != {"v", "scope", "date", "id"}:
            raise ValueError()
        if type(value["v"]) is not int or value["v"] != 1 or value["scope"] != scope:
            raise ValueError()
        if not isinstance(value["id"], str) or not 1 <= len(value["id"]) <= 256:
            raise ValueError()
        when = parse_instant(value["date"])
        if value["date"] != iso(when) or encode_cursor(scope, (when, value["id"])) != token:
            raise ValueError()
        return when, value["id"]
    except (ValueError, TypeError, UnicodeError, HTTPException):
        raise HTTPException(422, "Cursor inválido o incompatible con los filtros y el contexto.") from None


async def read_page(db, user, projection, public, *, context, account_id=None,
                    category_id=None, types=None, start=None, end=None,
                    limit=50, order="recent", cursor=None, budget=ReadBudget()):
    if type(limit) is not int or not 1 <= limit <= 100 or order not in {"recent", "oldest", "high", "low"}:
        raise HTTPException(422, "Límite u orden inválido.")
    if (type(budget) is not ReadBudget or type(budget.seconds) not in (int, float)
            or not math.isfinite(budget.seconds) or not 0 < budget.seconds <= 10
            or type(budget.documents) is not int or not 0 < budget.documents <= 100000
            or type(budget.bytes) is not int or not 0 < budget.bytes <= 33554432):
        raise HTTPException(422, "Presupuesto de lectura inválido.")
    for identifier in (account_id, category_id):
        if identifier is not None and (not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 256):
            raise HTTPException(422, "Identificador de filtro inválido.")
    if types is not None and (not types or any(t not in TYPES for t in types)):
        raise HTTPException(422, "Tipo de movimiento inválido.")
    lower = parse_instant(start) if start is not None else None
    upper = parse_instant(end) if end is not None else None
    if lower is not None and upper is not None and lower > upper:
        raise HTTPException(422, "El inicio no puede ser posterior al fin.")
    filters = {"user": user, "account": account_id, "category": category_id,
               "types": sorted(set(types or [])), "start": iso(lower) if lower else None,
               "end": iso(upper) if upper else None, "order": order}
    scope = scope_hash(context, filters)
    by_amount = order in {"high", "low"}
    after = (decode_amount_cursor(cursor, scope, order) if by_amount else decode_cursor(cursor, scope)) if cursor is not None else None
    query = {"user_id": user}
    if account_id is not None:
        query["$or"] = [{"account_id": account_id}, {"type": "transfer", "to_account_id": account_id}]
    if category_id is not None:
        query["category_id"] = category_id
    if types is not None:
        query["type"] = {"$in": sorted(set(types))}
    async def collect():
        selected = []
        sequence = total = visited = used = 0
        deadline = time.monotonic() + budget.seconds
        def remaining_ms():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HTTPException(503, "Se agotó el tiempo de consulta. No se devolvieron resultados parciales.")
            return max(1, int(remaining * 1000))
        await reject_duplicate_ids(db, user, remaining_ms())
        # Normalize only for comparison. Preserve stored date/payload in responses.
        # O(candidate count * page size), O(page size) retained documents.
        rows = db.transactions.find(query, projection).max_time_ms(remaining_ms()).batch_size(100)
        try:
            async for row in rows:
                remaining_ms()
                visited += 1
                used += len(BSON.encode(row))
                if visited > budget.documents or used > budget.bytes:
                    raise HTTPException(503, "El historial excede el presupuesto de lectura. No se devolvieron resultados parciales.")
                when = parse_instant(row.get("date"), stored=True)
                identifier = row.get("id")
                if not isinstance(identifier, str) or not 1 <= len(identifier) <= 256:
                    raise HTTPException(409, "Identificador histórico no verificable.")
                if lower is not None and when < lower or upper is not None and when >= upper:
                    continue
                amount = exact_amount(row.get("amount")) if by_amount else None
                key = ((amount if order == "high" else amount.copy_negate()), when, identifier) if by_amount else (when, identifier)
                total += 1
                if after is not None and (key <= after if order == "oldest" else key >= after):
                    continue
                sequence += 1
                entry = (key, sequence, row)
                if len(selected) == limit + 1:
                    worst = -1 if order == "oldest" else 0
                    if (entry >= selected[worst] if order == "oldest" else entry <= selected[worst]):
                        continue
                    selected.pop(worst)
                insort(selected, entry)
        finally:
            await asyncio.wait_for(rows.close(), 1)
        # Recheck the live catalog after scanning; this is still not a snapshot.
        await reject_duplicate_ids(db, user, remaining_ms())
        remaining_ms()
        if order != "oldest": selected.reverse()
        if any(a[0] == b[0] for a, b in zip(selected, selected[1:])):
            raise HTTPException(409, "Identificadores históricos duplicados; no se puede paginar con seguridad.")
        has_more = len(selected) > limit
        page = selected[:limit]
        next_cursor = None
        if has_more:
            key = page[-1][0]
            next_cursor = amount_cursor(scope, key[0] if order == "high" else key[0].copy_negate(), key[1], key[2]) if by_amount else encode_cursor(scope, key)
        items = [dict(entry[2], amount=str(entry[2]['amount'].to_decimal()))
                 if isinstance(entry[2].get('amount'), Decimal128) else entry[2] for entry in page]
        return {"items": public(items), "has_more": has_more,
                "next_cursor": next_cursor, "total": total}
    try:
        return await asyncio.wait_for(collect(), budget.seconds)
    except (PyMongoError, TimeoutError, BSONError):
        raise HTTPException(503, "No se pudo completar la consulta del historial dentro del presupuesto. Reintenta manualmente.") from None


async def read_detail(db, user, tid, projection, public):
    try:
        rows = await db.transactions.find({"user_id": user, "id": tid}, projection).to_list(2)
    except PyMongoError:
        raise HTTPException(503, "No se pudo consultar el movimiento. Reintenta manualmente.") from None
    if not rows:
        raise HTTPException(404, "Movimiento no encontrado.")
    if len(rows) != 1:
        raise HTTPException(409, "Identificador de movimiento ambiguo.")
    return public(rows[0])
