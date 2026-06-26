import argparse
import sys
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed products with bulk SQL.")
    parser.add_argument("--count", type=int, default=200_000)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing products and product versions before seeding.",
    )
    args = parser.parse_args()

    with psycopg.connect(settings.database_url) as conn:
        with conn.transaction():
            conn.execute((ROOT / "schema.sql").read_text(encoding="utf-8"))
            if args.reset:
                conn.execute("TRUNCATE product_versions, products RESTART IDENTITY CASCADE")

            conn.execute(
                """
                WITH generated AS (
                    SELECT
                        gen_random_uuid() AS id,
                        'Product ' || gs::text AS name,
                        categories[(gs % array_length(categories, 1)) + 1] AS category,
                        round((5 + random() * 995)::numeric, 2) AS price,
                        now()
                            - ((random() * 120)::int || ' days')::interval
                            - ((random() * 86400)::int || ' seconds')::interval AS created_at
                    FROM generate_series(1, %s) AS gs,
                         (SELECT ARRAY[
                            'electronics',
                            'books',
                            'home',
                            'fashion',
                            'sports',
                            'toys',
                            'beauty',
                            'grocery'
                         ] AS categories) AS c
                ),
                inserted_products AS (
                    INSERT INTO products (id, name, category, price, created_at, updated_at)
                    SELECT
                        id,
                        name,
                        category,
                        price,
                        created_at,
                        created_at + ((random() * 30)::int || ' days')::interval
                    FROM generated
                    RETURNING id, name, category, price, created_at, updated_at
                ),
                inserted_versions AS (
                    INSERT INTO product_versions (
                        product_id, name, category, price, created_at, updated_at
                    )
                    SELECT id, name, category, price, created_at, updated_at
                    FROM inserted_products
                    ORDER BY updated_at ASC, id ASC
                    RETURNING product_id, version_id
                )
                UPDATE products AS p
                SET current_version_id = v.version_id
                FROM inserted_versions AS v
                WHERE p.id = v.product_id
                """,
                (args.count,),
            )

    print(f"Seeded {args.count:,} products.")


if __name__ == "__main__":
    main()
