from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "figures"
TABLES = OUTPUTS / "tables"


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)

    x = np.linspace(0, 1, 50)
    y = 1 - np.exp(-4 * x)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(x, y, marker="o", markevery=8, label="example")
    ax.set_xlabel("parameter")
    ax.set_ylabel("response")
    ax.set_title("Example reproducible figure")
    ax.legend()
    fig.savefig(FIGURES / "example_result.png", dpi=300)
    fig.savefig(FIGURES / "example_result.pdf")
    print("Generated example_result figure under outputs/figures")


if __name__ == "__main__":
    main()
