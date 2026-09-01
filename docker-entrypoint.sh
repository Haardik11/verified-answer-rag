#!/bin/sh
set -e

# data/qdrant is a volume, so it starts empty on a fresh container even
# though the image ships the sample documents - build the index once if
# it isn't there yet, instead of requiring a manual step before the app
# is actually usable.
if [ ! -f "data/qdrant/meta.json" ]; then
  echo "No existing index found in data/qdrant - building it from data/*.pdf, *.txt, *.csv..."
  python scripts/build_index.py
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
