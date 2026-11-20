import { useEffect } from "react";
import { useRouter } from "expo-router";

// AuthGate owns the public form. Once authenticated, consume its route without
// carrying any credential or challenge into the private navigation history.
export default function AccountActionRoute() {
  const router = useRouter();
  useEffect(() => { router.replace("/"); }, [router]);
  return null;
}
