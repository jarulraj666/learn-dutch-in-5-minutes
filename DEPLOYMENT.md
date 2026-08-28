# Production Deployment

This repository's recommended first production setup is:

- Vercel for `learn/frontend`
- Railway for `learn/backend`
- Railway Postgres, Neon, or Supabase for PostgreSQL
- The content-generation pipeline kept separate from the public web services

## 1. Create PostgreSQL

Create a PostgreSQL database and copy its connection string. Apply the learner schema from the repository root:

```bash
psql "$DATABASE_URL" -f learn/db/schema.sql
```

Use the same `DATABASE_URL` for the Next.js service and the FastAPI service. Keep the connection string in platform environment variables; do not commit it.

## 2. Deploy the API to Railway

Create a Railway service from this repository and set its root directory to `learn/backend`. Railway will install `requirements.txt` and use `railway.json` for the production command and health check.

Set these variables on the Railway service:

```text
DATABASE_URL=postgresql://...
LEARN_ALLOWED_ORIGINS=https://your-domain.com,https://www.your-domain.com
ADMIN_EMAILS=you@example.com
LEARN_COMPLETION_PERCENT=90
LEARN_CERTIFICATE_PASS_PERCENT=70
```

After deployment, verify:

```text
https://your-api-service.up.railway.app/api/health
```

The response should report `ok: true` and `database: true`.

## 3. Deploy the frontend to Vercel

Import the repository into Vercel and set the project root directory to `learn/frontend`. Vercel detects the existing Next.js build and start configuration.

Set these Vercel environment variables for Production:

```text
DATABASE_URL=postgresql://...
DATABASE_SSL=true
AUTH_SECRET=<long-random-secret>
NEXTAUTH_URL=https://your-domain.com
LEARN_API_URL=https://your-api-service.up.railway.app
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
ADMIN_EMAILS=you@example.com
```

`LEARN_API_URL` is used by the server-side Next.js proxy. Browser requests should use the frontend domain, not the Railway API URL.

## 4. Configure Google sign-in

In the Google OAuth client, add this authorized redirect URI:

```text
https://your-domain.com/api/auth/callback/google
```

Add the Vercel domain as an authorized JavaScript origin if Google requests one. Add the Railway preview or production API URL only if the OAuth client specifically requires it; Auth.js handles the callback on the Vercel frontend.

## 5. Add the domain

Attach the production domain to Vercel. If both the apex and `www` domain are used, include both in `LEARN_ALLOWED_ORIGINS` and set `NEXTAUTH_URL` to the canonical domain.

## 6. Keep the pipeline separate

Do not run video generation, WhisperX, FFmpeg rendering, or social publishing inside a web request. Run `pipeline/run_pipeline.py` locally at first, then move it to a dedicated worker, VM, or scheduled job when needed.

## Deployment checklist

- [ ] PostgreSQL schema applied
- [ ] Railway API reports `ok: true`
- [ ] Vercel production variables configured
- [ ] Google redirect URI configured
- [ ] Custom domain attached
- [ ] `ADMIN_EMAILS` set
- [ ] Secrets and token files excluded from git
- [ ] Database backups enabled
