#!/usr/bin/env python3
"""
bad_server.py

Servidor UDP "malicioso" para testear la robustez del cliente en C.
Habla el mismo protocolo que server.c, pero puede:
- omitir un ACK
- enviar un ACK con seq incorrecto
- demorar un ACK más allá del timeout del cliente

Se asume que sólo se usa para pruebas de un único cliente a la vez.
"""

import argparse
import socket
import time
from pathlib import Path
from typing import Optional, Dict, Tuple

SERVER_PORT = 20252

TYPE_HELLO = 1
TYPE_WRQ   = 2
TYPE_DATA  = 3
TYPE_ACK   = 4
TYPE_FIN   = 5

MAX_PDU_SIZE  = 1500
MAX_DATA_SIZE = 1478  # igual que en protocol.h del TP


class ClientState:
    def __init__(self, addr: Tuple[str, int], output_dir: Path):
        self.addr = addr
        self.output_dir = output_dir
        self.filename: Optional[str] = None
        self.fp = None
        self.last_seq: Optional[int] = None
        self.data_pkts = 0
        self.drop_done = False
        self.wrong_ack_done = False
        self.delay_done = False

    def close(self):
        if self.fp is not None:
            try:
                self.fp.close()
            finally:
                self.fp = None


def send_pdu(sock: socket.socket,
             addr: Tuple[str, int],
             pdu_type: int,
             seq: int,
             payload: bytes = b"") -> None:
    if len(payload) > MAX_DATA_SIZE:
        raise ValueError("payload demasiado grande para PDU")
    buf = bytes([pdu_type & 0xFF, seq & 0xFF]) + payload
    sock.sendto(buf, addr)


def main():
    parser = argparse.ArgumentParser(
        description="Servidor UDP 'malo' para testear el cliente C (stop & wait).",
    )
    parser.add_argument(
        "--mode",
        choices=[
            "normal",
            "drop_first_data_ack",
            "wrong_seq_ack_once",
            "delay_first_data_ack",
        ],
        default="drop_first_data_ack",
        help="Comportamiento 'malo' a aplicar sobre la fase DATA.",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=4000,
        help="Delay artificial para 'delay_first_data_ack' (ms).",
    )
    parser.add_argument(
        "--expected-credential",
        type=str,
        default="TEST",
        help="Credencial válida esperada en HELLO.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Directorio donde se guardarán los archivos recibidos.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=SERVER_PORT,
        help="Puerto UDP en el que escucha el servidor.",
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))

    print(f"[BAD_SERVER] Escuchando en UDP {args.port}, modo={args.mode}")

    clients: Dict[Tuple[str, int], ClientState] = {}

    try:
        while True:
            data, addr = sock.recvfrom(MAX_PDU_SIZE)
            if len(data) < 2:
                continue

            pdu_type = data[0]
            seq = data[1]
            payload = data[2:]

            key = (addr[0], addr[1])
            if key not in clients:
                clients[key] = ClientState(key, output_dir)
            st = clients[key]

            if pdu_type == TYPE_HELLO:
                cred = payload.decode(errors="ignore")
                print(f"[BAD_SERVER] HELLO desde {addr}, cred='{cred}' seq={seq}")
                if cred == args.expected_credential:
                    # ACK seq=0, sin payload
                    send_pdu(sock, addr, TYPE_ACK, 0, b"")
                else:
                    msg = "Credencial invalida".encode()
                    send_pdu(sock, addr, TYPE_ACK, 0, msg)
                continue

            if pdu_type == TYPE_WRQ:
                # filename null-terminated
                if b"\x00" in payload:
                    filename = payload.split(b"\x00", 1)[0].decode(errors="ignore")
                else:
                    filename = payload.decode(errors="ignore")
                st.filename = filename or "output.bin"
                path = output_dir / st.filename
                print(f"[BAD_SERVER] WRQ filename='{st.filename}' -> {path}")
                st.fp = open(path, "wb")
                # ACK seq=1, sin payload
                send_pdu(sock, addr, TYPE_ACK, 1, b"")
                continue

            if pdu_type == TYPE_DATA:
                st.data_pkts += 1
                print(
                    f"[BAD_SERVER] DATA seq={seq} len={len(payload)} "
                    f"pkt={st.data_pkts}"
                )

                # Detección simple de retransmisión: mismo seq que el último
                if st.last_seq is not None and seq == st.last_seq:
                    print("[BAD_SERVER] DATA repetido (retransmisión), no reescribo")
                    send_pdu(sock, addr, TYPE_ACK, seq, b"")
                    continue

                # Nuevo bloque de datos
                if st.fp is not None and payload:
                    st.fp.write(payload)
                    st.fp.flush()

                # Comportamientos "malos"
                if args.mode == "drop_first_data_ack" and not st.drop_done:
                    print("[BAD_SERVER] MODO drop_first_data_ack: omito ACK")
                    st.drop_done = True
                    st.last_seq = seq
                    # No mando ACK, el cliente deberá retransmitir
                    continue

                if args.mode == "wrong_seq_ack_once" and not st.wrong_ack_done:
                    wrong_seq = 0 if seq == 1 else 1
                    print(
                        f"[BAD_SERVER] MODO wrong_seq_ack_once: envío ACK con seq={wrong_seq}"
                    )
                    send_pdu(sock, addr, TYPE_ACK, wrong_seq, b"")
                    st.wrong_ack_done = True
                    st.last_seq = seq
                    continue

                if args.mode == "delay_first_data_ack" and not st.delay_done:
                    delay_s = args.delay_ms / 1000.0
                    print(
                        f"[BAD_SERVER] MODO delay_first_data_ack: "
                        f"duermo {delay_s:.3f} s antes de ACK"
                    )
                    time.sleep(delay_s)
                    st.delay_done = True

                # Camino normal: ACK con el mismo seq recibido
                send_pdu(sock, addr, TYPE_ACK, seq, b"")
                st.last_seq = seq
                continue

            if pdu_type == TYPE_FIN:
                # El payload trae el filename null-terminated
                if b"\x00" in payload:
                    fin_name = payload.split(b"\x00", 1)[0].decode(errors="ignore")
                else:
                    fin_name = payload.decode(errors="ignore")
                print(
                    f"[BAD_SERVER] FIN seq={seq} filename='{fin_name}', "
                    f"guardado como '{st.filename}'"
                )
                # ACK final
                send_pdu(sock, addr, TYPE_ACK, seq, b"")
                st.close()
                continue

            print(f"[BAD_SERVER] PDU tipo desconocido {pdu_type}, ignoro.")

    except KeyboardInterrupt:
        print("[BAD_SERVER] Cerrando por KeyboardInterrupt")
    finally:
        for st in clients.values():
            st.close()
        sock.close()


if __name__ == "__main__":
    main()
