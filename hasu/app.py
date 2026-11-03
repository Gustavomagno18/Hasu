import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gdk, GdkPixbuf  # noqa: E402

from . import APP_ID, APP_NAME, VERSION  # noqa: E402
from .window import MainWindow  # noqa: E402


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        for name, cb in (("log", self._log), ("about", self._about), ("quit", lambda *_: self.quit())):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def do_activate(self):
        win = self.props.active_window or MainWindow(self)
        win.present()

    def do_shutdown(self):
        win = self.props.active_window
        if win and getattr(win, "session", None):
            win.session.stop()
        Adw.Application.do_shutdown(self)

    def _log(self, *_):
        self.props.active_window.show_log()

    def _about(self, *_):
        cls = getattr(Adw, "AboutDialog", None) or Adw.AboutWindow
        about = cls(
            application_name=APP_NAME,
            application_icon="io.github.Gustavomagno18.Hasu",
            version=VERSION,
            developer_name="Gustavo Gilabert",
            license_type=__import__("gi.repository.Gtk", fromlist=["x"]).License.GPL_3_0,
            comments="Interfaz gráfica para ani-cli-mx hecha con GTK4 y libadwaita.",
            website="https://github.com/Gustavomagno18/Hasu"
        )

        if cls is Adw.AboutDialog:
            about.present(self.props.active_window)
        else:
            about.set_transient_for(self.props.active_window)
            about.present()


def main():
    return App().run(sys.argv)
