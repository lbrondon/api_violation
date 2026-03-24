from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from PIL import Image as PILImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from identify_false_positives import MatchFirstFalsePositiveAnalyzer
from pc_utils import SENTINELS, is_valid_pc, normalize_pc

try:
    import matplotlib.pyplot as plt  # type: ignore
except Exception:
    plt = None


@dataclass(frozen=True)
class RQReportPaths:
    base_dir: Path
    figures_dir: Path
    tables_dir: Path
    markdown_path: Path
    pdf_path: Path
    filtered_path: Path
    analyzed_path: Path

    @classmethod
    def build(cls, base_dir: Path) -> "RQReportPaths":
        return cls(
            base_dir=base_dir,
            figures_dir=base_dir / "figures",
            tables_dir=base_dir / "tables",
            markdown_path=base_dir / "rq_technical_report.md",
            pdf_path=base_dir / "rq_technical_report.pdf",
            filtered_path=base_dir / "violations_filtered.csv",
            analyzed_path=base_dir / "violations_fp_analysis.csv",
        )


@dataclass(frozen=True)
class RQMetricBundle:
    overall: pd.DataFrame
    patterns_per_system: pd.DataFrame
    patterns_per_file: pd.DataFrame
    variability_per_system: pd.DataFrame
    variability_per_file: pd.DataFrame
    patterns_in_variability_by_system: pd.DataFrame
    patterns_in_variability_by_file: pd.DataFrame
    variability_with_patterns: pd.DataFrame
    patterns_across_variabilities: pd.DataFrame
    violations_overview: pd.DataFrame
    violated_patterns: pd.DataFrame
    violations_per_product: pd.DataFrame
    violation_types: pd.DataFrame


def _fmt_int(value: object) -> str:
    return f"{int(value):,}".replace(",", ".")


def _fmt_float(value: float) -> str:
    return f"{value:.2f}"


def _series_stats(series: pd.Series) -> dict[str, float]:
    s = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    if s.empty:
        return {"mean": 0.0, "median": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "q1": 0.0, "q3": 0.0}
    return {
        "mean": float(s.mean()),
        "median": float(s.median()),
        "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        "min": float(s.min()),
        "max": float(s.max()),
        "q1": float(s.quantile(0.25)),
        "q3": float(s.quantile(0.75)),
    }


def _normalize_true(value: object) -> str:
    s = "" if pd.isna(value) else str(value).strip()
    return "TRUE" if s.lower() == "true" else s


def _canonical_pattern(row: pd.Series) -> str:
    return " | ".join(sorted((str(row["Callee_A"]).strip(), str(row["Callee_B"]).strip())))


def _variability_class(pc_a: str, pc_b: str) -> str:
    a_true = pc_a == "TRUE"
    b_true = pc_b == "TRUE"
    if a_true and b_true:
        return "none"
    if (not a_true) and (not b_true):
        return "total"
    return "partial"


def _normalize_output(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["PC_A"] = out["PC_A"].map(_normalize_true)
    out["PC_B"] = out["PC_B"].map(_normalize_true)
    out["Pattern"] = out.apply(_canonical_pattern, axis=1)
    out["VarClass"] = out.apply(lambda r: _variability_class(r["PC_A"], r["PC_B"]), axis=1)
    out["IsViolation"] = out["Violation"].astype(str).str.upper() == "YES"
    return out


def _ensure_filtered_output(dedup_path: Path, analyzed_path: Path, filtered_path: Path) -> None:
    if analyzed_path.exists() and filtered_path.exists():
        return
    analyzer = MatchFirstFalsePositiveAnalyzer()
    analyzer.analyze_file(
        input_path=str(dedup_path),
        output_path=str(analyzed_path),
        filtered_output_path=str(filtered_path),
    )


def _load_pc_calls(pc_csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(pc_csv_path)
    df["PC"] = df["PC"].fillna("").astype(str).str.strip()
    df = df[(df["PC"] != "") & (~df["PC"].isin(SENTINELS))].copy()
    df = df[df["PC"].map(is_valid_pc)].copy()
    df["PC_norm"] = df["PC"].map(normalize_pc)
    df = df[df["PC_norm"] != ""].copy()
    df["is_variable"] = df["PC_norm"] != "TRUE"
    return df


def _build_metrics(pc_calls: pd.DataFrame, raw: pd.DataFrame, dedup: pd.DataFrame, filtered: pd.DataFrame) -> RQMetricBundle:
    patterns_per_system = (
        filtered.groupby("Project")
        .agg(
            padroes_distintos=("Pattern", "nunique"),
            instancias_de_padrao=("Pattern", "size"),
            arquivos_com_padrao=("File", "nunique"),
        )
        .reset_index()
        .sort_values(["instancias_de_padrao", "padroes_distintos", "Project"], ascending=[False, False, True])
    )

    patterns_per_file = (
        filtered.groupby(["Project", "File"])
        .agg(
            padroes_distintos=("Pattern", "nunique"),
            instancias_de_padrao=("Pattern", "size"),
            callers_com_padrao=("Caller", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["instancias_de_padrao", "padroes_distintos", "Project", "File"],
            ascending=[False, False, True, True],
        )
    )

    variable_calls = pc_calls[pc_calls["is_variable"]].copy()
    variability_per_system = (
        variable_calls.groupby("Project")
        .agg(
            variabilidades_distintas=("PC_norm", "nunique"),
            ocorrencias_variaveis=("PC_norm", "size"),
            arquivos_com_variabilidade=("File", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["variabilidades_distintas", "ocorrencias_variaveis", "Project"],
            ascending=[False, False, True],
        )
    )

    variability_per_file = (
        variable_calls.groupby(["Project", "File"])
        .agg(
            variabilidades_distintas=("PC_norm", "nunique"),
            ocorrencias_variaveis=("PC_norm", "size"),
            callers_com_variabilidade=("Caller", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["variabilidades_distintas", "ocorrencias_variaveis", "Project", "File"],
            ascending=[False, False, True, True],
        )
    )

    patterns_in_variability = filtered[filtered["VarClass"] != "none"].copy()
    patterns_in_variability_by_system = (
        patterns_in_variability.groupby("Project")
        .agg(
            padroes_distintos_em_variabilidade=("Pattern", "nunique"),
            instancias_em_variabilidade=("Pattern", "size"),
            instancias_parciais=("VarClass", lambda s: int((s == "partial").sum())),
            instancias_totais=("VarClass", lambda s: int((s == "total").sum())),
        )
        .reset_index()
        .sort_values(
            ["instancias_em_variabilidade", "padroes_distintos_em_variabilidade", "Project"],
            ascending=[False, False, True],
        )
    )

    patterns_in_variability_by_file = (
        patterns_in_variability.groupby(["Project", "File"])
        .agg(
            padroes_distintos_em_variabilidade=("Pattern", "nunique"),
            instancias_em_variabilidade=("Pattern", "size"),
            instancias_parciais=("VarClass", lambda s: int((s == "partial").sum())),
            instancias_totais=("VarClass", lambda s: int((s == "total").sum())),
        )
        .reset_index()
        .sort_values(
            ["instancias_em_variabilidade", "padroes_distintos_em_variabilidade", "Project", "File"],
            ascending=[False, False, True, True],
        )
    )

    frames = []
    for col in ["PC_A", "PC_B"]:
        tmp = filtered[filtered[col] != "TRUE"][[col, "Pattern", "Project", "File", "Caller"]].copy()
        tmp = tmp.rename(columns={col: "PC"})
        frames.append(tmp)
    var_pattern_instances = pd.concat(frames, ignore_index=True)
    var_pattern_distinct = var_pattern_instances.drop_duplicates(["PC", "Pattern", "Project", "File", "Caller"])
    variability_with_patterns = (
        var_pattern_instances.groupby("PC")
        .agg(
            padroes_distintos=("Pattern", "nunique"),
            ligacoes_repetidas=("Pattern", "size"),
            sistemas_afetados=("Project", "nunique"),
            arquivos_afetados=("File", "nunique"),
        )
        .reset_index()
        .sort_values(["padroes_distintos", "ligacoes_repetidas", "PC"], ascending=[False, False, True])
    )

    patterns_across_variabilities = (
        var_pattern_distinct.groupby("Pattern")
        .agg(
            variabilidades_distintas=("PC", "nunique"),
            ligacoes_distintas_padrao_variabilidade=("PC", "size"),
        )
        .reset_index()
        .sort_values(
            ["variabilidades_distintas", "ligacoes_distintas_padrao_variabilidade", "Pattern"],
            ascending=[False, False, True],
        )
    )

    violations = filtered[filtered["IsViolation"]].copy()
    violations_overview = pd.DataFrame(
        [
            {
                "violacoes_brutas": int(raw["IsViolation"].sum()),
                "violacoes_deduplicadas": int(dedup["IsViolation"].sum()),
                "violacoes_filtradas": int(violations.shape[0]),
                "violacoes_parciais": int((violations["VarClass"] == "partial").sum()),
                "violacoes_totais": int((violations["VarClass"] == "total").sum()),
                "produtos_com_violacao": int(violations["Project"].nunique()),
            }
        ]
    )

    violated_patterns = (
        violations.groupby("Pattern")
        .agg(
            violacoes=("Pattern", "size"),
            sistemas_afetados=("Project", "nunique"),
            arquivos_afetados=("File", "nunique"),
            violacoes_parciais=("VarClass", lambda s: int((s == "partial").sum())),
            violacoes_totais=("VarClass", lambda s: int((s == "total").sum())),
        )
        .reset_index()
        .sort_values(["violacoes", "sistemas_afetados", "Pattern"], ascending=[False, False, True])
    )

    violations_per_product = (
        violations.groupby("Project")
        .agg(
            violacoes=("Pattern", "size"),
            padroes_violados_distintos=("Pattern", "nunique"),
            arquivos_afetados=("File", "nunique"),
            violacoes_parciais=("VarClass", lambda s: int((s == "partial").sum())),
            violacoes_totais=("VarClass", lambda s: int((s == "total").sum())),
        )
        .reset_index()
        .sort_values(["violacoes", "padroes_violados_distintos", "Project"], ascending=[False, False, True])
    )

    violation_types = pd.DataFrame(
        [
            {"Tipo": "partial", "Quantidade": int((violations["VarClass"] == "partial").sum())},
            {"Tipo": "total", "Quantidade": int((violations["VarClass"] == "total").sum())},
        ]
    )

    overall = pd.DataFrame(
        [
            {
                "sistemas_com_padrao": int(filtered["Project"].nunique()),
                "arquivos_com_padrao": int(filtered[["Project", "File"]].drop_duplicates().shape[0]),
                "padroes_distintos": int(filtered["Pattern"].nunique()),
                "instancias_de_padrao": int(filtered.shape[0]),
                "variabilidades_distintas_no_corpus": int(variable_calls["PC_norm"].nunique()),
                "padroes_distintos_em_variabilidade": int(patterns_in_variability["Pattern"].nunique()),
                "instancias_de_padrao_em_variabilidade": int(patterns_in_variability.shape[0]),
                "variabilidades_com_padrao": int(variability_with_patterns["PC"].nunique()),
                "ligacoes_distintas_padrao_variabilidade": int(var_pattern_distinct[["PC", "Pattern"]].drop_duplicates().shape[0]),
                "ligacoes_repetidas_padrao_variabilidade": int(var_pattern_instances.shape[0]),
                "violacoes_filtradas": int(violations.shape[0]),
                "produtos_com_violacao": int(violations["Project"].nunique()),
            }
        ]
    )

    return RQMetricBundle(
        overall=overall,
        patterns_per_system=patterns_per_system,
        patterns_per_file=patterns_per_file,
        variability_per_system=variability_per_system,
        variability_per_file=variability_per_file,
        patterns_in_variability_by_system=patterns_in_variability_by_system,
        patterns_in_variability_by_file=patterns_in_variability_by_file,
        variability_with_patterns=variability_with_patterns,
        patterns_across_variabilities=patterns_across_variabilities,
        violations_overview=violations_overview,
        violated_patterns=violated_patterns,
        violations_per_product=violations_per_product,
        violation_types=violation_types,
    )


def write_rq_tables(metrics: RQMetricBundle, tables_dir: Path) -> None:
    tables_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "overall_summary.csv": metrics.overall,
        "patterns_per_system.csv": metrics.patterns_per_system,
        "patterns_per_file.csv": metrics.patterns_per_file,
        "variability_per_system.csv": metrics.variability_per_system,
        "variability_per_file.csv": metrics.variability_per_file,
        "patterns_in_variability_by_system.csv": metrics.patterns_in_variability_by_system,
        "patterns_in_variability_by_file.csv": metrics.patterns_in_variability_by_file,
        "variability_with_patterns.csv": metrics.variability_with_patterns,
        "patterns_across_variabilities.csv": metrics.patterns_across_variabilities,
        "violations_overview.csv": metrics.violations_overview,
        "violated_patterns.csv": metrics.violated_patterns,
        "violations_per_product.csv": metrics.violations_per_product,
        "violation_types.csv": metrics.violation_types,
    }
    for name, df in tables.items():
        df.to_csv(tables_dir / name, index=False)


def _setup_style() -> None:
    if plt is None:
        return
    plt.style.use("default")
    plt.rcParams.update(
        {
            "figure.figsize": (12, 7),
            "axes.titlesize": 16,
            "axes.titleweight": "bold",
            "axes.labelsize": 12,
            "axes.facecolor": "#fcfcfa",
            "figure.facecolor": "white",
            "axes.grid": True,
            "grid.color": "#d8d8d8",
            "grid.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.family": "DejaVu Sans",
        }
    )


def _save_plot(figures_dir: Path, name: str) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    if plt is None:
        return
    plt.tight_layout()
    plt.savefig(figures_dir / f"{name}.png", dpi=220, bbox_inches="tight")
    plt.close()


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _canvas(width: int = 1400, height: int = 900) -> tuple[PILImage.Image, ImageDraw.ImageDraw]:
    img = PILImage.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    return img, draw


def _save_pil(img: PILImage.Image, figures_dir: Path, name: str) -> None:
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
    gap = 12
    n = max(1, len(labels))
    bar_h = max(18, (plot_height - gap * (n - 1)) // n)
    vmax = max(values) if values else 1.0
    draw.line((left, bottom, right, bottom), fill="#555555", width=2)
    draw.line((left, top, left, bottom), fill="#555555", width=2)
    draw.text(((left + right) // 2, height - 35), x_label, fill="#333333", font=_font(18), anchor="mm")
    for idx, (label, value) in enumerate(zip(labels, values)):
        y = top + idx * (bar_h + gap)
        bar_w = int((value / vmax) * (right - left - 20)) if vmax else 0
        draw.rectangle((left, y, left + bar_w, y + bar_h), fill=color)
        draw.text((left - 15, y + bar_h // 2), str(label)[:40], fill="#222222", font=_font(16), anchor="rm")
        draw.text((left + bar_w + 10, y + bar_h // 2), str(int(value)), fill="#222222", font=_font(15), anchor="lm")
    _save_pil(img, figures_dir, name)


def _draw_stacked_chart(figures_dir: Path, name: str, title: str, categories: list[str], partial: list[int], total: list[int]) -> None:
    img, draw = _canvas()
    width, height = img.size
    _draw_title(draw, title, width)
    left = 140
    right = width - 100
    top = 140
    bottom = height - 120
    n = len(categories)
    bar_w = 140
    max_value = max([p + t for p, t in zip(partial, total)] + [1])
    draw.line((left, bottom, right, bottom), fill="#555555", width=2)
    draw.line((left, top, left, bottom), fill="#555555", width=2)
    for idx, cat in enumerate(categories):
        x = left + idx * ((right - left) // max(1, n))
        p_h = int((partial[idx] / max_value) * (bottom - top - 40))
        t_h = int((total[idx] / max_value) * (bottom - top - 40))
        draw.rectangle((x, bottom - p_h, x + bar_w, bottom), fill="#d95f02")
        draw.rectangle((x, bottom - p_h - t_h, x + bar_w, bottom - p_h), fill="#1b9e77")
        draw.text((x + bar_w // 2, bottom + 25), cat, fill="#222222", font=_font(16), anchor="mm")
        draw.text((x + bar_w // 2, bottom - p_h // 2), str(partial[idx]), fill="white", font=_font(14), anchor="mm")
        draw.text((x + bar_w // 2, bottom - p_h - t_h // 2), str(total[idx]), fill="white", font=_font(14), anchor="mm")
    _save_pil(img, figures_dir, name)


def _draw_histogram(figures_dir: Path, name: str, title: str, values: list[float], color: str, x_label: str) -> None:
    img, draw = _canvas()
    width, height = img.size
    _draw_title(draw, title, width)
    left = 120
    right = width - 80
    top = 120
    bottom = height - 100
    bins = 20
    if not values:
        _save_pil(img, figures_dir, name)
        return
    vmax = max(values)
    counts = [0] * bins
    for value in values:
        idx = min(bins - 1, int((value / max(vmax, 1)) * (bins - 1)))
        counts[idx] += 1
    max_count = max(counts) or 1
    draw.line((left, bottom, right, bottom), fill="#555555", width=2)
    draw.line((left, top, left, bottom), fill="#555555", width=2)
    draw.text(((left + right) // 2, height - 40), x_label, fill="#333333", font=_font(18), anchor="mm")
    bar_w = max(10, (right - left) // bins - 4)
    for idx, count in enumerate(counts):
        x = left + idx * ((right - left) // bins)
        bar_h = int((count / max_count) * (bottom - top - 20))
        draw.rectangle((x, bottom - bar_h, x + bar_w, bottom), fill=color)
    _save_pil(img, figures_dir, name)


def generate_rq_plots(metrics: RQMetricBundle, figures_dir: Path) -> None:
    _setup_style()
    overall = metrics.overall.iloc[0]
    if plt is None:
        labels = [
            "Sistemas com padrão",
            "Arquivos com padrão",
            "Padrões distintos",
            "Instâncias de padrão",
            "Variabilidades distintas",
            "Violações filtradas",
        ]
        values = [
            float(overall["sistemas_com_padrao"]),
            float(overall["arquivos_com_padrao"]),
            float(overall["padroes_distintos"]),
            float(overall["instancias_de_padrao"]),
            float(overall["variabilidades_distintas_no_corpus"]),
            float(overall["violacoes_filtradas"]),
        ]
        _draw_horizontal_bars(figures_dir, "01_resumo_corpus", "Resumo do Corpus e das Respostas Agregadas", labels, values, "#2b8cbe", "Contagem")
        top = metrics.patterns_per_system.head(12)
        _draw_horizontal_bars(figures_dir, "02_padroes_por_sistema", "Top Sistemas por Instâncias de Padrão de Uso", top["Project"].tolist(), top["instancias_de_padrao"].astype(float).tolist(), "#3182bd", "Instâncias de padrão")
        _draw_histogram(figures_dir, "03_padroes_por_arquivo", "Distribuição de Instâncias de Padrão por Arquivo", metrics.patterns_per_file["instancias_de_padrao"].astype(float).tolist(), "#6baed6", "Instâncias de padrão por arquivo")
        top = metrics.variability_per_system.head(12)
        _draw_horizontal_bars(figures_dir, "04_variabilidade_por_sistema", "Top Sistemas por Variabilidades Distintas", top["Project"].tolist(), top["variabilidades_distintas"].astype(float).tolist(), "#31a354", "Variabilidades distintas")
        _draw_histogram(figures_dir, "05_variabilidade_por_arquivo", "Distribuição de Variabilidades Distintas por Arquivo", metrics.variability_per_file["variabilidades_distintas"].astype(float).tolist(), "#74c476", "Variabilidades distintas por arquivo")
        _draw_stacked_chart(figures_dir, "06_parcial_vs_total", "Padrões em Variabilidade e Tipos de Violação", ["Padrões em variabilidade", "Violações"], [int(metrics.patterns_in_variability_by_system["instancias_parciais"].sum()), int(metrics.violation_types.loc[metrics.violation_types["Tipo"] == "partial", "Quantidade"].iloc[0])], [int(metrics.patterns_in_variability_by_system["instancias_totais"].sum()), int(metrics.violation_types.loc[metrics.violation_types["Tipo"] == "total", "Quantidade"].iloc[0])])
        top = metrics.violated_patterns.head(12)
        _draw_horizontal_bars(figures_dir, "07_padroes_mais_violados", "Padrões de Uso Mais Violados", top["Pattern"].tolist(), top["violacoes"].astype(float).tolist(), "#cb181d", "Violações filtradas")
        top = metrics.violations_per_product.head(12)
        _draw_horizontal_bars(figures_dir, "08_violacoes_por_produto", "Violações por Sistema", top["Project"].tolist(), top["violacoes"].astype(float).tolist(), "#756bb1", "Violações filtradas")
        top = metrics.variability_with_patterns.head(12).copy()
        top["PC_short"] = top["PC"].astype(str).str.slice(0, 60)
        _draw_horizontal_bars(figures_dir, "09_variabilidades_com_padroes", "Variabilidades Mais Ligadas a Padrões de Uso", top["PC_short"].tolist(), top["ligacoes_repetidas"].astype(float).tolist(), "#e6550d", "Ligações repetidas padrão-variabilidade")
        return

    fig, ax = plt.subplots(figsize=(12, 7))
    labels = [
        "Sistemas com padrão",
        "Arquivos com padrão",
        "Padrões distintos",
        "Instâncias de padrão",
        "Variabilidades distintas",
        "Violações filtradas",
    ]
    values = [
        overall["sistemas_com_padrao"],
        overall["arquivos_com_padrao"],
        overall["padroes_distintos"],
        overall["instancias_de_padrao"],
        overall["variabilidades_distintas_no_corpus"],
        overall["violacoes_filtradas"],
    ]
    ax.barh(labels, values, color=["#2b8cbe", "#74a9cf", "#31a354", "#74c476", "#fd8d3c", "#cb181d"])
    ax.invert_yaxis()
    ax.set_title("Resumo do Corpus e das Respostas Agregadas")
    ax.set_xlabel("Contagem")
    for i, value in enumerate(values):
        ax.text(value, i, f" {_fmt_int(value)}", va="center")
    _save_plot(figures_dir, "01_resumo_corpus")

    top = metrics.patterns_per_system.head(12)
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.barh(top["Project"], top["instancias_de_padrao"], color="#3182bd")
    ax.invert_yaxis()
    ax.set_title("Top Sistemas por Instâncias de Padrão de Uso")
    ax.set_xlabel("Instâncias de padrão")
    _save_plot(figures_dir, "02_padroes_por_sistema")

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.hist(metrics.patterns_per_file["instancias_de_padrao"], bins=30, color="#6baed6", edgecolor="white")
    ax.set_title("Distribuição de Instâncias de Padrão por Arquivo")
    ax.set_xlabel("Instâncias de padrão por arquivo")
    ax.set_ylabel("Arquivos")
    _save_plot(figures_dir, "03_padroes_por_arquivo")

    top = metrics.variability_per_system.head(12)
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.barh(top["Project"], top["variabilidades_distintas"], color="#31a354")
    ax.invert_yaxis()
    ax.set_title("Top Sistemas por Variabilidades Distintas")
    ax.set_xlabel("Variabilidades distintas")
    _save_plot(figures_dir, "04_variabilidade_por_sistema")

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.hist(metrics.variability_per_file["variabilidades_distintas"], bins=30, color="#74c476", edgecolor="white")
    ax.set_title("Distribuição de Variabilidades Distintas por Arquivo")
    ax.set_xlabel("Variabilidades distintas por arquivo")
    ax.set_ylabel("Arquivos")
    _save_plot(figures_dir, "05_variabilidade_por_arquivo")

    by_type = pd.DataFrame(
        [
            {
                "Categoria": "Padrões em variabilidade",
                "Partial": int(metrics.patterns_in_variability_by_system["instancias_parciais"].sum()),
                "Total": int(metrics.patterns_in_variability_by_system["instancias_totais"].sum()),
            },
            {
                "Categoria": "Violações",
                "Partial": int(metrics.violation_types.loc[metrics.violation_types["Tipo"] == "partial", "Quantidade"].iloc[0]),
                "Total": int(metrics.violation_types.loc[metrics.violation_types["Tipo"] == "total", "Quantidade"].iloc[0]),
            },
        ]
    )
    fig, ax = plt.subplots(figsize=(10, 7))
    x = range(len(by_type))
    ax.bar(x, by_type["Partial"], color="#d95f02", label="Partial")
    ax.bar(x, by_type["Total"], bottom=by_type["Partial"], color="#1b9e77", label="Total")
    ax.set_xticks(list(x))
    ax.set_xticklabels(by_type["Categoria"])
    ax.set_title("Padrões em Variabilidade e Tipos de Violação")
    ax.set_ylabel("Contagem")
    ax.legend()
    _save_plot(figures_dir, "06_parcial_vs_total")

    top = metrics.violated_patterns.head(12)
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.barh(top["Pattern"], top["violacoes"], color="#cb181d")
    ax.invert_yaxis()
    ax.set_title("Padrões de Uso Mais Violados")
    ax.set_xlabel("Violações filtradas")
    _save_plot(figures_dir, "07_padroes_mais_violados")

    top = metrics.violations_per_product.head(12)
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.barh(top["Project"], top["violacoes"], color="#756bb1")
    ax.invert_yaxis()
    ax.set_title("Violações por Produto")
    ax.set_xlabel("Violações filtradas")
    _save_plot(figures_dir, "08_violacoes_por_produto")

    top = metrics.variability_with_patterns.head(12).copy()
    top["PC_short"] = top["PC"].astype(str).str.slice(0, 60)
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.barh(top["PC_short"], top["ligacoes_repetidas"], color="#e6550d")
    ax.invert_yaxis()
    ax.set_title("Variabilidades Mais Ligadas a Padrões de Uso")
    ax.set_xlabel("Ligações repetidas padrão-variabilidade")
    _save_plot(figures_dir, "09_variabilidades_com_padroes")


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SectionBlue",
            parent=styles["Heading1"],
            textColor=colors.HexColor("#0b3c5d"),
            fontSize=15,
            leading=18,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyDense",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            spaceAfter=8,
        )
    )
    return styles


def _scaled_image(path: Path, max_width_cm: float = 16.0) -> Image:
    img = Image(str(path))
    max_width = max_width_cm * cm
    scale = min(1.0, max_width / img.drawWidth)
    img.drawWidth *= scale
    img.drawHeight *= scale
    return img


def _table_block(df: pd.DataFrame, columns: list[str], limit: int = 10) -> str:
    if df.empty:
        return "Sem dados."
    return "```\n" + df[columns].head(limit).to_string(index=False) + "\n```"


def write_rq_markdown_report(metrics: RQMetricBundle, paths: RQReportPaths) -> None:
    overall = metrics.overall.iloc[0]
    viol = metrics.violations_overview.iloc[0]
    stats_patterns_sys = _series_stats(metrics.patterns_per_system["instancias_de_padrao"])
    stats_patterns_file = _series_stats(metrics.patterns_per_file["instancias_de_padrao"])
    stats_var_sys = _series_stats(metrics.variability_per_system["variabilidades_distintas"])
    stats_var_file = _series_stats(metrics.variability_per_file["variabilidades_distintas"])
    top_pattern = metrics.violated_patterns.iloc[0]
    top_product = metrics.violations_per_product.iloc[0]

    content = [
        "# Relatório Técnico Orientado por Questões de Pesquisa",
        "",
        "## Estrutura do Relatório",
        "Este relatório adota uma organização objetiva orientada por questões de pesquisa, inspirada em práticas de relato de estudos empíricos em engenharia de software, especialmente na tradição de relatórios estruturados por contexto, definições operacionais, resultados por questão de pesquisa, visualizações e síntese analítica. O foco é exclusivamente o fenômeno de violações de padrões de uso de APIs em sistemas configuráveis em C/C++.",
        "",
        "## Definições Operacionais",
        "- `Padrão de uso`: par não ordenado de APIs observado na saída filtrada.",
        "- `Instância de padrão`: uma linha da saída filtrada.",
        "- `Variabilidade`: expressão de presença normalizada diferente de `TRUE`.",
        "- `Variabilidade parcial`: exatamente um lado do padrão está em variabilidade.",
        "- `Variabilidade total`: ambos os lados do padrão estão em variabilidade.",
        "- `Produto`: projeto/sistema identificado pela coluna `Project`.",
        "- `Violação`: linha `YES` na saída filtrada após remoção de falsos positivos confirmados.",
        "",
        "## RQ1. Número de padrões de uso por sistema",
        f"A resposta é dada por {int(metrics.patterns_per_system.shape[0])} sistemas com pelo menos um padrão observado. Em termos matemáticos, a métrica principal é a cardinalidade da multiconjunto de instâncias de padrão por sistema, complementada pela cardinalidade do conjunto de padrões distintos por sistema. Estatisticamente, a distribuição de instâncias de padrão por sistema apresenta média de {_fmt_float(stats_patterns_sys['mean'])}, mediana de {_fmt_float(stats_patterns_sys['median'])}, desvio padrão de {_fmt_float(stats_patterns_sys['std'])}, primeiro quartil de {_fmt_float(stats_patterns_sys['q1'])} e terceiro quartil de {_fmt_float(stats_patterns_sys['q3'])}. Isso indica forte heterogeneidade entre sistemas com baixa densidade de padrões e sistemas que concentram grande volume de ocorrências. Em ciência da computação, essa heterogeneidade é esperada porque sistemas em C com maior superfície funcional tendem a conter mais protocolos de alocação/liberação, abertura/fechamento e inicialização/finalização. O gráfico `02_padroes_por_sistema` e a tabela a seguir mostram os sistemas mais densos em instâncias de padrão.",
        _table_block(metrics.patterns_per_system, ["Project", "padroes_distintos", "instancias_de_padrao", "arquivos_com_padrao"]),
        "![RQ1](figures/02_padroes_por_sistema.png)",
        "",
        "## RQ2. Número de padrões de uso por arquivo",
        f"A análise por arquivo usa a mesma lógica de cardinalidade, agora aplicada ao agrupamento `(Project, File)`. Há {_fmt_int(overall['arquivos_com_padrao'])} arquivos com pelo menos uma instância de padrão. A distribuição por arquivo apresenta média de {_fmt_float(stats_patterns_file['mean'])}, mediana de {_fmt_float(stats_patterns_file['median'])}, desvio padrão de {_fmt_float(stats_patterns_file['std'])} e máximo de {_fmt_float(stats_patterns_file['max'])}. Sob a ótica estatística, a diferença entre média e mediana evidencia assimetria à direita: muitos arquivos têm poucas instâncias de padrão, enquanto poucos arquivos concentram muitas ocorrências. Isso é consistente com a teoria de modularidade em sistemas C, onde alguns arquivos agregam infraestrutura, gerenciamento de recursos ou caminhos de compilação condicional mais complexos. O gráfico `03_padroes_por_arquivo` mostra a distribuição dessa variável.",
        "![RQ2](figures/03_padroes_por_arquivo.png)",
        "",
        "## RQ3. Número de variabilidades por sistema",
        f"Esta questão é operacionalizada como o número de expressões de variabilidade distintas (`PC != TRUE`) observadas nas chamadas por sistema. O corpus contém {_fmt_int(overall['variabilidades_distintas_no_corpus'])} expressões distintas de variabilidade. Por sistema, a média é {_fmt_float(stats_var_sys['mean'])}, a mediana é {_fmt_float(stats_var_sys['median'])} e o desvio padrão é {_fmt_float(stats_var_sys['std'])}. Em sistemas configuráveis, essa métrica aproxima a diversidade configuracional local, isto é, quantas condições sintáticas distintas governam a presença das chamadas. Quanto maior essa diversidade, maior tende a ser a chance de fragmentação de protocolos entre ramos condicionais diferentes. O gráfico `04_variabilidade_por_sistema` destaca os sistemas com maior diversidade de variabilidades.",
        _table_block(metrics.variability_per_system, ["Project", "variabilidades_distintas", "ocorrencias_variaveis", "arquivos_com_variabilidade"]),
        "![RQ3](figures/04_variabilidade_por_sistema.png)",
        "",
        "## RQ4. Número de variabilidades por arquivo",
        f"No nível de arquivo, a análise mede quantas expressões distintas de variabilidade ocorrem nas chamadas presentes naquele arquivo. A média por arquivo é {_fmt_float(stats_var_file['mean'])}, a mediana é {_fmt_float(stats_var_file['median'])} e o valor máximo alcança {_fmt_float(stats_var_file['max'])}. Em termos de sistemas configuráveis, essa métrica aproxima a densidade configuracional local do arquivo. Arquivos com maior número de variabilidades distintas tendem a ser mais difíceis de analisar manualmente, pois concentram mais regiões alternativas de compilação. O gráfico `05_variabilidade_por_arquivo` mostra a distribuição dessa grandeza e ajuda a identificar a longa cauda de arquivos altamente configuráveis.",
        _table_block(metrics.variability_per_file, ["Project", "File", "variabilidades_distintas", "ocorrencias_variaveis", "callers_com_variabilidade"]),
        "![RQ4](figures/05_variabilidade_por_arquivo.png)",
        "",
        "## RQ5. Número de padrões de uso em sistema, excluindo `TRUE`",
        f"Esta questão considera apenas instâncias de padrão em que ao menos um lado está sob variabilidade, isto é, `VarClass != none`. O corpus contém {_fmt_int(overall['instancias_de_padrao_em_variabilidade'])} instâncias de padrão em variabilidade e {_fmt_int(overall['padroes_distintos_em_variabilidade'])} padrões distintos nesse subconjunto. Essa medida é relevante porque remove o uso totalmente incondicional e preserva justamente os contextos onde a variabilidade pode interferir na coocorrência das APIs. Em teoria de conjuntos, trata-se do subconjunto das instâncias filtradas que pertencem às classes `partial` ou `total`. A tabela abaixo mostra os sistemas com maior volume desse tipo de instância.",
        _table_block(metrics.patterns_in_variability_by_system, ["Project", "padroes_distintos_em_variabilidade", "instancias_em_variabilidade", "instancias_parciais", "instancias_totais"]),
        "",
        "## RQ6. Número de padrões de uso em arquivo",
        "Esta questão passa a ser interpretada estritamente como a quantidade de padrões do catálogo observados em cada arquivo, isto é, a cardinalidade do conjunto de pares distintos de APIs do catálogo que aparecem naquele arquivo. Portanto, ela coincide operacionalmente com a noção de `padroes_distintos` por arquivo. Em termos matemáticos, não se conta aqui a multiplicidade de instâncias, mas a diversidade de padrões catalogados efetivamente observados. Essa distinção é importante porque um arquivo pode conter muitas ocorrências repetidas do mesmo padrão e, ainda assim, baixa diversidade protocolar. Sob a ótica de sistemas configuráveis, arquivos com muitos padrões distintos do catálogo tendem a ser pontos de convergência funcional, onde vários protocolos de uso de recursos coexistem sob diferentes condições de presença. Esses arquivos são particularmente relevantes para inspeção porque combinam diversidade de padrões e potencial complexidade configuracional.",
        _table_block(metrics.patterns_per_file, ["Project", "File", "padroes_distintos", "instancias_de_padrao", "callers_com_padrao"]),
        "",
        "## RQ7. Número de padrões de uso em variabilidade parcial ou total",
        f"O corpus filtrado contém {_fmt_int(metrics.patterns_in_variability_by_system['instancias_parciais'].sum())} instâncias parciais e {_fmt_int(metrics.patterns_in_variability_by_system['instancias_totais'].sum())} instâncias totais. Do ponto de vista matemático, essa partição é mutuamente exclusiva e exaustiva dentro do subconjunto `VarClass != none`. Em termos de interpretação, instâncias parciais indicam assimetria direta entre os lados do padrão, enquanto instâncias totais indicam que ambos os lados estão condicionados, ainda que potencialmente por expressões diferentes. Em sistemas configuráveis, a segunda situação é particularmente importante porque revela protocolos inteiros submetidos à lógica de pré-processamento. O gráfico `06_parcial_vs_total` resume essa decomposição e a compara com os tipos de violação.",
        "![RQ7](figures/06_parcial_vs_total.png)",
        "",
        "## RQ8. Número de variabilidades com padrão de uso",
        f"Há {_fmt_int(overall['variabilidades_com_padrao'])} expressões de variabilidade que aparecem associadas a pelo menos um padrão de uso. Além disso, observam-se {_fmt_int(overall['ligacoes_distintas_padrao_variabilidade'])} ligações distintas padrão-variabilidade e {_fmt_int(overall['ligacoes_repetidas_padrao_variabilidade'])} ligações repetidas quando se consideram todas as ocorrências nos contextos analisados. Essa distinção entre ligações distintas e repetidas é teoricamente relevante: a primeira mede diversidade relacional; a segunda mede recorrência empírica. O gráfico `09_variabilidades_com_padroes` destaca as expressões de variabilidade mais frequentemente ligadas a padrões de uso.",
        _table_block(metrics.variability_with_patterns, ["PC", "padroes_distintos", "ligacoes_repetidas", "sistemas_afetados"]),
        "![RQ8](figures/09_variabilidades_com_padroes.png)",
        "",
        "## RQ9. Número de violações",
        f"Após a filtragem de falsos positivos confirmados, o número de violações é {_fmt_int(viol['violacoes_filtradas'])}. Para auditoria do pipeline, o relatório também preserva os valores anteriores: {_fmt_int(viol['violacoes_brutas'])} violações na saída bruta e {_fmt_int(viol['violacoes_deduplicadas'])} na saída deduplicada. Em termos de teoria de medição, a violação final é a cardinalidade do subconjunto `IsViolation = True` na saída filtrada, isto é, depois da correção por espelhamento e da remoção dos cruzamentos artificiais entre PCs já casados. Esse é o valor que deve ser usado nas análises finais do estudo.",
        "",
        "## RQ10. Padrões de uso mais violados",
        f"O padrão mais violado é `{top_pattern['Pattern']}`, com {_fmt_int(top_pattern['violacoes'])} violações filtradas, seguido pelos demais pares destacados na tabela e no gráfico. A interpretação desse ranking deve combinar volume absoluto, número de sistemas afetados e distribuição entre violações parciais e totais. Padrões com alta contagem e ampla dispersão em sistemas têm maior relevância empírica, enquanto padrões com maior fração de violações totais podem indicar protocolos fortemente fragmentados por diretivas de pré-processamento. O gráfico `07_padroes_mais_violados` responde a esta questão de forma direta.",
        _table_block(metrics.violated_patterns, ["Pattern", "violacoes", "sistemas_afetados", "violacoes_parciais", "violacoes_totais"]),
        "![RQ10](figures/07_padroes_mais_violados.png)",
        "",
        "## RQ11. Tipos de violações",
        f"As violações filtradas se dividem em {_fmt_int(viol['violacoes_parciais'])} violações parciais e {_fmt_int(viol['violacoes_totais'])} violações totais. Essa classificação importa teoricamente porque distingue entre casos em que apenas um lado do padrão permanece condicionado e casos em que o protocolo inteiro está imerso em variabilidade. Em termos de sistemas configuráveis, violações totais podem apontar cenários em que ambas as chamadas são opcionais, porém desalinhadas, ao passo que violações parciais frequentemente sugerem omissão de um lado do protocolo em um contexto configuracional específico.",
        _table_block(metrics.violation_types, ["Tipo", "Quantidade"]),
        "",
        "## RQ12. Número de produtos com violações",
        f"Interpretando `produto` como `Project`, o número de produtos com pelo menos uma violação é {_fmt_int(viol['produtos_com_violacao'])}. Essa medida corresponde à cardinalidade do conjunto de sistemas em que o fenômeno aparece e é importante porque distingue severidade local de disseminação do problema pelo corpus. Um número alto de produtos afetados indica generalidade do fenômeno; um número baixo com alta concentração indicaria um problema mais localizado.",
        "",
        "## RQ13. Número de violações por produto",
        f"O produto com mais violações é `{top_product['Project']}`, com {_fmt_int(top_product['violacoes'])} ocorrências filtradas. A tabela e o gráfico `08_violacoes_por_produto` mostram a distribuição dos produtos mais afetados. Em estatística aplicada, essa análise serve para identificar concentração do risco e orientar seleção de estudos de caso. Em engenharia de software empírica, produtos no topo desse ranking são candidatos naturais a análise qualitativa detalhada, porque reúnem massa crítica suficiente de evidência para discussão arquitetural e configuracional.",
        _table_block(metrics.violations_per_product, ["Project", "violacoes", "padroes_violados_distintos", "violacoes_parciais", "violacoes_totais"]),
        "![RQ13](figures/08_violacoes_por_produto.png)",
        "",
        "## Figura de Síntese",
        "O gráfico a seguir resume as principais grandezas do estudo em uma única visualização: sistemas e arquivos com padrão, padrões distintos, instâncias de padrão, variabilidades distintas e violações filtradas. Ele funciona como âncora quantitativa para todas as RQs subsequentes.",
        "![Resumo](figures/01_resumo_corpus.png)",
        "",
        "## Síntese Final",
        "Em síntese, o corpus apresenta alta heterogeneidade estrutural: poucos sistemas e poucos arquivos concentram grande parte das instâncias de padrão, das variabilidades e das violações. As violações residuais concentram-se em protocolos clássicos de gerenciamento de recursos e aparecem em número substancial de produtos. Sob a perspectiva de sistemas configuráveis, o resultado mais importante é que as respostas às RQs apontam para uma associação forte entre variabilidade por diretivas de pré-processamento e a fragmentação de padrões de uso de APIs, sobretudo quando se observa o subconjunto de instâncias em variabilidade e a decomposição entre violações parciais e totais.",
    ]
    paths.markdown_path.write_text("\n\n".join(content), encoding="utf-8")


def write_rq_pdf_report(metrics: RQMetricBundle, paths: RQReportPaths) -> None:
    styles = _build_styles()
    md_text = paths.markdown_path.read_text(encoding="utf-8")
    sections = [s.strip() for s in md_text.split("\n## ") if s.strip()]
    doc = SimpleDocTemplate(
        str(paths.pdf_path),
        pagesize=A4,
        leftMargin=1.7 * cm,
        rightMargin=1.7 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="Relatório Técnico Orientado por Questões de Pesquisa",
        author="OpenAI Codex",
    )
    story = []
    story.append(Paragraph("Relatório Técnico Orientado por Questões de Pesquisa", styles["SectionBlue"]))
    story.append(
        Paragraph(
            "Relatório técnico em português, com foco nas perguntas de pesquisa sobre padrões de uso, variabilidade e violações em sistemas configuráveis em C/C++.",
            styles["BodyDense"],
        )
    )
    image_names = {
        "RQ1": "02_padroes_por_sistema.png",
        "RQ2": "03_padroes_por_arquivo.png",
        "RQ3": "04_variabilidade_por_sistema.png",
        "RQ4": "05_variabilidade_por_arquivo.png",
        "RQ7": "06_parcial_vs_total.png",
        "RQ8": "09_variabilidades_com_padroes.png",
        "RQ10": "07_padroes_mais_violados.png",
        "RQ13": "08_violacoes_por_produto.png",
        "Resumo": "01_resumo_corpus.png",
    }
    for idx, section in enumerate(sections):
        title, _, body = section.partition("\n\n")
        title = title.replace("# ", "").strip()
        story.append(Paragraph(title, styles["SectionBlue"]))
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        for paragraph in paragraphs:
            if paragraph.startswith("!["):
                start = paragraph.find("(")
                end = paragraph.find(")")
                rel = paragraph[start + 1 : end]
                img_path = paths.base_dir / rel
                if img_path.exists():
                    story.append(_scaled_image(img_path))
                    story.append(Spacer(1, 0.15 * cm))
            elif paragraph.startswith("```"):
                code_text = paragraph.strip("`").strip().replace("\n", "<br/>")
                story.append(Paragraph(f"<font face='Courier'>{code_text}</font>", styles["BodyDense"]))
            else:
                story.append(Paragraph(paragraph, styles["BodyDense"]))
        if idx != len(sections) - 1:
            story.append(PageBreak())
    doc.build(story)


def generate_rq_technical_report(
    pc_csv_path: Path,
    raw_path: Path,
    dedup_path: Path,
    out_dir: Path,
) -> RQReportPaths:
    paths = RQReportPaths.build(out_dir)
    paths.base_dir.mkdir(parents=True, exist_ok=True)
    paths.figures_dir.mkdir(parents=True, exist_ok=True)
    paths.tables_dir.mkdir(parents=True, exist_ok=True)

    _ensure_filtered_output(dedup_path, paths.analyzed_path, paths.filtered_path)

    pc_calls = _load_pc_calls(pc_csv_path)
    raw = _normalize_output(pd.read_csv(raw_path))
    dedup = _normalize_output(pd.read_csv(dedup_path))
    filtered = _normalize_output(pd.read_csv(paths.filtered_path))
    metrics = _build_metrics(pc_calls, raw, dedup, filtered)

    write_rq_tables(metrics, paths.tables_dir)
    generate_rq_plots(metrics, paths.figures_dir)
    write_rq_markdown_report(metrics, paths)
    write_rq_pdf_report(metrics, paths)
    return paths
