import { useState } from "react";
import { Link } from "react-router";
import { ExternalLink, Mic } from "lucide-react";
import { formatDate } from "../../lib/utils";

export interface ParticipationHistory {
  name: string;
  coverageNote: string;
  records: {
    meetingId: number;
    date: string;
    meetingType: string;
    minutesUrl: string;
    recordingUrl: string;
    summary: string;
  }[];
}

export function PublicParticipation({ history }: { history: ParticipationHistory }) {
  const [query, setQuery] = useState("");
  const [year, setYear] = useState("all");
  const [expanded, setExpanded] = useState(false);
  const years = [...new Set(history.records.map((record) => record.date.slice(0, 4)))].sort().reverse();
  const matching = history.records.filter((record) =>
    (year === "all" || record.date.startsWith(year)) &&
    `${record.summary} ${record.date} ${record.meetingType}`.toLowerCase().includes(query.trim().toLowerCase()),
  ).sort((a, b) => b.date.localeCompare(a.date));
  const visible = expanded ? matching : matching.slice(0, 6);

  return (
    <section id="public-participation" className="rounded-xl border border-zinc-200 bg-white p-5 sm:p-6 space-y-5">
      <div>
        <div className="flex items-center gap-2 text-teal-700 mb-2">
          <Mic className="h-4 w-4" aria-hidden="true" />
          <span className="text-xs font-semibold uppercase tracking-wider">Before council service</span>
        </div>
        <h2 className="text-xl font-bold text-zinc-900">Public participation</h2>
        <p className="text-sm text-zinc-600 mt-2 leading-relaxed">
          {history.name}’s earlier appearances as a member of the public.
          These summaries describe statements recorded in official minutes; they are not verbatim quotations or council votes.
        </p>
        <p className="text-xs text-zinc-500 mt-2">{history.coverageNote} Speech timings and machine transcripts await audio review.</p>
      </div>
      <div className="flex flex-col sm:flex-row gap-3">
        <label className="flex-1 text-xs font-medium text-zinc-600">
          Search statements
          <input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setExpanded(false); }} placeholder="Try taxes, trees, RCMP…" className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900" />
        </label>
        <label className="text-xs font-medium text-zinc-600">
          Year
          <select value={year} onChange={(event) => { setYear(event.target.value); setExpanded(false); }} className="mt-1 block w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900">
            <option value="all">All years</option>
            {years.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
      </div>
      <p className="text-xs text-zinc-500" aria-live="polite">{matching.length} of {history.records.length} meetings{matching.length > visible.length ? ` · showing ${visible.length}` : ""}</p>
      <ol className="divide-y divide-zinc-100">
        {visible.map((record) => (
          <li key={record.meetingId} className="py-4 first:pt-0 space-y-2">
            <Link to={`/meetings/${record.meetingId}`} className="text-sm font-semibold text-zinc-900 hover:text-teal-700 hover:underline">{formatDate(record.date)} · {record.meetingType}</Link>
            <p className="text-sm leading-relaxed text-zinc-700">{record.summary}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs font-medium text-teal-700">
              <a href={record.minutesUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:underline">Official minutes <ExternalLink className="h-3 w-3" aria-hidden="true" /></a>
              <a href={record.recordingUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:underline">Official recording <ExternalLink className="h-3 w-3" aria-hidden="true" /></a>
            </div>
          </li>
        ))}
      </ol>
      {matching.length === 0 && <p className="text-sm text-zinc-500">No statements match these filters.</p>}
      {matching.length > 6 && <button type="button" onClick={() => setExpanded(!expanded)} className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-semibold hover:bg-zinc-50">{expanded ? "Show fewer meetings" : `Show all ${matching.length} meetings`}</button>}
    </section>
  );
}
