from __future__ import annotations

"""SQL loader that resolves query name -> SQL snippet from app/sql/*.sql.

Supports named queries using the format:
-- name: query_name
SELECT ...;
"""

from functools import lru_cache
from pathlib import Path


# Base directory where .sql query files live.
_SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


@lru_cache(maxsize=None)
def _parse_named_queries(sql_text: str) -> dict[str, str]:
    queries: dict[str, list[str]] = {}
    current_name: str | None = None
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("-- name:"):
            current_name = stripped.split(":", 1)[1].strip()
            queries[current_name] = []
            continue
        if current_name is not None:
            queries[current_name].append(line)
    return {name: "\n".join(lines).strip() for name, lines in queries.items()}


@lru_cache(maxsize=None)
def get_query(name: str) -> str:
    """Load SQL text by query name from app/sql/*.sql files."""
    for path in _SQL_DIR.glob("*.sql"):
        sql_text = path.read_text(encoding="utf-8")
        queries = _parse_named_queries(sql_text)
        if name in queries:
            return queries[name]
    raise FileNotFoundError(f"SQL query not found: {name}")
