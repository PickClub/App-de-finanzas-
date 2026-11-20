"""Transactional, owner-scoped receipts for authenticated movement mutations."""
from hashlib import sha256
import json

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(encoded.encode()).hexdigest()


async def apply_movement_once(db, owner, key, operation, payload, session, execute):
    if key is None:
        return await execute(session)
    if not key.isascii() or not all(33 <= ord(char) <= 126 for char in key):
        raise HTTPException(422, "Invalid Idempotency-Key")
    identity = {"_id": digest([owner, key]), "user_id": owner}
    fingerprint = digest([operation, payload])
    receipt = await db.movement_receipts.find_one(identity, session=session)
    if receipt is not None:
        if receipt["fingerprint"] != fingerprint:
            raise HTTPException(409, "Idempotency-Key already used for a different request")
        return receipt["response"]
    response = await execute(session)
    try:
        await db.movement_receipts.insert_one(
            {**identity, "fingerprint": fingerprint, "response": response}, session=session
        )
    except DuplicateKeyError:
        # Abort all effects. Never read the winning receipt through this snapshot.
        raise HTTPException(503, "Retry with the same Idempotency-Key") from None
    return response
