# Cloudflare Zero Trust Setup Guide — CYOA Game Server

> **Doc references verified against Cloudflare developer docs as of Feb 2026.**

This guide walks you through setting up Cloudflare Zero Trust so that
`cyoa.chat-sdp.com` is publicly accessible only to users who authenticate
via Google SSO. The Django app handles user creation automatically once it
receives a valid Cloudflare Access JWT.

---

## Prerequisites

| Item | Status |
|------|--------|
| Cloudflare account (free tier is fine) | ✅ you already have one |
| `chat-sdp.com` domain on Cloudflare (full DNS setup) | ✅ already added |

---

## Step 1 — Create / verify your Zero Trust organisation

1. Go to the [Cloudflare dashboard](https://dash.cloudflare.com/) → **Zero Trust**
   (or directly to <https://one.dash.cloudflare.com/>).
2. If prompted, choose a **team name** (e.g. `your-team`).
   Your team domain becomes: `https://your-team.cloudflareaccess.com`
3. Pick the **Free** plan (supports up to 50 users).

> **Note:** Your team name is visible at
> **Cloudflare One → Settings** (left sidebar).

---

## Step 2 — Add Google as an Identity Provider

1. In [Cloudflare One](https://one.dash.cloudflare.com/), go to
   **Integrations → Identity providers**.
2. Select **Add new identity provider → Google**.
3. In a separate tab, open the
   [Google Cloud console](https://console.cloud.google.com/):
   - Create a new project (or reuse one).
   - Go to **APIs & Services → Credentials**.
   - Select **Configure Consent Screen → Get started**.
     - App name: anything (e.g. "CYOA Login")
     - Audience Type: **External**
     - Fill in support email + contact info, agree to policy, **Create**.
   - Back on OAuth overview, click **Create OAuth client**.
     - Application type: **Web application**
     - **Authorized JavaScript origins:**
       ```
       https://your-team.cloudflareaccess.com
       ```
     - **Authorized redirect URIs:**
       ```
       https://your-team.cloudflareaccess.com/cdn-cgi/access/callback
       ```
   - Copy the **Client ID** and **Client Secret**.
4. Back in Cloudflare One, paste:
   - **App ID** = the Google Client ID
   - **Client Secret** = the Google Client Secret
5. Click **Save**, then **Test** to verify the connection.

---

## Step 3 — Create a Cloudflare Tunnel for CYOA

This is a **new, separate tunnel** — it has nothing to do with your OpenWebUI
tunnel.

1. Go to **Networks → Connectors → Cloudflare Tunnels**.
2. Click **Create a tunnel**.
3. Choose **Cloudflared** as the connector type → **Next**.
4. Name it something like `cyoa-game` → **Save tunnel**.
5. **Install & run `cloudflared`:**
   The dashboard will show a command like:
   ```bash
   brew install cloudflare/cloudflare/cloudflared   # if not already installed
   sudo cloudflared service install <TOKEN>
   ```
   Copy the token — you'll need it. Since you're on macOS, the simplest
   approach is to run `cloudflared` as a service. If you already have
   `cloudflared` installed for OpenWebUI, you can run a second instance
   with a different config file (see note below).
6. Once the connector shows as **Connected** in the dashboard, click **Next**.
7. **Add a public hostname:**
   - **Subdomain:** `cyoa`
   - **Domain:** `chat-sdp.com`
   - **Service type:** `HTTP`
   - **URL:** `localhost:8001`
     *(this is the Docker-mapped port — docker-compose maps
     host port 8001 → container port 8000)*
8. **Save**.

After a few seconds, `cyoa.chat-sdp.com` will resolve through the tunnel.
**Don't browse to it yet** — you need the Access Application first (Step 4),
or the app will be publicly open with no auth.

> **Running two tunnels on one Mac:**
> Each tunnel gets its own `cloudflared` token. If you're already running
> `cloudflared` as a LaunchAgent/service for OpenWebUI, the easiest
> option is to run the CYOA tunnel as a second `cloudflared` process
> (Cloudflare supports multiple tunnels per host). The dashboard install
> command handles this — each `cloudflared service install <TOKEN>` call
> registers a unique connector.

---

## Step 4 — Create an Access Application

1. Go to **Access controls → Applications**.
2. Click **Add an application → Self-hosted**.
3. Configure:
   - **Application name:** `CYOA Game`
   - **Session Duration:** 24 hours (or your preference)
   - Click **Add public hostname**:
     - **Domain:** `chat-sdp.com`
     - **Subdomain:** `cyoa`
4. Click **Next** to set up policies.
5. **Add an Allow policy:**
   - **Policy name:** `Allow Google users`
   - **Selector:** *Emails ending in* → enter the domain(s) you want
     (e.g. `gmail.com`, or a specific list of emails under *Emails*)
   - Or use **Everyone** if you want any authenticated Google user.
6. Under **Authentication**, select only **Google** as the identity provider.
   - (Recommended) Enable **Instant Auth** so users skip the Cloudflare
     login page and go straight to Google.
7. Click **Next** (App Launcher / Block page — defaults are fine).
8. Click **Next** (Advanced settings — defaults are fine).
9. **Save**.

### Get the Application Audience (AUD) tag

1. In **Access controls → Applications**, click **Configure** on your app.
2. On the **Basic information** tab, copy the **Application Audience (AUD) Tag**.
   This is a long hex string.

---

## Step 5 — Configure the Django app

Create or update the `.env` file used by `docker-compose.mac.yml`:

```bash
# .env  (in the llm-cyoa repo root, next to docker-compose.mac.yml)
CLOUDFLARE_AUTH_ENABLED=true
CLOUDFLARE_TEAM_DOMAIN=https://your-team.cloudflareaccess.com
CLOUDFLARE_AUD=<paste-the-long-hex-aud-tag>
CLOUDFLARE_ADMIN_EMAILS=you@gmail.com
```

Replace:
- `your-team` with your actual team name from Step 1
- `<paste-the-long-hex-aud-tag>` with the AUD from Step 4
- `you@gmail.com` with your Google email(s) — comma-separated for multiple

Then rebuild and restart:

```bash
cd /path/to/llm-cyoa
docker compose -f docker-compose.mac.yml up -d --build cyoa-game-server
```

---

## Step 6 — Verify

1. Open `https://cyoa.chat-sdp.com` in a browser.
2. You should be redirected to Google login (via Cloudflare).
3. After authenticating, you land on the CYOA home page.
4. Check the user bar shows "Signed in as **you@gmail.com**".
5. If your email is in `CLOUDFLARE_ADMIN_EMAILS`, you'll see the
   **Admin Panel** link.

---

## How it works (technical summary)

```
Browser → Cloudflare Edge (Access JWT issued) → Tunnel → Nginx → Django
```

1. **Cloudflare Access** intercepts every request to `cyoa.chat-sdp.com`.
   Unauthenticated users are redirected to Google login.
2. After login, Cloudflare adds a **`Cf-Access-Jwt-Assertion`** header
   (RS256-signed JWT) to every proxied request.
3. **Nginx** forwards this header to Django.
4. **`CloudflareAccessMiddleware`** in Django:
   - Fetches public keys from
     `https://your-team.cloudflareaccess.com/cdn-cgi/access/certs`
     (cached 5 min).
   - Validates the JWT signature, audience, and expiry.
   - Extracts the user's email.
   - Creates a Django `User` (or finds existing) and logs them in.
   - Grants `is_staff` + `is_superuser` if email is in
     `CLOUDFLARE_ADMIN_EMAILS`.

---

## Local development (LAN)

When `CLOUDFLARE_AUTH_ENABLED=false` (the default), the middleware is a
complete no-op. Normal Django username/password login at
`/admin/login/` works as before on `cyoa.mac.stargate.lan`.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 403 on login POST (CSRF) | Ensure `CSRF_TRUSTED_ORIGINS` includes `https://cyoa.chat-sdp.com` (already done) |
| "Invalid token" in Django logs | Check `CLOUDFLARE_AUD` matches the app's AUD tag exactly |
| "Failed to fetch Cloudflare JWKS" | Container can't reach `cloudflareaccess.com` — check DNS / firewall |
| User created but not staff | Add their email to `CLOUDFLARE_ADMIN_EMAILS` and restart |
| Tunnel shows "Inactive" | Ensure `cloudflared` is running on the host and connected |
