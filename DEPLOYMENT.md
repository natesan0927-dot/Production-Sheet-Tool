# Putting Titans Windows CRM live

Written for whoever sets this up and keeps it running — not necessarily a developer.

- [1. What this needs](#1-what-this-needs)
- [2. Is Oracle Cloud safe? Is 200 GB enough?](#2-is-oracle-cloud-safe-is-200-gb-enough)
- [3. Step by step on Oracle Cloud](#3-step-by-step-on-oracle-cloud)
- [3b. Step by step with no credit card — Render + Neon + Supabase](#3b-step-by-step-with-no-credit-card--render--neon--supabase)
- [4. Backups — read this one](#4-backups--read-this-one)
- [5. Updating it later](#5-updating-it-later)
- [6. When something is wrong](#6-when-something-is-wrong)
- [7. The other hosting options](#7-the-other-hosting-options)
- [8. The first sign-in](#8-the-first-sign-in)
- [9. Installing it as an app](#9-installing-it-as-an-app)

---

## 1. What this needs

| What | Why |
| --- | --- |
| Somewhere to run Python | The app itself |
| A database | Leads, orders, follow-ups — everything except the files |
| Somewhere for uploaded files | Quotations, signed CAFs, measurements, production sheets, receipts |
| A hostname | HTTPS needs one, and the app will not install on a phone without HTTPS. Free on DuckDNS, or ~₹800/year for your own |

The traffic is a dozen people and a few hundred leads a year. Nothing here needs to be big.
The only thing that grows is **uploaded files**.

**Which route?** Every provider that rents you a real Linux server — Oracle, AWS, Google, Azure,
DigitalOcean — wants a **credit card** to verify you, because a server is what gets abused for
mining. There is no way round that.

| | Section 3 — Oracle | Section 3b — Render + Neon + Supabase |
| --- | --- | --- |
| Credit card to sign up | **Yes** | **No** — email only |
| Setup | ~1 hour, some of it SSH | ~30 minutes, all in a browser |
| Free file storage | 200 GB | 1 GB, then a paid step |
| Always on | Yes | Sleeps after 15 min idle; ~50s first load |
| Server to look after | Yes (one script handles it) | None |

Oracle is the better home if the card can be arranged. Section 3b is the honest answer when it
cannot, and nothing about it is throwaway — the same code, and you can move later.

---

## 2. Is Oracle Cloud safe? Is 200 GB enough?

### Will the data be safe?

The storage itself is solid. Oracle keeps three copies of every block volume inside the data
centre, so a failed disk is their problem, not yours. That is better than most of what you would
get for money elsewhere.

The risks that actually matter are not hardware:

**Oracle reclaims idle Always Free machines.** This is the most common way people lose an Oracle
free server. If a machine sits under roughly 10% CPU, 10% network and 10% memory for seven days
straight, Oracle marks it idle, emails you, and may stop and eventually terminate it. A CRM used
every day by twelve people will normally stay above that, but a quiet fortnight — a holiday, a
slow month — could trip it.

> **Do this:** in the Oracle console, upgrade the account to **Pay As You Go**. The Always Free
> resources stay free, you are not billed while you stay inside the limits, and idle reclamation
> stops applying. It is the difference between a hobby server and one you can trust with the
> business. Oracle places a small temporary card authorisation (about ₹100) and refunds it.

**Capacity.** The free ARM machines are popular and a region can run out. You may see *"Out of
host capacity"* when creating one. Change the availability domain, or try again in an hour — they
free up. An annoyance at setup, not a risk afterwards.

**Free accounts can be closed.** Rare, but Oracle has closed free accounts over verification or
terms issues. Upgrading to Pay As You Go largely removes this too.

**You, or a bad migration.** Far and away the likeliest cause of lost data on any host.

None of these are reasons to avoid Oracle. They are reasons to **keep backups off the server** —
which [section 4](#4-backups--read-this-one) sets up in one command. With Pay As You Go and
off-server backups, this is genuinely dependable for a business this size.

### Is 200 GB enough?

Yes — comfortably, for years.

A completed job carries eight to thirteen documents: the rough measurement, the quotation, the
elevation report, the signed CAF, the final measurement, the production sheet and any revisions,
the signed handover, and payment receipts. PDFs run 100–500 KB; a measurement sheet photographed
on a phone runs 2–5 MB. Call it **15–20 MB per finished job**.

The operating system, PostgreSQL and the app take about 10 GB, leaving roughly 190 GB:

| Jobs per year | Roughly how long 190 GB lasts |
| --- | --- |
| 300 | about 30 years |
| 1,000 | about 9 years |
| 1,000, with full-resolution phone photos (~50 MB a job) | about 4 years |

The one thing that changes the answer is photo size. If staff upload straight from a phone camera
at full resolution, files are five to ten times bigger. Asking them to photograph documents with a
scanning app rather than the camera keeps this under control, and makes the documents easier to
read anyway.

### What if it does fill up?

Nothing breaks suddenly — you will watch the disk fill long before it matters. Three options,
cheapest first:

1. **Archive old jobs.** Move completed work older than a few years off the server. Free.
2. **Buy more block storage.** About **$0.026 per GB per month** — 100 GB extra is roughly
   **₹220/month**. You can grow the existing volume while the server is running, with no
   reinstall and no downtime.
3. **Move documents to a bucket.** Cloudflare R2 gives 10 GB free and charges nothing for
   downloads. Set `AWS_STORAGE_BUCKET_NAME` and the app writes there instead of the disk — no code
   change. See [section 7](#7-the-other-hosting-options).

You need a Pay As You Go account to buy anything, which is another reason to upgrade at the start.

---

## 3. Step by step on Oracle Cloud

Set aside about an hour. You will need a card for the Oracle signup (not charged) and a hostname.

### Step 1 — Get a hostname

The server needs a name, not just an IP address. Everything downstream depends on it: the HTTPS
certificate, the install-as-an-app prompt, and the `.apk` wrapper, which Android will only accept
against a verified `https://` hostname. A bare IP gets none of that, and staff passwords would
travel the public internet in clear text.

**Free — DuckDNS.** Sign in at **duckdns.org** with a Google account, type a name such as
`titanswindows`, and click *add domain*. You now own `titanswindows.duckdns.org`. Paste the
server's public IP into the box in step 5 instead of editing a registrar's DNS. Let's Encrypt
issues certificates for it exactly as it would for a paid domain, so step 7 is unchanged.

**Paid — your own name.** Around ₹800 a year at Namecheap, GoDaddy or Cloudflare, giving
something like `crm.titanswindows.in`. Worth it if the name will ever be seen by a customer, or if
you want email on it. For a tool only twelve staff open, DuckDNS is genuinely fine.

The one thing to know about the free route: if you later move to your own domain, the `.apk` has
to be rebuilt and reinstalled, because the hostname is baked into it. Browsers and the desktop
install are unaffected. So if you think you will want your own name eventually, buy it before
building the `.apk`, not after.

### Step 2 — Create the Oracle account

1. Go to **oracle.com/cloud/free** and sign up.
2. Pick the **home region closest to you** — for India, *India South (Hyderabad)* or
   *India West (Mumbai)*. **This cannot be changed later.**
3. Finish verification.
4. **Upgrade to Pay As You Go**: **Billing & Cost Management → Upgrade and Manage Payment**. As
   explained above, this keeps everything free but stops Oracle reclaiming the machine. Do it now,
   before you build anything on it.

### Step 3 — Create the machine

**Compute → Instances → Create instance**

| Setting | Choose |
| --- | --- |
| Name | `titans-crm` |
| Image | **Canonical Ubuntu 22.04** |
| Shape | **Ampere → VM.Standard.A1.Flex**, then **2 OCPUs, 12 GB memory** |
| Boot volume | Tick *Specify a custom boot volume size*, enter **200** (GB) |
| SSH keys | **Generate a key pair for me**, then **download the private key** |

Two cores and 12 GB is half the free allowance and far more than this needs. Taking the whole
200 GB as the boot volume means one disk to think about rather than two.

> **Save the private key file somewhere safe.** It is the only way into the server, and Oracle
> will not give you another copy.

If it says *"Out of host capacity"*, change the Availability Domain in the same form and try
again, or wait an hour.

When it finishes, copy the **Public IP address** from the instance page.

### Step 4 — Open the ports in the console

The step everyone forgets, and it makes a working server look dead.

1. On the instance page, click the **subnet** link.
2. Click the **Default Security List**.
3. **Add Ingress Rules**, and add these two:

| Source CIDR | IP Protocol | Destination Port Range |
| --- | --- | --- |
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

### Step 5 — Point the domain at it

At your registrar, add an **A record**:

| Type | Name | Value |
| --- | --- | --- |
| A | `crm` | the public IP from step 3 |

Give it fifteen minutes, then check:

```bash
ping crm.yourdomain.com
```

It should answer with the server's IP. The certificate in step 7 fails if this is not working yet,
so do not rush past it.

### Step 6 — Connect to the server

On Windows, open PowerShell in the folder holding the key you downloaded:

```powershell
icacls .\ssh-key.key /inheritance:r /grant:r "$($env:USERNAME):(R)"
ssh -i .\ssh-key.key ubuntu@<the public IP>
```

Type `yes` at the fingerprint question. You are in when the prompt reads `ubuntu@titans-crm`.

### Step 7 — Install it

One command. Five to ten minutes, and it prints what it is doing.

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/darshansathish2006/TITANS.git /tmp/titans
sudo bash /tmp/titans/scripts/setup_server.sh crm.yourdomain.com you@yourdomain.com
```

Use your real domain and a real email — the email only gets certificate expiry warnings.

It installs PostgreSQL, creates the database with a generated password, fetches the app, writes
the settings, creates the staff accounts, runs it under systemd, puts nginx in front, gets a free
HTTPS certificate that renews itself, and schedules nightly backups.

### Step 8 — Sign in

Open **https://crm.yourdomain.com**. Sign in as `admin` with `ChangeMe@123`. It will make you
choose a password before it lets you anywhere.

Then tell each person their sign-in name — `rahul`, `natesan`, `prema`, `balasubramaniam`,
`sowmiya`, `yogesh`, `venkatesan`, `quotation`, `production`, `fieldmanager`, `accounts` — and the
same starting password. Each picks their own on first sign-in.

### Step 9 — Turn on HSTS, a couple of days later

Once everyone has used it over HTTPS without trouble:

```bash
sudo nano /srv/titans/app/.env      # set SECURE_HSTS_SECONDS=31536000
sudo systemctl restart titans
```

This tells browsers never to try the site over plain HTTP again. Doing it before HTTPS is
definitely working locks people out for a year, which is why it starts off.

---

## 3b. Step by step with no credit card — Render + Neon + Supabase

Three free accounts, none of which asks for a card. About thirty minutes, entirely in a browser —
no SSH, no terminal, no key files to lose. Afterwards every `git push` redeploys the site by
itself.

Do them in this order, because the last step needs values from the first two.

### Step 1 — Neon, for the database (5 min)

1. **neon.tech** → *Sign up* → continue with GitHub.
2. Create a project: name `titans`, region **AWS ap-southeast-1 (Singapore)** — the closest to
   India.
3. On the dashboard, **Connection string** → copy it. It looks like:

   ```
   postgresql://titans_owner:XXXX@ep-cool-name-123.ap-southeast-1.aws.neon.tech/titans?sslmode=require
   ```

Keep that in a note. It is the `DATABASE_URL`. Free plan: 0.5 GB, which is tens of thousands of
leads — the database stays small because the *files* go elsewhere.

### Step 2 — Supabase, for the uploaded files (10 min)

1. **supabase.com** → *Start your project* → continue with GitHub.
2. New project: name `titans`, region **Southeast Asia (Singapore)**. It sets a database password
   — you will not need it, Neon is the database.
3. Wait for it to finish provisioning (~2 min).
4. **Storage → New bucket**, name it exactly **`titans-documents`**, leave *Public* **off**. The
   app signs its own expiring links, so the bucket must stay private.
5. **Project Settings → Storage → S3 Connection.** Copy the **Endpoint URL** and the **Region**.
   The endpoint looks like `https://abcdefgh.supabase.co/storage/v1/s3`.
6. On the same page, **New access key** → copy the **access key ID** and the **secret**. The
   secret is shown once.

You now have four values: endpoint, region, key id, secret.

> Supabase pauses a free project after **7 days with no activity**. Daily use keeps it awake; a
> long holiday does not. If it ever pauses, one *Restore* click in the dashboard brings it back
> with nothing lost.

### Step 3 — Render, to run the app (10 min)

1. **render.com** → *Get Started* → continue with GitHub, and authorise it for the **TITANS**
   repository. (This replaces the access token entirely — Render pulls the code itself, so there
   is no token to create or paste.)
2. **New → Blueprint** → pick the TITANS repo → **Apply**.

   Render reads `render.yaml` from the repo and sets almost everything up on its own. It stops and
   asks for the handful of values it cannot invent:

   | It asks for | Paste |
   | --- | --- |
   | `DATABASE_URL` | the Neon connection string from step 1 |
   | `AWS_S3_ENDPOINT_URL` | the Supabase endpoint |
   | `AWS_S3_REGION_NAME` | the Supabase region, e.g. `ap-southeast-1` |
   | `AWS_ACCESS_KEY_ID` | the Supabase key id |
   | `AWS_SECRET_ACCESS_KEY` | the Supabase secret |

3. It builds for five to ten minutes. Watch the log; it ends with the staff accounts being
   created.

### Step 4 — Nothing to fill in afterwards

Render tells the app its own address, and the app trusts it, so there is no address to paste into
`ALLOWED_HOSTS` or `CSRF_TRUSTED_ORIGINS`. (Forgetting one of those used to give "Bad Request (400)"
on every page or "CSRF verification failed" on every sign-in.) They matter only if you later add a
domain of your own.

### Step 4 — Sign in and prove the uploads work

Open the address. Sign in as `admin` / `ChangeMe@123`; it will make you change it.

Then do this before letting anyone else in — it is the one thing that can be silently misconfigured:

1. Create a test lead.
2. Upload any PDF to it.
3. Open it again from the timeline.

If it opens, files are landing in Supabase and will survive every future deploy. If it errors,
the four Supabase values are wrong — the endpoint is the usual culprit, it must end in
`/storage/v1/s3`. Delete the test lead afterwards.

### Already have a Render service from the earlier guide?

The first version of this guide told Render to run `seed_data` in both its **Build Command** and
its **Start Command**. That command creates the demo logins (`demo_sales1`…, password `Demo@123`)
and never creates the real staff, so a service set up that way shows the demo tiles on its login
page and none of your people.

The app now looks after this itself: on a live site (`DEBUG` off) `seed_data` creates no demo data,
removes any that is already there, and creates the real staff. The next deploy therefore clears it
up without you touching the dashboard. Real leads and real users are never touched.

Do change the two commands anyway, so the service stops calling something it no longer needs.
Render dashboard → your service → **Settings → Build & Deploy**:

| Setting | Set it to |
| --- | --- |
| Build Command | `bash scripts/render_build.sh` |
| Start Command | `gunicorn titans_crm.wsgi:application --workers 2 --threads 4 --timeout 300 --max-requests 500 --max-requests-jitter 50` |

Then add these under **Environment**, which move the data off Render's own disk and database
(both are wiped or expire on the free plan). Get the values from steps 1 and 2 of this section:

| Key | Value |
| --- | --- |
| `PYTHON_VERSION` | `3.12.10` (without it Render uses its newest Python, and a library can fail to install) |
| `DATABASE_URL` | the Neon connection string (replaces Render's own Postgres) |
| `AWS_STORAGE_BUCKET_NAME` | `titans-documents` |
| `AWS_S3_ENDPOINT_URL` | the Supabase S3 endpoint, ending `/storage/v1/s3` |
| `AWS_S3_REGION_NAME` | the Supabase region, e.g. `ap-southeast-1` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | the Supabase access key pair |
| `AWS_S3_ADDRESSING_STYLE` | `path` |

Then **Manual Deploy → Deploy latest commit**. When it finishes, sign in as `rahul` (or any name on
the Employees list) with `ChangeMe@123`. Two things to check under **Environment**:

- `DEBUG` must be **`False`**. If it is `True` the protection above does not apply and the demo
  data comes straight back.
- The service must be deploying the **`main`** branch of your repository, with **Auto-Deploy** on.
  If the *Events* tab shows an old commit message, that is why nothing has changed.

### Want it closer to India? Move to a Singapore service

Render cannot move a service to another region, and a new service in **Singapore** is closest to
you. If your existing one shows Oregon, Ohio or Frankfurt, make a new one instead of moving it:

1. **New → Blueprint** → pick the TITANS repo → **Apply**. `render.yaml` already says Singapore.
2. Paste the values it asks for (the Neon string and the Supabase keys — the same ones).
3. When it is up and you have signed in and tested an upload, **delete the old service**, and the old
   Render Postgres if it made one. Two free services in one account use up the 750 free hours twice
   over.

Put the Neon database in the same region as the service. Every page makes several queries, and each
one crosses the distance between them.

### Living with the free plan

**It sleeps.** After 15 minutes with nobody on it, Render stops the service; the next request
wakes it in about 50 seconds. You can stop that by having a free monitor visit the site every few
minutes:

1. **uptimerobot.com** → sign up with an email → **Add New Monitor**.
2. Type **HTTP(s)**, URL `https://<your-app>.onrender.com/healthz/`, interval **5 minutes**.

Point it at `/healthz/` and nothing else. That page touches no database. The login page does, and
a ping to it every five minutes would keep Neon awake all day and use up its free monthly
allowance (about 100 compute-hours, as of writing) in roughly two weeks, after which the database
stops until the month rolls over. Also set **Settings → Health Check Path** on the Render service
to `/healthz/`, for the same reason.

Two limits worth knowing:

- Render gives a workspace **750 free instance-hours a month**. One service awake all month is
  about 744, so it fits, but a second free web service in the same workspace will not. Render then
  suspends the free services until the month ends.
- Render's free tier is meant for testing, and it can change how idle services are treated. A ping
  is a widely used workaround, not something Render promises. If the first page each morning ever
  becomes a real problem, **Render Starter, about ₹600 a month**, removes it properly.

To let it sleep overnight and save instance-hours, use **cron-job.org** instead (also free): a job
hitting the same URL every 10 minutes between 8am and 8pm.

**1 GB of files.** Roughly 55 finished jobs. Watch it at **Supabase → Storage → Usage**. When it
gets close, either Supabase Pro (100 GB, about ₹2,000/month) or move the bucket to Cloudflare R2
(10 GB free, needs a card) by changing the same four values. Nothing in the app changes either way.

**Backups.** Neon keeps a short rewind window on the free plan (a matter of hours), which is
for mistakes, not for backups. Take a real one **once a week, and before any big change**. On your own
computer, in the project folder, with the Neon connection string as `DATABASE_URL`:

```powershell
$env:DATABASE_URL = "postgresql://...the Neon string..."
.\venv\Scripts\python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission -e admin.logentry -e sessions --indent 1 -o "titans-backup-$(Get-Date -Format yyyy-MM-dd).json"
```

That saves every lead, order, payment, follow-up and login, with passwords still scrambled, into one
file. Keep it somewhere that is not this computer alone — a Google Drive folder is fine. It is tested:
loaded into an empty database it brought back every record, the exact balances, and each person's own
password.

To restore it into a fresh database (a new Neon project, or after a disaster):

```powershell
$env:DATABASE_URL = "postgresql://...the new string..."
.\venv\Scripts\python manage.py migrate
.\venv\Scripts\python manage.py loaddata titans-backup-2026-10-05.json
```

The uploaded documents are not in that file. They live in the Supabase bucket, which keeps its own
copies, so a lost database does not lose them — but do not delete the bucket or the project.

**Updating it.** Push to `main` on GitHub. Render rebuilds and restarts by itself, migrations
included. There is nothing else to do.

---

## 4. Backups — read this one

`setup_server.sh` already runs a backup every night at 2am into `/srv/titans/backups`, keeping
seven days. That covers a bad migration or a deleted record.

It does **not** cover losing the server. For that the copies have to leave the machine — five
minutes, and the thing most likely to save you:

```bash
sudo apt install -y rclone
rclone config          # name the remote: titans-offsite
```

Point it at Google Drive, OneDrive, Dropbox or a Cloudflare R2 bucket — rclone walks you through
it. Name the remote exactly **`titans-offsite`** and the nightly job starts copying there by
itself; it checks for that name and does nothing if it is absent.

Check it after a day:

```bash
ls -lh /srv/titans/backups
sudo /usr/local/bin/titans-backup     # run one now
```

To restore onto a fresh server: install as in step 7, then

```bash
sudo systemctl stop titans
gunzip -c db-3.sql.gz | sudo -u postgres psql titans
sudo -u titans tar xzf media-3.tgz -C /srv/titans/app
sudo systemctl start titans
```

**Try this once, on purpose, before you need it.** A backup nobody has restored is a guess.

---

## 5. Updating it later

When there are changes to pick up:

```bash
ssh -i ssh-key.key ubuntu@<ip>
sudo bash /srv/titans/app/scripts/setup_server.sh crm.yourdomain.com
```

The same script pulls the new code, installs anything new, runs migrations and restarts. It leaves
your `.env`, your database and your uploaded files alone.

Security updates for the server itself, every month or two:

```bash
sudo apt update && sudo apt upgrade -y && sudo reboot
```

---

## 6. When something is wrong

| What you see | What it usually is |
| --- | --- |
| Browser hangs, never loads | Ports 80/443 not added in the Oracle console — [step 4](#step-4--open-the-ports-in-the-console) |
| *"Out of host capacity"* | The free ARM shape is busy in that availability domain. Change it in the form, or try in an hour |
| Certificate step failed | DNS is not pointing at the server yet. Check `ping crm.yourdomain.com`, then `sudo certbot --nginx -d crm.yourdomain.com` |
| **502 Bad Gateway** | The app is not running: `sudo systemctl status titans`, then `sudo journalctl -u titans -n 50` |
| *"Bad Request (400)"* | `ALLOWED_HOSTS` in `/srv/titans/app/.env` does not include the domain you typed |
| CSS missing, page looks plain | `sudo -u titans /srv/titans/app/venv/bin/python /srv/titans/app/manage.py collectstatic --noinput` |
| An upload fails on a big file | Raise `client_max_body_size` in `/etc/nginx/sites-available/titans`, then `sudo systemctl reload nginx` |
| Someone forgot their password | Employees tab → **Reset password**. No server access needed |

Useful commands:

```bash
sudo systemctl status titans        # is it running?
sudo journalctl -u titans -f        # watch the log live
sudo systemctl restart titans       # restart it
df -h /                             # how full is the disk
```

---

## 7. The other hosting options

### PythonAnywhere free — easiest, if nobody will look after a server

₹0 forever, no server admin, no cold starts, HTTPS included on `yourname.pythonanywhere.com`. The
catch is a **512 MB** disk — a few thousand documents, so two to three years — and no custom
domain on the free plan.

### Render free + Neon + Supabase — no server admin, no credit card

Now written out in full as [section 3b](#3b-step-by-step-with-no-credit-card--render--neon--supabase),
since it is the route to take when the Oracle card check cannot be cleared.

Swapping Supabase for **Cloudflare R2** later gives 10 GB instead of 1 GB and costs nothing, but
Cloudflare wants a card on file before it will enable R2. It is the same four environment
variables, plus `AWS_S3_ADDRESSING_STYLE=virtual` — R2 addresses a bucket by subdomain where
Supabase uses the path.

### If you would rather just pay

**Render Starter, around ₹600/month** — no sleeping, a real disk, one account, nothing to patch.

---

## 8. The first sign-in

`seed_employees` runs on every deploy and creates anyone missing. It never touches an account that
already exists, so it cannot reset a password somebody has chosen.

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
their own — no other page is reachable first.

The Super Admin adds anyone else from **Employees**, and can put a forgotten account back on the
default from the same screen.

---

## 9. Installing it as an app

It installs on a phone or a desktop straight from the browser. Nothing to download, nothing to
sideload, and it updates itself whenever the site does.

**Android** — open the site in Chrome, tap ⋮, **Add to Home screen**. It gets the Titans crest as
its icon and opens in its own window with no browser bars. Chrome usually offers this itself, and
there is an install button in the app's top bar.

**Windows** — open in Edge or Chrome and click the install icon in the address bar, or the same
button in the top bar. It lands in the Start menu and behaves like any other program.

**iPhone** — Safari, Share, **Add to Home Screen**.

All of this needs HTTPS. It will not offer to install over plain `http://`.

### If a real `.apk` file is needed

The install above is the same thing day to day, so only go here if you need a file to send around
or a Play Store listing. It wraps the live site in a thin Android shell, so the site has to be
deployed first.

```bash
npm install -g @bubblewrap/cli
bubblewrap init --manifest https://crm.yourdomain.com/static/manifest.webmanifest
bubblewrap build          # produces app-release-signed.apk
```

Bubblewrap needs the Android SDK and a JDK, and creates a signing key — **keep that key**, because
Android will not accept an update signed with a different one.

To stop the address bar showing inside the app, copy the `assetlinks.json` it prints onto the
server at `/srv/titans/assetlinks.json` — nginx already serves that path as
`/.well-known/assetlinks.json`. Check it with:

```bash
curl https://your-hostname/.well-known/assetlinks.json
```

### About a `.exe`

Installing from Edge already gives a Start-menu app with its own window and icon. That is the
`.exe` for a web app.

A self-contained `.exe` bundling Python and the database is possible, but it is the wrong shape
for this: each machine would carry its **own separate copy** of the data, so two people would
never see the same leads. This software is only useful when everyone is looking at one set of
records.
