import type { Route } from "./+types/matter-detail";
import {
  getMatterById,
  getDocumentsForAgendaItems,
  getMatterEvidence,
} from "../services/matters";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Link, redirect } from "react-router";
import { SubscribeButton } from "../components/subscribe-button";
import { ogImageUrl, ogUrl } from "../lib/og";

export const meta: Route.MetaFunction = ({ data }) => {
  if (!data?.matter) return [{ title: "Matter | ViewRoyal.ai" }];
  const m = data.matter as any;
  const title = `${m.title} | ViewRoyal.ai`;
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
  ChevronLeft,
  ChevronRight,
  Tag,
  Calendar,
  MessageSquare,
  ExternalLink,
  Gavel,
  Clock,
  Info,
  Book,
  FileText,
} from "lucide-react";
import { Badge } from "../components/ui/badge";
import { formatDate, cn } from "../lib/utils";
import { Separator } from "../components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import { ScrollArea } from "../components/ui/scroll-area";
import { MotionCard } from "../components/motion-card";
import {
  getDocumentTypeLabel,
  getDocumentTypeColor,
} from "../lib/document-types";
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
    if (String(matter.id) !== id) return redirect(`/matters/${matter.id}`, 301);

    // Fetch documents for all agenda items in this matter (batch query)
    const agendaItemIds = (matter.agenda_items || []).map((ai) => ai.id);
    const matterDocuments = await getDocumentsForAgendaItems(supabase, agendaItemIds);
    const matterEvidence = await getMatterEvidence(supabase, matter.id, matter.meta?.merged_matter_ids || []);

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

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto py-8 px-4 max-w-4xl">
        <Link
          to="/matters"
          className="group flex items-center text-sm font-medium text-zinc-600 hover:text-blue-600 mb-6 transition-colors"
        >
          <ChevronLeft className="mr-1 h-4 w-4 group-hover:-translate-x-1 transition-transform" />
          Back to Matters
        </Link>

        <header className="mb-12 bg-white p-8 rounded-3xl border border-zinc-200 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 p-8 opacity-5">
            <Tag className="h-32 w-32" />
          </div>

          <div className="relative">
            <div className="flex flex-wrap items-center gap-3 mb-4">
              {matter.identifier && (
                <Badge className="bg-zinc-900 text-white font-mono font-bold px-3 py-1 text-xs">
                  {matter.identifier}
                </Badge>
              )}
              <Badge
                variant="outline"
                className="border-blue-200 text-blue-700 bg-blue-50/50 px-3 py-1"
              >
                {matter.category || "General"}
              </Badge>
              <span
                className={cn(
                  "text-[10px] font-black uppercase tracking-[0.2em] px-3 py-1 rounded-full border",
                  matter.status === "Active"
                    ? "bg-green-50 text-green-700 border-green-100"
                    : "bg-zinc-50 text-zinc-400 border-zinc-200",
                )}
              >
                {matter.status}
              </span>
              <SubscribeButton type="matter" targetId={matter.id} label="Follow Matter" />
            </div>
            <h1 className="text-4xl font-extrabold tracking-tight text-zinc-900 mb-4">
              {matter.title}
            </h1>
            {matter.description && (
              <p className="text-lg text-zinc-600 leading-relaxed max-w-2xl">
                {matter.description}
              </p>
            )}

            {matter.plain_english_summary && (
              <div className="mt-6 p-5 bg-blue-50 rounded-2xl border border-blue-100 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <Info className="h-4 w-4 text-blue-600" />
                  <span className="text-[10px] font-black text-blue-400 uppercase tracking-widest">
                    Plain English Summary
                  </span>
                </div>
                <p className="text-sm text-blue-900 font-medium leading-relaxed">
                  {matter.plain_english_summary}
                </p>
              </div>
            )}

            {matter.bylaw && (
              <div className="mt-6 bg-zinc-900 rounded-2xl border border-zinc-800 shadow-sm text-white overflow-hidden">
                <div className="p-6">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-6">
                    <div className="flex items-start gap-4">
                      <div className="p-3 bg-zinc-800 rounded-xl shrink-0">
                        <Book className="h-6 w-6 text-zinc-400" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-[10px] font-black text-zinc-400 uppercase tracking-widest">
                            Governing Bylaw
                          </span>
                          {matter.bylaw.bylaw_number && (
                            <Badge
                              variant="outline"
                              className="border-zinc-700 text-zinc-400 text-[10px] h-5"
                            >
                              No. {matter.bylaw.bylaw_number}
                            </Badge>
                          )}
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-[10px] h-5 border-zinc-700",
                              matter.bylaw.status === "Active"
                                ? "bg-zinc-800 text-zinc-300"
                                : "bg-red-900/30 text-red-300",
                            )}
                          >
                            {matter.bylaw.status}
                          </Badge>
                        </div>
                        <Link
                          to={`/bylaws/${matter.bylaw.id}`}
                          className="text-xl font-bold text-white mb-2 leading-tight hover:text-blue-400 transition-colors block"
                        >
                          {matter.bylaw.title}
                        </Link>
                        {matter.bylaw.year && (
                          <span className="text-xs text-zinc-500 font-medium block mb-3">
                            Adopted {matter.bylaw.year}
                          </span>
                        )}
                        {matter.bylaw.plain_english_summary && (
                          <p className="text-sm text-zinc-400 leading-relaxed max-w-2xl">
                            {matter.bylaw.plain_english_summary}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="px-6 py-3 bg-zinc-950/50 border-t border-zinc-800 flex items-center justify-between">
                  <Link
                    to={`/bylaws/${matter.bylaw.id}`}
                    className="text-xs font-bold text-zinc-400 hover:text-white flex items-center gap-2 transition-colors"
                  >
                    View Full Legislation History
                    <ChevronRight className="h-3 w-3" />
                  </Link>

                  <Dialog>
                    <DialogTrigger asChild>
                      <button className="flex items-center justify-center gap-2 px-3 py-1.5 bg-zinc-800 text-zinc-300 rounded-lg text-xs font-bold hover:bg-zinc-700 hover:text-white transition-colors cursor-pointer border border-zinc-700">
                        <FileText className="h-3 w-3" />
                        Quick Read
                      </button>
                    </DialogTrigger>
                    <DialogContent className="max-w-4xl h-[80vh] flex flex-col p-0 gap-0">
                      <DialogHeader className="px-6 py-4 border-b border-zinc-100 bg-zinc-50/50">
                        <div className="flex items-center gap-2 mb-2">
                          <Badge
                            variant="outline"
                            className="border-blue-200 text-blue-700 bg-blue-50/50"
                          >
                            {matter.bylaw.bylaw_number
                              ? `Bylaw ${matter.bylaw.bylaw_number}`
                              : "Bylaw"}
                          </Badge>
                          <span className="text-xs text-zinc-400 font-medium">
                            Adopted {matter.bylaw.year}
                          </span>
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
                              <FileText className="h-12 w-12 mb-4 opacity-20" />
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
                          className="text-xs font-medium text-blue-600 hover:text-blue-700 flex items-center gap-1"
                        >
                          Download Original PDF{" "}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                    </DialogContent>
                  </Dialog>
                </div>
              </div>
            )}

            <div className="mt-8 flex items-center gap-6 text-sm text-zinc-400">
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                First seen: {formatDate(firstSeen || "")}
              </div>
              <Separator orientation="vertical" className="h-4" />
              <div className="flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                Last seen: {formatDate(lastSeen || "")}
              </div>
            </div>
          </div>
        </header>

        <div className="space-y-12">
          {matter.locations && matter.locations.length > 0 && (
            <section>
              <h2 className="text-sm font-black uppercase tracking-widest text-zinc-400 px-4 mb-4">
                Geographic Scope
              </h2>
              <ClientOnly
                fallback={
                  <div className="h-[600px] w-full bg-zinc-100 rounded-3xl" />
                }
              >
                {() => (
                  <Suspense
                    fallback={
                      <div className="h-[600px] w-full bg-zinc-100 rounded-3xl" />
                    }
                  >
                    <MattersMap matters={[matter]} />
                  </Suspense>
                )}
              </ClientOnly>
            </section>
          )}

          <section>
            <h2 className="text-sm font-black uppercase tracking-widest text-zinc-400 px-4">
              Lifecycle Timeline
            </h2>

            <div className="space-y-4 mt-4">
              {timelineEntries.map((entry: any) => {
                if (entry.kind === "evidence") {
                  return (
                    <div
                      key={entry.key}
                      className="relative pl-8 before:absolute before:left-0 before:top-4 before:bottom-0 before:w-0.5 before:bg-zinc-200 last:before:hidden"
                    >
                      <div className="absolute left-[-4px] top-4 w-2 h-2 rounded-full bg-zinc-400 ring-4 ring-zinc-50 z-10" />

                      <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden hover:border-zinc-300 transition-all group">
                        <div className="p-5">
                          <div className="flex flex-wrap items-center justify-between gap-4 mb-3">
                            <div className="flex items-center gap-3">
                              <span className="text-xs font-black text-zinc-400 uppercase tracking-widest">
                                {formatDate(entry.date)}
                              </span>
                              <Badge
                                variant="secondary"
                                className="bg-zinc-100 text-zinc-600 hover:bg-zinc-100 font-medium text-[10px]"
                              >
                                {entry.label}
                              </Badge>
                              {entry.evidence.confidence && (
                                <span className="text-[10px] font-bold text-zinc-400">
                                  {Math.round(Number(entry.evidence.confidence) * 100)}% match
                                </span>
                              )}
                              {entry.matchCount > 1 && (
                                <span className="text-[10px] font-bold text-zinc-400">
                                  {entry.matchCount} references
                                </span>
                              )}
                            </div>
                            {entry.meetingId && (
                              <Link
                                to={`/meetings/${entry.meetingId}`}
                                className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-1 group-hover:translate-x-1 transition-transform"
                              >
                                Open Meeting
                                <ExternalLink className="h-3 w-3" />
                              </Link>
                            )}
                          </div>

                          <h3 className="text-base font-bold text-zinc-900 mb-2">
                            {entry.title}
                          </h3>
                          {entry.snippet && (
                            <p className="text-sm text-zinc-500 font-medium leading-relaxed line-clamp-3">
                              {entry.snippet}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                }

                const item = entry.item;
                return (
                  <div
                    key={entry.key}
                    className="relative pl-8 before:absolute before:left-0 before:top-4 before:bottom-0 before:w-0.5 before:bg-zinc-200 last:before:hidden"
                  >
                    <div className="absolute left-[-4px] top-4 w-2 h-2 rounded-full bg-blue-600 ring-4 ring-zinc-50 z-10" />

                  <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden hover:border-blue-200 transition-all group">
                    <div className="p-6">
                      <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
                        <div className="flex items-center gap-3">
                          <span className="text-xs font-black text-zinc-400 uppercase tracking-widest">
                            {formatDate(item.meetings.meeting_date)}
                          </span>
                          <Badge
                            variant="secondary"
                            className="bg-zinc-100 text-zinc-600 hover:bg-zinc-100 font-medium text-[10px]"
                          >
                            {item.meetings.organizations?.name}
                          </Badge>
                        </div>
                        <Link
                          to={`/meetings/${item.meeting_id}`}
                          className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-1 group-hover:translate-x-1 transition-transform"
                        >
                          Full Recording
                          <ExternalLink className="h-3 w-3" />
                        </Link>
                      </div>

                      <h3 className="text-lg font-bold text-zinc-900 mb-2">
                        {item.title}
                      </h3>
                      {item.plain_english_summary && (
                        <p className="text-sm text-zinc-500 mb-4 font-medium leading-relaxed">
                          {item.plain_english_summary}
                        </p>
                      )}
                      {item.debate_summary && (
                        <div className="bg-zinc-50 p-4 rounded-xl border border-zinc-100 mb-4 italic text-sm text-zinc-600 leading-relaxed">
                          "{item.debate_summary}"
                        </div>
                      )}

                      {/* Document chips */}
                      {(() => {
                        const itemDocs = docsByItem.get(item.id) || [];
                        if (itemDocs.length === 0) return null;
                        return (
                          <div className="flex flex-wrap gap-2 mb-4">
                            {itemDocs.map((doc) => (
                              <Link
                                key={doc.id}
                                to={`/meetings/${item.meeting_id}/documents/${doc.id}`}
                                className="inline-flex items-center gap-1.5 text-xs bg-white border border-zinc-200 rounded-md px-2 py-1 hover:border-blue-200 hover:shadow-sm transition-all"
                              >
                                <span className={cn(
                                  "inline-block px-1 py-0.5 text-[8px] font-bold uppercase rounded border shrink-0",
                                  getDocumentTypeColor(doc.document_type),
                                )}>
                                  {getDocumentTypeLabel(doc.document_type).slice(0, 6)}
                                </span>
                                <span className="text-zinc-700 truncate max-w-[200px]">{doc.title}</span>
                              </Link>
                            ))}
                          </div>
                        );
                      })()}

                      {item.motions && item.motions.length > 0 && (
                        <div className="space-y-4 mt-6 border-t border-zinc-100 pt-6">
                          {item.motions.map((motion: any) => (
                            <MotionCard key={motion.id} motion={motion} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                );
              })}
            </div>
          </section>

        </div>
      </div>
    </div>
  );
}
