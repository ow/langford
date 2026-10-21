import { useEffect, useState } from "react";

// Cloudflare owns reuse/freshness; reopen fetches again rather than retaining text indefinitely.
function useSectionTexts(sections: DocumentSection[], enabled: boolean) {
  const [state, setState] = useState<{ key: string; texts: Record<number, string>; status: "loading" | "ready" | "error" } | null>(null);
  const [attempt, retry] = useState(0);
  const ids = [...new Set(sections.filter((section) => section.section_text == null).map((section) => section.id))].sort((a, b) => a - b);
  const key = ids.join(",");
  useEffect(() => {
    if (!enabled || !key) return;
    const controller = new AbortController();
    setState({ key, texts: {}, status: "loading" });
    const load = async () => {
      const texts: Record<number, string> = {};
      for (let start = 0; start < ids.length; start += 200) {
        const response = await fetch(`/api/meeting-text?kind=sections&ids=${ids.slice(start, start + 200).join(",")}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Document text unavailable");
        const data = await response.json() as { texts?: Record<number, string> };
        if (!data.texts || typeof data.texts !== "object") throw new Error("Invalid section text");
        Object.assign(texts, data.texts);
      }
      if (!controller.signal.aborted) setState({ key, texts, status: "ready" });
    };
    load().catch(() => { if (!controller.signal.aborted) setState({ key, texts: {}, status: "error" }); });
    return () => controller.abort();
  }, [enabled, key, attempt]);
  const current = state?.key === key ? state : null;
  return {
    textOf: (section: DocumentSection) => section.section_text ?? current?.texts[section.id],
    status: current?.status ?? (key ? "loading" : "ready"),
    retry: () => retry(value => value + 1),
  };
}
import { documentPath } from "../../lib/paths";
import { Link } from "react-router";
import { FileText, ChevronDown, ChevronRight, BookOpen, Lightbulb } from "lucide-react";
import { cn } from "../../lib/utils";
import { MarkdownContent } from "../markdown-content";
import type { DocumentSection, ExtractedDocument } from "../../lib/types";
import {
  getDocumentTypeLabel,
  getDocumentTypeColor,
} from "../../lib/document-types";

interface DocumentSectionsProps {
  sections: DocumentSection[];
  extractedDocuments?: ExtractedDocument[];
  meetingId: number;
  meetingSlug?: string | null;
}

export function DocumentSections({
  sections,
  extractedDocuments,
  meetingId,
  meetingSlug,
}: DocumentSectionsProps) {
  if (sections.length === 0) return null;

  // If we have extracted documents, group sections under them
  if (extractedDocuments && extractedDocuments.length > 0) {
    return (
      <GroupedDocumentSections
        sections={sections}
        extractedDocuments={extractedDocuments}
        meetingId={meetingId}
        meetingSlug={meetingSlug}
      />
    );
  }

  // Flat accordion fallback
  return <FlatDocumentSections sections={sections} />;
}

function GroupedDocumentSections({
  sections,
  extractedDocuments,
  meetingId,
  meetingSlug,
}: {
  sections: DocumentSection[];
  extractedDocuments: ExtractedDocument[];
  meetingId: number;
  meetingSlug?: string | null;
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const expandedSections = expandedId == null ? [] : sections.filter((s) => s.extracted_document_id === expandedId);
  const { textOf, status, retry } = useSectionTexts(expandedSections, expandedId != null);

  // Group sections by extracted_document_id
  const sectionsByDoc = new Map<number, DocumentSection[]>();
  const orphans: DocumentSection[] = [];

  for (const section of sections) {
    if (section.extracted_document_id) {
      const existing = sectionsByDoc.get(section.extracted_document_id);
      if (existing) {
        existing.push(section);
      } else {
        sectionsByDoc.set(section.extracted_document_id, [section]);
      }
    } else {
      orphans.push(section);
    }
  }

  // Filter to only extracted docs that have matching sections
  const relevantDocs = extractedDocuments.filter(
    (ed) => sectionsByDoc.has(ed.id),
  );

  if (relevantDocs.length === 0) {
    return <FlatDocumentSections sections={sections} />;
  }

  return (
    <div className="space-y-1">
      <h4 className="flex items-center gap-2 text-xs font-bold text-zinc-500 uppercase tracking-wider">
        <FileText className="w-3 h-3 text-indigo-500" />
        Documents ({relevantDocs.length})
      </h4>
      <div className="pl-5 space-y-2">
        {relevantDocs.map((ed) => {
          const childSections = sectionsByDoc.get(ed.id) || [];
          const isExpanded = expandedId === ed.id;

          return (
            <div
              key={ed.id}
              className="border border-zinc-100 rounded-lg overflow-hidden"
            >
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setExpandedId(isExpanded ? null : ed.id);
                }}
                className="w-full flex items-start justify-between px-3 py-2 text-left hover:bg-zinc-50 transition-colors gap-2"
              >
                <div className="flex items-start gap-2 min-w-0 flex-1">
                  <span
                    className={cn(
                      "inline-block px-1.5 py-0.5 text-[8px] font-bold uppercase rounded border shrink-0 mt-0.5",
                      getDocumentTypeColor(ed.document_type),
                    )}
                  >
                    {getDocumentTypeLabel(ed.document_type).slice(0, 6)}
                  </span>
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-zinc-700 line-clamp-1">
                      {ed.title}
                    </span>
                    {ed.summary && (
                      <p className="text-xs text-zinc-500 line-clamp-1 mt-0.5">
                        {ed.summary}
                      </p>
                    )}
                  </div>
                </div>
                <ChevronDown
                  className={cn(
                    "w-4 h-4 text-zinc-400 flex-shrink-0 transition-transform mt-0.5",
                    isExpanded && "rotate-180",
                  )}
                />
              </button>
              <div
                className={cn(
                  "grid transition-all duration-200 ease-in-out",
                  isExpanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                )}
              >
                <div className="overflow-hidden">
                  <div className="px-3 pb-3 border-t border-zinc-100">
                    {/* Summary & key facts inside expanded */}
                    {ed.summary && (
                      <div className="flex items-start gap-1.5 mt-2 mb-2">
                        <BookOpen className="w-3 h-3 text-zinc-400 shrink-0 mt-0.5" />
                        <p className="text-xs text-zinc-600 leading-relaxed">
                          {ed.summary}
                        </p>
                      </div>
                    )}
                    {ed.key_facts && ed.key_facts.length > 0 && (
                      <div className="flex items-start gap-1.5 mb-2">
                        <Lightbulb className="w-3 h-3 text-amber-500 shrink-0 mt-0.5" />
                        <div className="flex flex-wrap gap-1">
                          {ed.key_facts.map((fact, i) => (
                            <span
                              key={i}
                              className="text-[10px] text-zinc-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5"
                            >
                              {fact}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Child sections */}
                    {childSections.map((section, idx) => (
                      <div key={section.id} className={cn(idx > 0 && "mt-3")}>
                        {section.section_title && (
                          <h5 className="text-xs font-semibold text-zinc-700 mb-1">
                            {section.section_title}
                          </h5>
                        )}
                        <SectionText text={textOf(section)} status={status} onRetry={retry} />
                        {section.page_start != null && (
                          <span className="text-[10px] text-zinc-400 mt-1 block">
                            Page {section.page_start}
                            {section.page_end &&
                            section.page_end !== section.page_start
                              ? `\u2013${section.page_end}`
                              : ""}
                          </span>
                        )}
                        {idx < childSections.length - 1 && (
                          <hr className="mt-3 border-zinc-100" />
                        )}
                      </div>
                    ))}
                    <Link
                      to={documentPath({ id: meetingId, slug: meetingSlug }, ed.id)}
                      className="flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 mt-3 pt-2 border-t border-zinc-100 transition-colors"
                    >
                      View full document
                      <ChevronRight className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {/* Orphan sections that don't belong to any extracted doc */}
        {orphans.map((section) => (
          <FlatSectionItem
            key={section.id}
            section={section}
            expandedId={expandedId}
            onToggle={(id) =>
              setExpandedId(expandedId === id ? null : id)
            }
          />
        ))}
      </div>
    </div>
  );
}

function FlatDocumentSections({ sections }: { sections: DocumentSection[] }) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  return (
    <div className="space-y-1">
      <h4 className="flex items-center gap-2 text-xs font-bold text-zinc-500 uppercase tracking-wider">
        <FileText className="w-3 h-3 text-indigo-500" />
        Document Sections ({sections.length})
      </h4>
      <div className="pl-5 space-y-1">
        {sections.map((section) => (
          <FlatSectionItem
            key={section.id}
            section={section}
            expandedId={expandedId}
            onToggle={(id) =>
              setExpandedId(expandedId === id ? null : id)
            }
          />
        ))}
      </div>
    </div>
  );
}

function FlatSectionItem({
  section,
  expandedId,
  onToggle,
}: {
  section: DocumentSection;
  expandedId: number | null;
  onToggle: (id: number) => void;
}) {
  const isExpanded = expandedId === section.id;
  const { textOf, status, retry } = useSectionTexts([section], isExpanded);

  return (
    <div className="border border-zinc-100 rounded-lg overflow-hidden">
      <button
        onClick={(e) => {
          e.stopPropagation();
          onToggle(section.id);
        }}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-zinc-50 transition-colors"
      >
        <span className="text-sm font-medium text-zinc-700 truncate pr-2">
          {section.section_title || `Section ${section.section_order}`}
        </span>
        <ChevronDown
          className={cn(
            "w-4 h-4 text-zinc-400 flex-shrink-0 transition-transform",
            isExpanded && "rotate-180",
          )}
        />
      </button>
      <div
        className={cn(
          "grid transition-all duration-200 ease-in-out",
          isExpanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden">
          <div className="px-3 pb-3 border-t border-zinc-100 mt-2">
            <SectionText text={textOf(section)} status={status} onRetry={retry} />
            {section.page_start != null && (
              <span className="text-[10px] text-zinc-400 mt-2 block">
                Page {section.page_start}
                {section.page_end &&
                section.page_end !== section.page_start
                  ? `\u2013${section.page_end}`
                  : ""}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SectionText({ text, status, onRetry }: { text: string | undefined; status: string; onRetry: () => void }) {
  if (status === "error" && text == null) return <p role="status" className="text-xs text-zinc-500">Text could not load. <button type="button" className="underline" onClick={onRetry}>Try again</button></p>;
  if (text == null) return <p role="status" className="text-xs text-zinc-400">{status === "loading" ? "Loading…" : "Text not available."}</p>;
  return <MarkdownContent content={text} />;
}
