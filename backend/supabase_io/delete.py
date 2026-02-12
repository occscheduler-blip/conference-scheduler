from __future__ import annotations

from supabase_io import write as _write


def drop_table(
    table_name: str,
    *,
    schema: str = "public",
    if_exists: bool = True,
    db_url: str | None = None,
) -> None:
    """Drop a table by name.

    Args:
        table_name (str): the destination table name.
        schema (str, optional): the destination schema. Defaults to "public".
        if_exists (bool, optional): include IF EXISTS in SQL. Defaults to True.
        db_url (str | None, optional): explicit Postgres connection URL. If omitted, uses env/config.

    Returns:
        None: this function does not return a value.
    """
    schema = _write._validate_identifier(schema, "schema")
    table_name = _write._validate_identifier(table_name, "table name")
    db_url = _write._resolve_db_url(db_url)
    psycopg = _write._require_psycopg()

    sql_text = "DROP TABLE IF EXISTS {}" if if_exists else "DROP TABLE {}"
    with _write._connection(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL(sql_text).format(
                    psycopg.sql.Identifier(schema, table_name),
                )
            )
