"""Re-take the screenshots the walkthrough plays behind its narration.

Run this after a visible change to the screens:

    python scripts/capture_guide_shots.py

It never touches the working database. It builds a throwaway SQLite one,
seeds the demo accounts, drives a handful of invented leads all the way from
enquiry to handover so every queue has something in it, photographs each
screen and writes the results to static/guide/. Nothing real ever reaches
those images.

Needs playwright and requests, both of which are already in requirements.txt:

    python -m playwright install chromium
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "static" / "guide"
PORT = 8017
BASE = f"http://127.0.0.1:{PORT}"
PASSWORD = "Demo@123"
PYTHON = sys.executable


# --------------------------------------------------------------------------
# a throwaway app to photograph
# --------------------------------------------------------------------------


def run(args, env):
    subprocess.run([PYTHON, "manage.py", *args], cwd=BASE_DIR, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def wait_for_server():
    for _ in range(60):
        try:
            if requests.get(f"{BASE}/accounts/login/", timeout=1).status_code == 200:
                return True
        except requests.RequestException:
            time.sleep(0.5)
    return False


# --------------------------------------------------------------------------
# enough invented work to fill every queue
# --------------------------------------------------------------------------


def token(session, url):
    page = session.get(url)
    found = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
    return found.group(1) if found else session.cookies.get("csrftoken")


def login(username):
    session = requests.Session()
    session.post(
        f"{BASE}/accounts/login/",
        data={"username": username, "password": PASSWORD,
              "csrfmiddlewaretoken": token(session, f"{BASE}/accounts/login/")},
        headers={"Referer": f"{BASE}/accounts/login/"},
    )
    return session


def post(session, path, data=None, files=None, referer=None):
    ref = referer or f"{BASE}{path}"
    payload = dict(data or {})
    payload["csrfmiddlewaretoken"] = token(session, ref)
    return session.post(f"{BASE}{path}", data=payload, files=files,
                        headers={"Referer": ref}, allow_redirects=True)


def fake(name):
    return (name, io.BytesIO(b"sample document"), "application/pdf")


def build_demo_work():
    """Walk three invented leads to three different points in the journey."""
    sales = login("demo_sales1")
    measure = login("demo_measure")
    quotation = login("demo_quotation")
    production = login("demo_production")
    field = login("demo_field")
    today = date.today()

    def new_lead(name, phone, where, qty, value):
        response = post(sales, "/leads/new/", {
            "customer_name": name, "phone": phone, "site_location": where,
            "lead_source": "indiamart", "approx_quantity": qty,
            "expected_value": value, "site_stage": "plastering",
            "remarks": "Wants sliding windows across the first floor",
        })
        return re.search(r"/leads/(\d+)/", response.url).group(1)

    def to_quotation(pk, number):
        post(sales, f"/leads/{pk}/measurements/", {"mode": "requested"}, referer=f"{BASE}/leads/{pk}/")
        post(measure, f"/leads/{pk}/rough/", {"notes": "W1 4ft x 5ft, W2 3ft x 4ft"},
             files={"file": fake("rough-measurement.pdf")}, referer=f"{BASE}/leads/{pk}/")
        post(quotation, f"/leads/{pk}/quotation/", {"quotation_number": number},
             files=[("files", fake("quotation.pdf")), ("elevation", fake("elevation-report.pdf"))],
             referer=f"{BASE}/leads/{pk}/")

    def to_won(pk, value, advance):
        post(sales, f"/leads/{pk}/won/", {
            "order_value": value, "advance_received": advance,
            "committed_delivery_date": (today + timedelta(days=45)).isoformat(),
            "window_count": "14", "total_sqft": "486.50",
            "won_remarks": "Confirmed on site",
        })

    def to_production(pk):
        post(measure, f"/leads/{pk}/caf-final/",
             files={"caf_signed": fake("signed-caf.pdf"), "final_measurement": fake("final-measurement.pdf")},
             referer=f"{BASE}/leads/{pk}/")
        post(production, f"/leads/{pk}/production-sheet/", files={"file": fake("production-sheet.pdf")},
             referer=f"{BASE}/leads/{pk}/")

    # 1 — sitting on follow-up, so the Follow-up tab has something in it
    follow = new_lead("Anitha Raghavan", "9840120011", "Sholinganallur, Chennai", "11", "520000")
    to_quotation(follow, "TW/QT/2026/0142")
    post(sales, f"/leads/{follow}/follow-up/",
         {"date": today.isoformat(), "time": "10:30", "note": "Talk through the glass options"},
         referer=f"{BASE}/leads/{follow}/")

    # 2 — waiting on the measurement team's approval of the production sheet
    middle = new_lead("Gokul Srinivasan", "9840120022", "Thoraipakkam, Chennai", "18", "840000")
    to_quotation(middle, "TW/QT/2026/0143")
    to_won(middle, "812000", "300000")
    to_production(middle)

    # 3 — all the way to handover, which fills accounts, the floor and warranty
    finished = new_lead("Hema Balaji", "9840120033", "Perungudi, Chennai", "9", "410000")
    to_quotation(finished, "TW/QT/2026/0144")
    to_won(finished, "398000", "150000")
    to_production(finished)
    post(measure, f"/leads/{finished}/production-approve/", referer=f"{BASE}/leads/{finished}/")
    post(production, f"/leads/{finished}/fabrication/start/", referer=f"{BASE}/queue/fabrication/{finished}/")
    post(production, f"/leads/{finished}/fabrication/checklist/",
         {field_name: "on" for field_name in [
             "chk_cutting", "chk_reinforcement", "chk_welding", "chk_beading",
             "chk_cnc", "chk_assembly", "chk_glass_cutting", "chk_glass_installation"]},
         referer=f"{BASE}/queue/fabrication/{finished}/")
    post(production, f"/leads/{finished}/fabrication/dispatch-ready/",
         referer=f"{BASE}/queue/fabrication/{finished}/")
    post(production, f"/leads/{finished}/dispatch/", {
        "installation_person": "Murugan", "invoice_number": "TW/INV/2026/0088",
        "invoice_date": today.isoformat(),
    })
    accounts = login("demo_accounts")
    post(accounts, f"/queue/accounts/{finished}/", {
        "paid_on": today.isoformat(), "amount": "120000", "remarks": "Second instalment, NEFT",
    })
    post(field, f"/leads/{finished}/handover/upload/", files={"file": fake("signed-handover.pdf")},
         referer=f"{BASE}/leads/{finished}/")

    # something on each personal list
    post(sales, "/to-do/", {
        "title": "Send the revised drawing to Anitha", "assigned_to": _user_id(sales, "Arun"),
        "due_date": (today + timedelta(days=1)).isoformat(),
        "details": "She asked for the mesh option priced separately.",
    })

    return {"follow": follow, "middle": middle, "finished": finished}


def _user_id(session, first_name):
    page = session.get(f"{BASE}/to-do/").text
    match = re.search(r'<option value="(\d+)">[^<]*' + first_name, page)
    return match.group(1) if match else ""


# --------------------------------------------------------------------------
# the photographs
# --------------------------------------------------------------------------

# (file name, demo account, path). The walkthrough looks these up by name.
def shot_list(leads):
    return [
        ("dashboard", "demo_sales1", "/"),
        ("journey", "demo_sales1", f"/leads/{leads['finished']}/?stage=caf"),
        ("leads", "demo_admin", "/leads/"),
        ("followups", "demo_sales1", "/follow-ups/"),
        ("targets", "demo_sales1", "/targets/"),
        ("todo", "demo_sales1", "/to-do/"),
        ("rough", "demo_measure", "/queue/rough-measurements/"),
        ("caf", "demo_measure", "/queue/final-measurements/"),
        ("validation", "demo_measure", "/queue/production-validation/"),
        ("quotation", "demo_quotation", "/queue/quotations/"),
        ("accounts", "demo_accounts", "/queue/accounts/"),
        ("ledger", "demo_accounts", f"/queue/accounts/{leads['finished']}/"),
        ("production", "demo_production", "/queue/production/"),
        ("fabrication", "demo_production", "/queue/fabrication/"),
        ("warranty", "demo_field", "/queue/warranty/"),
        ("complaints", "demo_field", "/service-requests/"),
        ("stage-access", "demo_admin", "/settings/stage-access/"),
        ("pipeline", "demo_admin", "/pipeline/"),
    ]


def capture(leads):
    OUT.mkdir(parents=True, exist_ok=True)
    pages = {}
    with sync_playwright() as play:
        browser = play.chromium.launch()
        for name, username, path in shot_list(leads):
            page = pages.get(username)
            if page is None:
                context = browser.new_context(viewport={"width": 1440, "height": 810},
                                              device_scale_factor=1)
                page = context.new_page()
                page.goto(f"{BASE}/accounts/login/")
                page.fill('input[name="username"]', username)
                page.fill('input[name="password"]', PASSWORD)
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle")
                # The walkthrough would otherwise be sitting over the first shot.
                page.evaluate("localStorage.setItem('tw-theme','dark')")
                pages[username] = page

            page.goto(BASE + path)
            page.wait_for_load_state("networkidle")
            page.evaluate("document.querySelectorAll('#tw-walkthrough').forEach(n => n.remove())")
            page.wait_for_timeout(1600)
            raw = page.screenshot()
            _write_jpeg(raw, OUT / f"{name}.jpg")
            print("captured", name)
        browser.close()


def _write_jpeg(raw, path):
    """Down to 1200px and JPEG — they sit at half opacity behind the avatar,
    so the file size matters more than the last pixel of sharpness."""
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    image = image.resize((1200, round(image.height * 1200 / image.width)), Image.LANCZOS)
    image.save(path, "JPEG", quality=82, optimize=True, progressive=True)


def main():
    workspace = Path(tempfile.mkdtemp(prefix="titans-guide-"))
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{workspace / 'shots.sqlite3'}"}
    server = None
    try:
        print("building a throwaway database…")
        run(["migrate", "--noinput"], env)
        run(["seed_data"], env)

        server = subprocess.Popen(
            [PYTHON, "manage.py", "runserver", f"127.0.0.1:{PORT}", "--noreload"],
            cwd=BASE_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )
        if not wait_for_server():
            raise SystemExit("the throwaway server never came up")

        print("filling the queues…")
        leads = build_demo_work()
        print("photographing…")
        capture(leads)
        print(f"done — {OUT}")
    finally:
        if server:
            server.terminate()
            server.wait(timeout=10)
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()
