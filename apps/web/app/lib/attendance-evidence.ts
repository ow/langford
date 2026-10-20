import { civicToday, membershipIsActiveOn } from "./council-terms";
import type { Attendance, Meeting, Membership } from "./types";

export type AttendanceState = "present" | "absent" | "unknown";
export interface AttendanceSummary {
  rate: number | null;
  total: number;
  attended: number;
  absent: number;
  unknown: number;
  verified: number;
}

/** Legacy AI attendee lists and default modes do not establish attendance. */
export function attendanceEvidence(record: Pick<Attendance, "notes" | "meeting_id" | "person_id">) {
  try {
    const evidence = JSON.parse(record.notes || "null");
    if (
      evidence?.schema !== "council-attendance/v1" ||
      !["original_roster", "original_minutes_attendance"].includes(evidence.method) ||
      !["present", "absent"].includes(evidence.state) ||
      evidence.person_id !== record.person_id || evidence.meeting_id !== record.meeting_id ||
      !/^https:\/\//.test(evidence.source_url) ||
      !/^[a-f0-9]{64}$/.test(evidence.source_sha256) ||
      !Number.isInteger(evidence.source_page) || evidence.source_page < 1 ||
      typeof evidence.source_quote !== "string" || !evidence.source_quote.trim()
    ) return null;
    return evidence as { state: "present" | "absent"; source_url: string; local_date: string };
  } catch {
    return null;
  }
}

export function calculateAttendance(
  person: { id: number; memberships?: Membership[] },
  meetings: Meeting[],
  attendance: Attendance[],
  councilId: number,
  period?: { start: string; end: string },
): AttendanceSummary {
  const today = civicToday();
  const expected = new Map(meetings.filter((meeting) =>
    meeting.organization_id === councilId &&
    !/^(cancelled|canceled)$/i.test(meeting.status || "") &&
    meeting.meeting_date <= today &&
    (!period || (meeting.meeting_date >= period.start && meeting.meeting_date <= period.end)) &&
    (person.memberships || []).some((m) => m.organization_id === councilId && membershipIsActiveOn(m, meeting.meeting_date))
  ).map((meeting) => [meeting.id, meeting]));
  const states = new Map<number, Set<AttendanceState>>();
  for (const record of attendance) {
    const meeting = expected.get(record.meeting_id);
    if (!meeting || record.person_id !== person.id) continue;
    const evidence = attendanceEvidence(record);
    const state = evidence && evidence.local_date === meeting.meeting_date ? evidence.state : "unknown";
    const values = states.get(record.meeting_id) || new Set<AttendanceState>();
    values.add(state);
    states.set(record.meeting_id, values);
  }
  let attended = 0, absent = 0;
  for (const values of states.values()) {
    if (values.size !== 1) continue; // Conflicting records remain unresolved.
    if (values.has("present")) attended++;
    if (values.has("absent")) absent++;
  }
  const total = expected.size;
  const verified = attended + absent;
  const unknown = total - verified;
  return { total, attended, absent, unknown, verified,
    rate: total > 0 && unknown === 0 ? Math.round(attended / total * 100) : null };
}

export function attendanceCoverageText(stats: AttendanceSummary) {
  return `${stats.attended} present · ${stats.absent} absent · ${stats.unknown} unknown. Evidence verified for ${stats.verified} of ${stats.total} meetings.`;
}
