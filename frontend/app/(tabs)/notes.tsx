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
};

// Colors drawn from the visual family already present on Home (account cards +
// module accents): green, blue, coral, purple, orange, gold, teal.
const NOTE_COLORS = ["#126046", "#377FC4", "#D84D45", "#7546D7", "#E2763E", "#C6952C", "#176F78"];

function genId() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// First-run example notes so the screen demonstrates the design and both
// sections. They are ordinary notes — fully editable / deletable by the user.
function makeSeed(): Note[] {
  const now = Date.now();
  const iso = (minsAgo: number) => new Date(now - minsAgo * 60000).toISOString();
  return [
    { id: genId(), title: "Ideas de ahorro", content: "Revisar suscripciones y cancelar las que ya no uso este mes.", pinned: true, color: NOTE_COLORS[0], createdAt: iso(2880), updatedAt: iso(120) },
    { id: genId(), title: "Lista de compras", content: "Leche, pan, huevos, café y algo de fruta para la semana.", pinned: false, color: NOTE_COLORS[1], createdAt: iso(1440), updatedAt: iso(300) },
    { id: genId(), title: "Metas del mes", content: "Reducir gastos en restaurantes y salir a caminar más seguido.", pinned: false, color: NOTE_COLORS[2], createdAt: iso(600), updatedAt: iso(600) },
    { id: genId(), title: "Recordatorio", content: "Pagar la tarjeta antes del día 15 para evitar intereses.", pinned: false, color: NOTE_COLORS[3], createdAt: iso(240), updatedAt: iso(90) },
    { id: genId(), title: "Presupuesto viaje", content: "Estimar transporte, hospedaje y comidas para el fin de semana.", pinned: false, color: NOTE_COLORS[4], createdAt: iso(60), updatedAt: iso(30) },
  ];
}

export default function Notes() {
  const { colors, scheme } = useTheme();
  const styles = useStyles();
  const insets = useSafeAreaInsets();
  const isDark = scheme === "dark";
  const accent = isDark ? colors.brandPrimary : "#126046";
  const subColor = isDark ? colors.muted : "#68746D";

  const [notes, setNotes] = useState<Note[]>([]);
  const [query, setQuery] = useState("");
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

  const pinned = filtered.filter((n) => n.pinned);
  const others = filtered.filter((n) => !n.pinned);

  const renderCard = (note: Note) => (
    <Pressable
      key={note.id}
      testID={`note-card-${note.id}`}
      onPress={() => openEditor(note)}
      style={[styles.card, { backgroundColor: tintOf(note.color) }]}
    >
      <View style={styles.cardTop}>
        <View style={[styles.cardIcon, { backgroundColor: note.color }]}>
          <Ionicons name="document-text" size={18} color="#FFFFFF" />
        </View>
        <Pressable
          testID={`note-pin-${note.id}`}
          hitSlop={8}
          onPress={() => togglePin(note.id)}
          style={styles.pinBtn}
        >
          <Ionicons name={note.pinned ? "pin" : "pin-outline"} size={18} color={note.pinned ? note.color : subColor} />
        </Pressable>
      </View>
      <Text style={styles.cardTitle} numberOfLines={1}>{note.title}</Text>
      {note.content ? (
        <Text style={styles.cardPreview} numberOfLines={2}>{note.content}</Text>
      ) : null}
      <View style={styles.cardFooter}>
        <Ionicons name="time-outline" size={13} color={subColor} />
        <Text style={styles.cardDate}>{formatDateTime(note.updatedAt)}</Text>
      </View>
    </Pressable>
  );

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
            <Ionicons name="document-text" size={20} color={accent} />
          </View>
          <View style={{ flex: 1, marginLeft: 12 }}>
            <Text style={styles.title}>Notas</Text>
            <Text style={styles.subtitle} numberOfLines={2}>Tus notas personales, siempre a mano.</Text>
          </View>
          <Pressable testID="notes-new-btn" onPress={() => openEditor(null)} style={styles.newBtn}>
            <Ionicons name="add" size={18} color="#FFFFFF" />
            <Text style={styles.newBtnText}>Nueva</Text>
          </Pressable>
        </View>

        {/* Search */}
        <View style={styles.searchBox}>
          <Ionicons name="search" size={17} color={subColor} />
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
              <Ionicons name="close-circle" size={17} color={subColor} />
            </Pressable>
          ) : null}
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
            </View>
            {others.length > 0 ? (
              <View style={styles.cardWrap}>{others.map(renderCard)}</View>
            ) : (
              <Text style={styles.mutedRow}>{query.trim() ? "Sin resultados" : "No hay más notas"}</Text>
            )}
          </>
        )}
      </ScrollView>

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
      flexDirection: "row", alignItems: "center", gap: 8,
      marginHorizontal: spacing.lg,
      marginTop: spacing.lg,
      paddingHorizontal: 12,
      height: 44,
      backgroundColor: cardSurface,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: lineSoft,
    },
    searchInput: { flex: 1, fontSize: 14, color: titleColor, paddingVertical: 0 },

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

    // Note cards
    cardWrap: { paddingHorizontal: spacing.lg, gap: 10 },
    card: {
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: lineSoft,
      padding: 14,
      shadowColor: "#274738",
      shadowOpacity: 0.05,
      shadowRadius: 8,
      shadowOffset: { width: 0, height: 3 },
      elevation: 2,
    },
    cardTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
    cardIcon: {
      width: 38, height: 38, borderRadius: 12,
      alignItems: "center", justifyContent: "center",
    },
    pinBtn: {
      width: 30, height: 30, borderRadius: 15,
      alignItems: "center", justifyContent: "center",
    },
    cardTitle: { fontSize: 15, fontWeight: "800", color: titleColor, letterSpacing: -0.2, marginTop: 10 },
    cardPreview: { fontSize: 12.5, color: subColor, lineHeight: 17, marginTop: 3 },
    cardFooter: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 10 },
    cardDate: { fontSize: 11, color: subColor, fontWeight: "600" },

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
    confirmRow: { flexDirection: "row", alignItems: "center", gap: 10 },
    confirmText: { flex: 1, fontSize: 13.5, fontWeight: "700", color: titleColor },
    confirmCancel: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: lineSoft },
    confirmCancelText: { color: subColor, fontWeight: "700", fontSize: 13 },
    confirmDelBtn: { paddingHorizontal: 16, paddingVertical: 11, borderRadius: radius.pill, backgroundColor: colors.expenseRed },
    confirmDelText: { color: "#FFFFFF", fontWeight: "800", fontSize: 13 },
  };
});
