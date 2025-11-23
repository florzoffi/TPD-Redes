import pandas as pd
import re

def load_delay_csv(path):
    df = pd.read_csv(path, header=None, names=["n", "delay"])
    return df

def parse_envios_txt(path):
    patron = re.compile(r"Envio\s+(\d+):\s+mande\s+(\d+)\s+bytes")
    envios = []

    with open(path, "r", encoding="utf-8") as f:
        for linea in f:
            m = patron.search(linea)
            if m:
                n = int(m.group(1))
                b = int(m.group(2))
                envios.append((n, b))

    return len(envios), envios