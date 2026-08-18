"""Load applications from a CSV into an account.

Takes the same columns the export produces, so data can leave and come back
unchanged — and so anyone arriving from a spreadsheet has a format to aim at.

Runs with the service key, which bypasses row level security: this is an
operator's tool, not something the web application ever calls. The account is
named by email and resolved once; every row is written against that id.

    python scripts/import_applications.py rows.csv --email you@example.com --dry-run
    python scripts/import_applications.py rows.csv --email you@example.com
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import service_client  # noqa: E402

# The export's header, which is also what this accepts.
COLUMNS = [
    "company",
    "role",
    "status",
    "source",
    "location",
    "mode",
    "level",
    "submitted_on",
    "offer_closes",
    "salary_min",
    "salary_max",
    "currency",
    "salary_kind",
    "salary_period",
    "contract_offered",
    "declared_salary",
    "declared_kind",
    "declared_period",
    "declared_contract",
    "cv_version",
    "blocked_reason",
    "url",
    "notes",
]

REQUIRED = {"company", "role"}

# Anything the database will refuse is worth catching before the first insert
# rather than halfway through the file.
ENUMS = {
    "status": {
        "draft",
        "blocked",
        "submitted",
        "acknowledged",
        "replied",
        "interview",
        "offer",
        "rejected",
        "ghosted",
        "withdrawn",
    },
    "source": {
        "pracuj_pl",
        "linkedin",
        "olx",
        "justjoin",
        "rocketjobs",
        "referral",
        "direct",
        "other",
    },
    "mode": {"onsite", "hybrid", "remote"},
    "level": {"intern", "junior", "mid", "senior", "lead"},
    "salary_kind": {"gross", "net"},
    "declared_kind": {"gross", "net"},
    "salary_period": {"hour", "month", "year"},
    "declared_period": {"hour", "month", "year"},
    "contract_offered": {"employment", "b2b", "mandate", "task", "internship", "other"},
    "declared_contract": {"employment", "b2b", "mandate", "task", "internship", "other"},
}

# Statuses that mean the application actually went out, so the offer behind it
# counts as applied to rather than still under consideration.
SENT_STATUSES = {
    "submitted",
    "acknowledged",
    "replied",
    "interview",
    "offer",
    "rejected",
    "ghosted",
    "withdrawn",
}


def clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def money(value: str | None) -> float | None:
    text = (value or "").replace(" ", "").replace(" ", "").replace(",", ".").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def timestamp(day: str | None) -> str | None:
    """Midday, so a date does not slide into the previous one west of UTC."""
    day = clean(day)
    return f"{day}T12:00:00+00:00" if day else None


def check(rows: list[dict[str, Any]]) -> list[str]:
    """Everything the database would reject, found before the first write."""
    problems = []
    for number, row in enumerate(rows, start=2):  # the header is line 1
        for field in sorted(REQUIRED):
            if not clean(row.get(field)):
                problems.append(f"line {number}: {field} is empty")
        for field, allowed in ENUMS.items():
            value = clean(row.get(field))
            if value and value not in allowed:
                problems.append(f"line {number}: {field}={value} is not one of {sorted(allowed)}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Import applications from a CSV.")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--email", required=True, help="the account to import into")
    parser.add_argument("--dry-run", action="store_true", help="check and report, write nothing")
    args = parser.parse_args()

    with args.csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        print("nothing to import")
        return 0

    unknown = set(rows[0]) - set(COLUMNS)
    if unknown:
        print(f"unknown columns: {sorted(unknown)}")
        return 1

    problems = check(rows)
    if problems:
        print("\n".join(problems))
        return 1

    admin = service_client()

    users = admin.auth.admin.list_users()
    user = next((u for u in users if (u.email or "").lower() == args.email.lower()), None)
    if user is None:
        print(f"no account for {args.email}")
        return 1

    # Re-running should not double anything up.
    existing = admin.table("applications").select("offers(title, companies(name))").execute()
    already = set()
    for row in existing.data or []:
        offer = row.get("offers") or {}
        company = (offer.get("companies") or {}).get("name") or ""
        already.add(f"{company}|{offer.get('title') or ''}")

    companies: dict[str, str] = {}
    documents: dict[str, str] = {}
    written = skipped = 0

    for row in rows:
        company_name = clean(row["company"])
        title = clean(row["role"])
        status = clean(row.get("status")) or "submitted"

        if f"{company_name}|{title}" in already:
            print(f"  skip   {company_name} — {title} (already there)")
            skipped += 1
            continue

        if args.dry_run:
            print(f"  would  {company_name} — {title} [{status}]")
            written += 1
            continue

        if company_name not in companies:
            found = (
                admin.table("companies")
                .select("id")
                .eq("user_id", user.id)
                .eq("name", company_name)
                .limit(1)
                .execute()
            )
            if found.data:
                companies[company_name] = found.data[0]["id"]
            else:
                made = (
                    admin.table("companies")
                    .insert({"user_id": user.id, "name": company_name})
                    .execute()
                )
                companies[company_name] = made.data[0]["id"]

        cv_label = clean(row.get("cv_version"))
        if cv_label and cv_label not in documents:
            found = (
                admin.table("documents")
                .select("id")
                .eq("user_id", user.id)
                .eq("label", cv_label)
                .limit(1)
                .execute()
            )
            if found.data:
                documents[cv_label] = found.data[0]["id"]
            else:
                made = (
                    admin.table("documents")
                    .insert({"user_id": user.id, "label": cv_label, "kind": "cv"})
                    .execute()
                )
                documents[cv_label] = made.data[0]["id"]

        offer = (
            admin.table("offers")
            .insert(
                {
                    "user_id": user.id,
                    "company_id": companies[company_name],
                    "title": title,
                    "source": clean(row.get("source")) or "other",
                    "url": clean(row.get("url")),
                    "location": clean(row.get("location")),
                    "mode": clean(row.get("mode")),
                    "level": clean(row.get("level")),
                    "expires_at": clean(row.get("offer_closes")),
                    "salary_min": money(row.get("salary_min")),
                    "salary_max": money(row.get("salary_max")),
                    "salary_currency": (clean(row.get("currency")) or "PLN").upper()[:3],
                    "salary_kind": clean(row.get("salary_kind")),
                    "salary_period": clean(row.get("salary_period")),
                    "contract": clean(row.get("contract_offered")),
                    "status": "applied" if status in SENT_STATUSES else "shortlisted",
                }
            )
            .execute()
        )

        application = (
            admin.table("applications")
            .insert(
                {
                    "user_id": user.id,
                    "offer_id": offer.data[0]["id"],
                    "cv_document_id": documents.get(cv_label) if cv_label else None,
                    "status": status,
                    "submitted_at": timestamp(row.get("submitted_on")),
                    "declared_salary": money(row.get("declared_salary")),
                    "declared_salary_kind": clean(row.get("declared_kind")),
                    "declared_salary_period": clean(row.get("declared_period")),
                    "declared_contract": clean(row.get("declared_contract")),
                    "blocked_reason": clean(row.get("blocked_reason")),
                    "notes": clean(row.get("notes")),
                }
            )
            .execute()
        )

        # The history has to start somewhere, and it says where the row came
        # from rather than pretending it appeared by hand.
        admin.table("status_events").insert(
            {
                "user_id": user.id,
                "application_id": application.data[0]["id"],
                "from_status": None,
                "to_status": status,
                "source": "system",
                "note": f"Imported from {args.csv_path.name}",
            }
        ).execute()

        print(f"  wrote  {company_name} — {title} [{status}]")
        written += 1

    print(f"\n{'would write' if args.dry_run else 'wrote'} {written}, skipped {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
