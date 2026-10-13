"""Read-only history pagination. No startup, writes, migrations or index creation."""
import base64
from bisect import insort
from datetime import datetime, timezone
import hashlib
import json
import re

from fastapi import HTTPException
from pymongo.errors import PyMongoError

TYPES = {"income", "expense", "transfer", "debt_payment", "loan_given", "loan_received"}


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
                    limit=50, order="recent", cursor=None):
    if type(limit) is not int or not 1 <= limit <= 100 or order not in {"recent", "oldest"}:
        raise HTTPException(422, "Límite u orden inválido.")
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
    after = decode_cursor(cursor, scope) if cursor is not None else None
    query = {"user_id": user}
    if account_id is not None:
        query["$or"] = [{"account_id": account_id}, {"type": "transfer", "to_account_id": account_id}]
    if category_id is not None:
        query["category_id"] = category_id
    if types is not None:
        query["type"] = {"$in": sorted(set(types))}
    selected = []
    sequence = 0
    try:
        # Normalize only for comparison. Preserve stored date/payload in responses.
        # O(candidate count * page size), O(page size) retained documents.
        async for row in db.transactions.find(query, projection):
            when = parse_instant(row.get("date"), stored=True)
            identifier = row.get("id")
            if not isinstance(identifier, str) or not 1 <= len(identifier) <= 256:
                raise HTTPException(409, "Identificador histórico no verificable.")
            key = when, identifier
            if lower is not None and when < lower or upper is not None and when >= upper:
                continue
            if after is not None and (key >= after if order == "recent" else key <= after):
                continue
            sequence += 1
            insort(selected, (key, sequence, row))
            if len(selected) > limit + 1:
                selected.pop(0 if order == "recent" else -1)
    except PyMongoError:
        raise HTTPException(503, "No se pudo consultar el historial. Reintenta manualmente.") from None
    if order == "recent":
        selected.reverse()
    if any(a[0] == b[0] for a, b in zip(selected, selected[1:])):
        raise HTTPException(409, "Identificadores históricos duplicados; no se puede paginar con seguridad.")
    has_more = len(selected) > limit
    page = selected[:limit]
    return {"items": public([entry[2] for entry in page]), "has_more": has_more,
            "next_cursor": encode_cursor(scope, page[-1][0]) if has_more else None}


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
