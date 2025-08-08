-- Enable pgvector in all new databases
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable Apache AGE and create a sample graph (graph name: my_graph)
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';

-- Set search path so AGE functions are available
SET search_path = ag_catalog, "$user", public;

-- Now create the AGE catalog and graph
SELECT * FROM create_graph('my_graph');
