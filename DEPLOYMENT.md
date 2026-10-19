# Deploying InterviewOS

InterviewOS has three deployable processes. Deploying only the frontend or
only the API is not enough for a working voice interview.

| Service | Platform | Repository root | Start command |
| --- | --- | --- | --- |
| Frontend | Vercel | `frontend` | Vercel runs `npm run build` |
| API | Railway | `backend` | Dockerfile default command |
| LiveKit agent worker | Railway | `backend` | `python -m app.interview.agent start` |

## Before deployment

1. Push this repository to a private GitHub repository.
2. Do **not** commit `.env`. It contains private API keys.
3. Keep `.env.example` in the repository as the list of required variables.

## 1. Deploy the FastAPI API on Railway

1. In Railway, select **New Project** -> **Deploy from GitHub repo**.
2. Select this repository.
3. Open the service settings and set **Root Directory** to `backend`.
4. Railway detects `backend/Dockerfile`. Do not add a custom build command.
5. The default start command is already defined by the Dockerfile:

   ```text
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

6. Add a public Railway domain and copy its HTTPS URL. It is the API URL used
   by the frontend.

Add these Railway variables from your local `.env` (use the real values only
in Railway, never in Git):

```text
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
GROQ_API_KEY
GNANI_API_KEY
INTERVIEW_LANGUAGE_MODE
INTERVIEW_TTS_PROVIDER
LIVEKIT_TTS_VOICE
```

After the frontend is deployed, also add:

```text
DEMO_FRONTEND_ORIGIN=https://YOUR-VERCEL-DOMAIN
```

## 2. Deploy the LiveKit worker on Railway

Create a **second Railway service** from the same GitHub repository.

1. Set **Root Directory** to `backend`.
2. Railway uses the same Dockerfile and dependencies.
3. Override the service **Start Command** with:

   ```text
   python -m app.interview.agent start
   ```

4. Add the same LiveKit, Groq, Gnani, and interview-language variables used
   by the API service.
   Also add the API service's public Railway URL:

   ```text
   INTERVIEW_API_URL=https://YOUR-RAILWAY-API-DOMAIN
   ```

   The worker uses this URL to save the final report. `localhost` only works
   when both the API and worker run on the same machine.
5. Do not create a public domain for this worker. It connects outward to
   LiveKit and must remain running.

The worker log must show:

```text
registered worker
agent_name: interviewer
```

## 3. Deploy the frontend on Vercel

1. In Vercel, import the same GitHub repository.
2. Set **Root Directory** to `frontend`.
3. Framework preset: **Vite**.
4. Add this environment variable before deploying:

   ```text
   VITE_API_URL=https://YOUR-RAILWAY-API-DOMAIN
   ```

5. Deploy and copy the Vercel domain.
6. Return to the Railway API service and set `DEMO_FRONTEND_ORIGIN` to that
   exact Vercel domain, then redeploy the API.

`VITE_API_URL` is compiled into the frontend build. If the API URL changes,
update that value and redeploy the Vercel frontend.

## Validation

1. Open the Vercel domain.
2. Create an interview screening.
3. Railway API logs should show a successful request to
   `POST /api/interview/session`.
4. Railway worker logs should show `received job request` and then
   `registered worker` on startup.
5. Complete one short interview and open its report.

## Current prototype limitation

The current API uses in-memory session storage. A Railway API restart clears
active interview/report data. This is acceptable for a demo, but before a
real HR deployment the session and report data must move to PostgreSQL.
