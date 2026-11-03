from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, GObject, Gtk, Pango  # noqa: E402

from . import APP_NAME  # noqa: E402
from .backend import Menu, Row, Session, find_cli  # noqa: E402

MEDIA = [("Anime", "anime"), ("Películas", "movie"), ("Series", "series"), ("Doramas", "dorama")]
SOURCES = [("Automática", None), ("JKAnime", "jkanime"), ("AnimeAV1", "animeav1"),
           ("AniDB", "anidb"), ("AnimeX", "animex")]
QUALITY = [("Automática", None), ("1080p", "1080p"), ("720p", "720p"), ("480p", "480p")]

TITLES = {
    "results": "Resultados", "episodes": "Episodios", "player": "Reproduciendo",
    "history": "Continuar viendo", "source": "Fuente",
}
RESULT_RE = re.compile(r"^\[(?P<lang>[^\]]+)\]\s*(?P<title>.*?)\s*\[(?P<src>[^\]]+)\]\s*$")
CONFIG = Path(GLib.get_user_config_dir()) / "hasu" / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(data))
    except OSError:
        pass


class MenuPage(Adw.NavigationPage):
    """Una pantalla que muestra un menú de ani-cli-mx (o su estado de carga)."""

    def __init__(self, window: "MainWindow", kind: str):
        super().__init__(title=TITLES.get(kind, "Elegir"))
        self.window, self.kind = window, kind
        self.menu: Optional[Menu] = None

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        toolbar.set_content(self.stack)
        self.set_child(toolbar)

        # carga
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, margin_start=24, margin_end=24)
        self.spinner = Gtk.Spinner(width_request=42, height_request=42)
        self.status = Gtk.Label(label="Cargando…", wrap=True, justify=Gtk.Justification.CENTER,
                                css_classes=["dim-label"], max_width_chars=48)
        cancel = Gtk.Button(label="Cancelar", halign=Gtk.Align.CENTER, css_classes=["pill"])
        cancel.connect("clicked", lambda *_: window.cancel_session())
        for w in (self.spinner, self.status, cancel):
            box.append(w)
        self.stack.add_named(box, "loading")

        # lista
        page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.info = Gtk.Label(wrap=True, xalign=0, margin_top=12, margin_start=18, margin_end=18,
                              css_classes=["dim-label"], visible=False)
        self.search = Gtk.SearchEntry(placeholder_text="Filtrar…", margin_top=12,
                                      margin_start=18, margin_end=18, visible=False)
        self.search.connect("search-changed", lambda *_: self.listbox.invalidate_filter())
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        self.listbox.set_filter_func(self._filter)
        self.listbox.connect("row-activated", self._activated)
        clamp = Adw.Clamp(maximum_size=720, margin_top=12, margin_bottom=18,
                          margin_start=12, margin_end=12, valign=Gtk.Align.START)
        clamp.set_child(self.listbox)
        scroller = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(clamp)
        for w in (self.info, self.search, scroller):
            page_box.append(w)
        self.stack.add_named(page_box, "list")

        self.set_loading("Buscando…")

    # -- estados -------------------------------------------------------
    def set_loading(self, text: str) -> None:
        self.menu = None
        self.status.set_label(text)
        self.spinner.start()
        self.stack.set_visible_child_name("loading")
        self.set_can_pop(False)  # mientras ani-cli-mx trabaja no hay nada que cancelar con "atrás"

    def update_status(self, text: str) -> None:
        if self.stack.get_visible_child_name() == "loading":
            self.status.set_label(text)

    def set_menu(self, menu: Menu) -> None:
        self.menu = menu
        self.spinner.stop()
        while (row := self.listbox.get_first_child()) is not None:
            self.listbox.remove(row)

        rows = [r for r in menu.rows if not r.is_nav]
        self.search.set_text("")
        self.search.set_visible(len(rows) > 12)
        self.info.set_visible(self.kind == "player")
        if self.kind == "player":
            self.info.set_label(menu.prompt.rstrip(". "))

        for r in rows:
            self.listbox.append(self._make_row(r))
        self.stack.set_visible_child_name("list")
        self.set_can_pop(True)

    def _make_row(self, r: Row) -> Adw.ActionRow:
        title, subtitle = r.label, ""
        if self.kind in ("results", "history"):
            m = RESULT_RE.match(r.label)
            if m:
                title, subtitle = m["title"], f'{m["lang"].title()} · {m["src"]}'
            else:
                title = re.sub(r"\s*\[([^\]]+)\]$", "", r.label)
                m2 = re.search(r"\[([^\]]+)\]$", r.label)
                subtitle = m2.group(1) if m2 else ""
        elif self.kind == "episodes" and title.endswith(" *"):
            title, subtitle = title[:-2], "Último que viste"
        row = Adw.ActionRow(title=GLib.markup_escape_text(title),
                            subtitle=GLib.markup_escape_text(subtitle), activatable=True)
        row.row_data = r  # type: ignore[attr-defined]
        icon = "media-playback-start-symbolic" if self.kind in ("episodes", "results", "history") \
            else "go-next-symbolic"
        row.add_suffix(Gtk.Image.new_from_icon_name(icon))
        return row

    def _filter(self, row) -> bool:
        q = self.search.get_text().strip().lower()
        if not q:
            return True
        return q in (row.get_title() + " " + (row.get_subtitle() or "")).lower()

    def _activated(self, _lb, row) -> None:
        if self.menu is None:
            return
        menu, data = self.menu, row.row_data
        self.set_loading({"episodes": "Preparando el episodio…", "results": "Cargando episodios…"}
                         .get(self.kind, "Un momento…"))
        menu.answer(data)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title=APP_NAME, default_width=520, default_height=720)
        self.cli = find_cli()
        self.session: Optional[Session] = None
        self.pages: list[MenuPage] = []
        self.settings = load_settings()

        self.toasts = Adw.ToastOverlay()
        self.nav = Adw.NavigationView()
        self.nav.connect("popped", self._on_popped)
        self.toasts.set_child(self.nav)
        self.set_content(self.toasts)
        self.nav.add(self._build_home())

    # -- inicio --------------------------------------------------------
    def _build_home(self) -> Adw.NavigationPage:
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", primary=True)
        pop = Gtk.Popover()
        mbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=4, margin_bottom=4,
                       margin_start=4, margin_end=4)
        for label, action in (("Registro de ani-cli-mx", "app.log"), ("Acerca de Hasu", "app.about")):
            b = Gtk.Button(label=label, css_classes=["flat"], halign=Gtk.Align.FILL)
            b.set_action_name(action)
            b.connect("clicked", lambda *_: pop.popdown())
            mbox.append(b)
        pop.set_child(mbox)
        menu_btn.set_popover(pop)
        header.pack_end(menu_btn)
        toolbar.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=12, margin_bottom=24)
        title = Gtk.Label(label="¿Qué quieres ver hoy?", css_classes=["title-1"], margin_top=12)
        content.append(title)

        self.entry = Gtk.SearchEntry(placeholder_text="Busca un anime, película, serie o dorama")
        self.entry.connect("activate", lambda *_: self.on_search())
        self.entry.connect("search-changed", lambda *_: None)
        content.append(self.entry)

        group = Adw.PreferencesGroup()
        self.media_row = Adw.ComboRow(title="Tipo de contenido",
                                      model=Gtk.StringList.new([m[0] for m in MEDIA]))
        self.source_row = Adw.ComboRow(title="Fuente de anime",
                                       subtitle="Solo aplica a anime",
                                       model=Gtk.StringList.new([s[0] for s in SOURCES]))
        self.quality_row = Adw.ComboRow(title="Calidad", model=Gtk.StringList.new([q[0] for q in QUALITY]))
        self.dub_row = Adw.SwitchRow(title="Doblaje", subtitle="Pide la versión doblada si existe")
        self.cont_row = Adw.SwitchRow(title="Modo continuo",
                                      subtitle="Pasa al siguiente episodio en la misma ventana de mpv")
        for r in (self.media_row, self.source_row, self.quality_row, self.dub_row, self.cont_row):
            group.add(r)
        self.media_row.set_selected(self.settings.get("media", 0))
        self.source_row.set_selected(self.settings.get("source", 0))
        self.quality_row.set_selected(self.settings.get("quality", 0))
        self.dub_row.set_active(self.settings.get("dub", False))
        self.cont_row.set_active(self.settings.get("continuous", False))
        self.media_row.connect("notify::selected", self._sync_options)
        self._sync_options()
        content.append(group)

        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        search_btn = Gtk.Button(label="Buscar", css_classes=["suggested-action", "pill"])
        search_btn.connect("clicked", lambda *_: self.on_search())
        hist_btn = Gtk.Button(label="Continuar viendo", css_classes=["pill"])
        hist_btn.connect("clicked", lambda *_: self.on_history())
        buttons.append(search_btn)
        buttons.append(hist_btn)
        content.append(buttons)

        if not self.cli:
            status = Adw.StatusPage(
                icon_name="dialog-warning-symbolic", title="No encuentro ani-cli-mx",
                description="Instálalo y vuelve a abrir Hasu.\n\nArch: yay -S ani-cli-mx o paru -S ani-cli-mx")
            toolbar.set_content(status)
        else:
            clamp = Adw.Clamp(maximum_size=560, margin_start=18, margin_end=18)
            clamp.set_child(content)
            scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroller.set_child(clamp)
            toolbar.set_content(scroller)

        page = Adw.NavigationPage(title=APP_NAME, tag="home")
        page.set_child(toolbar)
        return page

    def _sync_options(self, *_) -> None:
        is_anime = MEDIA[self.media_row.get_selected()][1] == "anime"
        self.source_row.set_sensitive(is_anime)
        self.cont_row.set_sensitive(MEDIA[self.media_row.get_selected()][1] != "movie")

    # -- acciones ------------------------------------------------------
    def _common_args(self) -> list[str]:
        media = MEDIA[self.media_row.get_selected()][1]
        args = ["--type", media] if self.entry.get_text().strip() else []
        src = SOURCES[self.source_row.get_selected()][1]
        if src and media == "anime":
            args += ["--source", src]
        q = QUALITY[self.quality_row.get_selected()][1]
        if q:
            args += ["-q", q]
        if self.dub_row.get_active():
            args.append("--dub")
        if self.cont_row.get_active() and media != "movie":
            args.append("--continuous")
        self.settings = {
            "media": self.media_row.get_selected(), "source": self.source_row.get_selected(),
            "quality": self.quality_row.get_selected(), "dub": self.dub_row.get_active(),
            "continuous": self.cont_row.get_active(),
        }
        save_settings(self.settings)
        return args

    def on_search(self) -> None:
        text = self.entry.get_text().strip()
        if not text:
            self.toasts.add_toast(Adw.Toast.new("Escribe qué quieres buscar"))
            return
        words = [w.lstrip("-") for w in text.split() if w.lstrip("-")]
        self.start_session(self._common_args() + words, first_kind="results")

    def on_history(self) -> None:
        args = self._common_args()
        # el historial no usa --type/--source; se quitan para no chocar con las reglas del script
        cleaned, skip = [], False
        for a in args:
            if skip:
                skip = False
            elif a in ("--type", "--source"):
                skip = True
            else:
                cleaned.append(a)
        self.start_session(["-c", *cleaned], first_kind="history")

    # -- sesión --------------------------------------------------------
    def start_session(self, args: list[str], first_kind: str) -> None:
        if not self.cli:
            return
        self.cancel_session(silent=True)
        page = MenuPage(self, first_kind)
        self._push(page)
        self.session = Session(self.cli, args, self._on_menu, self._on_status, self._on_exit)
        try:
            self.session.start()
        except OSError as e:
            self.session = None
            self.nav.pop_to_tag("home")
            self.pages.clear()
            self.toasts.add_toast(Adw.Toast.new(f"No se pudo iniciar ani-cli-mx: {e}"))

    def cancel_session(self, silent: bool = False) -> None:
        if self.session:
            self.session.stop()
            self.session = None
        if self.pages:
            self.pages.clear()
            self.nav.pop_to_tag("home")
        if not silent:
            pass

    def _push(self, page: MenuPage) -> None:
        self.pages.append(page)
        self.nav.push(page)

    def _on_status(self, text: str) -> None:
        if self.pages:
            self.pages[-1].update_status(text)

    def _on_menu(self, menu: Menu) -> None:
        kind = menu.kind
        page = next((p for p in reversed(self.pages) if p.kind == kind), None)
        if page is None:
            page = MenuPage(self, kind)
            self._push(page)
        elif page is not self.pages[-1]:
            idx = self.pages.index(page)
            del self.pages[idx + 1:]  # se recortan antes de hacer pop para ignorar sus señales
            self.nav.pop_to_page(page)
        page.set_menu(menu)

    def _on_exit(self, code: int, tail: list[str]) -> None:
        self.session = None
        had_pages = bool(self.pages)
        self.pages.clear()
        self.nav.pop_to_tag("home")
        if code not in (0, 130) or (had_pages and tail and code != 0):
            msg = tail[-1] if tail else f"ani-cli-mx terminó con código {code}"
            self.toasts.add_toast(Adw.Toast.new(msg[:160]))

    def _on_popped(self, _nav, page) -> None:
        if page not in self.pages:
            return  # lo quitamos nosotros
        idx = self.pages.index(page)
        del self.pages[idx:]
        if idx == 0:
            # salió de la primera pantalla: se termina la sesión
            if self.session:
                self.session.stop()
                self.session = None
        elif page.menu is not None and not page.menu.answered:
            page.menu.cancel()  # "atrás" = Esc en dmenu; ani-cli-mx vuelve al menú anterior
            if self.pages:
                self.pages[-1].set_loading("Volviendo…")

    def show_log(self) -> None:
        win = Adw.Window(transient_for=self, modal=True, default_width=640, default_height=420,
                         title="Registro")
        tv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                          left_margin=12, right_margin=12, top_margin=12, bottom_margin=12)
        log = self.session.log if self.session else getattr(self, "_last_log", [])
        tv.get_buffer().set_text("\n".join(log) or "Sin mensajes todavía.")
        tb = Adw.ToolbarView()
        tb.add_top_bar(Adw.HeaderBar())
        sc = Gtk.ScrolledWindow()
        sc.set_child(tv)
        tb.set_content(sc)
        win.set_content(tb)
        win.present()
