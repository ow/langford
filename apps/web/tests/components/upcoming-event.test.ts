import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
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
