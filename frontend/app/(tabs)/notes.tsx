import { toggleChecklistLine, itemScrollOffset } from "@/src/notes/checklist";
import { noteLimitViolation, noteTextLength, type NoteDraft } from "@/src/notes/limits";
import { localizedError } from "@/src/i18n/errors";
import { tr, useTranslation as useInterfaceLanguage } from "@/src/i18n";
import { ElasticScrollView } from "@/src/components/elastic-scroll-view";
import { NATIVE_VERTICAL_SCROLL } from "@/src/native-scroll";
import { MoneyFlowHeaderActions } from "@/src/components/header-actions";
import { useRouter } from "expo-router";
import React, { useEffect, useMemo, useState, useCallback } from "react";
import {
  View,
  ScrollView,
  Modal,
  KeyboardAvoidingView,
  Platform,
  TextInput as NativeTextInput,
} from "react-native";
import { Pressable } from "@/src/components/pressable";
import { Text, TextInput } from "@/src/components/typography";
import Ionicons from "@react-native-vector-icons/ionicons";
import Animated, { useSharedValue, useAnimatedStyle, withTiming } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme, makeStyles, radius, spacing } from "@/src/theme";
import { formatDateTime } from "@/src/format";
import { useFonts } from "expo-font";
import { storage } from "@/src/utils/storage";
import { Alert, ContextActionsTrigger } from "@/src/components/interaction-system";

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

// Stable per-row refs are registered only after commit, never while rendering.
function NoteItemInput({ itemId, onReady, ...props }: React.ComponentProps<typeof TextInput> & {
  itemId: string; onReady: (id: string, input: NativeTextInput | null) => void;
}) {
  const input = React.useRef<NativeTextInput>(null);
  useEffect(() => {
    if (input.current) onReady(itemId, input.current);
    return () => onReady(itemId, null);
  }, [itemId, onReady]);
  return <NativeTextInput {...props} ref={input} />;
}

type NotePreviewBlock = { kind: ListMode; text: string; checked?: boolean; number?: number };

// Preview only: list metadata authorizes markers; paragraphs never create them.
function notePreviewBlocks(note: Note): NotePreviewBlock[] {
  const mode = note.listMode;
  if (mode !== "check" && mode !== "ordered") {
    return note.content ? [{ kind: "plain", text: note.content.slice(0, 720) }] : [];
  }
  const marker = mode === "check" ? /^\s*\[([ xX])\]\s?(.*)$/ : /^\s*(\d+)[.)]\s+(.*)$/;
  const hasExplicitMarkers = note.content.split("\n").some(line => marker.test(line));
  return note.content.split("\n", 3).map((line, index): NotePreviewBlock => {
    const match = line.match(marker);
    // Legacy notes may have only a whole-note listMode; keep that explicit metadata.
    if (!match && hasExplicitMarkers) return { kind: "plain", text: line.slice(0, 240) };
    return {
      kind: mode,
      text: (match ? match[2] : line.trim()).slice(0, 240),
      checked: mode === "check" && !!match && match[1].toLowerCase() === "x",
      number: mode === "ordered" && match ? Number(match[1]) : index + 1,
    };
  }).filter(block => block.text.trim().length > 0);
}

type ListItem = { id?: string; text: string; checked: boolean; originalLength?: number };

// Compare editable fields only; generated row IDs and legacy length allowances are not changes.
const editorDraftSignature = (draft: { title: string; content: string; mode: ListMode; items: ListItem[]; palette: PaletteKey | null }) => JSON.stringify({
  title: draft.title,
  content: draft.mode === "plain" ? draft.content : "",
  mode: draft.mode,
  items: draft.mode === "plain" ? [] : draft.items.map(({ text, checked }) => ({ text, checked })),
  palette: draft.palette,
});

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
function OrderedGlyph({ color, fontFamily }: { color: string; fontFamily?: string }) {
  return (
    <View style={{ width: us(20) }}>
      {[1, 2, 3].map((n) => (
        <View key={n} style={{ flexDirection: "row", alignItems: "center", marginVertical: us(1) }}>
          <Text style={{ fontSize: ufs(8), fontWeight: "800", fontFamily, color, width: us(7) }}>{n}</Text>
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
    { id: genId(), title: tr("notes.samples.savingTitle"), content: tr("notes.samples.savingBody"), pinned: true, color: NOTE_COLORS[0], icon: "bulb", categories: [tr("notes.sampleTags.finance"), tr("notes.sampleTags.personal")], createdAt: iso(2880), updatedAt: iso(120) },
    { id: genId(), title: tr("notes.samples.shoppingTitle"), content: tr("notes.samples.shoppingBody"), pinned: false, color: NOTE_COLORS[1], icon: "cart", categories: [tr("notes.sampleTags.shopping")], createdAt: iso(1440), updatedAt: iso(300) },
    { id: genId(), title: tr("notes.samples.goalsTitle"), content: tr("notes.samples.goalsBody"), pinned: false, color: NOTE_COLORS[2], icon: "radio-button-on", categories: [tr("notes.sampleTags.goals"), tr("notes.sampleTags.personal")], createdAt: iso(600), updatedAt: iso(600) },
    { id: genId(), title: tr("notes.samples.reminderTitle"), content: tr("notes.samples.reminderBody"), pinned: false, color: NOTE_COLORS[3], icon: "alarm", categories: [tr("notes.sampleTags.reminder")], createdAt: iso(240), updatedAt: iso(90) },
    { id: genId(), title: tr("notes.samples.travelTitle"), content: tr("notes.samples.travelBody"), pinned: false, color: NOTE_COLORS[4], icon: "airplane", categories: [tr("notes.sampleTags.travel")], createdAt: iso(60), updatedAt: iso(30) },
  ];
}

export default function Notes() {
  useInterfaceLanguage();
  const router = useRouter();
  const [editorFontsReady] = useFonts({
    NoteMontserrat: require("../../assets/fonts/Montserrat-Bold.ttf"),
    NoteMontserratRegular: require("../../assets/fonts/Montserrat-Regular.ttf"),
  });
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
  const [previewNote, setPreviewNote] = useState<Note | null>(null);
  const lastLimitNotice = React.useRef(0);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<Note | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [draftListMode, setDraftListMode] = useState<ListMode>("plain");
  const [draftItems, setDraftItems] = useState<ListItem[]>([]);
  const [draftPalette, setDraftPalette] = useState<PaletteKey | null>(null);
  const noteDeleting = React.useRef(false);
  // One gate for save/pin/delete; the ref survives stale event closures.
  const confirmedNotes = React.useRef<Note[]>([]);
  const notesReady = React.useRef(false);
  const saveComplete = React.useRef(false);
  const editorSnapshot = React.useRef({ signature: "", revision: 0, active: false });
  const discardPrompt = React.useRef(false);
  const deletedNotes = React.useRef(new Set<string>());
  const [deleteBusy, setDeleteBusy] = useState(false);
  const editorScroll = React.useRef<ScrollView>(null);
  const itemInputs = React.useRef(new Map<string, NativeTextInput>());
  const pendingItemFocus = React.useRef<{ id: string; revision: number } | null>(null);
  const focusedItem = React.useRef<string | null>(null);
  const submittedItem = React.useRef<string | null>(null);
  const itemLayouts = React.useRef(new Map<string, { y: number; height: number }>());
  const scrollLayout = React.useRef({ origin: 0, height: 0, offset: 0, ready: false });

  const revealItem = useCallback((id: string) => {
    if (!editorSnapshot.current.active) return;
    const row = itemLayouts.current.get(id), view = scrollLayout.current;
    if (!row || !view.ready) return;
    const offset = itemScrollOffset(view.origin + row.y, row.height, view.height, view.offset, us(12));
    if (offset !== null) editorScroll.current?.scrollTo({ y: offset, animated: true });
  }, []);
  const itemInputReady = useCallback((id: string, input: NativeTextInput | null) => {
    if (!input) { itemInputs.current.delete(id); itemLayouts.current.delete(id); return; }
    itemInputs.current.set(id, input);
    const pending = pendingItemFocus.current;
    if (!pending || pending.id !== id || pending.revision !== editorSnapshot.current.revision || !editorSnapshot.current.active) return;
    pendingItemFocus.current = null;
    focusedItem.current = id;
    input.focus();
    input.setNativeProps({ selection: { start: 0, end: 0 } });
    revealItem(id);
  }, [revealItem]);


  // Load (or seed on first run).
  useEffect(() => {
    (async () => {
      const raw = await storage.getItem(STORAGE_KEY, "");
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as Note[];
          if (Array.isArray(parsed)) {
            confirmedNotes.current = parsed;
            setNotes(parsed);
            notesReady.current = true;
            return;
          }
        } catch {
          /* fall through to seed */
        }
      }
      const seed = makeSeed();
      try {
        if (await storage.setItem(STORAGE_KEY, JSON.stringify(seed)) !== true) throw new Error("No se pudieron guardar las notas iniciales.");
        confirmedNotes.current = seed;
        setNotes(seed);
      } catch {
        Alert.alert(tr("ui.could_not_save_notes"), tr("ui.storage_is_unavailable_please_try_again"));
      } finally {
        notesReady.current = true;
      }
    })();
  }, []);

  const persist = useCallback(async (next: Note[]) => {
    const available = next.filter((note) => !deletedNotes.current.has(note.id));
    if (await storage.setItem(STORAGE_KEY, JSON.stringify(available)) !== true) throw new Error("No se pudo guardar la nota. Tu borrador se conserva; vuelve a pulsar Guardar.");
    confirmedNotes.current = available;
    setNotes(available);
  }, []);

  const tintOf = useCallback((c: string) => c + (isDark ? "22" : "14"), [isDark]);

  const openEditor = (note: Note | null) => {
    if (!notesReady.current || noteDeleting.current || (note && deletedNotes.current.has(note.id))) return;
    saveComplete.current = false;
    pendingItemFocus.current = null;
    focusedItem.current = null;
    submittedItem.current = null;
    itemInputs.current.clear();
    itemLayouts.current.clear();
    scrollLayout.current = { origin: 0, height: 0, offset: 0, ready: false };
    setEditing(note);
    setDraftTitle(note?.title || "");
    const mode: ListMode = note?.listMode || "plain";
    setDraftListMode(mode);
    setDraftContent(note?.content || "");
    const parsed = mode === "plain" ? [] : parseListItems(note?.content || "", mode).filter((i) => i.text.length > 0);
    const items = mode === "plain" ? [] : parsed.length
      ? parsed.map((p) => ({ id: genId(), ...p, originalLength: noteTextLength(p.text) }))
      : [{ id: genId(), text: "", checked: false }];
    const palette = note ? note.palette ?? null : "green";
    setDraftItems(items);
    setDraftPalette(palette);
    editorSnapshot.current = {
      revision: editorSnapshot.current.revision + 1,
      active: true,
      signature: editorDraftSignature({ title: note?.title || "", content: note?.content || "", mode, items, palette }),
    };
    discardPrompt.current = false;
    setEditorOpen(true);
  };

  // Every close path uses the same guard. Confirmations belong to one editor visit.
  const closeEditor = () => {
    if (noteDeleting.current || discardPrompt.current) return;
    const revision = editorSnapshot.current.revision;
    const discard = () => {
      if (revision !== editorSnapshot.current.revision || noteDeleting.current) return;
      discardPrompt.current = false;
      editorSnapshot.current.active = false;
      pendingItemFocus.current = null;
      focusedItem.current = null;
      submittedItem.current = null;
      setDraftTitle("");
      setDraftContent("");
      setDraftListMode("plain");
      setDraftItems([]);
      setDraftPalette(null);
      setEditing(null);
      setEditorOpen(false);
    };
    const current = editorDraftSignature({ title: draftTitle, content: draftContent, mode: draftListMode, items: draftItems, palette: draftPalette });
    if (editing && current !== editorSnapshot.current.signature) {
      discardPrompt.current = true;
      const keepEditing = () => { if (revision === editorSnapshot.current.revision) discardPrompt.current = false; };
      Alert.alert(tr("notes.editor.discardTitle"), tr("notes.editor.discardMessage"), [
        { text: tr("ui.cancel"), style: "cancel", onPress: keepEditing },
        { text: tr("notes.editor.discardAction"), style: "destructive", onPress: discard },
      ], { cancelable: true, onDismiss: keepEditing });
      return;
    }
    discard();
  };

  const validateDraft = (changes: Partial<NoteDraft> = {}) => {
    const violation = noteLimitViolation({ title: draftTitle, content: draftContent, mode: draftListMode, items: draftItems, ...changes }, editing);
    if (!violation) return true;
    const now = Date.now();
    if (now - lastLimitNotice.current > 2000) {
      lastLimitNotice.current = now;
      Alert.alert(tr("notes.limits.heading"), tr(`notes.limits.${violation}`));
    }
    return false;
  };
  const changeTitle = (title: string) => { if (validateDraft({ title })) setDraftTitle(title); };
  const changeContent = (content: string) => { if (validateDraft({ content })) setDraftContent(content); };

  // Toggle between plain / checklist / ordered. Switching seeds items from the
  // current text; turning a list off folds items back into plain content.
  const toggleListMode = (mode: ListMode) => {
    if (draftListMode === mode) {
      const content = draftItems.length ? serializeItems(draftItems, "plain") : draftContent;
      if (!validateDraft({ mode: "plain", content })) return;
      if (draftItems.length) setDraftContent(content);
      setDraftListMode("plain");
      return;
    }
    if (draftListMode === "plain") {
      const seed = draftContent.split("\n").map((s) => s.trim()).filter(Boolean);
      const items = (seed.length ? seed : [""]).map((t) => ({ id: genId(), text: t, checked: false }));
      if (!validateDraft({ mode, items })) return;
      setDraftItems(items);
    }
    setDraftListMode(mode);
  };

  const updateItemText = (id: string, text: string) => {
    const items = draftItems.map((i) => i.id === id ? { ...i, text } : i);
    if (validateDraft({ items })) {
      if (submittedItem.current === id) submittedItem.current = null;
      setDraftItems(items);
    }
  };
  const toggleItemCheck = (id: string) =>
    setDraftItems((items) => items.map((i) => (i.id === id ? { ...i, checked: !i.checked } : i)));
  const addItem = (afterId?: string) => {
    if (!editorSnapshot.current.active || noteDeleting.current || pendingItemFocus.current) return false;
    const position = afterId ? draftItems.findIndex(item => item.id === afterId) : draftItems.length - 1;
    if (afterId && position < 0) return false;
    const item = { id: genId(), text: "", checked: false };
    const items = [...draftItems.slice(0, position + 1), item, ...draftItems.slice(position + 1)];
    if (!validateDraft({ items })) return false;
    pendingItemFocus.current = { id: item.id, revision: editorSnapshot.current.revision };
    setDraftItems(items);
    return true;
  };
  const submitItem = (id: string) => {
    if (submittedItem.current === id) return;
    if (addItem(id)) submittedItem.current = id;
  };
  const removeItem = (id: string) =>
    setDraftItems((items) => (items.length > 1 ? items.filter((i) => i.id !== id) : items));

  const saveNote = async () => {
    if (!notesReady.current || !editorSnapshot.current.active || saveComplete.current || noteDeleting.current || discardPrompt.current || (editing && deletedNotes.current.has(editing.id))) return;
    if (!validateDraft()) return;
    const title = draftTitle.trim();
    const content = draftListMode === "plain" ? draftContent.trim() : serializeItems(draftItems, draftListMode);
    if (!title && !content) {
      editorSnapshot.current.active = false;
      setEditorOpen(false);
      return;
    }
    noteDeleting.current = true;
    setDeleteBusy(true);
    try {
      const current = confirmedNotes.current;
      const nowIso = new Date().toISOString();
      const listMode: ListMode | undefined = draftListMode === "plain" ? undefined : draftListMode;
      if (editing) {
        const palette = draftPalette ?? editing.palette;
        await persist(
          current.map((n) =>
            n.id === editing.id ? { ...n, title: title || n.title, content, listMode, palette, updatedAt: nowIso } : n,
          ),
        );
      } else {
        const color = NOTE_COLORS[current.length % NOTE_COLORS.length];
        const newNote: Note = {
          id: genId(),
          title: title || tr("ui.untitled"),
          content,
          pinned: false,
          color,
          listMode,
          palette: draftPalette ?? "green",
          createdAt: nowIso,
          updatedAt: nowIso,
        };
        await persist([newNote, ...current]);
      }
      saveComplete.current = true;
      editorSnapshot.current.active = false;
      setEditorOpen(false);
    } catch {
      Alert.alert(tr("ui.could_not_save"), tr("ui.your_draft_is_safe_check_storage_and_tap_save_again"));
    } finally {
      noteDeleting.current = false;
      setDeleteBusy(false);
    }
  };

  const togglePin = async (id: string) => {
    if (!notesReady.current || noteDeleting.current || deletedNotes.current.has(id)) return;
    noteDeleting.current = true;
    setDeleteBusy(true);
    try {
      await persist(confirmedNotes.current.map((n) => (n.id === id ? { ...n, pinned: !n.pinned } : n)));
    } catch {
      Alert.alert(tr("ui.could_not_pin_note"), tr("ui.the_change_was_not_saved_please_try_again"));
    } finally {
      noteDeleting.current = false;
      setDeleteBusy(false);
    }
  };

  const deleteNote = async (id: string) => {
    if (noteDeleting.current || deletedNotes.current.has(id)) return;
    noteDeleting.current = true;
    setDeleteBusy(true);
    try {
      const next = confirmedNotes.current.filter((n) => n.id !== id);
      if (await storage.setItem(STORAGE_KEY, JSON.stringify(next)) !== true) throw new Error("No se pudo guardar la eliminación de la nota.");
      deletedNotes.current.add(id);
      setPreviewNote(null);
      confirmedNotes.current = next;
      setNotes(next);
      setEditorOpen(false);
      setEditing(null);
    } catch (error) {
      Alert.alert(tr("ui.could_not_delete"), localizedError(error instanceof Error ? error.message : tr("ui.please_try_again")));
    } finally {
      noteDeleting.current = false;
      setDeleteBusy(false);
    }
  };

  const togglePreviewItem = async (index: number) => {
    if (!previewNote || noteDeleting.current || deletedNotes.current.has(previewNote.id)) return;
    const current = confirmedNotes.current;
    const note = current.find(item => item.id === previewNote.id);
    if (!note || note.listMode !== "check") return;
    const content = toggleChecklistLine(note.content, index);
    if (content === null) return;
    noteDeleting.current = true;
    setDeleteBusy(true);
    try {
      const updated = { ...note, content, updatedAt: new Date().toISOString() };
      await persist(current.map(item => item.id === note.id ? updated : item));
      setPreviewNote(visible => visible?.id === note.id ? updated : visible);
    } catch {
      Alert.alert(tr("ui.could_not_save"), tr("notes.preview.checkSaveFailed"));
    } finally {
      noteDeleting.current = false;
      setDeleteBusy(false);
    }
  };

  const requestPreviewDelete = () => {
    if (!previewNote || noteDeleting.current) return;
    const id = previewNote.id;
    Alert.alert(tr("ui.delete_this_note"), tr("notes.preview.deleteMessage"), [
      { text: tr("ui.cancel"), style: "cancel" },
      { text: tr("ui.delete"), style: "destructive", onPress: () => deleteNote(id) },
    ]);
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
    const blocks = notePreviewBlocks(note);
    const isList = note.listMode === "check" || note.listMode === "ordered";
    return (
      <Pressable
        key={note.id}
        testID={`note-card-${note.id}`}
        onPress={() => { if (!noteDeleting.current) setPreviewNote(note); }}
        style={[styles.card, { backgroundColor: cardBg }]}
      >
        <View style={[styles.cardAccent, { backgroundColor: accent }]} />
        <View style={styles.cardBody}>
          <View style={styles.cardTop}>
            <View style={[styles.cardIcon, { backgroundColor: accent }]}>
              <Ionicons name={icon as any} size={us(20)} color="#FFFFFF" />
            </View>
            <Text style={styles.cardTitle}>{note.title}</Text>
            <ContextActionsTrigger
              testID={`note-menu-${note.id}`}
              style={styles.menuBtn}
              iconColor={subColor}
              iconSize={us(18)}
              disabled={deleteBusy}
              actions={[
                { id: "edit", label: tr("ui.edit"), icon: "create-outline", onPress: () => openEditor(note) },
                { id: "pin", label: note.pinned ? tr("ui.unpin_note") : tr("ui.pin_note"), icon: note.pinned ? "pin" : "pin-outline", onPress: () => togglePin(note.id) },
                { id: "delete", label: tr("ui.delete"), icon: "trash-outline", destructive: true, onPress: () => Alert.alert(tr("ui.delete_this_note"), tr("notes.preview.deleteMessage"), [
                  { text: tr("ui.cancel"), style: "cancel" },
                  { text: tr("ui.delete"), style: "destructive", onPress: () => deleteNote(note.id) },
                ]) },
              ]}
            />
          </View>

          {blocks.length > 0 && (
            <View style={styles.itemList}>
              {blocks.map((block, index) => block.kind === "plain" ? (
                <View key={index} style={styles.itemRow}>
                  <Text style={styles.itemText} numberOfLines={isList ? 1 : 3}>{block.text}</Text>
                </View>
              ) : (
                <View key={index} style={styles.itemRow}>
                  {block.kind === "check" ? (
                    <Ionicons name={block.checked ? "checkbox" : "square-outline"} size={us(17)} color={accent} style={styles.itemMark} />
                  ) : (
                    <Text style={[styles.itemNum, { color: accent }]}>{block.number}.</Text>
                  )}
                  <Text style={[styles.itemText, block.kind === "check" && block.checked && styles.itemTextDone]} numberOfLines={1}>{block.text}</Text>
                </View>
              ))}
            </View>
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
      <ElasticScrollView {...NATIVE_VERTICAL_SCROLL}
        testID="notes-scroll"
        style={{ flex: 1, backgroundColor: "transparent" }}
        contentContainerStyle={{ paddingTop: insets.top + us(8), paddingBottom: us(132) }}
        keyboardShouldPersistTaps="handled"
      >
        {/* Header */}
        <View style={styles.header}>
          <MoneyFlowHeaderActions
            onBack={() => router.back()}
            backTestID="notes-back"
            title={
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={styles.title} numberOfLines={1}>{tr("ui.notes")}</Text>
                <Text style={styles.subtitle}>{tr("ui.your_ideas_tasks_and_reminders_in_one_place")}</Text>
              </View>
            }
            beforeActions={
              <Pressable testID="notes-new-btn" onPress={() => openEditor(null)} style={styles.newBtn}>
                <Ionicons name="add" size={us(18)} color="#FFFFFF" />
                <Text style={styles.newBtnText}>{tr("ui.new_note")}</Text>
              </Pressable>
            }
          />
        </View>

        {/* Search */}
        <View style={styles.searchBox}>
          <Ionicons name="search" size={us(18)} color={subColor} />
          <TextInput
            testID="notes-search"
            value={query}
            onChangeText={setQuery}
            placeholder={tr("ui.search_notes")}
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
            <Text style={styles.emptyTitle}>{tr("ui.no_notes_yet")}</Text>
            <Text style={styles.emptySub}>{tr("ui.create_your_first_note_to_get_started")}</Text>
            <Pressable testID="notes-empty-new" onPress={() => openEditor(null)} style={styles.emptyBtn}>
              <Ionicons name="add" size={us(18)} color="#FFFFFF" />
              <Text style={styles.newBtnText}>{tr("ui.new_note")}</Text>
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
                  <Text style={styles.sectionTitle}>{tr("ui.pinned_notes")}</Text>
                  <Text style={styles.sectionCount}>{pinned.length}</Text>
                  <View style={{ flex: 1 }} />
                  <Pressable testID="notes-ver-todas" hitSlop={6} onPress={() => setQuery("")} style={styles.verTodas}>
                    <Text style={styles.verTodasText}>{tr("ui.view_all")}</Text>
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
              <Text style={styles.sectionTitle}>{tr("ui.all_notes")}</Text>
              <Text style={styles.sectionCount}>{others.length}</Text>
              <View style={{ flex: 1 }} />
              <Pressable testID="notes-sort" hitSlop={6} onPress={() => setSortNewest((s) => !s)} style={styles.sortPill}>
                <Text style={styles.sortText}>{sortNewest ? tr("ui.most_recent") : tr("ui.oldest")}</Text>
                <Ionicons name={sortNewest ? "chevron-down" : "chevron-up"} size={us(14)} color={subColor} />
              </Pressable>
            </View>
            {others.length > 0 ? (
              <View style={styles.cardWrap}>{others.map(renderCard)}</View>
            ) : (
              <Text style={styles.mutedRow}>{query.trim() ? tr("ui.no_results") : tr("ui.no_more_notes")}</Text>
            )}
          </>
        )}
      </ElasticScrollView>

      <Modal visible={!!previewNote} transparent animationType="fade" onRequestClose={() => setPreviewNote(null)}>
        <View style={[styles.editorHost, styles.createHost, { paddingTop: insets.top, paddingBottom: insets.bottom }]}>
          <Pressable testID="notes-preview-backdrop" accessible={false} style={[styles.editorBackdrop, styles.createBackdrop]} onPress={() => setPreviewNote(null)} />
          {previewNote ? (
            <View testID="notes-preview-card" accessibilityViewIsModal style={[styles.sheet, styles.createCard]}>
              <View style={styles.previewHeader}>
                <View style={styles.previewIcon}>
                  <Ionicons name={(previewNote.icon || "document-text") as any} size={us(22)} color={noteGreen} />
                </View>
                <View style={styles.previewButtons}>
                  <ContextActionsTrigger testID="notes-preview-actions" accessibilityLabel={tr("ui.more_options")} disabled={deleteBusy} style={styles.previewButton} iconColor={noteGreen} iconSize={us(18)} actions={[
                    { id: "edit", label: tr("ui.edit_note"), icon: "create-outline", onPress: () => { const note = previewNote; setPreviewNote(null); openEditor(note); } },
                    { id: "pin", label: previewNote.pinned ? tr("ui.unpin_note") : tr("ui.pin_note"), icon: previewNote.pinned ? "pin" : "pin-outline", onPress: () => togglePin(previewNote.id) },
                    { id: "delete", label: tr("ui.delete"), icon: "trash-outline", destructive: true, onPress: requestPreviewDelete },
                  ]} />
                  <Pressable testID="notes-preview-close" accessibilityRole="button" accessibilityLabel={tr("common.close")} style={styles.previewButton} onPress={() => setPreviewNote(null)}>
                    <Ionicons name="close" size={us(20)} color={noteGreen} />
                  </Pressable>
                </View>
              </View>
              <Text testID="notes-preview-title" style={[styles.previewTitle, editorFontsReady && styles.editorFont]}>{previewNote.title}</Text>
              <Text testID="notes-preview-date" style={[styles.cardDate, editorFontsReady && styles.editorFont]}>{formatDateTime(previewNote.updatedAt)}</Text>
              <View style={styles.previewDivider} />
              <ScrollView testID="notes-preview-content" style={styles.sheetScroll} showsVerticalScrollIndicator={false} bounces={false} overScrollMode="never" contentContainerStyle={styles.sheetScrollContent}>
                {previewNote.listMode && previewNote.listMode !== "plain" ? parseListItems(previewNote.content, previewNote.listMode).map((item, index) => (
                  <View key={index} style={styles.itemRow}>
                    {previewNote.listMode === "check" ? <Pressable testID={`notes-preview-check-${index}`} accessibilityRole="checkbox" accessibilityLabel={item.text || tr("ui.item")} accessibilityState={{ checked: item.checked, disabled: deleteBusy }} disabled={deleteBusy} onPress={() => togglePreviewItem(index)} style={styles.editMark}>
                      <Ionicons name={item.checked ? "checkbox" : "square-outline"} size={us(18)} color={previewNote.palette ? NOTE_PALETTES[previewNote.palette][isDark ? "accentDark" : "accentLight"] : previewNote.color} />
                    </Pressable>
                      : <Text style={[styles.itemNum, editorFontsReady && styles.editorFont]}>{index + 1}.</Text>}
                    <Text style={[styles.itemText, editorFontsReady && styles.editorRegularFont, item.checked && styles.itemTextDone]}>{item.text}</Text>
                  </View>
                )) : <Text testID="notes-preview-text" style={[styles.itemText, editorFontsReady && styles.editorRegularFont]}>{previewNote.content}</Text>}
              </ScrollView>
            </View>
          ) : null}
        </View>
      </Modal>

      {/* Editor (create / edit) */}
      <Modal visible={editorOpen} transparent animationType="fade" onRequestClose={() => closeEditor()}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : "height"}
          style={[styles.editorHost, styles.createHost, { paddingTop: insets.top, paddingBottom: insets.bottom }]}
        >
          <Pressable testID="notes-editor-backdrop" accessible={false} style={[styles.editorBackdrop, styles.createBackdrop]} onPress={() => closeEditor()} />
          <View testID="notes-editor-card" accessibilityViewIsModal style={[styles.sheet, styles.createCard]} pointerEvents={deleteBusy ? "none" : "auto"}>
            <View style={styles.sheetHead}>
              <Text style={[styles.sheetTitle, editorFontsReady && styles.editorFont]}>{editing ? tr("ui.edit_note") : tr("ui.new_note")}</Text>
              <View style={styles.previewButtons}>
                {editing ? (
                  <Pressable testID="notes-editor-save" accessibilityRole="button" accessibilityLabel={tr("ui.save")} disabled={deleteBusy} style={[styles.previewButton, { backgroundColor: noteGreen }]} onPress={saveNote}>
                    <Ionicons name="checkmark" size={us(18)} color="#FFFFFF" />
                  </Pressable>
                ) : null}
                <Pressable testID="notes-editor-close" disabled={deleteBusy} style={styles.previewButton} accessibilityLabel={tr("common.close")} accessibilityRole="button" onPress={() => closeEditor()}>
                  <Ionicons name="close" size={us(20)} color={noteGreen} />
                </Pressable>
              </View>
            </View>

            <ScrollView
              ref={editorScroll}
              onLayout={event => { scrollLayout.current.height = event.nativeEvent.layout.height; if (focusedItem.current) revealItem(focusedItem.current); }}
              onScroll={event => { scrollLayout.current.offset = event.nativeEvent.contentOffset.y; }}
              scrollEventThrottle={16}
              onContentSizeChange={() => { if (focusedItem.current) revealItem(focusedItem.current); }}
              style={styles.sheetScroll}
              contentContainerStyle={styles.sheetScrollContent}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <Text style={[styles.fieldLabel, editorFontsReady && styles.editorFont]}>{tr("ui.title")}</Text>
              <TextInput
                testID="notes-title-input"
                editable={!deleteBusy}
                value={draftTitle}
                onChangeText={changeTitle}
                placeholder={tr("ui.title")}
                placeholderTextColor={subColor}
                style={[styles.titleInput, editorFontsReady && styles.editorFont]}
              />

              <View style={styles.toolsRow}>
                <Pressable
                  testID="notes-tool-check"
                  accessibilityRole="button"
                  accessibilityLabel={tr("ui.checklist")}
                  accessibilityState={{ selected: draftListMode === "check" }}
                  onPress={() => toggleListMode("check")}
                  style={[styles.toolBtn, draftListMode === "check" && { backgroundColor: noteGreen }]}
                >
                  <Ionicons name="checkbox-outline" size={us(18)} color={draftListMode === "check" ? "#FFFFFF" : noteGreen} />
                </Pressable>
                <Pressable
                  testID="notes-tool-ordered"
                  accessibilityRole="button"
                  accessibilityLabel={tr("ui.numbered_list")}
                  accessibilityState={{ selected: draftListMode === "ordered" }}
                  onPress={() => toggleListMode("ordered")}
                  style={[styles.toolBtn, draftListMode === "ordered" && { backgroundColor: noteGreen }]}
                >
                  <OrderedGlyph fontFamily={editorFontsReady ? "NoteMontserrat" : undefined} color={draftListMode === "ordered" ? "#FFFFFF" : noteGreen} />
                </Pressable>
              </View>

              <Text style={[styles.fieldLabel, editorFontsReady && styles.editorFont, { marginTop: us(14) }]}>{tr("ui.content")}</Text>
              {draftListMode === "plain" ? (
                <TextInput
                  testID="notes-content-input"
                  editable={!deleteBusy}
                  value={draftContent}
                  onChangeText={changeContent}
                  placeholder={tr("ui.write_your_note")}
                  placeholderTextColor={subColor}
                  style={[styles.contentInput, editorFontsReady && styles.editorRegularFont]}
                  multiline
                  textAlignVertical="top"
                />
              ) : (
                <View testID="notes-items-editor" style={styles.itemsEditor} onLayout={event => { scrollLayout.current.origin = event.nativeEvent.layout.y; scrollLayout.current.ready = true; if (focusedItem.current) revealItem(focusedItem.current); }}>
                  {draftItems.map((it, idx) => (
                    <View key={it.id} style={styles.editRow} onLayout={event => { if (it.id) { itemLayouts.current.set(it.id, { y: event.nativeEvent.layout.y, height: event.nativeEvent.layout.height }); if (focusedItem.current === it.id) revealItem(it.id); } }}>
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
                          <Text style={[styles.editNumText, editorFontsReady && styles.editorFont, { color: noteGreen }]}>{idx + 1}.</Text>
                        </View>
                      )}
                      <NoteItemInput
                        itemId={it.id!}
                        onReady={itemInputReady}
                        onFocus={() => { focusedItem.current = it.id!; if (submittedItem.current === it.id) submittedItem.current = null; revealItem(it.id!); }}
                        testID={`notes-item-input-${idx}`}
                        editable={!deleteBusy}
                        value={it.text}
                        onChangeText={(t) => it.id && updateItemText(it.id, t)}
                        placeholder={tr("ui.item")}
                        placeholderTextColor={subColor}
                        style={[styles.editItemInput, editorFontsReady && styles.editorRegularFont, draftListMode === "check" && it.checked && styles.editItemDone]}
                        onSubmitEditing={() => it.id && submitItem(it.id)}
                        submitBehavior="submit"
                        blurOnSubmit={false}
                        returnKeyType="next"
                      />
                      <Pressable hitSlop={6} onPress={() => it.id && removeItem(it.id)} style={styles.editRemove}>
                        <Ionicons name="close" size={us(16)} color={subColor} />
                      </Pressable>
                    </View>
                  ))}
                  <Pressable testID="notes-item-add" onPress={() => addItem()} style={styles.addItemBtn}>
                    <Ionicons name="add" size={us(18)} color={noteGreen} />
                    <Text style={[styles.addItemText, editorFontsReady && styles.editorFont, { color: noteGreen }]}>{tr("ui.add_item")}</Text>
                  </Pressable>
                </View>
              )}


              <Text style={[styles.fieldLabel, editorFontsReady && styles.editorFont, { marginTop: us(16) }]}>{tr("ui.note_color")}</Text>
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

            {!editing ? (
              <View style={styles.sheetActions}>
                <Pressable testID="notes-cancel-btn" accessibilityRole="button" style={styles.createCancel} onPress={() => closeEditor()}>
                  <Text style={[styles.createCancelText, editorFontsReady && styles.editorFont]}>{tr("ui.cancel")}</Text>
                </Pressable>
                <Pressable testID="notes-save-btn" style={[styles.saveBtn, styles.createSave]} onPress={saveNote}>
                  <Ionicons name="checkmark" size={us(18)} color="#FFFFFF" />
                  <Text style={[styles.saveText, editorFontsReady && styles.editorFont]}>{tr("ui.save")}</Text>
                </Pressable>
              </View>
            ) : null}
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

    previewHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 14 },
    previewIcon: { width: 40, height: 40, borderRadius: radius.md, alignItems: "center", justifyContent: "center", backgroundColor: isDark ? "#37C08D1A" : tileGreen },
    previewButtons: { flexDirection: "row", gap: 12 },
    previewButton: { width: 36, height: 36, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: isDark ? "#37C08D1A" : tileGreen },
    previewTitle: { fontSize: 18, fontWeight: "600", color: titleColor, marginBottom: 8 },
    previewDivider: { height: 1, backgroundColor: lineSoft, marginVertical: 14 },
    editorHost: { flex: 1 },
    createHost: { justifyContent: "center", alignItems: "center" },
    editorBackdrop: { position: "absolute", top: 0, bottom: 0, left: 0, right: 0, backgroundColor: "rgba(0,0,0,0.35)" },
    createBackdrop: { backgroundColor: "rgba(0,0,0,0.18)" },
    createCard: {
      width: "90%", maxHeight: "75%", borderRadius: radius.cardLg,
      paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.lg, borderWidth: 1, borderColor: lineSoft,
      shadowColor: "#000000", shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.08, shadowRadius: 6, elevation: 2,
    },
    editorFont: { fontFamily: "NoteMontserrat" },
    editorRegularFont: { fontFamily: "NoteMontserratRegular", fontWeight: "400" },
    createCancel: { flex: 1, alignItems: "center", justifyContent: "center", minHeight: 44, backgroundColor: isDark ? "#37C08D1A" : tileGreen, borderRadius: radius.md, paddingHorizontal: 16 },
    createCancelText: { color: isDark ? "#37C08D" : "#146448", fontWeight: "700", fontSize: 13.5 },
    createSave: { flex: 1, justifyContent: "center", minHeight: 44, backgroundColor: "#146448", borderRadius: radius.md },
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
    toolsRow: { flexDirection: "row", gap: 12, marginTop: 12 },
    toolBtn: {
      width: 36, height: 36, alignItems: "center", justifyContent: "center",
      borderRadius: radius.md, backgroundColor: isDark ? "#37C08D1A" : tileGreen,
    },
    toolText: { fontSize: 13, fontWeight: "700", color: subColor },

    // Color de nota
    colorRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },

    sheetActions: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 16 },
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

    confirmRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 16 },
    confirmText: { flex: 1, fontSize: 13.5, fontWeight: "700", color: titleColor },
    confirmCancel: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: lineSoft },
    confirmCancelText: { color: subColor, fontWeight: "700", fontSize: 13 },
    confirmDelBtn: { paddingHorizontal: 16, paddingVertical: 11, borderRadius: radius.pill, backgroundColor: colors.expenseRed },
    confirmDelText: { color: "#FFFFFF", fontWeight: "800", fontSize: 13 },
  };
});
