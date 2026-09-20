// Shared, visual-only color helper.
// `premiumizeColor` takes any stored hex/rgb color (e.g. a category or account
// color chosen by the user / seed) and returns a deeper, slightly desaturated
// tone in the SAME hue family so every accent harmonizes with the forest-green
// premium palette. The original stored value is never modified — this is a
// pure display transform.

export type Scheme = "light" | "dark";

function parseRgb(input: string) {
  const rgbMatch = input.match(/rgba?\(([^)]+)\)/i);
  if (rgbMatch) {
    const [r, g, b] = rgbMatch[1].split(",").map((v) => parseInt(v.trim(), 10));
    return { r: r || 0, g: g || 0, b: b || 0 };
  }
  let h = input.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = parseInt(h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function rgbToHsl(r: number, g: number, b: number) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0;
  const l = (max + min) / 2;
  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (d !== 0) {
    switch (max) {
      case r: h = ((g - b) / d) % 6; break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4; break;
    }
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s, l };
}

function hslToRgbString(h: number, s: number, l: number) {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  let r = 0, g = 0, b = 0;
  if (h < 60) { r = c; g = x; }
  else if (h < 120) { r = x; g = c; }
  else if (h < 180) { g = c; b = x; }
  else if (h < 240) { g = x; b = c; }
  else if (h < 300) { r = x; b = c; }
  else { r = c; b = x; }
  const to = (v: number) => Math.round((v + m) * 255);
  return `rgb(${to(r)},${to(g)},${to(b)})`;
}

export function premiumizeColor(hex: string, scheme: Scheme) {
  try {
    const { r, g, b } = parseRgb(hex);
    const { h, s } = rgbToHsl(r, g, b);
    const ns = Math.max(0.3, Math.min(0.55, s * 0.72));
    const nl = scheme === "dark" ? 0.44 : 0.34;
    return hslToRgbString(h, ns, nl);
  } catch {
    return hex;
  }
}
