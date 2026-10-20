import { expect, it } from "vitest";
import { serializeMeetingSummary, serializeMeetingDetail } from "../../app/api/serializers/meeting";

it.each([serializeMeetingSummary, (row: any) => serializeMeetingDetail(row,{})])("preserves explicit scheduled cancellation and only public provenance", serialize => {
  const result = serialize({title:"Inauguration",status:"Cancelled",calendar_source_id:7,
    calendar:{source_url:"https://langford.ca/meetings/",verified_at:"2026-10-20T16:00:00Z",start_time:null,internal_notes:"private"}});
  expect(result.status).toBe("Cancelled");
  expect(result.calendar).toEqual({source_url:"https://langford.ca/meetings/",verified_at:"2026-10-20T16:00:00Z",start_time:null});
  expect(JSON.stringify(result)).not.toContain("private");
});
