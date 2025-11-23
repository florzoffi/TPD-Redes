import matplotlib.pyplot as plt
from utils import load_delay_csv, parse_envios_txt

csv_path = "delay_jitter.csv"
txt_path = "jitter.txt"

df_delay = load_delay_csv(csv_path)
cant_envios, _ = parse_envios_txt(txt_path)

# plt.figure(figsize=(10, 5))
# plt.plot(df_delay["n"], df_delay["delay"], marker="o", linestyle="-")
# 
# plt.title(f"One-Way Delay con Jitter (muestras = {len(df_delay)}, envíos = {cant_envios})")
# plt.xlabel("Número de muestra / envío")
# plt.ylabel("Delay [s]")
# plt.grid(True, linestyle="--", alpha=0.4)
# 
# plt.tight_layout()
# plt.show()

df_clean = df_delay[(df_delay["delay"] > 0) & (df_delay["delay"] < 10)]

plt.figure(figsize=(10, 5))
plt.plot(df_clean["n"], df_clean["delay"], marker="o", linestyle="-")

plt.title(
    f"One-Way Delay con Jitter (FILTRADO)\n"
    f"muestras reales = {len(df_clean)}, envíos = {cant_envios}"
)
plt.xlabel("Número de muestra / envío")
plt.ylabel("Delay [s]")
plt.grid(True, linestyle="--", alpha=0.4)

plt.tight_layout()
plt.show()
