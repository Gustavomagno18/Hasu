"""Prueba de humo de la interfaz: arranca la app con un ani-cli-mx simulado y toma capturas."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HASU_CLI"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock-ani-cli-mx")
os.environ["XDG_CONFIG_HOME"] = "/tmp/hasu-cfg"

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Graphene, Gdk  # noqa: E402

from hasu.app import App  # noqa: E402

OUT = "/tmp/shots"
os.makedirs(OUT, exist_ok=True)
log = []


def shot(win, name):
    paintable = Gtk.WidgetPaintable.new(win)
    w, h = win.get_width(), win.get_height()
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, w, h)
    node = snap.to_node()
    tex = win.get_native().get_renderer().render_texture(node, Graphene.Rect().init(0, 0, w, h))
    tex.save_to_png(f"{OUT}/{name}.png")


def top(win):
    return win.pages[-1] if win.pages else None


class _R:
    def __init__(self, page, row):
        self.page, self.row = page, row

    def activate(self):
        self.page.listbox.emit("row-activated", self.row)


def first_row(page, n=0):
    return _R(page, page.listbox.get_row_at_index(n))


steps = []


def step(delay, fn):
    steps.append((delay, fn))


def run_steps(win):
    t = 0
    for delay, fn in steps:
        t += delay
        GLib.timeout_add(t, lambda f=fn: (f(win), False)[1])


def main():
    app = App()

    def on_activate(app):
        win = app.props.active_window
        win.set_default_size(520, 720)
        win.entry.set_text("naruto")

        step(600, lambda w: shot(w, "1_home"))
        step(200, lambda w: w.on_search())
        step(150, lambda w: shot(w, "2_loading"))
        step(1200, lambda w: (log.append(("results kind", top(w).kind, top(w).listbox.get_row_at_index(2) is not None)), shot(w, "3_results")))
        step(100, lambda w: first_row(top(w), 0).activate())
        step(1500, lambda w: (log.append(("after pick", top(w).kind)), shot(w, "4_episodes")))
        step(100, lambda w: first_row(top(w), 2).activate())
        step(1500, lambda w: (log.append(("after ep", top(w).kind)), shot(w, "5_player")))
        # siguiente episodio -> el menú del reproductor vuelve a salir (misma página, se refresca)
        step(100, lambda w: first_row(top(w), 0).activate())
        step(1500, lambda w: (log.append(("after next", top(w).kind, top(w).info.get_label())), shot(w, "6_player_next")))
        # "atrás" desde el reproductor => Esc => vuelve a episodios
        step(100, lambda w: w.nav.pop())
        step(1500, lambda w: (log.append(("after back", top(w).kind, len(w.pages))), shot(w, "7_back_to_eps")))
        step(100, lambda w: w.nav.pop())
        step(1500, lambda w: (log.append(("after back2", top(w).kind, len(w.pages))),))
        step(100, lambda w: w.nav.pop())
        step(800, lambda w: (log.append(("after back3", len(w.pages), w.session is None, w.nav.get_visible_page().get_tag())), shot(w, "8_home_again")))
        step(200, lambda w: app.quit())

        run_steps(win)

    app.connect_after("activate", on_activate)
    app.run([])
    for l in log:
        print(l)


main()
