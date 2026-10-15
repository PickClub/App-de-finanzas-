// Preserve fields absent from the existing form and never submit payment-derived fields.
export function debtUpdatePayload(debt: any, fields: any, hasPayments: boolean) {
  return {
    name: fields.name, direction: debt.direction,
    person: fields.person === (debt.person ?? "") ? debt.person ?? null : fields.person,
    original_amount: hasPayments ? debt.original_amount : fields.original_amount,
    start_date: debt.start_date, due_date: debt.due_date ?? null,
    minimum_payment: fields.minimum_payment, payment_frequency: fields.payment_frequency,
    interest_rate: fields.interest_rate, notes: debt.notes ?? null,
    color: fields.color, icon: fields.icon,
    account_id: debt.account_id ?? null, category_id: fields.category_id ?? null,
  };
}

// This read-before-write guard detects stale edits; the server remains authoritative.
// It does not provide atomic compare-and-swap against other clients.
export function debtSnapshotMatches(before: any, current: any): boolean {
  const keys = ['id', 'name', 'direction', 'person', 'original_amount', 'total_paid',
    'remaining_amount', 'status', 'start_date', 'due_date', 'minimum_payment',
    'payment_frequency', 'interest_rate', 'notes', 'color', 'icon', 'account_id', 'category_id'];
  return !!current && keys.every(key => (before[key] ?? null) === (current[key] ?? null));
}
