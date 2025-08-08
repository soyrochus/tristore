Add a new option to the cypherrepl module 

Only change the cypherrepl module

This option should be -t --tui

It should launch an alternative REPL created with the Textual library. Use the latest version.

Use colours where sensible. 

Meaning: a TUI similar to applications like htop etc. 


Here are visual representation of two modes. Minimal commands, clear booleans, model shown only if LLM is ON.

# 1) Chat TUI (LLM left, You right) — compact

This is the default view

```
+──────────────────────────────────────────────────────────────────────────────+
|                               CONVERSATION                                   |
+──────────────────────────────────────────────────────────────────────────────+
| LLM / Assistant (60%)                         | You / Question (40%)         |
|───────────────────────────────────────────────┼──────────────────────────────|
| ▎Hello! How can I help today?                 |                              |
| ▎I can assist with…                           | ▎What can you do?            |
| ▎Here’s a code sample…                        | ▎Compare X vs Y…             |
| … older messages above …                      | … older messages above …     |
+───────────────────────────────────────────────┼──────────────────────────────+
| INPUT — Multi-line editor                                                    |
| > Your message here…  (Enter=Send, Shift+Enter=New line)                     |
| Commands: \q Quit  •  \log [on|off]  •  \llm [on|off]  •  \h Help            |
| Status: Connected | LLM: ON  | Model: gpt-X | Log: OFF | Time: 19:34         |
+──────────────────────────────────────────────────────────────────────────────+
```

# 2) Chat + Right-hand Logs — compact

This view should be enabled when \log on

```
+──────────────────────────────────────────────────────────────────────────────+
|                                  CHAT + LOGS                                 |
+───────────────────────────────┬──────────────────────────────────────────────+
|  CONVERSATION                 │  LOGS (opened with \log on)                  |
|  LLM / Assistant   |  You     │──────────────────────────────────────────────|
|────────────────────┼──────────│ [12:03:11] INFO  Loaded profile "default"    |
| ▎Answer …          | ▎Q …     │ [12:03:12] DEBUG prompt_len=948              |
| ▎Follow-up …       | ▎Reply   │ [12:03:13] CALL  tool.search("foo")          |
| … history …        | … … …    │ [12:03:14] WARN  nearing rate-limit          |
+────────────────────┼──────────┼──────────────────────────────────────────────+
|  INPUT — Multi-line editor    │  (auto-scroll; \log off to close)            |
| > Draft message … (Enter=Send, Shift+Enter=New line)                         |
| Commands: \q Quit  •  \log [on|off]  •  \llm [on|off]  •  \h Help            |
| Status: Connected | LLM: OFF | Model: -     | Log: ON  | Time: 19:34         |
+──────────────────────────────────────────────────────────────────────────────+
```

Resuse all functions, commands, structure etc. the TUI should be optional 

