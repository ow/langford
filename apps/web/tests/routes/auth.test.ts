import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { action as signup, loader as signupLoader } from "~/routes/signup";
import { action as login } from "~/routes/login";
import { publicSignupsEnabled } from "~/lib/features.server";
import { requireAdmin } from "~/lib/auth.server";

const mocks = vi.hoisted(() => ({ signUp: vi.fn(), signIn: vi.fn(), insert: vi.fn(), getUser: vi.fn() }));
vi.mock("~/lib/supabase.server", () => ({
  createSupabaseServerClient: () => ({
    supabase: {
      auth: { signUp: mocks.signUp, signInWithPassword: mocks.signIn, getUser: mocks.getUser },
      from: () => ({ insert: mocks.insert }),
    },
    headers: new Headers({ "Set-Cookie": "session=test; HttpOnly" }),
  }),
}));

function args(path = "/signup", fields: Record<string, string> = {}, origin = "https://example.com", success = true): any {
  return {
    request: new Request(`https://example.com${path}`, {
      method: "POST", headers: { Origin: origin, "CF-Connecting-IP": "192.0.2.1" },
      body: new URLSearchParams({ email: "reader@example.com", password: "test-password", ...fields }),
    }),
    context: { cloudflare: { env: { SIGNUP_RATE_LIMITER: { limit: vi.fn().mockResolvedValue({ success }) } } } },
    params: {},
  };
}

afterEach(() => vi.unstubAllEnvs());

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv("ENABLE_SIGNUPS", "true");
  vi.stubEnv("PUBLIC_SIGNUP_LINKS", "false");
  vi.stubEnv("ADMIN_EMAILS", "");
  vi.stubEnv("ADMIN_EMAIL", "");
  mocks.signUp.mockResolvedValue({ data: { user: { id: "reader" }, session: {} }, error: null });
  mocks.signIn.mockResolvedValue({ error: null });
  mocks.insert.mockResolvedValue({ error: null });
  mocks.getUser.mockResolvedValue({ data: { user: { id: "reader", email: "reader@example.com" } } });
});

it("accepts direct signup without public links and preserves cookies and the local destination", async () => {
  expect(await signupLoader({} as any)).toEqual({ signupsEnabled: true });
  expect(publicSignupsEnabled()).toBe(false);
  const response = await signup(args("/signup?redirectTo=%2Fmatters%3Fq%3Dparks", { displayName: "Reader", role: "admin", is_admin: "true" }));
  expect(response).toBeInstanceOf(Response);
  expect((response as Response).headers.get("Location")).toBe("/matters?q=parks");
  expect((response as Response).headers.get("Set-Cookie")).toContain("session=test");
  expect(mocks.signUp).toHaveBeenCalledWith({ email: "reader@example.com", password: "test-password", options: { data: { display_name: "Reader" } } });
});

it("keeps the server-side signup kill switch", async () => {
  vi.stubEnv("ENABLE_SIGNUPS", "false");
  expect(await signupLoader({} as any)).toEqual({ signupsEnabled: false });
  expect(await signup(args())).toHaveProperty("error");
  expect(mocks.signUp).not.toHaveBeenCalled();
});

it.each(["https://evil.test/", "//evil.test/", "/\\evil.test/", "javascript:alert(1)", "/\tevil.test/"])("rejects unsafe return URL %s for both auth actions", async (target) => {
  const query = `?redirectTo=${encodeURIComponent(target)}`;
  expect((await signup(args(`/signup${query}`)) as Response).headers.get("Location")).toBe("/onboarding");
  expect((await login(args(`/login${query}`)) as Response).headers.get("Location")).toBe("/");
});

it.each([
  ["cross-site", () => args("/signup", {}, "https://evil.test")],
  ["honeypot", () => args("/signup", { website: "bot" })],
  ["invalid email", () => args("/signup", { email: "invalid" })],
  ["short password", () => args("/signup", { password: "short" })],
  ["limited", () => args("/signup", {}, "https://example.com", false)],
  ["missing limiter", () => ({ ...args(), context: {} })],
])("stops %s submissions before Supabase", async (_, input) => {
  expect(await signup(input())).toHaveProperty("error");
  expect(mocks.signUp).not.toHaveBeenCalled();
});

it("does not create a profile before confirmation and returns auth cookies", async () => {
  mocks.signUp.mockResolvedValue({ data: { user: { id: "reader" }, session: null }, error: null });
  const result: any = await signup(args());
  expect(result.data).toMatchObject({ success: true, confirmEmail: true });
  expect(new Headers(result.init.headers).get("Set-Cookie")).toContain("session=test");
  expect(mocks.insert).not.toHaveBeenCalled();
});

it("honors provider signup restrictions", async () => {
  mocks.signUp.mockResolvedValue({ data: { user: null, session: null }, error: { message: "Signups not allowed" } });
  expect(await signup(args())).toEqual({ error: "Signups not allowed" });
  expect(mocks.insert).not.toHaveBeenCalled();
});

it("never makes an ordinary reader admin when no allowlist is configured", async () => {
  await expect(requireAdmin(new Request("https://example.com/admin"))).rejects.toMatchObject({ status: 403 });
});

it.each([
  ["true", "true", true, true],
  ["true", "false", true, false],
  ["false", "true", false, false],
  ["false", "false", false, false],
])("signup switch %s and public links %s control separate behaviors", async (enabled, links, accepts, advertised) => {
  vi.stubEnv("ENABLE_SIGNUPS", enabled);
  vi.stubEnv("PUBLIC_SIGNUP_LINKS", links);
  expect(await signupLoader({} as any)).toEqual({ signupsEnabled: accepts });
  expect(publicSignupsEnabled()).toBe(advertised);
});

it("fails closed when the signup limiter is unavailable", async () => {
  const input = args();
  input.context.cloudflare.env.SIGNUP_RATE_LIMITER.limit.mockRejectedValue(new Error("offline"));
  expect(await signup(input)).toHaveProperty("error");
  expect(mocks.signUp).not.toHaveBeenCalled();
});

it("denies an ordinary reader even when an admin allowlist exists", async () => {
  vi.stubEnv("ADMIN_EMAILS", "admin@example.com");
  await expect(requireAdmin(new Request("https://example.com/admin"))).rejects.toMatchObject({ status: 403 });
});
