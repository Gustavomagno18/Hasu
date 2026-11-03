#!/bin/sh
# Desinstala Hasu para tu usuario: elimina ejecutable, archivos, icono y entrada del menú.
set -e

prefix="${PREFIX:-$HOME/.local}"

echo "Desinstalando Hasu de $prefix..."

# 1. Eliminar el ejecutable del sistema
rm -f "$prefix/bin/hasu"

# 2. Eliminar la carpeta de datos de la aplicación
rm -rf "$prefix/share/hasu"

# 3. Eliminar el lanzador (.desktop)
rm -f "$prefix/share/applications/io.github.Gustavomagno18.Hasu.desktop"

# 4. Eliminar el icono
rm -f "$prefix/share/icons/hicolor/scalable/apps/io.github.Gustavomagno18.Hasu.svg"

# 5. Actualizar la base de datos de aplicaciones de escritorio
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$prefix/share/applications" || true
fi

# 6. Actualizar la caché de iconos si está disponible
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$prefix/share/icons/hicolor" || true
fi

echo "Hasu ha sido desinstalado correctamente."
