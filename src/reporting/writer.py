from __future__ import annotations

from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reporting.metrics import MetricBundle
from reporting.models import ReportPaths


FIGURE_EXPLANATIONS = {
    "01_stage_comparison": "Compara as saídas bruta, deduplicada, analisada e filtrada. O objetivo é mostrar o efeito acumulado das transformações do pipeline sobre o volume total, o volume de violações e o volume de não violações.",
    "02_top_violation_pairs": "Mostra os pares de APIs com maior concentração de violações após a remoção dos falsos positivos confirmados. Esse gráfico ajuda a priorizar protocolos com maior criticidade prática.",
    "03_top_non_violation_pairs": "Mostra os pares que aparecem com frequência, mas majoritariamente sem violação. Isso é importante para stakeholders porque evidencia padrões estáveis e contextos de uso consistente.",
    "04_top_systems": "Evidencia quais sistemas concentram mais violações após o refinamento do pipeline. O gráfico ajuda a localizar outliers e potenciais focos de inspeção manual.",
    "05_variability_breakdown": "Relaciona violação/não violação com as classes de variabilidade none, partial e total. O objetivo é mostrar como a variabilidade se distribui entre casos estáveis e casos problemáticos.",
    "06_fp_status": "Resume a etapa de análise de falsos positivos. O gráfico separa linhas sem ação, violações candidatas e falsos positivos confirmados para mostrar o impacto analítico da filtragem.",
    "07_top_fp_contexts": "Mostra os contextos mais afetados por falsos positivos confirmados. Normalmente esses casos apontam funções grandes ou altamente configuráveis com várias instâncias do mesmo protocolo de API.",
    "08_pattern_volume_vs_rate": "Cruza volume de ocorrências e taxa de violação por padrão. Esse gráfico ajuda a diferenciar padrões raros e extremos de padrões frequentes e sistematicamente problemáticos.",
}


def _fmt_int(value: object) -> str:
    return f"{int(value):,}".replace(",", ".")


def _df_block(df: pd.DataFrame, limit: int = 10) -> str:
    if df.empty:
        return "Sem dados."
    return "```\n" + df.head(limit).to_string(index=False) + "\n```"


def write_metric_tables(metrics: MetricBundle, tables_dir: Path) -> None:
    tables_dir.mkdir(parents=True, exist_ok=True)
    metric_frames = {
        "overall_summary.csv": metrics.overall,
        "stage_counts.csv": metrics.stage_counts,
        "pair_summary.csv": metrics.pair_summary,
        "non_violation_pairs.csv": metrics.non_violation_pairs,
        "system_summary.csv": metrics.system_summary,
        "variability_summary.csv": metrics.variability_summary,
        "fp_summary.csv": metrics.fp_summary,
        "fp_contexts.csv": metrics.fp_contexts,
        "pattern_scatter.csv": metrics.pattern_scatter,
    }
    for name, df in metric_frames.items():
        df.to_csv(tables_dir / name, index=False)


def write_markdown_report(metrics: MetricBundle, paths: ReportPaths) -> None:
    overall = metrics.overall.iloc[0]
    stage = metrics.stage_counts.set_index("Stage")
    raw_rows = int(stage.loc["raw", "Rows"])
    dedup_rows = int(stage.loc["dedup", "Rows"])
    filtered_rows = int(stage.loc["filtered", "Rows"])
    raw_yes = int(stage.loc["raw", "YES"])
    dedup_yes = int(stage.loc["dedup", "YES"])
    filtered_yes = int(stage.loc["filtered", "YES"])
    dedup_row_reduction = (raw_rows - dedup_rows) / raw_rows if raw_rows else 0.0
    dedup_yes_reduction = (raw_yes - dedup_yes) / raw_yes if raw_yes else 0.0
    fp_yes_reduction = (dedup_yes - filtered_yes) / dedup_yes if dedup_yes else 0.0

    top3_pair_share = metrics.pair_summary.head(3)["yes_rows"].sum() / filtered_yes if filtered_yes else 0.0
    top5_pair_share = metrics.pair_summary.head(5)["yes_rows"].sum() / filtered_yes if filtered_yes else 0.0
    top3_system_share = metrics.system_summary.head(3)["yes_rows"].sum() / filtered_yes if filtered_yes else 0.0
    top5_system_share = metrics.system_summary.head(5)["yes_rows"].sum() / filtered_yes if filtered_yes else 0.0

    fp_total = int(overall["confirmed_false_positives"])
    top_fp_context_share = (
        metrics.fp_contexts.iloc[0]["confirmed_false_positives"] / fp_total
        if fp_total and not metrics.fp_contexts.empty
        else 0.0
    )

    var_pivot = metrics.variability_summary.pivot(index="VarClass", columns="Violation", values="count").fillna(0)
    for idx in ["none", "partial", "total"]:
        if idx not in var_pivot.index:
            var_pivot.loc[idx] = {"NO": 0, "YES": 0}
    for col in ["NO", "YES"]:
        if col not in var_pivot.columns:
            var_pivot[col] = 0
    var_pivot = var_pivot.loc[["none", "partial", "total"]]
    var_lines = []
    for idx, row in var_pivot.iterrows():
        total = row["NO"] + row["YES"]
        rate = (row["YES"] / total) if total else 0.0
        var_lines.append(f"- `{idx}`: {_fmt_int(total)} linhas, taxa de violacao {rate:.2%}.")

    top_pair = metrics.pair_summary.iloc[0]
    top_system = metrics.system_summary.iloc[0]
    top_fp_context = metrics.fp_contexts.iloc[0] if not metrics.fp_contexts.empty else None
    md = f"""# Technical Violation Report

## Executive Summary
- Systems analyzed: {_fmt_int(overall['systems'])}
- Files covered in filtered output: {_fmt_int(overall['files'])}
- Distinct API patterns after filtering: {_fmt_int(overall['distinct_patterns'])}
- Raw rows: {_fmt_int(overall['raw_rows'])}
- Rows after deduplication: {_fmt_int(overall['dedup_rows'])}
- Rows after false-positive filtering: {_fmt_int(overall['filtered_rows'])}
- Raw violations: {_fmt_int(overall['raw_violations'])}
- Violations after deduplication: {_fmt_int(overall['dedup_violations'])}
- Violations after filtering: {_fmt_int(overall['filtered_violations'])}
- Confirmed false positives removed: {_fmt_int(overall['confirmed_false_positives'])}

## Stakeholder Interpretation
This report separates the pipeline into stages so the stakeholder can understand not only how many violations were detected, but also how many were later identified as analytical artifacts. The most important distinction is between:
- candidate violations that remain after filtering
- confirmed false positives caused by Cartesian cross-products among already matched PCs
- stable non-violating patterns that dominate the normal operational behavior

## Statistical Highlights
- Deduplication reduced the total output from {_fmt_int(raw_rows)} to {_fmt_int(dedup_rows)} rows, a reduction of {dedup_row_reduction:.2%}.
- Deduplication reduced raw violations from {_fmt_int(raw_yes)} to {_fmt_int(dedup_yes)}, a reduction of {dedup_yes_reduction:.2%}.
- Match-First Filtering removed {_fmt_int(dedup_yes - filtered_yes)} of {_fmt_int(dedup_yes)} deduplicated violations, i.e. {fp_yes_reduction:.2%} of the post-dedup violation set.
- The top 3 violated API pairs account for {top3_pair_share:.2%} of the filtered violations; the top 5 account for {top5_pair_share:.2%}.
- The top 3 systems account for {top3_system_share:.2%} of the filtered violations; the top 5 account for {top5_system_share:.2%}.
- The most affected pair after filtering is `{top_pair['Pattern']}`, with {_fmt_int(top_pair['yes_rows'])} violation rows and violation rate {top_pair['yes_rate']:.2%}.
- The most affected system after filtering is `{top_system['Project']}`, with {_fmt_int(top_system['yes_rows'])} violation rows and violation rate {top_system['yes_rate']:.2%}.
"""
    if top_fp_context is not None:
        md += f"- The top false-positive context is `{top_fp_context['Project']} | {top_fp_context['Caller']} | {top_fp_context['PairKey']}`, concentrating {top_fp_context_share:.2%} of all confirmed false positives.\n"

    md += f"""

## Stage Comparison
The stage comparison shows how the pipeline evolves from raw evidence to filtered evidence. The first reduction stage is dominated by mirrored-row elimination, which is expected in an unordered detector. The second relevant reduction occurs between the analyzed and filtered stages and reflects false positives attributable to cross-product mixing among PCs that already match textually in the same context.

From a statistical perspective, the filtered output is the most decision-relevant artifact because it combines:
- the original sensitivity of the detector;
- the symmetry correction performed by deduplication;
- a conservative false-positive removal rule that does not alter the detector baseline.

{_df_block(metrics.stage_counts)}

## Violation Analysis
The table below ranks the API pairs with the highest number of violations after filtering. These pairs deserve priority because they combine residual inconsistency with practical recurrence across many systems and files.

Two complementary readings are important here:
- absolute violation volume indicates operational relevance;
- violation rate indicates structural fragility relative to the number of observed instances.

For example, a pair such as `free | malloc` may dominate in absolute count because it is ubiquitous, whereas a pair such as `close | open` may deserve special attention if its violation rate is proportionally higher.

{_df_block(metrics.pair_summary[['Pattern', 'yes_rows', 'no_rows', 'total_rows', 'yes_rate', 'projects']])}

The next table highlights the pairs with many non-violations. These are useful as a control signal because they show where the detector repeatedly observes stable, coherent and probably well-understood protocols. In statistical terms, these rows form the baseline of normal behavior against which the violation distribution should be interpreted.

{_df_block(metrics.non_violation_pairs[['Pattern', 'no_rows', 'yes_rows', 'total_rows', 'yes_rate']])}

## System-Level Analysis
The system ranking identifies which projects concentrate more residual violations. This ranking should be read with care:
- high absolute counts may reflect large, mature and highly configurable systems;
- high violation rates may indicate concentrated fragility;
- high diversity of patterns suggests a wider protocol surface under variability.

The systems at the top of this table are strong candidates for case-study analysis, targeted inspection and manual validation.

{_df_block(metrics.system_summary[['Project', 'yes_rows', 'no_rows', 'total_rows', 'yes_rate', 'distinct_patterns']])}

## Variability and Result
The variability summary connects violations and non-violations with the classes `none`, `partial` and `total`. This section is important because it indicates whether the residual violations are mostly associated with:
- no variability at all;
- asymmetric variability between the two sides of the pattern;
- or full variability on both sides.

The current filtered output shows a strong separation between stable unconditional usage and the contexts where violations remain. That is analytically important because it suggests that the residual problems are not uniformly distributed across all usage, but are concentrated in variability-aware regions.

{_df_block(metrics.variability_summary)}

### Variability Rates
{chr(10).join(var_lines)}

## False-Positive Analysis
The false-positive analysis isolates the impact of Match-First Filtering. Rows marked as `ConfirmedFalsePositive` are those where the same context already contained exact textual PC matches, meaning the reported `YES` came from an artificial cross-product rather than a strong residual mismatch.

This is not merely a cosmetic reduction. Statistically, it means the filtered violation set has a stronger signal-to-noise ratio than the deduplicated set. Methodologically, it preserves the unordered and string-based detector while making the analytical interpretation more trustworthy.

{_df_block(metrics.fp_summary)}

The next table shows the contexts with the highest concentration of confirmed false positives. These are typically large and highly configurable callers where multiple API-call instances were merged by the Cartesian product. In other words, they are not random noise; they are structural indicators of where the detector's grouping granularity is most stressed.

{_df_block(metrics.fp_contexts)}

## Figure-by-Figure Interpretation
Each figure should be read together with the corresponding tables. The figures are not decorative; each one was selected to answer a practical question that a stakeholder may ask about scale, concentration, consistency and analytical reliability.
"""
    for fig_name, explanation in FIGURE_EXPLANATIONS.items():
        md += f"\n### {fig_name}\n- {explanation}\n"

    md += f"""

## Interpretation for Decision-Making
- If the objective is prioritization, start with the top violated pairs and the top systems simultaneously.
- If the objective is methodological validation, inspect the false-positive contexts first, because they reveal where Cartesian mixing is strongest.
- If the objective is risk management, prioritize patterns with both high volume and high violation rate.
- If the objective is scientific reporting, contrast the stable high-frequency non-violation pairs with the concentrated residual violation pairs.

## Methodological Limitations
- The detector remains intentionally string-based and unordered; therefore, the report does not claim semantic equivalence between distinct PCs.
- Confirmed false positives here mean cross-product artifacts under the implemented rule; they are not a universal notion of false positive.
- Large projects can dominate absolute counts, so absolute rankings must always be interpreted together with rates and coverage.

## Output Structure
- Figures: `{paths.figures_dir}`
- Tables: `{paths.tables_dir}`
- Filtered violation CSV: `{paths.filtered_output_path}`
- False-positive analysis CSV: `{paths.fp_analysis_path}`

## Conclusion
The filtered report preserves the sensitivity of the baseline detector while reducing a meaningful subset of analytical artifacts. For stakeholders, the key message is that the final violation set is not just a raw detector output: it is an auditable result refined by deduplication and false-positive identification, making it more suitable for inspection, prioritization and downstream quality analysis.

From a statistical standpoint, the most important outcome is concentration: a relatively small subset of API pairs and systems explains a substantial share of the residual violations. From a software-engineering standpoint, the most important outcome is interpretability: the report now distinguishes raw evidence, corrected evidence and filtered evidence, enabling more defensible conclusions about where variability is actually stressing API usage patterns.
"""
    paths.markdown_path.write_text(md, encoding="utf-8")


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TitleCenter",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionBlue",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0b3c5d"),
            spaceBefore=8,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodySmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            spaceAfter=6,
        )
    )
    return styles


def _scaled_image(path: Path, max_width_cm: float = 16.5) -> Image:
    img = Image(str(path))
    max_width = max_width_cm * cm
    scale = min(1.0, max_width / img.drawWidth)
    img.drawWidth *= scale
    img.drawHeight *= scale
    return img


def _top_rows_table(df: pd.DataFrame, n: int = 8) -> Table:
    rows = [list(df.columns)]
    for _, row in df.head(n).iterrows():
        rows.append([str(v) for v in row.tolist()])
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3c5d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#eef5fb")]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8c7d1")),
            ]
        )
    )
    return table


def write_pdf_report(metrics: MetricBundle, paths: ReportPaths) -> None:
    styles = _build_styles()
    overall = metrics.overall.iloc[0]
    stage = metrics.stage_counts.set_index("Stage")
    dedup_yes = int(stage.loc["dedup", "YES"])
    filtered_yes = int(stage.loc["filtered", "YES"])
    fp_yes_reduction = (dedup_yes - filtered_yes) / dedup_yes if dedup_yes else 0.0
    doc = SimpleDocTemplate(
        str(paths.pdf_path),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title="Technical Violation Report",
        author="OpenAI Codex",
    )
    story = []
    story.append(Paragraph("Technical Violation Report", styles["TitleCenter"]))
    story.append(
        Paragraph(
            "This report was generated automatically from the detector outputs, the "
            "deduplicated outputs, and the Match-First false-positive analysis stage.",
            styles["BodySmall"],
        )
    )
    story.append(Paragraph("Executive Summary", styles["SectionBlue"]))
    summary_lines = [
        f"Systems analyzed: {_fmt_int(overall['systems'])}.",
        f"Files in filtered output: {_fmt_int(overall['files'])}.",
        f"Distinct patterns after filtering: {_fmt_int(overall['distinct_patterns'])}.",
        f"Raw violations: {_fmt_int(overall['raw_violations'])}; filtered violations: {_fmt_int(overall['filtered_violations'])}.",
        f"Confirmed false positives removed: {_fmt_int(overall['confirmed_false_positives'])}, equal to {fp_yes_reduction:.2%} of the deduplicated violation set.",
    ]
    for line in summary_lines:
        story.append(Paragraph(line, styles["BodySmall"]))

    story.append(Paragraph("Interpretive Highlights", styles["SectionBlue"]))
    story.append(
        Paragraph(
            "The report should be interpreted as a staged analytical pipeline: raw evidence, "
            "deduplicated evidence, false-positive analysis and filtered evidence. This makes "
            "the final violation set more robust for stakeholder decisions than the raw detector output alone.",
            styles["BodySmall"],
        )
    )

    story.append(Paragraph("Top Violation Pairs", styles["SectionBlue"]))
    story.append(_top_rows_table(metrics.pair_summary[["Pattern", "yes_rows", "no_rows", "yes_rate"]], n=8))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("Top Systems", styles["SectionBlue"]))
    story.append(_top_rows_table(metrics.system_summary[["Project", "yes_rows", "no_rows", "yes_rate"]], n=8))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("False-Positive Summary", styles["SectionBlue"]))
    story.append(_top_rows_table(metrics.fp_summary[["FPStatus", "count"]], n=8))
    story.append(PageBreak())

    for fig_name, explanation in FIGURE_EXPLANATIONS.items():
        fig_path = paths.figures_dir / f"{fig_name}.png"
        if not fig_path.exists():
            continue
        story.append(Paragraph(fig_name, styles["SectionBlue"]))
        story.append(_scaled_image(fig_path))
        story.append(Paragraph(explanation, styles["BodySmall"]))
        story.append(Spacer(1, 0.2 * cm))

    doc.build(story)
