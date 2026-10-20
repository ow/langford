/** Only explicitly verified calendar records bypass document readiness. */
export const PUBLIC_MEETING_FILTER =
  "has_agenda.eq.true,has_minutes.eq.true,has_transcript.eq.true,summary.not.is.null,calendar_source_id.not.is.null";
