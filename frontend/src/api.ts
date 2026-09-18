const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

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
    throw new Error(`API ${res.status}: ${text}`);
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
  createBudget: (d: any) => request<any>("/budgets", { method: "POST", body: JSON.stringify(d) }),
  updateBudget: (id: string, d: any) => request<any>(`/budgets/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  deleteBudget: (id: string) => request<any>(`/budgets/${id}`, { method: "DELETE" }),
  // Goals
  listGoals: () => request<any[]>("/goals"),
  createGoal: (d: any) => request<any>("/goals", { method: "POST", body: JSON.stringify(d) }),
  updateGoal: (id: string, d: any) => request<any>(`/goals/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  deleteGoal: (id: string) => request<any>(`/goals/${id}`, { method: "DELETE" }),
  // Debts
  listDebts: () => request<any[]>("/debts"),
  getDebt: (id: string) => request<any>(`/debts/${id}`),
  createDebt: (d: any) => request<any>("/debts", { method: "POST", body: JSON.stringify(d) }),
  updateDebt: (id: string, d: any) => request<any>(`/debts/${id}`, { method: "PUT", body: JSON.stringify(d) }),
  deleteDebt: (id: string) => request<any>(`/debts/${id}`, { method: "DELETE" }),
  listDebtPayments: (id: string) => request<any[]>(`/debts/${id}/payments`),
  createDebtPayment: (d: any) => request<any>("/debt-payments", { method: "POST", body: JSON.stringify(d) }),
  // Summary
  summary: () => request<any>("/summary"),
  seed: () => request<any>("/seed", { method: "POST" }),
  // Recurring templates (config only)
  listRecurring: () => request<any[]>("/recurring"),
  createRecurring: (d: any) => request<any>("/recurring", { method: "POST", body: JSON.stringify(d) }),
  deleteRecurring: (id: string) => request<any>(`/recurring/${id}`, { method: "DELETE" }),
};
