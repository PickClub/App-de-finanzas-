import { useNavigation } from "expo-router";

// Preserve an existing list and remove the preview/editor of this account.
export function accountListAfterRemoval(state: { routes: readonly any[] }, id?: string) {
  const remaining = state.routes.filter(route => !(
    (route.name === "accounts/[id]" || route.name === "accounts/new") && route.params?.id === id
  ));
  const listIndex = remaining.findIndex(route => route.name === "accounts/index");
  const routes = listIndex >= 0
    ? remaining.slice(0, listIndex + 1)
    : [...remaining, { name: "accounts/index" }];
  return { routes, index: routes.length - 1 };
}

export function useAccountDeletionExit(id?: string) {
  const navigation = useNavigation("/");
  return () => {
    const state = navigation.getState();
    if (state) navigation.reset(accountListAfterRemoval(state, id));
  };
}
