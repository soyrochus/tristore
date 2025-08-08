CREATE (n:TestNode {msg: 'Hello, AGE!'})
  RETURN n;

MATCH (n:TestNode)
  RETURN n.msg;