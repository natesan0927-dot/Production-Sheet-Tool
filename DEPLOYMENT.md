# Putting Titans Windows CRM live

Written for whoever sets this up and keeps it running — not necessarily a developer.

---

## 1. What this needs to run

| What | Why |
| --- | --- |
| Somewhere to run Python | The app itself |
| A database | Leads, orders, follow-ups — everything except the files |
| Somewhere for uploaded files | Quotations, signed CAFs, measurements, production sheets, receipts |
| HTTPS | Sign-ins, and the app cannot be installed on a phone without it |

The traffic is a dozen people and a few hundred leads a year. Nothing here needs to be big.
The only thing that grows is **uploaded files**, and that is the one thing to keep an eye on.

---

## 2. The plans, cheapest first

### Plan A — Oracle Cloud Always Free  *(recommended: free forever, nothing expires)*

One small virtual machine running everything: the app, PostgreSQL and the files, on the same box.

- **Cost:** ₹0, permanently. Oracle's Always Free tier is not a trial — 4 ARM cores, 24 GB RAM,
  200 GB disk, and it does not expire.
- **Good:** no cold starts, no file-size worries for years, no third-party accounts to wire up,
  everything in one place so backups are one command.
- **Bad:** it is a real server. You install it once (about an hour) and apply security updates
  every month or two. If nobody will do that, take Plan B.
- **Needs a card** to open the Oracle account, but the Always Free resources are never charged.

### Plan B — PythonAnywhere free  *(easiest genuinely free option)*

- **Cost:** ₹0, permanently.
- **Good:** no server admin at all, no cold starts, uploaded files sit on their disk and stay
  there, HTTPS on `yourname.pythonanywhere.com` included.
- **Bad:** **512 MB** total disk. At roughly 300 KB a document that is a few thousand files —
  likely two to three years — after which you either archive old jobs or pay ₹450/month for more.
  No custom domain on the free plan.

### Plan C — Render free + Neon + Cloudflare R2  *(no server admin, three accounts)*

- **Cost:** ₹0 across all three free tiers.
- **Good:** deploys straight from GitHub on every push, nothing to patch.
- **Bad:** the free web service **sleeps after 15 minutes idle** — the first person in each
  morning waits about 50 seconds. Render's own free database expires after 30 days, which is why
  the database goes to **Neon** (free, no expiry) and the files to **Cloudflare R2**
  (10 GB free, no charge for downloads) instead.

### If you would rather just pay

**Render Starter, ₹600/month or so** — the same as Plan C but no sleeping and a real disk,
everything in one account. If the ₹0 constraint ever loosens, this is the least fuss.

---

## 3. Setting up Plan A (Oracle Cloud)

On a fresh Ubuntu 22.04 ARM instance, as root:

```bash
apt update && apt install -y python3-venv python3-pip postgresql nginx git
sudo -u postgres psql -c "CREATE USER titans WITH PASSWORD 'pick-a-long-one';"
sudo -u postgres psql -c "CREATE DATABASE titans OWNER titans;"

adduser --system --group --home /srv/titans titans
cd /srv/titans && sudo -u titans git clone https://github.com/darshansathish2006/TITANS.git app
cd app && sudo -u titans python3 -m venv venv
sudo -u titans venv/bin/pip install -r requirements.txt
```

Write `/srv/titans/app/.env`:

```ini
DJANGO_SECRET_KEY=<50 random characters>
DEBUG=False
ALLOWED_HOSTS=crm.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://crm.yourdomain.com
DATABASE_URL=postgres://titans:pick-a-long-one@localhost:5432/titans
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

Then:

```bash
sudo -u titans venv/bin/python manage.py migrate
sudo -u titans venv/bin/python manage.py collectstatic --noinput
sudo -u titans venv/bin/python manage.py seed_employees
```

Run it with systemd — `/etc/systemd/system/titans.service`:

```ini
[Unit]
Description=Titans Windows CRM
After=network.target postgresql.service

[Service]
User=titans
WorkingDirectory=/srv/titans/app
ExecStart=/srv/titans/app/venv/bin/gunicorn titans_crm.wsgi:application --bind 127.0.0.1:8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

`systemctl enable --now titans`, then put nginx in front of `127.0.0.1:8000` and get a free
certificate with `certbot --nginx`. Open ports 80 and 443 in **both** the Oracle security list
and `ufw` — forgetting the Oracle side is the usual reason a new instance seems dead.

**Back it up.** One line in `crontab -e` keeps a week of nightly copies:

```
0 2 * * * pg_dump titans | gzip > /srv/titans/backup-$(date +\%u).sql.gz && tar czf /srv/titans/media-$(date +\%u).tgz /srv/titans/app/media
```

---

## 4. Setting up Plan C (Render + Neon + R2)

1. **Neon** — create a project, copy the connection string.
2. **Cloudflare R2** — create a bucket, then an API token with Object Read & Write.
3. **Render** — New Web Service from the GitHub repo. It reads the `Procfile`, so:
   - Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - Start command: leave blank
4. Set the environment variables below and deploy.

| Key | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | 50 random characters |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `your-app.onrender.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://your-app.onrender.com` |
| `DATABASE_URL` | the Neon connection string |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | `True` |
| `AWS_STORAGE_BUCKET_NAME` | the R2 bucket name |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | from the R2 token |
| `AWS_S3_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` |

With `AWS_STORAGE_BUCKET_NAME` set, every upload goes to the bucket instead of the container's
disk, so a redeploy no longer loses anything. Leave it unset and files stay local — which is
correct for Plan A and Plan B, where the disk is permanent.

Once the certificate is working and people have used the site over HTTPS for a day or two, add
`SECURE_HSTS_SECONDS=31536000` (and `SECURE_HSTS_INCLUDE_SUBDOMAINS=True` if every subdomain is
HTTPS). Setting it before HTTPS is reliable locks browsers out for a year, which is why it starts
off.

**If the database already holds an older version of this software**, the first migration stops
with an explanation rather than damaging anything. Set `RESET_LEGACY_SCHEMA=true`, deploy once to
clear it, then remove the variable.

---

## 5. The first sign-in

`seed_employees` runs on every deploy and creates anyone missing. It never touches an account
that already exists, so it cannot reset a password somebody has chosen.

| Signs in as | Role |
| --- | --- |
| `rahul`, `natesan`, `prema`, `balasubramaniam`, `sowmiya` | Sales Executive |
| `yogesh`, `venkatesan` | Measurement Staff |
| `quotation` | Quotation Staff |
| `production` | Production Staff |
| `fieldmanager` | Field Manager |
| `accounts` | Accounts Department |
| `admin` | Super Admin |

Everyone starts on **`ChangeMe@123`** and is stopped at a change-password screen until they pick
their own — they cannot reach any other page first.

The Super Admin adds anyone else from **Employees**, and can put a forgotten account back on the
default from the same screen.

---

## 6. Installing it as an app

The app installs on a phone or a desktop straight from the browser. There is nothing to download,
nothing to sideload, and it updates itself whenever the site does.

**Android** — open the site in Chrome, tap the ⋮ menu, **Add to Home screen**. It gets the Titans
crest as its icon and opens in its own window with no browser bars. Chrome usually offers this by
itself, and there is an install button in the app's own top bar too.

**Windows** — open the site in Edge or Chrome and click the install icon in the address bar (or
the same button in the top bar). It lands in the Start menu and behaves like any other program.

**iPhone** — Safari, Share, **Add to Home Screen**.

HTTPS is required for all of this. It will not offer to install over plain `http://`.

### If a real `.apk` file is needed

The install above is the same thing for day-to-day use, so only go here if you specifically need
a file to send around or a Play Store listing. It wraps the live site in a thin Android shell, so
the site still has to be deployed first.

```bash
npm install -g @bubblewrap/cli
bubblewrap init --manifest https://crm.yourdomain.com/static/manifest.webmanifest
bubblewrap build          # produces app-release-signed.apk
```

Bubblewrap needs the Android SDK and a JDK, and asks you to create a signing key — **keep that
key**, because Android will not accept an update signed with a different one. To stop the address
bar showing inside the app, upload the `assetlinks.json` it prints to
`https://crm.yourdomain.com/.well-known/assetlinks.json`.

### About a `.exe`

Installing from Edge, above, already gives a Start-menu app with its own window and icon. That is
the `.exe` for a web app.

A self-contained `.exe` bundling Python and the database is possible with PyInstaller, but it is
the wrong shape for this: each machine would carry its **own separate copy** of the data, so two
people would never see the same leads. This software is only useful when everyone is looking at
one set of records, so it is deliberately not built that way.

---

## 7. Day to day

```bash
python manage.py seed_employees              # add anyone missing, touch nobody else
python manage.py reset_to_live               # wipe demo data and create the real staff (asks first)
python manage.py seed_data                   # put the demo accounts and sample leads back
```

**Watch the disk.** On Plan B the 512 MB limit is the thing that will eventually bite. `media/`
holds every uploaded document; check it now and then.

**Back up the database.** Whichever plan you pick, a nightly `pg_dump` somewhere off the server
is the difference between a bad afternoon and a lost year.
