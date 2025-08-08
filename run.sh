#!/bin/bash
    
podman run -d \
    --name tristore \
    -e POSTGRES_PASSWORD=secret \
    -p 5432:5432  \
    -v db:/var/lib/postgresql/data \
    -d localhost/tristore-pg
