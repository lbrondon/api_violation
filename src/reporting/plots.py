from __future__ import annotations

from pathlib import Path
from textwrap import shorten

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from reporting.metrics import MetricBundle

try:
    import matplotlib.pyplot as plt  # type: ignore
except Exception:
    plt = None


def setup_style() -> None:
    if plt is None:
        return
    plt.style.use("default")
    plt.rcParams.update(
        {
            "figure.figsize": (12, 7),
            "axes.titlesize": 18,
            "axes.titleweight": "bold",
            "axes.labelsize": 12,
            "figure.facecolor": "white",
            "axes.facecolor": "#fcfcfa",
            "axes.grid": True,
            "grid.color": "#d8d8d8",
            "grid.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.family": "DejaVu Sans",
        }
    )


def _save_matplotlib(figures_dir: Path, name: str) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(figures_dir / f"{name}.png", dpi=220, bbox_inches="tight")
    plt.close()


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _canvas(width: int = 1400, height: int = 900) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    return img, draw


def _save_pil(img: Image.Image, figures_dir: Path, name: str) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    img.save(figures_dir / f"{name}.png")


def _draw_title(draw: ImageDraw.ImageDraw, title: str, width: int) -> None:
    draw.text((width // 2, 35), title, fill="#222222", font=_font(28), anchor="mm")


def _draw_horizontal_bars(
    figures_dir: Path,
    name: str,
    title: str,
    labels: list[str],
    values: list[float],
    color: str,
    x_label: str,
) -> None:
    img, draw = _canvas()
    width, height = img.size
    _draw_title(draw, title, width)

    left = 360
    right = width - 90
    top = 110
    bottom = height - 90
    plot_height = bottom - top
    bar_gap = 12
    n = max(1, len(labels))
    bar_h = max(18, (plot_height - bar_gap * (n - 1)) // n)
    vmax = max(values) if values else 1.0

    draw.line((left, bottom, right, bottom), fill="#555555", width=2)
    draw.line((left, top, left, bottom), fill="#555555", width=2)
    draw.text(((left + right) // 2, height - 35), x_label, fill="#333333", font=_font(18), anchor="mm")

    for idx, (label, value) in enumerate(zip(labels, values)):
        y = top + idx * (bar_h + bar_gap)
        bar_w = int((value / vmax) * (right - left - 20)) if vmax else 0
        draw.rectangle((left, y, left + bar_w, y + bar_h), fill=color)
        draw.text((left - 15, y + bar_h // 2), shorten(label, width=42, placeholder="..."), fill="#222222", font=_font(16), anchor="rm")
        draw.text((left + bar_w + 10, y + bar_h // 2), str(int(value)), fill="#222222", font=_font(15), anchor="lm")

    _save_pil(img, figures_dir, name)


def _draw_stacked_stage_chart(figures_dir: Path, name: str, title: str, df: pd.DataFrame) -> None:
    img, draw = _canvas()
    width, height = img.size
    _draw_title(draw, title, width)

    left = 120
    right = width - 80
    top = 120
    bottom = height - 120
    stage_gap = 60
    n = len(df)
    bar_w = 90
    vmax = float(df["Rows"].max()) if len(df) else 1.0

    draw.line((left, bottom, right, bottom), fill="#555555", width=2)
    draw.line((left, top, left, bottom), fill="#555555", width=2)

    for idx, row in df.iterrows():
        x = left + idx * ((right - left) // max(1, n))
        total_h = int((row["Rows"] / vmax) * (bottom - top - 40))
        no_h = int((row["NO"] / vmax) * (bottom - top - 40))
        yes_h = int((row["YES"] / vmax) * (bottom - top - 40))
        draw.rectangle((x, bottom - no_h, x + bar_w, bottom), fill="#9ecae1")
        draw.rectangle((x, bottom - no_h - yes_h, x + bar_w, bottom - no_h), fill="#ef3b2c")
        draw.text((x + bar_w // 2, bottom + 22), str(row["Stage"]), fill="#222222", font=_font(16), anchor="mm")
        draw.text((x + bar_w // 2, bottom - total_h - 18), str(int(row["Rows"])), fill="#222222", font=_font(14), anchor="mm")

    draw.rectangle((right - 220, top, right - 190, top + 20), fill="#9ecae1")
    draw.text((right - 180, top + 10), "NO", fill="#222222", font=_font(16), anchor="lm")
    draw.rectangle((right - 220, top + 35, right - 190, top + 55), fill="#ef3b2c")
    draw.text((right - 180, top + 45), "YES", fill="#222222", font=_font(16), anchor="lm")

    _save_pil(img, figures_dir, name)


def _draw_scatter(
    figures_dir: Path,
    name: str,
    title: str,
    x_values: list[float],
    y_values: list[float],
    labels: list[str],
    sizes: list[float],
    x_label: str,
    y_label: str,
) -> None:
    img, draw = _canvas()
    width, height = img.size
    _draw_title(draw, title, width)

    left = 140
    right = width - 80
    top = 120
    bottom = height - 100
    draw.line((left, bottom, right, bottom), fill="#555555", width=2)
    draw.line((left, top, left, bottom), fill="#555555", width=2)
    draw.text(((left + right) // 2, height - 40), x_label, fill="#222222", font=_font(18), anchor="mm")
    draw.text((60, (top + bottom) // 2), y_label, fill="#222222", font=_font(18), anchor="mm")

    xmax = max(x_values) if x_values else 1.0
    ymax = max(y_values) if y_values else 1.0
    for idx, (xv, yv, label, size) in enumerate(zip(x_values, y_values, labels, sizes)):
        x = left + int((xv / xmax) * (right - left - 20)) if xmax else left
        y = bottom - int((yv / ymax) * (bottom - top - 20)) if ymax else bottom
        radius = max(6, min(20, int(size)))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#41ab5d", outline="#225ea8")
        if idx < 12:
            draw.text((x + radius + 4, y), shorten(label, width=24, placeholder="..."), fill="#222222", font=_font(12), anchor="lm")

    _save_pil(img, figures_dir, name)


def plot_stage_comparison(metrics: MetricBundle, figures_dir: Path) -> None:
    df = metrics.stage_counts
    if plt is not None:
        fig, ax = plt.subplots(figsize=(11, 7))
        x = range(len(df))
        ax.bar(x, df["NO"], label="NO", color="#9ecae1")
        ax.bar(x, df["YES"], bottom=df["NO"], label="YES", color="#ef3b2c")
        ax.set_xticks(list(x))
        ax.set_xticklabels(df["Stage"])
        ax.set_ylabel("Rows")
        ax.set_title("Rows by Pipeline Stage: Violations vs Non-violations")
        ax.legend()
        for idx, row in df.iterrows():
            ax.text(idx, row["Rows"] + max(df["Rows"]) * 0.015, str(int(row["Rows"])), ha="center", fontsize=10)
        _save_matplotlib(figures_dir, "01_stage_comparison")
        return
    _draw_stacked_stage_chart(figures_dir, "01_stage_comparison", "Rows by Pipeline Stage: Violations vs Non-violations", df)


def plot_top_violation_pairs(metrics: MetricBundle, figures_dir: Path) -> None:
    df = metrics.pair_summary.head(12).copy()
    if plt is not None:
        fig, ax = plt.subplots(figsize=(13, 8))
        ax.barh(df["Pattern"], df["yes_rows"], color="#cb181d")
        ax.invert_yaxis()
        ax.set_title("Top API Pairs by Violations After Filtering")
        ax.set_xlabel("Violation rows")
        _save_matplotlib(figures_dir, "02_top_violation_pairs")
        return
    _draw_horizontal_bars(figures_dir, "02_top_violation_pairs", "Top API Pairs by Violations After Filtering", df["Pattern"].tolist(), df["yes_rows"].tolist(), "#cb181d", "Violation rows")


def plot_top_non_violation_pairs(metrics: MetricBundle, figures_dir: Path) -> None:
    df = metrics.non_violation_pairs.head(12).copy()
    if plt is not None:
        fig, ax = plt.subplots(figsize=(13, 8))
        ax.barh(df["Pattern"], df["no_rows"], color="#3182bd")
        ax.invert_yaxis()
        ax.set_title("Top API Pairs by Non-violations After Filtering")
        ax.set_xlabel("Non-violation rows")
        _save_matplotlib(figures_dir, "03_top_non_violation_pairs")
        return
    _draw_horizontal_bars(figures_dir, "03_top_non_violation_pairs", "Top API Pairs by Non-violations After Filtering", df["Pattern"].tolist(), df["no_rows"].tolist(), "#3182bd", "Non-violation rows")


def plot_top_systems(metrics: MetricBundle, figures_dir: Path) -> None:
    df = metrics.system_summary.head(12).copy()
    if plt is not None:
        fig, ax = plt.subplots(figsize=(13, 8))
        ax.barh(df["Project"], df["yes_rows"], color="#756bb1")
        ax.invert_yaxis()
        ax.set_title("Top Systems by Violations After Filtering")
        ax.set_xlabel("Violation rows")
        _save_matplotlib(figures_dir, "04_top_systems")
        return
    _draw_horizontal_bars(figures_dir, "04_top_systems", "Top Systems by Violations After Filtering", df["Project"].tolist(), df["yes_rows"].tolist(), "#756bb1", "Violation rows")


def plot_variability_breakdown(metrics: MetricBundle, figures_dir: Path) -> None:
    df = metrics.variability_summary.pivot(index="VarClass", columns="Violation", values="count").fillna(0)
    for col in ["NO", "YES"]:
        if col not in df.columns:
            df[col] = 0
    df = df.loc[[idx for idx in ["none", "partial", "total"] if idx in df.index]]
    if plt is not None:
        fig, ax = plt.subplots(figsize=(10, 7))
        x = range(len(df))
        ax.bar(x, df["NO"], label="NO", color="#9ecae1")
        ax.bar(x, df["YES"], bottom=df["NO"], label="YES", color="#ef3b2c")
        ax.set_xticks(list(x))
        ax.set_xticklabels(list(df.index))
        ax.set_ylabel("Rows")
        ax.set_title("Variability Class vs Result After Filtering")
        ax.legend()
        _save_matplotlib(figures_dir, "05_variability_breakdown")
        return
    stage_df = pd.DataFrame({"Stage": list(df.index), "NO": df["NO"].tolist(), "YES": df["YES"].tolist()})
    stage_df["Rows"] = stage_df["NO"] + stage_df["YES"]
    _draw_stacked_stage_chart(figures_dir, "05_variability_breakdown", "Variability Class vs Result After Filtering", stage_df)


def plot_fp_status(metrics: MetricBundle, figures_dir: Path) -> None:
    df = metrics.fp_summary.copy()
    if plt is not None:
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.bar(df["FPStatus"], df["count"], color=["#d95f02", "#1b9e77", "#7570b3"][: len(df)])
        ax.set_title("False-positive Analysis Status")
        ax.set_ylabel("Rows")
        for idx, row in df.iterrows():
            ax.text(idx, row["count"] + max(df["count"]) * 0.02, str(int(row["count"])), ha="center")
        _save_matplotlib(figures_dir, "06_fp_status")
        return
    _draw_horizontal_bars(figures_dir, "06_fp_status", "False-positive Analysis Status", df["FPStatus"].tolist(), df["count"].tolist(), "#d95f02", "Rows")


def plot_top_fp_contexts(metrics: MetricBundle, figures_dir: Path) -> None:
    df = metrics.fp_contexts.head(12).copy()
    if df.empty:
        return
    df["Context"] = df.apply(
        lambda r: shorten(f"{r['Project']} | {r['Caller']} | {r['PairKey']}", width=60, placeholder="..."),
        axis=1,
    )
    if plt is not None:
        fig, ax = plt.subplots(figsize=(13, 8))
        ax.barh(df["Context"], df["confirmed_false_positives"], color="#ff7f00")
        ax.invert_yaxis()
        ax.set_title("Contexts with the Most Confirmed False Positives")
        ax.set_xlabel("Confirmed false positives")
        _save_matplotlib(figures_dir, "07_top_fp_contexts")
        return
    _draw_horizontal_bars(figures_dir, "07_top_fp_contexts", "Contexts with the Most Confirmed False Positives", df["Context"].tolist(), df["confirmed_false_positives"].tolist(), "#ff7f00", "Confirmed false positives")


def plot_pattern_scatter(metrics: MetricBundle, figures_dir: Path) -> None:
    df = metrics.pattern_scatter.head(40).copy()
    if plt is not None:
        fig, ax = plt.subplots(figsize=(11, 8))
        ax.scatter(df["total_rows"], df["yes_rate"], s=df["projects"] * 30, alpha=0.7, color="#2ca25f")
        ax.set_title("Pattern Volume vs Violation Rate")
        ax.set_xlabel("Total rows")
        ax.set_ylabel("Violation rate")
        for _, row in df.head(12).iterrows():
            ax.annotate(shorten(str(row["label"]), width=28, placeholder="..."), (row["total_rows"], row["yes_rate"]), fontsize=8)
        _save_matplotlib(figures_dir, "08_pattern_volume_vs_rate")
        return
    _draw_scatter(
        figures_dir,
        "08_pattern_volume_vs_rate",
        "Pattern Volume vs Violation Rate",
        df["total_rows"].astype(float).tolist(),
        df["yes_rate"].astype(float).tolist(),
        df["label"].astype(str).tolist(),
        [max(6.0, float(v) * 3.0) for v in df["projects"].astype(float).tolist()],
        "Total rows",
        "Violation rate",
    )


def generate_all_plots(metrics: MetricBundle, figures_dir: Path) -> None:
    setup_style()
    plot_stage_comparison(metrics, figures_dir)
    plot_top_violation_pairs(metrics, figures_dir)
    plot_top_non_violation_pairs(metrics, figures_dir)
    plot_top_systems(metrics, figures_dir)
    plot_variability_breakdown(metrics, figures_dir)
    plot_fp_status(metrics, figures_dir)
    plot_top_fp_contexts(metrics, figures_dir)
    plot_pattern_scatter(metrics, figures_dir)
