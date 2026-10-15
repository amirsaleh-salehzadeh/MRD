import sys

from sqlalchemy.dialects.postgresql import insert

from app.db.session import SessionLocal, initialize_database
from app.db.models import Product
from scripts.cli import run_cli

SEED_PRODUCTS = [
    {"sku": "BAN-001", "name": "Bananas 1kg", "price_cents": 199, "stock": 50},
    {"sku": "APL-003", "name": "Apples 1kg", "price_cents": 299, "stock": 40},
    {"sku": "COF-005", "name": "Coffee", "price_cents": 895, "stock": 25},
]


def seed() -> None:
    initialize_database()
    with SessionLocal.begin() as session:
        session.execute(
            insert(Product)
            .values(SEED_PRODUCTS)
            .on_conflict_do_nothing(index_elements=[Product.sku])
        )


if __name__ == "__main__":

    def main() -> None:
        seed()
        print("Seed products inserted where missing; existing stock was preserved.")

    sys.exit(run_cli(main))
