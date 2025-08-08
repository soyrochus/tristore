import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv


# Load .env early if present
load_dotenv()


def getenv(key: str, default: Optional[str]) -> str:
    val = os.environ.get(key)
    return val if val is not None else (default or "")


@dataclass(frozen=True)
class DBSettings:
    host: str
    port: int
    dbname: str
    user: str
    password: str

    def as_psycopg_kwargs(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
        }


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    openai_api_key: Optional[str]
    openai_model: str
    openai_temperature: float
    azure_api_key: Optional[str]
    azure_endpoint: Optional[str]
    azure_api_version: str
    azure_deployment: str


@dataclass(frozen=True)
class Settings:
    db: DBSettings
    graph_name: str
    default_cols: str
    history_file: str
    default_system_prompt: str
    llm: LLMSettings

    def init_statements(self) -> List[str]:
        return [
            "CREATE EXTENSION IF NOT EXISTS age;",
            "LOAD 'age';",
            "SET search_path = ag_catalog, \"$user\", public;",
            f"SELECT create_graph('{self.graph_name}');",
        ]


DEFAULT_SYSTEM_PROMPT = (
    "You are a Cypher agent for an AGE/PostgreSQL graph database. "
    "You have one tool: send_cypher(query).\n\n"
    "When to call the tool:\n"
    "- The user asks to show/run/find/create/update/delete data, or to count/filter/analyze data stored in the graph.\n\n"
    "When NOT to call the tool:\n"
    "- The user wants concepts, syntax help, or examples without execution — then answer in text only.\n\n"
    "Rules for tool usage:\n"
    "- Emit PURE CYPHER ONLY (no SQL wrapper, no graph name, no semicolons).\n"
    "  Example: MATCH (n) RETURN n AS node\n"
    "- Prefer clear aliases in RETURN when multiple items are returned.\n\n"
    "Examples:\n"
    "User: Show the first 5 nodes.\n"
    "Assistant: (call send_cypher with \"MATCH (n) RETURN n AS node LIMIT 5\")\n\n"
    "User: How do I count Person nodes?\n"
    "Assistant: Explain: \"MATCH (p:Person) RETURN count(p) AS count\" (no tool call)."
)


def get_settings() -> Settings:
    db = DBSettings(
        host=getenv("PGHOST", "localhost"),
        port=int(getenv("PGPORT", "5432")),
        dbname=getenv("PGDATABASE", "postgres"),
        user=getenv("PGUSER", "postgres"),
        password=getenv("PGPASSWORD", ""),
    )

    llm = LLMSettings(
        provider=getenv("LLM_PROVIDER", "openai"),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        openai_model=getenv("OPENAI_MODEL_NAME", "gpt-4.1"),
        openai_temperature=float(getenv("OPENAI_TEMPERATURE", "0")),
        azure_api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_api_version=getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        azure_deployment=getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
    )

    return Settings(
        db=db,
        graph_name=getenv("AGE_GRAPH", "demo"),
        default_cols="(result agtype)",
        history_file=os.path.expanduser("~/.cypher_repl_history"),
        default_system_prompt=DEFAULT_SYSTEM_PROMPT.strip(),
        llm=llm,
    )

