"""`migrate`, with a guard for databases left over from the previous build.

The rebuild reused the app names `accounts` and `crm`, so an old database
already records `accounts.0001_initial` and `crm.0001_initial` as applied.
Django would skip creating the new tables and then fail part-way through with
an error that points nowhere useful. Instead we spot the old schema up front
and stop with instructions.

Wiping it is never automatic: set RESET_LEGACY_SCHEMA=true for one deploy to
drop the old tables and start fresh (Render's free plan has no shell, so an
environment variable is the only lever there is). Once the old tables are gone
the setting does nothing, so leaving it in place is harmless.
"""

import os

from django.core.management.base import CommandError
from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connections

# Tables that only ever existed in the previous build.
LEGACY_TABLES = {"core_companyprofile", "sales_quotation", "crm_customer"}


class Command(MigrateCommand):
    def handle(self, *args, **options):
        connection = connections[options["database"]]
        tables = set(connection.introspection.table_names())
        if LEGACY_TABLES & tables:
            if os.environ.get("RESET_LEGACY_SCHEMA", "").strip().lower() == "true":
                self._drop_all(connection, tables)
            else:
                raise CommandError(
                    "This database still holds the previous version of Titans CRM, whose tables "
                    "clash with this one. Nothing has been changed. To start fresh, set the "
                    "environment variable RESET_LEGACY_SCHEMA=true and deploy again - that "
                    "permanently deletes the old data - or point DATABASE_URL at an empty database."
                )
        return super().handle(*args, **options)

    def _drop_all(self, connection, tables):
        self.stdout.write(self.style.WARNING(f"RESET_LEGACY_SCHEMA is set - dropping {len(tables)} old tables."))
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                for table in tables:
                    cursor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            else:
                cursor.execute("PRAGMA foreign_keys = OFF")
                for table in tables:
                    if not table.startswith("sqlite_"):
                        cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
                cursor.execute("PRAGMA foreign_keys = ON")
        self.stdout.write(self.style.SUCCESS("Old schema removed. Building the new one."))
