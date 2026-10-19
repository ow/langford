/**
 * Feature flags read from env (wrangler.toml [vars], inlined at build time by
 * vite.config.ts). Server-only; expose to the UI via the root loader.
 */
export function signupsEnabled(): boolean {
  return (process.env.ENABLE_SIGNUPS ?? "true").trim().toLowerCase() !== "false";
}
