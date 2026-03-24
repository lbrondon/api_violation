from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reporting.datasets import load_datasets
from reporting.metrics import MetricBundle, build_metrics
from reporting.models import ReportPaths
from reporting.plots import generate_all_plots
from reporting.rq_report import (
    RQMetricBundle,
    _build_metrics as build_rq_metrics,
    _load_pc_calls,
    _normalize_output,
    generate_rq_plots,
    write_rq_tables,
)
from reporting.writer import write_metric_tables


@dataclass(frozen=True)
class UnifiedReportPaths:
    base_dir: Path
    markdown_path: Path
    pdf_path: Path
    technical_figures_dir: Path
    rq_figures_dir: Path
    technical_tables_dir: Path
    rq_tables_dir: Path
    fp_analysis_path: Path
    filtered_output_path: Path

    @classmethod
    def build(cls, base_dir: Path) -> "UnifiedReportPaths":
        return cls(
            base_dir=base_dir,
            markdown_path=base_dir / "unified_master_report.md",
            pdf_path=base_dir / "unified_master_report.pdf",
            technical_figures_dir=base_dir / "figures" / "technical",
            rq_figures_dir=base_dir / "figures" / "rq",
            technical_tables_dir=base_dir / "tables" / "technical",
            rq_tables_dir=base_dir / "tables" / "rq",
            fp_analysis_path=base_dir / "violations_fp_analysis.csv",
            filtered_output_path=base_dir / "violations_filtered.csv",
        )


def _fmt_int(value: object) -> str:
    return f"{int(value):,}".replace(",", ".")


def _fmt_pct(num: float) -> str:
    return f"{num:.2%}"


def _series_stats(series: pd.Series) -> dict[str, float]:
    s = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    if s.empty:
        return {"mean": 0.0, "median": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": float(s.mean()),
        "median": float(s.median()),
        "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        "min": float(s.min()),
        "max": float(s.max()),
    }


def _table_block(df: pd.DataFrame, columns: list[str], limit: int = 10) -> str:
    if df.empty:
        return "Sem dados."
    return "```\n" + df[columns].head(limit).to_string(index=False) + "\n```"


def _kv_table_block(title_left: str, title_right: str, rows: list[tuple[str, object]]) -> str:
    df = pd.DataFrame(rows, columns=[title_left, title_right])
    return "```\n" + df.to_string(index=False) + "\n```"


def _scaled_image(path: Path, max_width_cm: float = 16.0) -> Image:
    img = Image(str(path))
    max_width = max_width_cm * cm
    scale = min(1.0, max_width / img.drawWidth)
    img.drawWidth *= scale
    img.drawHeight *= scale
    return img


def _code_block_to_table(paragraph: str) -> Table | None:
    raw = paragraph.strip()
    if not (raw.startswith("```") and raw.endswith("```")):
        return None
    body = raw[3:-3].strip("\n")
    if not body:
        return None
    try:
        df = pd.read_fwf(StringIO(body))
    except Exception:
        return None
    if df.empty:
        return None

    rows = [list(df.columns)] + [[str(v) for v in row] for row in df.itertuples(index=False, name=None)]
    table = Table(rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3c5d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("LEADING", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#eef5fb")]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8c7d1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


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
            fontSize=9.4,
            leading=13,
            spaceAfter=8,
        )
    )
    return styles


def _figure_sections(paths: UnifiedReportPaths) -> list[tuple[str, Path, str]]:
    return [
        (
            "Figura 1. Comparação entre estágios do pipeline",
            paths.technical_figures_dir / "01_stage_comparison.png",
            "A Figura 1 sintetiza a evolução do pipeline da saída bruta até a saída filtrada. Ela mostra, simultaneamente, o efeito da deduplicação sobre espelhamentos e o efeito da análise de falsos positivos sobre o conjunto residual de violações. Do ponto de vista metodológico, essa figura é a âncora para interpretar por que a contagem final de violações não coincide com a primeira contagem emitida pelo detector.",
        ),
        (
            "Figura 2. Pares com maior volume de violações",
            paths.technical_figures_dir / "02_top_violation_pairs.png",
            "A Figura 2 destaca os pares de APIs com maior concentração de violações após a filtragem. Ela deve ser interpretada como evidência de concentração do fenômeno em protocolos clássicos de gerenciamento de recursos, como memória, arquivos e descritores. Em termos de priorização, os pares do topo combinam recorrência empírica e criticidade potencial.",
        ),
        (
            "Figura 3. Pares com maior volume de não violações",
            paths.technical_figures_dir / "03_top_non_violation_pairs.png",
            "A Figura 3 funciona como grupo de controle. Ela mostra que padrões muito frequentes podem permanecer majoritariamente estáveis, o que é importante para afastar a hipótese de que o detector apenas penaliza padrões populares. Em termos estatísticos, a figura oferece a base comparativa necessária para interpretar a massa de violações.",
        ),
        (
            "Figura 4. Sistemas com maior concentração de violações",
            paths.technical_figures_dir / "04_top_systems.png",
            "A Figura 4 mostra em quais produtos o problema residual de violação se concentra. O valor dessa figura está em combinar volume absoluto com contexto de produto, permitindo selecionar sistemas candidatos a estudos de caso e inspeção manual aprofundada.",
        ),
        (
            "Figura 6. Resumo da análise de falsos positivos",
            paths.technical_figures_dir / "06_fp_status.png",
            "A Figura 6 resume a distribuição entre `NoAction`, `CandidateViolation` e `ConfirmedFalsePositive`. Estatisticamente, ela explicita a decomposição do conjunto deduplicado em três subconjuntos mutuamente exclusivos, permitindo observar que a massa majoritária das linhas não demanda intervenção analítica, enquanto uma fração menor constitui o conjunto efetivo de violações residuais e uma parcela ainda menor corresponde a artefatos do produto cartesiano. Em termos metodológicos, a figura mostra que o Match-First Filtering não altera a baseline de detecção, mas atua na qualificação inferencial da saída, reduzindo a superestimação do fenômeno sem negar a complexidade variacional dos contextos originais. Portanto, esta figura é central para a validade analítica do estudo porque expressa, de maneira quantitativa, a passagem entre sensibilidade observacional e confiabilidade interpretativa.",
        ),
        (
            "Figura 9. Resumo do corpus e das respostas agregadas",
            paths.rq_figures_dir / "01_resumo_corpus.png",
            "A Figura 9 resume as grandezas agregadas mais importantes do estudo: sistemas e arquivos com padrão, padrões distintos, instâncias de padrão, variabilidades distintas e violações filtradas. Ela funciona como painel executivo do relatório consolidado.",
        ),
        (
            "Figura 10. Padrões de uso por sistema",
            paths.rq_figures_dir / "02_padroes_por_sistema.png",
            "A Figura 10 responde diretamente à questão sobre número de padrões por sistema. Ela evidencia a heterogeneidade estrutural do corpus e mostra quais produtos concentram maior densidade de padrões do catálogo.",
        ),
        (
            "Figura 11. Distribuição de padrões por arquivo",
            paths.rq_figures_dir / "03_padroes_por_arquivo.png",
            "A Figura 11 mostra a distribuição de instâncias de padrão por arquivo. Em termos estatísticos, ela evidencia assimetria à direita e longa cauda, o que sugere que poucos arquivos concentram grande volume de protocolos observados.",
        ),
        (
            "Figura 12. Variabilidades por sistema",
            paths.rq_figures_dir / "04_variabilidade_por_sistema.png",
            "A Figura 12 responde à questão sobre variabilidade por sistema. Ela aproxima a diversidade configuracional local de cada produto e ajuda a comparar densidade de variabilidade com densidade de padrões.",
        ),
        (
            "Figura 13. Distribuição de variabilidades por arquivo",
            paths.rq_figures_dir / "05_variabilidade_por_arquivo.png",
            "A Figura 13 mostra a densidade configuracional em nível de arquivo. Ela é importante para identificar arquivos que concentram alta diversidade de condições de presença e, portanto, maior dificuldade potencial de análise e manutenção.",
        ),
        (
            "Figura 14. Padrões em variabilidade e tipos de violação",
            paths.rq_figures_dir / "06_parcial_vs_total.png",
            "A Figura 14 compara a massa de padrões em variabilidade parcial e total com a massa de violações parciais e totais. Ela ajuda a responder se o problema está mais associado a assimetrias locais ou a protocolos integralmente imersos em variabilidade.",
        ),
        (
            "Figura 15. Padrões de uso mais violados",
            paths.rq_figures_dir / "07_padroes_mais_violados.png",
            "A Figura 15 responde de forma direta à questão sobre os padrões mais violados. Ela complementa a leitura do ranking de pares ao explicitar a hierarquia residual após a remoção dos falsos positivos confirmados.",
        ),
        (
            "Figura 16. Violações por produto",
            paths.rq_figures_dir / "08_violacoes_por_produto.png",
            "A Figura 16 mostra a distribuição de violações por produto, interpretando `Project` como unidade de produto. Essa figura é central para responder quantos produtos são afetados e com que intensidade.",
        ),
        (
            "Figura 17. Variabilidades mais ligadas a padrões de uso",
            paths.rq_figures_dir / "09_variabilidades_com_padroes.png",
            "A Figura 17 mostra quais expressões de variabilidade aparecem mais frequentemente associadas a padrões de uso. Ela é importante para investigar o acoplamento entre a diversidade configuracional e a manifestação dos protocolos do catálogo.",
        ),
    ]


def write_unified_markdown_report(
    technical: MetricBundle,
    rq: RQMetricBundle,
    paths: UnifiedReportPaths,
) -> None:
    overall = technical.overall.iloc[0]
    stage = technical.stage_counts.set_index("Stage")
    rq_overall = rq.overall.iloc[0]
    rq_viol = rq.violations_overview.iloc[0]
    top_pair = technical.pair_summary.iloc[0]
    top_system = technical.system_summary.iloc[0]
    top_product = rq.violations_per_product.iloc[0]
    pstats = _series_stats(rq.patterns_per_system["instancias_de_padrao"])
    vstats = _series_stats(rq.variability_per_system["variabilidades_distintas"])

    content = [
        "# Violação de Padrão de uso de API em Sistemas Configuráveis em C",
        "",
        "## Introdução",
        "Este relatório apresenta os resultados consolidados da identificação de violações de padrão de uso de API em sistemas configuráveis implementados em C. O foco principal está nas violações residuais observadas após a aplicação completa do pipeline analítico, isto é, depois da geração inicial dos candidatos, da deduplicação de espelhamentos e da remoção dos falsos positivos confirmados. Em termos práticos, o documento busca caracterizar onde as violações se concentram, quais padrões são mais afetados, como a variabilidade se distribui pelo corpus e em que medida a filtragem analítica altera a interpretação final do fenômeno. O problema central, portanto, não é apenas contar ocorrências, mas compreender como a variabilidade implementada por diretivas de pré-processamento está associada à fragmentação de protocolos de uso de APIs como `fopen`/`fclose`, `malloc`/`free`, `open`/`close` e outros pares do catálogo.",
        "",
        "## Objetivo do Relatório",
        "O objetivo específico deste relatório é caracterizar quantitativamente os resultados da identificação de violações de padrão de uso de API e responder, com base em rastreabilidade metodológica, às seguintes perguntas: número de padrões de uso por sistema; número de padrões de uso por arquivo; número de variabilidade por sistema; número de variabilidade por arquivo; número de padrões de uso em arquivo; número de padrões de uso em variabilidade parcial ou total; número de variabilidades com padrão de uso, distinguindo padrões distintos e padrões repetidos entre variabilidades; número total de violações; padrões de uso mais violados; tipos de violações; quantidade de sistemas com violações; e quantidade de violações por sistema. O relatório também explicita, para cada medida, a etapa metodológica do pipeline da qual ela deriva, de modo que a interpretação dos resultados permaneça cientificamente auditável.",
        "",
        "## Resumo das violações identificadas",
        "O corpus final analisado contém "
        + _fmt_int(overall["systems"])
        + " sistemas com pelo menos um padrão de uso observado e "
        + _fmt_int(overall["files"])
        + " arquivos cobertos na saída filtrada. Esses dois números delimitam a cobertura empírica do estudo e indicam a escala observacional sobre a qual as conclusões são construídas. Em termos metodológicos, eles decorrem da agregação das linhas finais do pipeline por `Project` e por `(Project, File)`, respectivamente, após o processo de qualificação analítica das violações.",
        "No conjunto final, foram observados "
        + _fmt_int(overall["distinct_patterns"])
        + " padrões distintos do catálogo. Esse número representa a diversidade protocolar efetivamente materializada no corpus, isto é, quantos pares não ordenados de APIs do catálogo apareceram nas saídas analisadas. Em termos teóricos, essa medida é importante porque distingue amplitude de repertório protocolar de simples volume de ocorrências.",
        "A saída bruta contém "
        + _fmt_int(overall["raw_rows"])
        + " linhas, enquanto a saída deduplicada contém "
        + _fmt_int(overall["dedup_rows"])
        + " linhas e a saída final após filtragem contém "
        + _fmt_int(overall["filtered_rows"])
        + " linhas. A diferença entre essas grandezas expressa a ação sucessiva de duas etapas metodológicas distintas. A deduplicação remove espelhamentos estruturais introduzidos pela interpretação não ordenada dos pares de APIs e dos pares de PCs. Já a filtragem posterior remove falsos positivos confirmados produzidos por cruzamentos cartesianos entre PCs que já estavam textualmente casados no mesmo contexto.",
        "No plano específico das violações, a saída bruta contém "
        + _fmt_int(overall["raw_violations"])
        + " violações, a saída deduplicada contém "
        + _fmt_int(overall["dedup_violations"])
        + " violações e a saída filtrada contém "
        + _fmt_int(overall["filtered_violations"])
        + " violações. Em termos de interpretação científica, a contagem bruta deve ser lida como sensibilidade máxima do detector, a contagem deduplicada como correção de redundância espelhada e a contagem filtrada como melhor aproximação atual do conjunto residual de violações com maior confiabilidade analítica.",
        "Por fim, "
        + _fmt_int(overall["confirmed_false_positives"])
        + " falsos positivos confirmados foram removidos entre a saída deduplicada e a filtrada. Esse número não representa uma simples limpeza cosmética de dados, mas sim o resultado de uma etapa metodologicamente motivada, voltada a reduzir a inflação do conjunto violador causada por combinações artificiais entre PCs já compatíveis no mesmo `(Project, File, Caller, par de APIs)`. Sob a ótica teórica, essa etapa melhora a razão sinal-ruído do estudo sem modificar a baseline de detecção adotada pela pesquisa.",
        "",
        "## Fundamentação Conceitual",
        "Um padrão de uso de API é entendido aqui como uma relação de uso coordenado entre funções interdependentes, em que a presença de uma chamada cria expectativa operacional sobre a presença de outra chamada complementar. Em linguagens como C, essa relação costuma aparecer em protocolos clássicos de aquisição e liberação de recursos, como `malloc`/`free`, `fopen`/`fclose`, `open`/`close` e `socket`/`close`. A correção desse uso não depende apenas da presença isolada das chamadas, mas da coerência entre os contextos em que elas aparecem. Em sistemas configuráveis, essa coerência é tensionada pela variabilidade anotativa implementada por diretivas de pré-processamento, pois trechos distintos do protocolo podem ser incluídos ou excluídos conforme combinações de macros e expressões booleanas. Como consequência, o protocolo pode permanecer íntegro em algumas configurações e fragmentado em outras. A noção de violação adotada no relatório, portanto, não se limita à ausência absoluta de uma chamada complementar, mas à divergência entre as condições de presença sob as quais as partes do padrão aparecem. Essa formulação permite analisar o problema sob a ótica de sistemas configuráveis, em que a variabilidade não é ruído, mas parte constitutiva do fenômeno investigado.",
        "",
        "## Metodologia e Pipeline Analítico",
        "O pipeline analítico é composto por cinco etapas. A primeira etapa é a ingestão e normalização dos dados de chamadas, em que cada ocorrência é representada por `Project`, `File`, `Caller`, `Callee` e `PC`. A segunda etapa é a detecção não ordenada baseada em comparação textual de condições de presença. Nessa etapa, para cada contexto `(Project, File, Caller)` e para cada par do catálogo, o sistema constrói os conjuntos de PCs observados em cada lado do padrão e avalia o produto cartesiano entre esses conjuntos. Quando `PC_A != PC_B`, a linha é marcada como potencial violação.",
        "A terceira etapa é a deduplicação de espelhamentos. Como os padrões são tratados de forma não ordenada, o detector pode gerar pares logicamente equivalentes, por exemplo `(fopen, fclose, TRUE, ENABLE_CLOSE)` e `(fclose, fopen, ENABLE_CLOSE, TRUE)`. A deduplicação transforma esses casos em uma representação canônica baseada em contexto fixo, par de APIs ordenado lexicograficamente, par de PCs ordenado lexicograficamente e rótulo de violação. Assim, linhas espelhadas que representam o mesmo fato analítico são reduzidas a uma única ocorrência. Essa etapa é importante porque evita inflacionar artificialmente o conjunto de violações apenas por simetria estrutural.",
        "A quarta etapa é a análise posterior de falsos positivos pelo Match-First Filtering. Nessa etapa, para cada `(Project, File, Caller, par de APIs)`, o sistema reconstrói os conjuntos de PCs de ambos os lados e calcula a interseção textual exata entre eles. Se um `YES` foi produzido entre dois PCs que já pertencem ao conjunto casado, esse `YES` é reclassificado como falso positivo confirmado, pois ele resulta de um cruzamento artificial do produto cartesiano e não de uma evidência residual forte de violação. Um exemplo típico ocorre quando um mesmo caller contém `fopen` e `fclose` em `TRUE`, `WIN32` e `!WIN32`: os pares casados `TRUE/TRUE`, `WIN32/WIN32` e `!WIN32/!WIN32` são evidência de correspondência correta, ao passo que combinações como `TRUE/WIN32` podem surgir apenas da multiplicação cruzada entre instâncias diferentes.",
        "A quinta etapa é a geração dos relatórios e visualizações. Ela consolida a saída filtrada, produz estatísticas agregadas, ranqueamentos por padrão e por sistema, e cria os gráficos que sustentam a interpretação final do estudo. Em termos de rigor metodológico, essa arquitetura em camadas separa sensibilidade observacional, correção de redundância, qualificação analítica e comunicação científica dos resultados.",
        "",
        "## Questões de Pesquisa",
        "1. Quantos padrões de uso do catálogo são observados por sistema?",
        "2. Quantos padrões de uso são observados por arquivo?",
        "3. Quantas variabilidades distintas são observadas por sistema?",
        "4. Quantas variabilidades distintas são observadas por arquivo?",
        "5. Quantos padrões de uso são observados em arquivo?",
        "6. Quantos padrões de uso estão em variabilidade parcial ou total?",
        "7. Quantas variabilidades aparecem associadas a padrões de uso, considerando padrões distintos e padrões repetidos entre variabilidades?",
        "8. Qual é o número total de violações?",
        "9. Quais são os padrões de uso mais violados?",
        "10. Como as violações se distribuem entre os tipos parcial e total?",
        "11. Quantos sistemas apresentam violações?",
        "12. Quantas violações são observadas por sistema?",
        "",
        "## Respostas Integradas às Questões de Pesquisa",
        "### RQ1. Número de padrões de uso por sistema",
        f"A saída filtrada contém {_fmt_int(rq_overall['sistemas_com_padrao'])} sistemas com pelo menos um padrão observado. A tabela abaixo mostra os sistemas mais densos em padrões.",
        _kv_table_block(
            "Métrica",
            "Valor",
            [
                ("Sistemas com pelo menos um padrão", _fmt_int(rq_overall["sistemas_com_padrao"])),
                ("Padrões distintos observados", _fmt_int(rq_overall["padroes_distintos"])),
                ("Instâncias totais de padrão", _fmt_int(stage.loc["filtered", "Rows"])),
            ],
        ),
        _table_block(rq.patterns_per_system, ["Project", "padroes_distintos", "instancias_de_padrao", "arquivos_com_padrao"]),
        "",
        "### RQ2 e RQ5. Padrões de uso por arquivo",
        "A análise por arquivo distingue duas leituras complementares. A primeira mede instâncias de padrão por arquivo, isto é, carga observada. A segunda mede padrões distintos do catálogo observados por arquivo, isto é, diversidade protocolar. Ambas são relevantes porque arquivos com muitas instâncias não necessariamente exibem grande diversidade, e arquivos com muitos padrões distintos tendem a concentrar maior complexidade funcional.",
        _kv_table_block(
            "Métrica",
            "Valor",
            [
                ("Arquivos com pelo menos um padrão", _fmt_int(rq_overall["arquivos_com_padrao"])),
                ("Máximo de instâncias em um arquivo", _fmt_int(rq.patterns_per_file["instancias_de_padrao"].max())),
                ("Máximo de padrões distintos em um arquivo", _fmt_int(rq.patterns_per_file["padroes_distintos"].max())),
            ],
        ),
        _table_block(rq.patterns_per_file, ["Project", "File", "padroes_distintos", "instancias_de_padrao", "callers_com_padrao"]),
        "",
        "### RQ3 e RQ4. Variabilidade por sistema e por arquivo",
        f"O corpus contém {_fmt_int(rq_overall['variabilidades_distintas_no_corpus'])} expressões distintas de variabilidade. As tabelas abaixo mostram os produtos e arquivos com maior densidade configuracional.",
        _kv_table_block(
            "Métrica",
            "Valor",
            [
                ("Variabilidades distintas no corpus", _fmt_int(rq_overall["variabilidades_distintas_no_corpus"])),
                ("Máximo de variabilidades em um sistema", _fmt_int(rq.variability_per_system["variabilidades_distintas"].max())),
                ("Máximo de variabilidades em um arquivo", _fmt_int(rq.variability_per_file["variabilidades_distintas"].max())),
            ],
        ),
        _table_block(rq.variability_per_system, ["Project", "variabilidades_distintas", "ocorrencias_variaveis", "arquivos_com_variabilidade"]),
        _table_block(rq.variability_per_file, ["Project", "File", "variabilidades_distintas", "ocorrencias_variaveis"]),
        "",
        "### RQ6 e RQ7. Padrões em variabilidade e variabilidades com padrões",
        f"Há {_fmt_int(rq_overall['instancias_de_padrao_em_variabilidade'])} instâncias de padrão em variabilidade e {_fmt_int(rq_overall['padroes_distintos_em_variabilidade'])} padrões distintos nesse subconjunto. As instâncias se distribuem em {_fmt_int(int(rq.violation_types.loc[rq.violation_types['Tipo'] == 'partial', 'Quantidade'].iloc[0]))} violações parciais e {_fmt_int(int(rq.violation_types.loc[rq.violation_types['Tipo'] == 'total', 'Quantidade'].iloc[0]))} violações totais, enquanto as associações entre variabilidade e padrões somam {_fmt_int(rq_overall['variabilidades_com_padrao'])} variabilidades com padrão, {_fmt_int(rq_overall['ligacoes_distintas_padrao_variabilidade'])} ligações distintas e {_fmt_int(rq_overall['ligacoes_repetidas_padrao_variabilidade'])} ligações repetidas.",
        _kv_table_block(
            "Métrica",
            "Valor",
            [
                ("Instâncias de padrão em variabilidade", _fmt_int(rq_overall["instancias_de_padrao_em_variabilidade"])),
                ("Padrões distintos em variabilidade", _fmt_int(rq_overall["padroes_distintos_em_variabilidade"])),
                ("Variabilidades com padrão", _fmt_int(rq_overall["variabilidades_com_padrao"])),
                ("Ligações distintas padrão-variabilidade", _fmt_int(rq_overall["ligacoes_distintas_padrao_variabilidade"])),
                ("Ligações repetidas padrão-variabilidade", _fmt_int(rq_overall["ligacoes_repetidas_padrao_variabilidade"])),
            ],
        ),
        _table_block(rq.patterns_in_variability_by_system, ["Project", "padroes_distintos_em_variabilidade", "instancias_em_variabilidade", "instancias_parciais", "instancias_totais"]),
        _table_block(rq.variability_with_patterns, ["PC", "padroes_distintos", "ligacoes_repetidas", "sistemas_afetados"]),
        "",
        "### RQ8. Número total de violações",
        "O pipeline completo preserva a rastreabilidade entre os estágios. As contagens são as seguintes:",
        _kv_table_block(
            "Estágio",
            "Violações",
            [
                ("Saída bruta", _fmt_int(stage.loc["raw", "YES"])),
                ("Saída deduplicada", _fmt_int(stage.loc["dedup", "YES"])),
                ("Saída filtrada", _fmt_int(stage.loc["filtered", "YES"])),
            ],
        ),
        "",
        "### RQ9 e RQ10. Padrões mais violados e tipos de violação",
        f"O padrão mais violado é `{top_pair['Pattern']}`, com {_fmt_int(top_pair['yes_rows'])} violações na visão agregada por par e `{rq.violated_patterns.iloc[0]['Pattern']}` com {_fmt_int(rq.violated_patterns.iloc[0]['violacoes'])} violações na visão orientada por RQ. A decomposição entre `partial` e `total` ajuda a distinguir entre assimetrias locais e protocolos inteiramente imersos em variabilidade.",
        _kv_table_block(
            "Métrica",
            "Valor",
            [
                ("Padrão mais violado", top_pair["Pattern"]),
                ("Violações do padrão líder", _fmt_int(top_pair["yes_rows"])),
                ("Violações parciais", _fmt_int(rq.violation_types.loc[rq.violation_types["Tipo"] == "partial", "Quantidade"].iloc[0])),
                ("Violações totais", _fmt_int(rq.violation_types.loc[rq.violation_types["Tipo"] == "total", "Quantidade"].iloc[0])),
            ],
        ),
        _table_block(rq.violated_patterns, ["Pattern", "violacoes", "sistemas_afetados", "violacoes_parciais", "violacoes_totais"]),
        _table_block(rq.violation_types, ["Tipo", "Quantidade"]),
        "",
        "### RQ11 e RQ12. Quantidade de sistemas com violações e violações por sistema",
        f"Há {_fmt_int(rq_viol['produtos_com_violacao'])} sistemas com pelo menos uma violação. O sistema mais afetado é `{top_product['Project']}`, com {_fmt_int(top_product['violacoes'])} violações filtradas. Na visão agregada do pipeline, `{top_system['Project']}` também aparece como sistema mais crítico, com taxa de violação de {_fmt_pct(top_system['yes_rate'])}.",
        _kv_table_block(
            "Métrica",
            "Valor",
            [
                ("Sistemas com pelo menos uma violação", _fmt_int(rq_viol["produtos_com_violacao"])),
                ("Sistema mais afetado", top_product["Project"]),
                ("Violações no sistema líder", _fmt_int(top_product["violacoes"])),
                ("Taxa de violação do sistema líder", _fmt_pct(top_system["yes_rate"])),
            ],
        ),
        _table_block(rq.violations_per_product, ["Project", "violacoes", "padroes_violados_distintos", "violacoes_parciais", "violacoes_totais"]),
        "",
        "## Discussão dos Resultados",
        "Os resultados mostram que o corpus possui forte heterogeneidade estrutural e configuracional. Poucos sistemas concentram grande parte das instâncias de padrão, das variabilidades e das violações, e os protocolos mais problemáticos pertencem majoritariamente ao domínio de gerenciamento de recursos. Além disso, a separação nítida entre contextos sem variabilidade e contextos com violações residuais reforça a leitura de que a variabilidade por pré-processamento não é um detalhe periférico, mas um fator explicativo central para o fenômeno observado. A análise de falsos positivos, por sua vez, mostra que parte da carga inicial de violações era inflacionada por artefatos do produto cartesiano, o que justifica a necessidade de uma etapa explícita de refinamento analítico.",
        "",
        "## Interpretação Integrada das Figuras",
        "As figuras abaixo consolidam os gráficos das linhas anteriores de relatório. Cada uma deve ser lida como evidência para uma parte específica das questões de pesquisa e da interpretação científica do fenômeno.",
    ]

    for title, fig_path, explanation in _figure_sections(paths):
        rel = fig_path.relative_to(paths.base_dir)
        content.extend(["", f"### {title}", f"![{title}]({rel.as_posix()})", explanation])

    content.extend(
        [
            "",
            "## Ameaças à Validade",
            "Há pelo menos quatro ameaças à validade que precisam ser explicitadas. Primeiro, a análise permanece intencionalmente baseada em comparação textual de condições de presença, o que significa que equivalências lógicas entre expressões diferentes não são exploradas. Segundo, a noção de padrão continua não ordenada, em conformidade com a decisão metodológica da pesquisa, mas essa escolha pode influenciar a forma como alguns contextos complexos são agregados. Terceiro, a identificação de falsos positivos adotada aqui é operacional e conservadora: ela captura cruzamentos artificiais entre PCs já casados no mesmo contexto, mas não pretende esgotar todas as formas possíveis de falso positivo. Quarto, as medidas de concentração por sistema e por arquivo devem sempre ser interpretadas juntamente com a escala do produto, já que sistemas grandes tendem naturalmente a acumular mais ocorrências observáveis.",
            "",
            "## Achados Principais",
            f"1. O pipeline reduz as violações de {_fmt_int(stage.loc['raw', 'YES'])} na saída bruta para {_fmt_int(stage.loc['filtered', 'YES'])} na saída filtrada, mostrando que deduplicação e filtragem de falsos positivos são etapas analiticamente indispensáveis.",
            f"2. O fenômeno residual é fortemente concentrado em poucos protocolos, com destaque para `{top_pair['Pattern']}`.",
            f"3. O problema se concentra exclusivamente em contextos com variabilidade, já que a classe `none` não contém violações residuais.",
            f"4. Há {_fmt_int(rq_viol['produtos_com_violacao'])} produtos afetados, o que mostra que o fenômeno não é isolado, embora se concentre em poucos sistemas no topo do ranking.",
            f"5. A análise de falsos positivos remove {_fmt_int(overall['confirmed_false_positives'])} casos confirmados e melhora a confiabilidade interpretativa do conjunto final.",
            "",
            "## Conclusão",
            "O relatório mestre consolidado mostra que o repositório já oferece uma cadeia experimental suficientemente madura para sustentar análises sobre violações de padrões de uso de APIs em sistemas configuráveis em C/C++. A principal contribuição deste documento unificado é reunir, em uma única peça, a visão operacional do pipeline, a fundamentação conceitual alinhada ao exame de qualificação, a metodologia de geração dos resultados, as respostas objetivas às questões de pesquisa, a discussão integrada dos achados e a interpretação detalhada dos gráficos. Com isso, o relatório deixa de ser apenas uma coleção de saídas e passa a funcionar como artefato central de análise científica para a tese.",
        ]
    )

    paths.markdown_path.write_text("\n\n".join(content), encoding="utf-8")


def write_unified_pdf_report(paths: UnifiedReportPaths) -> None:
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
        title="Violação de Padrão de uso de API em Sistemas Configuráveis em C",
        author="OpenAI Codex",
    )
    story = []
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
                table = _code_block_to_table(paragraph)
                if table is not None:
                    story.append(table)
                    story.append(Spacer(1, 0.15 * cm))
                else:
                    code_text = paragraph.strip("`").strip().replace("\n", "<br/>")
                    story.append(Paragraph(f"<font face='Courier'>{code_text}</font>", styles["BodyDense"]))
            else:
                story.append(Paragraph(paragraph, styles["BodyDense"]))
        if idx != len(sections) - 1:
            story.append(PageBreak())
    doc.build(story)


def generate_unified_master_report(
    pc_csv_path: Path,
    raw_path: Path,
    dedup_path: Path,
    out_dir: Path,
) -> UnifiedReportPaths:
    paths = UnifiedReportPaths.build(out_dir)
    paths.base_dir.mkdir(parents=True, exist_ok=True)
    paths.technical_figures_dir.mkdir(parents=True, exist_ok=True)
    paths.rq_figures_dir.mkdir(parents=True, exist_ok=True)
    paths.technical_tables_dir.mkdir(parents=True, exist_ok=True)
    paths.rq_tables_dir.mkdir(parents=True, exist_ok=True)

    report_paths = ReportPaths(
        base_dir=paths.base_dir,
        figures_dir=paths.technical_figures_dir,
        tables_dir=paths.technical_tables_dir,
        markdown_path=paths.markdown_path,
        pdf_path=paths.pdf_path,
        fp_analysis_path=paths.fp_analysis_path,
        filtered_output_path=paths.filtered_output_path,
    )
    loaded = load_datasets(raw_path=raw_path, dedup_path=dedup_path, report_paths=report_paths)
    technical = build_metrics(loaded)
    write_metric_tables(technical, paths.technical_tables_dir)
    generate_all_plots(technical, paths.technical_figures_dir)

    pc_calls = _load_pc_calls(pc_csv_path)
    raw = _normalize_output(pd.read_csv(raw_path))
    dedup = _normalize_output(pd.read_csv(dedup_path))
    filtered = _normalize_output(pd.read_csv(paths.filtered_output_path))
    rq = build_rq_metrics(pc_calls, raw, dedup, filtered)
    write_rq_tables(rq, paths.rq_tables_dir)
    generate_rq_plots(rq, paths.rq_figures_dir)

    write_unified_markdown_report(technical, rq, paths)
    write_unified_pdf_report(paths)
    return paths
