import socket
import threading
import json

HOST = "0.0.0.0"
PORT = 8815

clienti = []
lock_clienti = threading.Lock()
index_rr = 0

rezultate = {}
lock_rezultate = threading.Lock()

contor_task = 0
lock_contor = threading.Lock()

def id_task_nou():
    global contor_task
    with lock_contor:
        contor_task += 1
        return contor_task


def urmatorul_client():
    global index_rr
    with lock_clienti:
        if not clienti:
            return None
        c = clienti[index_rr % len(clienti)]
        index_rr = (index_rr + 1) % len(clienti)
        return dict(c)


def sterge_client(adresa, port):
    global index_rr
    with lock_clienti:
        inainte = len(clienti)
        clienti[:] = [c for c in clienti if not (c["adresa"] == adresa and c["port"] == port)]
        dupa = len(clienti)
        if inainte != dupa:
            print(f"[SERVER] Client eliminat: {adresa}:{port}. Activi: {dupa}")
            if dupa > 0:
                index_rr = index_rr % dupa
            else:
                index_rr = 0

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

def trimite_task_la_client(task_id, binar, argumente, conexiune_solicitant):
    incercari = 0
    while incercari < 10:
        target = urmatorul_client()
        if target is None:
            trimite_json(conexiune_solicitant, {
                "tip": "REZULTAT",
                "task_id": task_id,
                "exit_code": None,
                "eroare": "Niciun client disponibil"
            })
            return

        with lock_rezultate:
            rezultate[task_id] = conexiune_solicitant

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((target["adresa"], target["port"]))
            trimite_json(s, {
                "tip": "EXECUTA_TASK",
                "task_id": task_id,
                "binar": binar,
                "argumente": argumente
            })
            s.close()
            print(f"[SERVER] Task {task_id} trimis la {target['adresa']}:{target['port']}")
            return

        except Exception as e:
            print(f"[SERVER] Client {target['adresa']}:{target['port']} indisponibil: {e}")
            with lock_rezultate:
                rezultate.pop(task_id, None)
            sterge_client(target["adresa"], target["port"])
            incercari += 1

    trimite_json(conexiune_solicitant, {
        "tip": "REZULTAT",
        "task_id": task_id,
        "exit_code": None,
        "eroare": "Niciun client disponibil dupa mai multe incercari"
    })

def gestioneaza_client_tcp(conn, addr):
    adresa_client = addr[0]
    try:
        while True:
            mesaj = primeste_json(conn)
            if mesaj is None:
                break

            tip = mesaj.get("tip")

            if tip == "TRIMITE_TASK":
                binar = mesaj.get("binar")
                argumente = mesaj.get("argumente", [])
                if not binar:
                    trimite_json(conn, {"tip": "EROARE", "mesaj": "Lipseste codul binar"})
                    continue
                task_id = id_task_nou()
                print(f"[SERVER] Task {task_id} primit de la {adresa_client}, argumente={argumente}")
                t = threading.Thread(
                    target=trimite_task_la_client,
                    args=(task_id, binar, argumente, conn),
                    daemon=True
                )
                t.start()
                break

            elif tip == "REZULTAT":
                task_id = mesaj.get("task_id")
                exit_code = mesaj.get("exit_code")
                print(f"[SERVER] Rezultat task {task_id}: exit_code={exit_code}")
                with lock_rezultate:
                    conn_solicitant = rezultate.pop(task_id, None)
                if conn_solicitant:
                    try:
                        trimite_json(conn_solicitant, {
                            "tip": "REZULTAT",
                            "task_id": task_id,
                            "exit_code": exit_code
                        })
                        conn_solicitant.close()
                    except Exception as e:
                        print(f"[SERVER] Nu am putut trimite rezultatul: {e}")

            else:
                trimite_json(conn, {"tip": "EROARE", "mesaj": f"Tip necunoscut: {tip}"})

    except Exception as e:
        print(f"[SERVER] Eroare cu {adresa_client}: {e}")
    finally:
        conn.close()

def gestioneaza_udp(udp_sock):
    while True:
        try:
            date, addr = udp_sock.recvfrom(4096)
        except Exception as e:
            print(f"[SERVER] Eroare UDP: {e}")
            continue
        try:
            mesaj = json.loads(date.decode())
        except Exception:
            print(f"[SERVER] Datagrama UDP invalida de la {addr}")
            continue
        adresa_client = addr[0]
        tip = mesaj.get("tip")
        if tip == "INREGISTRARE":
            port_procesare = mesaj.get("port_procesare")
            adresa_client = mesaj.get("adresa") or adresa_client
            with lock_clienti:
                exista = any(c["adresa"] == adresa_client and c["port"] == port_procesare for c in clienti)
                if not exista:
                    clienti.append({"adresa": adresa_client, "port": port_procesare})
            print(f"[SERVER] Inregistrat {adresa_client}:{port_procesare}. Total: {len(clienti)}")
        elif tip == "DECONECTARE":
            port_procesare = mesaj.get("port_procesare")
            adresa_client = mesaj.get("adresa") or adresa_client
            sterge_client(adresa_client, port_procesare)


def main():
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_sock.bind((HOST, PORT))
    threading.Thread(target=gestioneaza_udp, args=(udp_sock,), daemon=True).start()
    print(f"[SERVER] Ascult UDP pe {HOST}:{PORT}")

    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_sock.bind((HOST, PORT))
    tcp_sock.listen(50)
    print(f"[SERVER] Ascult TCP pe {HOST}:{PORT}")

    try:
        while True:
            conn, addr = tcp_sock.accept()
            threading.Thread(target=gestioneaza_client_tcp, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[SERVER] Oprire server.")
    finally:
        tcp_sock.close()
        udp_sock.close()


if __name__ == "__main__":
    main()
