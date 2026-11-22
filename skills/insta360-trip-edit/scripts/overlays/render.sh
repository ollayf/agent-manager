#!/bin/zsh
# render.sh RENDER_DIR [ID…] — render compositions to transparent ProRes 4444 MOVs in RENDER_DIR/out.
# Skips ids already rendered (delete out/<id>.mov to force). 3 at a time. Prints FAIL/MISSING lines.
# Run in the background for a full set (~45 overlays ≈ 10 min on an M1).
# Do NOT use xargs here: "command line cannot be assembled" silently dropped a third of a batch once.
cd "$1" || exit 1; shift; mkdir -p out
[ $# -gt 0 ] && printf "%s\n" "$@" > .todo || cp ids.txt .todo
run(){ [ -f out/$1.mov ] || npx -y hyperframes@0.9.7 render --composition $1.html --format mov --output out/$1.mov --quiet >/dev/null 2>&1 || echo "FAIL $1"; }
n=0; while read id; do [ -z "$id" ] && continue; run $id & n=$((n+1)); [ $((n%3)) -eq 0 ] && wait; done < .todo; wait
echo RENDER_DONE; while read id; do [ -n "$id" ] && [ ! -f out/$id.mov ] && echo "MISSING $id"; done < .todo; true
