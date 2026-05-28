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
