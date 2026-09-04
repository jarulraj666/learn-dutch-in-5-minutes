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

## 7. Sync mock exams and media

Keep the admin pipeline service private. Its Pipeline tab can upload completed mock-exam media to an S3-compatible Cloudflare R2 bucket and then sync the updated exam to Railway Postgres. Configure these variables on that service:

```text
PRODUCTION_DATABASE_URL=postgresql://...
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=learn-dutch-media
R2_PUBLIC_BASE_URL=https://media.your-domain.com
```

`R2_PUBLIC_BASE_URL` must be a public custom domain or public bucket URL that serves the bucket. The bucket must permit the service credentials to upload objects. Generate videos, MP3/WAV audio, images, and subtitles locally or on a worker first. In the admin Mock Exam Pipeline tab, select **Sync to Production**, confirm the action, and wait for the job to finish. It uploads local media, rewrites the exam artifact to use public URLs, and upserts that exam to `PRODUCTION_DATABASE_URL`.

Do not use Railway's container filesystem for generated video or audio. It is ephemeral and can be cleared during a deploy. Learners stream public media directly from R2; private speaking recordings are transcribed and deleted by the API.

## Deployment checklist

- [ ] PostgreSQL schema applied
- [ ] Railway API reports `ok: true`
- [ ] Vercel production variables configured
- [ ] Google redirect URI configured
- [ ] Custom domain attached
- [ ] `ADMIN_EMAILS` set
- [ ] Secrets and token files excluded from git
- [ ] Database backups enabled
- [ ] R2 variables configured on the private admin pipeline service
- [ ] R2 public media domain configured
