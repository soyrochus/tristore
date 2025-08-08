import re
from typing import List


def preprocess_cypher_query(query: str) -> str:
    """Remove trailing semicolons not supported by AGE's cypher() function."""
    return query.strip().rstrip(";")


def split_cypher_statements(query: str) -> List[str]:
    """Split a string into individual Cypher statements by semicolon."""
    return [stmt.strip() for stmt in query.split(";") if stmt.strip()]


def parse_return_clause(query: str, default_cols: str) -> str:
    """
    Parse the RETURN clause from a Cypher query to determine column definitions.
    Returns appropriate column definition string for AGE.
    """
    q = query.strip()
    return_match = re.search(r"\bRETURN\s+(.+?)(?:\s+(?:ORDER|LIMIT|SKIP|UNION)|$)", q, re.IGNORECASE | re.DOTALL)
    if not return_match:
        return default_cols
    return_clause = return_match.group(1).strip()
    items = [item.strip() for item in return_clause.split(",")]
    if len(items) == 1:
        return default_cols
    cols = []
    for i, item in enumerate(items):
        alias_match = re.search(r"\s+AS\s+(\w+)", item, re.IGNORECASE)
        if alias_match:
            col_name = alias_match.group(1)
        else:
            var_match = re.search(r"(\w+)", item)
            col_name = var_match.group(1) if var_match else f"col{i+1}"
        cols.append(f"{col_name} agtype")
    return f"({', '.join(cols)})"


# Sanitize LLM slips that return SQL wrappers; extract pure Cypher
_SQL_WRAPPER_RE = re.compile(
    r"SELECT\s+\*\s+FROM\s+cypher\([^$]*\$\$\s*(?P<cypher>.+?)\s*\$\$\)\s+AS\s*\([^)]+\);?",
    re.IGNORECASE | re.DOTALL,
)
_CYPHER_FN_RE = re.compile(
    r"cypher\([^$]*\$\$\s*(?P<cypher>.+?)\s*\$\$\)\s*;?",
    re.IGNORECASE | re.DOTALL,
)


def sanitize_llm_query_maybe_wrapped(q: str) -> str:
    """If the LLM emits SQL wrapper or cypher(...), extract inner pure Cypher."""
    s = q.strip()
    m = _SQL_WRAPPER_RE.search(s)
    if m:
        return m.group("cypher").strip().rstrip(";")
    m = _CYPHER_FN_RE.search(s)
    if m:
        return m.group("cypher").strip().rstrip(";")
    return s.rstrip(";")

