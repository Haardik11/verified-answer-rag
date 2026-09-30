#!/bin/sh
set -e

# data/qdrant is a volume, so it starts empty on a fresh container even
# though the image ships the sample documents - build the index once if
# it isn't there yet, instead of requiring a manual step before the app
# is actually usable.
#
# Checking for a dedicated marker file rather than meta.json - Qdrant
# creates meta.json on the FIRST successfully-indexed document, not when
# the whole build finishes. Found this the hard way: a mid-build crash
# (see DEVLOG) left meta.json sitting there from the documents indexed
# before the crash, so a container restart saw it, assumed the index was
# complete, and launched uvicorn on a silently partial index instead of
# retrying. The marker is only created after build_index.py exits
# successfully, so a crash always triggers a full, honest retry.
if [ ! -f "data/qdrant/.build_complete" ]; then
  echo "No completed index found in data/qdrant - building it from data/*.pdf, *.txt, *.csv..."
  python scripts/build_index.py
  touch "data/qdrant/.build_complete"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
