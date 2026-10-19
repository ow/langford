# Langford web deployment

The web app deploys to the `langford-intelligence` Cloudflare Worker. Meeting
processing stays on the Mac; both services use the same Supabase database.
The repository is `ow/langford`; Workers Builds is configured to watch the
`local-first-pdf-extraction` production branch. The previous View Royal domain is not attached
to this Worker.

## Cloudflare Workers Builds

Connect the GitHub repository to this Worker, then configure:

- Root directory: `/` (the pnpm workspace root).
- Build command: `pnpm --filter web typecheck && pnpm --filter web exec vitest run && pnpm build:web`.
- Deploy command: `pnpm --filter web exec wrangler deploy`.
- Production branch: `local-first-pdf-extraction`.
- Non-production branch deployments: disabled until preview data/access is configured.

Build-time secrets must include `SUPABASE_SECRET_KEY` and `OPENAI_API_KEY`.
Add `GEMINI_API_KEY` only if selecting Gemini. Use encrypted secret fields;
never commit credentials. This app currently embeds server configuration during
the Vite build, so setting runtime secrets alone is insufficient. Public settings
and the production admin email allowlist are read from `apps/web/wrangler.toml`.

After changing build-time credentials or the admin allowlist, rebuild and deploy.
Keep deployments limited to trusted branches because builds can access secrets.

## Local deployment

With the existing ignored root `.env` configured and Wrangler authenticated:

```sh
pnpm deploy:web
```

The web package runs its test suite before deployment. Run `pnpm --filter web
typecheck` separately when deploying locally.

Verify the public homepage and meetings page, confirm `/admin/pipeline` redirects
unauthenticated visitors to login, and check an AI answer before announcing the
site. Custom-domain setup is a separate step after the workers.dev deployment.

Start the Mac processing worker with `pnpm dev:worker` when jobs should run.
Cloudflare does not run the Python transcription pipeline.

## GitHub connection status

As of October 18, the Cloudflare GitHub app installation exists, but `ow/langford`
is not yet in its saved selected-repository grants. The repository addition is
prepared in GitHub and awaits its access confirmation. Until saved and verified
with a push-triggered build, deployment remains manual. The build commands,
production branch, encrypted build secrets and deployment token are already saved.
