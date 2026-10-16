"""Read-only aggregate diagnostic; importing this module never opens a connection."""


def expense_account_pipeline(user_id):
    """Return counts only; never emit IDs, amounts, dates or source documents.

    Call on transactions using a snapshot session, allowDiskUse=False and a
    bounded maxTimeMS. A missing, foreign, deleted or ambiguous account is not
    a valid source. Linked expenses are counted separately, never rewritten.
    """
    links = ("debt_id", "debt_payment_id", "bill_payment_id", "goal_contribution_id", "recurring_record_id")
    return [
        {"$match": {"user_id": user_id, "type": "expense"}},
        {"$project": {
            "_id": 0, "account_id": 1,
            "ordinary": {"$and": [{"$eq": [{"$ifNull": ["$" + field, None]}, None]} for field in links]},
        }},
        {"$lookup": {
            "from": "accounts", "let": {"source": "$account_id"},
            "pipeline": [
                {"$match": {"user_id": user_id, "deleted": {"$ne": True},
                            "$expr": {"$eq": ["$id", "$$source"]}}},
                {"$project": {"_id": 0, "id": 1}}, {"$limit": 2},
            ], "as": "source_matches",
        }},
        {"$group": {
            "_id": "$ordinary", "expenses": {"$sum": 1},
            "missing_or_empty_source": {"$sum": {"$cond": [
                {"$in": [{"$ifNull": ["$account_id", ""]}, [""]]}, 1, 0]}},
            "invalid_source": {"$sum": {"$cond": [
                {"$and": [{"$eq": [{"$type": "$account_id"}, "string"]},
                           {"$ne": ["$account_id", ""]}, {"$eq": [{"$size": "$source_matches"}, 1]}]}, 0, 1]}},
        }},
    ]
