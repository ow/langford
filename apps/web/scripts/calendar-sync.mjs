/** Explicit operator dry run/apply; never exposes a public endpoint or logs credentials. */
import { createServer } from "vite";
import { createClient } from "@supabase/supabase-js";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const args = process.argv.slice(2);
const option = name => args[args.indexOf(name) + 1];
const root = fileURLToPath(new URL("../", import.meta.url));
const server = await createServer({ root, configFile: false, server: { middlewareMode: true } });
try {
  const { discoverCalendarEvents } = await server.ssrLoadModule("/app/services/calendar-sync.ts");
  const preview = await discoverCalendarEvents();
  if (args.includes("--output")) writeFileSync(option("--output"), JSON.stringify(preview, null, 2));
  console.log(JSON.stringify(preview, null, 2));
  if (args.includes("--apply")) {
    if (!args.includes("--reviewed")) throw new Error("Apply requires a reviewed dry-run file");
    const reviewed = JSON.parse(readFileSync(option("--reviewed"), "utf8"));
    if (JSON.stringify(reviewed.events) !== JSON.stringify(preview.events)) throw new Error("Official-source rows changed since review; run a new dry run");
    const url = process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL;
    const key = process.env.SUPABASE_SECRET_KEY;
    if (new URL(url).hostname !== "zxcvifwkaxtdfpanlwtl.supabase.co" || !key) throw new Error("Expected Langford backend configuration is required");
    const db = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
    // Fetch again under the lease; require the reviewed prospective rows
    // to remain stable immediately before the transaction, too.
    const { data: token, error } = await db.rpc("claim_calendar_sync", { p_trigger: "manual" });
    if (error) throw error;
    if (!token) throw new Error("Another calendar run is active");
    try {
      const current = await discoverCalendarEvents();
      if (JSON.stringify(current.events) !== JSON.stringify(reviewed.events)) throw new Error("Official-source rows changed during apply");
      const receipt = await db.rpc("apply_calendar_sync", { p_token: token, p_events: current.events, p_warnings: current.warnings });
      if (receipt.error) throw receipt.error;
      console.log("IMPORT_RECEIPT", JSON.stringify(receipt.data));
    } catch (error) {
      await db.rpc("fail_calendar_sync", { p_token: token, p_error: "Manual reviewed calendar import failed; previous schedule retained" });
      throw error;
    }
  }
} finally { await server.close(); }
