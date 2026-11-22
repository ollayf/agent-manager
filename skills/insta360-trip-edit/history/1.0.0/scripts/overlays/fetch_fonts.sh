#!/bin/zsh
# fetch_fonts.sh RENDER_DIR — download the default theme's fonts (Google Fonts, OFL) into RENDER_DIR/fonts.
# Swapping the theme? Put that theme's font files in RENDER_DIR/fonts yourself; names must match theme.json.
set -e; F="$1/fonts"; mkdir -p "$F"; G=https://github.com/google/fonts/raw/main/ofl
[ -f "$F/ArchivoBlack-Regular.ttf" ] || curl -sfL -o "$F/ArchivoBlack-Regular.ttf" $G/archivoblack/ArchivoBlack-Regular.ttf
[ -f "$F/SpaceMono-Bold.ttf" ]       || curl -sfL -o "$F/SpaceMono-Bold.ttf" $G/spacemono/SpaceMono-Bold.ttf
[ -f "$F/SpaceMono-Regular.ttf" ]    || curl -sfL -o "$F/SpaceMono-Regular.ttf" $G/spacemono/SpaceMono-Regular.ttf
[ -f "$F/NotoSansJP.ttf" ]           || curl -sfL -o "$F/NotoSansJP.ttf" "$G/notosansjp/NotoSansJP%5Bwght%5D.ttf"
ls "$F"
