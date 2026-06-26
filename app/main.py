from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.db import close_pool, get_conn, open_pool


MAX_LIMIT = 100
DEFAULT_LIMIT = 25


app = FastAPI(title="CodeVector Products API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProductOut(BaseModel):
    id: UUID
    name: str
    category: str
    price: Decimal
    created_at: str
    updated_at: str
    version_id: int


class PageOut(BaseModel):
    items: list[ProductOut]
    limit: int
    next_cursor: int | None
    snapshot: int


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    price: Decimal = Field(ge=0, decimal_places=2)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    price: Decimal | None = Field(default=None, ge=0, decimal_places=2)


@app.on_event("startup")
def startup() -> None:
    open_pool()


@app.on_event("shutdown")
def shutdown() -> None:
    close_pool()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "CodeVector Products API",
        "health": "/health",
        "products": "/products?limit=25",
        "docs": "/docs",
    }


@app.get("/categories")
def categories() -> dict[str, list[str]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT category
            FROM products
            ORDER BY category
            """
        ).fetchall()
    return {"categories": [row["category"] for row in rows]}


@app.get("/products", response_model=PageOut)
def list_products(
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: Annotated[int | None, Query(ge=1)] = None,
    snapshot: Annotated[int | None, Query(ge=0)] = None,
) -> PageOut:
    with get_conn() as conn:
        if snapshot is None:
            snapshot = conn.execute(
                "SELECT COALESCE(max(version_id), 0) AS snapshot FROM product_versions"
            ).fetchone()["snapshot"]

        rows = conn.execute(
            """
            SELECT
                product_id AS id,
                name,
                category,
                price,
                created_at::text AS created_at,
                updated_at::text AS updated_at,
                version_id
            FROM product_versions
            WHERE version_id <= %(snapshot)s
              AND (%(cursor)s IS NULL OR version_id < %(cursor)s)
              AND (visible_until IS NULL OR visible_until > %(snapshot)s)
              AND (%(category)s IS NULL OR category = %(category)s)
            ORDER BY version_id DESC
            LIMIT %(limit_plus_one)s
            """,
            {
                "snapshot": snapshot,
                "cursor": cursor,
                "category": category,
                "limit_plus_one": limit + 1,
            },
        ).fetchall()

    page_rows = rows[:limit]
    next_cursor = page_rows[-1]["version_id"] if len(rows) > limit else None
    return PageOut(
        items=[ProductOut(**row) for row in page_rows],
        limit=limit,
        next_cursor=next_cursor,
        snapshot=snapshot,
    )


@app.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductCreate, response: Response) -> ProductOut:
    with get_conn() as conn:
        with conn.transaction():
            product = conn.execute(
                """
                INSERT INTO products (name, category, price)
                VALUES (%s, %s, %s)
                RETURNING id, name, category, price, created_at, updated_at
                """,
                (body.name, body.category, body.price),
            ).fetchone()
            version = conn.execute(
                """
                INSERT INTO product_versions (
                    product_id, name, category, price, created_at, updated_at
                )
                VALUES (
                    %(id)s, %(name)s, %(category)s, %(price)s,
                    %(created_at)s, %(updated_at)s
                )
                RETURNING version_id
                """,
                product,
            ).fetchone()
            conn.execute(
                "UPDATE products SET current_version_id = %s WHERE id = %s",
                (version["version_id"], product["id"]),
            )

    response.headers["Location"] = f"/products/{product['id']}"
    return ProductOut(
        id=product["id"],
        name=product["name"],
        category=product["category"],
        price=product["price"],
        created_at=str(product["created_at"]),
        updated_at=str(product["updated_at"]),
        version_id=version["version_id"],
    )


@app.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: UUID, body: ProductUpdate) -> ProductOut:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No fields to update")

    with get_conn() as conn:
        with conn.transaction():
            current = conn.execute(
                """
                SELECT id, name, category, price, created_at, current_version_id
                FROM products
                WHERE id = %s
                FOR UPDATE
                """,
                (product_id,),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Product not found")

            next_product = {
                "id": current["id"],
                "name": changes.get("name", current["name"]),
                "category": changes.get("category", current["category"]),
                "price": changes.get("price", current["price"]),
                "created_at": current["created_at"],
            }
            version = conn.execute(
                """
                INSERT INTO product_versions (
                    product_id, name, category, price, created_at, updated_at
                )
                VALUES (
                    %(id)s, %(name)s, %(category)s, %(price)s,
                    %(created_at)s, now()
                )
                RETURNING version_id, updated_at
                """,
                next_product,
            ).fetchone()
            conn.execute(
                """
                UPDATE product_versions
                SET visible_until = %s
                WHERE version_id = %s
                """,
                (version["version_id"], current["current_version_id"]),
            )
            conn.execute(
                """
                UPDATE products
                SET name = %(name)s,
                    category = %(category)s,
                    price = %(price)s,
                    updated_at = %(updated_at)s,
                    current_version_id = %(version_id)s
                WHERE id = %(id)s
                """,
                {
                    **next_product,
                    "updated_at": version["updated_at"],
                    "version_id": version["version_id"],
                },
            )

    return ProductOut(
        id=next_product["id"],
        name=next_product["name"],
        category=next_product["category"],
        price=next_product["price"],
        created_at=str(next_product["created_at"]),
        updated_at=str(version["updated_at"]),
        version_id=version["version_id"],
    )
