#!/usr/bin/env bash
set -euo pipefail

DEST="${1:-$(pwd)/rt/patch-6.1.99-rt36.patch}"
URL="https://www.kernel.org/pub/linux/kernel/projects/rt/6.1/older/patch-6.1.99-rt36.patch.xz"
TMP="${DEST}.xz"

mkdir -p "$(dirname "$DEST")"
echo "Downloading $URL"
curl -fL "$URL" -o "$TMP"
xz -dc "$TMP" > "$DEST"
rm -f "$TMP"
echo "Saved: $DEST"
