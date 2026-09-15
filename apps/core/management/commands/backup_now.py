import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Creates a timestamped backup snapshot: the full database plus every "
        "uploaded/generated file under MEDIA_ROOT (photos, quotations, "
        "certificates, exports). Intended to be run on a schedule (Windows Task "
        "Scheduler / cron) -- see DEPLOYMENT.md."
    )

    def handle(self, *args, **options):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = Path(settings.BASE_DIR) / "backups" / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        db = settings.DATABASES["default"]
        engine = db["ENGINE"]

        if "sqlite3" in engine:
            src = Path(db["NAME"])
            dest = snapshot_dir / f"db_{timestamp}.sqlite3"
            shutil.copy2(src, dest)
            self.stdout.write(self.style.SUCCESS(f"Database snapshot (SQLite copy): {dest}"))
        elif "postgresql" in engine:
            dest = snapshot_dir / f"db_{timestamp}.sql"
            cmd = [
                "pg_dump",
                f"--host={db.get('HOST') or 'localhost'}",
                f"--port={db.get('PORT') or 5432}",
                f"--username={db.get('USER')}",
                f"--dbname={db.get('NAME')}",
                "--no-password",
                "--file", str(dest),
            ]
            env = None
            if db.get("PASSWORD"):
                import os

                env = os.environ.copy()
                env["PGPASSWORD"] = db["PASSWORD"]
            try:
                subprocess.run(cmd, check=True, env=env)
                self.stdout.write(self.style.SUCCESS(f"Database snapshot (pg_dump): {dest}"))
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                self.stderr.write(self.style.ERROR(f"pg_dump failed ({exc}). Is PostgreSQL client installed and on PATH?"))
        else:
            self.stderr.write(self.style.WARNING(f"Unrecognised database engine '{engine}': skipped DB snapshot."))

        media_root = Path(settings.MEDIA_ROOT)
        if media_root.exists() and any(media_root.iterdir()):
            archive_base = snapshot_dir / f"media_{timestamp}"
            shutil.make_archive(str(archive_base), "zip", root_dir=media_root)
            self.stdout.write(self.style.SUCCESS(f"Media snapshot: {archive_base}.zip"))
        else:
            self.stdout.write("No media files to back up yet.")

        self.stdout.write(self.style.SUCCESS(f"Backup complete: {snapshot_dir}"))
        self.stdout.write(
            "Copy this backups/ folder to an external drive or cloud storage regularly -- "
            "a local-only backup does not protect against disk failure or theft."
        )
