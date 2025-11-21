#!/usr/bin/env bash
clear

set -euo pipefail

RED="\033[0;31m"
GREEN="\033[0;32m"
NC="\033[0m"

echo -e "${GREEN}===========================${NC}"
echo -e "${GREEN}  TPD REDES – Batería de Tests${NC}"
echo -e "${GREEN}===========================${NC}\n"

# 1. Build limpio con Makefile
echo -e "${GREEN}[1/3] Limpiando y compilando...${NC}"
make clean
make all

echo -e "\n${GREEN}Compilación exitosa.\n${NC}"

# 2. Chequear python3
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}python3 no encontrado en el sistema.${NC}"
    exit 1
fi

# 3. Ejecutar test runner de Python
echo -e "${GREEN}[2/3] Ejecutando tests...${NC}\n"

python3 tests/run_tests.py
RESULT=$?

echo -e "\n${GREEN}[3/3] Finalizado.${NC}"

make clean

if [ $RESULT -eq 0 ]; then
    echo -e "${GREEN}TODOS LOS TESTS PASARON CORRECTAMENTE${NC}"
else
    echo -e "${RED}ALGUNOS TESTS FALLARON${NC}"
fi

exit $RESULT
