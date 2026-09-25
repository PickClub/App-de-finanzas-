import React, { useEffect, useMemo, useState, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  Pressable,
  TextInput,
  Modal,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatDateTime } from "@/src/format";
import { storage } from "@/src/utils/storage";

// Simple, text-only Notes V1. Persisted locally via the shared storage wrapper
// (AsyncStorage on native / localStorage on web). Values must be primitives, so
// the note list is stored as a JSON string. No backend / no financial data.
const STORAGE_KEY = "moneyflow.notes.v1";

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
};

// Colors drawn from the visual family already present on Home (account cards +
// module accents): green, blue, coral, purple, orange, gold, teal.
const NOTE_COLORS = ["#126046", "#377FC4", "#D84D45", "#7546D7", "#E2763E", "#C6952C", "#176F78"];

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

  const [notes, setNotes] = useState<Note[]>([]);
  const [query, setQuery] = useState("");
  const [sortNewest, setSortNewest] = useState(true);
  const [menuNote, setMenuNote] = useState<Note | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<Note | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

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
    setNotes(next);
    storage.setItem(STORAGE_KEY, JSON.stringify(next));
  }, []);

  const tintOf = useCallback((c: string) => c + (isDark ? "22" : "14"), [isDark]);

  const openEditor = (note: Note | null) => {
    setEditing(note);
    setDraftTitle(note?.title || "");
    setDraftContent(note?.content || "");
    setConfirmDelete(false);
    setEditorOpen(true);
  };

  const saveNote = () => {
    const title = draftTitle.trim();
    const content = draftContent.trim();
    if (!title && !content) {
      setEditorOpen(false);
      return;
    }
    const nowIso = new Date().toISOString();
    if (editing) {
      persist(notes.map((n) => (n.id === editing.id ? { ...n, title: title || n.title, content, updatedAt: nowIso } : n)));
    } else {
      const color = NOTE_COLORS[notes.length % NOTE_COLORS.length];
      const newNote: Note = {
        id: genId(),
        title: title || "Sin título",
        content,
        pinned: false,
        color,
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

  const deleteNote = (id: string) => {
    persist(notes.filter((n) => n.id !== id));
    setEditorOpen(false);
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
    const items = toItems(note.content);
    const checklist = !note.pinned; // pinned → filled bullets, others → check circles
    const cats = note.categories || [];
    const icon = note.icon || "document-text";
    return (
      <Pressable
        key={note.id}
        testID={`note-card-${note.id}`}
        onPress={() => openEditor(note)}
        style={[styles.card, { backgroundColor: tintOf(note.color) }]}
      >
        <View style={[styles.cardAccent, { backgroundColor: note.color }]} />
        <View style={styles.cardBody}>
          <View style={styles.cardTop}>
            <View style={[styles.cardIcon, { backgroundColor: note.color }]}>
              <Ionicons name={icon as any} size={20} color="#FFFFFF" />
            </View>
            <Text style={styles.cardTitle} numberOfLines={1}>{note.title}</Text>
            <Pressable
              testID={`note-menu-${note.id}`}
              hitSlop={8}
              onPress={() => setMenuNote(note)}
              style={styles.menuBtn}
            >
              <Ionicons name="ellipsis-vertical" size={18} color={subColor} />
            </Pressable>
          </View>

          {items.length > 0 && (
            <View style={styles.itemList}>
              {items.slice(0, 6).map((it, idx) => (
                <View key={idx} style={styles.itemRow}>
                  {checklist ? (
                    <Ionicons name="ellipse-outline" size={16} color={note.color} style={styles.itemMark} />
                  ) : (
                    <View style={[styles.itemDot, { backgroundColor: note.color }]} />
                  )}
                  <Text style={styles.itemText} numberOfLines={2}>{it}</Text>
                </View>
              ))}
            </View>
          )}

          <View style={styles.cardFooter}>
            <View style={styles.footerLeft}>
              <Ionicons name="time-outline" size={13} color={subColor} />
              <Text style={styles.cardDate}>{formatDateTime(note.updatedAt)}</Text>
            </View>
            {cats.length > 0 && (
              <View style={styles.chips}>
                {cats.slice(0, 2).map((c, i) => (
                  <View
                    key={c}
                    style={[styles.chip, i === 0 ? { backgroundColor: note.color + (isDark ? "2E" : "1F") } : styles.chipNeutral]}
                  >
                    <Text style={[styles.chipText, i === 0 ? { color: note.color } : styles.chipTextNeutral]}>{c}</Text>
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
        contentContainerStyle={{ paddingTop: insets.top + 8, paddingBottom: 132 }}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headIconTile}>
            <Ionicons name="document-text" size={22} color={accent} />
          </View>
          <View style={{ flex: 1, marginLeft: 12 }}>
            <Text style={styles.title}>Notas</Text>
            <Text style={styles.subtitle} numberOfLines={2}>Tus ideas, tareas y recuerdos en un solo lugar.</Text>
          </View>
          <Pressable testID="notes-new-btn" onPress={() => openEditor(null)} style={styles.newBtn}>
            <Ionicons name="add" size={18} color="#FFFFFF" />
            <Text style={styles.newBtnText}>Nueva nota</Text>
          </Pressable>
        </View>

        {/* Search */}
        <View style={styles.searchBox}>
          <Ionicons name="search" size={18} color={subColor} />
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
              <Ionicons name="close-circle" size={18} color={subColor} />
            </Pressable>
          ) : (
            <Ionicons name="options-outline" size={18} color={subColor} />
          )}
        </View>

        {notes.length === 0 ? (
          <View style={styles.empty}>
            <View style={styles.emptyIcon}>
              <Ionicons name="document-text-outline" size={30} color={accent} />
            </View>
            <Text style={styles.emptyTitle}>No tienes notas todavía</Text>
            <Text style={styles.emptySub}>Crea tu primera nota para empezar.</Text>
            <Pressable testID="notes-empty-new" onPress={() => openEditor(null)} style={styles.emptyBtn}>
              <Ionicons name="add" size={18} color="#FFFFFF" />
              <Text style={styles.newBtnText}>Nueva nota</Text>
            </Pressable>
          </View>
        ) : (
          <>
            {pinned.length > 0 && (
              <>
                <View style={styles.sectionLabel}>
                  <View style={styles.sectionChip}>
                    <Ionicons name="pin" size={13} color={accent} />
                  </View>
                  <Text style={styles.sectionTitle}>Notas fijadas</Text>
                  <Text style={styles.sectionCount}>{pinned.length}</Text>
                  <View style={{ flex: 1 }} />
                  <Pressable testID="notes-ver-todas" hitSlop={6} onPress={() => setQuery("")} style={styles.verTodas}>
                    <Text style={styles.verTodasText}>Ver todas</Text>
                    <Ionicons name="chevron-forward" size={14} color={subColor} />
                  </Pressable>
                </View>
                <View style={styles.cardWrap}>{pinned.map(renderCard)}</View>
              </>
            )}

            <View style={styles.sectionLabel}>
              <View style={styles.sectionChip}>
                <Ionicons name="albums-outline" size={13} color={accent} />
              </View>
              <Text style={styles.sectionTitle}>Todas las notas</Text>
              <Text style={styles.sectionCount}>{others.length}</Text>
              <View style={{ flex: 1 }} />
              <Pressable testID="notes-sort" hitSlop={6} onPress={() => setSortNewest((s) => !s)} style={styles.sortPill}>
                <Text style={styles.sortText}>{sortNewest ? "Más recientes" : "Más antiguas"}</Text>
                <Ionicons name={sortNewest ? "chevron-down" : "chevron-up"} size={14} color={subColor} />
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
        <View style={[styles.menuSheet, { paddingBottom: insets.bottom + 12 }]}>
          <View style={styles.sheetHandle} />
          <Pressable
            testID="note-menu-edit"
            style={styles.menuItem}
            onPress={() => { const n = menuNote; setMenuNote(null); if (n) openEditor(n); }}
          >
            <Ionicons name="create-outline" size={20} color={titleColor} />
            <Text style={styles.menuItemText}>Editar</Text>
          </Pressable>
          <Pressable
            testID="note-menu-pin"
            style={styles.menuItem}
            onPress={() => { const n = menuNote; setMenuNote(null); if (n) togglePin(n.id); }}
          >
            <Ionicons name={menuNote?.pinned ? "pin" : "pin-outline"} size={20} color={titleColor} />
            <Text style={styles.menuItemText}>{menuNote?.pinned ? "Desfijar nota" : "Fijar nota"}</Text>
          </Pressable>
          <Pressable
            testID="note-menu-delete"
            style={styles.menuItem}
            onPress={() => { const n = menuNote; setMenuNote(null); if (n) deleteNote(n.id); }}
          >
            <Ionicons name="trash-outline" size={20} color={colors.expenseRed} />
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
                <Ionicons name="close" size={22} color={subColor} />
              </Pressable>
            </View>

            <TextInput
              testID="notes-title-input"
              value={draftTitle}
              onChangeText={setDraftTitle}
              placeholder="Título"
              placeholderTextColor={subColor}
              style={styles.titleInput}
            />
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

            {confirmDelete ? (
              <View style={styles.confirmRow}>
                <Text style={styles.confirmText}>¿Eliminar esta nota?</Text>
                <Pressable style={styles.confirmCancel} onPress={() => setConfirmDelete(false)}>
                  <Text style={styles.confirmCancelText}>Cancelar</Text>
                </Pressable>
                <Pressable
                  testID="notes-confirm-delete"
                  style={styles.confirmDelBtn}
                  onPress={() => editing && deleteNote(editing.id)}
                >
                  <Text style={styles.confirmDelText}>Eliminar</Text>
                </Pressable>
              </View>
            ) : (
              <View style={styles.sheetActions}>
                {editing ? (
                  <Pressable testID="notes-delete-btn" style={styles.deleteBtn} onPress={() => setConfirmDelete(true)}>
                    <Ionicons name="trash-outline" size={18} color={colors.expenseRed} />
                    <Text style={styles.deleteText}>Eliminar</Text>
                  </Pressable>
                ) : (
                  <View />
                )}
                <Pressable testID="notes-save-btn" style={styles.saveBtn} onPress={saveNote}>
                  <Ionicons name="checkmark" size={18} color="#FFFFFF" />
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
    itemText: { flex: 1, fontSize: 14, color: titleColor, lineHeight: 20 },
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
    },
    sheetHandle: { alignSelf: "center", width: 44, height: 4, borderRadius: 2, backgroundColor: lineSoft, marginBottom: 12 },
    sheetHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
    sheetTitle: { fontSize: 18, fontWeight: "800", color: titleColor, letterSpacing: -0.3 },
    titleInput: {
      fontSize: 16, fontWeight: "700", color: titleColor,
      backgroundColor: isDark ? colors.surface : "#FFFFFF",
      borderWidth: 1, borderColor: lineSoft, borderRadius: radius.md,
      paddingHorizontal: 12, paddingVertical: 12,
      marginBottom: 10,
    },
    contentInput: {
      fontSize: 14, color: titleColor,
      backgroundColor: isDark ? colors.surface : "#FFFFFF",
      borderWidth: 1, borderColor: lineSoft, borderRadius: radius.md,
      paddingHorizontal: 12, paddingVertical: 12,
      minHeight: 130, marginBottom: 14,
    },
    sheetActions: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
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
    confirmRow: { flexDirection: "row", alignItems: "center", gap: 10 },
    confirmText: { flex: 1, fontSize: 13.5, fontWeight: "700", color: titleColor },
    confirmCancel: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: lineSoft },
    confirmCancelText: { color: subColor, fontWeight: "700", fontSize: 13 },
    confirmDelBtn: { paddingHorizontal: 16, paddingVertical: 11, borderRadius: radius.pill, backgroundColor: colors.expenseRed },
    confirmDelText: { color: "#FFFFFF", fontWeight: "800", fontSize: 13 },
  };
});
