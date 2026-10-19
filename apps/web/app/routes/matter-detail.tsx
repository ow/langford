import { SITE_NAME } from "../lib/site-name";
import type { Route } from "./+types/matter-detail";
import {
  getMatterById,
  getDocumentsForAgendaItems,
  getMatterEvidence,
} from "../services/matters";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Link } from "react-router";
import { SubscribeButton } from "../components/subscribe-button";
import { ogImageUrl, ogUrl } from "../lib/og";

export const meta: Route.MetaFunction = ({ data }) => {
  if (!data?.matter) return [{ title: `Matter | ${SITE_NAME}` }];
  const m = data.matter as any;
  const title = `${m.title} | ${SITE_NAME}`;
  const description = m.plain_english_summary || m.description
    || `${m.category || "Council matter"} — ${m.status || "Active"}`;
  return [
    { title },
    { name: "description", content: description },
    { property: "og:title", content: m.title },
    { property: "og:description", content: description },
    { property: "og:type", content: "article" },
    { property: "og:url", content: ogUrl(`/matters/${m.id}`) },
    { property: "og:image", content: ogImageUrl(m.title, { subtitle: m.status, type: "matter" }) },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
  ];
};
import {
  ChevronRight,
  MessageSquare,
  ExternalLink,
  Clock,
  Info,
  Book,
  FileText,
  MapPin,
} from "lucide-react";
import { Badge } from "../components/ui/badge";
import { SectionHeading } from "../components/ui/section-heading";
import { DetailHeader } from "../components/ui/detail-header";
import { formatDate } from "../lib/utils";
import { displayTitle } from "../lib/display-text";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import { ScrollArea } from "../components/ui/scroll-area";
import { MatterMotion } from "../components/matter/matter-motion";
import { getDocumentTypeLabel } from "../lib/document-types";
import { ClientOnly } from "../components/utils/client-only";
import { lazy, Suspense } from "react";

const MattersMap = lazy(() =>
  import("../components/matters-map").then((module) => ({
    default: module.MattersMap,
  })),
);

const GENERIC_EVIDENCE_TITLES = new Set([
  "agenda",
  "agenda cover page",
  "background",
  "commentary",
  "correspondence",
  "executive summary",
  "engagement activities",
  "minutes",
  "notice of intent",
  "options",
  "page",
  "parks, recreation, and facilities",
  "proposed operating revenues",
  "proposed tax change",
  "reports",
  "significant 2026 budget items include:",
  "sports",
  "staff report",
]);

function cleanEvidenceText(value: string | null | undefined) {
  return (value || "")
    .replace(/^#+\s*/gm, "")
    .replace(/\[Image[^\]]*\]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function isGenericEvidenceTitle(value: string | null | undefined) {
  const normalized = cleanEvidenceText(value)
    .replace(/^\d+(?:\.\d+)*\s*/, "")
    .replace(/^[.)\s-]+/, "")
    .toLowerCase();
  if (!normalized) return true;
  if (normalized.length < 4) return true;
  if (/^page\s+\d+$/i.test(normalized)) return true;
  if (normalized.endsWith("/") || normalized.includes("participant/")) return true;
  if (
    /^(activity|attendees|dates|engagement|where\?|who was|of participant)/i.test(normalized)
  ) {
    return true;
  }
  if (/^(city of langford\s+)?arts and cultural development strategy$/i.test(normalized)) {
    return true;
  }
  if (/^\d+\.\s*(reports|correspondence|bylaws|notices of intent)$/i.test(normalized)) {
    return true;
  }
  return GENERIC_EVIDENCE_TITLES.has(normalized);
}

function getMatterTerms(matter: any) {
  const meta = matter?.meta && typeof matter.meta === "object" ? matter.meta : {};
  const aliases = Array.isArray(meta.aliases) ? meta.aliases : [];
  return [matter?.title, ...aliases]
    .filter(Boolean)
    .map((term: string) => cleanEvidenceText(term).toLowerCase())
    .filter((term: string) => term.length >= 4);
}

function titleCaseEvidence(value: string) {
  const cleaned = cleanEvidenceText(value)
    .replace(/^\d+(?:\.\d+)*\s*/, "")
    .replace(/^[-–—:]+/, "")
    .trim();
  if (!cleaned) return "";
  return cleaned.length > 140 ? `${cleaned.slice(0, 137).trim()}...` : cleaned;
}

function findLabeledLine(sectionText: string, labels: string[]) {
  const lines = sectionText.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const line = cleanEvidenceText(lines[i]);
    for (const label of labels) {
      const direct = line.match(new RegExp(`^${label}:\\s*(.+)$`, "i"));
      if (direct?.[1]) return titleCaseEvidence(direct[1]);
      if (line.toLowerCase() === label.toLowerCase()) {
        const next = lines.slice(i + 1).map(cleanEvidenceText).find(Boolean);
        if (next) return titleCaseEvidence(next);
      }
    }
  }
  return "";
}

function findUsefulHeading(sectionText: string, terms: string[]) {
  const headings = [...sectionText.matchAll(/^#{1,4}\s+(.+)$/gm)]
    .map((match) => titleCaseEvidence(match[1]))
    .filter((heading) => {
      if (isGenericEvidenceTitle(heading)) return false;
      const lower = heading.toLowerCase();
      if (lower.length < 12 && !terms.some((term) => lower.includes(term))) {
        return false;
      }
      return true;
    });

  const termHeading = headings.find((heading) => {
    const lower = heading.toLowerCase();
    return terms.some((term) => lower.includes(term));
  });
  return termHeading || headings[0] || "";
}

function findRelevantSentence(sectionText: string, terms: string[]) {
  const paragraphs = sectionText
    .split(/\n\s*\n/)
    .map(cleanEvidenceText)
    .filter((paragraph) => paragraph.length > 40);
  const relevant = paragraphs.find((paragraph) => {
    const lower = paragraph.toLowerCase();
    return terms.some((term) => lower.includes(term));
  }) || paragraphs[0] || "";
  if (!relevant) return "";
  return relevant.length > 280 ? `${relevant.slice(0, 277).trim()}...` : relevant;
}

function inferTitleFromRelevantText(matter: any, sectionText: string, summary: string) {
  const text = `${sectionText} ${summary}`.toLowerCase();
  const matterTitle = matter?.title || "Matter";
  const lowerMatterTitle = matterTitle.toLowerCase();
  if (lowerMatterTitle.includes("starlight stadium")) {
    if (
      text.includes("fifa world cup") ||
      text.includes("team base camp") ||
      text.includes("fifa representatives")
    ) {
      return "FIFA World Cup team base camp proposal at Starlight Stadium";
    }
    if (text.includes("commonwealth games")) {
      return "Commonwealth Games support involving Westhills Stadium";
    }
    if (text.includes("thunder bowl")) {
      return "Thunder Bowl event support at City Centre Park";
    }
    if (text.includes("telus walk to cure diabetes")) {
      return "JDRF TELUS Walk to Cure Diabetes at Westhills Stadium";
    }
    if (text.includes("canada women's sevens") || text.includes("canada women’s sevens")) {
      return "Canada Women's Sevens at Westhills Stadium";
    }
    if (text.includes("westshore rebels")) {
      return "Westshore Rebels game at Westhills Stadium";
    }
    if (text.includes("super summer kids day")) {
      return "Super Summer Kids Day at Westhills Stadium";
    }
    if (
      text.includes("arts and cultural development strategy") ||
      text.includes("community working group")
    ) {
      return "Arts and culture strategy engagement at Starlight Stadium";
    }
    if (
      text.includes("parks, recreation, and facilities") ||
      text.includes("city-owned parks, trails, and recreation infrastructure")
    ) {
      return "Parks and facilities budget reference to Starlight Stadium";
    }
  }
  if (
    lowerMatterTitle.includes("ymca") ||
    lowerMatterTitle.includes("aquatic centre")
  ) {
    if (text.includes("supplementary agreement")) {
      return "Langford Aquatic Centre supplementary agreement with YMCA/YWCA";
    }
    if (
      text.includes("langford aquatic centre debt") ||
      text.includes("woodlands park purchase") ||
      text.includes("west shore parks and recreation")
    ) {
      return "Langford Aquatic Centre debt and operating budget reference";
    }
    if (text.includes("permissive tax exemptions")) {
      return "YMCA property tax exemption reference";
    }
    if (text.includes("proposed changes to ymca-ywca services agreement")) {
      return "Proposed changes to YMCA-YWCA services agreement";
    }
    if (text.includes("purchase of service agreement")) {
      return "YMCA/YWCA services agreement contractual rights";
    }
    if (text.includes("leased to:") && text.includes("public athletic facility")) {
      return "YMCA/YWCA public athletic facility lease reference";
    }
  }
  return "";
}

function classifyEvidenceRecord(
  evidence: any,
  title: string,
  summary: string,
  sectionText: string,
) {
  const sectionTitle = evidence.document_section?.section_title || "";
  const text = `${title} ${summary} ${sectionTitle} ${sectionText}`.toLowerCase();
  if (evidence.evidence_type === "agenda_item") return "Agenda item";
  if (text.includes("moved by") || text.includes("carried")) return "Council decision";
  if (text.includes("staff report") || text.includes("department:")) return "Staff report";
  if (text.includes("budget") || text.includes("financial plan")) return "Budget";
  if (text.includes("letter") || text.includes("re:")) return "Correspondence";
  if (
    sectionTitle.toLowerCase().includes("sports") ||
    sectionTitle.toLowerCase().includes("public notices") ||
    text.includes("news gazette") ||
    text.includes("photo contributed")
  ) {
    return "Media clipping";
  }
  if (text.includes("minutes")) return "Minutes";
  return "Supporting record";
}

function buildFriendlyEvidence(evidence: any, matter: any) {
  const section = evidence.document_section;
  const agendaItem = evidence.agenda_item;
  const document = section?.document;
  const sectionText = section?.section_text || "";
  const terms = getMatterTerms(matter);
  const labeled =
    findLabeledLine(sectionText, ["Subject", "Re", "Purpose", "File No"]) ||
    findUsefulHeading(sectionText, terms);
  const summary = findRelevantSentence(sectionText, terms) || cleanEvidenceText(evidence.reason);
  const inferredTitle = inferTitleFromRelevantText(matter, sectionText, summary);
  const rawTitle =
    agendaItem?.title ||
    (!isGenericEvidenceTitle(section?.section_title) ? section?.section_title : "") ||
    (!isGenericEvidenceTitle(document?.title) ? document?.title : "");
  const title = titleCaseEvidence(inferredTitle || labeled || rawTitle || `${matter.title} supporting record`);
  return {
    title,
    summary,
    label: classifyEvidenceRecord(evidence, title, summary, sectionText),
  };
}

export async function loader({ params }: Route.LoaderArgs) {
  const { id } = params;

  try {
    const supabase = getSupabaseAdminClient();
    const matter = await getMatterById(supabase, id);

    // Fetch documents for all agenda items in this matter (batch query)
    const agendaItemIds = (matter.agenda_items || []).map((ai) => ai.id);
    const matterDocuments = await getDocumentsForAgendaItems(supabase, agendaItemIds);
    const matterEvidence = await getMatterEvidence(supabase, id);

    return { matter, matterDocuments, matterEvidence };
  } catch (error) {
    console.error("Error fetching matter:", error);
    throw new Response("Matter Not Found", { status: 404 });
  }
}

export default function MatterDetail({ loaderData }: Route.ComponentProps) {
  const { matter, matterDocuments, matterEvidence } = loaderData;

  // Sort agenda items by meeting date
  const timeline = [...(matter.agenda_items || [])].sort(
    (a, b) =>
      new Date(b.meetings.meeting_date).getTime() -
      new Date(a.meetings.meeting_date).getTime(),
  );
  const primaryAgendaItemIds = new Set(timeline.map((item) => item.id));
  const rawEvidenceTimeline = (matterEvidence || [])
    .filter((evidence: any) => {
      if (
        evidence.evidence_type === "agenda_item" &&
        evidence.agenda_item_id &&
        primaryAgendaItemIds.has(evidence.agenda_item_id)
      ) {
        return false;
      }
      return true;
    })
    .map((evidence: any) => {
      const section = evidence.document_section;
      const agendaItem = evidence.agenda_item;
      const document = section?.document;
      const friendly = buildFriendlyEvidence(evidence, matter);
      const documentMeeting = Array.isArray(document?.meetings)
        ? document.meetings[0]
        : document?.meetings;
      const meeting = agendaItem?.meetings || documentMeeting || null;
      return {
        kind: "evidence" as const,
        key: `evidence-${evidence.id}`,
        date: meeting?.meeting_date || null,
        meetingId: agendaItem?.meeting_id || document?.meeting_id || null,
        title: friendly.title,
        snippet: friendly.summary,
        label: friendly.label,
        matchCount: 1,
        evidence,
      };
    })
    .filter((entry: any) => entry.date);
  const evidenceTimeline = Array.from(
    rawEvidenceTimeline
      .reduce((groups: Map<string, any>, entry: any) => {
        const key = [
          entry.date,
          entry.meetingId || "no-meeting",
          entry.title.toLowerCase(),
        ].join("|");
        const existing = groups.get(key);
        if (!existing) {
          groups.set(key, entry);
          return groups;
        }

        existing.matchCount += 1;
        const existingConfidence = Number(existing.evidence?.confidence || 0);
        const entryConfidence = Number(entry.evidence?.confidence || 0);
        if (entryConfidence > existingConfidence) {
          existing.evidence = entry.evidence;
        }
        if (entry.snippet && entry.snippet.length > (existing.snippet || "").length) {
          existing.snippet = entry.snippet;
        }
        return groups;
      }, new Map<string, any>())
      .values(),
  );

  const timelineEntries = [
    ...timeline.map((item) => ({
      kind: "primary" as const,
      key: `agenda-${item.id}`,
      date: item.meetings.meeting_date,
      item,
    })),
    ...evidenceTimeline,
  ].sort(
    (a, b) => new Date(b.date || "").getTime() - new Date(a.date || "").getTime(),
  );

  // Build document lookup by agenda item ID
  const docsByItem = new Map<number, typeof matterDocuments>();
  for (const doc of matterDocuments || []) {
    if (doc.agenda_item_id != null) {
      const existing = docsByItem.get(doc.agenda_item_id);
      if (existing) {
        existing.push(doc);
      } else {
        docsByItem.set(doc.agenda_item_id, [doc]);
      }
    }
  }

  const lastSeen = timelineEntries.length > 0 ? timelineEntries[0].date : null;
  const firstSeen =
    timelineEntries.length > 0
      ? timelineEntries[timelineEntries.length - 1].date
      : null;

  const statusVariant =
    matter.status && matter.status !== "Active"
      ? /defeat|fail|withdraw|rescind|repeal/i.test(matter.status)
        ? "danger"
        : /adopt|complete|approv|pass|closed|resolved/i.test(matter.status)
          ? "success"
          : /pend|defer|tabled|hold/i.test(matter.status)
            ? "warning"
            : "muted"
      : null;

  const shortDate = (d: string | null | undefined) =>
    d
      ? formatDate(d, { year: "numeric", month: "short", day: "numeric" })
      : "";

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-4xl px-4 py-12">
        <header className="mb-10">
          <DetailHeader
            className="mb-0"
            back={{ to: "/matters", label: "Matters" }}
            meta={[
              matter.category || "General",
              matter.identifier ? (
                <span className="font-mono">{matter.identifier}</span>
              ) : null,
              firstSeen ? (
                <span className="tabular-nums">First seen {shortDate(firstSeen)}</span>
              ) : null,
              lastSeen && lastSeen !== firstSeen ? (
                <span className="tabular-nums">Last discussed {shortDate(lastSeen)}</span>
              ) : null,
            ]}
            title={displayTitle(matter.title)}
            badges={
              statusVariant ? (
                <Badge variant={statusVariant}>{matter.status}</Badge>
              ) : undefined
            }
            actions={
              <SubscribeButton
                type="matter"
                targetId={matter.id}
                label="Follow matter"
              />
            }
          />

          {matter.description && (
            <p className="mt-5 max-w-2xl text-base leading-relaxed text-zinc-600">
              {matter.description}
            </p>
          )}

          {matter.plain_english_summary && (
            <div className="mt-6 rounded-2xl border border-brand-100 bg-brand-50/60 p-5">
              <div className="mb-1.5 flex items-center gap-2 text-sm font-semibold text-brand-800">
                <Info className="h-4 w-4 text-brand-600" />
                In plain English
              </div>
              <p className="text-sm leading-relaxed text-zinc-700">
                {matter.plain_english_summary}
              </p>
            </div>
          )}

          {matter.bylaw && (
            <div className="mt-6 rounded-2xl border border-zinc-200 bg-white shadow-sm">
              <div className="flex items-start gap-4 p-5">
                <div className="hidden shrink-0 rounded-xl bg-brand-50 p-2.5 text-brand-700 ring-1 ring-brand-100 sm:block">
                  <Book className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                    <span>Governing bylaw</span>
                    {matter.bylaw.bylaw_number && (
                      <Badge variant="muted">No. {matter.bylaw.bylaw_number}</Badge>
                    )}
                    {matter.bylaw.status && matter.bylaw.status !== "Active" && (
                      <Badge variant="danger">{matter.bylaw.status}</Badge>
                    )}
                    {matter.bylaw.year && (
                      <span className="tabular-nums">
                        Adopted {matter.bylaw.year}
                      </span>
                    )}
                  </div>
                  <Link
                    to={`/bylaws/${matter.bylaw.id}`}
                    className="block text-base font-semibold leading-snug text-zinc-900 hover:text-brand-700"
                  >
                    {matter.bylaw.title}
                  </Link>
                  {matter.bylaw.plain_english_summary && (
                    <p className="mt-1.5 text-sm leading-relaxed text-zinc-600">
                      {matter.bylaw.plain_english_summary}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center justify-between gap-3 border-t border-zinc-100 px-5 py-3">
                <Link
                  to={`/bylaws/${matter.bylaw.id}`}
                  className="inline-flex items-center gap-1 text-sm font-semibold text-brand-700 hover:text-brand-800"
                >
                  Legislation history
                  <ChevronRight className="h-3.5 w-3.5" />
                </Link>

                <Dialog>
                  <DialogTrigger asChild>
                    <button className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 transition-colors hover:border-zinc-300 hover:bg-zinc-50">
                      <FileText className="h-3.5 w-3.5" />
                      Quick read
                    </button>
                  </DialogTrigger>
                  <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0 gap-0">
                    <DialogHeader className="px-6 py-4 border-b border-zinc-100 bg-zinc-50/50">
                      <div className="flex items-center gap-2 mb-2">
                        <Badge variant="brand">
                          {matter.bylaw.bylaw_number
                            ? `Bylaw ${matter.bylaw.bylaw_number}`
                            : "Bylaw"}
                        </Badge>
                        {matter.bylaw.year && (
                          <span className="text-xs text-zinc-500">
                            Adopted {matter.bylaw.year}
                          </span>
                        )}
                      </div>
                      <DialogTitle className="text-xl font-bold text-zinc-900">
                        {matter.bylaw.title}
                      </DialogTitle>
                    </DialogHeader>
                    <ScrollArea className="flex-1 min-h-0">
                      <div className="prose prose-sm max-w-none text-zinc-700 p-6">
                        {matter.bylaw.full_text ? (
                          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-zinc-600">
                            {matter.bylaw.full_text}
                          </pre>
                        ) : (
                          <div className="flex flex-col items-center justify-center py-12 text-zinc-400">
                            <FileText className="h-10 w-10 mb-3 opacity-30" />
                            <p>Full text not available.</p>
                          </div>
                        )}
                      </div>
                    </ScrollArea>
                    <div className="p-4 border-t border-zinc-100 bg-zinc-50 flex justify-end">
                      <a
                        href={`/api/bylaws/${matter.bylaw.id}/download`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm font-medium text-brand-700 hover:text-brand-800 flex items-center gap-1"
                      >
                        Download original PDF <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            </div>
          )}
        </header>

        <div className="space-y-12">
          {matter.locations && matter.locations.length > 0 && (
            <section>
              <SectionHeading title="Location" icon={MapPin} />
              <div className="overflow-hidden rounded-2xl border border-zinc-200 shadow-sm">
                <ClientOnly
                  fallback={<div className="h-[420px] w-full bg-zinc-100" />}
                >
                  {() => (
                    <Suspense
                      fallback={<div className="h-[420px] w-full bg-zinc-100" />}
                    >
                      <MattersMap matters={[matter]} />
                    </Suspense>
                  )}
                </ClientOnly>
              </div>
            </section>
          )}

          <section>
            <SectionHeading
              title="Timeline"
              icon={Clock}
              description="Every time this matter appeared in council records, newest first."
            />

            {timelineEntries.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-zinc-200 bg-white px-6 py-12 text-center text-sm text-zinc-500">
                No meeting records are linked to this matter yet.
              </div>
            ) : (
              <ol className="relative space-y-4 before:absolute before:bottom-4 before:left-[5px] before:top-4 before:w-px before:bg-zinc-200">
                {timelineEntries.map((entry: any) => {
                  if (entry.kind === "evidence") {
                    return (
                      <li key={entry.key} className="relative pl-7">
                        <span className="absolute left-0 top-6 h-[11px] w-[11px] rounded-full border-2 border-zinc-50 bg-zinc-300" />
                        <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
                          <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-zinc-500">
                            {entry.meetingId ? (
                              <Link
                                to={`/meetings/${entry.meetingId}`}
                                className="tabular-nums hover:text-brand-700"
                              >
                                {formatDate(entry.date)}
                              </Link>
                            ) : (
                              <span className="tabular-nums">
                                {formatDate(entry.date)}
                              </span>
                            )}
                            <Badge variant="muted">{entry.label}</Badge>
                            {entry.matchCount > 1 && (
                              <span className="text-xs tabular-nums">
                                {entry.matchCount} references
                              </span>
                            )}
                          </div>
                          <h3 className="text-base font-semibold leading-snug text-zinc-900">
                            {displayTitle(entry.title)}
                          </h3>
                          {entry.snippet && (
                            <p className="mt-1.5 line-clamp-3 text-sm leading-relaxed text-zinc-600">
                              {entry.snippet}
                            </p>
                          )}
                        </div>
                      </li>
                    );
                  }

                  const item = entry.item;
                  const itemDocs = docsByItem.get(item.id) || [];
                  return (
                    <li key={entry.key} className="relative pl-7">
                      <span className="absolute left-0 top-6 h-[11px] w-[11px] rounded-full border-2 border-zinc-50 bg-brand-600" />
                      <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm sm:p-6">
                        <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-zinc-500">
                          <Link
                            to={`/meetings/${item.meeting_id}`}
                            className="inline-flex items-center gap-1 hover:text-brand-700"
                          >
                            <span className="tabular-nums">
                              {formatDate(item.meetings.meeting_date)}
                            </span>
                            {item.meetings.organizations?.name && (
                              <>
                                <span className="text-zinc-300">·</span>
                                <span>{item.meetings.organizations.name}</span>
                              </>
                            )}
                            <ChevronRight className="h-3.5 w-3.5 text-zinc-300" />
                          </Link>
                        </div>

                        <h3 className="text-lg font-semibold leading-snug text-zinc-900">
                          {displayTitle(item.title)}
                        </h3>
                        {item.plain_english_summary && (
                          <p className="mt-1.5 text-sm leading-relaxed text-zinc-600">
                            {item.plain_english_summary}
                          </p>
                        )}
                        {item.debate_summary && (
                          <div className="mt-4 rounded-xl bg-zinc-50 px-4 py-3 text-sm leading-relaxed text-zinc-600">
                            <span className="mb-0.5 flex items-center gap-1.5 text-xs font-medium text-zinc-500">
                              <MessageSquare className="h-3.5 w-3.5" />
                              Discussion
                            </span>
                            {item.debate_summary}
                          </div>
                        )}

                        {itemDocs.length > 0 && (
                          <div className="mt-4 flex flex-wrap gap-2">
                            {itemDocs.map((doc) => (
                              <Link
                                key={doc.id}
                                to={`/meetings/${item.meeting_id}/documents/${doc.id}`}
                                title={getDocumentTypeLabel(doc.document_type)}
                                className="inline-flex max-w-full items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-2.5 py-1 text-xs text-zinc-700 transition-colors hover:border-brand-200 hover:text-brand-800"
                              >
                                <FileText className="h-3.5 w-3.5 shrink-0 text-zinc-400" />
                                <span className="truncate max-w-[240px]">
                                  {displayTitle(doc.title)}
                                </span>
                              </Link>
                            ))}
                          </div>
                        )}

                        {item.motions && item.motions.length > 0 && (
                          <div className="mt-5 space-y-5 border-t border-zinc-100 pt-5">
                            {item.motions.map((motion: any) => (
                              <MatterMotion key={motion.id} motion={motion} />
                            ))}
                          </div>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
