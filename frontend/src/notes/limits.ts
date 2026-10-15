// Presentation/input limits only. Stored notes are never migrated or truncated.
export const NOTE_LIMITS = { title: 80, content: 5000, items: 50, item: 200 } as const;
export type NoteListMode = "plain" | "check" | "ordered";
export type DraftItem = { text: string; originalLength?: number };
export type NoteDraft = { title: string; content: string; mode: NoteListMode; items: DraftItem[] };
type OriginalNote = { title: string; content: string; listMode?: NoteListMode };
export type NoteLimit = keyof typeof NOTE_LIMITS;

// Count Unicode characters rather than cutting UTF-16 surrogate pairs.
export function noteTextLength(value: string): number {
  return Array.from(value).length;
}

export function noteLimitViolation(draft: NoteDraft, original?: OriginalNote | null): NoteLimit | null {
  if (noteTextLength(draft.title) > Math.max(NOTE_LIMITS.title, noteTextLength(original?.title || ""))) return "title";
  if (draft.mode === "plain") {
    if (noteTextLength(draft.content) > Math.max(NOTE_LIMITS.content, noteTextLength(original?.content || ""))) return "content";
  } else {
    const originalItems = original?.listMode && original.listMode !== "plain"
      ? original.content.split("\n").filter(line => line.trim()).length : 0;
    if (draft.items.length > Math.max(NOTE_LIMITS.items, originalItems)) return "items";
    if (draft.items.some(item => noteTextLength(item.text) > Math.max(NOTE_LIMITS.item, item.originalLength || 0))) return "item";
  }
  return null;
}
