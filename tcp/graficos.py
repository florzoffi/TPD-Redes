import matplotlib.pyplot as plt
from utils import load_delay_csv, parse_envios_txt

escenarios = [
    ("Loss 1%", "delay_loss1.csv", "loss1.txt"),
    ("Loss 2%", "delay_loss2.csv", "loss2.txt"),
    ("Loss 5%", "delay_loss5.csv", "loss5.txt"),
]

# fig, axes = plt.subplots(3, 1, figsize=(8, 10), sharex=True)
# fig.suptitle("One-Way Delay por escenario de pérdida", fontsize=14)
# 
# for ax, (titulo, csv_path, txt_path) in zip(axes, escenarios):
#     df_delay = load_delay_csv(csv_path)
#     cant_envios, _ = parse_envios_txt(txt_path)
# 
#     ax.plot(df_delay["n"], df_delay["delay"], marker="o")
#     ax.set_ylabel("Delay [s]")
#     ax.grid(True, linestyle="--", alpha=0.4)
# 
#     ax.set_title(f"{titulo}  (muestras delay = {len(df_delay)}, envíos = {cant_envios})")
# 
# axes[-1].set_xlabel("Número de muestra / envío")
# 
# plt.tight_layout(rect=[0, 0, 1, 0.96])
# plt.show()

fig, axes = plt.subplots(3, 1, figsize=(8, 10), sharex=True)
fig.suptitle("One-Way Delay por escenario de pérdida (filtrado outliers)", fontsize=14)

for ax, (titulo, csv_path, txt_path) in zip(axes, escenarios):
    df = load_delay_csv(csv_path)
    df_clean = df[(df["delay"] > 0) & (df["delay"] < 10)]
    cant_envios, _ = parse_envios_txt(txt_path)

    ax.plot(df_clean["n"], df_clean["delay"], marker="o")
    ax.set_ylabel("Delay [s]")
    ax.grid(True, linestyle="--", alpha=0.4)

    ax.set_title(
        f"{titulo}  (muestras delay = {len(df_clean)}, envíos = {cant_envios})\n"
        f"Filtro: 0 < delay < 10 s"
    )

axes[-1].set_xlabel("Número de muestra / envío")
plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.show()