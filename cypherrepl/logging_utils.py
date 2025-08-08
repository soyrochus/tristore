import logging
from typing import Optional

from langchain_core.callbacks import BaseCallbackHandler


def setup_logging(verbose: bool) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")

    if not verbose:
        for noisy in ["openai", "httpx", "urllib3", "langchain", "langchain_openai"]:
            logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger("cypherrepl")
    if verbose:
        logger.debug("Verbose logging enabled")
    return logger


class VerboseCallback(BaseCallbackHandler):
    """LangChain callback handler to expose detailed LLM & tool interactions when verbose."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def on_llm_start(self, serialized, prompts, **kwargs):  # type: ignore[override]
        try:
            for i, p in enumerate(prompts):
                self.logger.debug("LLM IN  > prompt[%d]=%r", i, (p or "")[:1000])
        except Exception:
            self.logger.debug("LLM IN  > (unable to log prompts)")

    def on_llm_end(self, response, **kwargs):  # type: ignore[override]
        try:
            gens = getattr(response, "generations", None)
            if gens and gens[0] and hasattr(gens[0][0], "text"):
                gen_text = gens[0][0].text
                self.logger.debug("LLM OUT < %r", (gen_text or "")[:1000])
            else:
                self.logger.debug("LLM OUT < (no generations)")
        except Exception:
            self.logger.debug("LLM OUT < (unparseable response)")

    def on_tool_start(self, serialized, input_str, **kwargs):  # type: ignore[override]
        try:
            self.logger.debug(
                "TOOL IN  > %s %r",
                getattr(serialized, "get", lambda *_: "tool")("name", "?"),
                (input_str or "")[:1000],
            )
        except Exception:
            self.logger.debug("TOOL IN  > (unparseable tool start)")

    def on_tool_end(self, output, **kwargs):  # type: ignore[override]
        try:
            self.logger.debug("TOOL OUT < %r", str(output)[:1000])
        except Exception:
            self.logger.debug("TOOL OUT < (unparseable output)")


def log_print(prefix: str, text: str) -> None:
    for line in text.splitlines():
        print(f"[{prefix}] {line}")

