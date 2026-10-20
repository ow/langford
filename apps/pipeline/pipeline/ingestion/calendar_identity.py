"""Attach published documents to a verified calendar identity, never first-match by date."""


def find_scheduled_meeting(client, municipality_id, archive_path, meeting_date, meeting_type):
    sources = (client.table("source_meetings").select("id,ingested_meeting_id,source_type")
               .eq("municipality_id", municipality_id).eq("archive_path", archive_path)
               .execute().data or [])
    ids = {row["ingested_meeting_id"] for row in sources if row.get("ingested_meeting_id")}
    # A calendar-only record may predate the first published source discovery.
    # The service-only RPC safely links its GUID even after the event date passed.
    if not ids and len(sources) == 1 and sources[0].get("source_type") == "escribe":
        linked = client.rpc("reconcile_calendar_source", {
            "p_source_meeting_id": sources[0]["id"],
        }).execute().data
        if linked:
            ids.add(linked)
    if len(ids) > 1:
        raise RuntimeError("Ambiguous calendar source mapping; review before ingestion")
    if ids:
        rows = (client.table("meetings").select("id,video_url,meta,calendar_source_id,organization_id,type,title")
                .eq("municipality_id", municipality_id).eq("id", next(iter(ids))).execute().data or [])
        if len(rows) != 1:
            raise RuntimeError("Calendar source mapping has no matching municipality record")
        return rows[0]
    # Legacy placeholders only. Verified calendar entries require their source identity.
    rows = (client.table("meetings").select("id,video_url,meta,calendar_source_id,organization_id,type,title")
            .eq("municipality_id", municipality_id).eq("meeting_date", meeting_date)
            .eq("type", meeting_type).is_("archive_path", "null")
            .is_("calendar_source_id", "null").execute().data or [])
    if len(rows) > 1:
        raise RuntimeError("Ambiguous legacy scheduled meetings; review before ingestion")
    return rows[0] if rows else None
