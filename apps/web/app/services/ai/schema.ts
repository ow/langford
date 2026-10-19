import { z } from "zod";

export type JsonSchema = Record<string, unknown>;

const SAFE_INT = Number.MAX_SAFE_INTEGER;

/**
 * Convert a zod schema into JSON Schema accepted by OpenAI strict structured output:
 * root must be an object, every property required (use `.nullable()` not `.optional()`),
 * `additionalProperties: false`, `anyOf` rather than `oneOf`.
 */
export function toStrictJsonSchema(schema: z.ZodType): JsonSchema {
  const raw = z.toJSONSchema(schema, { target: "draft-7" }) as JsonSchema;
  delete raw.$schema;
  if (raw.type !== "object") {
    throw new Error("Structured output schemas must have an object at the root");
  }
  return normalize(raw, "$") as JsonSchema;
}

function normalize(node: unknown, path: string): unknown {
  if (Array.isArray(node)) return node.map((n, i) => normalize(n, `${path}[${i}]`));
  if (!node || typeof node !== "object") return node;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    if (key === "oneOf") out.anyOf = normalize(value, `${path}.anyOf`);
    else if ((key === "minimum" && value === -SAFE_INT) || (key === "maximum" && value === SAFE_INT)) continue;
    else out[key] = normalize(value, `${path}.${key}`);
  }
  if (out.type === "object" && out.properties) {
    const keys = Object.keys(out.properties as object);
    const required = new Set((out.required as string[] | undefined) ?? []);
    const missing = keys.filter((k) => !required.has(k));
    if (missing.length) {
      throw new Error(
        `Strict schema at ${path}: properties [${missing.join(", ")}] must be required; use .nullable() instead of .optional()`,
      );
    }
    out.additionalProperties = false;
  }
  return out;
}
