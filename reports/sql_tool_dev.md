# Read-only SQL tool development check

The local `make sql-smoke` query counted 200 synthetic customers by region: AMER 70, EMEA 69, APAC 61. It returned three rows in about 4 ms with a 10-row request cap. The dedicated reader role was used through the project database connection.

Seven focused SQL-tool tests passed against the actual local PostgreSQL database. They covered grammar allowlisting, bound literal and tenant values, write/escape rejection, transaction/read-only/timeout setup, row truncation, tenant filtering, and a rejected delete that left customer count unchanged. Full-suite and lockfile results are recorded in `docs/PROGRESS.md`.

The timeout is configured and its setup is unit-tested; no deliberately expensive query was run against the shared local database. This milestone does not claim protection against every PostgreSQL workload or production multitenant isolation.
