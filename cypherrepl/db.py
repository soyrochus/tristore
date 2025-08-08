from typing import Any, List, Optional, Sequence, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import Settings
from .cypher import (
    parse_return_clause,
    preprocess_cypher_query,
    split_cypher_statements,
    sanitize_llm_query_maybe_wrapped,
)


def connect_db(settings: Settings):
    conn = psycopg2.connect(**settings.db.as_psycopg_kwargs())
    cur = conn.cursor(cursor_factory=RealDictCursor)
    return conn, cur


def init_age(cur, conn, settings: Settings) -> None:
    for stmt in settings.init_statements():
        try:
            cur.execute(stmt)
            conn.commit()
        except Exception:
            conn.rollback()


def execute_single_cypher_statement(
    cur,
    conn,
    query: str,
    settings: Settings,
    logger=None,
) -> Tuple[bool, Any]:
    try:
        clean_query = sanitize_llm_query_maybe_wrapped(preprocess_cypher_query(query))
        if not clean_query:
            return True, []
        col_def = parse_return_clause(clean_query, settings.default_cols)
        sql = f"SELECT * FROM cypher('{settings.graph_name}', $$ {clean_query} $$) AS {col_def};"
        try:
            if logger:
                logger.debug("DB IN  > %s", sql)
            cur.execute(sql)
            rows = cur.fetchall()
            conn.commit()
            if logger:
                logger.debug("DB OUT < rows=%d sample=%r", len(rows), rows[:1] if rows else None)
            return True, rows
        except Exception:
            if col_def != settings.default_cols:
                if logger:
                    logger.debug("DB retry with default column definition")
                conn.rollback()
                sql2 = f"SELECT * FROM cypher('{settings.graph_name}', $$ {clean_query} $$) AS {settings.default_cols};"
                if logger:
                    logger.debug("DB IN  > %s", sql2)
                cur.execute(sql2)
                rows = cur.fetchall()
                conn.commit()
                if logger:
                    logger.debug("DB OUT < rows=%d sample=%r", len(rows), rows[:1] if rows else None)
                return True, rows
            raise
    except Exception as e:
        conn.rollback()
        if logger:
            logger.exception("Cypher execution failed")
        msg = str(e).split("\n")[0]
        return False, f"Cypher error: {msg}"


def execute_cypher_with_smart_columns(cur, conn, query: str, settings: Settings, logger=None):
    statements = split_cypher_statements(query)
    if not statements:
        return True, []
    if len(statements) == 1:
        return execute_single_cypher_statement(cur, conn, statements[0], settings, logger)
    all_results: List[Any] = []
    for i, stmt in enumerate(statements, start=1):
        print(f"\n--- Statement {i} ---")
        success, result = execute_single_cypher_statement(cur, conn, stmt, settings, logger)
        if not success:
            return False, result
        if result:
            all_results.extend(result)
            print_result(result)
        else:
            print("(no results)")
    return True, all_results


def execute_cypher(cur, conn, query: str, settings: Settings, logger=None) -> bool:
    success, result = execute_cypher_with_smart_columns(cur, conn, query, settings, logger)
    if success:
        print_result(result)
        return True
    else:
        print(result)
        return False


def format_rows(rows: Sequence[dict]) -> str:
    if not rows:
        return "(no results)"
    keys = rows[0].keys()
    lines = ["\t".join(str(k) for k in keys)]
    for row in rows:
        lines.append("\t".join(str(row[k]) for k in keys))
    return "\n".join(lines)


def print_result(rows: Sequence[dict]) -> None:
    print(format_rows(rows))


def load_and_execute_files(cur, conn, files, settings: Settings, logger=None) -> None:
    for file_path in files:
        print(f"\n--- Executing file: {file_path} ---")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            statements = [stmt.strip() for stmt in content.split(";") if stmt.strip()]
            for i, stmt in enumerate(statements, 1):
                print(f"\nStatement {i}:")
                print(f"cypher> {stmt}")
                execute_cypher(cur, conn, stmt, settings, logger)
        except FileNotFoundError:
            print(f"Error: File '{file_path}' not found")
        except Exception as e:
            print(f"Error reading file '{file_path}': {e}")

