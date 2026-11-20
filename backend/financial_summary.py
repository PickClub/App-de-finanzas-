"""Existing financial summary calculations on an explicit owner snapshot."""
from datetime import datetime, timezone
import math

from fastapi import HTTPException
from pymongo.errors import PyMongoError


SUMMARY_LIMITS = (10, 100000, 32 * 1024 * 1024, 10000)


async def summarize(db, owner, session, *, now=None):
    import asyncio
    import time
    from bson import BSON, Decimal128
    from contextlib import aclosing
    from bson.errors import BSONError
    from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext

    timeout, max_docs, max_bytes, max_digits = SUMMARY_LIMITS
    deadline = time.monotonic() + timeout
    visited = used = 0
    now = now or datetime.now(timezone.utc)

    def milliseconds():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(503, "Se agotó el tiempo del resumen. No se devolvieron totales parciales.")
        return max(1, int(remaining * 1000))

    def money(row, field):
        value = row.get(field)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal, Decimal128)):
            raise HTTPException(409, "El resumen contiene un importe no verificable.")
        try:
            result = value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise HTTPException(409, "El resumen contiene un importe no verificable.") from None
        if not result.is_finite():
            raise HTTPException(409, "El resumen contiene un importe no verificable.")
        return result

    def precision(*values):
        digits = max(0, *(v.adjusted() for v in values)) - min(-2, *(v.as_tuple().exponent for v in values)) + 2
        if digits > max_digits:
            raise HTTPException(503, "El resumen excede el presupuesto de precisión. No se devolvieron totales parciales.")
        return max(28, digits)

    def add(total, value):
        with localcontext() as ctx:
            ctx.prec = precision(total, value)
            return total + value

    def number(value, rounded=True):
        with localcontext() as ctx:
            ctx.prec = precision(value)
            result = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN) if rounded else value
        output = float(result)  # Only at the existing JSON-number boundary.
        # Large valid values are not corruption. If the numeric API cannot
        # preserve the result, fail explicitly rather than silently lose cents.
        if not math.isfinite(output) or Decimal(str(output)) != result:
            raise HTTPException(503, "El total no puede representarse con precisión en la respuesta numérica actual.")
        return output

    def this_month(row):
        try:
            d = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, TypeError, ValueError):
            raise HTTPException(409, "El resumen contiene una fecha no verificable.") from None
        # Preserve the original stored-calendar month/offset convention (R9).
        return d.year == now.year and d.month == now.month

    async def duplicates(collection, query):
        cursor = collection.aggregate([
            {"$match": query}, {"$group": {"_id": "$id", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}, {"$limit": 1},
            {"$project": {"_id": 0, "duplicate": {"$literal": True}}},
        ], session=session, allowDiskUse=False, maxTimeMS=milliseconds(), batchSize=1,
           collation={"locale": "simple"})
        try:
            if await cursor.to_list(1):
                raise HTTPException(409, "El resumen contiene identificadores duplicados; no se pueden verificar los totales.")
        finally:
            await asyncio.wait_for(cursor.close(), 1)

    async def rows(collection, query, fields):
        nonlocal visited, used
        cursor = collection.find(query, {"_id": 0, "id": 1, **{field: 1 for field in fields}}, session=session)
        cursor = cursor.max_time_ms(milliseconds()).batch_size(100)
        try:
            async for row in cursor:
                milliseconds()
                visited += 1
                used += len(BSON.encode(row))
                if visited > max_docs or used > max_bytes:
                    raise HTTPException(503, "El resumen excede el presupuesto de lectura. No se devolvieron totales parciales.")
                if not isinstance(row.get("id"), str) or not row["id"] or len(row["id"]) > 256:
                    raise HTTPException(409, "El resumen contiene una identidad no verificable.")
                yield row
        finally:
            await asyncio.wait_for(cursor.close(), 1)

    async def collect():
        query = {"user_id": owner}
        payments_query = {**query, "deleted": {"$ne": True}}
        for collection, scope in ((db.accounts, query), (db.transactions, query),
                                  (db.debts, query), (db.debt_payments, payments_query)):
            await duplicates(collection, scope)
        total_balance = Decimal(0)
        accounts_count = 0
        async with aclosing(rows(db.accounts, query, ("current_balance",))) as source:
            async for row in source:
                total_balance = add(total_balance, money(row, "current_balance"))
                accounts_count += 1
        month_income = month_expense = Decimal(0)
        tx_query = {**query, "type": {"$in": ["income", "expense", "debt_payment"]}}
        async with aclosing(rows(db.transactions, tx_query, ("type", "date", "amount"))) as source:
            async for row in source:
                if this_month(row):
                    amount = money(row, "amount")
                    if row["type"] == "income":
                        month_income = add(month_income, amount)
                    else:
                        month_expense = add(month_expense, amount)
        i_owe = they_owe = Decimal(0)
        next_pay = None
        async with aclosing(rows(db.debts, query, ("direction", "remaining_amount", "due_date", "status", "minimum_payment", "name"))) as source:
            async for row in source:
                direction = row.get("direction")
                if direction not in ("i_owe", "they_owe"):
                    raise HTTPException(409, "El resumen contiene una dirección de deuda no verificable.")
                if direction == "i_owe":
                    i_owe = add(i_owe, money(row, "remaining_amount"))
                else:
                    they_owe = add(they_owe, money(row, "remaining_amount"))
                if direction == "i_owe" and row.get("due_date") and row.get("status") == "active":
                    if not isinstance(row["due_date"], str):
                        raise HTTPException(409, "El resumen contiene una fecha de deuda no verificable.")
                    try:
                        datetime.fromisoformat(row["due_date"].replace("Z", "+00:00"))
                    except ValueError:
                        raise HTTPException(409, "El resumen contiene una fecha de deuda no verificable.") from None
                    if next_pay is None or row["due_date"] < next_pay["date"]:
                        next_pay = {"date": row["due_date"], "amount": money(row, "minimum_payment"), "name": row.get("name", "")}
        paid_this_month = Decimal(0)
        async with aclosing(rows(db.debt_payments, payments_query, ("date", "amount"))) as source:
            async for row in source:
                if this_month(row):
                    paid_this_month = add(paid_this_month, money(row, "amount"))
        result = {
            "total_balance": number(total_balance),
            "month_income": number(month_income),
            "month_expense": number(month_expense),
            "debts": {"i_owe": number(i_owe), "they_owe": number(they_owe),
                      "paid_this_month": number(paid_this_month),
                      "next_payment": {**next_pay, "amount": number(next_pay["amount"], rounded=False)} if next_pay else None},
            "accounts_count": accounts_count,
        }
        milliseconds()
        return result

    try:
        return await asyncio.wait_for(collect(), timeout)
    except (PyMongoError, TimeoutError, BSONError, InvalidOperation):
        raise HTTPException(503, "No se pudo completar el resumen. Reintenta; no se devolvieron totales parciales.") from None
