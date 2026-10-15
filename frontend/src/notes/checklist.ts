// Toggle one stored checklist marker without normalizing text, whitespace or other rows.
export function toggleChecklistLine(content: string, index: number): string | null {
  const lines = content.split("\n");
  if (!Number.isInteger(index) || index < 0 || index >= lines.length) return null;
  const marker = lines[index].match(/^([ \t]*)\[([ xX])\]/);
  if (marker) {
    const position = marker[1].length + 1;
    lines[index] = lines[index].slice(0, position) + (marker[2] === " " ? "x" : " ") + lines[index].slice(position + 1);
  } else {
    const indentation = lines[index].match(/^[ \t]*/)?.[0] || "";
    lines[index] = indentation + "[x] " + lines[index].slice(indentation.length);
  }
  return lines.join("\n");
}

// All positions come from committed onLayout events in the same scroll content.
export function itemScrollOffset(rowTop: number, rowHeight: number, viewport: number, offset: number, inset: number): number | null {
  if (![rowTop, rowHeight, viewport, offset, inset].every(Number.isFinite) || viewport <= 0 || rowHeight <= 0) return null;
  if (rowTop < offset + inset) return Math.max(0, rowTop - inset);
  if (rowTop + rowHeight > offset + viewport - inset) return Math.max(0, rowTop + rowHeight - viewport + inset);
  return null;
}
