# Proiect Retele de Calculatoare - Tema 21

Distribuirea procesarii intr-un sistem client-server.

Echipa: Dina Ana-Maria, Danila Alexia-Andreea
Grupa 1088

## Despre proiect

Un server central primeste task-uri (cod binar + argumente) de la clienti si
le distribuie spre executie folosind round-robin. Clientul care primeste un
task il executa ca proces separat si trimite inapoi exit code-ul, pe care
serverul il ruteaza catre clientul care a cerut task-ul.

Inregistrarea si deregistrarea clientilor se fac prin UDP, iar trimiterea
task-urilor si returnarea rezultatelor prin TCP. Serverul asculta UDP si TCP
pe acelasi port. Codul binar al task-ului se transmite codificat base64 in
mesaje JSON.

## Cum se ruleaza

Din radacina proiectului:

    docker compose up --build

Aceasta porneste tot clusterul: serverul si doi clienti (client1 si client2)
intr-o retea Docker comuna. Clientii se inregistreaza automat la pornire.

Pentru oprire: `docker compose down`.

## Cum se trimite un task

Intr-un alt terminal:

    docker attach distrib-client1

Apasa Enter ca sa apara prompt-ul `client>`, apoi:

    trimite example_task.py salut 123

Trimite acelasi task de mai multe ori ca sa observi round-robin-ul
(primul ajunge la client1, al doilea la client2, samd).

Pentru a iesi din attach fara a opri clientul: Ctrl+P, apoi Ctrl+Q.
Pentru log-uri curate ale serverului: `docker compose logs -f server`.

## Structura

    server/      - serverul central (server.py + Dockerfile)
    client/      - clientul (client.py + Dockerfile + example_task.py)
    docker-compose.yml
    README.md

Munca a fost impartita astfel: Ana-Maria a implementat serverul (gestiunea
listei de clienti, distributia round-robin, rutarea rezultatelor), iar
Alexia a implementat clientul (inregistrare UDP, server de procesare,
executia task-urilor cu subprocess, meniul din consola).

## Protocol

Mesaje JSON. Pe TCP folosim un prefix de 4 octeti pentru lungimea mesajului,
ca sa stim unde se termina fiecare mesaj in stream.

INREGISTRARE   - UDP, client -> server, anunta portul de procesare
DECONECTARE    - UDP, client -> server, scoate clientul din lista
TRIMITE_TASK   - TCP, client -> server, cod binar (base64) + argumente
EXECUTA_TASK   - TCP, server -> client, task spre executie
REZULTAT       - TCP, ruteaza exit code-ul

## Porturi

Serverul ruleaza pe portul 8815 al masinii gazda (port alocat echipei).
Clientii folosesc 9001 si 9002 doar in interiorul retelei Docker, deci nu
intra in conflict cu nimic de pe gazda.



