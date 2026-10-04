#!/bin/bash

uv run python -m exercises.ticket_router.router > out-1.txt
uv run python -m exercises.ticket_router.router --no-descriptions > out-2.txt
uv run python -m exercises.ticket_router.router --threshold 0.8 > out-3.txt