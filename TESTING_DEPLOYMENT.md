# Getting this in front of the company for testing

This is the fast path: a real, multi-user, always-on web address that every
role can log into from their own phone or laptop, in about 20–30 minutes.
It's meant for the testing/UAT phase — see `DEPLOYMENT.md` for the
longer-term production setup once testing is signed off.

**Recommended host: [Render](https://render.com)** — free HTTPS, a managed
PostgreSQL database, and it deploys straight from a GitHub repo (push code →
it redeploys automatically). The free tier does **not** keep uploaded files
(site photos, generated PDFs) safely between restarts, so use the **Starter**
plan (~$7/month) for the web service during testing — cancel it once testing
is done if you don't need it further.

## 1. Push the code to GitHub (5 min)

```powershell
cd D:\Projects\Titans
git init
git add .
git commit -m "Titans Windows CRM - ready for testing"
```
Create a new **private** repository on GitHub, then:
```powershell
git remote add origin https://github.com/<your-account>/titans-crm.git
git branch -M main
git push -u origin main
```

## 2. Create the database on Render (3 min)

1. Sign up / log in at render.com.
2. **New → PostgreSQL**. Name it `titans-crm-db`, region closest to your
   testers (e.g. Singapore for India), plan **Free** is fine for the
   database itself. Create it, then open it and copy the **Internal Database
   URL** (starts with `postgres://...`) — you'll need it in step 3.

## 3. Create the web service (10 min)

1. **New → Web Service** → connect your GitHub repo.
2. Settings:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - **Start Command**: `gunicorn titans_crm.wsgi:application --bind 0.0.0.0:$PORT`
   - **Plan**: Starter (needed for a persistent disk — see below)
3. **Environment variables** (Render's "Environment" tab) — add these first:

   | Key | Value |
   |---|---|
   | `DJANGO_SECRET_KEY` | a long random string (e.g. generate one at [djecrety.ir](https://djecrety.ir)) |
   | `DEBUG` | `False` |
   | `ALLOWED_HOSTS` | `<your-app-name>.onrender.com` |
   | `CSRF_TRUSTED_ORIGINS` | `https://<your-app-name>.onrender.com` |
   | `DATABASE_URL` | the Internal Database URL from step 2 |
   | `SECURE_SSL_REDIRECT` | `True` |
   | `SESSION_COOKIE_SECURE` | `True` |
   | `CSRF_COOKIE_SECURE` | `True` |

4. Click **Create Web Service** and let the first deploy finish (watch the
   Logs tab) — you need the app to have deployed once before you can find its
   working directory for the next step.
5. Add a **Disk** (Render will now ask for an absolute mount path). Open the
   **Shell** tab on the running service and run:
   ```
   python -c "from django.conf import settings; print(settings.MEDIA_ROOT)"
   ```
   Use that exact path as the disk's mount path, size 1 GB, then save — this
   is what keeps uploaded photos and generated PDFs from disappearing when
   the service restarts. Render redeploys once more after you attach the disk.

## 4. Set up the data (5 min)

Once it's deployed, open the **Shell** tab on the web service (or use
`render ssh`) and run:
```
python manage.py seed_data
python manage.py createsuperuser
```
`seed_data` creates the default roles, master data, your real logo, **and**
the 8 one-click demo accounts (password `Demo@123`) shown on the login page —
so your testers have something to click immediately.

## 5. Send it to the company

Your app is now live at `https://<your-app-name>.onrender.com`.

**For real testing with real names** (recommended over the generic demo
accounts): sign in as your new superuser, go to **Employees → Add Employee**,
and create one account per person who's testing, with their actual role.
That way feedback and the audit history point to real people, and it doubles
as a rehearsal of the actual "Admin creates employee accounts" step you'll do
at go-live.

A short message to send testers works well:
> Hi team — the new Titans Windows system is ready to try. Go to
> `https://<your-app-name>.onrender.com`, log in with the username/password I
> sent you separately, and try doing your normal day-to-day work in it —
> [Documentation link] walks through what each screen does. Let me know
> anything that's confusing, broken, or missing.

## What to watch for during testing

- **Render's free-tier services "sleep" after 15 minutes of no traffic** and
  take ~30–50 seconds to wake up on the next request — the Starter plan used
  above does not sleep, so this shouldn't come up, but if the first login of
  the day feels slow, that's why.
- Keep an eye on the **Logs** tab for errors while testers are active — most
  issues will show up there immediately.
- Ask testers to use their **own phone** for at least the measurement and
  installation flows (site photo upload, signature capture) — that's the
  scenario worth validating most, since it's the one place people won't be
  sitting at a desk.

## Once testing is signed off

Move to the durable production setup in `DEPLOYMENT.md` (same idea, but with
proper backup automation, and cheaper if you're running it indefinitely
rather than on Render's per-service pricing). Migrating later is just moving
the database and `media/` folder — nothing about the application changes.
