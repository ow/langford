import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { useSpeakerStats } from "../../app/hooks/useSpeakerStats";
import { MeetingAttendance } from "../../app/components/meeting/MeetingSidebar";
import type { Attendance, Membership, Person, TranscriptSegment } from "../../app/lib/types";

const membership = (classification: string, start = "2020-01-01", end?: string): Membership => ({
  id: 1, person_id: 1, organization_id: 1, role: classification.toLowerCase() === "council" ? "Councillor" : "Director",
  start_date: start, end_date: end, created_at: "", organization: { id: 1, name: classification, classification: classification as NonNullable<Membership["organization"]>["classification"], created_at: "" },
});
const person = (id: number, name: string, memberships: Membership[] = []): Person => ({ id, name, memberships, is_councillor: false, created_at: "" });
const attendance = (p: Person, mode: string): Attendance => ({ id: p.id, person_id: p.id, meeting_id: 1, attendance_mode: mode, person: p, created_at: "" });
const segment = (p: Person | null, name: string, start: number, end: number): TranscriptSegment => ({
  id: start, meeting_id: 1, person_id: p?.id ?? null, person: p ?? undefined, speaker_name: name,
  start_time: start, end_time: end, agenda_item_id: null, matter_id: null, motion_id: null,
  attribution_source: "machine", is_verified: false, is_procedural: false, text_content: "Statement", created_at: "",
});

function renderStats(options: Parameters<typeof useSpeakerStats>[0]) {
  let result!: ReturnType<typeof useSpeakerStats>;
  function Harness() {
    result = useSpeakerStats(options);
    return createElement(MeetingAttendance, result);
  }
  const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Harness)));
  return { result, html };
}
const resolveSpeakerName = (seg: { person?: { name: string } | null; speaker_name?: string | null }) => seg.person?.name || seg.speaker_name || "Unknown Speaker";

describe("meeting participant evidence", () => {
  it("does not invent regrets, count absences, or hide conflicting transcript attribution", () => {
    const present = person(1, "Alice Present", [membership("Council")]);
    const absent = person(2, "Bob Recorded Absent", [membership("Council")]);
    const speechOnly = person(3, "Cara Speech Only", [membership("Council")]);
    const missing = person(4, "Dana Missing", [membership("Council")]);
    const unknown = person(5, "Evan Unknown Attendance", [membership("Council")]);
    const unknownWithoutSpeech = person(6, "Frank Unknown Attendance", [membership("Council")]);
    const { result, html } = renderStats({
      transcript: [segment(absent, absent.name, 0, 4), segment(speechOnly, speechOnly.name, 5, 15), segment(unknown, unknown.name, 15, 20)],
      attendance: [attendance(present, "Remote"), attendance(absent, "Regrets"), attendance(unknown, "Unknown"), attendance(unknownWithoutSpeech, "Unknown")],
      activeCouncilMemberIds: [1, 2, 3, 4, 5], people: { 1: present, 2: absent, 3: speechOnly, 4: missing, 5: unknown },
      meetingDate: "2024-06-01", resolveSpeakerName,
    });
    expect(result.attendanceGroups.council.map(r => r.resolvedName)).not.toContain(missing.name);
    expect(result.participantCount).toBe(3);
    expect(result.attendanceGroups.council.find(r => r.person_id === 2)).toMatchObject({ attendance_mode: "Regrets", isParticipant: false, hasTranscriptEvidence: true });
    expect(result.attendanceGroups.council.find(r => r.person_id === 5)).toMatchObject({ participationEvidence: "transcript_only", isParticipant: true });
    expect(result.attendanceGroups.council.find(r => r.person_id === 6)).toMatchObject({ participationEvidence: "unknown", isParticipant: false });
    expect(html).toContain("Attendance unknown");
    expect(html).toContain("Transcript only");
    expect(html).toContain("Regrets");
    expect(html).toContain("Transcript attribution conflicts");
    expect(html).not.toContain("of 5 present");
  });

  it("requires a canonical person link, not an alias or an unlinked full name, to count speech as participation", () => {
    const zero = person(8, "Zero Interval");
    const { result } = renderStats({
      transcript: [segment(null, "SPEAKER_00", 0, 10), segment(null, "Speaker 1", 10, 20), segment(null, "Unknown Speaker", 20, 30), segment(null, "SPEAKER_A", 30, 31), segment(null, "Public Speaker", 31, 32), segment(null, "UNKNOWN_SPEAKER", 32, 33),
        segment(zero, zero.name, 31, 31), segment(null, "Negative Interval", 40, 35), segment(null, "Not Finite", 0, Infinity), segment(null, "Lisa Foxall", 45, 50)],
      attendance: [], meetingDate: "2024-06-01",
      resolveSpeakerName: seg => seg.speaker_name === "SPEAKER_00" ? "Lisa Foxall" : resolveSpeakerName(seg),
    });
    expect(result.attendanceGroups.others).toEqual([]);
    expect(result.participantCount).toBe(0);
    expect(result.speakerStats.totalTime).toBe(38);
  });

  it("keeps unlinked name evidence out of canonical speaking totals without merging same-name people", () => {
    const lisa = person(20, "Lisa Foxall");
    const unique = renderStats({ transcript: [segment(null, lisa.name, 0, 5), segment(lisa, lisa.name, 5, 10)],
      attendance: [], meetingDate: "2024-06-01", resolveSpeakerName }).result;
    expect(unique.participantCount).toBe(1);
    expect(unique.attendanceGroups.others.map(r => r.person_id)).toEqual([20]);
    expect(unique.attendanceGroups.others[0].speakingSeconds).toBe(5);
    const first = person(21, "Alex Smith", [membership("Council")]), second = person(22, "Alex Smith", [membership("Council")]);
    const ambiguousRender = renderStats({ transcript: [segment(null, first.name, 0, 5), segment(first, first.name, 5, 10), segment(second, second.name, 10, 15)],
      attendance: [], meetingDate: "2024-06-01", resolveSpeakerName });
    const ambiguous = ambiguousRender.result;
    expect(ambiguous.participantCount).toBe(2);
    expect(ambiguous.attendanceGroups.council.map(r => [r.person_id, r.speakingSeconds])).toEqual([[21, 5], [22, 5]]);
    expect(ambiguousRender.html).not.toContain("15s");
    expect(ambiguousRender.html.match(/Transcript only · 5s/g)).toHaveLength(2);
  });

  it("classifies staff using the office active on the meeting date and case-insensitive classifications", () => {
    const former = person(10, "Former Director", [membership("Staff", "2010-01-01", "2020-12-31")]);
    const current = person(11, "Current Staff Member", [{ ...membership("staff", "2021-01-01"), role: "Employee" }]);
    const councillor = person(12, "Current Councillor", [{ ...membership("council", "2021-01-01"), role: "Member" }]);
    const { result } = renderStats({ transcript: [], attendance: [attendance(former, "In Person"), attendance(current, "In Person"), attendance(councillor, "In Person")],
      meetingDate: "2024-06-01", resolveSpeakerName });
    expect(result.attendanceGroups.staff.map(r => r.person_id)).toEqual([11]);
    expect(result.attendanceGroups.others.map(r => r.person_id)).toEqual([10]);
    expect(result.attendanceGroups.council.map(r => r.person_id)).toEqual([12]);
    expect(result.getPersonRole(former)).toBeNull();
  });
});
