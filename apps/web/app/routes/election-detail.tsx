import type { Route } from "./+types/election-detail";
import { getElectionById } from "../services/elections";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Link } from "react-router";
import { ogImageUrl, ogUrl } from "../lib/og";

export const meta: Route.MetaFunction = ({ data }) => {
  if (!data?.election) return [{ title: "Election | ViewRoyal.ai" }];
  const e = data.election as any;
  const title = `${e.name} | ViewRoyal.ai`;
  const description = e.notes || `${e.classification} — ${e.election_date}`;
  return [
    { title },
    { name: "description", content: description },
    { property: "og:title", content: e.name },
    { property: "og:description", content: description },
    { property: "og:type", content: "article" },
    { property: "og:url", content: ogUrl(`/elections/${e.id}`) },
    { property: "og:image", content: ogImageUrl(e.name, { subtitle: e.election_date, type: "election" }) },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
  ];
};
import { AlertTriangle, ExternalLink } from "lucide-react";
import { Badge } from "../components/ui/badge";
import { DetailHeader } from "../components/ui/detail-header";
import { OfficeResults } from "../components/elections/office-results";
import { formatDate } from "../lib/utils";

/** Mayor first, then other offices alphabetically. */
function officeRank(name: string) {
  const lower = (name || "").toLowerCase();
  if (lower.includes("mayor")) return 0;
  if (lower.includes("council")) return 1;
  return 2;
}

export async function loader({ params }: Route.LoaderArgs) {
  const { id } = params;

  try {
    const supabase = getSupabaseAdminClient();
    const election = await getElectionById(supabase, id);
    return { election };
  } catch (error) {
    console.error("Error fetching election:", error);
    throw new Response("Election Not Found", { status: 404 });
  }
}

export default function ElectionDetail({ loaderData }: Route.ComponentProps) {
  const { election } = loaderData;
  const hasResults = election.election_offices?.some((office: any) => office.candidacies?.length > 0);
  const preliminary = election.results_status === "preliminary";
  const status = !hasResults
    ? { label: "Results not loaded", variant: "muted" as const }
    : preliminary
      ? { label: "Preliminary results", variant: "warning" as const }
      : election.results_status === "official"
        ? { label: "Official results", variant: "success" as const }
        : { label: "Results pending", variant: "muted" as const };

  const offices = [...(election.election_offices || [])].sort(
    (a: any, b: any) =>
      officeRank(a.office) - officeRank(b.office) ||
      a.office.localeCompare(b.office),
  );

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-5xl px-4 py-12">
        <DetailHeader
          back={{ to: "/elections", label: "Elections" }}
          meta={[
            formatDate(election.election_date),
            `${election.classification || "General"} election`,
            <Badge key="status" variant={status.variant}>
              {status.label}
            </Badge>,
          ]}
          title={election.name}
          description={election.notes || undefined}
          actions={
            election.source_url ? (
              <a
                href={election.source_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 shadow-sm transition-colors hover:border-brand-200 hover:text-brand-700"
              >
                {hasResults ? "Source results" : "Council term source"}
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            ) : undefined
          }
        />

        {preliminary && hasResults && (
          <div className="mb-10 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden="true" />
            <p>
              These results are preliminary and may change before the official
              declaration. Election winners take office when their council term
              begins.
            </p>
          </div>
        )}

        {!hasResults ? (
          <div className="rounded-2xl border border-dashed border-zinc-200 bg-white p-8 text-center text-sm text-zinc-500">
            This election is recorded for council term history. Candidate
            results have not been added.
          </div>
        ) : (
          <div className="space-y-10">
            {offices.map((office: any) => (
              <OfficeResults
                key={office.id}
                office={office}
                preliminary={preliminary}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
