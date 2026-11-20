/** First-session catalog setup. Existing user categories are never reorganized. */
type Category = { id: string };
type CatalogPort = {
  read(): Promise<Category[]>;
  initialize(): Promise<unknown>;
  assertCurrent(): void;
};

export async function ensureCategoryCatalog(port: CatalogPort): Promise<void> {
  port.assertCurrent();
  const categories = await port.read();
  port.assertCurrent();
  if (!Array.isArray(categories)) throw new Error("Invalid category response");
  if (categories.length > 0) return;
  await port.initialize();
  port.assertCurrent();
  const initialized = await port.read();
  port.assertCurrent();
  if (!Array.isArray(initialized) || initialized.length === 0) {
    throw new Error("Category initialization did not provide a catalog");
  }
}
