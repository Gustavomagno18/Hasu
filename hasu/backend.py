"""Conexión con ani-cli-mx.

Idea: ani-cli-mx ya sabe buscar, listar episodios y resolver el stream. Lo
ejecutamos con --dmenu y ponemos delante en el PATH un `dmenu` falso
(dmenu_shim.py). Cada menú que ani-cli-mx quiere mostrar llega a la interfaz;
la respuesta de la persona vuelve al script como si fuera dmenu.
No se reescribe ningún scraper.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from gi.repository import GLib

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\(B|\r")
SHIM = Path(__file__).with_name("dmenu_shim.py")

# Filas de navegación de ani-cli-mx que la interfaz resuelve con sus propios botones.
NAV_LABELS = {
    "buscar de nuevo", "volver al inicio", "salir", "volver a resultados",
    "volver a continuar viendo", "buscar contenido", "buscar otro anime",
}


def find_cli() -> Optional[str]:
    return os.environ.get("HASU_CLI") or shutil.which("ani-cli-mx")


def clean(text: str) -> str:
    return ANSI_RE.sub("", text).strip()


@dataclass
class Row:
    index: str
    label: str
    raw: str  # línea completa, tal cual la espera ani-cli-mx

    @property
    def is_nav(self) -> bool:
        return self.label.strip().lower() in NAV_LABELS


class Menu:
    """Un menú pendiente de ani-cli-mx. Se responde una sola vez."""

    def __init__(self, prompt: str, lines: list[str], responder: Callable[[Optional[str]], None]):
        self.prompt = prompt.strip()
        self.rows = []
        for ln in lines:
            idx, _, label = ln.partition(" ")
            self.rows.append(Row(idx, label.strip() or idx, ln))
        self._responder = responder
        self.answered = False

    @property
    def kind(self) -> str:
        p = self.prompt.lower()
        if p.startswith("selecciona episodio"):
            return "episodes"
        if p.startswith("reproduciendo"):
            return "player"
        if p.startswith("continuar viendo"):
            return "history"
        if p.startswith("selecciona fuente"):
            return "source"
        if p.startswith("selecciona"):
            return "results"
        return "generic:" + p

    def answer(self, row: Row) -> None:
        self._send(row.raw)

    def cancel(self) -> None:
        self._send(None)

    def _send(self, choice: Optional[str]) -> None:
        if self.answered:
            return
        self.answered = True
        self._responder(choice)


class Session:
    """Una ejecución de ani-cli-mx y su canal de menús."""

    def __init__(self, cli: str, args: list[str],
                 on_menu: Callable[[Menu], None],
                 on_status: Callable[[str], None],
                 on_exit: Callable[[int, list[str]], None]):
        self.cli, self.args = cli, args
        self.on_menu, self.on_status, self.on_exit = on_menu, on_status, on_exit
        self.log: list[str] = []
        self.proc: Optional[subprocess.Popen] = None
        self._tmp: Optional[str] = None
        self._srv: Optional[socket.socket] = None
        self._closed = False
        self._pending: list[Menu] = []
        self._dmenu_path = ""

    # -- ciclo de vida -------------------------------------------------
    def start(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="hasu-")
        bindir = Path(self._tmp, "bin")
        bindir.mkdir()
        dmenu = bindir / "dmenu"
        dmenu.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{SHIM}" "$@"\n')
        dmenu.chmod(0o755)
        self._dmenu_path = str(dmenu)
        if shutil.which("fzf") is None:
            # ani-cli-mx exige fzf al arrancar aunque con --dmenu nunca lo usa
            fzf = bindir / "fzf"
            fzf.write_text("#!/bin/sh\nexit 1\n")
            fzf.chmod(0o755)

        sock_path = os.path.join(self._tmp, "menu.sock")
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(sock_path)
        self._srv.listen(4)
        threading.Thread(target=self._accept_loop, daemon=True).start()

        env = os.environ.copy()
        env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
        env["HASU_SOCK"] = sock_path
        env.setdefault("TERM", "xterm")
        self.proc = subprocess.Popen(
            [self.cli, "--dmenu", *self.args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True, errors="replace", bufsize=1,
        )
        readers = [threading.Thread(target=self._read, args=(s,), daemon=True)
                   for s in (self.proc.stdout, self.proc.stderr)]
        for t in readers:
            t.start()
        threading.Thread(target=self._wait, args=(readers,), daemon=True).start()

    def stop(self) -> None:
        """Termina ani-cli-mx (su trap limpia y cierra el reproductor rastreado)."""
        if self._closed:
            return
        self._closed = True
        for m in list(self._pending):
            m.cancel()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.send_signal(signal.SIGTERM)
            except OSError:
                pass
        self._teardown()

    def _teardown(self) -> None:
        if self._srv:
            try:
                self._srv.close()
            except OSError:
                pass
            self._srv = None
        if self._tmp:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    # -- hilos ---------------------------------------------------------
    def _accept_loop(self) -> None:
        while True:
            try:
                conn, _ = self._srv.accept()  # type: ignore[union-attr]
            except (OSError, AttributeError):
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        f = conn.makefile("rwb")
        try:
            req = json.loads(f.readline().decode() or "{}")
        except ValueError:
            f.close(); conn.close()
            return

        def responder(choice: Optional[str]) -> None:
            try:
                f.write(json.dumps({"choice": choice}).encode() + b"\n")
                f.flush()
            except OSError:
                pass
            finally:
                try:
                    f.close(); conn.close()
                except OSError:
                    pass

        menu = Menu(req.get("prompt", ""), req.get("lines", []), responder)
        if self._closed:
            menu.cancel()
            return
        self._pending.append(menu)

        def deliver() -> bool:
            if menu in self._pending:
                self._pending.remove(menu)
            if self._closed:
                menu.cancel()
            else:
                self.on_menu(menu)
            return False
        GLib.idle_add(deliver)

    def _read(self, stream) -> None:
        for line in stream:
            text = clean(line)
            if not text or text == self._dmenu_path:  # `command -v dmenu` del script
                continue
            self.log.append(text)
            GLib.idle_add(self._status, text)

    def _status(self, text: str) -> bool:
        if not self._closed:
            self.on_status(text)
        return False

    def _wait(self, readers) -> None:
        code = self.proc.wait()  # type: ignore[union-attr]
        for t in readers:
            t.join(timeout=1)

        def done() -> bool:
            was_closed = self._closed
            self._closed = True
            self._teardown()
            if not was_closed:
                self.on_exit(code, self.log[-3:])
            return False
        GLib.idle_add(done)
