import socket
import threading
import json
import base64
import os
import sys
import subprocess
import tempfile
import argparse
import signal

def trimite_json(sock, obj):
    data = json.dumps(obj).encode()
    sock.sendall(len(data).to_bytes(4, "big") + data)


def citeste_exact(sock, n):
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except:
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


def primeste_json(sock):
    raw = citeste_exact(sock, 4)
    if not raw:
        return None
    lungime = int.from_bytes(raw, "big")
    data = citeste_exact(sock, lungime)
    if not data:
        return None
    return json.loads(data.decode())

def executa_task(date_binare, argumente, task_id):
    if date_binare[:2] == b"#!":
        sufix = ".sh"
        if b"python" in date_binare[:50]:
            sufix = ".py"
    elif date_binare[:4] == b"\x7fELF":
        sufix = ""
    else:
        sufix = ".py"

    with tempfile.NamedTemporaryFile(delete=False, suffix=sufix, prefix=f"task_{task_id}_") as f:
        f.write(date_binare)
        cale = f.name

    try:
        os.chmod(cale, 0o755)

        if sufix == ".py":
            cmd = [sys.executable, cale] + [str(a) for a in argumente]
        elif sufix == ".sh":
            cmd = ["bash", cale] + [str(a) for a in argumente]
        else:
            cmd = [cale] + [str(a) for a in argumente]

        print(f"[CLIENT] Rulez: {' '.join(cmd)}")
        rezultat = subprocess.run(cmd, timeout=30)
        return rezultat.returncode

    except subprocess.TimeoutExpired:
        print(f"[CLIENT] Task {task_id} a depasit timpul limita")
        return -2
    except Exception as e:
        print(f"[CLIENT] Eroare la executie: {e}")
        return -1
    finally:
        try:
            os.unlink(cale)
        except:
            pass
