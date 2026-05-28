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

    proces = None
    try:
        os.chmod(cale, 0o755)

        if sufix == ".py":
            cmd = [sys.executable, cale] + [str(a) for a in argumente]
        elif sufix == ".sh":
            cmd = ["bash", cale] + [str(a) for a in argumente]
        else:
            cmd = [cale] + [str(a) for a in argumente]

        print(f"[CLIENT] Rulez: {' '.join(cmd)}")
        
        proces = subprocess.Popen(cmd)
        proces.communicate(timeout=30)
        return proces.returncode

    except subprocess.TimeoutExpired:
        print(f"[CLIENT] Task {task_id} a depasit timpul limita. Incerc oprirea fortata...")
        if proces:
            proces.kill()
            proces.wait()
        return -2
    except Exception as e:
        print(f"[CLIENT] Eroare la executie: {e}")
        if proces:
            proces.kill()
            proces.wait()
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

def afiseaza_ajutor():
    print("""
Comenzi disponibile:
  trimite <fisier> [arg1 arg2 ...]   - Trimite un task pentru executie distribuita
  iesire                             - Deconectare si inchidere
  ajutor                             - Afiseaza acest mesaj
""")


def trimite_udp(host_server, port_server, mesaj):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(json.dumps(mesaj).encode(), (host_server, port_server))
    s.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-host", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, default=9000)
    parser.add_argument("--port-procesare", type=int, required=True)
    parser.add_argument("--nume", default=None)
    args = parser.parse_args()

    threading.Thread(
        target=server_procesare,
        args=(args.port_procesare, args.server_host, args.server_port),
        daemon=True
    ).start()

    trimite_udp(args.server_host, args.server_port, {
        "tip": "INREGISTRARE",
        "port_procesare": args.port_procesare,
        "adresa": args.nume
    })
    print(f"[CLIENT] Inregistrat la server {args.server_host}:{args.server_port}, port procesare {args.port_procesare}")

    def oprire(sig, frame):
        print("\n[CLIENT] Inchidere...")
        trimite_udp(args.server_host, args.server_port, {
            "tip": "DECONECTARE",
            "port_procesare": args.port_procesare,
            "adresa": args.nume
        })
        sys.exit(0)

    signal.signal(signal.SIGINT, oprire)
    signal.signal(signal.SIGTERM, oprire)

    afiseaza_ajutor()

    while True:
        try:
            linie = input("client> ").strip()
        except EOFError:
            break

        if not linie:
            continue

        parti = linie.split()
        comanda = parti[0].lower()

        if comanda == "iesire":
            trimite_udp(args.server_host, args.server_port, {
                "tip": "DECONECTARE",
                "port_procesare": args.port_procesare,
                "adresa": args.nume
            })
            sys.exit(0)

        elif comanda == "trimite":
            if len(parti) < 2:
                print("Utilizare: trimite <fisier> [argumente...]")
                continue
            cale_fisier = parti[1]
            argumente_task = parti[2:]
            if not os.path.isfile(cale_fisier):
                print(f"[CLIENT] Fisierul nu exista: {cale_fisier}")
                continue
            with open(cale_fisier, "rb") as f:
                date = f.read()
            binar_b64 = base64.b64encode(date).decode()
            print(f"[CLIENT] Trimit task: {cale_fisier}, argumente={argumente_task}")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((args.server_host, args.server_port))
            trimite_json(s, {
                "tip": "TRIMITE_TASK",
                "binar": binar_b64,
                "argumente": argumente_task
            })
            print("[CLIENT] Astept rezultatul...")
            try:
                rezultat = primeste_json(s)
                if rezultat and rezultat.get("tip") == "REZULTAT":
                    eroare = rezultat.get("eroare")
                    if eroare:
                        print(f"[CLIENT] Eroare: {eroare}")
                    else:
                        print(f"[CLIENT] Task executat. Exit code: {rezultat.get('exit_code')}")
            except Exception as e:
                print(f"[CLIENT] Eroare la primirea rezultatului: {e}")
            finally:
                s.close()

        elif comanda == "ajutor":
            afiseaza_ajutor()

        else:
            print(f"Comanda necunoscuta: {comanda}")


if __name__ == "__main__":
    main()
