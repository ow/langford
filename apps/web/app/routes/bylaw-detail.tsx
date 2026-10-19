import { SITE_NAME } from "../lib/site-name";
import { DEFAULT_MUNICIPALITY } from "../lib/site-config";
import type { Route } from "./+types/bylaw-detail";
import { getBylawById } from "../services/bylaws";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Link, useRouteLoaderData } from "react-router";
import type { Municipality } from "../lib/types";
import { ogImageUrl, ogUrl } from "../lib/og";
import { bylawPath, meetingPath } from "../lib/paths";
import { resolveSlugParam } from "../lib/slug-params.server";

export const meta: Route.MetaFunction = ({ data }) => {
  if (!data?.bylaw) return [{ title: `Bylaw | ${SITE_NAME}` }];
  const b = data.bylaw as any;
  const label = b.bylaw_number ? `Bylaw ${b.bylaw_number}` : b.title;
  const title = `${label} | ${SITE_NAME}`;
  const description = b.plain_english_summary || `${b.title} — ${b.status || "Active"}`;
  return [
    { title },
    { name: "description", content: description },
    { property: "og:title", content: label },
    { property: "og:description", content: description },
    { property: "og:type", content: "article" },
    { property: "og:url", content: ogUrl(bylawPath(b)) },
    { property: "og:image", content: ogImageUrl(label, { subtitle: b.status, type: "bylaw" }) },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
  ];
};
import {
  FileText,
  List,
  Info,
  Download,
  History,
} from "lucide-react";
import { Badge } from "../components/ui/badge";
import { SectionHeading } from "../components/ui/section-heading";
import { DetailHeader } from "../components/ui/detail-header";
import { cn, formatDate } from "../lib/utils";
import { displayTitle } from "../lib/display-text";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export async function loader({ params, request }: Route.LoaderArgs) {
  const supabase = getSupabaseAdminClient();
  const resolved = await resolveSlugParam(supabase, "bylaws", params.id, request, (b) => bylawPath(b), "Bylaw Not Found");

  try {
    const bylaw = await getBylawById(supabase, String(resolved.id));
    if (!bylaw) throw new Response("Bylaw Not Found", { status: 404 });
    return { bylaw };
  } catch (error) {
    console.error(error);
    throw new Response("Bylaw Not Found", { status: 404 });
  }
}

export default function BylawDetail({ loaderData }: Route.ComponentProps) {
  const { bylaw } = loaderData;
  const rootData = useRouteLoaderData("root") as { municipality?: Municipality } | undefined;
  const municipalityName = rootData?.municipality?.name || DEFAULT_MUNICIPALITY.name;

  // Construct legislative timeline from linked matters and agenda items
  const meetingEvents = (bylaw.matters || []).flatMap((matter) =>
    (matter.agenda_items || []).map((item) => {
      const isAdoption =
        item.title.toLowerCase().includes("adoption") ||
        item.title.toLowerCase().includes("adopted");

      return {
        id: `item-${item.id}`,
        date: item.meetings?.meeting_date,
        meetingTitle: item.meetings?.title,
        meetingId: item.meeting_id,
        meetingSlug: item.meetings?.slug,
        orgName: item.meetings?.organization?.name,
        title: item.title,
        matterTitle: matter.title,
        type: isAdoption ? "adoption" : "meeting",
      };
    }),
  );

  const milestoneEvents = bylaw.year
    ? [
        {
          id: "adoption-event",
          date: `${bylaw.year}-01-01`,
          meetingTitle: `Adopted ${bylaw.year}`,
          meetingId: 0,
          meetingSlug: null,
          orgName: municipalityName,
          title: `Official adoption year of Bylaw No. ${bylaw.bylaw_number || ""}`,
          matterTitle: bylaw.title,
          type: "milestone",
        },
      ]
    : [];

  const timeline = [...meetingEvents, ...milestoneEvents]
    .filter((item) => item.date)
    .sort((a, b) => new Date(b.date!).getTime() - new Date(a.date!).getTime());

  const downloadHref = `/api/bylaws/${bylaw.id}/download`;

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-5xl px-4 py-12">
        <DetailHeader
          className="mb-10"
          back={{ to: "/bylaws", label: "Bylaws" }}
          meta={[
            <span className="tabular-nums">
              {bylaw.bylaw_number ? `No. ${bylaw.bylaw_number}` : "Policy"}
            </span>,
            bylaw.category || null,
            bylaw.year ? (
              <span className="tabular-nums">Adopted {bylaw.year}</span>
            ) : null,
          ]}
          title={displayTitle(bylaw.title)}
          badges={
            bylaw.status && bylaw.status !== "Active" ? (
              <Badge variant="danger">{bylaw.status}</Badge>
            ) : undefined
          }
          actions={
            <a
              href={downloadHref}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3.5 py-2 text-sm font-semibold text-zinc-800 shadow-xs transition-colors hover:border-zinc-300 hover:bg-zinc-50"
            >
              <Download className="h-4 w-4 text-zinc-500" />
              Download PDF
            </a>
          }
        />

        <div className="grid grid-cols-1 gap-10 lg:grid-cols-3">
          <div className="space-y-10 lg:col-span-2">
            {bylaw.plain_english_summary && (
              <section className="rounded-2xl border border-brand-100 bg-brand-50/60 p-5">
                <div className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-brand-800">
                  <Info className="h-4 w-4 text-brand-600" />
                  In plain English
                </div>
                <p className="text-base leading-relaxed text-zinc-700">
                  {bylaw.plain_english_summary}
                </p>
              </section>
            )}

            {timeline.length > 0 && (
              <section>
                <SectionHeading title="Legislative history" icon={History} />
                <ol className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white shadow-sm">
                  {timeline.map((event) => (
                    <li key={event.id} className="flex gap-3 px-4 py-4 sm:px-5">
                      <span
                        className={cn(
                          "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                          event.type === "milestone"
                            ? "bg-zinc-400"
                            : event.type === "adoption"
                              ? "bg-emerald-500"
                              : "bg-brand-500",
                        )}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="mb-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-zinc-500">
                          {event.type === "milestone" ? (
                            <span className="tabular-nums">
                              {event.date?.split("-")[0]}
                            </span>
                          ) : (
                            <Link
                              to={meetingPath({ id: event.meetingId, slug: event.meetingSlug })}
                              className="hover:text-brand-700"
                            >
                              <span className="tabular-nums">
                                {formatDate(event.date!, {
                                  year: "numeric",
                                  month: "short",
                                  day: "numeric",
                                })}
                              </span>
                              {event.meetingTitle && (
                                <>
                                  <span className="mx-1.5 text-zinc-300">·</span>
                                  {displayTitle(event.meetingTitle)}
                                </>
                              )}
                            </Link>
                          )}
                          {event.type === "adoption" && (
                            <Badge variant="success">Adoption</Badge>
                          )}
                        </div>
                        <p className="text-sm leading-relaxed text-zinc-800">
                          {event.type === "milestone"
                            ? event.meetingTitle
                            : displayTitle(event.title)}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {bylaw.outline && (
              <section>
                <SectionHeading title="Outline" icon={List} />
                <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm sm:p-6">
                  <div className="prose prose-sm prose-zinc max-w-none">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {bylaw.outline}
                    </ReactMarkdown>
                  </div>
                </div>
              </section>
            )}

            <section>
              <SectionHeading title="Full text" icon={FileText} />
              <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
                <div className="max-h-[600px] overflow-y-auto p-5 sm:p-6">
                  {bylaw.full_text ? (
                    <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-zinc-700">
                      {bylaw.full_text}
                    </pre>
                  ) : (
                    <p className="text-sm text-zinc-500">
                      Full text isn&apos;t available.{" "}
                      <a
                        href={downloadHref}
                        target="_blank"
                        rel="noreferrer"
                        className="font-medium text-brand-700 hover:text-brand-800"
                      >
                        Download the PDF
                      </a>{" "}
                      instead.
                    </p>
                  )}
                </div>
              </div>
            </section>
          </div>

          <aside className="space-y-6">
            <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
              <h2 className="mb-3 text-sm font-semibold text-zinc-900">Details</h2>
              <dl className="divide-y divide-zinc-100 text-sm">
                <div className="flex justify-between gap-4 py-2">
                  <dt className="text-zinc-500">Number</dt>
                  <dd className="font-medium text-zinc-900 tabular-nums">
                    {bylaw.bylaw_number || "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-4 py-2">
                  <dt className="text-zinc-500">Status</dt>
                  <dd className="font-medium text-zinc-900">
                    {bylaw.status || "—"}
                  </dd>
                </div>
                {bylaw.year && (
                  <div className="flex justify-between gap-4 py-2">
                    <dt className="text-zinc-500">Adopted</dt>
                    <dd className="font-medium text-zinc-900 tabular-nums">
                      {bylaw.year}
                    </dd>
                  </div>
                )}
                {bylaw.category && (
                  <div className="flex justify-between gap-4 py-2">
                    <dt className="text-zinc-500">Category</dt>
                    <dd className="text-right font-medium text-zinc-900">
                      {bylaw.category}
                    </dd>
                  </div>
                )}
              </dl>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
