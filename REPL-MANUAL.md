# Cypher LLM REPL Manual

## Overview

The Cypher LLM REPL is an interactive command-line tool that provides two modes for querying PostgreSQL databases with Apache AGE (Graph) extensions:

1. **LLM Mode (default)**: Natural language queries processed by an AI assistant
2. **Direct Mode**: Direct Cypher query execution

## Features

- **Dual Query Modes**: Switch between AI-assisted and direct Cypher execution
- **Smart Column Detection**: Automatically handles complex return clauses with multiple columns
- **Multi-Statement Support**: Execute multiple Cypher statements in a single input
- **Relationship Display**: Proper formatting of nodes, relationships, and paths
- **Command History**: Persistent command history across sessions
- **Logging**: Optional logging of LLM interactions and database responses

## Getting Started

### Basic Usage

```bash
python cypher_llm_repl.py
```

### With Files

```bash
# Execute Cypher files and start REPL
python cypher_llm_repl.py init_graph.cypher

# Execute files and exit (no REPL)
python cypher_llm_repl.py -e init_graph.cypher queries.cypher
```

### Custom System Prompt

```bash
python cypher_llm_repl.py -s custom_prompt.txt
```

## REPL Commands

| Command | Description |
|---------|-------------|
| `\q` | Quit the REPL |
| `\h` | Show help message |
| `\llm [on\|off]` | Toggle LLM mode (AI assistance) |
| `\log [on\|off]` | Toggle logging of interactions |

## LLM Mode Examples

In LLM mode (default), you can use natural language to query and manipulate your graph database.

### Example Session - LLM Mode

```
cypher> \llm on
LLM enabled.

cypher> show all in the database
Here is everything currently in the database, including all nodes and their relationships:

1. Node: TestNode (id: 844424930131969, properties: {msg: "Hello, AGE!"})
   - Relationship: OWNS
   - Target Node: TargetNode (id: 1125899906842625, properties: {effect: "Booh!"})

2. Node: Window (id: 4222124650659841, properties: {})
   - Relationship: HAS_BUTTON
   - Target Node: Button (id: 4785074604081153, properties: {name: "start"})

If you want to see nodes that are not connected to any relationships, or need more details about any node or relationship, let me know!

cypher> create a new person named Alice who is 30 years old
I'll create a new Person node for Alice with age 30.

result
{"id": 1407374883553281, "label": "Person", "properties": {"name": "Alice", "age": 30}}::vertex

The Person node for Alice has been successfully created with id 1407374883553281.

cypher> make Alice friends with the TestNode
I'll create a FRIENDS relationship between Alice and the TestNode.

(no results)

The FRIENDS relationship between Alice and TestNode has been created successfully.

cypher> show me all the people and their connections
Here are all the people in the database and their connections:

1. **Alice** (Person, age: 30)
   - FRIENDS with → TestNode (msg: "Hello, AGE!")

2. **TestNode** (msg: "Hello, AGE!")
   - OWNS → TargetNode (effect: "Booh!")
   - FRIENDS with ← Alice (Person, age: 30)

Alice is connected to TestNode through a FRIENDS relationship, and TestNode owns TargetNode.
```

### Natural Language Query Examples

```
cypher> find all nodes with more than 2 relationships
cypher> show me the shortest path between Alice and any Button
cypher> create a company called TechCorp and make Alice work there
cypher> delete all OWNS relationships
cypher> show me all isolated nodes (nodes with no relationships)
```

## Direct Mode Examples

In direct mode, you write raw Cypher queries that are executed directly against the database.

### Example Session - Direct Mode

```
cypher> \llm off
LLM disabled.

cypher> MATCH (n) RETURN n
result
{"id": 844424930131969, "label": "TestNode", "properties": {"msg": "Hello, AGE!"}}::vertex
{"id": 1125899906842625, "label": "TargetNode", "properties": {"effect": "Booh!"}}::vertex
{"id": 4222124650659841, "label": "Window", "properties": {}}::vertex
{"id": 4785074604081153, "label": "Button", "properties": {"name": "start"}}::vertex
{"id": 1407374883553281, "label": "Person", "properties": {"name": "Alice", "age": 30}}::vertex

cypher> MATCH (n)-[r]->(m) RETURN n, r, m
n	r	m
{"id": 844424930131969, "label": "TestNode", "properties": {"msg": "Hello, AGE!"}}::vertex	{"id": 2251799813685250, "label": "OWNS", "end_id": 1125899906842625, "start_id": 844424930131969, "properties": {}}::edge	{"id": 1125899906842625, "label": "TargetNode", "properties": {"effect": "Booh!"}}::vertex
{"id": 4222124650659841, "label": "Window", "properties": {}}::vertex	{"id": 4503599627370497, "label": "HAS_BUTTON", "end_id": 4785074604081153, "start_id": 4222124650659841, "properties": {}}::edge	{"id": 4785074604081153, "label": "Button", "properties": {"name": "start"}}::vertex
{"id": 1407374883553281, "label": "Person", "properties": {"name": "Alice", "age": 30}}::vertex	{"id": 2533274790395905, "label": "FRIENDS", "end_id": 844424930131969, "start_id": 1407374883553281, "properties": {}}::edge	{"id": 844424930131969, "label": "TestNode", "properties": {"msg": "Hello, AGE!"}}::vertex

cypher> MATCH p = (a)-[r]->(b) RETURN p
result
[{"id": 844424930131969, "label": "TestNode", "properties": {"msg": "Hello, AGE!"}}::vertex, {"id": 2251799813685250, "label": "OWNS", "end_id": 1125899906842625, "start_id": 844424930131969, "properties": {}}::edge, {"id": 1125899906842625, "label": "TargetNode", "properties": {"effect": "Booh!"}}::vertex]::path
[{"id": 4222124650659841, "label": "Window", "properties": {}}::vertex, {"id": 4503599627370497, "label": "HAS_BUTTON", "end_id": 4785074604081153, "start_id": 4222124650659841, "properties": {}}::edge, {"id": 4785074604081153, "label": "Button", "properties": {"name": "start"}}::vertex]::path
[{"id": 1407374883553281, "label": "Person", "properties": {"name": "Alice", "age": 30}}::vertex, {"id": 2533274790395905, "label": "FRIENDS", "end_id": 844424930131969, "start_id": 1407374883553281, "properties": {}}::edge, {"id": 844424930131969, "label": "TestNode", "properties": {"msg": "Hello, AGE!"}}::vertex]::path

cypher> CREATE (p:Product {name: 'Laptop', price: 999.99}) RETURN p
result
{"id": 1688849860263937, "label": "Product", "properties": {"name": "Laptop", "price": 999.99}}::vertex
```

### Multiple Statement Execution

You can execute multiple Cypher statements in a single input by separating them with semicolons:

```
cypher> CREATE (a:Author {name: 'Jane Doe'}); CREATE (b:Book {title: 'Graph Theory'}); MATCH (a:Author), (b:Book) CREATE (a)-[:WROTE]->(b)

--- Statement 1 ---
result
{"id": 1970324836974593, "label": "Author", "properties": {"name": "Jane Doe"}}::vertex

--- Statement 2 ---
result
{"id": 2251799813685251, "label": "Book", "properties": {"title": "Graph Theory"}}::vertex

--- Statement 3 ---
(no results)
```

## Advanced Features

### Smart Column Detection

The REPL automatically detects return clauses and adjusts column definitions for optimal display:

```cypher
# Single column - uses default formatting
MATCH (n) RETURN n

# Multiple columns - creates appropriate column definitions  
MATCH (n)-[r]->(m) RETURN n as source, r as relationship, m as target

# Complex expressions work automatically
MATCH (n) RETURN n.name as name, count(*) as degree
```

### Logging Mode

Enable logging to see the internal interactions:

```
cypher> \log on
Logging enabled.

cypher> show all nodes
[TOOL] MATCH (n) RETURN n
[DB] result
{"id": 844424930131969, "label": "TestNode", "properties": {"msg": "Hello, AGE!"}}::vertex
{"id": 1125899906842625, "label": "TargetNode", "properties": {"effect": "Booh!"}}::vertex

[LLM] Here are all the nodes currently in the database:

1. **TestNode** (id: 844424930131969)
   - Properties: {msg: "Hello, AGE!"}

2. **TargetNode** (id: 1125899906842625) 
   - Properties: {effect: "Booh!"}

These are the 2 nodes currently stored in your graph database.
```

## Configuration

### Environment Variables

Set these in your `.env` file or environment:

```bash
# Database connection
PGHOST=localhost
PGPORT=5432
PGDATABASE=postgres
PGUSER=postgres
PGPASSWORD=secret

# Graph name
AGE_GRAPH=demo

# OpenAI settings (for LLM mode)
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL_NAME=gpt-4.1
OPENAI_TEMPERATURE=0
```

### Command Line Options

```bash
python cypher_llm_repl.py [options] [files...]

Options:
  -h, --help            Show help message
  -e, --execute         Execute files and exit (no REPL)
  -s FILE, --system-prompt FILE
                        Path to custom system prompt file
```

## Tips and Best Practices

### LLM Mode Tips

1. **Be specific**: "Show me all Person nodes with their relationships" is better than "show me stuff"
2. **Use domain language**: The AI understands graph terminology like "nodes", "relationships", "paths"
3. **Ask for explanations**: "Explain what this query does: MATCH (n)-[r*2..3]->(m) RETURN n, m"

### Direct Mode Tips

1. **Semicolons are optional**: Both `MATCH (n) RETURN n` and `MATCH (n) RETURN n;` work
2. **Multiple statements**: Separate with semicolons for batch execution
3. **Path queries**: Use `MATCH p = (a)-[r]->(b) RETURN p` to see full path information
4. **Column aliases**: Use `RETURN n as node, r as rel` for cleaner output

### Performance Considerations

- Use `LIMIT` clauses for large datasets
- Index frequently queried properties
- In LLM mode, complex queries may take longer due to AI processing time
- Direct mode provides immediate query execution

## Troubleshooting

### Common Issues

1. **"return row and column definition list do not match"**
   - This is automatically handled by smart column detection
   - If you see this error, report it as a bug

2. **Connection errors**
   - Check your `.env` file database settings
   - Ensure PostgreSQL with AGE is running
   - Verify the graph exists: `SELECT * FROM ag_graph;`

3. **LLM not responding**
   - Check your `OPENAI_API_KEY` environment variable
   - Verify internet connectivity
   - Switch to direct mode with `\llm off`

### Debug Mode

Use logging to debug issues:

```
cypher> \log on
cypher> \llm off
cypher> YOUR_PROBLEMATIC_QUERY_HERE
```

This will show you exactly what's being sent to the database.

## Examples Repository

The `examples/` directory contains sample Cypher files you can load:

```bash
python cypher_llm_repl.py examples/schema.dsl examples/data.dsl
```

These demonstrate various graph patterns and queries you can use as starting points for your own graphs.

## License and Copyright

Copyright (c) 2025, Iwan van der Kleijn

This project is licensed under the MIT License. See the [LICENSE](../LICENSE.txt) file for details.