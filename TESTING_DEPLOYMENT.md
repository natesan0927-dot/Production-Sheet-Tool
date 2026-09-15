# Getting this in front of the company for testing

This is the fast path: a real, multi-user, always-on web address that every
role can log into from their own phone or laptop. It's meant for the
testing/UAT phase — see `DEPLOYMENT.md` for the longer-term production setup
once testing is signed off.

**Host: [Render](https://render.com)** — free HTTPS, a managed PostgreSQL
database, deploys straight from a GitHub repo. Everything below is written to
need **zero shell/terminal access on Render**, because that's a paid-plan-only
feature — the deploy itself does all the setup (database tables, master data,
your logo, your admin account) automatically. You can start entirely on
Render's **Free** plan; see "Free plan limitations" below for the two things
it doesn't do, and when to upgrade.

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
   testers (e.g. Singapore for India), plan **Free** is fine. Create it, then
   open it and copy the **Internal Database URL** (starts with
   `postgres://...`) — you'll need it in step 3.

## 3. Create the web service (10 min)

1. **New → Web Service** → connect your GitHub repo.
2. Settings:
   - **Runtime**: Python 3
   - **Build Command**:
     ```
     pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput && python manage.py seed_data
     ```
     This one line does everything a shell session would otherwise be needed
     for: creates every database table, loads all the default roles and
     master data, sets your real logo, creates the 8 one-click demo accounts,
     and creates your own admin account (from the environment variables
     below) — automatically, on every deploy, no manual step required.
   - **Start Command**: `gunicorn titans_crm.wsgi:application --bind 0.0.0.0:$PORT`
   - **Plan**: Free (upgrade to Starter later if you need the things listed
     under "Free plan limitations")
3. **Environment variables** (Render's "Environment" tab) — add these now:

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
   | `DJANGO_SUPERUSER_USERNAME` | pick a username for yourself, e.g. `owner` |
   | `DJANGO_SUPERUSER_PASSWORD` | pick a strong password |
   | `DJANGO_SUPERUSER_EMAIL` | your email address |

   Use the **exact** address Render assigns you (shown at the top of the
   service page once created) for the two `.onrender.com` values — if Render
   added a random suffix to the name you typed, that suffix has to be in both
   values or you'll see a "disallowed host" or "CSRF" error.
4. Click **Create Web Service** and let the first deploy finish — watch the
   Logs tab. Once it says "Live", everything is already set up.

## 4. Sign in

Go to `https://<your-app-name>.onrender.com` and sign in with the
`DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` you set above. The 8
demo accounts (password `Demo@123`) are also ready immediately on the login
page's quick-login tiles.

**For real testing with real names** (recommended over the generic demo
accounts): once signed in, go to **Employees → Add Employee** and create one
account per person who's testing, with their actual role. That way feedback
and the audit history point to real people, and it doubles as a rehearsal of
the actual "Admin creates employee accounts" step you'll do at go-live.

## Free plan limitations

Render's Free plan is genuinely enough to let every role click through the
whole system and try their day-to-day work. Two things it doesn't do, which
matter before testers rely on it for real:

- **Uploaded files don't survive a restart.** Site photos, generated
  quotation/certificate PDFs, and signatures are written to disk, and Free
  services have no persistent disk — a redeploy or Render recycling the
  service on its own wipes them. Upgrade to the **Starter** plan (~$7/month)
  and attach a **Disk** (Render will prompt for a mount path once you're on a
  paid plan — open the **Shell** tab, now available, and run
  `python -c "from django.conf import settings; print(settings.MEDIA_ROOT)"`
  to get the exact path to use) to make this permanent.
- **The service "sleeps" after 15 minutes of no traffic** and takes
  ~30–50 seconds to wake up on the next request. Fine for asynchronous
  testing; annoying if someone's watching. Starter removes this too.

Neither is a reason to wait to start testing — just don't be surprised if an
uploaded photo disappears after a deploy while you're still on Free, and
upgrade before this becomes the system of record.

## Send it to the company

A short message to send testers works well:
> Hi team — the new Titans Windows system is ready to try. Go to
> `https://<your-app-name>.onrender.com`, log in with the username/password I
> sent you separately, and try doing your normal day-to-day work in it —
> [Documentation link] walks through what each screen does. Let me know
> anything that's confusing, broken, or missing.

## What to watch for during testing

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
