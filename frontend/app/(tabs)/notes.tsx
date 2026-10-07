import React, { useEffect, useMemo, useState, useCallback } from "react";
import {
  View,
  ScrollView,
  Modal,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import Animated, { useSharedValue, useAnimatedStyle, withTiming } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatDateTime } from "@/src/format";
import { storage } from "@/src/utils/storage";

import { us, ufs } from "@/src/ui-scale";
// Simple, text-only Notes V1. Persisted locally via the shared storage wrapper
// (AsyncStorage on native / localStorage on web). Values must be primitives, so
// the note list is stored as a JSON string. No backend / no financial data.
const STORAGE_KEY = "moneyflow.notes.v1";

type ListMode = "plain" | "check" | "ordered";
type PaletteKey = "green" | "cream" | "yellow" | "blue" | "lavender" | "coral";

type Note = {
  id: string;
  title: string;
  content: string;
  pinned: boolean;
  color: string;
  createdAt: string; // ISO
  updatedAt: string; // ISO
  icon?: string; // optional Ionicons name for the note tile
  categories?: string[]; // optional labels shown as chips
  listMode?: ListMode; // optional: renders content as a checklist / numbered list
  palette?: PaletteKey; // optional: subtle per-note card color (background + accent)
};

// Colors drawn from the visual family already present on Home (account cards +
// module accents): green, blue, coral, purple, orange, gold, teal.
const NOTE_COLORS = ["#126046", "#377FC4", "#D84D45", "#7546D7", "#E2763E", "#C6952C", "#176F78"];

// Subtle per-note palette adapted to the existing app identity (forest green +
// cream surfaces). `bg` tints ONLY the card background; `accent` reuses the
// existing note accent family for the left strip / icon tile. Both are scheme
// aware so dark mode stays subtle. Notes without a `palette` keep their
// original appearance untouched (full backward compatibility).
const NOTE_PALETTES: Record<PaletteKey, { accentLight: string; accentDark: string; bgLight: string; bgDark: string }> = {
  green: { accentLight: "#146448", accentDark: "#37C08D", bgLight: "#DCE9DD", bgDark: "#1B2A22" },
  cream: { accentLight: "#B98A34", accentDark: "#D8B25A", bgLight: "#F0E6D2", bgDark: "#2A2620" },
  yellow: { accentLight: "#C6952C", accentDark: "#E7C766", bgLight: "#F5EAC2", bgDark: "#2B2717" },
  blue: { accentLight: "#377FC4", accentDark: "#6D9BFF", bgLight: "#DAE6F3", bgDark: "#1B2432" },
  lavender: { accentLight: "#7546D7", accentDark: "#A57DFF", bgLight: "#E4DDF3", bgDark: "#241F33" },
  coral: { accentLight: "#D84D45", accentDark: "#EB6D5F", bgLight: "#F4DDD8", bgDark: "#2E1F1D" },
};
const PALETTE_ORDER: PaletteKey[] = ["green", "cream", "yellow", "blue", "lavender", "coral"];

function genId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// Parse a plain-text note body into individual items for a note-like
// presentation. Splits on line breaks first; a single-line note is broken into
// sentences. Never mutates or persists — purely a display transform, so the
// existing plain-text data model is fully preserved.
function toItems(content: string): string[] {
  if (!content) return [];
  const lines = content
    .split("\n")
    .map((s) => s.replace(/^[-•○\s]+/, "").trim())
    .filter(Boolean);
  if (lines.length > 1) return lines;
  const parts = content.split(/([.!?])\s+/);
  const sentences: string[] = [];
  for (let i = 0; i < parts.length; i += 2) {
    const seg = (parts[i] || "").trim();
    if (!seg) continue;
    const punct = parts[i + 1] || "";
    sentences.push((seg + punct).trim());
  }
  return sentences.length ? sentences : [content.trim()];
}

type ListItem = { id?: string; text: string; checked: boolean };

// Parse a note body into structured items for checklist / ordered rendering.
// Checklist lines carry an inline "[x] " / "[ ] " marker so the plain-text
// `content` field keeps holding everything (smallest safe model change).
function parseListItems(content: string, mode: ListMode): ListItem[] {
  const lines = (content || "").split("\n");
  return lines.map((raw) => {
    let line = raw.trim();
    let checked = false;
    if (mode === "check") {
      const m = line.match(/^\[( |x|X)\]\s?(.*)$/);
      if (m) {
        checked = m[1].toLowerCase() === "x";
        line = m[2];
      }
    } else if (mode === "ordered") {
      line = line.replace(/^\d+[.)]\s*/, "");
    }
    return { text: line, checked };
  });
}

// Serialize editor items back into the plain-text `content` string.
function serializeItems(items: ListItem[], mode: ListMode): string {
  const clean = items.map((i) => ({ ...i, text: i.text.trim() })).filter((i) => i.text.length > 0);
  if (mode === "check") return clean.map((i) => `${i.checked ? "[x]" : "[ ]"} ${i.text}`).join("\n");
  return clean.map((i) => i.text).join("\n");
}

// Compact "1 / 2 / 3" glyph for the ordered-list tool (Ionicons has no
// numbered-list icon, so we compose one from the existing type system).
function OrderedGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: us(20) }}>
      {[1, 2, 3].map((n) => (
        <View key={n} style={{ flexDirection: "row", alignItems: "center", marginVertical: us(1) }}>
          <Text style={{ fontSize: ufs(8), fontWeight: "800", color, width: us(7) }}>{n}</Text>
          <View style={{ height: us(2), flex: 1, borderRadius: us(1), backgroundColor: color, marginLeft: us(2) }} />
        </View>
      ))}
    </View>
  );
}

// Circular note-color swatch with a subtle scale pop on selection (reanimated —
// the project's existing animation system; ~180ms, no bounce).
function ColorSwatch({
  bg,
  border,
  selected,
  ring,
  onPress,
}: {
  bg: string;
  border: string;
  selected: boolean;
  ring: string;
  onPress: () => void;
}) {
  const s = useSharedValue(selected ? 1 : 0);
  useEffect(() => {
    s.value = withTiming(selected ? 1 : 0, { duration: 180 });
  }, [selected, s]);
  const aStyle = useAnimatedStyle(() => ({ transform: [{ scale: 1 + s.value * 0.06 }] }));
  return (
    <Pressable onPress={onPress} hitSlop={6}>
      <Animated.View
        style={[
          {
            width: us(46),
            height: us(46),
            borderRadius: us(23),
            alignItems: "center",
            justifyContent: "center",
            backgroundColor: bg,
            borderWidth: selected ? 2 : 1,
            borderColor: selected ? ring : border,
          },
          aStyle,
        ]}
      >
        {selected ? <Ionicons name="checkmark" size={us(16)} color={ring} /> : null}
      </Animated.View>
    </Pressable>
  );
}


// First-run example notes so the screen demonstrates the design and both
// sections. They are ordinary notes — fully editable / deletable by the user.
function makeSeed(): Note[] {
  const now = Date.now();
  const iso = (minsAgo: number) => new Date(now - minsAgo * 60000).toISOString();
  return [
    { id: genId(), title: "Ideas de ahorro", content: "Revisar suscripciones y cancelar las que ya no uso este mes.\nPreparar más comidas en casa.\nComparar precios antes de comprar.", pinned: true, color: NOTE_COLORS[0], icon: "bulb", categories: ["Finanzas", "Personal"], createdAt: iso(2880), updatedAt: iso(120) },
    { id: genId(), title: "Lista de compras", content: "Leche\nPan\nHuevos\nCafé\nAlgo de fruta para la semana", pinned: false, color: NOTE_COLORS[1], icon: "cart", categories: ["Compras"], createdAt: iso(1440), updatedAt: iso(300) },
    { id: genId(), title: "Metas del mes", content: "Reducir gastos en restaurantes.\nSalir a caminar más seguido.\nLeer al menos un libro.\nOrganizar mejor mi tiempo.", pinned: false, color: NOTE_COLORS[2], icon: "radio-button-on", categories: ["Metas", "Personal"], createdAt: iso(600), updatedAt: iso(600) },
    { id: genId(), title: "Recordatorio", content: "Pagar la tarjeta antes del día 15 para evitar intereses.", pinned: false, color: NOTE_COLORS[3], icon: "alarm", categories: ["Recordatorio"], createdAt: iso(240), updatedAt: iso(90) },
    { id: genId(), title: "Presupuesto viaje", content: "Estimar transporte, hospedaje y comidas para el fin de semana.", pinned: false, color: NOTE_COLORS[4], icon: "airplane", categories: ["Viaje"], createdAt: iso(60), updatedAt: iso(30) },
  ];
}

export default function Notes() {
  const { colors, scheme } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const isDark = scheme === "dark";
  const accent = isDark ? colors.brandPrimary : "#126046";
  const subColor = isDark ? colors.muted : "#68746D";
  const titleColor = isDark ? colors.onSurface : "#15251E";
  // Forest-green accent used for the editor tools / color selection ring so the
  // Notes editor stays green-theme compatible in both light and dark modes.
  const noteGreen = isDark ? "#37C08D" : "#146448";
  const editorLine = isDark ? colors.border : "rgba(39,71,56,0.10)";

  const [notes, setNotes] = useState<Note[]>([]);
  const [query, setQuery] = useState("");
  const [sortNewest, setSortNewest] = useState(true);
  const [menuNote, setMenuNote] = useState<Note | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<Note | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [draftListMode, setDraftListMode] = useState<ListMode>("plain");
  const [draftItems, setDraftItems] = useState<ListItem[]>([]);
  const [draftPalette, setDraftPalette] = useState<PaletteKey | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const noteDeleting = React.useRef(false);
  const deletedNotes = React.useRef(new Set<string>());
  const [deleteBusy, setDeleteBusy] = useState(false);

  // Load (or seed on first run).
  useEffect(() => {
    (async () => {
      const raw = await storage.getItem(STORAGE_KEY, "");
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as Note[];
          if (Array.isArray(parsed)) {
            setNotes(parsed);
            return;
          }
        } catch {
          /* fall through to seed */
        }
      }
      const seed = makeSeed();
      setNotes(seed);
      storage.setItem(STORAGE_KEY, JSON.stringify(seed));
    })();
  }, []);

  const persist = useCallback((next: Note[]) => {
    if (noteDeleting.current) return;
    const available = next.filter((note) => !deletedNotes.current.has(note.id));
    setNotes(available);
    storage.setItem(STORAGE_KEY, JSON.stringify(available));
  }, []);

  const tintOf = useCallback((c: string) => c + (isDark ? "22" : "14"), [isDark]);

  const openEditor = (note: Note | null) => {
    if (noteDeleting.current || (note && deletedNotes.current.has(note.id))) return;
    setEditing(note);
    setDraftTitle(note?.title || "");
    const mode: ListMode = note?.listMode || "plain";
    setDraftListMode(mode);
    setDraftContent(note?.content || "");
    if (mode === "plain") {
      setDraftItems([]);
    } else {
      const parsed = parseListItems(note?.content || "", mode).filter((i) => i.text.length > 0);
      setDraftItems(
        parsed.length
          ? parsed.map((p) => ({ id: genId(), ...p }))
          : [{ id: genId(), text: "", checked: false }],
      );
    }
    setDraftPalette(note ? note.palette ?? null : "green");
    setConfirmDelete(false);
    setEditorOpen(true);
  };

  // Toggle between plain / checklist / ordered. Switching seeds items from the
  // current text; turning a list off folds items back into plain content.
  const toggleListMode = (mode: ListMode) => {
    if (draftListMode === mode) {
      if (draftItems.length) setDraftContent(serializeItems(draftItems, "plain"));
      setDraftListMode("plain");
      return;
    }
    if (draftListMode === "plain") {
      const seed = draftContent.split("\n").map((s) => s.trim()).filter(Boolean);
      setDraftItems((seed.length ? seed : [""]).map((t) => ({ id: genId(), text: t, checked: false })));
    }
    setDraftListMode(mode);
  };

  const updateItemText = (id: string, text: string) =>
    setDraftItems((items) => items.map((i) => (i.id === id ? { ...i, text } : i)));
  const toggleItemCheck = (id: string) =>
    setDraftItems((items) => items.map((i) => (i.id === id ? { ...i, checked: !i.checked } : i)));
  const addItem = () => setDraftItems((items) => [...items, { id: genId(), text: "", checked: false }]);
  const removeItem = (id: string) =>
    setDraftItems((items) => (items.length > 1 ? items.filter((i) => i.id !== id) : items));

  const saveNote = () => {
    if (noteDeleting.current || (editing && deletedNotes.current.has(editing.id))) return;
    const title = draftTitle.trim();
    const content = draftListMode === "plain" ? draftContent.trim() : serializeItems(draftItems, draftListMode);
    if (!title && !content) {
      setEditorOpen(false);
      return;
    }
    const nowIso = new Date().toISOString();
    const listMode: ListMode | undefined = draftListMode === "plain" ? undefined : draftListMode;
    if (editing) {
      const palette = draftPalette ?? editing.palette;
      persist(
        notes.map((n) =>
          n.id === editing.id ? { ...n, title: title || n.title, content, listMode, palette, updatedAt: nowIso } : n,
        ),
      );
    } else {
      const color = NOTE_COLORS[notes.length % NOTE_COLORS.length];
      const newNote: Note = {
        id: genId(),
        title: title || "Sin título",
        content,
        pinned: false,
        color,
        listMode,
        palette: draftPalette ?? "green",
        createdAt: nowIso,
        updatedAt: nowIso,
      };
      persist([newNote, ...notes]);
    }
    setEditorOpen(false);
  };

  const togglePin = (id: string) => {
    persist(notes.map((n) => (n.id === id ? { ...n, pinned: !n.pinned } : n)));
  };

  const deleteNote = async (id: string) => {
    if (noteDeleting.current || deletedNotes.current.has(id)) return;
    noteDeleting.current = true;
    setDeleteBusy(true);
    try {
      const next = notes.filter((n) => n.id !== id);
      if (!await storage.setItem(STORAGE_KEY, JSON.stringify(next))) throw new Error("No se pudo guardar la eliminación de la nota.");
      deletedNotes.current.add(id);
      setNotes(next);
      setEditorOpen(false);
      setEditing(null);
      setMenuNote(null);
      setConfirmDelete(false);
    } catch (error) {
      Alert.alert("No se pudo eliminar", error instanceof Error ? error.message : "Inténtalo de nuevo.");
    } finally {
      noteDeleting.current = false;
      setDeleteBusy(false);
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return notes;
    return notes.filter((n) => n.title.toLowerCase().includes(q) || n.content.toLowerCase().includes(q));
  }, [notes, query]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const da = new Date(a.updatedAt).getTime();
      const db = new Date(b.updatedAt).getTime();
      return sortNewest ? db - da : da - db;
    });
    return arr;
  }, [filtered, sortNewest]);

  const pinned = sorted.filter((n) => n.pinned);
  const others = sorted.filter((n) => !n.pinned);

  const renderCard = (note: Note) => {
    const cats = note.categories || [];
    const icon = note.icon || "document-text";
    // Resolve per-note color: palette (if set) drives background + accent;
    // otherwise fall back to the original accent-derived look (unchanged).
    const pal = note.palette ? NOTE_PALETTES[note.palette] : null;
    const accent = pal ? (isDark ? pal.accentDark : pal.accentLight) : note.color;
    const cardBg = pal ? (isDark ? pal.bgDark : pal.bgLight) : tintOf(note.color);
    const isCheck = note.listMode === "check";
    const listItems = note.listMode ? parseListItems(note.content, note.listMode).filter((i) => i.text.length > 0) : [];
    const items = note.listMode ? [] : toItems(note.content);
    const checklist = !note.pinned; // pinned → filled bullets, others → check circles
    return (
      <Pressable
        key={note.id}
        testID={`note-card-${note.id}`}
        onPress={() => openEditor(note)}
        style={[styles.card, { backgroundColor: cardBg }]}
      >
        <View style={[styles.cardAccent, { backgroundColor: accent }]} />
        <View style={styles.cardBody}>
          <View style={styles.cardTop}>
            <View style={[styles.cardIcon, { backgroundColor: accent }]}>
              <Ionicons name={icon as any} size={us(20)} color="#FFFFFF" />
            </View>
            <Text style={styles.cardTitle}>{note.title}</Text>
            <Pressable
              testID={`note-menu-${note.id}`}
              hitSlop={8}
              onPress={() => setMenuNote(note)}
              style={styles.menuBtn}
            >
              <Ionicons name="ellipsis-vertical" size={us(18)} color={subColor} />
            </Pressable>
          </View>

          {note.listMode ? (
            listItems.length > 0 && (
              <View style={styles.itemList}>
                {listItems.slice(0, 6).map((it, idx) => (
                  <View key={idx} style={styles.itemRow}>
                    {isCheck ? (
                      <Ionicons
                        name={it.checked ? "checkbox" : "square-outline"}
                        size={us(17)}
                        color={accent}
                        style={styles.itemMark}
                      />
                    ) : (
                      <Text style={[styles.itemNum, { color: accent }]}>{idx + 1}.</Text>
                    )}
                    <Text
                      style={[styles.itemText, isCheck && it.checked && styles.itemTextDone]}
                      numberOfLines={2}
                    >
                      {it.text}
                    </Text>
                  </View>
                ))}
              </View>
            )
          ) : (
            items.length > 0 && (
              <View style={styles.itemList}>
                {items.slice(0, 6).map((it, idx) => (
                  <View key={idx} style={styles.itemRow}>
                    {checklist ? (
                      <Ionicons name="ellipse-outline" size={us(16)} color={accent} style={styles.itemMark} />
                    ) : (
                      <View style={[styles.itemDot, { backgroundColor: accent }]} />
                    )}
                    <Text style={styles.itemText} numberOfLines={2}>{it}</Text>
                  </View>
                ))}
              </View>
            )
          )}

          <View style={styles.cardFooter}>
            <View style={styles.footerLeft}>
              <Ionicons name="time-outline" size={us(13)} color={subColor} />
              <Text style={styles.cardDate}>{formatDateTime(note.updatedAt)}</Text>
            </View>
            {cats.length > 0 && (
              <View style={styles.chips}>
                {cats.slice(0, 2).map((c, i) => (
                  <View
                    key={c}
                    style={[styles.chip, i === 0 ? { backgroundColor: accent + (isDark ? "2E" : "1F") } : styles.chipNeutral]}
                  >
                    <Text style={[styles.chipText, i === 0 ? { color: accent } : styles.chipTextNeutral]}>{c}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        </View>
      </Pressable>
    );
  };

  return (
    <View style={{ flex: 1, backgroundColor: isDark ? colors.surface : "#E8EFE7" }}>
      <ScrollView
        testID="notes-scroll"
        style={{ flex: 1, backgroundColor: "transparent" }}
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(132) }}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headIconTile}>
            <Ionicons name="document-text" size={us(22)} color={accent} />
          </View>
          <View style={{ flex: 1, marginLeft: us(12) }}>
            <Text style={styles.title}>Notas</Text>
            <Text style={styles.subtitle}>Tus ideas, tareas y recuerdos en un solo lugar.</Text>
          </View>
          <Pressable testID="notes-new-btn" onPress={() => openEditor(null)} style={styles.newBtn}>
            <Ionicons name="add" size={us(18)} color="#FFFFFF" />
            <Text style={styles.newBtnText}>Nueva nota</Text>
          </Pressable>
        </View>

        {/* Search */}
        <View style={styles.searchBox}>
          <Ionicons name="search" size={us(18)} color={subColor} />
          <TextInput
            testID="notes-search"
            value={query}
            onChangeText={setQuery}
            placeholder="Buscar notas..."
            placeholderTextColor={subColor}
            style={styles.searchInput}
          />
          {query ? (
            <Pressable hitSlop={8} onPress={() => setQuery("")}>
              <Ionicons name="close-circle" size={us(18)} color={subColor} />
            </Pressable>
          ) : (
            <Ionicons name="options-outline" size={us(18)} color={subColor} />
          )}
        </View>

        {notes.length === 0 ? (
          <View style={styles.empty}>
            <View style={styles.emptyIcon}>
              <Ionicons name="document-text-outline" size={us(30)} color={accent} />
            </View>
            <Text style={styles.emptyTitle}>No tienes notas todavía</Text>
            <Text style={styles.emptySub}>Crea tu primera nota para empezar.</Text>
            <Pressable testID="notes-empty-new" onPress={() => openEditor(null)} style={styles.emptyBtn}>
              <Ionicons name="add" size={us(18)} color="#FFFFFF" />
              <Text style={styles.newBtnText}>Nueva nota</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {pinned.length > 0 && (
              <>
                <View style={styles.sectionLabel}>
                  <View style={styles.sectionChip}>
                    <Ionicons name="pin" size={us(13)} color={accent} />
                  </View>
                  <Text style={styles.sectionTitle}>Notas fijadas</Text>
                  <Text style={styles.sectionCount}>{pinned.length}</Text>
                  <View style={{ flex: 1 }} />
                  <Pressable testID="notes-ver-todas" hitSlop={6} onPress={() => setQuery("")} style={styles.verTodas}>
                    <Text style={styles.verTodasText}>Ver todas</Text>
                    <Ionicons name="chevron-forward" size={us(14)} color={subColor} />
                  </Pressable>
                </View>
                <View style={styles.cardWrap}>{pinned.map(renderCard)}</View>
              </>
            )}

            <View style={styles.sectionLabel}>
              <View style={styles.sectionChip}>
                <Ionicons name="albums-outline" size={us(13)} color={accent} />
              </View>
              <Text style={styles.sectionTitle}>Todas las notas</Text>
              <Text style={styles.sectionCount}>{others.length}</Text>
              <View style={{ flex: 1 }} />
              <Pressable testID="notes-sort" hitSlop={6} onPress={() => setSortNewest((s) => !s)} style={styles.sortPill}>
                <Text style={styles.sortText}>{sortNewest ? "Más recientes" : "Más antiguas"}</Text>
                <Ionicons name={sortNewest ? "chevron-down" : "chevron-up"} size={us(14)} color={subColor} />
              </Pressable>
            </View>
            {others.length > 0 ? (
              <View style={styles.cardWrap}>{others.map(renderCard)}</View>
            ) : (
              <Text style={styles.mutedRow}>{query.trim() ? "Sin resultados" : "No hay más notas"}</Text>
            )}
          </>
        )}
      </ScrollView>

      {/* Card action menu (three-dot) */}
      <Modal visible={!!menuNote} transparent animationType="fade" onRequestClose={() => setMenuNote(null)}>
        <Pressable style={styles.menuBackdrop} onPress={() => setMenuNote(null)} />
        <View style={[styles.menuSheet, { paddingBottom: insets.bottom + us(12) }]}>
          <View style={styles.sheetHandle} />
          <Pressable
            testID="note-menu-edit"
            style={styles.menuItem}
            onPress={() => { const n = menuNote; setMenuNote(null); if (n) openEditor(n); }}
          >
            <Ionicons name="create-outline" size={us(20)} color={titleColor} />
            <Text style={styles.menuItemText}>Editar</Text>
          </Pressable>
          <Pressable
            testID="note-menu-pin"
            style={styles.menuItem}
            onPress={() => { const n = menuNote; setMenuNote(null); if (n) togglePin(n.id); }}
          >
            <Ionicons name={menuNote?.pinned ? "pin" : "pin-outline"} size={us(20)} color={titleColor} />
            <Text style={styles.menuItemText}>{menuNote?.pinned ? "Desfijar nota" : "Fijar nota"}</Text>
          </Pressable>
          <Pressable
            testID="note-menu-delete"
            disabled={deleteBusy}
            style={styles.menuItem}
            onPress={() => { const n = menuNote; setMenuNote(null); if (n) deleteNote(n.id); }}
          >
            <Ionicons name="trash-outline" size={us(20)} color={colors.expenseRed} />
            <Text style={[styles.menuItemText, { color: colors.expenseRed }]}>Eliminar</Text>
          </Pressable>
        </View>
      </Modal>

      {/* Editor (create / edit) */}
      <Modal visible={editorOpen} transparent animationType="slide" onRequestClose={() => setEditorOpen(false)}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={{ flex: 1, justifyContent: "flex-end" }}
        >
          <Pressable style={styles.backdrop} onPress={() => setEditorOpen(false)} />
          <View style={styles.sheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHead}>
              <Text style={styles.sheetTitle}>{editing ? "Editar nota" : "Nueva nota"}</Text>
              <Pressable testID="notes-editor-close" hitSlop={8} onPress={() => setEditorOpen(false)}>
                <Ionicons name="close" size={us(22)} color={subColor} />
              </Pressable>
            </View>

            <ScrollView
              style={styles.sheetScroll}
              contentContainerStyle={styles.sheetScrollContent}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <Text style={styles.fieldLabel}>Título</Text>
              <TextInput
                testID="notes-title-input"
                value={draftTitle}
                onChangeText={setDraftTitle}
                placeholder="Título"
                placeholderTextColor={subColor}
                style={styles.titleInput}
              />

              <Text style={[styles.fieldLabel, { marginTop: us(14) }]}>Contenido</Text>
              {draftListMode === "plain" ? (
                <TextInput
                  testID="notes-content-input"
                  value={draftContent}
                  onChangeText={setDraftContent}
                  placeholder="Escribe tu nota..."
                  placeholderTextColor={subColor}
                  style={styles.contentInput}
                  multiline
                  textAlignVertical="top"
                />
              ) : (
                <View testID="notes-items-editor" style={styles.itemsEditor}>
                  {draftItems.map((it, idx) => (
                    <View key={it.id} style={styles.editRow}>
                      {draftListMode === "check" ? (
                        <Pressable
                          testID={`notes-item-check-${idx}`}
                          hitSlop={6}
                          onPress={() => it.id && toggleItemCheck(it.id)}
                          style={styles.editMark}
                        >
                          <Ionicons name={it.checked ? "checkbox" : "square-outline"} size={us(22)} color={noteGreen} />
                        </Pressable>
                      ) : (
                        <View style={styles.editMark}>
                          <Text style={[styles.editNumText, { color: noteGreen }]}>{idx + 1}.</Text>
                        </View>
                      )}
                      <TextInput
                        testID={`notes-item-input-${idx}`}
                        value={it.text}
                        onChangeText={(t) => it.id && updateItemText(it.id, t)}
                        placeholder="Elemento"
                        placeholderTextColor={subColor}
                        style={[styles.editItemInput, draftListMode === "check" && it.checked && styles.editItemDone]}
                        onSubmitEditing={addItem}
                        blurOnSubmit={false}
                        returnKeyType="next"
                      />
                      <Pressable hitSlop={6} onPress={() => it.id && removeItem(it.id)} style={styles.editRemove}>
                        <Ionicons name="close" size={us(16)} color={subColor} />
                      </Pressable>
                    </View>
                  ))}
                  <Pressable testID="notes-item-add" onPress={addItem} style={styles.addItemBtn}>
                    <Ionicons name="add" size={us(18)} color={noteGreen} />
                    <Text style={[styles.addItemText, { color: noteGreen }]}>Agregar elemento</Text>
                  </Pressable>
                </View>
              )}

              <Text style={[styles.fieldLabel, { marginTop: us(16) }]}>Herramientas</Text>
              <View style={styles.toolsRow}>
                <Pressable
                  testID="notes-tool-check"
                  onPress={() => toggleListMode("check")}
                  style={[styles.toolBtn, draftListMode === "check" && { borderColor: noteGreen, backgroundColor: noteGreen + (isDark ? "24" : "14") }]}
                >
                  <Ionicons name="checkbox-outline" size={us(18)} color={draftListMode === "check" ? noteGreen : subColor} />
                  <Text style={[styles.toolText, draftListMode === "check" && { color: noteGreen }]}>Lista de checks</Text>
                </Pressable>
                <Pressable
                  testID="notes-tool-ordered"
                  onPress={() => toggleListMode("ordered")}
                  style={[styles.toolBtn, draftListMode === "ordered" && { borderColor: noteGreen, backgroundColor: noteGreen + (isDark ? "24" : "14") }]}
                >
                  <OrderedGlyph color={draftListMode === "ordered" ? noteGreen : subColor} />
                  <Text style={[styles.toolText, draftListMode === "ordered" && { color: noteGreen }]}>Lista ordenada</Text>
                </Pressable>
              </View>

              <Text style={[styles.fieldLabel, { marginTop: us(16) }]}>Color de nota</Text>
              <View style={styles.colorRow}>
                {PALETTE_ORDER.map((key) => {
                  const p = NOTE_PALETTES[key];
                  const sel = (draftPalette ?? "green") === key;
                  return (
                    <ColorSwatch
                      key={key}
                      bg={isDark ? p.bgDark : p.bgLight}
                      border={editorLine}
                      selected={sel}
                      ring={noteGreen}
                      onPress={() => setDraftPalette(key)}
                    />
                  );
                })}
              </View>
            </ScrollView>

            {confirmDelete ? (
              <View style={styles.confirmRow}>
                <Text style={styles.confirmText}>¿Eliminar esta nota?</Text>
                <Pressable style={styles.confirmCancel} onPress={() => setConfirmDelete(false)}>
                  <Text style={styles.confirmCancelText}>Cancelar</Text>
                </Pressable>
                <Pressable
                  testID="notes-confirm-delete"
                  disabled={deleteBusy}
                  style={styles.confirmDelBtn}
                  onPress={() => editing && deleteNote(editing.id)}
                >
                  <Text style={styles.confirmDelText}>Eliminar</Text>
                </Pressable>
              </View>
            ) : (
              <View style={styles.sheetActions}>
                {editing ? (
                  <Pressable testID="notes-delete-btn" disabled={deleteBusy} style={styles.deleteBtn} onPress={() => setConfirmDelete(true)}>
                    <Ionicons name="trash-outline" size={us(18)} color={colors.expenseRed} />
                    <Text style={styles.deleteText}>Eliminar</Text>
                  </Pressable>
                ) : (
                  <View />
                )}
                <Pressable testID="notes-save-btn" style={styles.saveBtn} onPress={saveNote}>
                  <Ionicons name="checkmark" size={us(18)} color="#FFFFFF" />
                  <Text style={styles.saveText}>Guardar</Text>
                </Pressable>
              </View>
            )}
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((colors, scheme) => {
  const isDark = scheme === "dark";
  // Values reused/derived from the existing Home screen palette (light mode).
  const cardSurface = isDark ? colors.surfaceSecondary : "#FCFCF8";
  const lineSoft = isDark ? colors.border : "rgba(39,71,56,0.10)";
  const tileGreen = isDark ? colors.brandPrimary + "1A" : "#DCE9DD";
  const titleColor = isDark ? colors.onSurface : "#15251E";
  const subColor = isDark ? colors.muted : "#68746D";
  return {
    header: {
      flexDirection: "row",
      alignItems: "center",
      paddingHorizontal: spacing.lg,
      marginTop: spacing.sm,
    },
    headIconTile: {
      width: 44, height: 44, borderRadius: 14,
      backgroundColor: tileGreen,
      alignItems: "center", justifyContent: "center",
    },
    title: { fontSize: 22, fontWeight: "800", color: titleColor, letterSpacing: -0.4 },
    subtitle: { fontSize: 12.5, color: subColor, marginTop: 1 },
    newBtn: {
      flexDirection: "row", alignItems: "center", gap: 4,
      backgroundColor: isDark ? colors.brandPrimary : "#146448",
      paddingHorizontal: 12, paddingVertical: 9,
      borderRadius: radius.pill,
    },
    newBtnText: { color: "#FFFFFF", fontWeight: "800", fontSize: 12.5 },

    // Search
    searchBox: {
      flexDirection: "row", alignItems: "center", gap: 10,
      marginHorizontal: spacing.lg,
      marginTop: spacing.lg,
      paddingHorizontal: 16,
      height: 52,
      backgroundColor: isDark ? colors.surfaceSecondary : "#FFFFFF",
      borderRadius: 18,
      borderWidth: 1,
      borderColor: isDark ? colors.border : "rgba(39,71,56,0.08)",
    },
    searchInput: { flex: 1, fontSize: 15, color: titleColor, paddingVertical: 0 },

    // Section labels (Home section-header language, compact)
    sectionLabel: {
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
      paddingHorizontal: spacing.lg,
      marginTop: spacing.xl,
      marginBottom: spacing.sm,
    },
    sectionChip: {
      width: 26, height: 26, borderRadius: 9,
      backgroundColor: tileGreen,
      alignItems: "center", justifyContent: "center",
    },
    sectionTitle: { fontSize: 16, fontWeight: "800", color: titleColor, letterSpacing: -0.3 },
    sectionCount: { fontSize: 12.5, fontWeight: "700", color: subColor, marginLeft: 2 },
    verTodas: {
      flexDirection: "row", alignItems: "center", gap: 2,
      paddingHorizontal: 12, paddingVertical: 6,
      borderRadius: radius.pill,
      backgroundColor: isDark ? colors.surfaceSecondary : "#FFFFFF",
      borderWidth: 1, borderColor: isDark ? colors.border : "rgba(39,71,56,0.08)",
    },
    verTodasText: { fontSize: 12.5, fontWeight: "700", color: subColor },
    sortPill: {
      flexDirection: "row", alignItems: "center", gap: 3,
      paddingHorizontal: 12, paddingVertical: 6,
      borderRadius: radius.pill,
      backgroundColor: isDark ? colors.surfaceSecondary : "#FFFFFF",
      borderWidth: 1, borderColor: isDark ? colors.border : "rgba(39,71,56,0.08)",
    },
    sortText: { fontSize: 12.5, fontWeight: "700", color: subColor },

    // Note cards — note-like pastel surface with a colored left accent strip.
    cardWrap: { paddingHorizontal: spacing.lg, gap: 14 },
    card: {
      flexDirection: "row",
      borderRadius: radius.lg,
      overflow: "hidden",
      backgroundColor: cardSurface,
    },
    cardAccent: { width: 5, alignSelf: "stretch" },
    cardBody: { flex: 1, paddingVertical: 14, paddingHorizontal: 14 },
    cardTop: { flexDirection: "row", alignItems: "center", gap: 12 },
    cardIcon: {
      width: 40, height: 40, borderRadius: 12,
      alignItems: "center", justifyContent: "center",
    },
    cardTitle: { flex: 1, fontSize: 16.5, fontWeight: "800", color: titleColor, letterSpacing: -0.2 },
    menuBtn: {
      width: 28, height: 28, borderRadius: 14,
      alignItems: "center", justifyContent: "center",
    },
    itemList: { marginTop: 12, gap: 7 },
    itemRow: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
    itemDot: { width: 8, height: 8, borderRadius: 4, marginTop: 6, marginLeft: 3 },
    itemMark: { marginTop: 1 },
    itemNum: { fontSize: 13.5, fontWeight: "800", lineHeight: 20, minWidth: 16 },
    itemText: { flex: 1, fontSize: 14, color: titleColor, lineHeight: 20 },
    itemTextDone: { textDecorationLine: "line-through", color: subColor },
    cardFooter: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 14, gap: 8 },
    footerLeft: { flexDirection: "row", alignItems: "center", gap: 5 },
    cardDate: { fontSize: 12, color: subColor, fontWeight: "600" },
    chips: { flexDirection: "row", alignItems: "center", gap: 6, flexShrink: 1, flexWrap: "wrap", justifyContent: "flex-end" },
    chip: { paddingHorizontal: 11, paddingVertical: 5, borderRadius: radius.pill },
    chipNeutral: { backgroundColor: isDark ? "rgba(255,255,255,0.08)" : "rgba(39,71,56,0.07)" },
    chipText: { fontSize: 11.5, fontWeight: "700" },
    chipTextNeutral: { color: subColor },

    mutedRow: { color: subColor, fontSize: 13, paddingHorizontal: spacing.lg, paddingVertical: 6 },

    // Empty state
    empty: {
      alignItems: "center",
      marginTop: spacing.xxl,
      marginHorizontal: spacing.lg,
      paddingVertical: spacing.xxl,
      paddingHorizontal: spacing.lg,
      backgroundColor: cardSurface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: lineSoft,
    },
    emptyIcon: {
      width: 60, height: 60, borderRadius: 20,
      backgroundColor: tileGreen,
      alignItems: "center", justifyContent: "center",
      marginBottom: 14,
    },
    emptyTitle: { fontSize: 16, fontWeight: "800", color: titleColor },
    emptySub: { fontSize: 12.5, color: subColor, marginTop: 4, textAlign: "center" },
    emptyBtn: {
      flexDirection: "row", alignItems: "center", gap: 5,
      backgroundColor: isDark ? colors.brandPrimary : "#146448",
      paddingHorizontal: 16, paddingVertical: 11,
      borderRadius: radius.pill,
      marginTop: 16,
    },

    // Editor sheet
    backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)" },
    sheet: {
      backgroundColor: isDark ? colors.surfaceSecondary : "#FCFCF8",
      borderTopLeftRadius: radius.cardLg,
      borderTopRightRadius: radius.cardLg,
      paddingHorizontal: 20,
      paddingTop: 10,
      paddingBottom: 28,
      maxHeight: "90%",
    },
    sheetScroll: { flexGrow: 0, flexShrink: 1 },
    sheetScrollContent: { paddingBottom: 4 },
    fieldLabel: { fontSize: 13, fontWeight: "800", color: subColor, marginBottom: 8, letterSpacing: 0.1 },
    sheetHandle: { alignSelf: "center", width: 44, height: 4, borderRadius: 2, backgroundColor: lineSoft, marginBottom: 12 },
    sheetHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
    sheetTitle: { fontSize: 18, fontWeight: "800", color: titleColor, letterSpacing: -0.3 },
    titleInput: {
      fontSize: 16, fontWeight: "700", color: titleColor,
      backgroundColor: isDark ? colors.surface : "#FFFFFF",
      borderWidth: 1, borderColor: lineSoft, borderRadius: radius.md,
      paddingHorizontal: 12, paddingVertical: 12,
    },
    contentInput: {
      fontSize: 14, color: titleColor,
      backgroundColor: isDark ? colors.surface : "#FFFFFF",
      borderWidth: 1, borderColor: lineSoft, borderRadius: radius.md,
      paddingHorizontal: 12, paddingVertical: 12,
      minHeight: 112,
    },

    // Checklist / ordered-list editor (inside the note sheet, no new screen)
    itemsEditor: {
      backgroundColor: isDark ? colors.surface : "#FFFFFF",
      borderWidth: 1, borderColor: lineSoft, borderRadius: radius.md,
      paddingHorizontal: 10, paddingVertical: 6, minHeight: 112,
    },
    editRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 3 },
    editMark: { width: 26, alignItems: "center", justifyContent: "center" },
    editNumText: { fontSize: 14, fontWeight: "800" },
    editItemInput: { flex: 1, fontSize: 14, color: titleColor, paddingVertical: 6 },
    editItemDone: { textDecorationLine: "line-through", color: subColor },
    editRemove: { width: 24, alignItems: "center", justifyContent: "center" },
    addItemBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 8, paddingHorizontal: 4, marginTop: 2 },
    addItemText: { fontSize: 13, fontWeight: "700" },

    // Herramientas (two compact rounded tools)
    toolsRow: { flexDirection: "row", gap: 12 },
    toolBtn: {
      flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
      paddingVertical: 13, paddingHorizontal: 10,
      borderRadius: radius.md, borderWidth: 1, borderColor: lineSoft,
      backgroundColor: isDark ? colors.surface : "#FFFFFF",
    },
    toolText: { fontSize: 13, fontWeight: "700", color: subColor },

    // Color de nota
    colorRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },

    sheetActions: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 16 },
    deleteBtn: {
      flexDirection: "row", alignItems: "center", gap: 5,
      paddingHorizontal: 14, paddingVertical: 11,
      borderRadius: radius.pill,
      backgroundColor: colors.expenseRed + (isDark ? "24" : "16"),
    },
    deleteText: { color: colors.expenseRed, fontWeight: "800", fontSize: 13 },
    saveBtn: {
      flexDirection: "row", alignItems: "center", gap: 5,
      backgroundColor: isDark ? colors.brandPrimary : "#146448",
      paddingHorizontal: 20, paddingVertical: 11,
      borderRadius: radius.pill,
    },
    saveText: { color: "#FFFFFF", fontWeight: "800", fontSize: 13.5 },

    // Card action menu (three-dot)
    menuBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.35)" },
    menuSheet: {
      position: "absolute", left: 0, right: 0, bottom: 0,
      backgroundColor: isDark ? colors.surfaceSecondary : "#FCFCF8",
      borderTopLeftRadius: radius.cardLg,
      borderTopRightRadius: radius.cardLg,
      paddingHorizontal: 12, paddingTop: 10,
    },
    menuItem: {
      flexDirection: "row", alignItems: "center", gap: 14,
      paddingHorizontal: 14, paddingVertical: 15,
      borderRadius: radius.md,
    },
    menuItemText: { fontSize: 15.5, fontWeight: "700", color: titleColor },
    confirmRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 16 },
    confirmText: { flex: 1, fontSize: 13.5, fontWeight: "700", color: titleColor },
    confirmCancel: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: lineSoft },
    confirmCancelText: { color: subColor, fontWeight: "700", fontSize: 13 },
    confirmDelBtn: { paddingHorizontal: 16, paddingVertical: 11, borderRadius: radius.pill, backgroundColor: colors.expenseRed },
    confirmDelText: { color: "#FFFFFF", fontWeight: "800", fontSize: 13 },
  };
});
