import { Form, Link, useNavigation } from "react-router";
import type { Route } from "./+types/admin-matters";
import { requireAdmin } from "../lib/auth.server";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { PageHeader } from "../components/ui/page-header";
import { Badge } from "../components/ui/badge";
import { matterTitle } from "../lib/display-text";
import { formatDate } from "../lib/utils";

type Decision = {
  a: number;
  b: number;
  verdict: "same_matter" | "same_project" | "different";
  confidence: number;
  probabilities?: Record<string, number>;
};

const VERDICT_LABEL: Record<string, string> = {
  same_matter: "Same matter",
  same_project: "Same project",
  different: "Different",
};

export const meta: Route.MetaFunction = () => [{ title: "Matter merge review" }];

export async function loader({ request }: Route.LoaderArgs) {
  await requireAdmin(request);
  const supabase = getSupabaseAdminClient();
  const [{ data: proposals }, { count: decided }] = await Promise.all([
    supabase
      .from("matter_merge_proposals")
      .select("id, matter_ids, decisions, created_at")
      .eq("status", "pending")
      .order("created_at", { ascending: true })
      .limit(50),
    supabase
      .from("matter_merge_proposals")
      .select("id", { count: "exact", head: true })
      .neq("status", "pending"),
  ]);

  const ids = [...new Set((proposals || []).flatMap((p: any) => p.matter_ids as number[]))];
  const { data: matters } = ids.length
    ? await supabase
        .from("matters")
        .select(
          "id, title, identifier, first_seen, last_seen, meta, plain_english_summary, agenda_items(id, title, meetings(meeting_date))",
        )
        .in("id", ids)
    : { data: [] as any[] };
  const byId = new Map((matters || []).map((m: any) => [m.id, m]));

  return {
    decided: decided || 0,
    proposals: (proposals || []).map((p: any) => ({
      ...p,
      matters: (p.matter_ids as number[])
        .map((id) => byId.get(id))
        .filter(Boolean)
        .sort((x: any, y: any) => String(x.first_seen).localeCompare(String(y.first_seen))),
    })),
  };
}

export async function action({ request }: Route.ActionArgs) {
  const user = await requireAdmin(request);
  const supabase = getSupabaseAdminClient();
  const form = await request.formData();
  const id = Number(form.get("proposal_id"));
  const intent = String(form.get("intent"));
  if (!id) return { error: "Missing proposal." };

  const { data: proposal } = await supabase
    .from("matter_merge_proposals")
    .select("id, matter_ids, status")
    .eq("id", id)
    .maybeSingle();
  if (!proposal || proposal.status !== "pending") return { error: "That proposal was already decided." };

  if (intent === "merge") {
    const { data: rows, error } = await supabase
      .from("matters")
      .select("id, first_seen, last_seen, meta")
      .in("id", proposal.matter_ids);
    if (error || !rows || rows.length < 2) return { error: error?.message || "Matters not found." };
    if (rows.some((r: any) => r.meta?.canonical_matter_id)) {
      return { error: "One of these matters has already been merged elsewhere." };
    }
    // Earliest matter becomes canonical; the rest become aliases (reversible).
    rows.sort((x: any, y: any) => String(x.first_seen || "9999").localeCompare(String(y.first_seen || "9999")) || x.id - y.id);
    const [canonical, ...aliases] = rows as any[];
    const merged = [...new Set([...(canonical.meta?.merged_matter_ids || []), ...aliases.map((a) => a.id)])].sort(
      (x, y) => x - y,
    );
    const lastSeen = rows.map((r: any) => r.last_seen || "").sort().pop() || canonical.last_seen;
    const updates = [
      supabase
        .from("matters")
        .update({ meta: { ...(canonical.meta || {}), merged_matter_ids: merged }, last_seen: lastSeen })
        .eq("id", canonical.id),
      ...aliases.map((a) =>
        supabase
          .from("matters")
          .update({ meta: { ...(a.meta || {}), canonical_matter_id: canonical.id, merge_reason: "admin-review" } })
          .eq("id", a.id),
      ),
    ];
    for (const res of await Promise.all(updates)) {
      if (res.error) return { error: res.error.message };
    }
  } else if (intent !== "reject") {
    return { error: "Unknown action." };
  }

  const { error } = await supabase
    .from("matter_merge_proposals")
    .update({
      status: intent === "merge" ? "approved" : "rejected",
      decided_at: new Date().toISOString(),
      decided_by: user.email ?? null,
    })
    .eq("id", id);
  return error ? { error: error.message } : { ok: intent === "merge" ? "Merged." : "Kept separate." };
}

function bestDecision(decisions: Decision[]): Decision | null {
  const same = decisions.filter((d) => d.verdict !== "different");
  return (same.length ? same : decisions).sort((a, b) => b.confidence - a.confidence)[0] || null;
}

export default function AdminMatters({ loaderData, actionData }: Route.ComponentProps) {
  const { proposals, decided } = loaderData;
  const busy = useNavigation().state !== "idle";

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-6xl px-4 py-12">
        <PageHeader
          title="Matter merge review"
          description="Possible duplicates the resolver wasn't sure about. Merging keeps every record: the later matters become aliases of the earliest one and their history shows on its page."
        />

        {actionData && "error" in actionData && actionData.error && (
          <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{actionData.error}</p>
        )}
        {actionData && "ok" in actionData && actionData.ok && (
          <p className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{actionData.ok}</p>
        )}

        <p className="mb-4 text-sm text-zinc-500">
          <span className="font-semibold text-zinc-900">{proposals.length}</span> awaiting review
          {decided > 0 && <> · {decided} decided</>}
        </p>

        {proposals.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-5 text-sm text-zinc-500">
            Nothing to review.
          </div>
        ) : (
          <ul className="space-y-4">
            {proposals.map((p: any) => {
              const top = bestDecision(p.decisions as Decision[]);
              return (
                <li key={p.id} className="rounded-2xl border border-zinc-200 bg-white shadow-sm">
                  <div className="grid gap-px overflow-hidden rounded-t-2xl bg-zinc-100 md:grid-cols-2 lg:grid-flow-col lg:auto-cols-fr lg:grid-cols-none">
                    {p.matters.map((m: any) => {
                      const items = [...(m.agenda_items || [])]
                        .sort((x: any, y: any) =>
                          String(x.meetings?.meeting_date).localeCompare(String(y.meetings?.meeting_date)),
                        )
                        .slice(-3);
                      return (
                        <div key={m.id} className="bg-white p-4">
                          <Link
                            to={`/matters/${m.id}`}
                            target="_blank"
                            className="text-sm font-semibold leading-snug text-zinc-900 hover:text-brand-700"
                          >
                            {matterTitle(m)}
                          </Link>
                          <p className="mt-1 text-xs text-zinc-500 tabular-nums">
                            {[m.identifier, m.first_seen && formatDate(m.first_seen), m.last_seen !== m.first_seen && m.last_seen && formatDate(m.last_seen)]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                          {m.plain_english_summary && (
                            <p className="mt-2 text-sm leading-relaxed text-zinc-600 line-clamp-3">{m.plain_english_summary}</p>
                          )}
                          {items.length > 0 && (
                            <ul className="mt-3 space-y-1 border-t border-zinc-100 pt-2">
                              {items.map((it: any) => (
                                <li key={it.id} className="text-xs leading-snug text-zinc-500">
                                  <span className="tabular-nums text-zinc-400">{it.meetings?.meeting_date}</span> {it.title}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 px-4 py-3">
                    <p className="text-xs text-zinc-500">
                      {top ? (
                        <>
                          Model says <Badge variant={top.verdict === "different" ? "muted" : "brand"}>{VERDICT_LABEL[top.verdict]}</Badge>{" "}
                          <span className="tabular-nums">{Math.round(top.confidence * 100)}%</span>
                        </>
                      ) : (
                        "No model verdict"
                      )}
                    </p>
                    <Form method="post" className="flex gap-2">
                      <input type="hidden" name="proposal_id" value={p.id} />
                      <button
                        name="intent"
                        value="reject"
                        disabled={busy}
                        className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
                      >
                        Keep separate
                      </button>
                      <button
                        name="intent"
                        value="merge"
                        disabled={busy}
                        className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
                      >
                        Merge
                      </button>
                    </Form>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
