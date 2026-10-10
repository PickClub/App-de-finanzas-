const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

export class ApiError extends Error {
  readonly detail: string;
  constructor(public readonly status: number, text: string) {
    super(`API ${status}: ${text}`);
    this.detail = this.message;
    try {
      const detail = JSON.parse(text).detail;
      if (typeof detail === "string") this.detail = detail;
    } catch { /* Non-JSON errors keep the original message. */ }
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new ApiError(res.status, text);
  }
  return res.json();
}

export const api = {
  // User
  getUser: () => request<any>("/user"),
  updateUser: (data: any) => request<any>("/user", { method: "PUT", body: JSON.stringify(data) }),
  // Accounts
  listAccounts: () => request<any[]>("/accounts"),
  createAccount: (d: any) => request<any>("/accounts", { method: "POST", body: JSON.stringify(d) }),
  updateAccount: (id: string, d: any) => request<any>(`/accounts/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  deleteAccount: (id: string) => request<any>(`/accounts/${id}`, { method: "DELETE" }),
  // Categories
  listCategories: () => request<any[]>("/categories"),
  initDefaultCategories: () => request<any>("/categories/init-defaults", { method: "POST" }),
  createCategory: (d: any) => request<any>("/categories", { method: "POST", body: JSON.stringify(d) }),
  updateCategory: (id: string, d: any) => request<any>(`/categories/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  deleteCategory: (id: string) => request<any>(`/categories/${id}`, { method: "DELETE" }),
  // Transactions
  listTransactions: () => request<any[]>("/transactions"),
  createTransaction: (d: any) => request<any>("/transactions", { method: "POST", body: JSON.stringify(d) }),
  updateTransaction: (id: string, d: any) => request<any>(`/transactions/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  deleteTransaction: (id: string) => request<any>(`/transactions/${id}`, { method: "DELETE" }),
  // Budgets
  listBudgets: () => request<any[]>("/budgets"),
  createBudget: (d: any, idempotencyKey?: string) =>
    request<any>("/budgets", {
      method: "POST",
      body: JSON.stringify(d),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    }),
  budgetsOverview: (year: number, month: number) =>
    request<any>(`/budgets/overview?year=${year}&month=${month}&tz_offset=${new Date().getTimezoneOffset()}`),
  budgetDetail: (id: string, year: number, month: number) =>
    request<any>(`/budgets/${id}/detail?year=${year}&month=${month}&tz_offset=${new Date().getTimezoneOffset()}`),
  updateBudget: (id: string, d: any) => request<any>(`/budgets/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  deleteBudget: (id: string) => request<any>(`/budgets/${id}`, { method: "DELETE" }),
  // Goals
  listGoals: () => request<any[]>("/goals"),
  goalsOverview: () => request<any>("/goals/overview"),
  getGoal: (id: string) => request<any>(`/goals/${id}`),
  listGoalContributions: (id: string, offset = 0, limit = 20) =>
    request<any>(`/goals/${id}/contributions?offset=${offset}&limit=${limit}`),
  createGoal: (d: any, idempotencyKey?: string) =>
    request<any>("/goals", {
      method: "POST",
      body: JSON.stringify(d),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    }),
  updateGoal: (id: string, d: any) => request<any>(`/goals/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  deleteGoal: (id: string) => request<any>(`/goals/${id}`, { method: "DELETE" }),
  createGoalContribution: (id: string, d: any, idempotencyKey?: string) =>
    request<any>(`/goals/${id}/contributions`, {
      method: "POST",
      body: JSON.stringify(d),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    }),
  // Debts
  listDebts: () => request<any[]>("/debts"),
  getDebt: (id: string) => request<any>(`/debts/${id}`),
  createDebt: (d: any) => request<any>("/debts", { method: "POST", body: JSON.stringify(d) }),
  updateDebt: (id: string, d: any) => request<any>(`/debts/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  deleteDebt: (id: string) => request<any>(`/debts/${id}`, { method: "DELETE" }),
  listDebtPayments: (id: string) => request<any[]>(`/debts/${id}/payments`),
  createDebtPayment: (d: any) => request<any>("/debt-payments", { method: "POST", body: JSON.stringify(d) }),
  deleteDebtPayment: (id: string) => request<any>(`/debt-payments/${id}`, { method: "DELETE" }),
  // Summary
  summary: () => request<any>("/summary"),
  seed: () => request<any>("/seed", { method: "POST" }),
  // Recurring payments (bills / subscriptions with due dates)
  rpOverview: (year: number, month: number) =>
    request<any>(`/recurring-payments/overview?year=${year}&month=${month}&tz_offset=${new Date().getTimezoneOffset()}`),
  rpGet: (id: string) => request<any>(`/recurring-payments/${id}?tz_offset=${new Date().getTimezoneOffset()}`),
  rpOccurrences: (id: string, offset = 0, limit = 20) =>
    request<any>(`/recurring-payments/${id}/occurrences?offset=${offset}&limit=${limit}&tz_offset=${new Date().getTimezoneOffset()}`),
  rpCandidates: (id: string, due: string) => request<any[]>(`/recurring-payments/${id}/link-candidates?due_date=${due}`),
  rpCreate: (d: any, key?: string) =>
    request<any>("/recurring-payments", { method: "POST", body: JSON.stringify(d), headers: key ? { "Idempotency-Key": key } : {} }),
  rpUpdate: (id: string, d: any) => request<any>(`/recurring-payments/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  rpAction: (id: string, action: "pause" | "resume" | "end") => request<any>(`/recurring-payments/${id}/${action}`, { method: "POST" }),
  rpDelete: (id: string) => request<any>(`/recurring-payments/${id}`, { method: "DELETE" }),
  rpPay: (id: string, d: any, key?: string) =>
    request<any>(`/recurring-payments/${id}/payments`, { method: "POST", body: JSON.stringify(d), headers: key ? { "Idempotency-Key": key } : {} }),
  rpDeletePayment: (pid: string) => request<any>(`/recurring-payments/payments/${pid}`, { method: "DELETE" }),
  // Financial calendar (read-only aggregation)
  calendarEvents: (start: string, end: string) =>
    request<any>(`/calendar/events?start=${start}&end=${end}&tz_offset=${new Date().getTimezoneOffset()}`),
  calendarSummary: (year: number, month: number) =>
    request<any>(`/calendar/summary?year=${year}&month=${month}&tz_offset=${new Date().getTimezoneOffset()}`),
  calendarUpcoming: (limit = 3, types?: string) =>
    request<any>(`/calendar/upcoming?limit=${limit}&tz_offset=${new Date().getTimezoneOffset()}${types ? `&types=${types}` : ""}`),
  // Recurring templates (config only)
  listRecurring: () => request<any[]>("/recurring"),
  createRecurring: (d: any) => request<any>("/recurring", { method: "POST", body: JSON.stringify(d) }),
  deleteRecurring: (id: string) => request<any>(`/recurring/${id}`, { method: "DELETE" }),
};
