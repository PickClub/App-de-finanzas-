// Localised display labels for category/group canonical (English) names.
// Scoped to the Categories feature so other screens are untouched. Custom
// categories (not in the map) fall back to their stored name (e.g. "Motica").
type Label = { es: string; en: string };

const CATEGORY_LABELS: Record<string, Label> = {
  // --- Main groups ---
  "Food & Dining": { es: "Alimentación", en: "Food" },
  "Home & Housing": { es: "Vivienda", en: "Housing" },
  "Transport & Auto": { es: "Transporte", en: "Transport" },
  "Shopping & Goods": { es: "Compras", en: "Shopping" },
  "Health & Wellness": { es: "Salud", en: "Health" },
  "Entertainment & Leisure": { es: "Entretenimiento", en: "Entertainment" },
  "Finance": { es: "Finanzas", en: "Finance" },
  "Other & Misc": { es: "Otros", en: "Other" },
  "Work": { es: "Trabajo", en: "Work" },
  "Investing": { es: "Inversiones", en: "Investments" },
  "Selling": { es: "Ventas", en: "Sales" },
  "Other Earnings": { es: "Otros ingresos", en: "Other income" },

  // --- Expense subcategories ---
  "Food": { es: "Comida", en: "Food" },
  "Groceries": { es: "Supermercado", en: "Groceries" },
  "Restaurants": { es: "Restaurantes", en: "Restaurants" },
  "Housing": { es: "Vivienda", en: "Housing" },
  "Rent": { es: "Alquiler", en: "Rent" },
  "Utilities": { es: "Servicios", en: "Utilities" },
  "Transportation": { es: "Transporte", en: "Transport" },
  "Fuel": { es: "Gasolina", en: "Fuel" },
  "Car": { es: "Vehículo", en: "Car" },
  "Shopping": { es: "Compras generales", en: "Shopping" },
  "Clothing": { es: "Ropa", en: "Clothing" },
  "Electronics": { es: "Electrónica", en: "Electronics" },
  "Home": { es: "Hogar", en: "Home" },
  "Gifts": { es: "Regalos", en: "Gifts" },
  "Beauty": { es: "Belleza", en: "Beauty" },
  "Health": { es: "Salud", en: "Health" },
  "Pharmacy": { es: "Farmacia", en: "Pharmacy" },
  "Personal Care": { es: "Cuidado personal", en: "Personal care" },
  "Fitness": { es: "Fitness", en: "Fitness" },
  "Entertainment": { es: "Entretenimiento", en: "Entertainment" },
  "Subscriptions": { es: "Suscripciones", en: "Subscriptions" },
  "Travel": { es: "Viajes", en: "Travel" },
  "Taxes": { es: "Impuestos", en: "Taxes" },
  "Loans": { es: "Préstamos", en: "Loans" },
  "Credit Cards": { es: "Tarjetas de crédito", en: "Credit cards" },
  "Insurance": { es: "Seguros", en: "Insurance" },
  "Pets": { es: "Mascotas", en: "Pets" },
  "Family": { es: "Familia", en: "Family" },
  "Education": { es: "Educación", en: "Education" },
  "Technology": { es: "Tecnología", en: "Technology" },
  "Other": { es: "Otros", en: "Other" },

  // --- Income subcategories ---
  "Salary": { es: "Salario", en: "Salary" },
  "Freelance": { es: "Freelance", en: "Freelance" },
  "Business": { es: "Negocios", en: "Business" },
  "Tips": { es: "Propinas", en: "Tips" },
  "Investments": { es: "Inversiones", en: "Investments" },
  "Interest": { es: "Intereses", en: "Interest" },
  "Sales": { es: "Ventas", en: "Sales" },
  "Refunds": { es: "Reembolsos", en: "Refunds" },
  "Other Income": { es: "Otros ingresos", en: "Other income" },
};

export function catLabel(name?: string | null, lang?: string): string {
  if (!name) return "";
  const entry = CATEGORY_LABELS[name];
  if (!entry) return name; // custom categories keep their stored name
  return (lang || "es").startsWith("es") ? entry.es : entry.en;
}
