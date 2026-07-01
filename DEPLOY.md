# Deploy BI Platform to Production

## What you need

- A GitHub account with the `bi-platform` repository already connected to Vercel.
- A Render account (free tier is enough for the API + database).
- (Optional) An Upstash Redis account for WebSocket/SSE caching. The backend works without Redis for the demo.

## 1. Deploy the FastAPI backend on Render

1. Log in to [render.com](https://render.com) with GitHub.
2. In the Render Dashboard go to **Blueprints** → **New Blueprint Instance**.
3. Select the `bi-platform` GitHub repo.
4. Render will detect `bi_platform/render.yaml` and provision:
   - a free PostgreSQL database (`bi-platform-db`)
   - a free Docker web service (`bi-platform-api`)
5. After the first deploy finishes, open the web service **Shell** tab and run:

   ```bash
   python scripts/init_remote_db.py
   ```

   This creates tables, applies SQL migrations, and seeds demo users
   (`admin`/`admin123`, `ceo`/`ceo123`, `cfo`/`cfo123`, `sales_head`/`sales123`,
   `manager1`/`manager123`).
6. Note the public URL of the web service, e.g. `https://bi-platform-api.onrender.com`.

## 2. Connect Redis (optional)

If you want Redis caching:

1. Create a free Redis database at [Upstash](https://upstash.com).
2. Copy the Redis connection string (e.g. `rediss://...`).
3. In Render, add an environment variable `REDIS_URL` to `bi-platform-api`.

If you skip this step, keep `REDIS_URL` unset; the demo does not require it.

## 3. Update Vercel environment variables

1. Open the Vercel dashboard for the `bi-platform` project.
2. Go to **Settings** → **Environment Variables**.
3. Add or update the following variables (use the URL from step 1):

   | Name | Value | Environment |
   |---|---|---|
   | `API_URL` | `https://bi-platform-api.onrender.com` | Production |
   | `NEXT_PUBLIC_API_URL` | `https://bi-platform-api.onrender.com` | Production |
   | `NEXT_PUBLIC_WS_URL` | `wss://bi-platform-api.onrender.com` | Production |
   | `API_USER` | `admin` | Production |
   | `API_PASS` | `admin123` | Production |

4. (Optional) If you deploy Metabase publicly, also add:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_METABASE_URL` | your public Metabase URL |
   | `NEXT_PUBLIC_METABASE_DASHBOARD_UUID` | the dashboard UUID |
   | `NEXT_PUBLIC_METABASE_DASHBOARD_URL` | the public dashboard URL |

5. Redeploy the project from Vercel: **Deployments** → the latest one → **Redeploy**.

## 4. Verify the public site

1. Open the production Vercel URL.
2. Log in with `admin` / `admin123`.
3. Dashboard, managers, sales funnel, budget-vs-actual, and P&L waterfall pages
   should load data from the Render backend.

## 5. Keeping the backend alive (free tier)

Render free web services spin down after 15 minutes of inactivity and take
~30 seconds to wake up. For a portfolio/demo site this is acceptable.
If you need always-on performance, upgrade to Render's starter plan.

## Troubleshooting

- **Login still shows "backend-authentic"**: check Vercel env vars and make sure
  `API_URL` points to the Render URL, not `localhost:8000`.
- **Empty dashboard / no data**: run `python scripts/init_remote_db.py` again in the
  Render shell; then verify the backend health endpoint `/health` returns `{"status":"ok"}`.
- **CORS errors**: the backend already allows `*` origins. If you see CORS errors,
  make sure you are using `https://` for both Vercel and Render, not mixed `http`/`https`.
