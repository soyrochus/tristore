import os
import argparse
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from dotenv import load_dotenv
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

INIT_STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS age;",
    "LOAD 'age';",
    "SET search_path = ag_catalog, \"$user\", public;",
    f"SELECT create_graph('{GRAPH_NAME}');"
]

def print_result(rows):
    if not rows:
        print("(no results)")
        return
    keys = rows[0].keys()
    print("\t".join(str(k) for k in keys))
    for row in rows:
        print("\t".join(str(row[k]) for k in keys))

def execute_cypher(cur, conn, query):
    """Execute a Cypher query and return success status"""
    try:
        sql = f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {query} $$) AS {DEFAULT_COLS};"
        cur.execute(sql)
        rows = cur.fetchall()
        print_result(rows)
        conn.commit()  # Commit the transaction
        return True
    except Exception as e:
        # Show only the Cypher error (not the SQL)
        msg = str(e)
        msg_clean = msg.split('\n')[0]
        print("Cypher error:", msg_clean)
        conn.rollback()
        return False

def load_and_execute_files(cur, conn, files):
    """Load and execute Cypher statements from files"""
    for file_path in files:
        print(f"\n--- Executing file: {file_path} ---")
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Split on semicolons and execute each statement
            statements = [stmt.strip() for stmt in content.split(';') if stmt.strip()]
            
            for i, stmt in enumerate(statements, 1):
                print(f"\nStatement {i}:")
                print(f"cypher> {stmt}")
                execute_cypher(cur, conn, stmt)
                
        except FileNotFoundError:
            print(f"Error: File '{file_path}' not found")
        except Exception as e:
            print(f"Error reading file '{file_path}': {e}")

def main():
    parser = argparse.ArgumentParser(description='Cypher REPL for AGE/PostgreSQL')
    parser.add_argument('files', nargs='*', help='Cypher files to load and execute')
    parser.add_argument('-e', '--execute', action='store_true', 
                       help='Execute files and exit (do not start REPL)')
    
    args = parser.parse_args()
    
    print(f"Cypher REPL for AGE/PostgreSQL - graph: {GRAPH_NAME}")
    
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Initialization block
    for stmt in INIT_STATEMENTS:
        try:
            cur.execute(stmt)
            conn.commit()
        except Exception:
            conn.rollback()

    try:
        # Execute files if provided
        if args.files:
            load_and_execute_files(cur, conn, args.files)
        
        # Exit if --execute flag is set
        if args.execute:
            print("\nExecution complete.")
            return
        
        # Start REPL (either after file execution or if no files provided)
        if not args.files:
            print("Enter adds a new line. Esc+Enter executes your Cypher query.")
        print("Type \\q to quit. End queries with a semicolon (;).\n")

        session = PromptSession(
            history=FileHistory(HISTORY_FILE),
            multiline=True,
        )

        while True:
            try:
                text = session.prompt("cypher> ")
                if text.strip() == "\\q":
                    break
                if not text.strip():
                    continue
                # Remove trailing semicolon if present
                query = text.strip().rstrip(";")
                execute_cypher(cur, conn, query)
            except KeyboardInterrupt:
                print("\n(Use Ctrl+D or \\q to quit.)")
            except EOFError:
                print("\nExiting REPL.")
                break
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
