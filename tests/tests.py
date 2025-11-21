#!/usr/bin/env python3
import subprocess
import time
import os
import sys
import hashlib
from pathlib import Path
from contextlib import contextmanager

# Colores básicos "institucionales"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"

# Directorios
ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
DATA_DIR = TESTS_DIR / "data"

# Tamaño de bloque según protocol.h
MAX_DATA_SIZE = 1478


def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_test_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    small = DATA_DIR / "small.txt"
    if not small.exists():
        small.write_text("hola mundo de redes\n", encoding="utf-8")

    # 3 archivos "grandes"
    for i in range(1, 4):
        p = DATA_DIR / f"big{i}.bin"
        if not p.exists():
            size = 2 * 1024 * 1024  # 2 MB para que no tarde una eternidad
            p.write_bytes(os.urandom(size))

    # Archivo con último bloque parcial
    partial = DATA_DIR / "partial.bin"
    if not partial.exists():
        size = 2 * MAX_DATA_SIZE + 123
        partial.write_bytes(os.urandom(size))


class TestContext:
    def __init__(self):
        self.records = []
        self.to_cleanup = set()

    def record_checksum(self, test_id: str, step: str, local: Path, remote: Path) -> bool:
        md5_local = md5sum(local)
        md5_remote = md5sum(remote)
        ok = (md5_local == md5_remote)
        self.records.append(
            {
                "test": test_id,
                "step": step,
                "local": str(local),
                "remote": str(remote),
                "md5_local": md5_local,
                "md5_remote": md5_remote,
                "ok": ok,
            }
        )
        self.to_cleanup.add(remote)
        status = f"{GREEN}OK{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"    {DIM}Comparación de checksums [{step}]:{RESET} {status}")
        if not ok:
            print(f"      local : {md5_local}")
            print(f"      remoto: {md5_remote}")
        return ok

    def record_zero_size(self, test_id: str, step: str, remote: Path) -> bool:
        """
        Verifica que el archivo remoto exista y tenga tamaño 0 bytes.
        Lo agrega a la lista de archivos a limpiar, igual que record_checksum.
        """
        if not remote.exists():
            print(f"    {DIM}Verificación tamaño [{step}]:{RESET} "
                  f"{RED}FAIL{RESET} (archivo no existe: {remote})")
            return False

        size = remote.stat().st_size
        ok = (size == 0)
        self.to_cleanup.add(remote)

        status = f"{GREEN}OK{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(
            f"    {DIM}Verificación tamaño [{step}]:{RESET} {status} "
            f"(esperado 0 bytes, real {size})"
        )
        return ok

    def write_report(self, report_path: Path | None = None):
        if report_path is None:
            report_path = TESTS_DIR / "checksums_report.txt"
        lines = []
        lines.append("==== Comparación de checksums (todas las ejecuciones) ====\n")
        for r in self.records:
            status = "OK" if r["ok"] else "FAIL"
            lines.append(
                f"[{status}] test={r['test']} step={r['step']}\n"
                f"  local : {r['local']}\n"
                f"  remoto: {r['remote']}\n"
                f"  md5_local : {r['md5_local']}\n"
                f"  md5_remoto: {r['md5_remote']}\n\n"
            )
        report_path.write_text("".join(lines), encoding="utf-8")

    def cleanup_files(self):
        print(f"\n{DIM}Limpieza de archivos remotos generados...{RESET}")
        for p in sorted(self.to_cleanup):
            try:
                if p.exists():
                    p.unlink()
                    print(f"  {p.name} eliminado")
            except Exception as e:
                print(f"  No se pudo eliminar {p}: {e}")


class ServerProcess:
    def __init__(self, server_bin: Path):
        self.server_bin = server_bin
        self.proc = None
        self._finalized = False
        self.stdout_text = ""
        self.stderr_text = ""

    def __enter__(self):
        self.proc = subprocess.Popen(
            [str(self.server_bin)],
            cwd=self.server_bin.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.3)
        return self

    def finalize(self, timeout: float = 2.0):
        if self._finalized:
            return self.stdout_text, self.stderr_text
        self._finalized = True
        if self.proc is None:
            return "", ""
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
            out, err = self.proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            out, err = self.proc.communicate()
        self.stdout_text = out or ""
        self.stderr_text = err or ""
        return self.stdout_text, self.stderr_text

    def __exit__(self, exc_type, exc, tb):
        self.finalize()


def run_client(client_bin: Path, server_ip: str, cred: str, local: Path, remote_name: str, timeout: int = 60):
    proc = subprocess.run(
        [
            str(client_bin),
            server_ip,
            cred,
            str(local),
            remote_name,
        ],
        cwd=client_bin.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ===========================
#        TESTS
# ===========================

def test_small_file(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    test_id = "T1_small_file"
    print(f"{BLUE}{test_id}{RESET} Archivo pequeño flujo completo")

    local = DATA_DIR / "small.txt"
    # Debe tener largo entre 4 y 10 caracteres
    remote_name = "t1s.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(client_bin, "127.0.0.1", "g17-d111", local, remote_name)
        if rc != 0:
            out_s, err_s = sp.finalize()
            print(f"{RED}Cliente terminó con código {rc}{RESET}")
            print(f"{DIM}stdout cliente:{RESET}\n{out}")
            print(f"{DIM}stderr cliente:{RESET}\n{err}")
            print(f"{DIM}stdout server:{RESET}\n{out_s}")
            print(f"{DIM}stderr server:{RESET}\n{err_s}")
            return False

    if not remote.exists():
        print(f"{RED}No se creó el archivo remoto {remote_name}{RESET}")
        return False

    ok = ctx.record_checksum(test_id, "envio_unico", local, remote)
    return ok


def test_many_clients_parallel(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    test_id = "T2_big_parallel"
    print(f"{BLUE}{test_id}{RESET} Múltiples clientes con archivos grandes en paralelo")

    sources = [DATA_DIR / f"big{i}.bin" for i in range(1, 4)]
    remote_names = [f"t2b{i}.bin" for i in range(1, 4)]
    remotes = [ROOT / rn for rn in remote_names]

    for r in remotes:
        if r.exists():
            r.unlink()

    with ServerProcess(server_bin) as sp:
        procs = []
        for i in range(3):
            p = subprocess.Popen(
                [
                    str(client_bin),
                    "127.0.0.1",
                    "g17-d111",
                    str(sources[i]),
                    remote_names[i],
                ],
                cwd=client_bin.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            procs.append(p)

        all_ok = True
        for i, p in enumerate(procs):
            try:
                out, err = p.communicate(timeout=180)
            except subprocess.TimeoutExpired:
                p.kill()
                out, err = p.communicate()
                all_ok = False
                print(f"{RED}Timeout en cliente {i+1}{RESET}")
            if p.returncode != 0:
                all_ok = False
                print(f"{RED}Cliente {i+1} falló (exit={p.returncode}){RESET}")
                print(f"{DIM}stdout cliente {i+1}:{RESET}\n{out}")
                print(f"{DIM}stderr cliente {i+1}:{RESET}\n{err}")

        if not all_ok:
            out_s, err_s = sp.finalize()
            print(f"{DIM}stdout server:{RESET}\n{out_s}")
            print(f"{DIM}stderr server:{RESET}\n{err_s}")
            return False

    global_ok = True
    for i in range(3):
        if not remotes[i].exists():
            print(f"{RED}No se creó archivo remoto para big{i+1}.bin ({remotes[i].name}){RESET}")
            global_ok = False
        else:
            ok = ctx.record_checksum(test_id, f"cliente_{i+1}", sources[i], remotes[i])
            if not ok:
                global_ok = False

    return global_ok


def test_invalid_credential(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    test_id = "T3_bad_credential"
    print(f"{BLUE}{test_id}{RESET} Credencial inválida no debe crear archivo")

    local = DATA_DIR / "small.txt"
    remote_name = "t3bad.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(client_bin, "127.0.0.1", "BAD", local, remote_name)

        if rc == 0:
            out_s, err_s = sp.finalize()
            print(f"{RED}Cliente terminó con código 0 usando credencial inválida{RESET}")
            print(f"{DIM}stdout cliente:{RESET}\n{out}")
            print(f"{DIM}stderr cliente:{RESET}\n{err}")
            print(f"{DIM}stdout server:{RESET}\n{out_s}")
            print(f"{DIM}stderr server:{RESET}\n{err_s}")
            return False

    if remote.exists():
        print(f"{RED}Se creó archivo remoto pese a credencial inválida ({remote_name}){RESET}")
        ctx.to_cleanup.add(remote)
        return False

    print(f"    {DIM}Credencial inválida correctamente rechazada, sin archivo creado.{RESET}")
    return True


def test_mixed_credentials_concurrent(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    test_id = "T4_mixed_credentials"
    print(f"{BLUE}{test_id}{RESET} Cliente válido + cliente con credencial inválida en paralelo")

    src_ok = DATA_DIR / "big1.bin"
    src_bad = DATA_DIR / "big2.bin"
    remote_ok_name = "t4ok.bin"
    remote_bad_name = "t4bad.bin"
    remote_ok = ROOT / remote_ok_name
    remote_bad = ROOT / remote_bad_name

    for r in (remote_ok, remote_bad):
        if r.exists():
            r.unlink()

    with ServerProcess(server_bin) as sp:
        p_ok = subprocess.Popen(
            [
                str(client_bin),
                "127.0.0.1",
                "g17-d111",
                str(src_ok),
                remote_ok_name,
            ],
            cwd=client_bin.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        p_bad = subprocess.Popen(
            [
                str(client_bin),
                "127.0.0.1",
                "WRONG",
                str(src_bad),
                remote_bad_name,
            ],
            cwd=client_bin.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        out_ok, err_ok = p_ok.communicate(timeout=180)
        out_bad, err_bad = p_bad.communicate(timeout=180)

        if p_ok.returncode != 0:
            out_s, err_s = sp.finalize()
            print(f"{RED}Cliente válido falló (exit={p_ok.returncode}){RESET}")
            print(f"{DIM}stdout cliente válido:{RESET}\n{out_ok}")
            print(f"{DIM}stderr cliente válido:{RESET}\n{err_ok}")
            print(f"{DIM}stdout server:{RESET}\n{out_s}")
            print(f"{DIM}stderr server:{RESET}\n{err_s}")
            return False

        if p_bad.returncode == 0:
            out_s, err_s = sp.finalize()
            print(f"{RED}Cliente con credencial inválida terminó con exit=0{RESET}")
            print(f"{DIM}stdout cliente inválido:{RESET}\n{out_bad}")
            print(f"{DIM}stderr cliente inválido:{RESET}\n{err_bad}")
            print(f"{DIM}stdout server:{RESET}\n{out_s}")
            print(f"{DIM}stderr server:{RESET}\n{err_s}")
            return False

    if not remote_ok.exists():
        print(f"{RED}No se creó archivo remoto válido ({remote_ok_name}){RESET}")
        return False
    if remote_bad.exists():
        print(f"{RED}Se creó archivo remoto para credencial inválida ({remote_bad_name}){RESET}")
        ctx.to_cleanup.add(remote_bad)
        return False

    ok = ctx.record_checksum(test_id, "cliente_valido", src_ok, remote_ok)
    return ok


def test_partial_block_file(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    test_id = "T5_partial_block"
    print(f"{BLUE}{test_id}{RESET} Archivo con último bloque parcial")

    local = DATA_DIR / "partial.bin"
    remote_name = "t5part.bin"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(client_bin, "127.0.0.1", "g17-d111", local, remote_name)
        if rc != 0:
            out_s, err_s = sp.finalize()
            print(f"{RED}Cliente falló (exit={rc}) en archivo parcial{RESET}")
            print(f"{DIM}stdout cliente:{RESET}\n{out}")
            print(f"{DIM}stderr cliente:{RESET}\n{err}")
            print(f"{DIM}stdout server:{RESET}\n{out_s}")
            print(f"{DIM}stderr server:{RESET}\n{err_s}")
            return False

    if not remote.exists():
        print(f"{RED}No se creó archivo remoto para partial.bin{RESET}")
        return False

    ok = ctx.record_checksum(test_id, "partial", local, remote)
    return ok


def test_repeated_small_file(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    test_id = "T6_repeated_small"
    print(f"{BLUE}{test_id}{RESET} Múltiples envíos secuenciales del mismo archivo pequeño")

    local = DATA_DIR / "small.txt"
    runs = 3
    all_ok = True

    with ServerProcess(server_bin) as sp:
        for i in range(1, runs + 1):
            remote_name = f"t6r{i}.dat"
            remote = ROOT / remote_name
            if remote.exists():
                remote.unlink()

            print(f"    {DIM}Ejecución {i}/{runs}{RESET}")
            rc, out, err = run_client(client_bin, "127.0.0.1", "g17-d111", local, remote_name)
            if rc != 0:
                out_s, err_s = sp.finalize()
                print(f"{RED}Cliente falló en ejecución {i} (exit={rc}){RESET}")
                print(f"{DIM}stdout cliente:{RESET}\n{out}")
                print(f"{DIM}stderr cliente:{RESET}\n{err}")
                print(f"{DIM}stdout server:{RESET}\n{out_s}")
                print(f"{DIM}stderr server:{RESET}\n{err_s}")
                return False

            if not remote.exists():
                print(f"{RED}No se creó archivo remoto en ejecución {i} ({remote_name}){RESET}")
                all_ok = False
            else:
                ok = ctx.record_checksum(test_id, f"run_{i}", local, remote)
                if not ok:
                    all_ok = False

    return all_ok


def test_mixed_sizes_parallel(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    test_id = "T7_mixed_parallel"
    print(f"{BLUE}{test_id}{RESET} Envío paralelo pequeño + grande")

    small_local = DATA_DIR / "small.txt"
    big_local = DATA_DIR / "big3.bin"

    small_remote_name = "t7s.dat"
    big_remote_name = "t7b.bin"

    small_remote = ROOT / small_remote_name
    big_remote = ROOT / big_remote_name

    for r in (small_remote, big_remote):
        if r.exists():
            r.unlink()

    with ServerProcess(server_bin) as sp:
        p_small = subprocess.Popen(
            [
                str(client_bin),
                "127.0.0.1",
                "g17-d111",
                str(small_local),
                small_remote_name,
            ],
            cwd=client_bin.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        p_big = subprocess.Popen(
            [
                str(client_bin),
                "127.0.0.1",
                "g17-d111",
                str(big_local),
                big_remote_name,
            ],
            cwd=client_bin.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        out_s, err_s = p_small.communicate(timeout=180)
        out_b, err_b = p_big.communicate(timeout=180)

        if p_small.returncode != 0 or p_big.returncode != 0:
            out_sv, err_sv = sp.finalize()
            if p_small.returncode != 0:
                print(f"{RED}Cliente pequeño falló (exit={p_small.returncode}){RESET}")
                print(f"{DIM}stdout pequeño:{RESET}\n{out_s}")
                print(f"{DIM}stderr pequeño:{RESET}\n{err_s}")
            if p_big.returncode != 0:
                print(f"{RED}Cliente grande falló (exit={p_big.returncode}){RESET}")
                print(f"{DIM}stdout grande:{RESET}\n{out_b}")
                print(f"{DIM}stderr grande:{RESET}\n{err_b}")
            print(f"{DIM}stdout server:{RESET}\n{out_sv}")
            print(f"{DIM}stderr server:{RESET}\n{err_sv}")
            return False

    global_ok = True
    if not small_remote.exists():
        print(f"{RED}No se creó archivo remoto pequeño{RESET}")
        global_ok = False
    else:
        if not ctx.record_checksum(test_id, "small", small_local, small_remote):
            global_ok = False

    if not big_remote.exists():
        print(f"{RED}No se creó archivo remoto grande{RESET}")
        global_ok = False
    else:
        if not ctx.record_checksum(test_id, "big", big_local, big_remote):
            global_ok = False

    return global_ok

def test_bad_server_drop_ack(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    Cliente C hablando contra bad_server.py:
    - El bad_server omite el ACK del primer DATA.
    - Se espera que el cliente retransmita y que el archivo remoto quede íntegro.
    """
    test_id = "T8_bad_server_drop_ack"
    print(f"{BLUE}{test_id}{RESET} Cliente C frente a servidor que omite un ACK de DATA")
    print(f"    {DIM}Este test puede tardar un poco más de lo habitual.{RESET}")

    local = DATA_DIR / "small.txt"
    remote_name = "t8_bad_srv.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    bad_server_py = TESTS_DIR / "bad_server.py"
    if not bad_server_py.is_file():
        print(f"{YELLOW}[WARN]{RESET} bad_server.py no encontrado en {bad_server_py}")
        return False

    srv_proc = subprocess.Popen(
        [
            sys.executable,
            str(bad_server_py),
            "--mode",
            "drop_first_data_ack",
            "--output-dir",
            str(ROOT),
        ],
        cwd=TESTS_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            "g17-d111",
            local,
            remote_name,
            timeout=90,
        )
    finally:
        try:
            out_srv, err_srv = srv_proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            srv_proc.kill()
            out_srv, err_srv = srv_proc.communicate()

    if rc != 0:
        print(f"{RED}[FAIL]{RESET} Cliente C devolvió código de salida {rc}")
        print(out)
        print(err)
        print("[BAD_SERVER stdout]")
        print(out_srv)
        print("[BAD_SERVER stderr]")
        print(err_srv, file=sys.stderr)
        return False

    if not remote.exists():
        print(f"{RED}[FAIL]{RESET} El archivo remoto no se creó: {remote}")
        print("[BAD_SERVER stdout]")
        print(out_srv)
        print("[BAD_SERVER stderr]")
        print(err_srv, file=sys.stderr)
        return False

    ok = ctx.record_checksum(test_id, "drop_first_data_ack", local, remote)
    return ok


def test_bad_client_out_of_order(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    Server C hablando contra bad_client.py:

    - bad_client envía HELLO y WRQ correctos.
    - Luego envía el primer DATA con seq=1 en lugar de 0.

    Esperado:
    - El server crea el archivo (por el WRQ válido).
    - Pero NO escribe el DATA fuera de orden -> archivo de tamaño 0 bytes.
    """
    test_id = "T9_bad_client_out_of_order"
    print(f"{BLUE}{test_id}{RESET} Server C frente a cliente con DATA fuera de orden")

    remote_name = "t9bad.bin"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    bad_client_script = TESTS_DIR / "bad_client.py"
    if not bad_client_script.is_file():
        print(f"{YELLOW}[WARN]{RESET} bad_client.py no encontrado en {bad_client_script}")
        return False

    local = DATA_DIR / "small.txt"

    with ServerProcess(server_bin) as sp:
        proc = subprocess.run(
            [
                sys.executable,
                str(bad_client_script),
                "127.0.0.1",
                "--mode",
                "bad_seq_order",
                "--remote-name",
                remote_name,
                "--local-file",
                str(local),
            ],
            cwd=TESTS_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        out_bad = proc.stdout
        err_bad = proc.stderr

        out_s, err_s = sp.finalize()

    # 1) El server debería haber aceptado el WRQ y creado el archivo
    if not remote.exists():
        print(f"{RED}[FAIL]{RESET} El server C no creó el archivo remoto (WRQ no procesado?)")
        print("=== BAD_CLIENT STDOUT ===")
        print(out_bad)
        print("=== BAD_CLIENT STDERR ===")
        print(err_bad)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        return False

    # 2) El archivo debe quedar vacío (DATA fuera de orden ignorado)
    ok = ctx.record_zero_size(test_id, "out_of_order_data", remote)
    return ok

def test_bad_server_delay_ack(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    Cliente C hablando contra bad_server.py (delay_first_data_ack):
    - El bad_server demora el ACK del primer DATA más allá del timeout (~3s).
    - El cliente debe retransmitir y la transferencia debe terminar OK (checksum).
    """
    test_id = "T10_bad_server_delay_ack"
    print(f"{BLUE}{test_id}{RESET} Cliente C frente a servidor que demora el ACK de DATA")
    print(f"    {DIM}Este test puede tardar un poco más de lo habitual.{RESET}")

    local = DATA_DIR / "small.txt"
    remote_name = "t10_bad_srv_delay.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    bad_server_py = TESTS_DIR / "bad_server.py"
    if not bad_server_py.is_file():
        print(f"{YELLOW}[WARN]{RESET} bad_server.py no encontrado en {bad_server_py}")
        return False

    srv_proc = subprocess.Popen(
        [
            sys.executable,
            str(bad_server_py),
            "--mode",
            "delay_first_data_ack",
            "--delay-ms",
            "4000",
            "--output-dir",
            str(ROOT),
        ],
        cwd=TESTS_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            "g17-d111",
            local,
            remote_name,
            timeout=120,
        )
    finally:
        try:
            out_srv, err_srv = srv_proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            srv_proc.kill()
            out_srv, err_srv = srv_proc.communicate()

    if rc != 0:
        print(f"{RED}[FAIL]{RESET} Cliente C devolvió código de salida {rc}")
        print(out)
        print(err)
        print("[BAD_SERVER stdout]")
        print(out_srv)
        print("[BAD_SERVER stderr]")
        print(err_srv, file=sys.stderr)
        return False

    if not remote.exists():
        print(f"{RED}[FAIL]{RESET} El archivo remoto no se creó: {remote}")
        print("[BAD_SERVER stdout]")
        print(out_srv)
        print("[BAD_SERVER stderr]")
        print(err_srv, file=sys.stderr)
        return False

    ok = ctx.record_checksum(test_id, "delay_first_data_ack", local, remote)
    return ok

def test_bad_server_wrong_ack_seq(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    Cliente C hablando contra bad_server.py (wrong_seq_ack_once):
    - El bad_server responde al primer DATA con un ACK cuyo seq es incorrecto.
    - El cliente debe ignorarlo, retransmitir, y la transferencia debe terminar OK.
    """
    test_id = "T11_bad_server_wrong_ack_seq"
    print(f"{BLUE}{test_id}{RESET} Cliente C frente a servidor que envía ACK con seq incorrecto")

    local = DATA_DIR / "small.txt"
    remote_name = "t11_bad_srv_wrongack.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    bad_server_py = TESTS_DIR / "bad_server.py"
    if not bad_server_py.is_file():
        print(f"{YELLOW}[WARN]{RESET} bad_server.py no encontrado en {bad_server_py}")
        return False

    srv_proc = subprocess.Popen(
        [
            sys.executable,
            str(bad_server_py),
            "--mode",
            "wrong_seq_ack_once",
            "--output-dir",
            str(ROOT),
        ],
        cwd=TESTS_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            "g17-d111",
            local,
            remote_name,
            timeout=90,
        )
    finally:
        try:
            out_srv, err_srv = srv_proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            srv_proc.kill()
            out_srv, err_srv = srv_proc.communicate()

    if rc != 0:
        print(f"{RED}[FAIL]{RESET} Cliente C devolvió código de salida {rc}")
        print(out)
        print(err)
        print("[BAD_SERVER stdout]")
        print(out_srv)
        print("[BAD_SERVER stderr]")
        print(err_srv, file=sys.stderr)
        return False

    if not remote.exists():
        print(f"{RED}[FAIL]{RESET} El archivo remoto no se creó: {remote}")
        print("[BAD_SERVER stdout]")
        print(out_srv)
        print("[BAD_SERVER stderr]")
        print(err_srv, file=sys.stderr)
        return False

    ok = ctx.record_checksum(test_id, "wrong_seq_ack_once", local, remote)
    return ok

def test_wrq_without_hello(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    bad_client envía WRQ sin hacer HELLO.
    Esperado: el servidor ignora la petición y NO crea archivo.
    """
    test_id = "T12_wrq_without_hello"
    print(f"{BLUE}{test_id}{RESET} WRQ sin HELLO debe ser descartado")

    remote_name = "t12_wrq_no_hello.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    bad_client_script = TESTS_DIR / "bad_client.py"
    if not bad_client_script.is_file():
        print(f"{YELLOW}[WARN]{RESET} bad_client.py no encontrado en {bad_client_script}")
        return False

    with ServerProcess(server_bin) as sp:
        proc = subprocess.run(
            [
                sys.executable,
                str(bad_client_script),
                "127.0.0.1",
                "--mode",
                "wrq_without_hello",
                "--remote-name",
                remote_name,
            ],
            cwd=TESTS_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        out_bad = proc.stdout
        err_bad = proc.stderr

        out_s, err_s = sp.finalize()

    if remote.exists():
        print(f"{RED}[FAIL]{RESET} El server creó archivo pese a WRQ sin HELLO ({remote})")
        ctx.to_cleanup.add(remote)
        print("=== BAD_CLIENT STDOUT ===")
        print(out_bad)
        print("=== BAD_CLIENT STDERR ===")
        print(err_bad)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        return False

    print(f"    {DIM}WRQ sin HELLO correctamente descartado (sin archivo creado).{RESET}")
    return True

def test_data_without_wrq(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    bad_client envía DATA sin HELLO ni WRQ.
    Esperado: el servidor ignora todo y NO crea archivos.
    (Se verifica solo que no aparezca ningún archivo 't13_*.dat')
    """
    test_id = "T13_data_without_wrq"
    print(f"{BLUE}{test_id}{RESET} DATA sin HELLO/WRQ debe ser descartado")

    bad_client_script = TESTS_DIR / "bad_client.py"
    if not bad_client_script.is_file():
        print(f"{YELLOW}[WARN]{RESET} bad_client.py no encontrado en {bad_client_script}")
        return False

    local = DATA_DIR / "small.txt"

    # Usamos un nombre remoto para que, si por error el server lo toma, se note.
    remote_name = "t13_data_no_wrq.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        proc = subprocess.run(
            [
                sys.executable,
                str(bad_client_script),
                "127.0.0.1",
                "--mode",
                "data_without_wrq",
                "--local-file",
                str(local),
            ],
            cwd=TESTS_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        out_bad = proc.stdout
        err_bad = proc.stderr

        out_s, err_s = sp.finalize()

    # No debería haberse creado nada con ese nombre
    if remote.exists():
        print(f"{RED}[FAIL]{RESET} El server creó archivo pese a DATA sin WRQ/HELLO ({remote})")
        ctx.to_cleanup.add(remote)
        print("=== BAD_CLIENT STDOUT ===")
        print(out_bad)
        print("=== BAD_CLIENT STDERR ===")
        print(err_bad)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        return False

    print(f"    {DIM}DATA sin WRQ/HELLO correctamente descartado (sin archivo creado).{RESET}")
    return True

def test_hello_long_credential(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    HELLO con credencial ASCII pero de más de 10 caracteres.
    Según consigna, debería ser rechazada (ACK con error, cliente exit != 0, sin archivo).
    """
    test_id = "T14_hello_long_credential"
    print(f"{BLUE}{test_id}{RESET} HELLO con credencial demasiado larga debe ser rechazada")

    local = DATA_DIR / "small.txt"
    remote_name = "t14_credlong.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    long_cred = "ABCDEFGHIJK"  # 11 chars

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            long_cred,
            local,
            remote_name,
        )
        out_s, err_s = sp.finalize()

    if rc == 0 or remote.exists():
        print(f"{RED}[FAIL]{RESET} Credencial >10 chars fue aceptada (revísar handle_hello en server.c)")
        print("=== CLIENTE STDOUT ===")
        print(out)
        print("=== CLIENTE STDERR ===")
        print(err)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        if remote.exists():
            ctx.to_cleanup.add(remote)
        return False

    print(f"    {DIM}Credencial larga correctamente rechazada (exit != 0, sin archivo creado).{RESET}")
    return True

def test_wrq_short_filename(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    WRQ con filename demasiado corto (<4 caracteres).
    Debe ser rechazado (ACK con error, cliente exit != 0, sin archivo).
    """
    test_id = "T15_wrq_short_filename"
    print(f"{BLUE}{test_id}{RESET} WRQ con filename demasiado corto")

    local = DATA_DIR / "small.txt"
    remote_name = "a.c"  # 3 caracteres antes del \0
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            "g17-d111",
            local,
            remote_name,
        )
        out_s, err_s = sp.finalize()

    if rc == 0 or remote.exists():
        print(f"{RED}[FAIL]{RESET} Filename corto fue aceptado (revísar validate_filename)")
        print("=== CLIENTE STDOUT ===")
        print(out)
        print("=== CLIENTE STDERR ===")
        print(err)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        if remote.exists():
            ctx.to_cleanup.add(remote)
        return False

    print(f"    {DIM}Filename corto correctamente rechazado (sin archivo creado).{RESET}")
    return True

def test_wrq_long_filename(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    WRQ con filename demasiado largo (>10 caracteres).
    Debe ser rechazado (ACK con error, cliente exit != 0, sin archivo).
    """
    test_id = "T16_wrq_long_filename"
    print(f"{BLUE}{test_id}{RESET} WRQ con filename demasiado largo")

    local = DATA_DIR / "small.txt"
    remote_name = "12345678901"  # 11 chars
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            "g17-d111",
            local,
            remote_name,
        )
        out_s, err_s = sp.finalize()

    if rc == 0 or remote.exists():
        print(f"{RED}[FAIL]{RESET} Filename largo fue aceptado (revisar validate_filename)")
        print("=== CLIENTE STDOUT ===")
        print(out)
        print("=== CLIENTE STDERR ===")
        print(err)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        if remote.exists():
            ctx.to_cleanup.add(remote)
        return False

    print(f"    {DIM}Filename largo correctamente rechazado (sin archivo creado).{RESET}")
    return True

def test_many_small_clients_stress(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    Varios clientes (N>=8) enviando el mismo archivo pequeño en paralelo.
    Verifica que el servidor soporte concurrencia y que todos los archivos lleguen íntegros.
    """
    test_id = "T17_many_small_clients_stress"
    print(f"{BLUE}{test_id}{RESET} Stress de concurrencia con muchos clientes pequeños en paralelo")

    local = DATA_DIR / "small.txt"
    num_clients = 8  # puedes subirlo a 10 si querés apretar más
    remote_names = [f"t17_c{i+1}.dat" for i in range(num_clients)]
    remotes = [ROOT / name for name in remote_names]

    # Limpiar cualquier archivo remoto previo
    for r in remotes:
        if r.exists():
            r.unlink()

    all_ok = True

    with ServerProcess(server_bin) as sp:
        procs = []
        for i in range(num_clients):
            p = subprocess.Popen(
                [
                    str(client_bin),
                    "127.0.0.1",
                    "g17-d111",
                    str(local),
                    remote_names[i],
                ],
                cwd=client_bin.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            procs.append(p)

        # Esperar a que todos terminen
        for i, p in enumerate(procs):
            try:
                out, err = p.communicate(timeout=180)
            except subprocess.TimeoutExpired:
                p.kill()
                out, err = p.communicate()
                all_ok = False
                print(f"{RED}Timeout en cliente {i+1}{RESET}")

            if p.returncode != 0:
                all_ok = False
                print(f"{RED}Cliente {i+1} falló (exit={p.returncode}){RESET}")
                print(f"{DIM}stdout cliente {i+1}:{RESET}\n{out}")
                print(f"{DIM}stderr cliente {i+1}:{RESET}\n{err}")

        if not all_ok:
            out_s, err_s = sp.finalize()
            print(f"{DIM}stdout server:{RESET}\n{out_s}")
            print(f"{DIM}stderr server:{RESET}\n{err_s}")
            return False

    # Verificar que todos los archivos se hayan creado y sean correctos
    global_ok = True
    for i in range(num_clients):
        if not remotes[i].exists():
            print(f"{RED}No se creó archivo remoto para cliente {i+1} ({remotes[i].name}){RESET}")
            global_ok = False
        else:
            ok = ctx.record_checksum(test_id, f"cliente_{i+1}", local, remotes[i])
            if not ok:
                global_ok = False

    return global_ok

def test_wrq_non_ascii_filename(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    WRQ con filename que incluye caracteres no ASCII (por ejemplo 'ñ').
    Según la consigna, el filename debe ser ASCII puro, así que esto debe ser rechazado:
    - ACK con mensaje de error
    - cliente con exit != 0
    - sin archivo creado
    """
    test_id = "T18_wrq_non_ascii_filename"
    print(f"{BLUE}{test_id}{RESET} WRQ con filename no ASCII")

    local = DATA_DIR / "small.txt"
    # 'tñ18.dat' tiene 8 caracteres, dentro del rango [4, 10], pero contiene 'ñ' (no ASCII)
    remote_name = "tñ18.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            "g17-d111",
            local,
            remote_name,
        )
        out_s, err_s = sp.finalize()

    # Debe ser rechazado: exit != 0 y sin archivo creado
    if rc == 0 or remote.exists():
        print(f"{RED}[FAIL]{RESET} Filename con caracteres no ASCII fue aceptado.")
        print("=== CLIENTE STDOUT ===")
        print(out)
        print("=== CLIENTE STDERR ===")
        print(err)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        if remote.exists():
            ctx.to_cleanup.add(remote)
        return False

    print(f"    {DIM}Filename no ASCII correctamente rechazado (sin archivo creado).{RESET}")
    return True

def test_bad_credential_shows_user_message(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    Igual que T3, pero además chequea que el cliente muestre *algún* mensaje
    de error al usuario (stdout o stderr no vacíos).
    """
    test_id = "T19_bad_credential_msg"
    print(f"{BLUE}{test_id}{RESET} Mensaje de error visible para credencial inválida")

    local = DATA_DIR / "small.txt"
    remote_name = "t19_badmsg.dat"
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            "BAD",
            local,
            remote_name,
        )
        out_s, err_s = sp.finalize()

    # No debe crear archivo
    if remote.exists():
        print(f"{RED}[FAIL]{RESET} Se creó archivo remoto pese a credencial inválida ({remote})")
        ctx.to_cleanup.add(remote)
        return False

    # Debe fallar
    if rc == 0:
        print(f"{RED}[FAIL]{RESET} Cliente terminó con exit=0 usando credencial inválida")
        print("=== CLIENTE STDOUT ===")
        print(out)
        print("=== CLIENTE STDERR ===")
        print(err)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        return False

    # Debe mostrar ALGÚN mensaje al usuario
    combined = (out + err).strip()
    if not combined:
        print(f"{RED}[FAIL]{RESET} Credencial inválida pero el cliente no mostró ningún mensaje.")
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        return False

    print(f"    {DIM}Credencial inválida con mensaje visible para el usuario (stdout/stderr no vacíos).{RESET}")
    return True


def test_wrq_min_length_filename_ok(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    Filename de longitud mínima válida (4 caracteres ASCII).
    Debe ser aceptado y transferir correctamente.
    """
    test_id = "T20_wrq_min_length_ok"
    print(f"{BLUE}{test_id}{RESET} Filename longitud mínima (4 chars) aceptado")

    local = DATA_DIR / "small.txt"
    remote_name = "abcd"   # 4 chars, todo ASCII
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            "g17-d111",
            local,
            remote_name,
        )
        out_s, err_s = sp.finalize()

    if rc != 0:
        print(f"{RED}[FAIL]{RESET} Cliente falló con filename mínimo válido (exit={rc})")
        print("=== CLIENTE STDOUT ===")
        print(out)
        print("=== CLIENTE STDERR ===")
        print(err)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        return False

    if not remote.exists():
        print(f"{RED}[FAIL]{RESET} No se creó archivo remoto para filename mínimo ({remote})")
        return False

    ok = ctx.record_checksum(test_id, "min_len_ok", local, remote)
    return ok


def test_wrq_max_length_filename_ok(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    Filename de longitud máxima válida (10 caracteres ASCII).
    Debe ser aceptado y transferir correctamente.
    """
    test_id = "T21_wrq_max_length_ok"
    print(f"{BLUE}{test_id}{RESET} Filename longitud máxima (10 chars) aceptado")

    local = DATA_DIR / "small.txt"
    remote_name = "1234567890"  # 10 chars ASCII
    remote = ROOT / remote_name
    if remote.exists():
        remote.unlink()

    with ServerProcess(server_bin) as sp:
        rc, out, err = run_client(
            client_bin,
            "127.0.0.1",
            "g17-d111",
            local,
            remote_name,
        )
        out_s, err_s = sp.finalize()

    if rc != 0:
        print(f"{RED}[FAIL]{RESET} Cliente falló con filename máximo válido (exit={rc})")
        print("=== CLIENTE STDOUT ===")
        print(out)
        print("=== CLIENTE STDERR ===")
        print(err)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        return False

    if not remote.exists():
        print(f"{RED}[FAIL]{RESET} No se creó archivo remoto para filename máximo ({remote})")
        return False

    ok = ctx.record_checksum(test_id, "max_len_ok", local, remote)
    return ok


def test_fin_wrong_filename(server_bin: Path, client_bin: Path, ctx: TestContext) -> bool:
    """
    FIN con filename distinto al del WRQ.

    Escenario:
      - bad_client envía HELLO válido
      - envía WRQ válido con <remote_ok_name>
      - envía DATA correctos desde local.txt
      - termina con FIN cuyo filename NO coincide (otro distinto)

    Esperado:
      - El archivo <remote_ok_name> debe existir e igual al local.
      - El server no debe romper la transferencia ya escrita.
    """
    test_id = "T22_fin_wrong_filename"
    print(f"{BLUE}{test_id}{RESET} FIN con filename distinto al WRQ")

    bad_client_script = TESTS_DIR / "bad_client.py"
    if not bad_client_script.is_file():
        print(f"{YELLOW}[WARN]{RESET} bad_client.py no encontrado en {bad_client_script}")
        return False

    local = DATA_DIR / "small.txt"

    # Nombre "bueno" del WRQ: dentro de [4,10] chars y ASCII
    remote_ok_name = "t22ok.bin"   # 8 caracteres → válido
    remote_ok = ROOT / remote_ok_name

    # Limpiar archivo previo si existe
    if remote_ok.exists():
        remote_ok.unlink()

    with ServerProcess(server_bin) as sp:
        proc = subprocess.run(
            [
                sys.executable,
                str(bad_client_script),
                "127.0.0.1",        # server_ip
                "--mode",
                "fin_wrong_filename",
                "--remote-name",
                remote_ok_name,
                "--local-file",
                str(local),
            ],
            cwd=TESTS_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        out_bad = proc.stdout
        err_bad = proc.stderr

        out_s, err_s = sp.finalize()

    # 1) El archivo "bueno" debe existir e igual al local
    if not remote_ok.exists():
        print(f"{RED}[FAIL]{RESET} No se creó archivo remoto esperado ({remote_ok})")
        print("=== BAD_CLIENT STDOUT ===")
        print(out_bad)
        print("=== BAD_CLIENT STDERR ===")
        print(err_bad)
        print("=== SERVER STDOUT ===")
        print(out_s)
        print("=== SERVER STDERR ===")
        print(err_s)
        return False

    ok_data = ctx.record_checksum(test_id, "fin_wrong_filename_okfile", local, remote_ok)

    if not ok_data:
        return False

    print(f"    {DIM}FIN con filename distinto manejado correctamente (archivo bueno OK).{RESET}")
    return True



TESTS = [
    ("T1_small_file",              test_small_file),
    ("T2_big_parallel",            test_many_clients_parallel),
    ("T3_bad_credential",          test_invalid_credential),
    ("T4_mixed_credentials",       test_mixed_credentials_concurrent),
    ("T5_partial_block",           test_partial_block_file),
    ("T6_repeated_small",          test_repeated_small_file),
    ("T7_mixed_parallel",          test_mixed_sizes_parallel),
    ("T8_bad_server_drop_ack",     test_bad_server_drop_ack),
    ("T9_bad_client_out_of_order", test_bad_client_out_of_order),
    ("T10_bad_server_delay_ack",   test_bad_server_delay_ack),
    ("T11_bad_server_wrong_ack_seq", test_bad_server_wrong_ack_seq),
    ("T12_wrq_without_hello",      test_wrq_without_hello),
    ("T13_data_without_wrq",       test_data_without_wrq),
    ("T14_hello_long_credential",  test_hello_long_credential),
    ("T15_wrq_short_filename",     test_wrq_short_filename),
    ("T16_wrq_long_filename",      test_wrq_long_filename),
    ("T17_many_small_clients_stress", test_many_small_clients_stress),
    ("T18_wrq_non_ascii_filename",    test_wrq_non_ascii_filename),
    ("T19_bad_credential_msg",        test_bad_credential_shows_user_message),
    ("T20_wrq_min_length_ok",         test_wrq_min_length_filename_ok),
    ("T21_wrq_max_length_ok",         test_wrq_max_length_filename_ok),
    ("T22_fin_wrong_filename",        test_fin_wrong_filename),
]
