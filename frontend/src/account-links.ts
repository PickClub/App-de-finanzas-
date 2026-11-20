// A link may select a public form; it never carries a session, password or account code.
export type AccountForm = "login" | "invite" | "recover";
export function accountFormFromLink(url: string | null): AccountForm | undefined {
  if (!url) return;
  const match = /^pickwallet:\/\/(?:\/)?account\/(invite|recover)$/.exec(url);
  return match?.[1] as "invite" | "recover" | undefined;
}
