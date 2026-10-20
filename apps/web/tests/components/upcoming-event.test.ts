import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { CalendarProvenance } from "../../app/components/calendar-provenance";
import { expect, it, vi } from "vitest";
import { IncomingCouncilSection } from "../../app/components/home/incoming-council-section";
import { UpcomingMeetingSection } from "../../app/components/home/upcoming-meeting-section";

it("presents inauguration as the next event without implying a regular council meeting", () => {
  const html = renderToStaticMarkup(h(MemoryRouter, null,
    h(UpcomingMeetingSection, { meeting: {
      id: 1, title: "Inauguration", type: "Inauguration",
      meeting_date: "2026-11-02", agendaPreview: [],
    } }),
  ));
  expect(html).toContain("Next event");
  expect(html).toContain("Inauguration");
  expect(html).toContain("November 2, 2026");
  expect(html).toContain("View event");
  expect(html).not.toContain("Next meeting");
});


it("calls the November 2 incoming-council event Inauguration", () => {
  const html = renderToStaticMarkup(h(MemoryRouter, null,
    h(IncomingCouncilSection, { council: {
      termId: 2, startDate: "2026-11-02", preliminary: false, members: [],
    } }),
  ));
  expect(html).toContain("Inauguration is scheduled for November 2, 2026.");
  expect(html).not.toMatch(/inaugural meeting|first council meeting/i);
});

it("shows source, freshness and unknown ceremony time for a verified calendar event", () => {
  const html = renderToStaticMarkup(h(MemoryRouter, null,
    h(UpcomingMeetingSection, { meeting: {
      id: 1, title: "Inauguration", type: "Inauguration", calendar_source_id: 7,
      meeting_date: "2026-11-02", agendaPreview: [], meta: { calendar: {
        source_url:"https://langford.ca/meetings/", verified_at:new Date().toISOString(), start_time:null,
      } },
    } }),
  ));
  expect(html).toContain("Scheduled");
  expect(html).toContain('href="https://langford.ca/meetings/"');
  expect(html).toContain("Schedule checked");
  expect(html).toContain("Time not published");
  expect(html).toContain("Agenda not yet published");
  expect(html).not.toContain("Processing");
});


it.each([
  ["Planned", "Scheduled date passed; occurrence unconfirmed"],
  ["Cancelled", "Cancelled"],
])("keeps past calendar-only %s events truthful and visibly stale", (status, label) => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-11-04T16:00:00Z"));
  try {
    const html = renderToStaticMarkup(h(CalendarProvenance, {meeting: {
      calendar_source_id:7, meeting_date:"2026-11-02",status,
      meta:{calendar:{source_url:"https://langford.ca/meetings/",verified_at:"2026-10-20T16:00:00Z",start_time:null}},
    }}));
    expect(html).toContain(label);
    expect(html).toContain("Schedule check overdue");
    expect(html).not.toMatch(/Completed|Processing/);
  } finally { vi.useRealTimers(); }
});
