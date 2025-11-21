#!/usr/bin/env python3
import argparse
import socket
import struct
import sys
import time
from pathlib import Path

SERVER_PORT = 20252

TYPE_HELLO = 1
TYPE_WRQ   = 2
TYPE_DATA  = 3
TYPE_ACK   = 4
TYPE_FIN   = 5

MAX_PDU_SIZE = 1500
CREDENTIAL = b"TEST"  # misma que EXPECTED_CREDENTIAL en server.c


def send_pdu(sock: socket.socket, addr, pdu_type: int, seq: int, payload: bytes = b""):
    if len(payload) > (MAX_PDU_SIZE - 2):
        raise ValueError("payload demasiado grande")
    pdu = struct.pack("!BB", pdu_type, seq) + payload
    sock.sendto(pdu, addr)


def wait_ack(sock: socket.socket, addr, expected_type: int, expected_seq: int, timeout: float = 1.0):
    sock.settimeout(timeout)
    while True:
        try:
            data, from_addr = sock.recvfrom(MAX_PDU_SIZE)
        except socket.timeout:
            return None, None

        if from_addr[0] != addr[0] or from_addr[1] != addr[1]:
            continue
        if len(data) < 2:
            continue

        ptype, pseq = data[0], data[1]
        payload = data[2:]

        if ptype == expected_type and pseq == expected_seq:
            return pseq, payload
        # si no matchea, ignoramos y seguimos esperando (como el cliente C)


def mode_bad_seq_order(sock, addr, remote_name: str, local_path: Path):
    """
    HELLO + WRQ correctos, primer DATA con seq=1 en vez de 0.
    Esto debería gatillar que el server ignore ese DATA fuera de orden.
    """
    # HELLO
    send_pdu(sock, addr, TYPE_HELLO, 0, CREDENTIAL)
    seq, payload = wait_ack(sock, addr, TYPE_ACK, 0, timeout=1.0)
    if seq is None or (payload and len(payload) > 0):
        print("[BAD_CLIENT] HELLO rechazado o sin ACK")
        return

    # WRQ (filename\0, seq=1)
    fn_bytes = remote_name.encode("ascii", errors="strict") + b"\x00"
    send_pdu(sock, addr, TYPE_WRQ, 1, fn_bytes)
    seq, payload = wait_ack(sock, addr, TYPE_ACK, 1, timeout=1.0)
    if seq is None or (payload and len(payload) > 0):
        print("[BAD_CLIENT] WRQ rechazado o sin ACK")
        return

    # Primer DATA mal: seq=1 (el server espera 0)
    data = local_path.read_bytes()
    chunk = data[:512]  # no importa el tamaño exacto, es sólo para molestar
    send_pdu(sock, addr, TYPE_DATA, 1, chunk)
    print("[BAD_CLIENT] HELLO + WRQ correctos, primer DATA con seq=1 en vez de 0")

    # Miramos si responde algo, pero no es obligatorio
    _, _ = wait_ack(sock, addr, TYPE_ACK, 1, timeout=1.0)


def mode_wrq_without_hello(sock, addr, remote_name: str):
    """
    Manda un WRQ sin haber mandado HELLO antes.
    El server debería descartar silenciosamente y no crear archivo.
    """
    fn_bytes = remote_name.encode("ascii", errors="strict") + b"\x00"
    send_pdu(sock, addr, TYPE_WRQ, 1, fn_bytes)
    print("[BAD_CLIENT] Mando WRQ sin HELLO previo")
    time.sleep(0.1)


def mode_data_without_wrq(sock, addr, local_path: Path):
    """
    Manda un DATA sin haber hecho HELLO ni WRQ.
    El server debería descartar silenciosamente y no crear archivo.
    """
    data = local_path.read_bytes()
    chunk = data[:512]
    send_pdu(sock, addr, TYPE_DATA, 0, chunk)
    print("[BAD_CLIENT] Mando DATA sin HELLO ni WRQ")
    time.sleep(0.1)


def main():
    parser = argparse.ArgumentParser(description="Cliente UDP 'malo' para testear el server C.")
    parser.add_argument("server_ip", type=str, help="IP del servidor C (ej. 127.0.0.1)")
    parser.add_argument(
        "--mode",
        choices=["bad_seq_order", "wrq_without_hello", "data_without_wrq"],
        required=True,
        help="Tipo de comportamiento incorrecto a generar.",
    )
    parser.add_argument(
        "--remote-name",
        type=str,
        default="bad.dat",
        help="Nombre de archivo remoto (para modos que lo usan).",
    )
    parser.add_argument(
        "--local-file",
        type=str,
        default=None,
        help="Archivo local (para modos que envían DATA).",
    )

    args = parser.parse_args()
    addr = (args.server_ip, SERVER_PORT)

    local_path = None
    if args.local_file is not None:
        local_path = Path(args.local_file).resolve()
        if not local_path.is_file():
            print(f"[BAD_CLIENT] Archivo local no encontrado: {local_path}")
            sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if args.mode == "bad_seq_order":
            if local_path is None:
                print("[BAD_CLIENT] --local-file es obligatorio en mode=bad_seq_order")
                sys.exit(1)
            mode_bad_seq_order(sock, addr, args.remote_name, local_path)
        elif args.mode == "wrq_without_hello":
            mode_wrq_without_hello(sock, addr, args.remote_name)
        elif args.mode == "data_without_wrq":
            if local_path is None:
                print("[BAD_CLIENT] --local-file es obligatorio en mode=data_without_wrq")
                sys.exit(1)
            mode_data_without_wrq(sock, addr, local_path)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
