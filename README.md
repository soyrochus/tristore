#  Step-by-step setup for a PostgreSQL “TriStore” for Reagent

## Introduction

Below is a hands-on, step-by-step setup for a PostgreSQL “TriStore” (Structured \+ Graph \+ Vector) in a single Docker container, including:

* PostgreSQL 16  
* pgvector (vector search, open source)  
* Apache AGE (property graph with openCypher, open source)

This is a fully open-source, self-contained approach.

## 1\. **Create a Dockerfile**

This Dockerfile builds on the official Postgres image, installs `pgvector`, and compiles Apache AGE from source. It also enables both extensions by default.

\# syntax=docker/dockerfile:1

FROM postgres:16

\# Install build dependencies and git

RUN apt-get update \\

    && apt-get install \-y \--no-install-recommends \\

        build-essential \\

        git \\

        postgresql-server-dev-16 \\

        ca-certificates \\

        libreadline-dev \\

        zlib1g-dev \\

        flex \\

        bison \\

    && rm \-rf /var/lib/apt/lists/\*

\# Install pgvector

RUN git clone \--branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector \\

    && cd /tmp/pgvector \\

    && make && make install \\

    && cd / && rm \-rf /tmp/pgvector

\# Install Apache AGE (latest stable)

RUN git clone \--branch PG16 https://github.com/apache/age.git /tmp/age \\

    && cd /tmp/age \\

    && make PG\_CONFIG=/usr/lib/postgresql/16/bin/pg\_config && make install PG\_CONFIG=/usr/lib/postgresql/16/bin/pg\_config \\

    && cd / && rm \-rf /tmp/age

\# Enable extensions on init

COPY init-tristore.sql /docker-entrypoint-initdb.d/

## 2\. **Create the initialization SQL**

This file (`init-tristore.sql`) will be run automatically on the first launch.

\-- Enable pgvector in all new databases   
CREATE EXTENSION IF NOT EXISTS vector;

\-- Enable Apache AGE and create a sample graph (graph name: my\_graph)   
CREATE EXTENSION IF NOT EXISTS age;  
 LOAD 'age';

\-- Set search path so AGE functions are available   
SET search\_path \= ag\_catalog, "$user", public;

\-- Now create the AGE catalog and graph   
SELECT \* FROM create\_graph('my\_graph');

\-- You can add any default tables or test data here if you wish

## 3\. **Build and Run the Container**

Assuming your `Dockerfile` and `init-tristore.sql` are in the same directory:

docker build \-t tristore-pg:latest .

docker run \-d \--name tristore \-e POSTGRES\_PASSWORD=secret \-p 5432:5432 tristore-pg:latest

* The database will listen on **localhost:5432**  
* Username: `postgres`  
* Password: `secret`  
* DB name: `postgres` (default)

## 4\. **Test the Database**

Connect (psql, DBeaver, Python, LangChain, etc.):

psql \-h localhost \-U postgres

\# Then, inside psql:

\\dx

\-- Should show vector and age extensions enabled

Expected output something like

                             List of installed extensions  
  Name   | Version |   Schema   |                     Description  
\---------+---------+------------+------------------------------------------------------  
 age     | 1.5.0   | ag\_catalog | AGE database extension  
 plpgsql | 1.0     | pg\_catalog | PL/pgSQL procedural language  
 vector  | 0.8.0   | public     | vector data type and ivfflat and hnsw access methods  
(3 rows)

Test the Age 

\-- Create a node  
SELECT \* FROM cypher('test\_graph', $$  
  CREATE (n:Person {name: 'Alice', age: 30})  
  RETURN n  
$$) AS (node agtype);

\-- Query nodes  
SELECT \* FROM cypher('test\_graph', $$  
  MATCH (n:Person) RETURN n.name, n.age  
$$) AS (name agtype, age agtype);

**Create a sample table with vector column:**

CREATE TABLE embeddings (

  id serial PRIMARY KEY,

  content TEXT,

  embedding vector(1536) \-- for OpenAI ada-002, adjust as needed

);

\-- Insert a dummy row:

INSERT INTO embeddings (content, embedding)

VALUES ('Hello world', '\[0.1, 0.2, ... up to 1536 ...\]');

\-- Search by similarity:

SELECT \* FROM embeddings ORDER BY embedding \<-\> '\[0.1, 0.2, ...\]' LIMIT 1;

**Test graph functionality:**

SELECT \* FROM cypher('my\_graph', $$

  CREATE (p:Person {name: 'Alice'})-\[:KNOWS\]-\>(q:Person {name: 'Bob'})

$$) as (result agtype);

SELECT \* FROM cypher('my\_graph', $$

  MATCH (p:Person)-\[:KNOWS\]-\>(q:Person) RETURN p, q

$$) as (p agtype, q agtype);

## 5\. **Python Driver Example**

* Use **psycopg2** (or **asyncpg**) for SQL/vector  
* Cypher queries via `SELECT * FROM cypher('my_graph', ...)`

import psycopg2

conn \= psycopg2.connect(

    dbname="postgres",

    user="postgres",

    password="secret",

    host="localhost",

    port=5432,

)

cur \= conn.cursor()

\# Vector search example

cur.execute(

    "SELECT content FROM embeddings ORDER BY embedding \<-\> %s LIMIT 1",

    (\[0.1, 0.2, ...\],)

)

print(cur.fetchone())

\# Cypher query example

cypher \= "MATCH (p:Person)-\[:KNOWS\]-\>(q:Person) RETURN p, q"

cur.execute(

    "SELECT \* FROM cypher('my\_graph', %s) as (p agtype, q agtype);",

    (cypher,)

)

print(cur.fetchall())

6\. **Extensions & Notes**

* You can script more graph/table/vector setup as needed.  
* All components are **fully open-source**.  
* To persist data, add a volume to the container.  
* For production, tweak `postgresql.conf` (memory, WAL, etc.).


## License and Copyright

Copyright (c) 2025, Iwan van der Kleijn

This project is licensed under the MIT License. See the [LICENSE](../LICENSE.txt) file for details.