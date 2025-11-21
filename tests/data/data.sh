#!/usr/bin/env bash
set -euo pipefail

# Carpeta donde está este script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR"

echo "[INFO] Creando carpeta de datos en: $DATA_DIR"
mkdir -p "$DATA_DIR"

echo "[INFO] Generando small.txt..."
echo "hola mundo de redes" > "$DATA_DIR/small.txt"

# 512 KB por archivo: bs=1024 bytes, count=512
for i in 1 2 3; do
  echo "[INFO] Generando big${i}.bin (512 KB)..."
  dd if=/dev/urandom of="$DATA_DIR/big${i}.bin" bs=1024 count=512 status=none
done

echo "[OK] Archivos generados:"
ls -lh "$DATA_DIR"
