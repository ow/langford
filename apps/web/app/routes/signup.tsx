import { Form, Link, redirect, useActionData, useLoaderData } from "react-router";
import type { Route } from "./+types/signup";
import { createSupabaseServerClient } from "../lib/supabase.server";
import { signupsEnabled } from "../lib/features.server";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";

export async function loader(_: Route.LoaderArgs) {
  return { signupsEnabled: signupsEnabled() };
}

export async function action({ request }: Route.ActionArgs) {
  if (!signupsEnabled()) {
    return { error: "Sign-ups are closed for now." };
  }

  const formData = await request.formData();
  const email = formData.get("email") as string;
  const password = formData.get("password") as string;
  const displayName = formData.get("displayName") as string;
  const url = new URL(request.url);
  const redirectTo = url.searchParams.get("redirectTo") || "/onboarding";

  const { supabase, headers } = createSupabaseServerClient(request);

  // Sign up
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: { display_name: displayName },
    },
  });

  if (error) {
    return { error: error.message };
  }

  // Create user profile
  if (data.user) {
    const { error: profileError } = await supabase
      .from("user_profiles")
      .insert({
        id: data.user.id,
        display_name: displayName || null,
        notification_email: email,
      });

    if (profileError) {
      console.error("Error creating user profile:", profileError);
    }
  }

  // If email confirmation is required, tell the user
  if (data.user && !data.session) {
    return { success: true, confirmEmail: true };
  }

  return redirect(redirectTo, { headers });
}

const fieldClass = "h-10 bg-white";
const labelClass = "text-sm font-medium text-zinc-700";

export default function Signup() {
  const { signupsEnabled } = useLoaderData<typeof loader>();
  const actionData = useActionData<typeof action>();
  const error =
    actionData && "error" in actionData ? actionData.error : null;

  if (actionData && "success" in actionData && actionData.confirmEmail) {
    return (
      <div className="min-h-screen bg-zinc-50">
        <div className="container mx-auto max-w-md px-4 py-16">
          <div
            role="status"
            className="space-y-3 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm sm:p-8"
          >
            <h1 className="text-2xl font-extrabold tracking-tight text-zinc-900">
              Check your email
            </h1>
            <p className="text-sm leading-relaxed text-zinc-600">
              We sent you a confirmation link. Open it to activate your account,
              then sign in to choose which alerts you want.
            </p>
            <p className="text-sm text-zinc-500">
              Nothing arrived after a few minutes? Check your spam folder.
            </p>
            <div className="pt-2">
              <Link
                to="/login"
                className="text-sm font-semibold text-brand-700 hover:text-brand-800 hover:underline"
              >
                Go to sign in
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!signupsEnabled) {
    return (
      <div className="min-h-screen bg-zinc-50">
        <div className="container mx-auto max-w-md px-4 py-16">
          <div className="space-y-3 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm sm:p-8">
            <h1 className="text-2xl font-extrabold tracking-tight text-zinc-900">
              Sign-ups are closed for now
            </h1>
            <p className="text-sm leading-relaxed text-zinc-600">
              We're not creating new accounts at the moment, so email alerts
              aren't available yet. Everything else is open to everyone, no
              account needed: browse meetings, read up on matters and search what
              council has discussed.
            </p>
            <div className="flex flex-wrap gap-x-5 gap-y-2 pt-2 text-sm">
              <Link
                to="/meetings"
                className="font-semibold text-brand-700 hover:text-brand-800 hover:underline"
              >
                Browse meetings
              </Link>
              <Link
                to="/login"
                className="font-medium text-zinc-500 hover:text-zinc-800 hover:underline"
              >
                Already have an account? Sign in
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-md px-4 py-16">
        <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm sm:p-8">
          <div className="mb-6 space-y-2">
            <h1 className="text-2xl font-extrabold tracking-tight text-zinc-900">
              Create an account
            </h1>
            <p className="text-sm leading-relaxed text-zinc-600">
              Alerts are short emails about council business you care about:
              a matter you follow coming back to an agenda, a topic you picked
              being discussed, or a decision near your home. You choose what to
              follow, and you can change it any time.
            </p>
          </div>

          <Form method="post" className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="displayName" className={labelClass}>
                Name <span className="font-normal text-zinc-400">(optional)</span>
              </label>
              <Input
                id="displayName"
                type="text"
                name="displayName"
                autoComplete="name"
                className={fieldClass}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="email" className={labelClass}>
                Email
              </label>
              <Input
                id="email"
                type="email"
                name="email"
                autoComplete="email"
                required
                autoFocus
                aria-invalid={error ? true : undefined}
                className={fieldClass}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="password" className={labelClass}>
                Password
              </label>
              <Input
                id="password"
                type="password"
                name="password"
                autoComplete="new-password"
                required
                minLength={6}
                aria-describedby="password-hint"
                className={fieldClass}
              />
              <p id="password-hint" className="text-xs text-zinc-500">
                At least 6 characters.
              </p>
            </div>

            {error && (
              <div
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
              >
                {error}
              </div>
            )}

            <Button
              type="submit"
              className="h-10 w-full bg-brand-600 text-white hover:bg-brand-700"
            >
              Create account
            </Button>
          </Form>

          <p className="mt-6 border-t border-zinc-100 pt-4 text-center text-sm text-zinc-500">
            Already have an account?{" "}
            <Link
              to="/login"
              className="font-semibold text-brand-700 hover:text-brand-800 hover:underline"
            >
              Sign in
            </Link>
          </p>
        </div>
        <p className="mt-4 text-center text-xs text-zinc-500">
          We only use your email to send the alerts you ask for.
        </p>
      </div>
    </div>
  );
}
