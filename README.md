# Hasu

Interfaz gráfica (GTK4 + libadwaita) para [ani-cli-mx](https://github.com/Gildedboy/ani-cli-mx).
Busca anime, películas, series y doramas, elige episodio y lo reproduce con mpv.

## Cómo funciona

No reescribe ningún scraper. Ejecuta `ani-cli-mx --dmenu` y pone delante en el `PATH` un `dmenu`
falso (`animx/dmenu_shim.py`). Cada menú que el script mostraría (resultados, episodios, fuente,
controles de reproducción…) llega a AniMX por un socket Unix; tu elección vuelve al script como si
fuera dmenu. Así las fuentes nuevas o arregladas en ani-cli-mx funcionan en AniMX sin tocar nada.

## Requisitos (Arch)

    sudo pacman -S python-gobject gtk4 libadwaita
    yay -S ani-cli-mx        # trae mpv, curl, fzf, yt-dlp…

## Probar sin instalar

    python -m animx

## Instalar para tu usuario

    ./install-local.sh

## Flatpak (borrador sin probar)

`io.github.Gustavomagno18.Hasu.yaml` empaqueta la interfaz y ani-cli-mx. Faltan dos cosas:

1. **mpv dentro del sandbox**: hay que añadir un módulo de mpv (copiando el de `io.mpv.Mpv` en
   Flathub) o permitir lanzar el reproductor del sistema. Es la parte más pesada.
2. **yt-dlp** (bloque comentado en el manifiesto).

## Pruebas

`tests/mock-ani-cli-mx` imita los menús del script real y `tests/ui_test.py` recorre la interfaz
(búsqueda → episodios → reproductor → atrás) con capturas:

    GSK_RENDERER=cairo xvfb-run -a python3 tests/ui_test.py

## Aviso

Hasu no aloja ni distribuye contenido. Respeta las leyes de derechos de autor de tu país.
Licencia: GPL-3.0-or-later (como ani-cli-mx).
