import argparse
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from langchain_core.messages import AIMessage, HumanMessage

from .config import get_settings
from .db import (
    connect_db,
    execute_cypher_with_smart_columns,
    format_rows,
    init_age,
    load_and_execute_files,
    print_result,
)
from .llm import build_send_cypher_tool, create_agent_executor, create_llm
from .logging_utils import VerboseCallback, log_print, setup_logging


def _parse_toggle(value: str) -> Optional[bool]:
    val = value.lower()
    if val in {"on", "true"}:
        return True
    if val in {"off", "false"}:
        return False
    return None


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Cypher REPL for AGE/PostgreSQL")
    parser.add_argument("files", nargs="*", help="Cypher files to load and execute")
    parser.add_argument("-e", "--execute", action="store_true", help="Execute files and exit (do not start REPL)")
    parser.add_argument("-t", "--tui", action="store_true", help="Launch the Textual TUI instead of the standard REPL")
    parser.add_argument("-s", "--system-prompt", help="Path to a file containing a system prompt for the LLM")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output (show stack traces on errors)")
    args = parser.parse_args()

    logger = setup_logging(args.verbose)

    print(f"Cypher REPL for AGE/PostgreSQL - graph: {settings.graph_name}")

    # Validate LLM provider configuration early
    try:
        create_llm(settings)
    except ValueError as e:
        print(f"LLM Configuration Error: {e}")
        return

    try:
        conn, cur = connect_db(settings)
    except Exception as e:
        if args.verbose:
            raise
        from psycopg2 import OperationalError

        if isinstance(e, OperationalError):
            print(f"Database connection failed: {e}")
            print("Please ensure the PostgreSQL server is running and accessible.")
        else:
            print(f"Database error: {e}")
        return

    try:
        try:
            init_age(cur, conn, settings)
            system_prompt = settings.default_system_prompt
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

        if args.tui:
            from .tui import run_tui

            # If only executing files in batch mode
            if args.execute:
                if args.files:
                    load_and_execute_files(cur, conn, args.files, settings, logger if args.verbose else None)
                print("\nExecution complete.")
                return

            run_tui(cur, conn, settings, system_prompt, verbose=args.verbose, files=args.files or None, execute_only=args.execute)
            return

        log_enabled = False
        llm_enabled = True

        if args.files:
            load_and_execute_files(cur, conn, args.files, settings, logger if args.verbose else None)

        if args.execute:
            print("\nExecution complete.")
            return

        # Build LLM agent if possible, otherwise fall back to cypher-only mode
        agent_executor = None
        try:
            callbacks = [VerboseCallback(logger)] if args.verbose else None
            send_cypher_tool = build_send_cypher_tool(
                cur,
                conn,
                settings,
                logger if args.verbose else None,
                is_logging_enabled=lambda: log_enabled,
            )
            llm = create_llm(settings, callbacks=callbacks)
            agent_executor = create_agent_executor(llm, send_cypher_tool, system_prompt)
        except Exception as e:
            if args.verbose:
                logger.exception("LLM initialization error")
            else:
                print(f"LLM initialization error: {e}")
            print("Running in Cypher-only mode (LLM disabled)")
            llm_enabled = False

        # REPL intro
        if not args.files:
            print("Enter adds a new line. Esc+Enter executes your  Natural Language or Cypher query.")
        print("Use Ctrl+D or \\q to quit. \\h for list of commands.\n")

        session = PromptSession(history=FileHistory(settings.history_file), multiline=True)
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
                        val = _parse_toggle(parts[1])
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
                        val = _parse_toggle(parts[1])
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
                        print(
                            "LLM is not available. Use \\llm off to disable LLM mode or check your configuration."
                        )
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
                    success, result = execute_cypher_with_smart_columns(
                        cur, conn, text, settings, logger if args.verbose else None
                    )
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
    finally:
        try:
            cur.close()
        finally:
            conn.close()
