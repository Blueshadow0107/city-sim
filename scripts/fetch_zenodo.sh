#!/usr/bin/env bash
# Resumable Zenodo download: fetch_zenodo.sh <record> <file> <dest-dir>
set -euo pipefail
rec=$1; f=$2; dest=$3
size=$(curl -sL "https://zenodo.org/api/records/$rec" | python3 -c "import sys,json;print(next(x['size'] for x in json.load(sys.stdin)['files'] if x['key']=='$f'))")
until [ "$(stat -c %s "$dest/$f" 2>/dev/null || echo 0)" -ge "$size" ]; do
  curl -sL -m 300 -C - -o "$dest/$f" "https://zenodo.org/api/records/$rec/files/$f/content" || true
done
echo "done $f $size"
