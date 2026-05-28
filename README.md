# Proiect Retele de Calculatoare - Tema 21: Distribuirea procesarii

Sistem distribuit client-server in care un server central primeste task-uri
(cod binar + argumente) de la clienti si le distribuie spre executie folosind
algoritm round-robin. Clientul de procesare lanseaza task-ul ca proces separat
si trimite inapoi exit code-ul, pe care serverul il ruteaza catre clientul
care a cerut executia.

**Echipa:** Dina Ana-Maria, Danila Alexia-Andreea — Grupa 1088


---

## 1. Cum se ruleaza

Din radacina proiectului:

```bash
docker compose up --build
```

Aceasta porneste tot clusterul intr-o retea Docker comuna `distrib-net`:

- `distrib-server` — serverul central, asculta UDP si TCP pe portul 8815
- `distrib-client1` — primul client procesator, port de procesare 9001
- `distrib-client2` — al doilea client procesator, port de procesare 9002

Clientii se inregistreaza automat la pornire prin UDP.

Pentru oprire completa:

```bash
docker compose down
```

### Cum se trimite un task

Intr-un alt terminal, atasati-va la unul din clienti:

```bash
docker attach distrib-client1
```

Apasati Enter ca sa apara prompt-ul `client>`, apoi:

```
trimite example_task.py salut 123
```

Pentru a iesi din attach **fara** a opri clientul: `Ctrl+P`, apoi `Ctrl+Q`.
Pentru log-uri curate ale serverului: `docker compose logs -f server`.

---

## 2. Structura proiectului

```
/server
  server.py          - serverul central
  Dockerfile
/client
  client.py          - clientul (inregistrare + procesare + meniu)
  example_task.py    - task de exemplu pentru testare
  Dockerfile
/docker-compose.yml  - orchestrare server + 2 clienti
/README.md
```

---

## 3. Protocol

Mesajele sunt JSON. Pe TCP folosim un prefix de 4 octeti (big-endian) pentru
lungimea mesajului, ca sa stim unde se termina fiecare mesaj in stream.
Inregistrarea si deregistrarea folosesc UDP (datagrame), iar trimiterea
task-urilor si returnarea rezultatelor folosesc TCP.

| Mesaj           | Transport | Sens                  | Continut                                |
|-----------------|-----------|-----------------------|-----------------------------------------|
| `INREGISTRARE`  | UDP       | client -> server      | `port_procesare`, `adresa` (nume)       |
| `DECONECTARE`   | UDP       | client -> server      | `port_procesare`, `adresa`              |
| `TRIMITE_TASK`  | TCP       | client -> server      | `binar` (base64), `argumente`           |
| `EXECUTA_TASK`  | TCP       | server -> client      | `task_id`, `binar`, `argumente`         |
| `REZULTAT`      | TCP       | client -> server -> client solicitant | `task_id`, `exit_code`  |
| `EROARE`        | TCP       | server -> client      | `mesaj`                                 |

---

## 4. Porturi

- **Server:** 8815 (TCP + UDP) — port alocat echipei, expus pe gazda prin
  `docker-compose.yml`.
- **Clienti:** 9001 (client1) si 9002 (client2) — interne retelei Docker,
  nu intra in conflict cu nimic de pe masina gazda.

Daca aveti deja ceva care asculta pe 8815 pe gazda, modificati maparea din
`docker-compose.yml`:

```yaml
ports:
  - "ALT_PORT:8815/tcp"
  - "ALT_PORT:8815/udp"
```

---

## 5. Cum acopera proiectul cerintele temei 21

### 5.1 Inregistrarea clientilor (cerinta 2.1)

La pornire, fiecare client trimite UDP pe `8815` un mesaj `INREGISTRARE` cu
portul pe care asculta pentru task-uri. Serverul adauga clientul in lista
`clienti` (`server.py`, functia `gestioneaza_udp`). La iesire — fie prin
comanda `iesire` din meniu, fie prin SIGTERM la `docker stop` — clientul
trimite `DECONECTARE` si serverul il scoate din lista.

### 5.2 Trimiterea unui task (cerinta 2.2)

Un client citeste local un fisier (script Python, shell, sau binar ELF),
il codifica in base64 si il trimite serverului cu `TRIMITE_TASK`. Serverul
genereaza un `task_id` unic, alege urmatorul client din lista
(`urmatorul_client()` — round-robin cu `index_rr`) si ii trimite codul +
argumentele pe portul lui de procesare.

### 5.3 Executia task-ului (cerinta 2.3)

Clientul care primeste `EXECUTA_TASK` scrie binarul intr-un fisier temporar
si il lanseaza cu `subprocess.run` — **proces separat real**, nu thread.
Captureaza `returncode`-ul si il trimite la server cu un mesaj `REZULTAT`.
Serverul ruteaza rezultatul catre conexiunea TCP a clientului solicitant.

### 5.4 Eliminarea clientilor (cerinta 2.4)

Doua cazuri tratate:

- **Inchidere curata:** clientul trimite `DECONECTARE` la SIGINT/SIGTERM
  sau la comanda `iesire`. Serverul il sterge imediat din lista.
- **Client cazut brutal:** la urmatoarea incercare de distribuire, serverul
  face `connect()` cu `settimeout(5)` la portul lui. Daca esueaza
  (timeout, connection refused, etc.), il elimina din lista si incearca
  urmatorul (`trimite_task_la_client`, blocul `except`).

### 5.5 Tratarea erorilor (cerinta 3)

- **Niciun client activ:** serverul raspunde solicitantului cu
  `{"eroare": "Niciun client disponibil"}` in loc sa blocheze.
- **Task invalid:** validare `if not binar` inainte de a accepta cererea.
- **Tip de mesaj necunoscut:** raspuns `EROARE` explicit.
- **Conexiune intrerupta:** `citeste_exact` intoarce `None`, thread-ul
  iese curat fara crash.

### 5.6 Server concurent (cerinta 3)

- Un thread separat pentru UDP (inregistrari/deregistrari).
- Un thread per conexiune TCP acceptata.
- Un thread per distribuire de task (ca acceptarea TCP sa nu se blocheze).
- Lock-uri (`lock_clienti`, `lock_rezultate`, `lock_contor`) pentru toate
  structurile partajate.

---

## 6. Scenarii de testare (corespund celor 8 scenarii din enuntul temei)

### Scenariul 1 — Pornire server in Docker

```bash
docker compose up --build
```

In log trebuie sa apara:

```
[SERVER] Ascult UDP pe 0.0.0.0:8815
[SERVER] Ascult TCP pe 0.0.0.0:8815
```

### Scenariile 2 + 3 — Pornirea si inregistrarea celor doi clienti

In acelasi log, imediat dupa pornirea serverului:

```
[SERVER] Inregistrat client1:9001. Total: 1
[SERVER] Inregistrat client2:9002. Total: 2
```

### Scenariul 4 — Trimiterea unui task si distribuirea la primul client

In alt terminal:

```bash
docker attach distrib-client1
```

(apasa Enter pana apare prompt-ul `client>`)

```
trimite example_task.py salut 123
```

In log-ul serverului:

```
[SERVER] Task 1 primit de la ..., argumente=['salut', '123']
[SERVER] Task 1 trimis la client1:9001
```

### Scenariul 5 — Al doilea task, distribuit round-robin la al doilea client

In acelasi client1:

```
trimite example_task.py test round-robin
```

In log-ul serverului:

```
[SERVER] Task 2 trimis la client2:9002
```

Asta dovedeste rotatia: al doilea task nu mai ajunge la client1, ci la
client2.

### Scenariul 6 — Returnarea exit code-ului

Pentru fiecare task de mai sus, la client1 (cel solicitant) apare:

```
[CLIENT] Task executat. Exit code: 0
```

Iar in log-ul serverului:

```
[SERVER] Rezultat task 2: exit_code=0
```

### Scenariul 7 — Inchiderea unui client si eliminarea din lista

In al treilea terminal:

```bash
docker stop distrib-client2
```

`docker stop` trimite SIGTERM clientului. Handler-ul din `client.py`
(`signal.signal(signal.SIGTERM, oprire)`) trimite `DECONECTARE` inainte
de iesire. In log-ul serverului:

```
[SERVER] Client eliminat: client2:9002. Activi: 1
```

### Scenariul 8 — Distributie corecta dupa eliminare

Inapoi in client1:

```
trimite example_task.py dupa eliminare
```

In log-ul serverului:

```
[SERVER] Task 3 trimis la client1:9001
```

Task-ul ajunge la singurul client ramas, confirmand actualizarea listei.

### Bonus — Detectarea unui client cazut brutal (fara DECONECTARE)

```bash
docker kill distrib-client2
```

`docker kill` trimite SIGKILL (nu SIGTERM), deci clientul nu mai apuca
sa trimita `DECONECTARE`. Serverul nu stie inca de problema. La urmatorul
`trimite`, serverul incearca round-robin la client2, primeste un
`ConnectionRefusedError` / timeout, il sterge din lista si incearca
clientul urmator:

```
[SERVER] Client client2:9002 indisponibil: ...
[SERVER] Client eliminat: client2:9002. Activi: 1
[SERVER] Task 4 trimis la client1:9001
```

## 7. Cum acopera proiectul cerintele generale

- **Repository Git** (cerinta 4.1): cod complet (server + client + auxiliare),
  acest README, Dockerfile-uri si `docker-compose.yml` la radacina.
- **Docker** (cerinta 4.2): pornirea cu `docker compose up --build`, asa cum
  cere enuntul. Nu sunt necesare variabile de mediu sau setari suplimentare.
- **Stabilitate** (cerinta 5): tratam deconectarile (vezi sectiunea 5.4),
  task-urile invalide (vezi 5.5), si serverul nu cade daca un client moare.
- **Integritate** (cerinta 6): cod realizat de echipa, ambele putem explica
  partea pe care am implementat-o.

---

## 8. Impartirea muncii

- **Dina Ana-Maria** — serverul central: gestionarea listei de clienti
  (inregistrare UDP, deregistrare, eliminare la cadere), algoritmul
  round-robin, rutarea rezultatelor, protocol JSON cu framing TCP.
- **Danila Alexia-Andreea** — clientul: inregistrarea UDP la pornire, serverul de
  procesare (thread separat care asculta task-uri pe port-ul propriu),
  executia cu `subprocess`, handler-ele de semnal pentru iesire curata,
  meniul din consola.

