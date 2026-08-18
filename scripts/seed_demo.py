"""Fill an account with invented applications, to see the interface under load.

Twenty real rows show whether a page works. Two hundred invented ones show
whether it holds together — where a chart runs out of room, where a table stops
being readable, where a funnel finally has enough shape to say something.

Everything written here is recorded in a manifest beside the CSV, so `--undo`
removes exactly what this created and nothing else. Invented rows sitting
undetected among real ones would poison the only numbers this product exists to
produce.

    python scripts/seed_demo.py --email you@example.com --count 200
    python scripts/seed_demo.py --email you@example.com --undo
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.client import service_client  # noqa: E402

MANIFEST = Path(__file__).resolve().parents[1] / "private" / "seed_manifest.json"

# Invented, and obviously so on inspection — nothing here should ever be
# mistaken for a company someone actually applied to.
COMPANIES = [
    "Nordlys Systemy",
    "Kwadrat Software",
    "Bielik Digital",
    "Cztery Wiatry",
    "Modrzew Technologie",
    "Ostoja IT",
    "Zenit Rozwiązania",
    "Przęsło Labs",
    "Bursztyn Analytics",
    "Kruszywo Cloud",
    "Wierzba Consulting",
    "Reduta Systems",
    "Fala Automatyka",
    "Jarzębina Soft",
    "Granit Integracje",
    "Latarnia Studio",
    "Wapiennik Data",
    "Sosnowy Bór IT",
    "Pryzmat Rozwój",
    "Klepsydra Works",
    "Zorza Platform",
    "Bystrzyca Tech",
    "Podkowa Systems",
    "Świt Automatyzacje",
]

ROLES = [
    ("Specjalista ds. wsparcia IT", "junior"),
    ("Młodszy administrator systemów", "junior"),
    ("Konsultant Service Desk", "mid"),
    ("Specjalista ds. automatyzacji", "mid"),
    ("Analityk procesów biznesowych", "mid"),
    ("Koordynator projektów IT", "mid"),
    ("Przedstawiciel handlowy B2B", "mid"),
    ("Specjalista ds. wdrożeń", "mid"),
    ("Inżynier wsparcia aplikacji", "mid"),
    ("Administrator sieci", "senior"),
]

CITIES = ["Gliwice", "Katowice", "Zabrze", "Tychy", "Rybnik", "Bytom", "Chorzów", "Zdalnie"]
SOURCES = ["pracuj_pl", "linkedin", "olx", "justjoin", "rocketjobs", "referral", "direct"]
MODES = ["onsite", "hybrid", "remote"]
CV_LABELS = ["Ogólna", "Helpdesk", "Sprzedaż B2B", "Automatyzacje", "Koordynator"]


# Roughly how a real search goes: most sent applications hear nothing back.
# Deliberately unflattering — a demo that shows a 60% response rate teaches the
# interface nothing about the shape it will actually have to draw.
def outcome(chance: random.Random) -> tuple[list[str], str]:
    """A plausible path through the statuses, and where it comes to rest."""
    roll = chance.random()
    if roll < 0.08:
        return ["draft"], "draft"
    if roll < 0.12:
        return ["blocked"], "blocked"
    if roll < 0.55:
        return ["submitted", "ghosted"], "ghosted"
    if roll < 0.70:
        return ["submitted"], "submitted"
    if roll < 0.82:
        return ["submitted", "replied", "rejected"], "rejected"
    if roll < 0.88:
        return ["submitted", "acknowledged", "replied"], "replied"
    if roll < 0.95:
        return ["submitted", "replied", "interview", "rejected"], "rejected"
    if roll < 0.98:
        return ["submitted", "replied", "interview"], "interview"
    return ["submitted", "replied", "interview", "offer"], "offer"


def find_user(admin, email: str):
    for user in admin.auth.admin.list_users():
        if (user.email or "").lower() == email.lower():
            return user
    return None


def undo(admin) -> int:
    if not MANIFEST.exists():
        print("no manifest — nothing was seeded from here")
        return 0

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    offers = manifest.get("offers", [])
    companies = manifest.get("companies", [])

    # Deleting the offer takes its application and history with it.
    for offer_id in offers:
        admin.table("offers").delete().eq("id", offer_id).execute()
    for company_id in companies:
        admin.table("companies").delete().eq("id", company_id).execute()

    MANIFEST.unlink()
    print(f"removed {len(offers)} seeded applications and {len(companies)} companies")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed invented applications.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--undo", action="store_true", help="remove what this created")
    parser.add_argument("--seed", type=int, default=7, help="for a repeatable set")
    args = parser.parse_args()

    admin = service_client()
    if args.undo:
        return undo(admin)

    if MANIFEST.exists():
        print(f"{MANIFEST.name} already exists — run --undo first, or delete it by hand")
        return 1

    user = find_user(admin, args.email)
    if user is None:
        print(f"no account for {args.email}")
        return 1

    chance = random.Random(args.seed)
    today = datetime.now(UTC)
    manifest: dict[str, list[str]] = {"companies": [], "offers": []}
    MANIFEST.parent.mkdir(exist_ok=True)

    def remember() -> None:
        """Record what exists so far.

        Written as we go rather than at the end: the first run of this script
        failed halfway and left rows behind that nothing could identify, which
        is the exact situation the manifest exists to prevent.
        """
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # CV versions are shared with whatever is already there rather than
    # duplicated, so the per-version numbers stay meaningful.
    documents: dict[str, str] = {}
    for label in CV_LABELS:
        found = (
            admin.table("documents").select("id").eq("user_id", user.id).eq("label", label).limit(1)
        ).execute()
        if found.data:
            documents[label] = found.data[0]["id"]
        else:
            made = (
                admin.table("documents")
                .insert({"user_id": user.id, "label": label, "kind": "cv"})
                .execute()
            )
            documents[label] = made.data[0]["id"]

    for index in range(args.count):
        # Cycled, not drawn at random: two draws landing on the same name is
        # what broke the first run against the unique (user_id, name) index.
        company_name = f"{COMPANIES[index % len(COMPANIES)]} {index // len(COMPANIES) + 1}"
        company = (
            admin.table("companies").insert({"user_id": user.id, "name": company_name}).execute()
        )
        company_id = company.data[0]["id"]
        manifest["companies"].append(company_id)
        remember()

        title, level = chance.choice(ROLES)
        low = chance.choice([5500, 6000, 6500, 7000, 7500, 8000, 9000, 10000])
        path, resting = outcome(chance)
        sent_days_ago = chance.randint(1, 120)
        sent_at = today - timedelta(days=sent_days_ago)

        offer = (
            admin.table("offers")
            .insert(
                {
                    "user_id": user.id,
                    "company_id": company_id,
                    "title": title,
                    "source": chance.choice(SOURCES),
                    "location": chance.choice(CITIES),
                    "mode": chance.choice(MODES),
                    "level": level,
                    "salary_min": low,
                    "salary_max": low + chance.choice([1500, 2000, 3000, 4000]),
                    "salary_currency": "PLN",
                    "salary_kind": "gross",
                    "salary_period": "month",
                    "contract": chance.choice(["employment", "b2b", "mandate"]),
                    "status": "applied" if "submitted" in path else "shortlisted",
                    "expires_at": (sent_at + timedelta(days=chance.randint(5, 40)))
                    .date()
                    .isoformat(),
                }
            )
            .execute()
        )
        offer_id = offer.data[0]["id"]
        manifest["offers"].append(offer_id)
        remember()

        application = (
            admin.table("applications")
            .insert(
                {
                    "user_id": user.id,
                    "offer_id": offer_id,
                    "cv_document_id": documents[chance.choice(CV_LABELS)],
                    "status": resting,
                    "submitted_at": sent_at.isoformat() if "submitted" in path else None,
                    "declared_salary": low + chance.choice([0, 500, 1000]),
                    "declared_salary_kind": "gross",
                    "declared_salary_period": "month",
                    "declared_contract": "employment",
                    "notes": "Wpis demonstracyjny — dane wymyślone.",
                }
            )
            .execute()
        )
        application_id = application.data[0]["id"]

        # The history is what the funnel and the flow chart read, so the whole
        # path is written, not just where it ended.
        previous = None
        moment = sent_at
        for step in path:
            admin.table("status_events").insert(
                {
                    "user_id": user.id,
                    "application_id": application_id,
                    "from_status": previous,
                    "to_status": step,
                    "source": "system",
                    "note": "seed",
                    "created_at": moment.isoformat(),
                }
            ).execute()
            previous = step
            moment = moment + timedelta(days=chance.randint(2, 12))

        if (index + 1) % 25 == 0:
            print(f"  {index + 1}/{args.count}")

    MANIFEST.parent.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nseeded {args.count} applications; manifest at {MANIFEST}")
    print("undo with: python scripts/seed_demo.py --email ... --undo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
