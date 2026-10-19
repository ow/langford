export interface DocumentedParticipantRole {
  person_id: number;
  classification: "government_staff";
  role: string;
  organization: string;
  observed_date: string;
  source_file: string;
  source_sha256: string;
  source_url: string;
  source_quote: string;
  method: "official_minutes_explicit_role_v1";
}

/** A role observed at this meeting establishes no wider employment tenure. */
export function documentedParticipantRole(roles: unknown, personId: number, meetingDate: string): DocumentedParticipantRole | null {
  if (!roles || typeof roles !== "object" || Array.isArray(roles)) return null;
  const role = (roles as Record<string, DocumentedParticipantRole>)[String(personId)];
  if (!role || role.person_id !== personId || role.observed_date !== meetingDate ||
      role.classification !== "government_staff" || role.method !== "official_minutes_explicit_role_v1" ||
      !/^[a-f0-9]{64}$/.test(role.source_sha256 || "") || !/^https:\/\//.test(role.source_url || "") ||
      ![role.role, role.organization, role.source_quote, role.source_file].every(value => typeof value === "string" && value.trim().length > 0)) return null;
  return role;
}
