CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT create_graph('demo');



-- Create a test node
SELECT * FROM cypher('demo', $$
  CREATE (n:TestNode {msg: 'Hello, AGE!'})
  RETURN n
$$) AS (n agtype);

-- Query all nodes of label TestNode
SELECT * FROM cypher('demo', $$
  MATCH (n:TestNode)
  RETURN n.msg
$$) AS (msg agtype);
