from typing import Any, Callable, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from .config import Settings
from .db import execute_cypher_with_smart_columns, format_rows
from .logging_utils import log_print


def create_llm(settings: Settings, callbacks=None):
    common_kwargs: dict[str, Any] = {"temperature": settings.llm.openai_temperature}
    if callbacks is not None:
        common_kwargs["callbacks"] = callbacks
    provider = settings.llm.provider
    if provider == "openai":
        if not settings.llm.openai_api_key:
            raise ValueError(
                "OpenAI API key is required when using 'openai' provider. Please set OPENAI_API_KEY environment variable."
            )
        return ChatOpenAI(model=settings.llm.openai_model, **common_kwargs)
    if provider == "azure_openai":
        if not settings.llm.azure_api_key:
            raise ValueError(
                "Azure OpenAI API key is required when using 'azure_openai' provider. Please set AZURE_OPENAI_API_KEY environment variable."
            )
        if not settings.llm.azure_endpoint:
            raise ValueError(
                "Azure OpenAI endpoint is required when using 'azure_openai' provider. Please set AZURE_OPENAI_ENDPOINT environment variable."
            )
        return AzureChatOpenAI(
            api_key=settings.llm.azure_api_key,  # type: ignore
            azure_deployment=settings.llm.azure_deployment,
            api_version=settings.llm.azure_api_version,
            azure_endpoint=settings.llm.azure_endpoint,
            **common_kwargs,
        )
    raise ValueError(
        f"Unknown LLM provider: '{provider}'. Supported providers are 'openai' and 'azure_openai'."
    )


def build_send_cypher_tool(
    cur,
    conn,
    settings: Settings,
    logger=None,
    is_logging_enabled: Optional[Callable[[], bool]] = None,
):
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
        if is_logging_enabled and is_logging_enabled():
            log_print("TOOL", query)
        success, result = execute_cypher_with_smart_columns(
            cur, conn, query, settings, logger
        )
        if success:
            formatted = format_rows(result)
            if is_logging_enabled and is_logging_enabled():
                log_print("DB", formatted)
            return formatted
        else:
            error_msg = str(result) if not isinstance(result, str) else result
            if is_logging_enabled and is_logging_enabled():
                log_print("DB", error_msg)
            return error_msg

    return send_cypher


def create_agent_executor(llm, tool, system_prompt: str) -> AgentExecutor:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder("chat_history"),
            ("user", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )
    agent = create_tool_calling_agent(llm, [tool], prompt)
    return AgentExecutor(agent=agent, tools=[tool])

