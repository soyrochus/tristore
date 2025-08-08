import argparse
import os
import re
import logging
from typing import Optional, Any, List

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
import psycopg2
from psycopg2.extras import RealDictCursor

# Load .env if present
load_dotenv()

def getenv(key, default):
    return os.environ.get(key, default)

DB_PARAMS = {
    "host": getenv("PGHOST", "localhost"),
    "port": int(getenv("PGPORT", 5432)),
    "dbname": getenv("PGDATABASE", "postgres"),
    "user": getenv("PGUSER", "postgres"),
    "password": getenv("PGPASSWORD", ""),
}
GRAPH_NAME = getenv("AGE_GRAPH", "demo")
DEFAULT_COLS = "(result agtype)"
HISTORY_FILE = os.path.expanduser("~/.cypher_repl_history")

# -------- Ultra-tight system prompt (pure Cypher, no SQL) --------
DEFAULT_SYSTEM_PROMPT = """
You are a Cypher agent for an AGE/PostgreSQL graph database. You have one tool: send_cypher(query).

When to call the tool:
- The user asks to show/run/find/create/update/delete data, or to count/filter/analyze data stored in the graph.

When NOT to call the tool:
- The user wants concepts, syntax help, or examples without execution — then answer in text only.

Rules for tool usage:
- Emit PURE CYPHER ONLY (no SQL wrapper, no graph name, no semicolons).
  Example: MATCH (n) RETURN n AS node
- Prefer clear aliases in RETURN when multiple items are returned.

Examples:
User: Show the first 5 nodes.
Assistant: (call send_cypher with "MATCH (n) RETURN n AS node LIMIT 5")

User: How do I count Person nodes?
Assistant: Explain: "MATCH (p:Person) RETURN count(p) AS count" (no tool call).
""".strip()

OPENAI_API_KEY = getenv("OPENAI_API_KEY", None)
OPENAI_MODEL_NAME = getenv("OPENAI_MODEL_NAME", "gpt-4.1")
OPENAI_TEMPERATURE = float(getenv("OPENAI_TEMPERATURE", "0"))

# LLM Provider configuration
LLM_PROVIDER = getenv("LLM_PROVIDER", "openai")

# Azure OpenAI configuration
AZURE_OPENAI_API_KEY = getenv("AZURE_OPENAI_API_KEY", None)
AZURE_OPENAI_ENDPOINT = getenv("AZURE_OPENAI_ENDPOINT", None)
AZURE_OPENAI_API_VERSION = getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
AZURE_OPENAI_DEPLOYMENT_NAME = getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")

def create_llm(callbacks=None):
    """Create and return the appropriate LLM instance based on provider configuration"""
    common_kwargs: dict[str, Any] = {"temperature": OPENAI_TEMPERATURE}
    if callbacks is not None:
        common_kwargs["callbacks"] = callbacks
    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OpenAI API key is required when using 'openai' provider. Please set OPENAI_API_KEY environment variable.")
        return ChatOpenAI(model=OPENAI_MODEL_NAME, **common_kwargs)
    if LLM_PROVIDER == "azure_openai":
        if not AZURE_OPENAI_API_KEY:
            raise ValueError("Azure OpenAI API key is required when using 'azure_openai' provider. Please set AZURE_OPENAI_API_KEY environment variable.")
        if not AZURE_OPENAI_ENDPOINT:
            raise ValueError("Azure OpenAI endpoint is required when using 'azure_openai' provider. Please set AZURE_OPENAI_ENDPOINT environment variable.")
        return AzureChatOpenAI(
            api_key=AZURE_OPENAI_API_KEY,  # type: ignore
            azure_deployment=AZURE_OPENAI_DEPLOYMENT_NAME,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            **common_kwargs,
        )
    raise ValueError(f"Unknown LLM provider: '{LLM_PROVIDER}'. Supported providers are 'openai' and 'azure_openai'.")


class VerboseCallback(BaseCallbackHandler):
    """LangChain callback handler to expose detailed LLM & tool interactions when verbose."""
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def on_llm_start(self, serialized, prompts, **kwargs):  # type: ignore[override]
        try:
            for i, p in enumerate(prompts):
                self.logger.debug("LLM IN  > prompt[%d]=%r", i, (p or '')[:1000])
        except Exception:
            self.logger.debug("LLM IN  > (unable to log prompts)")

    def on_llm_end(self, response, **kwargs):  # type: ignore[override]
        try:
            gens = getattr(response, 'generations', None)
            if gens and gens[0] and hasattr(gens[0][0], 'text'):
                gen_text = gens[0][0].text
                self.logger.debug("LLM OUT < %r", (gen_text or '')[:1000])
            else:
                self.logger.debug("LLM OUT < (no generations)")
        except Exception:
            self.logger.debug("LLM OUT < (unparseable response)")

    def on_tool_start(self, serialized, input_str, **kwargs):  # type: ignore[override]
        try:
            self.logger.debug("TOOL IN  > %s %r", getattr(serialized, 'get', lambda *_: 'tool')("name", "?"), (input_str or '')[:1000])
        except Exception:
            self.logger.debug("TOOL IN  > (unparseable tool start)")

    def on_tool_end(self, output, **kwargs):  # type: ignore[override]
        try:
            self.logger.debug("TOOL OUT < %r", str(output)[:1000])
        except Exception:
            self.logger.debug("TOOL OUT < (unparseable output)")

INIT_STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS age;",
    "LOAD 'age';",
    "SET search_path = ag_catalog, \"$user\", public;",
    f"SELECT create_graph('{GRAPH_NAME}');"
]

def parse_return_clause(query):
    """
    Parse the RETURN clause from a Cypher query to determine column definitions.
    Returns appropriate column definition string for AGE.
    """
    query = query.strip()
    return_match = re.search(r'\bRETURN\s+(.+?)(?:\s+(?:ORDER|LIMIT|SKIP|UNION)|$)', query, re.IGNORECASE | re.DOTALL)
    if not return_match:
        return DEFAULT_COLS
    return_clause = return_match.group(1).strip()
    items = [item.strip() for item in return_clause.split(',')]
    if len(items) == 1:
        return DEFAULT_COLS
    cols = []
    for i, item in enumerate(items):
        alias_match = re.search(r'\s+AS\s+(\w+)', item, re.IGNORECASE)
        if alias_match:
            col_name = alias_match.group(1)
        else:
            var_match = re.search(r'(\w+)', item)
            col_name = var_match.group(1) if var_match else f"col{i+1}"
        cols.append(f"{col_name} agtype")
    return f"({', '.join(cols)})"

def preprocess_cypher_query(query):
    """Remove trailing semicolons not supported by AGE's cypher() function."""
    return query.strip().rstrip(';')

def split_cypher_statements(query):
    """Split a string into individual Cypher statements by semicolon."""
    return [stmt.strip() for stmt in query.split(';') if stmt.strip()]

# --- extra: sanitize LLM slips that return SQL wrappers; extract pure Cypher ---
_SQL_WRAPPER_RE = re.compile(
    r"SELECT\s+\*\s+FROM\s+cypher\([^$]*\$\$\s*(?P<cypher>.+?)\s*\$\$\)\s+AS\s*\([^)]+\);?",
    re.IGNORECASE | re.DOTALL,
)
_CYPHER_FN_RE = re.compile(
    r"cypher\([^$]*\$\$\s*(?P<cypher>.+?)\s*\$\$\)\s*;?",
    re.IGNORECASE | re.DOTALL,
)

def _sanitize_llm_query_maybe_wrapped(q: str) -> str:
    """
    If the LLM mistakenly emits a SQL wrapper or cypher(...) call,
    extract the inner pure Cypher. Otherwise return q unchanged.
    """
    s = q.strip()
    m = _SQL_WRAPPER_RE.search(s)
    if m:
        return m.group("cypher").strip().rstrip(';')
    m = _CYPHER_FN_RE.search(s)
    if m:
        return m.group("cypher").strip().rstrip(';')
    # fallback: just strip trailing semicolon
    return s.rstrip(';')

def execute_cypher_with_smart_columns(cur, conn, query, logger: Optional[logging.Logger] = None):
    """Execute a Cypher query with intelligent column detection (optionally verbose)."""
    statements = split_cypher_statements(query)
    if not statements:
        return True, []
    if len(statements) == 1:
        return execute_single_cypher_statement(cur, conn, statements[0], logger)
    all_results = []
    for i, stmt in enumerate(statements, start=1):
        print(f"\n--- Statement {i} ---")
        success, result = execute_single_cypher_statement(cur, conn, stmt, logger)
        if not success:
            return False, result
        if result:
            all_results.extend(result)
            print_result(result)
        else:
            print("(no results)")
    return True, all_results

def execute_single_cypher_statement(cur, conn, query, logger: Optional[logging.Logger] = None):
    """Execute a single Cypher statement with intelligent column detection."""
    try:
        # sanitize any accidental SQL wrapper from the LLM
        clean_query = _sanitize_llm_query_maybe_wrapped(preprocess_cypher_query(query))
        if not clean_query:
            return True, []
        col_def = parse_return_clause(clean_query)
        sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {clean_query} $$) AS {col_def};"
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
            if col_def != DEFAULT_COLS:
                if logger:
                    logger.debug("DB retry with default column definition")
                conn.rollback()
                sql2 = f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {clean_query} $$) AS {DEFAULT_COLS};"
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
        msg = str(e).split('\n')[0]
        if logger:
            logger.exception("Cypher execution failed")
        return False, f"Cypher error: {msg}"

def format_rows(rows):
    if not rows:
        return "(no results)"
    keys = rows[0].keys()
    lines = ["\t".join(str(k) for k in keys)]
    for row in rows:
        lines.append("\t".join(str(row[k]) for k in keys))
    return "\n".join(lines)

def print_result(rows):
    print(format_rows(rows))

def log_print(prefix: str, text: str) -> None:
    for line in text.splitlines():
        print(f"[{prefix}] {line}")

def execute_cypher(cur, conn, query, logger: Optional[logging.Logger] = None):
    """Execute a Cypher query and return success status"""
    success, result = execute_cypher_with_smart_columns(cur, conn, query, logger)
    if success:
        print_result(result)
        return True
    else:
        print(result)
        return False

def load_and_execute_files(cur, conn, files, logger: Optional[logging.Logger] = None):
    """Load and execute Cypher statements from files"""
    for file_path in files:
        print(f"\n--- Executing file: {file_path} ---")
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            statements = [stmt.strip() for stmt in content.split(';') if stmt.strip()]
            for i, stmt in enumerate(statements, 1):
                print(f"\nStatement {i}:")
                print(f"cypher> {stmt}")
                execute_cypher(cur, conn, stmt, logger)
        except FileNotFoundError:
            print(f"Error: File '{file_path}' not found")
        except Exception as e:
            print(f"Error reading file '{file_path}': {e}")

def main():
    parser = argparse.ArgumentParser(description="Cypher REPL for AGE/PostgreSQL")
    parser.add_argument("files", nargs="*", help="Cypher files to load and execute")
    parser.add_argument("-e", "--execute", action="store_true", help="Execute files and exit (do not start REPL)")
    parser.add_argument("-s", "--system-prompt", help="Path to a file containing a system prompt for the LLM")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output (show stack traces on errors)")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
        for noisy in ["openai", "httpx", "urllib3", "langchain", "langchain_openai"]:
            logging.getLogger(noisy).setLevel(logging.WARNING)
    logger = logging.getLogger("cypher_llm_repl")
    if args.verbose:
        logger.debug("Verbose logging enabled")

    print(f"Cypher REPL for AGE/PostgreSQL - graph: {GRAPH_NAME}")

    # Validate LLM provider configuration early
    try:
        create_llm()
    except ValueError as e:
        print(f"LLM Configuration Error: {e}")
        return

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except psycopg2.OperationalError as e:
        if args.verbose:
            raise
        print(f"Database connection failed: {e}")
        print("Please ensure the PostgreSQL server is running and accessible.")
        return
    except Exception as e:
        if args.verbose:
            raise
        print(f"Database error: {e}")
        return

    try:
        for stmt in INIT_STATEMENTS:
            try:
                cur.execute(stmt)
                conn.commit()
            except Exception:
                conn.rollback()

        system_prompt = DEFAULT_SYSTEM_PROMPT
        if args.system_prompt:
            try:
                with open(args.system_prompt, "r", encoding="utf-8") as f:
                    system_prompt = f.read()
            except OSError as e:
                print(f"Error reading system prompt file: {e}")
    except Exception as e:
        if args.verbose:
            raise
        print(f"Initialization error: {e}")
        return

    log_enabled = False
    llm_enabled = True

    def parse_toggle(value: str) -> Optional[bool]:
        val = value.lower()
        if val in {"on", "true"}:
            return True
        if val in {"off", "false"}:
            return False
        return None

    def build_send_cypher():
        @tool
        def send_cypher(query: str) -> str:
            """
            Execute a pure Cypher query on the AGE/PostgreSQL graph database and return results.

            Args:
                query: The full Cypher statement ONLY (no SQL wrapper, no graph name, no trailing semicolon).
                       Examples:
                         MATCH (n) RETURN n AS node
                         MATCH (p:Person) RETURN count(p) AS count
                         CREATE (:Person {name: 'Alice'})

            Use this tool when the user asks to retrieve/create/update/delete graph data,
            or to count/filter/analyze data stored in the graph.

            Do NOT use this tool for conceptual questions or syntax explanations.

            Returns:
                A formatted text table of results, or an error message.
            """
            if log_enabled:
                log_print("TOOL", query)
            # sanitize in case the LLM accidentally emits SQL wrapper
            cypher_only = _sanitize_llm_query_maybe_wrapped(query)
            success, result = execute_cypher_with_smart_columns(
                cur, conn, cypher_only, logger if args.verbose else None
            )
            if success:
                formatted = format_rows(result)
                if log_enabled:
                    log_print("DB", formatted)
                return formatted
            else:
                error_msg = str(result) if not isinstance(result, str) else result
                if log_enabled:
                    log_print("DB", error_msg)
                return error_msg

        return send_cypher

    try:
        if args.files:
            load_and_execute_files(cur, conn, args.files, logger if args.verbose else None)

        if args.execute:
            print("\nExecution complete.")
            return

        agent_executor = None
        try:
            callbacks = [VerboseCallback(logger)] if args.verbose else None
            send_cypher_tool = build_send_cypher()
            llm = create_llm(callbacks=callbacks)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder("chat_history"),
                    ("user", "{input}"),
                    MessagesPlaceholder("agent_scratchpad"),
                ]
            )
            agent = create_tool_calling_agent(llm, [send_cypher_tool], prompt)
            agent_executor = AgentExecutor(agent=agent, tools=[send_cypher_tool])
        except Exception as e:
            if args.verbose:
                logger.exception("LLM initialization error")
            else:
                print(f"LLM initialization error: {e}")
            print("Running in Cypher-only mode (LLM disabled)")
            llm_enabled = False

        if not args.files:
            print("Enter adds a new line. Esc+Enter executes your Cypher query.")
        print("Use Ctrl+D or \\q to quit. \\h for list of commands.\n")

        session = PromptSession(history=FileHistory(HISTORY_FILE), multiline=True)

        chat_history = []
        while True:
            try:
                text = session.prompt("cypher> ")
                stripped = text.strip()
                if not stripped:
                    continue
                if stripped == "\\q":
                    break
                if stripped == "\\h":
                    print("Available commands:")
                    print("  \\q              Quit the REPL")
                    print("  \\log [on|off]   Toggle logging of LLM and DB interactions")
                    print("  \\llm [on|off]   Toggle LLM usage (off executes Cypher directly)")
                    print("  \\h              Show this help message")
                    continue
                if stripped.startswith("\\log"):
                    parts = stripped.split(maxsplit=1)
                    if len(parts) == 2:
                        val = parse_toggle(parts[1])
                        if val is None:
                            print("Usage: \\log [on|off|true|false]")
                        else:
                            log_enabled = val
                            state = "enabled" if log_enabled else "disabled"
                            print(f"Logging {state}.")
                    else:
                        print("Usage: \\log [on|off|true|false]")
                    continue
                if stripped.startswith("\\llm"):
                    parts = stripped.split(maxsplit=1)
                    if len(parts) == 2:
                        val = parse_toggle(parts[1])
                        if val is None:
                            print("Usage: \\llm [on|off|true|false]")
                        else:
                            llm_enabled = val
                            state = "enabled" if llm_enabled else "disabled"
                            print(f"LLM {state}.")
                    else:
                        print("Usage: \\llm [on|off|true|false]")
                    continue

                if llm_enabled:
                    if agent_executor is None:
                        print("LLM is not available. Use \\llm off to disable LLM mode or check your configuration.")
                        continue
                    result = agent_executor.invoke({"input": text, "chat_history": chat_history})
                    output = result.get("output", "")
                    if output:
                        if log_enabled:
                            log_print("LLM", output)
                        else:
                            print(output)
                    chat_history.extend([HumanMessage(content=text), AIMessage(content=output)])
                else:
                    if log_enabled:
                        log_print("TOOL", text)
                    success, result = execute_cypher_with_smart_columns(cur, conn, text, logger if args.verbose else None)
                    if success:
                        formatted = format_rows(result)
                        if log_enabled:
                            log_print("DB", formatted)
                        else:
                            print_result(result)
                    else:
                        error_msg = str(result) if not isinstance(result, str) else result
                        if log_enabled:
                            log_print("DB", error_msg)
                        else:
                            print(error_msg)
            except KeyboardInterrupt:
                print("\n(Use Ctrl+D or \\q to quit. \\h for list of commands)")
            except EOFError:
                print("\nExiting REPL.")
                break
    except Exception as e:
        if args.verbose:
            raise
        print(e)
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
