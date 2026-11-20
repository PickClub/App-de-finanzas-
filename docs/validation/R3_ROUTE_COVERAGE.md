# R3 delivery 2 route coverage

The 72 legacy private method/path pairs below are compared against the
detached FastAPI registration. Offline verification covers the shared
authentication boundary for every pair and focused feature regressions.
It does not certify MongoDB transactions or every payload variant.
There are 71 implemented pairs, one intentional exclusion and no missing
functional pairs. New Notes and movement-reference routes are outside this
denominator. Existing managed R4 write variants remain gated.

| Method | Route | Disposition |
| --- | --- | --- |
| GET | `/api/accounts` | Implemented and verified offline |
| POST | `/api/accounts` | Implemented and verified offline |
| DELETE | `/api/accounts/{account_id}` | Implemented and verified offline |
| PUT | `/api/accounts/{account_id}` | Implemented and verified offline |
| GET | `/api/bills` | Implemented and verified offline |
| POST | `/api/bills` | Implemented and verified offline |
| DELETE | `/api/bills/payments/{pid}` | Implemented and verified offline |
| GET | `/api/bills/summary` | Implemented and verified offline |
| DELETE | `/api/bills/{bid}` | Implemented and verified offline |
| GET | `/api/bills/{bid}` | Implemented and verified offline |
| PUT | `/api/bills/{bid}` | Implemented and verified offline |
| POST | `/api/bills/{bid}/payments` | Implemented and verified offline |
| POST | `/api/bills/{bid}/payments/reconcile` | Implemented and verified offline |
| GET | `/api/budgets` | Implemented and verified offline |
| POST | `/api/budgets` | Implemented and verified offline |
| GET | `/api/budgets/overview` | Implemented and verified offline |
| DELETE | `/api/budgets/{bid}` | Implemented and verified offline |
| PUT | `/api/budgets/{bid}` | Implemented and verified offline |
| GET | `/api/budgets/{bid}/detail` | Implemented and verified offline |
| GET | `/api/calendar/events` | Implemented and verified offline |
| GET | `/api/calendar/summary` | Implemented and verified offline |
| GET | `/api/calendar/upcoming` | Implemented and verified offline |
| GET | `/api/categories` | Implemented and verified offline |
| POST | `/api/categories` | Implemented and verified offline |
| POST | `/api/categories/init-defaults` | Implemented and verified offline |
| DELETE | `/api/categories/{cid}` | Implemented and verified offline |
| PUT | `/api/categories/{cid}` | Implemented and verified offline |
| POST | `/api/debt-payments` | Implemented and verified offline |
| POST | `/api/debt-payments/reconcile` | Implemented and verified offline |
| DELETE | `/api/debt-payments/{pid}` | Implemented and verified offline |
| GET | `/api/debts` | Implemented and verified offline |
| POST | `/api/debts` | Implemented and verified offline |
| DELETE | `/api/debts/{did}` | Implemented and verified offline |
| GET | `/api/debts/{did}` | Implemented and verified offline |
| PUT | `/api/debts/{did}` | Implemented and verified offline |
| GET | `/api/debts/{did}/payments` | Implemented and verified offline |
| GET | `/api/financial-context` | Implemented and verified offline |
| GET | `/api/goals` | Implemented and verified offline |
| POST | `/api/goals` | Implemented and verified offline |
| GET | `/api/goals/overview` | Implemented and verified offline |
| DELETE | `/api/goals/{gid}` | Implemented and verified offline |
| GET | `/api/goals/{gid}` | Implemented and verified offline |
| PUT | `/api/goals/{gid}` | Implemented and verified offline |
| GET | `/api/goals/{gid}/contributions` | Implemented and verified offline |
| POST | `/api/goals/{gid}/contributions` | Implemented and verified offline |
| GET | `/api/recurring` | Implemented and verified offline |
| POST | `/api/recurring` | Implemented and verified offline |
| GET | `/api/recurring-payments` | Implemented and verified offline |
| POST | `/api/recurring-payments` | Implemented and verified offline |
| GET | `/api/recurring-payments/overview` | Implemented and verified offline |
| DELETE | `/api/recurring-payments/payments/{pid}` | Implemented and verified offline |
| DELETE | `/api/recurring-payments/{rid}` | Implemented and verified offline |
| GET | `/api/recurring-payments/{rid}` | Implemented and verified offline |
| PUT | `/api/recurring-payments/{rid}` | Implemented and verified offline |
| POST | `/api/recurring-payments/{rid}/end` | Implemented and verified offline |
| GET | `/api/recurring-payments/{rid}/link-candidates` | Implemented and verified offline |
| GET | `/api/recurring-payments/{rid}/occurrences` | Implemented and verified offline |
| POST | `/api/recurring-payments/{rid}/pause` | Implemented and verified offline |
| POST | `/api/recurring-payments/{rid}/payments` | Implemented and verified offline |
| POST | `/api/recurring-payments/{rid}/payments/reconcile` | Implemented and verified offline |
| POST | `/api/recurring-payments/{rid}/resume` | Implemented and verified offline |
| DELETE | `/api/recurring/{rid}` | Implemented and verified offline |
| POST | `/api/seed` | Intentionally excluded for security |
| GET | `/api/summary` | Implemented and verified offline |
| GET | `/api/transactions` | Implemented and verified offline |
| POST | `/api/transactions` | Implemented and verified offline |
| GET | `/api/transactions/page` | Implemented and verified offline |
| DELETE | `/api/transactions/{tid}` | Implemented and verified offline |
| GET | `/api/transactions/{tid}` | Implemented and verified offline |
| PUT | `/api/transactions/{tid}` | Implemented and verified offline |
| GET | `/api/user` | Implemented and verified offline |
| PUT | `/api/user` | Implemented and verified offline |
