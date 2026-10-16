#!/bin/sh
# Check that src/unipdf/i2u differs from upstream indic2unicode only by the
# import rewrite (REQUIREMENTS D-16). Usage: tools/check_upstream.sh [upstream-repo]
set -e
HERE=$(cd "$(dirname "$0")/.." && pwd)
UPSTREAM=${1:-$HERE/../indic2unicode}
COMMIT=$(sed -n 's/.*commit \([0-9a-f]\{7,\}\).*/\1/p' "$HERE/src/unipdf/i2u/UPSTREAM" | head -1)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git -C "$UPSTREAM" archive "$COMMIT" | tar -x -C "$TMP"
mkdir "$TMP/want"
cp -R "$TMP/fonts" "$TMP/langs" "$TMP/fontconv.py" "$TMP/__init__.py" \
      "$TMP/LICENSE" "$TMP/COPYING" "$TMP/README" "$TMP/BUGS" "$TMP/want/"
cp "$TMP/tools/fix_tounicode.py" "$TMP/want/fix_tounicode.py"
find "$TMP/want" -name '*.py' -exec sed -i.bak -E \
  -e 's/^([[:space:]]*(from|import) )indic2unicode\.tools\.fix_tounicode/\1unipdf.i2u.fix_tounicode/' \
  -e 's/^([[:space:]]*(from|import) )indic2unicode\./\1unipdf.i2u./' {} \;
find "$TMP/want" -name '*.bak' -delete
diff -r -x __pycache__ -x UPSTREAM "$TMP/want" "$HERE/src/unipdf/i2u"
diff -r "$TMP/testdata" "$HERE/tests/i2u/testdata"
diff -r "$TMP/expected" "$HERE/tests/i2u/expected"
echo "i2u matches upstream $COMMIT (imports rewritten only)"
