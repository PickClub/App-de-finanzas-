import AsyncStorage from "@react-native-async-storage/async-storage";
import { authGeneration, privateSession } from "./auth-session";

let cached: { epoch: number; journal: ReturnType<typeof buildJournal> } | undefined;
let writeTail: Promise<unknown> = Promise.resolve();

function serialize<T>(work: () => Promise<T>): Promise<T> {
  const pending = writeTail.catch(() => {}).then(work);
  writeTail = pending;
  return pending;
}

const deletionMarker = "moneyflow:deleted-journal:";
const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const privateNamespace = new RegExp(`^moneyflow:r3:${uuid}:${uuid}:$`);

async function purge(namespace: string) {
  const keys = (await AsyncStorage.getAllKeys()).filter(key => key.startsWith(namespace));
  if (keys.length) await AsyncStorage.multiRemove(keys);
  await AsyncStorage.removeItem(deletionMarker + namespace);
}

export function erasePrivateJournal(namespace: string): Promise<void> {
  return serialize(async () => {
    if (!privateNamespace.test(namespace)) throw new Error("Invalid journal namespace");
    await AsyncStorage.setItem(deletionMarker + namespace, "1");
    await purge(namespace);
  });
}

export function resumeDeletedJournals(): Promise<void> {
  return serialize(async () => {
    for (const key of await AsyncStorage.getAllKeys()) {
      if (!key.startsWith(deletionMarker)) continue;
      const namespace = key.slice(deletionMarker.length);
      if (privateNamespace.test(namespace)) await purge(namespace);
    }
  });
}

export function privateJournal() {
  const epoch = authGeneration();
  if (cached?.epoch !== epoch) cached = { epoch, journal: buildJournal() };
  return cached.journal;
}

function buildJournal() {
  const session = privateSession();
  const scoped = (key: string) => session.namespace + key;
  const storage = {
    getItem(key: string) {
      session.assertCurrent();
      return AsyncStorage.getItem(scoped(key));
    },
    setItem(key: string, value: string) {
      return serialize(() => {
        session.assertCurrent();
        return AsyncStorage.setItem(scoped(key), value);
      });
    },
    removeItem(key: string) {
      return serialize(() => {
        session.assertCurrent();
        return AsyncStorage.removeItem(scoped(key));
      });
    },
    async getAllKeys() {
      session.assertCurrent();
      const keys = await AsyncStorage.getAllKeys();
      session.assertCurrent();
      return keys.filter(key => key.startsWith(session.namespace)).map(key => key.slice(session.namespace.length));
    },
  };
  return { storage, assertCurrent: session.assertCurrent };
}
