import argparse
import socket
from pathlib import Path

SERVER_PORT = 20252

TYPE_HELLO = 1
TYPE_WRQ   = 2
TYPE_DATA  = 3
TYPE_ACK   = 4
TYPE_FIN   = 5

MAX_DATA_SIZE = 1478  


def send_pdu(sock: socket.socket, addr, pdu_type: int, seq: int, payload: bytes = b"") -> None:
    if len(payload) > MAX_DATA_SIZE:
        raise ValueError("payload demasiado grande")
    buf = bytes([pdu_type & 0xFF, seq & 0xFF]) + payload
    sock.sendto(buf, addr)


def send_hello(sock, addr, cred: bytes) -> None:
    print(f"[BAD_CLIENT] Enviando HELLO cred={cred!r}")
    send_pdu(sock, addr, TYPE_HELLO, 0, cred)


def send_wrq(sock, addr, filename: bytes) -> None:
    if b"\x00" in filename:
        raise ValueError("filename no debe contener NUL")
    payload = filename + b"\x00"
    print(f"[BAD_CLIENT] Enviando WRQ filename={filename!r}")
    send_pdu(sock, addr, TYPE_WRQ, 0, payload)


def send_file_data_normal(sock, addr, local_file: Path) -> None:
    """
    Envía DATA "bien formado":
    - primera PDU DATA con seq=0
    - siguiente con seq=1, etc. (alternando)
    """
    seq = 0
    print(f"[BAD_CLIENT] Enviando DATA normal desde {local_file}")
    with local_file.open("rb") as f:
        while True:
            chunk = f.read(MAX_DATA_SIZE)
            if not chunk:
                break
            send_pdu(sock, addr, TYPE_DATA, seq, chunk)
            seq ^= 1


def send_file_data_bad_seq_first(sock, addr, local_file: Path) -> None:
    """
    Modo "bad_seq_order":
    - Envía UN solo bloque DATA, pero con seq=1 en lugar de 0.
    Esto hace que el server ignore el bloque (espera 0), dejando
    el archivo creado en 0 bytes.
    """
    print(f"[BAD_CLIENT] Enviando DATA con seq=1 (fuera de orden) desde {local_file}")
    with local_file.open("rb") as f:
        chunk = f.read(MAX_DATA_SIZE)
        if not chunk:
            chunk = b""
        send_pdu(sock, addr, TYPE_DATA, 1, chunk)


def send_fin(sock, addr, filename: bytes) -> None:
    """
    Envía FIN con filename dado (null-terminated).
    """
    if b"\x00" in filename:
        raise ValueError("filename no debe contener NUL")
    payload = filename + b"\x00"
    print(f"[BAD_CLIENT] Enviando FIN filename={filename!r}")
    send_pdu(sock, addr, TYPE_FIN, 0, payload)


def main():
    parser = argparse.ArgumentParser(
        description="Cliente UDP malicioso para probar udp_server.c",
    )
    parser.add_argument(
        "server_ip",
        help="IP del servidor (por ejemplo 127.0.0.1)",
    )
    parser.add_argument(
        "--mode",
        choices=[
            "bad_seq_order",
            "wrq_without_hello",
            "data_without_wrq",
            "fin_wrong_filename",
        ],
        required=True,
        help="Modo de prueba maliciosa",
    )
    parser.add_argument(
        "--remote-name",
        help="Nombre remoto (filename) a usar en modos que lo requieran",
    )
    parser.add_argument(
        "--local-file",
        help="Archivo local a leer en modos que lo requieran",
    )

    args = parser.parse_args()
    server_addr = (args.server_ip, SERVER_PORT)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        if args.mode == "bad_seq_order":
            # Necesita remote-name y local-file
            if not args.remote_name or not args.local_file:
                parser.error("bad_seq_order requiere --remote-name y --local-file")

            local = Path(args.local_file)
            remote = args.remote_name.encode("ascii", errors="strict")

            send_hello(sock, server_addr, b"g17-d111")
            send_wrq(sock, server_addr, remote)
            send_file_data_bad_seq_first(sock, server_addr, local)

        elif args.mode == "wrq_without_hello":
            if not args.remote_name:
                parser.error("wrq_without_hello requiere --remote-name")
            remote = args.remote_name.encode("ascii", errors="strict")
            send_wrq(sock, server_addr, remote)

        elif args.mode == "data_without_wrq":
            if not args.local_file:
                parser.error("data_without_wrq requiere --local-file")
            local = Path(args.local_file)
            print("[BAD_CLIENT] Enviando DATA sin HELLO ni WRQ")
            with local.open("rb") as f:
                chunk = f.read(MAX_DATA_SIZE)
                if not chunk:
                    chunk = b""
                send_pdu(sock, server_addr, TYPE_DATA, 0, chunk)

        elif args.mode == "fin_wrong_filename":
            if not args.remote_name or not args.local_file:
                parser.error("fin_wrong_filename requiere --remote-name y --local-file")

            local = Path(args.local_file)
            remote_ok = args.remote_name.encode("ascii", errors="strict")

            wrong = b"ZZ" + remote_ok 

            send_hello(sock, server_addr, b"g17-d111")
            send_wrq(sock, server_addr, remote_ok)
            send_file_data_normal(sock, server_addr, local)
            send_fin(sock, server_addr, wrong)
            print(f"[BAD_CLIENT] FIN malformado enviado (filename {wrong.decode(errors='ignore')!r})")

        else:
            parser.error(f"Modo no implementado: {args.mode}")

    finally:
        sock.close()


if __name__ == "__main__":
    main()
