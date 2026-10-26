#!/bin/sh
# Copy upstream indic2unicode into src/unipdf/i2u with the import rewrite only
# (REQUIREMENTS D-16), from its working tree, or from a commit if one is
# given. The counterpart of tools/check_upstream.sh; update i2u/UPSTREAM after.
# Usage: tools/sync_upstream.sh [commit] [upstream-repo]
set -e
HERE=$(cd "$(dirname "$0")/.." && pwd)
COMMIT=${1:-}
UPSTREAM=${2:-$HERE/../indic2unicode}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if [ -n "$COMMIT" ]; then
  git -C "$UPSTREAM" archive "$COMMIT" | tar -x -C "$TMP"
else
  (cd "$UPSTREAM" && git ls-files -z | xargs -0 tar -cf - ) | tar -x -C "$TMP"
fi
I2U=$HERE/src/unipdf/i2u
for d in fonts langs; do rm -rf "${I2U:?}/$d"; cp -R "$TMP/$d" "$I2U/$d"; done
cp "$TMP/fontconv.py" "$TMP/__init__.py" "$TMP/LICENSE" "$TMP/COPYING" "$TMP/README" \
   "$TMP/BUGS" "$I2U/"
cp "$TMP/tools/fix_tounicode.py" "$I2U/fix_tounicode.py"
find "$I2U" -name '*.py' -not -path '*/__pycache__/*' -exec sed -i.bak -E \
  -e 's/^([[:space:]]*(from|import) )indic2unicode\.tools\.fix_tounicode/\1unipdf.i2u.fix_tounicode/' \
  -e 's/^([[:space:]]*(from|import) )indic2unicode\./\1unipdf.i2u./' {} \;
find "$I2U" -name '*.bak' -delete
rm -rf "$HERE/tests/i2u/testdata" "$HERE/tests/i2u/expected"
cp -R "$TMP/testdata" "$HERE/tests/i2u/testdata"
cp -R "$TMP/expected" "$HERE/tests/i2u/expected"
echo "src/unipdf/i2u synced from $UPSTREAM ${COMMIT:-(working tree)}"
