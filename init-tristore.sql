-- Enable pgvector in all new databases
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable Apache AGE and create a sample graph (graph name: my_graph)
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';

-- Example: create the AGE catalog (safe if re-run)
SELECT * FROM create_graph('my_graph');

-- You can add any default tables or test data here if you wish

