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

type MeetingRole<C extends "government_staff" | "committee_member"> = Omit<DocumentedParticipantRole, "classification"> & { classification: C };

/** A role observed at this meeting establishes no wider service tenure. */
function documentedRole<C extends "government_staff" | "committee_member">(roles: unknown, personId: number, meetingDate: string, classification: C): MeetingRole<C> | null {
  if (!roles || typeof roles !== "object" || Array.isArray(roles)) return null;
  const role = (roles as Record<string, MeetingRole<C>>)[String(personId)];
  if (!role || role.person_id !== personId || role.observed_date !== meetingDate ||
      role.classification !== classification || role.method !== "official_minutes_explicit_role_v1" ||
      !/^[a-f0-9]{64}$/.test(role.source_sha256 || "") || !/^https:\/\//.test(role.source_url || "") ||
      ![role.role, role.organization, role.source_quote, role.source_file].every(value => typeof value === "string" && value.trim().length > 0)) return null;
  return role;
}

export function documentedParticipantRole(roles: unknown, personId: number, meetingDate: string) {
  return documentedRole(roles, personId, meetingDate, "government_staff");
}

export function documentedCommitteeRole(roles: unknown, personId: number, meetingDate: string) {
  return documentedRole(roles, personId, meetingDate, "committee_member");
}
