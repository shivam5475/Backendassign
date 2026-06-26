# CodeVector Product Browser Backend

Small FastAPI + PostgreSQL backend for browsing about 200,000 products newest first, with category filtering and cursor pagination.

## Why this shape?

The important part is stable pagination while products are changing. Plain `OFFSET` pagination gets slower as pages get deeper and can duplicate or skip rows when new products are inserted. Plain keyset pagination over a mutable `products.updated_at` column is faster, but can still miss a product if that product is updated and moves ahead of the user's current cursor.

This app uses immutable product versions:

- `products` stores the current product row.
- `product_versions` stores every browsable version with a monotonic `version_id`.
- The first `/products` request captures `snapshot = max(version_id)`.
- Later pages pass the same `snapshot` and the returned `next_cursor`.
- Updates create a new version and mark the previous version with `visible_until`.

That means a browsing session reads the product list exactly as it existed at its first page. Products inserted or updated later do not create duplicates or holes in that session.

## API

```text
GET /health
GET /categories
GET /products?limit=25&category=books
GET /products?limit=25&category=books&snapshot=200000&cursor=199950
POST /products
PATCH /products/{id}
```

`GET /products` returns:

```json
{
  "items": [],
  "limit": 25,
  "next_cursor": 199975,
  "snapshot": 200000
}
```

Use `next_cursor` and `snapshot` from the previous response to fetch the next page. If `next_cursor` is `null`, there are no more results.

## Local setup

Create a PostgreSQL database, then:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your `DATABASE_URL`.

Create tables and seed 200,000 products:

```bash
python scripts/seed.py --reset --count 200000
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for interactive API docs.

## Deployment

Works well with:

- Backend: Render free web service
- Database: Neon or Supabase Postgres

Render start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set `DATABASE_URL` in Render environment variables. Run the seed command once against the hosted database.

## What I would improve with more time

- Add automated integration tests with Testcontainers or a disposable Neon branch.
- Add a tiny UI for browsing and category switching.
- Add auth or admin controls around create/update endpoints.
- Add observability around slow queries and pagination depth.

## AI usage note

AI helped scaffold the FastAPI project, write the bulk seed SQL, and reason through pagination failure cases. The main thing to verify carefully was the mutable-row pagination problem: keyset pagination alone is not enough when updates can move unseen products ahead of the cursor, so the implementation uses immutable versions plus a snapshot high-water mark.
