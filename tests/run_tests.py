#!/usr/bin/env python3
import subprocess
import sys
import os
from pathlib import Path

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"


def run_cmd(cmd, cwd=None, timeout=None):
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def find_binary(name: str) -> Path:
    candidates = [
        ROOT / name,
        SRC_DIR / name,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    raise FileNotFoundError(f"No se encontró binario '{name}' en {candidates}")


def build_binaries():
    print(f"{CYAN}{BOLD}== Compilando con make all =={RESET}")
    rc, out, err = run_cmd(["make", "clean"], cwd=ROOT)
    if rc != 0:
        print(f"{YELLOW}make clean falló (continuando si los binarios ya existen):{RESET}")
        if err or out:
            print(err or out)

    rc, out, err = run_cmd(["make", "all"], cwd=ROOT)
    if rc != 0:
        print(f"{RED}make all falló:{RESET}")
        print(err or out)
        sys.exit(1)

    try:
        server_bin = find_binary("server")
        client_bin = find_binary("client")
    except FileNotFoundError as e:
        print(f"{RED}{e}{RESET}")
        sys.exit(1)

    print(f"{GREEN}Compilación OK{RESET}. server={server_bin}, client={client_bin}\n")
    return server_bin, client_bin


def main():
    os.chdir(ROOT)

    from tests import TESTS, TestContext, ensure_test_files

    ensure_test_files()
    server_bin, client_bin = build_binaries()

    ctx = TestContext()

    total = len(TESTS)
    ok_count = 0

    print(f"{CYAN}{BOLD}== Ejecutando batería de tests UDP =={RESET}\n")

    for name, fn in TESTS:
        print(f"{BOLD}=== {name} ==={RESET}")
        try:
            success = fn(server_bin, client_bin, ctx)
        except Exception as e:
            success = False
            print(f"{RED}Excepción durante el test {name}: {e}{RESET}")

        if success:
            print(f"{GREEN}[OK]{RESET} {name}\n")
            ok_count += 1
        else:
            print(f"{RED}[FAIL]{RESET} {name}\n")

    print(f"{CYAN}{BOLD}== Resumen =={RESET}")
    color = GREEN if ok_count == total else YELLOW
    print(f"{color}{ok_count}/{total} tests OK{RESET}")

    ctx.write_report()
    ctx.cleanup_files()

    exit_code = 0 if ok_count == total else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
