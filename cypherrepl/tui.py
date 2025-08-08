from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional, Tuple

from langchain_core.messages import AIMessage, HumanMessage

from .config import Settings
from .db import (
    execute_cypher_with_smart_columns,
    format_rows,
    init_age,
    load_and_execute_files,
)
from .llm import build_send_cypher_tool, create_agent_executor, create_llm
from .logging_utils import VerboseCallback, set_log_sink


def _parse_toggle(value: str) -> Optional[bool]:
    val = value.lower()
    if val in {"on", "true"}:
        return True
    if val in {"off", "false"}:
        return False
    return None


def run_tui(
    cur,
    conn,
    settings: Settings,
    system_prompt: str,
    verbose: bool = False,
    files: Optional[List[str]] = None,
    execute_only: bool = False,
):
    """Launch the Textual TUI REPL.

    This function imports Textual lazily so the dependency is optional.
    """
    try:
        # Lazy imports to keep dependency optional
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.containers import Container, Horizontal, Vertical
        from textual.reactive import reactive
        from textual.timer import Timer
        from textual.widgets import Static, TextArea
        from rich.text import Text
        # Prefer RichLog for robust color rendering; fall back to Log/TextLog
        try:
            from textual.widgets import RichLog as _LogWidget  # type: ignore
        except Exception:
            try:
                from textual.widgets import Log as _LogWidget  # type: ignore
            except Exception:
                from textual.widgets import TextLog as _LogWidget  # type: ignore
        from textual import events
    except Exception as e:  # pragma: no cover - import guard
        print(
            "Textual is required for TUI mode. Install with: pip install textual --upgrade\n"
            f"Import error: {e}"
        )
        return

    class CypherReplTUI(App):
        CSS = """
        Screen {
            layout: vertical;
        }
        .title {
            height: 3;
            content-align: center middle;
            background: $boost;
            color: $text;
            text-style: bold;
        }
        .main {
            height: 1fr;
        }
        .columns {
            height: 1fr;
        }
        .panel-title {
            height: 1;
            content-align: left middle;
            color: $primary;
            text-style: bold;
        }
        .pane {
            border: tall $surface;
        }
        .footer {
            height: 3;
            background: $surface;
            color: $text;
        }
        .status {
            height: 1;
            content-align: left middle;
        }
        .commands {
            height: 1;
            content-align: left middle;
            color: $secondary;
        }
        .input {
            height: 6;
            border: round $accent;
        }
        """

        BINDINGS = [
            Binding("enter", "send", "Send", show=False),
        ]

        log_enabled = reactive(False)
        llm_enabled = reactive(True)
        connected = reactive(True)
        model_name = reactive("")

        def __init__(self):
            super().__init__()
            self._cur = cur
            self._conn = conn
            self._settings = settings
            self._system_prompt = system_prompt
            self._verbose = verbose
            self._chat_history: List[object] = []
            self._agent_executor = None
            self._callbacks = [VerboseCallback(self.log)] if verbose else None
            self._clock_timer: Optional[Timer] = None

        def compose(self) -> ComposeResult:  # type: ignore[override]
            # Title/Header
            yield Static("CONVERSATION", classes="title")

            # Main area: single conversation pane on the left; optional logs on right
            with Horizontal(classes="main"):
                with Vertical(classes="columns"):
                    # Unified conversation history
                    yield Static("Conversation", classes="panel-title")
                    self.chat_panel = self._make_log_widget(classes="pane")
                    yield self.chat_panel

                # Right-hand logs (toggle visibility via \log on/off)
                with Vertical(id="logs_container"):
                    yield Static("LOGS", classes="panel-title")
                    self.logs_panel = self._make_log_widget(classes="pane")
                    yield self.logs_panel

            # Input & footer
            # Custom TextArea to handle Enter=Send, Shift+Enter=New line, and Esc then Enter.
            app_ref = self

            class SubmitTextArea(TextArea):
                """Text input where Enter adds a newline and Esc then Enter sends."""

                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    self._armed_send = False  # Set by Esc; next Enter sends

                def on_key(self, event):  # type: ignore[override]
                    # Arm on Escape
                    if getattr(event, "key", None) == "escape":
                        self._armed_send = True
                        event.stop()
                        return
                    # On Enter: send if armed, otherwise let TextArea insert newline
                    if getattr(event, "key", None) == "enter":
                        if self._armed_send:
                            msg = self.text
                            try:
                                asyncio.create_task(app_ref._send(msg))
                            except RuntimeError:
                                app_ref.call_from_thread(asyncio.run, app_ref._send(msg))
                            self.text = ""
                            self._armed_send = False
                            event.stop()
                            return
                        # Not armed: allow default behavior (newline)
                        return  # do not stop event; TextArea handles newline
                    # Any other key disarms send
                    if self._armed_send:
                        self._armed_send = False

            self.input = SubmitTextArea(classes="input")
            # Try to set a placeholder if the attribute exists on this version.
            try:
                # Newer Textual may expose `placeholder` or `placeholder_text`.
                if hasattr(self.input, "placeholder"):
                    setattr(self.input, "placeholder", "> Your message here…  (Enter=Send, Shift+Enter=New line)")
                elif hasattr(self.input, "placeholder_text"):
                    setattr(self.input, "placeholder_text", "> Your message here…  (Enter=Send, Shift+Enter=New line)")
            except Exception:
                pass
            yield self.input

            with Container(classes="footer"):
                self.commands = Static(
                    r"Commands: \\q Quit  •  \\log [on|off]  •  \\llm [on|off]  •  \\h Help",
                    classes="commands",
                )
                yield self.commands
                self.status = Static("", classes="status")
                yield self.status

        async def on_mount(self) -> None:  # type: ignore[override]
            # Hide logs container initially
            logs_container = self.query_one("#logs_container")
            logs_container.display = False

            # Execute initial files if provided
            if files:
                try:
                    load_and_execute_files(self._cur, self._conn, files, self._settings)
                except Exception as e:  # pragma: no cover
                    self._append_log(f"[WARN] Error executing files: {e}")

            # Initialize LLM agent (may fail -> cypher-only mode)
            try:
                send_cypher_tool = build_send_cypher_tool(
                    self._cur,
                    self._conn,
                    self._settings,
                    logger=self.log if self._verbose else None,
                    is_logging_enabled=lambda: self.log_enabled,
                )
                llm = create_llm(self._settings, callbacks=self._callbacks)
                self._agent_executor = create_agent_executor(llm, send_cypher_tool, self._system_prompt)
                self.model_name = self._settings.llm.openai_model if self._settings.llm.provider in {"openai", "azure_openai"} else "?"
                self.llm_enabled = True
            except Exception as e:
                self._agent_executor = None
                self.llm_enabled = False
                self._append_log(f"[WARN] LLM initialization error: {e}")

            # Install log sink that writes into logs panel
            def _sink(line: str) -> None:
                # Route to UI only if log pane is present; UI decides visibility based on log_enabled
                self._log_write(self.logs_panel, line)

            set_log_sink(_sink)

            # If verbose, show logs panel and route stdout/stderr and logging to it
            if self._verbose:
                # Open logs view and mark as enabled
                logs_container.display = True
                self.log_enabled = True

                # Redirect stdout/stderr so any print/logging goes to the logs panel
                import sys, logging

                class _UILogStream:
                    def __init__(self, write_fn):
                        self._write_fn = write_fn
                    def write(self, data):
                        if not data:
                            return 0
                        # Split on newlines to preserve line structure
                        for part in str(data).splitlines():
                            if part:
                                self._write_fn(part)
                        return len(data)
                    def flush(self):
                        return None

                self._old_stdout, self._old_stderr = sys.stdout, sys.stderr
                ui_stream = _UILogStream(lambda s: self._log_write(self.logs_panel, s))
                sys.stdout = ui_stream  # type: ignore[assignment]
                sys.stderr = ui_stream  # type: ignore[assignment]

                # Reconfigure root logger to use our stream
                root_logger = logging.getLogger()
                for h in list(root_logger.handlers):
                    root_logger.removeHandler(h)
                handler = logging.StreamHandler(ui_stream)
                handler.setLevel(logging.DEBUG)
                formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
                handler.setFormatter(formatter)
                root_logger.addHandler(handler)
                root_logger.setLevel(logging.DEBUG)

            # Welcome message into the unified conversation panel
            self._log_write(self.chat_panel, "[cyan]▎ Hello! How can I help today?[/]")

            # Clock/status updater
            self._clock_timer = self.set_interval(1.0, self._update_status)
            self._update_status()

        async def on_unmount(self) -> None:  # type: ignore[override]
            # Restore default logging sink
            set_log_sink(None)
            if self._clock_timer is not None:
                self._clock_timer.stop()
            # Restore stdout/stderr if we redirected them
            try:
                import sys
                if hasattr(self, "_old_stdout") and self._old_stdout is not None:
                    sys.stdout = self._old_stdout  # type: ignore[assignment]
                if hasattr(self, "_old_stderr") and self._old_stderr is not None:
                    sys.stderr = self._old_stderr  # type: ignore[assignment]
            except Exception:
                pass

        def _update_status(self) -> None:
            time_str = datetime.now().strftime("%H:%M")
            model = self.model_name if self.llm_enabled else "-"
            status = (
                f"Status: [green]Connected[/] | LLM: {'[green]ON[/]' if self.llm_enabled else '[red]OFF[/]'}  "
                f"| Model: {model} | Log: {'[green]ON[/]' if self.log_enabled else '[yellow]OFF[/]'} | Time: {time_str}"
            )
            self.status.update(status)

        def _append_log(self, line: str) -> None:
            self._log_write(self.logs_panel, line)

        # --- Compatibility helpers for Textual Log/TextLog/RichLog ---
        def _make_log_widget(self, classes: str):
            # Try to construct with nicest args supported by the current widget
            # Some variants support (highlight, markup); others don't.
            for kwargs in (
                {"highlight": True, "markup": True, "classes": classes},
                {"highlight": True, "classes": classes},
                {"classes": classes},
            ):
                try:
                    panel = _LogWidget(**kwargs)  # type: ignore
                    # Annotate the panel with expected input style for logging
                    try:
                        panel_type = panel.__class__.__name__.lower()
                    except Exception:
                        panel_type = ""
                    # RichLog prefers Rich renderables; Log/TextLog prefer str
                    prefers_rich = "richlog" in panel_type
                    setattr(panel, "_prefers_rich", prefers_rich)
                    # Record if markup likely supported (Log/TextLog with markup kw)
                    setattr(panel, "_supports_markup", "textlog" in panel_type or "log" == panel_type)
                    # Force-enable markup if the widget supports it
                    try:
                        if hasattr(panel, "markup"):
                            setattr(panel, "markup", True)
                    except Exception:
                        pass
                    return panel
                except TypeError:
                    continue
            # Last resort
            panel = _LogWidget()  # type: ignore
            try:
                panel_type = panel.__class__.__name__.lower()
            except Exception:
                panel_type = ""
            setattr(panel, "_prefers_rich", "richlog" in panel_type)
            setattr(panel, "_supports_markup", "textlog" in panel_type or "log" == panel_type)
            try:
                if hasattr(panel, "markup"):
                    setattr(panel, "markup", True)
            except Exception:
                pass
            return panel

        def _log_write(self, panel, line: str) -> None:
            # Decide whether to pass rich renderable or plain string
            prefers_rich = bool(getattr(panel, "_prefers_rich", False))

            if prefers_rich:
                try:
                    renderable = Text.from_markup(line)
                except Exception:
                    renderable = Text(line)
                if hasattr(panel, "write"):
                    panel.write(renderable)  # type: ignore[attr-defined]
                    return
                # Fallback append with update
                try:
                    existing = getattr(panel, "renderable", Text(""))
                    if not isinstance(existing, Text):
                        existing = Text(str(existing))
                    existing.append_text(renderable)
                    existing.append("\n")
                    panel.update(existing)  # type: ignore[attr-defined]
                except Exception:
                    pass
                return

            # Default path: use strings; if markup isn't supported, strip tags
            try:
                text = Text.from_markup(line).plain
            except Exception:
                text = line
            if hasattr(panel, "write_line"):
                panel.write_line(text)  # type: ignore[attr-defined]
                return
            if hasattr(panel, "write"):
                panel.write(text + "\n")  # type: ignore[attr-defined]
                return
            try:
                existing = getattr(panel, "renderable", "")
                new_text = f"{existing}\n{text}" if existing else text
                panel.update(new_text)  # type: ignore[attr-defined]
            except Exception:
                pass

        async def _handle_command(self, cmd: str) -> None:
            stripped = cmd.strip()
            if stripped == "\\q":
                await self.action_quit()
                return
            if stripped == "\\h":
                help_text = (
                    "Available commands:\n"
                    "  \\q              Quit the REPL\n"
                    "  \\log [on|off]   Toggle logging of LLM and DB interactions\n"
                    "  \\llm [on|off]   Toggle LLM usage (off executes Cypher directly)\n"
                    "  \\h              Show this help message\n"
                )
                for line in help_text.splitlines():
                    self._append_log(f"[INFO] {line}")
                return
            if stripped.startswith("\\log"):
                parts = stripped.split(maxsplit=1)
                if len(parts) == 2:
                    val = _parse_toggle(parts[1])
                    if val is None:
                        self._append_log("[WARN] Usage: \\log [on|off|true|false]")
                    else:
                        self.log_enabled = val
                        # Show/hide logs pane
                        self.query_one("#logs_container").display = val
                        state = "enabled" if self.log_enabled else "disabled"
                        self._append_log(f"[INFO] Logging {state}.")
                        self._update_status()
                else:
                    self._append_log("[WARN] Usage: \\log [on|off|true|false]")
                return
            if stripped.startswith("\\llm"):
                parts = stripped.split(maxsplit=1)
                if len(parts) == 2:
                    val = _parse_toggle(parts[1])
                    if val is None:
                        self._append_log("[WARN] Usage: \\llm [on|off|true|false]")
                    else:
                        if val and self._agent_executor is None:
                            # Try to (re)initialize LLM
                            try:
                                send_cypher_tool = build_send_cypher_tool(
                                    self._cur,
                                    self._conn,
                                    self._settings,
                                    logger=self.log if self._verbose else None,
                                    is_logging_enabled=lambda: self.log_enabled,
                                )
                                llm = create_llm(self._settings, callbacks=self._callbacks)
                                self._agent_executor = create_agent_executor(
                                    llm, send_cypher_tool, self._system_prompt
                                )
                                self.model_name = self._settings.llm.openai_model
                            except Exception as e:
                                self._append_log(f"[WARN] LLM initialization error: {e}")
                                val = False
                        self.llm_enabled = val
                        state = "enabled" if self.llm_enabled else "disabled"
                        self._append_log(f"[INFO] LLM {state}.")
                        self._update_status()
                else:
                    self._append_log("[WARN] Usage: \\llm [on|off|true|false]")
                return

            self._append_log(f"[WARN] Unknown command: {stripped}")

        async def _send(self, message: str) -> None:
            text = message.strip()
            if not text:
                return
            # Commands
            if text.startswith("\\"):
                await self._handle_command(text)
                return

            # Append user message in unified history
            for line in text.splitlines():
                self._log_write(self.chat_panel, f"[green]▎ {line}[/]")

            if self.llm_enabled:
                if self._agent_executor is None:
                    self._log_write(
                        self.chat_panel,
                        "[yellow]▎ LLM is not available. Use \\llm off or check configuration.[/]",
                    )
                    return

                async def _invoke() -> Tuple[str, object]:
                    result = await asyncio.to_thread(
                        self._agent_executor.invoke, {"input": message, "chat_history": self._chat_history}
                    )
                    output = result.get("output", "")
                    return output, result

                try:
                    output, result = await _invoke()
                    if output:
                        for line in str(output).splitlines():
                            self._log_write(self.chat_panel, f"[cyan]▎ {line}[/]")
                    self._chat_history.extend([HumanMessage(content=message), AIMessage(content=str(output))])
                except Exception as e:
                    self._log_write(self.chat_panel, f"[red]▎ LLM error: {e}[/]")
            else:
                # Execute Cypher directly
                success, result = await asyncio.to_thread(
                    execute_cypher_with_smart_columns, self._cur, self._conn, message, self._settings
                )
                if success:
                    formatted = format_rows(result)
                    for line in formatted.splitlines():
                        self._log_write(self.chat_panel, f"[cyan]▎ {line}[/]")
                else:
                    err = str(result) if not isinstance(result, str) else result
                    self._log_write(self.chat_panel, f"[red]▎ {err}[/]")

        # App-level key handling not required; handled in SubmitTextArea
        def action_send(self) -> None:
            # Kept for completeness; input handles Enter logic.
            pass

    # Run app
    CypherReplTUI().run()
