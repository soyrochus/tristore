# syntax=docker/dockerfile:1

FROM postgres:16

# Install build dependencies and git
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        postgresql-server-dev-16 \
        ca-certificates \
        libreadline-dev \
        zlib1g-dev \
        flex \
        bison \
    && rm -rf /var/lib/apt/lists/*

# Install pgvector
RUN git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make && make install \
    && cd / && rm -rf /tmp/pgvector

# Install Apache AGE (latest stable)
RUN git clone --branch v1.5.0 https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age \
    && make PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config && make install PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config \
    && cd / && rm -rf /tmp/age

# Enable extensions on init
COPY init-tristore.sql /docker-entrypoint-initdb.d/

