import { useRouteLoaderData } from "react-router";

/** Client-side view of server feature flags (from the root loader). */
export function useSiteFlags() {
  const data = useRouteLoaderData("root") as { signupsEnabled?: boolean } | undefined;
  return { signupsEnabled: data?.signupsEnabled ?? true };
}
