from sqlalchemy import func, select

from app.database import SessionLocal, create_all
from app.models import Campaign
from seed import seed_database


def seed_if_empty() -> None:
    create_all()
    with SessionLocal() as db:
        campaign_count = db.scalar(select(func.count(Campaign.id))) or 0
    if campaign_count == 0:
        seed_database()
    else:
        print(f"Demo seed skipped: {campaign_count} campaign(s) already exist.")


if __name__ == "__main__":
    seed_if_empty()
