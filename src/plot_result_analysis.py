from __future__ import annotations

from pathlib import Path
from textwrap import shorten

import matplotlib.pyplot as plt
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = BASE_DIR / "result_analysis"
FIG_DIR = ANALYSIS_DIR / "figures"
PAPER_DIR = FIG_DIR / "paper_ready"


def setup_style() -> None:
    plt.style.use("default")
    plt.rcParams.update(
        {
            "figure.figsize": (12, 7),
            "axes.titlesize": 18,
            "axes.titleweight": "bold",
            "axes.labelsize": 13,
            "axes.facecolor": "#fafafa",
            "figure.facecolor": "white",
            "grid.color": "#d9d9d9",
            "grid.linewidth": 0.8,
            "axes.grid": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 11,
            "font.family": "DejaVu Sans",
        }
    )


def save_current(fig_name: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(FIG_DIR / f"{fig_name}.png", dpi=220, bbox_inches="tight")
    plt.savefig(PAPER_DIR / f"{fig_name}.pdf", bbox_inches="tight")
    plt.savefig(PAPER_DIR / f"{fig_name}.svg", bbox_inches="tight")
    plt.close()


def horizontal_bar(df: pd.DataFrame, y_col: str, x_col: str, title: str, xlabel: str, fig_name: str, color: str) -> None:
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.barh(df[y_col], df[x_col], color=color)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("")
    xmax = float(df[x_col].max()) if len(df) else 0.0
    ax.set_xlim(0, xmax * 1.15 if xmax else 1)
    for i, value in enumerate(df[x_col]):
        ax.text(float(value) + max(xmax * 0.015, 0.5), i, f"{int(value)}", va="center", fontsize=10)
    save_current(fig_name)


def plot_overall_summary() -> None:
    row = pd.read_csv(ANALYSIS_DIR / "overall_summary.csv").iloc[0]
    labels = [
        "Systems",
        "Files",
        "Distinct patterns",
        "Pattern instances",
        "Variability PCs",
        "Distinct violations",
    ]
    values = [
        row["systems"],
        row["files"],
        row["distinct_patterns_observed"],
        row["distinct_pattern_instances"],
        row["distinct_variability_pcs"],
        row["distinct_violations"],
    ]

    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.barh(labels, values, color=["#2b8cbe", "#a6bddb", "#41ab5d", "#74c476", "#fe9929", "#de2d26"])
    ax.invert_yaxis()
    ax.set_title("Corpus Overview")
    ax.set_xlabel("Count")
    xmax = max(values)
    ax.set_xlim(0, xmax * 1.15)
    for bar, value in zip(bars, values):
        ax.text(value + xmax * 0.015, bar.get_y() + bar.get_height() / 2, f"{int(value)}", va="center", fontsize=10)
    save_current("01_corpus_overview")


def plot_partial_vs_total() -> None:
    row = pd.read_csv(ANALYSIS_DIR / "overall_summary.csv").iloc[0]
    categories = ["Patterns in variability", "Violations"]
    partial = [row["partial_pattern_instances"], row["partial_violations"]]
    total = [row["total_pattern_instances"], row["total_violations"]]

    fig, ax = plt.subplots(figsize=(10, 7))
    x = range(len(categories))
    width = 0.6
    ax.bar(x, partial, width=width, label="Partial", color="#d95f02")
    ax.bar(x, total, width=width, bottom=partial, label="Total", color="#1b9e77")
    ax.set_xticks(list(x))
    ax.set_xticklabels(categories)
    ax.set_title("Partial vs Total Effects")
    ax.set_ylabel("Count")
    ax.legend()
    for idx, (p, t) in enumerate(zip(partial, total)):
        ax.text(idx, p / 2, str(int(p)), ha="center", va="center", color="white", fontsize=10, fontweight="bold")
        ax.text(idx, p + t / 2, str(int(t)), ha="center", va="center", color="white", fontsize=10, fontweight="bold")
    save_current("02_partial_vs_total")


def plot_top_violated_patterns() -> None:
    df = pd.read_csv(ANALYSIS_DIR / "violated_patterns.csv").head(10).copy()
    horizontal_bar(
        df=df,
        y_col="Pattern",
        x_col="distinct_violations",
        title="Top 10 Violated Patterns",
        xlabel="Distinct violations",
        fig_name="03_top_violated_patterns",
        color="#cb181d",
    )


def plot_top_systems_violations() -> None:
    df = pd.read_csv(ANALYSIS_DIR / "violations_per_system.csv").head(10).copy()
    horizontal_bar(
        df=df,
        y_col="Project",
        x_col="distinct_violations",
        title="Top 10 Systems by Violations",
        xlabel="Distinct violations",
        fig_name="04_top_systems_violations",
        color="#6a51a3",
    )


def plot_top_systems_patterns_vs_variability() -> None:
    patterns = pd.read_csv(ANALYSIS_DIR / "patterns_per_system.csv")[["Project", "distinct_pattern_instances"]]
    variability = pd.read_csv(ANALYSIS_DIR / "variability_per_system.csv")[["Project", "distinct_variability_pcs"]]
    df = patterns.merge(variability, on="Project", how="inner")
    df = df.sort_values(["distinct_pattern_instances", "distinct_variability_pcs"], ascending=False).head(10)

    fig, ax = plt.subplots(figsize=(14, 8))
    y = list(range(len(df)))
    h = 0.38
    ax.barh([v - h / 2 for v in y], df["distinct_pattern_instances"], height=h, label="Pattern instances", color="#3182bd")
    ax.barh([v + h / 2 for v in y], df["distinct_variability_pcs"], height=h, label="Variability PCs", color="#31a354")
    ax.set_yticks(y)
    ax.set_yticklabels(df["Project"])
    ax.invert_yaxis()
    ax.set_title("Top 10 Systems: Patterns vs Variability")
    ax.set_xlabel("Count")
    ax.legend()
    save_current("05_top_systems_patterns_vs_variability")


def plot_distribution_patterns_per_file() -> None:
    df = pd.read_csv(ANALYSIS_DIR / "patterns_per_file.csv")
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.hist(df["distinct_pattern_instances"], bins=30, color="#3182bd", edgecolor="white")
    ax.set_title("Distribution of Pattern Instances per File")
    ax.set_xlabel("Distinct pattern instances per file")
    ax.set_ylabel("Files")
    save_current("06_distribution_patterns_per_file")


def plot_distribution_variability_per_file() -> None:
    df = pd.read_csv(ANALYSIS_DIR / "variability_per_file.csv")
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.hist(df["distinct_variability_pcs"], bins=30, color="#31a354", edgecolor="white")
    ax.set_title("Distribution of Variability PCs per File")
    ax.set_xlabel("Distinct variability PCs per file")
    ax.set_ylabel("Files")
    save_current("07_distribution_variability_per_file")


def plot_top_variability_expressions() -> None:
    df = pd.read_csv(ANALYSIS_DIR / "variability_with_patterns.csv").head(12).copy()
    df["PC_short"] = df["PC"].map(lambda s: shorten(str(s), width=52, placeholder="..."))
    horizontal_bar(
        df=df,
        y_col="PC_short",
        x_col="pattern_links",
        title="Top Variability Expressions Linked to Patterns",
        xlabel="Distinct variability-pattern links",
        fig_name="08_top_variability_expressions",
        color="#e6550d",
    )


def main() -> None:
    setup_style()
    plot_overall_summary()
    plot_partial_vs_total()
    plot_top_violated_patterns()
    plot_top_systems_violations()
    plot_top_systems_patterns_vs_variability()
    plot_distribution_patterns_per_file()
    plot_distribution_variability_per_file()
    plot_top_variability_expressions()
    write_figure_index()
    print(f"Wrote figures to: {FIG_DIR}")


def write_figure_index() -> None:
    PAPER_DIR.mkdir(parents=True, exist_ok=True)
    content = """# Figure Index

- `01_corpus_overview`: corpus-level overview with systems, files, patterns, variability, and violations.
- `02_partial_vs_total`: stacked comparison between partial and total variability effects, and between partial and total violations.
- `03_top_violated_patterns`: top 10 usage patterns with the largest number of distinct violations.
- `04_top_systems_violations`: top 10 systems ranked by distinct violations.
- `05_top_systems_patterns_vs_variability`: comparison between pattern density and variability density in the top systems.
- `06_distribution_patterns_per_file`: histogram of distinct pattern instances per file.
- `07_distribution_variability_per_file`: histogram of distinct variability expressions per file.
- `08_top_variability_expressions`: variability expressions most frequently linked to usage patterns.

## Publication guidance

- Prefer `PDF` or `SVG` from `paper_ready/` for articles, theses, and slide decks.
- Prefer `PNG` from `figures/` for quick inspection or web embedding.
- Figures `03`, `04`, and `05` are the highest-value plots for a results section.
- Figures `06` and `07` are better suited for appendix or supplementary material.
"""
    (FIG_DIR / "FIGURE_INDEX.md").write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
