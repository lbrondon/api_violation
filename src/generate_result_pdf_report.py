from __future__ import annotations

from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


BASE_DIR = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = BASE_DIR / "result_analysis"
FIG_DIR = ANALYSIS_DIR / "figures"
OUT_PDF = ANALYSIS_DIR / "result_visual_report.pdf"


def load_data() -> dict[str, pd.DataFrame]:
    return {
        "overall": pd.read_csv(ANALYSIS_DIR / "overall_summary.csv"),
        "patterns_per_system": pd.read_csv(ANALYSIS_DIR / "patterns_per_system.csv"),
        "patterns_per_file": pd.read_csv(ANALYSIS_DIR / "patterns_per_file.csv"),
        "variability_per_system": pd.read_csv(ANALYSIS_DIR / "variability_per_system.csv"),
        "variability_per_file": pd.read_csv(ANALYSIS_DIR / "variability_per_file.csv"),
        "violated_patterns": pd.read_csv(ANALYSIS_DIR / "violated_patterns.csv"),
        "violations_per_system": pd.read_csv(ANALYSIS_DIR / "violations_per_system.csv"),
        "variability_with_patterns": pd.read_csv(ANALYSIS_DIR / "variability_with_patterns.csv"),
    }


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TitleCenter",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
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
            fontSize=10,
            leading=14,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Caption",
            parent=styles["Italic"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=colors.HexColor("#555555"),
            leading=12,
            spaceAfter=8,
        )
    )
    return styles


def fmt_int(value: object) -> str:
    return f"{int(value):,}".replace(",", ".")


def top_rows_table(df: pd.DataFrame, columns: list[str], n: int = 5) -> Table:
    rows = [columns]
    for _, row in df.head(n).iterrows():
        rows.append([str(row[col]) for col in columns])
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3c5d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#eef5fb")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8c7d1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def scaled_image(path: Path, max_width_cm: float = 16.5) -> Image:
    img = Image(str(path))
    max_width = max_width_cm * cm
    scale = min(1.0, max_width / img.drawWidth)
    img.drawWidth *= scale
    img.drawHeight *= scale
    return img


def add_figure(story: list, styles, fig_name: str, title: str, explanation: str) -> None:
    story.append(Paragraph(title, styles["Section"]))
    story.append(scaled_image(FIG_DIR / f"{fig_name}.png"))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(explanation, styles["BodySmall"]))
    story.append(Paragraph(f"Figura: {fig_name}.png", styles["Caption"]))
    story.append(Spacer(1, 0.25 * cm))


def build_report() -> None:
    styles = build_styles()
    data = load_data()
    overall = data["overall"].iloc[0]
    pps = data["patterns_per_system"]
    ppf = data["patterns_per_file"]
    vps = data["variability_per_system"]
    vpf = data["variability_per_file"]
    vp = data["violated_patterns"]
    vpsys = data["violations_per_system"]
    vwp = data["variability_with_patterns"]

    doc = SimpleDocTemplate(
        str(OUT_PDF),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title="API Violation Result Analysis",
        author="OpenAI Codex",
    )

    story: list = []
    story.append(Paragraph("Relatório de Resultados e Visualizações", styles["TitleCenter"]))
    story.append(
        Paragraph(
            "Este relatório explica os gráficos gerados para o estudo de violações de padrões de uso de API "
            "em sistemas configuráveis, usando como base o conjunto de 57 sistemas e os artefatos calculados em "
            "`result_analysis/`.",
            styles["BodySmall"],
        )
    )
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph("Resumo Executivo", styles["Section"]))
    summary_items = [
        f"Sistemas analisados: {fmt_int(overall['systems'])}.",
        f"Arquivos com chamadas válidas: {fmt_int(overall['files'])}.",
        f"Padrões de uso distintos observados: {fmt_int(overall['distinct_patterns_observed'])}.",
        f"Instâncias distintas de padrão após deduplicação: {fmt_int(overall['distinct_pattern_instances'])}.",
        f"Expressões de variabilidade distintas (PC != TRUE): {fmt_int(overall['distinct_variability_pcs'])}.",
        f"Instâncias de padrão em variabilidade: {fmt_int(overall['distinct_pattern_instances_in_variability'])}, sendo {fmt_int(overall['partial_pattern_instances'])} parciais e {fmt_int(overall['total_pattern_instances'])} totais.",
        f"Violações distintas: {fmt_int(overall['distinct_violations'])}; violações brutas: {fmt_int(overall['raw_violations'])}.",
        f"Produtos com violações, considerando produto = sistema: {fmt_int(len(vpsys))}.",
    ]
    for item in summary_items:
        story.append(Paragraph(f"• {item}", styles["BodySmall"]))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Respostas às Perguntas de Pesquisa", styles["Section"]))
    answers = [
        f"1. Número de padrões de uso por sistema: disponível em `patterns_per_system.csv`; mediana de {pps['distinct_patterns'].median():.1f} padrões distintos por sistema e máximo de {fmt_int(pps['distinct_patterns'].max())}.",
        f"2. Número de padrões de uso por arquivo: disponível em `patterns_per_file.csv`; {fmt_int(len(ppf))} arquivos exibem ao menos um padrão, com mediana de {ppf['distinct_patterns'].median():.1f} padrão distinto por arquivo.",
        f"3. Número de variabilidade por sistema: disponível em `variability_per_system.csv`; mediana de {vps['distinct_variability_pcs'].median():.1f} PCs distintos por sistema.",
        f"4. Número de variabilidade por arquivo: disponível em `variability_per_file.csv`; {fmt_int(len(vpf))} arquivos contêm variabilidade, com mediana de {vpf['distinct_variability_pcs'].median():.1f} PCs distintos por arquivo.",
        f"5. Número de padrões de uso em sistema (exceto TRUE): {fmt_int(overall['distinct_pattern_instances_in_variability'])} instâncias distintas em contexto variável, distribuídas entre todos os {fmt_int(overall['distinct_pattern_pairs_in_variability'])} padrões observados.",
        f"6. Número de padrões de uso em arquivo: coincide com a análise por arquivo do item 2; os detalhes estão em `patterns_per_file.csv`.",
        f"7. Número de padrões de uso em variabilidade parcial ou total: {fmt_int(overall['partial_pattern_instances'])} instâncias parciais e {fmt_int(overall['total_pattern_instances'])} instâncias totais.",
        f"8. Número de variabilidades com padrão de uso: {fmt_int(overall['distinct_variabilities_with_pattern'])} expressões de variabilidade participam de ao menos um padrão, totalizando {fmt_int(overall['distinct_variability_pattern_links'])} vínculos variabilidade-padrão.",
        f"9. Número de violações: {fmt_int(overall['distinct_violations'])} violações distintas e {fmt_int(overall['raw_violations'])} violações brutas.",
        f"10. Padrões de uso mais violados: liderados por `{vp.iloc[0]['Pattern']}` ({fmt_int(vp.iloc[0]['distinct_violations'])}) e `{vp.iloc[1]['Pattern']}` ({fmt_int(vp.iloc[1]['distinct_violations'])}).",
        f"11. Tipos de violações: {fmt_int(overall['partial_violations'])} violações parciais e {fmt_int(overall['total_violations'])} violações totais.",
        f"12. Número de produtos com violações: {fmt_int(len(vpsys))}, adotando produto = sistema.",
        f"13. Número de violações por produto: disponível em `violations_per_system.csv`; os sistemas com mais violações são `{vpsys.iloc[0]['Project']}` ({fmt_int(vpsys.iloc[0]['distinct_violations'])}) e `{vpsys.iloc[1]['Project']}` ({fmt_int(vpsys.iloc[1]['distinct_violations'])}).",
    ]
    for answer in answers:
        story.append(Paragraph(answer, styles["BodySmall"]))

    story.append(PageBreak())

    add_figure(
        story,
        styles,
        "01_corpus_overview",
        "1. Visão Geral do Corpus",
        "Este gráfico resume a escala do estudo. Ele mostra que a base é ampla em número de arquivos e expressões "
        "de variabilidade, mas relativamente compacta em número de padrões distintos. Essa combinação é importante "
        "porque sugere um cenário com poucos protocolos de uso recorrentes, porém instanciados em muitos contextos "
        "de compilação e implementação. Em termos metodológicos, isso reforça que a análise de violações não depende "
        "apenas da presença de pares de chamadas, mas da interação entre esses pares e a variabilidade do sistema.",
    )

    add_figure(
        story,
        styles,
        "02_partial_vs_total",
        "2. Comparação entre Efeitos Parciais e Totais",
        "O gráfico compara dois fenômenos: ocorrência de padrões em variabilidade e ocorrência de violações em "
        "variabilidade. Em ambos os casos, o componente total é maior que o parcial. Isso sugere que a maior parte "
        "da complexidade relevante não está em cenários onde apenas um lado do padrão depende de variabilidade, mas "
        "em casos onde ambas as chamadas são moduladas por PCs não triviais. Esse resultado é coerente com sistemas "
        "configuráveis de larga escala, em que dependências entre APIs frequentemente se espalham por múltiplas "
        "condições de compilação.",
    )

    add_figure(
        story,
        styles,
        "03_top_violated_patterns",
        "3. Padrões de Uso Mais Violados",
        "Este gráfico responde diretamente à pergunta sobre os padrões de uso mais violados. Os pares ligados a "
        "gerência de memória e ciclo de vida de recursos dominam o ranking, com destaque para `free | malloc` e "
        "`close | open`. Isso indica que os principais problemas do corpus não estão em APIs raras ou especializadas, "
        "mas em protocolos fundamentais de alocação, desalocação, abertura e fechamento de recursos. A concentração "
        "nesses pares também sugere alto potencial de impacto prático para ferramentas que priorizem esses padrões.",
    )

    story.append(Paragraph("Tabela de apoio: top 5 padrões mais violados", styles["Section"]))
    story.append(
        top_rows_table(
            vp,
            ["Pattern", "distinct_violations", "affected_systems", "partial_violations", "total_violations"],
            n=5,
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    add_figure(
        story,
        styles,
        "04_top_systems_violations",
        "4. Sistemas com Maior Número de Violações",
        "Este gráfico responde à distribuição de violações por produto, onde produto foi definido como sistema. "
        "A distribuição é claramente desigual: poucos sistemas concentram um volume grande de violações distintas. "
        "Essa assimetria é relevante porque indica que a carga de inconsistências não se distribui uniformemente pelo "
        "corpus. Em termos empíricos, `xterm-snapshots` e `gzip` funcionam como outliers importantes e merecem análise "
        "qualitativa adicional, pois podem revelar mecanismos estruturais de violação repetida sob variabilidade.",
    )

    story.append(Paragraph("Tabela de apoio: top 5 sistemas com mais violações", styles["Section"]))
    story.append(
        top_rows_table(
            vpsys,
            ["Project", "distinct_violations", "distinct_violated_patterns", "partial_violations", "total_violations"],
            n=5,
        )
    )

    story.append(PageBreak())

    add_figure(
        story,
        styles,
        "05_top_systems_patterns_vs_variability",
        "5. Relação entre Densidade de Padrões e Densidade de Variabilidade",
        "Este gráfico compara, nos sistemas mais intensos em padrões, a quantidade de instâncias de padrão e a "
        "quantidade de expressões de variabilidade. Ele ajuda a interpretar as perguntas sobre número de padrões por "
        "sistema e número de variabilidades por sistema. Nem sempre os sistemas com mais padrões são os que têm mais "
        "variabilidade, o que indica que esses dois fenômenos são relacionados, mas não equivalentes. Em outras "
        "palavras, a mera presença de variabilidade não implica necessariamente maior densidade de padrões, e vice-versa.",
    )

    add_figure(
        story,
        styles,
        "06_distribution_patterns_per_file",
        "6. Distribuição de Padrões por Arquivo",
        "O histograma mostra que a maioria dos arquivos possui poucos padrões de uso observados, enquanto uma minoria "
        "concentra vários padrões simultaneamente. Esse comportamento de cauda longa é típico de código de infraestrutura, "
        "camadas utilitárias ou arquivos centrais do sistema. Para a pergunta sobre padrões por arquivo, isso sugere que "
        "medidas de tendência central devem ser acompanhadas por análise dos extremos, pois os arquivos mais densos "
        "podem distorcer a percepção global do corpus.",
    )

    add_figure(
        story,
        styles,
        "07_distribution_variability_per_file",
        "7. Distribuição de Variabilidade por Arquivo",
        "Este histograma mostra a dispersão da variabilidade em nível de arquivo. Assim como nos padrões, há forte "
        "assimetria: muitos arquivos têm poucas expressões distintas, mas alguns concentram variabilidade elevada. "
        "Essa informação complementa a análise anterior ao indicar que a variabilidade também se organiza de forma "
        "não uniforme. Arquivos no topo dessa distribuição são candidatos naturais para inspeção manual, pois combinam "
        "alta complexidade configurável com maior probabilidade de interação entre condições.",
    )

    add_figure(
        story,
        styles,
        "08_top_variability_expressions",
        "8. Expressões de Variabilidade Mais Ligadas a Padrões de Uso",
        "Este gráfico ajuda a responder quantas e quais variabilidades participam de padrões de uso. Em vez de apenas "
        "contar PCs, ele mostra quais expressões reaparecem mais frequentemente em conexões com padrões. O resultado "
        "sugere que certas condições, como variantes relacionadas a plataformas e flags de compilação, funcionam como "
        "hubs de interação. Isso é importante porque aponta para regiões semânticas da variabilidade que têm maior "
        "potencial de influenciar protocolos de uso de API.",
    )

    story.append(Paragraph("Síntese Interpretativa", styles["Section"]))
    synthesis = [
        "Os gráficos mostram que o corpus combina alta diversidade de variabilidade com um conjunto relativamente pequeno de protocolos de uso recorrentes.",
        "As violações não se distribuem uniformemente: elas se concentram em poucos padrões centrais e em poucos sistemas com comportamento extremo.",
        "A predominância de casos totais sobre parciais sugere que a inconsistência entre chamadas relacionadas emerge, em grande parte, quando ambos os lados do padrão estão sujeitos a condições configuráveis.",
        "Pares como `free | malloc` e `close | open` devem ser priorizados em discussões de ameaça à validade prática, porque representam protocolos básicos e muito disseminados.",
        "As figuras de distribuição por arquivo indicam que uma análise apenas agregada por sistema pode esconder hotspots locais importantes.",
    ]
    for item in synthesis:
        story.append(Paragraph(f"• {item}", styles["BodySmall"]))

    doc.build(story)


if __name__ == "__main__":
    build_report()
