from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from app.config import settings


class DatabaseNotConfigured(RuntimeError):
    pass


def _database_url() -> str:
    if settings.database_url is None:
        raise DatabaseNotConfigured("DATABASE_URL is not configured")
    return settings.database_url


def open_pool() -> None:
    return None


def close_pool() -> None:
    return None


@contextmanager
def get_conn() -> Iterator[Connection]:
    with psycopg.connect(_database_url(), row_factory=dict_row) as conn:
        yield conn
