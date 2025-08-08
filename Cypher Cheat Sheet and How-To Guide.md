# Cypher Cheat Sheet & How-To Guide

## Introduction

Cypher is a powerful and intuitive query language used primarily with Neo4j and Apache AGE to interact with graph databases. This guide provides a clear and detailed overview, structured by practical topics to facilitate learning and reference.

## 1. Graph Database Basics

* **Nodes** represent entities and are denoted by parentheses: `(n)`
* **Labels** categorize nodes: `(person:Person)`
* **Relationships** represent connections and have directions: `(a)-[:KNOWS]->(b)`
* **Properties** store data as key-value pairs: `{name: "Alice", age: 30}`

## 2. Creating Nodes and Relationships

**Creating nodes:**

```cypher
CREATE (p:Person {name: "Alice", age: 30})
```

**Creating relationships:**

```cypher
CREATE (:Person {name:"Bob"})-[:FRIENDS_WITH]->(:Person {name:"Carol"})
```

**Multiple creations:**

```cypher
CREATE (a:City {name:"Paris"}), (b:City {name:"Berlin"})
```

## 3. Querying the Database

Basic syntax:

```cypher
MATCH (p:Person)
RETURN p.name, p.age
ORDER BY p.age DESC
LIMIT 10
```

Filtering results:

```cypher
MATCH (p:Person)
WHERE p.age > 18 AND p.name STARTS WITH 'A'
RETURN p
```

## 4. Advanced Pattern Queries

**Variable-length paths:**

```cypher
MATCH path = (a)-[:KNOWS*1..3]->(b)
RETURN path
```

**Shortest paths:**

```cypher
MATCH (a:Person {name:'Alice'}), (b:Person {name:'Bob'})
MATCH path = shortestPath((a)-[*]-(b))
RETURN path
```

## 5. Aggregations and Grouping

Example:

```cypher
MATCH (p:Person)-[:LIVES_IN]->(c:City)
RETURN c.name, count(p) AS residents
ORDER BY residents DESC
```

## 6. Updating Data

**Setting properties and labels:**

```cypher
MATCH (p:Person {name:'Alice'})
SET p.age = 31, p:Employee
```

**Removing properties and labels:**

```cypher
MATCH (p:Person {name:'Alice'})
REMOVE p.age, p:Employee
```

## 7. MERGE: Create or Match

Ensures node existence:

```cypher
MERGE (c:City {name:'Valencia'})
ON CREATE SET c.createdAt = date()
ON MATCH SET c.lastSeen = date()
```

## 8. Deleting Nodes and Relationships

**Deleting relationships:**

```cypher
MATCH (:Person {name:'Bob'})-[r:FRIENDS_WITH]-()
DELETE r
```

**Deleting nodes with relationships:**

```cypher
MATCH (c:City {name:'Berlin'})
DETACH DELETE c
```

## 9. Subqueries and Intermediate Results

Using `WITH`:

```cypher
MATCH (p:Person)-[:LIVES_IN]->(c)
WITH c, count(p) AS population
WHERE population > 100
RETURN c, population
```

## 10. Lists and UNWIND

Expanding lists:

```cypher
UNWIND ['Alice', 'Bob', 'Carol'] AS name
MERGE (:Person {name:name})
```

## 11. Indexes and Constraints

Creating indexes:

```cypher
CREATE INDEX FOR (p:Person) ON (p.name)
```

Uniqueness constraints:

```cypher
CREATE CONSTRAINT FOR (p:Person) REQUIRE p.id IS UNIQUE
```

## 12. Procedures and Functions (Neo4j)

Calling procedures:

```cypher
CALL db.labels()
CALL apoc.meta.schema()
```

## 13. Parameterized Queries

Using parameters:

```cypher
:param minAge => 18
MATCH (p:Person) WHERE p.age >= $minAge RETURN p
```

## 14. Performance Tuning

Analyzing queries:

```cypher
PROFILE MATCH (p:Person)-[:FRIENDS_WITH]->(f) RETURN f
```

## 15. Common Pitfalls

* Ensure matching column definitions in Apache AGE.
* Avoid accidental Cartesian products.
* Specify upper bounds for path lengths to optimize performance.

## 16. Useful Snippets

**Finding isolated nodes:**

```cypher
MATCH (n) WHERE NOT (n)--() RETURN n
```

**Most connected nodes:**

```cypher
MATCH (n)--()
RETURN n, size((n)--()) AS connections
ORDER BY connections DESC LIMIT 5
```

## 17. Recommended Practices

* Clearly define node and relationship patterns.
* Use descriptive aliases in RETURN statements.
* Regularly profile queries to identify bottlenecks.
* Always test queries individually before integrating into applications.

## Further Reading

* [Neo4j Cypher Reference](https://neo4j.com/docs/cypher-manual/current/)
* [Apache AGE Documentation](https://age.apache.org/)
