#!/usr/bin/env python3
"""Sustituto de `dmenu` que usa ani-cli-mx con --dmenu.

ani-cli-mx llama a `dmenu -l 20 -p "<prompt>"` y le pasa las opciones por
stdin ("<n> <etiqueta>" por línea). Este shim reenvía esa petición a Hasu por
un socket Unix y devuelve por stdout la línea elegida. Si la persona cancela,
sale con código 1 (igual que dmenu al pulsar Esc).
"""
import json
import os
import socket
import sys


def main() -> int:
    args = sys.argv[1:]
    prompt = ""
    i = 0
    while i < len(args):
        if args[i] == "-p" and i + 1 < len(args):
            prompt = args[i + 1]
            i += 2
        elif args[i] in ("-l", "-fn", "-nb", "-nf", "-sb", "-sf", "-m") and i + 1 < len(args):
            i += 2
        else:
            i += 1

    lines = [ln for ln in sys.stdin.read().splitlines() if ln.strip()]
    sock_path = os.environ.get("HASU_SOCK")
    if not sock_path:
        print("HASU_SOCK no está definido", file=sys.stderr)
        return 2

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(sock_path)
        s.sendall(json.dumps({"prompt": prompt, "lines": lines}).encode() + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    except OSError:
        return 1

    try:
        reply = json.loads(data.decode() or "{}")
    except ValueError:
        return 1
    choice = reply.get("choice")
    if choice is None:
        return 1
    print(choice)
    return 0


if __name__ == "__main__":
    sys.exit(main())
