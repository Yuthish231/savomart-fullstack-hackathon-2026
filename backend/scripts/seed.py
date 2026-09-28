"""Seed demo personas. Idempotent: re-running updates names/roles, keeps ids.

Usage (from backend/):  python -m scripts.seed
All demo users share the password below; it is documented in the README
and only meaningful for local demo databases.
"""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Role, User

DEMO_PASSWORD = "savomart@2026"

PERSONAS = [
    ("bdm.priya", "Priya Raman", Role.BDM, "+91 90000 00001"),
    ("bde.arjun", "Arjun Kumar", Role.BDE, "+91 90000 00002"),
    ("bde.divya", "Divya Shankar", Role.BDE, "+91 90000 00003"),
    ("sm.karthik", "Karthik Subramanian", Role.SM, "+91 90000 00004"),
    ("se.meena", "Meena Lakshmi", Role.SE, "+91 90000 00005"),
    ("se.rahul", "Rahul Nair", Role.SE, "+91 90000 00006"),
    ("se.farhan", "Farhan Ali", Role.SE, "+91 90000 00007"),
]


def seed_users() -> None:
    pw = hash_password(DEMO_PASSWORD)
    with SessionLocal() as db:
        for username, name, role, phone in PERSONAS:
            user = db.scalar(select(User).where(User.username == username))
            if user is None:
                db.add(User(username=username, name=name, role=role, phone=phone, password_hash=pw))
            else:
                user.name, user.role, user.phone = name, role, phone
        db.commit()
    print(f"seeded {len(PERSONAS)} personas")


if __name__ == "__main__":
    seed_users()
