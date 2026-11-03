#!/bin/sh
# Instala Hasu para tu usuario (sin root): ~/.local/share/hasu + lanzador + icono + menú de apps.
set -e
cd "$(dirname "$0")"
prefix="${PREFIX:-$HOME/.local}"
install -d "$prefix/share/hasu" "$prefix/bin"
rm -rf "$prefix/share/hasu/hasu"
cp -r hasu "$prefix/share/hasu/"
install -Dm755 bin/hasu "$prefix/bin/hasu"
install -Dm644 data/io.github.Gustavomagno18.Hasu.desktop -t "$prefix/share/applications"
install -Dm644 data/io.github.Gustavomagno18.Hasu.svg -t "$prefix/share/icons/hicolor/scalable/apps"
command -v update-desktop-database >/dev/null && update-desktop-database "$prefix/share/applications" || true
echo "Listo. Ejecuta: hasu   (asegúrate de tener $prefix/bin en tu PATH)"
