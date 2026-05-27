import { useEffect } from "react";
import {
  Form,
  Link,
  useActionData,
  useNavigation,
  useRevalidator,
} from "react-router";
import {
  Activity,
  Archive,
  CheckCircle2,
  Database,
  FileText,
  ListChecks,
  Play,
  RadioTower,
  Search,
  StopCircle,
} from "lucide-react";
import type { Route } from "./+types/admin-pipeline";
import { requireAdmin } from "../lib/auth.server";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Input } from "../components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import { formatDate, formatRelativeTime } from "../lib/utils";
import {
  enqueuePipelineJob,
  cancelPipelineJob,
  getPipelineDashboard,
  type PipelineJobType,
} from "../services/pipeline-admin.server";

export async function loader({ request }: Route.LoaderArgs) {
  await requireAdmin(request);
  const supabase = getSupabaseAdminClient();
  const url = new URL(request.url);
  const page = Number(url.searchParams.get("page") || "1");
  const q = url.searchParams.get("q") || "";
  return getPipelineDashboard(supabase, {
    page: Number.isFinite(page) ? page : 1,
    search: q,
    pageSize: 25,
  });
}

export async function action({ request }: Route.ActionArgs) {
  const user = await requireAdmin(request);
  const supabase = getSupabaseAdminClient();
  const formData = await request.formData();
  const jobType = formData.get("job_type") as PipelineJobType | null;
  const intent = formData.get("intent");
  const jobId = formData.get("job_id") as string | null;
  const limitValue = (formData.get("limit") as string | null)?.trim();
  const discoverAll = formData.get("discover_all") === "true" && !limitValue;
  const limit = discoverAll ? undefined : limitValue ? Number(limitValue) : undefined;
  const sourceMeetingId = formData.get("source_meeting_id") as string | null;
  const meetingId = formData.get("meeting_id") as string | null;
  const table = formData.get("table") as string | null;

  if (intent === "cancel_job") {
    if (!jobId) return { error: "Missing job id." };
    try {
      await cancelPipelineJob(supabase, jobId);
      return { success: `Cancelled job #${jobId}.` };
    } catch (error: any) {
      return { error: error.message || "Failed to cancel job." };
    }
  }

  const supportedJobTypes: PipelineJobType[] = [
    "preflight",
    "discover_meetings",
    "sync_documents",
    "sync_media",
    "ingest_meeting",
    "extract_documents",
    "embed_content",
    "diarize_meeting",
  ];

  if (!jobType || !supportedJobTypes.includes(jobType)) {
    return { error: "Unsupported pipeline job type." };
  }

  if (limitValue && (!Number.isInteger(limit) || Number(limit) <= 0)) {
    return { error: "Limit must be a positive whole number." };
  }

  try {
    const args: Record<string, unknown> = {};
    if (limit) args.limit = limit;
    if (sourceMeetingId) args.source_meeting_id = Number(sourceMeetingId);
    if (meetingId) args.meeting_id = Number(meetingId);
    if (table) args.tables = [table];

    const job = await enqueuePipelineJob(
      supabase,
      jobType,
      user.email || user.id,
      args,
    );
    return { success: `Queued ${jobType.replace("_", " ")} job #${job.id}.` };
  } catch (error: any) {
    return { error: error.message || "Failed to queue pipeline job." };
  }
}

function StatusBadge({ status }: { status: string }) {
  const classes: Record<string, string> = {
    queued: "border-amber-200 bg-amber-50 text-amber-800",
    running: "border-blue-200 bg-blue-50 text-blue-800",
    succeeded: "border-emerald-200 bg-emerald-50 text-emerald-800",
    failed: "border-red-200 bg-red-50 text-red-800",
    discovered: "border-sky-200 bg-sky-50 text-sky-800",
    documents_downloaded: "border-emerald-200 bg-emerald-50 text-emerald-800",
    media_downloaded: "border-teal-200 bg-teal-50 text-teal-800",
    ingested: "border-indigo-200 bg-indigo-50 text-indigo-800",
    extracted: "border-fuchsia-200 bg-fuchsia-50 text-fuchsia-800",
    diarized: "border-cyan-200 bg-cyan-50 text-cyan-800",
  };

  return (
    <Badge variant="outline" className={classes[status] || "border-zinc-200"}>
      {status.replaceAll("_", " ")}
    </Badge>
  );
}

function StatCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: number;
  detail: string;
  icon: typeof Database;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-zinc-600">
          {label}
        </CardTitle>
        <Icon className="h-4 w-4 text-zinc-400" />
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold tracking-tight">{value}</div>
        <p className="mt-1 text-xs text-zinc-500">{detail}</p>
      </CardContent>
    </Card>
  );
}

export default function AdminPipeline({ loaderData }: Route.ComponentProps) {
  const {
    municipality,
    counts,
    jobs,
    sourceMeetings,
    sourceMeetingsPage,
    events,
  } = loaderData;
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const revalidator = useRevalidator();
  const isSubmitting = navigation.state === "submitting";
  const hasActiveVisibleJob = sourceMeetings.some((meeting: any) =>
    ["queued", "running"].includes(meeting.latest_job?.status),
  );
  const page = sourceMeetingsPage.page;
  const totalPages = sourceMeetingsPage.totalPages;
  const searchParams = new URLSearchParams();
  if (sourceMeetingsPage.search) {
    searchParams.set("q", sourceMeetingsPage.search);
  }
  const pageHref = (nextPage: number) => {
    const params = new URLSearchParams(searchParams);
    params.set("page", String(nextPage));
    return `/admin/pipeline?${params.toString()}`;
  };

  useEffect(() => {
    if (!hasActiveVisibleJob) return;
    const id = window.setInterval(() => revalidator.revalidate(), 5000);
    return () => window.clearInterval(id);
  }, [hasActiveVisibleJob, revalidator]);

  return (
    <div className="container mx-auto max-w-7xl px-4 py-8">
      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-medium text-zinc-600">
            <RadioTower className="h-3.5 w-3.5" />
            Internal pipeline ops
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-950">
            {municipality.short_name} pipeline
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-600">
            Track source meetings, queue safe pipeline work, and inspect recent
            worker events.
          </p>
        </div>

        <Card className="w-full md:w-[420px]">
          <CardHeader>
            <CardTitle className="text-base">Queue a job</CardTitle>
            <CardDescription>
              Run `uv run python worker.py --once` from `apps/pipeline` to
              process queued jobs. Use source-row Ingest for the normal full
              analysis path.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Form method="post" className="grid gap-3">
              <Button
                type="submit"
                name="job_type"
                value="preflight"
                variant="outline"
                disabled={isSubmitting}
              >
                Run preflight
              </Button>
              <div className="grid grid-cols-[1fr_auto] gap-2">
                <Input
                  name="limit"
                  type="number"
                  min="1"
                  placeholder="Optional limit, blank = all"
                />
                <input type="hidden" name="discover_all" value="true" />
                <Button
                  type="submit"
                  name="job_type"
                  value="discover_meetings"
                  disabled={isSubmitting}
                >
                  <Search className="mr-2 h-4 w-4" />
                  Discover
                </Button>
              </div>
              <Button
                type="submit"
                name="job_type"
                value="sync_documents"
                variant="secondary"
                disabled={isSubmitting}
              >
                <Archive className="mr-2 h-4 w-4" />
                Sync documents
              </Button>
              <div className="grid grid-cols-[1fr_auto] gap-2 border-t pt-3">
                <input type="hidden" name="table" value="document_sections" />
                <div className="rounded-md border border-zinc-200 px-3 py-2 text-sm text-zinc-600">
                  Embed document sections
                </div>
                <Button
                  type="submit"
                  name="job_type"
                  value="embed_content"
                  variant="outline"
                  disabled={isSubmitting}
                >
                  Queue
                </Button>
              </div>
            </Form>
            {actionData?.success && (
              <p className="mt-3 text-sm text-emerald-700">{actionData.success}</p>
            )}
            {actionData?.error && (
              <p className="mt-3 text-sm text-red-700">{actionData.error}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Source meetings"
          value={counts.sourceTotal}
          detail={`${counts.sourcePendingIngest} not linked to app meetings`}
          icon={RadioTower}
        />
        <StatCard
          label="Extracted documents"
          value={counts.appExtractedDocuments}
          detail={`${counts.appSections} searchable sections`}
          icon={FileText}
        />
        <StatCard
          label="App meetings"
          value={counts.appMeetings}
          detail={`${counts.appDocuments} source PDFs`}
          icon={Database}
        />
        <StatCard
          label="Audio output"
          value={counts.appTranscripts}
          detail="Transcript segments from diarization"
          icon={ListChecks}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <CardTitle>Source meeting inventory</CardTitle>
                <CardDescription>
                  {sourceMeetingsPage.total} discovered upstream meetings.
                </CardDescription>
              </div>
              <Form method="get" className="flex gap-2">
                <Input
                  name="q"
                  defaultValue={sourceMeetingsPage.search}
                  placeholder="Search title, type, source id"
                  className="w-64"
                />
                <Button type="submit" variant="outline">
                  <Search className="mr-2 h-4 w-4" />
                  Search
                </Button>
              </Form>
            </div>
            <CardDescription>
              Latest discovered meetings from the upstream source.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Meeting</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Job</TableHead>
                  <TableHead>Readiness</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sourceMeetings.map((meeting: any) => (
                  <TableRow key={meeting.id}>
                    <TableCell>{formatDate(meeting.meeting_date)}</TableCell>
                    <TableCell>
                      <div className="font-medium text-zinc-900">
                        {meeting.title}
                      </div>
                      <div className="text-xs text-zinc-500">
                        {meeting.meeting_type || meeting.source_id}
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={meeting.status} />
                    </TableCell>
                    <TableCell>
                      {meeting.latest_job ? (
                        <div className="space-y-1 text-sm">
                          <Link
                            to={`/admin/pipeline/jobs/${meeting.latest_job.id}`}
                            className="inline-flex items-center gap-1 hover:underline"
                          >
                            <StatusBadge status={meeting.latest_job.status} />
                            <span className="text-xs text-zinc-500">
                              #{meeting.latest_job.id}
                            </span>
                          </Link>
                          <div className="text-xs text-zinc-500">
                            {meeting.latest_job.job_type.replaceAll("_", " ")}
                            {meeting.latest_job.locked_at
                              ? ` · heartbeat ${formatRelativeTime(meeting.latest_job.locked_at)}`
                              : meeting.latest_job.requested_at
                                ? ` · queued ${formatRelativeTime(meeting.latest_job.requested_at)}`
                                : ""}
                          </div>
                          {meeting.latest_job.last_error && (
                            <div
                              className="max-w-[220px] truncate text-xs text-red-700"
                              title={meeting.latest_job.last_error}
                            >
                              {meeting.latest_job.last_error}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-sm text-zinc-400">No job</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {meeting.ingested_meeting_id ? (
                        <div className="space-y-1 text-sm">
                          <span className="inline-flex items-center gap-1 text-emerald-700">
                            <CheckCircle2 className="h-4 w-4" />
                            Meeting #{meeting.ingested_meeting_id}
                          </span>
                          <div className="text-xs text-zinc-500">
                            {meeting.document_count} docs · {meeting.section_count} sections
                          </div>
                        </div>
                      ) : (
                        <span className="text-zinc-400">Not yet</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        {!meeting.ingested_meeting_id && meeting.video_url && (
                          <Form method="post">
                            <input
                              type="hidden"
                              name="source_meeting_id"
                              value={meeting.id}
                            />
                            <Button
                              type="submit"
                              name="job_type"
                              value="sync_media"
                              variant="outline"
                              size="sm"
                              disabled={isSubmitting}
                              title="Download/cache documents and media only. Does not diarize, transcribe, or run AI extraction."
                            >
                              Cache media
                            </Button>
                          </Form>
                        )}
                        {!meeting.ingested_meeting_id && (
                          <Form method="post">
                            <input
                              type="hidden"
                              name="source_meeting_id"
                              value={meeting.id}
                            />
                            <Button
                              type="submit"
                              name="job_type"
                              value="ingest_meeting"
                              variant="outline"
                              size="sm"
                              disabled={isSubmitting}
                            >
                              Ingest full
                            </Button>
                          </Form>
                        )}
                        {meeting.ingested_meeting_id && (
                          <Form method="post">
                            <input
                              type="hidden"
                              name="source_meeting_id"
                              value={meeting.id}
                            />
                            <Button
                              type="submit"
                              name="job_type"
                              value="extract_documents"
                              variant="outline"
                              size="sm"
                              disabled={isSubmitting}
                              title="Recovery action: rerun PDF extraction for an already-ingested meeting."
                            >
                              Rerun docs
                            </Button>
                          </Form>
                        )}
                        {meeting.ingested_meeting_id && meeting.video_url && (
                          <Form method="post">
                            <input
                              type="hidden"
                              name="source_meeting_id"
                              value={meeting.id}
                            />
                            <Button
                              type="submit"
                              name="job_type"
                              value="diarize_meeting"
                              variant="outline"
                              size="sm"
                              disabled={isSubmitting}
                              title="Recovery action: rerun media sync, diarization, transcript ingest, and embeddings."
                            >
                              Rerun audio
                            </Button>
                          </Form>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {sourceMeetings.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-zinc-500">
                      No source meetings recorded yet. Queue discovery to populate this table.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
            <div className="mt-4 flex flex-col gap-3 border-t pt-4 text-sm text-zinc-600 sm:flex-row sm:items-center sm:justify-between">
              <div>
                Page {page} of {totalPages}
                {sourceMeetingsPage.search
                  ? ` for "${sourceMeetingsPage.search}"`
                  : ""}
              </div>
              <div className="flex gap-2">
                <Button asChild variant="outline" size="sm" disabled={page <= 1}>
                  <Link to={pageHref(Math.max(page - 1, 1))}>Previous</Link>
                </Button>
                <Button
                  asChild
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                >
                  <Link to={pageHref(Math.min(page + 1, totalPages))}>Next</Link>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Jobs</CardTitle>
              <CardDescription>Running and queued jobs first, then recent history.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {jobs.map((job: any) => (
                <div
                  key={job.id}
                  className="rounded-lg border border-zinc-200 p-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <Link
                      to={`/admin/pipeline/jobs/${job.id}`}
                      className="font-medium hover:text-blue-700 hover:underline"
                    >
                      #{job.id} {job.job_type.replaceAll("_", " ")}
                    </Link>
                    <StatusBadge status={job.status} />
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
                    <Play className="h-3.5 w-3.5" />
                    {job.requested_at
                      ? formatRelativeTime(job.requested_at)
                      : "Unknown time"}
                    {job.requested_by ? ` by ${job.requested_by}` : ""}
                  </div>
                  {job.status === "running" && job.locked_at && (
                    <div className="mt-1 text-xs text-zinc-500">
                      Last heartbeat {formatRelativeTime(job.locked_at)}
                    </div>
                  )}
                  {job.last_error && (
                    <p className="mt-2 text-xs text-red-700">{job.last_error}</p>
                  )}
                  <div className="mt-3 flex gap-2">
                    <Button asChild variant="outline" size="sm">
                      <Link to={`/admin/pipeline/jobs/${job.id}`}>Details</Link>
                    </Button>
                    {job.status === "queued" && (
                      <Form method="post">
                        <input type="hidden" name="intent" value="cancel_job" />
                        <input type="hidden" name="job_id" value={job.id} />
                        <Button
                          type="submit"
                          variant="outline"
                          size="sm"
                          disabled={isSubmitting}
                        >
                          <StopCircle className="mr-1 h-3.5 w-3.5" />
                          Cancel
                        </Button>
                      </Form>
                    )}
                  </div>
                </div>
              ))}
              {jobs.length === 0 && (
                <p className="text-sm text-zinc-500">No jobs queued yet.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Worker events</CardTitle>
              <CardDescription>Most recent events for visible jobs.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {events.map((event: any) => (
                <div
                  key={event.id}
                  className="rounded-lg border border-zinc-200 p-3 text-sm"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">{event.message}</div>
                    <Badge variant="outline">{event.level}</Badge>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-xs text-zinc-500">
                    <Activity className="h-3.5 w-3.5" />
                    Job #{event.job_id} - {formatRelativeTime(event.created_at)}
                  </div>
                </div>
              ))}
              {events.length === 0 && (
                <p className="text-sm text-zinc-500">No worker events yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
