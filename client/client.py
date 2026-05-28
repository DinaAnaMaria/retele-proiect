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

def server_procesare(port_procesare, host_server, port_server):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port_procesare))
    sock.listen(10)
    print(f"[CLIENT] Ascult pe portul {port_procesare} pentru task-uri")

    while True:
        try:
            conn, addr = sock.accept()
            threading.Thread(target=proceseaza_task, args=(conn, host_server, port_server), daemon=True).start()
        except Exception as e:
            print(f"[CLIENT] Eroare server procesare: {e}")
            break


def proceseaza_task(conn, host_server, port_server):
    try:
        mesaj = primeste_json(conn)
        if mesaj is None or mesaj.get("tip") != "EXECUTA_TASK":
            conn.close()
            return

        task_id = mesaj["task_id"]
        binar_b64 = mesaj["binar"]
        argumente = mesaj.get("argumente", [])

        print(f"[CLIENT] Execut task {task_id}, argumente={argumente}")

        try:
            date_binare = base64.b64decode(binar_b64)
        except Exception as e:
            print(f"[CLIENT] Eroare decodare binar: {e}")
            trimite_rezultat(host_server, port_server, task_id, -1)
            conn.close()
            return

        exit_code = executa_task(date_binare, argumente, task_id)
        print(f"[CLIENT] Task {task_id} terminat cu exit_code={exit_code}")
        trimite_rezultat(host_server, port_server, task_id, exit_code)

    except Exception as e:
        print(f"[CLIENT] Eroare procesare task: {e}")
    finally:
        conn.close()


def trimite_rezultat(host_server, port_server, task_id, exit_code):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((host_server, port_server))
        trimite_json(s, {
            "tip": "REZULTAT",
            "task_id": task_id,
            "exit_code": exit_code
        })
        s.close()
    except Exception as e:
        print(f"[CLIENT] Nu am putut trimite rezultatul la server: {e}")
