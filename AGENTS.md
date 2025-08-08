
You are a senior Python engineer. 

Refactor the existing tristor/cypher_llm_repl.py into a new modile cypherrepl (see down for a suggested structure).

DO NOT CHANGE the cypher_llm_repl.py ! 
RECREATE the repl into this new module

It should use 100% of funcionality of cypher_llm_repl.py
the same command line parameters, commands etc

# Packaging & Entry Point
- Structure the project as an installable package:
  cypherrepl/
    __init__.py
    __main__.py         # `python -m cypherrepl` entrypoint
    cli.py              # argument parsing, boot mode selection (headless vs repl_
    config.py           # env + defaults + typed settings
    db.py               # DB connection, AGE init, cypher execution, column inference
    llm.py              # LLM provider factory, tool wiring, system prompt
    cypher.py           # query sanitization, statement splitting, smart column logic
    logging_utils.py    # log setup, VerboseCallback, prefixed logging helpers
    
- `__main__.py` should delegate to `cli.main()`.
- Keep the code self-contained (no placeholders), same behaviors/logic as before, but surface them via repl.


Deliver the full package code with the structure above, ready to run with:
  python -m cypherrepl
and headless mode with:
  python -m cypherrepl -e path/to/file.cypher
```
