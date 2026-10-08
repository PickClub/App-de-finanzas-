/**
 * Single shared palette (20 colors) for every user color selector
 * (accounts, debts, categories, goals).
 *
 * Order: the 10 ORIGINAL colors exactly as they existed in the app (unchanged
 * HEX), followed by 10 new distinct tones. Proposed colors that were near
 * duplicates of originals (blue, green, coral, yellow, purple, turquoise,
 * dark red, orange) were NOT added — the originals are reused instead.
 */
export const COLOR_PALETTE: readonly string[] = [
  // Originals (accounts order, then the extra category tones)
  "#4C83EA", // Azul
  "#2FA47C", // Verde
  "#FF654A", // Coral
  "#F5B83B", // Amarillo
  "#8F5BE8", // Morado
  "#29C4A9", // Turquesa
  "#D95345", // Rojo oscuro
  "#FF8A3D", // Naranja
  "#27221F", // Carbón (categorías)
  "#8E8883", // Gris (categorías)
  // New
  "#244F87", // Azul marino
  "#719B62", // Verde oliva
  "#E88DAA", // Rosa
  "#4C6E78", // Azul petróleo
  "#C7A55A", // Dorado
  "#8267B7", // Lavanda
  "#D77D59", // Terracota
  "#9A715C", // Marrón
  "#8BA59A", // Verde salvia
  "#E6B4C7", // Rosa pastel
];
