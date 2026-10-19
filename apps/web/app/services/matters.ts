import { parseRelatedAddresses } from "../lib/addresses";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Matter, Municipality, AgendaItem } from "../lib/types";

const DEFAULT_MUNICIPALITY = { id: 1 } as Municipality;

function isMunicipality(value: unknown): value is Municipality {
  return !!value && typeof value === "object" && "id" in value;
}

function resolveMunicipalityAndId(
  municipalityOrId: Municipality | string,
  id?: string,
): [Municipality, string] {
  if (isMunicipality(municipalityOrId)) {
    if (!id) throw new Error("Missing id");
    return [municipalityOrId, id];
  }
  return [DEFAULT_MUNICIPALITY, municipalityOrId];
}

function resolveMunicipalityAndIds(
  municipalityOrIds: Municipality | number[],
  ids?: number[],
): [Municipality, number[]] {
  if (isMunicipality(municipalityOrIds)) {
    return [municipalityOrIds, ids || []];
  }
  return [DEFAULT_MUNICIPALITY, municipalityOrIds];
}

export async function getMatters(
  supabase: SupabaseClient,
  municipality: Municipality = DEFAULT_MUNICIPALITY,
) {
  const allData: any[] = [];
  const pageSize = 1000;
  let offset = 0;

  while (true) {
    const { data, error } = await supabase
      .from("matters")
      .select(
        `
        id,
        title,
        identifier,
        category,
        status,
        description,
        plain_english_summary,
        first_seen,
        last_seen,
        geo_location,
        meta,
        bylaw:bylaws(title, bylaw_number),
        agenda_items(related_address, geo_location)
      `,
      )
      .eq("municipality_id", municipality.id)
      .is("meta->>canonical_matter_id", null)
      .is("meta->>hidden", null)
      .order("last_seen", { ascending: false, nullsFirst: false })
      .range(offset, offset + pageSize - 1);

    if (error) throw error;
    if (!data || data.length === 0) break;

    allData.push(...data);
    offset += pageSize;

    if (data.length < pageSize) break;
  }

  // Retained source IDs may hold the only location evidence for a matter.
  // Fetch those agenda links before aggregating map/filter fields, while the
  // canonical list itself remains filtered and paginated in the database.
  const canonicalById = new Map(allData.map((matter) => [matter.id, matter]));
  const aliasLocations = new Map<number, any[]>();
  const aliasIds: number[] = [...new Set<number>(allData.flatMap((matter) =>
    (matter.meta?.merged_matter_ids || []).filter((value: unknown): value is number =>
      Number.isSafeInteger(value) && Number(value) > 0),
  ))];
  for (let start = 0; start < aliasIds.length; start += 100) {
    const { data: aliases, error } = await supabase.from("matters")
      .select("id, meta, geo_location, agenda_items(related_address, geo_location)")
      .eq("municipality_id", municipality.id).in("id", aliasIds.slice(start, start + 100));
    if (error) throw error;
    for (const alias of aliases || []) {
      const canonical = canonicalById.get(Number(alias.meta?.canonical_matter_id));
      if (canonical && canonical.meta?.merged_matter_ids?.includes(alias.id)) {
        canonical.agenda_items = [...(canonical.agenda_items || []), ...(alias.agenda_items || [])];
        if (alias.geo_location) aliasLocations.set(canonical.id, [...(aliasLocations.get(canonical.id) || []), alias.geo_location]);
      }
    }
  }

  return allData.map((matter) => {
    // Aggregate addresses from agenda items
    const addresses = new Set<string>();
    (matter.agenda_items || []).forEach((item: any) => {
      parseRelatedAddresses(item.related_address).forEach((addr) => addresses.add(addr));
    });

    // Aggregate locations from matter + agenda items
    const locationsMap = new Map<string, any>();
    for (const mGeo of [matter.geo_location, ...(aliasLocations.get(matter.id) || [])]) {
      if (mGeo?.lat && mGeo?.lng) {
        locationsMap.set(`${mGeo.lat},${mGeo.lng}`, mGeo);
      }
    }
    (matter.agenda_items || []).forEach((item: any) => {
      const g = item.geo_location;
      if (g?.lat && g?.lng) {
        locationsMap.set(`${g.lat},${g.lng}`, {
          ...g,
          address: parseRelatedAddresses(item.related_address)[0],
        });
      }
    });

    // Exclude agenda_items from response
    const { agenda_items, geo_location, ...rest } = matter;
    return {
      ...rest,
      addresses: Array.from(addresses),
      locations: Array.from(locationsMap.values()),
    };
  });
}

export async function getMatterById(
  supabase: SupabaseClient,
  id: string,
): Promise<Matter & { agenda_items: (AgendaItem & { meetings: any; motions: any })[] }>;
export async function getMatterById(
  supabase: SupabaseClient,
  municipality: Municipality,
  id: string,
): Promise<Matter & { agenda_items: (AgendaItem & { meetings: any; motions: any })[] }>;
export async function getMatterById(
  supabase: SupabaseClient,
  municipalityOrId: Municipality | string,
  maybeId?: string,
) {
  const [municipality, id] = resolveMunicipalityAndId(
    municipalityOrId,
    maybeId,
  );
  const detailSelection = "id, title, identifier, description, category, plain_english_summary, status, first_seen, last_seen, bylaw_id, meta, created_at, bylaw:bylaws(id, title, bylaw_number, year, category, status, plain_english_summary, full_text, created_at), agenda_items(id, meeting_id, item_order, title, description, category, debate_summary, plain_english_summary, is_controversial, is_consent_agenda, discussion_start_time, financial_cost, funding_source, related_address, geo_location, matter_status_snapshot, meta, meetings(id, title, meeting_date, organizations(name)), motions(id, meeting_id, agenda_item_id, mover, seconder, mover_id, seconder_id, text_content, plain_english_summary, result, disposition, yes_votes, no_votes, abstain_votes, absent_votes, votes(id, motion_id, person_id, vote, recusal_reason, person:people(id, name, image_url))))";
  const load = async (matterId: string) => {
    const { data, error } = await supabase.from("matters").select(detailSelection)
      .eq("id", matterId).eq("municipality_id", municipality.id).single();
    if (error) throw error;
    return data;
  };
  let matter = await load(id);
  const visited = new Set<number>();
  while (matter.meta?.canonical_matter_id) {
    if (visited.has(matter.id) || visited.size >= 8) throw new Error("Invalid matter alias chain");
    visited.add(matter.id);
    matter = await load(String(matter.meta.canonical_matter_id));
  }
  const mergedIds: number[] = (matter.meta?.merged_matter_ids || [])
    .filter((value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0);
  if (mergedIds.length) {
    const { data: aliases, error } = await supabase.from("matters")
      .select(detailSelection).eq("municipality_id", municipality.id).in("id", mergedIds);
    if (error) throw error;
    const historicalItems = (aliases || [])
      .filter((alias: any) => Number(alias.meta?.canonical_matter_id) === matter.id)
      .flatMap((alias: any) => alias.agenda_items || []);
    matter.agenda_items = [...(matter.agenda_items || []), ...historicalItems];
  }

  return matter as unknown as Matter & {
    agenda_items: (AgendaItem & {
      meetings: any;
      motions: any;
    })[];
  };
}

export async function getDocumentsForAgendaItems(
  supabase: SupabaseClient,
  agendaItemIds: number[],
): Promise<any[]>;
export async function getDocumentsForAgendaItems(
  supabase: SupabaseClient,
  municipality: Municipality,
  agendaItemIds: number[],
): Promise<any[]>;
export async function getDocumentsForAgendaItems(
  supabase: SupabaseClient,
  municipalityOrAgendaItemIds: Municipality | number[],
  maybeAgendaItemIds?: number[],
) {
  const [, agendaItemIds] = resolveMunicipalityAndIds(
    municipalityOrAgendaItemIds,
    maybeAgendaItemIds,
  );
  if (agendaItemIds.length === 0) return [];
  const { data, error } = await supabase
    .from("extracted_documents")
    .select("id, document_id, agenda_item_id, title, document_type, page_start, page_end")
    .in("agenda_item_id", agendaItemIds)
    .order("agenda_item_id")
    .order("page_start", { ascending: true, nullsFirst: false });
  if (error) {
    console.error("Error fetching documents for agenda items:", error);
    return [];
  }
  return data ?? [];
}

export async function getMatterEvidence(
  supabase: SupabaseClient,
  matterId: string | number,
  mergedMatterIds: number[] = [],
) {
  const { data, error } = await supabase
    .from("matter_evidence")
    .select(
      "id, evidence_type, confidence, reason, agenda_item_id, document_section_id, agenda_item:agenda_items(id, meeting_id, item_order, title, meetings(id, title, meeting_date, organizations(name))), document_section:document_sections(id, section_title, section_text, page_start, page_end, document_id, agenda_item_id, document:documents(id, title, meeting_id, meetings(id, title, meeting_date, organizations(name))))",
    )
    .in("matter_id", [Number(matterId), ...mergedMatterIds])
    .order("confidence", { ascending: false })
    .order("id", { ascending: true })
    .limit(25);

  if (error) {
    console.error("Error fetching matter evidence:", error);
    return [];
  }

  return data ?? [];
}

export async function getHotTopics(
  supabase: SupabaseClient,
  municipality: Municipality = DEFAULT_MUNICIPALITY,
) {
  const { data, error } = await supabase
    .from("agenda_items")
    .select(
      "id, meeting_id, title, description, category, debate_summary, plain_english_summary, is_controversial, discussion_start_time, created_at, meetings!inner(id, title, meeting_date, municipality_id, organizations(name))",
    )
    .eq("is_controversial", true)
    .eq("meetings.municipality_id", municipality.id)
    .order("created_at", { ascending: false });

  if (error) throw error;
  return data as any[];
}

export async function getFiscalData(supabase: SupabaseClient) {
  const { data: items, error } = await supabase
    .from("agenda_items")
    .select(
      "id, meeting_id, title, description, category, financial_cost, funding_source, created_at, meetings(id, title, meeting_date, organizations(name))",
    )
    .not("financial_cost", "is", null)
    .order("financial_cost", { ascending: false });

  if (error) throw error;
  return items || [];
}

/**
 * Story context for a matter: other matters that are steps of the same
 * initiative, and mixed-topic agenda items (notices of motion, presentations,
 * public participation) that discussed it. Written by the pipeline's
 * matter_links step.
 */
export async function getMatterStory(supabase: SupabaseClient, matterId: number) {
  const { data: links, error } = await supabase
    .from("matter_links")
    .select("kind, matter_id, related_matter_id, agenda_item_id, confidence")
    .eq("hidden", false)
    .or(`matter_id.eq.${matterId},related_matter_id.eq.${matterId}`);
  if (error) {
    console.error("Error fetching matter links:", error);
    return { related: [], mentions: [] };
  }
  const relatedIds = [
    ...new Set(
      (links || [])
        .filter((l: any) => l.kind === "related_matter")
        .map((l: any) => (l.matter_id === matterId ? l.related_matter_id : l.matter_id)),
    ),
  ];
  const mentionIds = (links || [])
    .filter((l: any) => l.kind === "mention" && l.matter_id === matterId)
    .map((l: any) => l.agenda_item_id);

  const [related, mentions] = await Promise.all([
    relatedIds.length
      ? supabase
          .from("matters")
          .select("id, title, status, first_seen, last_seen, meta, plain_english_summary")
          .in("id", relatedIds)
          .is("meta->>canonical_matter_id", null)
      : Promise.resolve({ data: [] as any[] }),
    mentionIds.length
      ? supabase
          .from("agenda_items")
          .select("id, meeting_id, title, plain_english_summary, meta, meetings(id, meeting_date, title, organizations(name))")
          .in("id", mentionIds)
      : Promise.resolve({ data: [] as any[] }),
  ]);
  return {
    related: ((related as any).data || []).sort((a: any, b: any) =>
      String(a.first_seen).localeCompare(String(b.first_seen)),
    ),
    mentions: (mentions as any).data || [],
  };
}
