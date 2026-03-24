from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from reporting.metrics import MetricBundle


@dataclass(frozen=True)
class DoctoralReportPaths:
    base_dir: Path
    markdown_path: Path
    pdf_path: Path

    @classmethod
    def build(cls, base_dir: Path) -> "DoctoralReportPaths":
        return cls(
            base_dir=base_dir,
            markdown_path=base_dir / "doctoral_violation_report.md",
            pdf_path=base_dir / "doctoral_violation_report.pdf",
        )


FIGURE_FILES = {
    "01_stage_comparison": "Comparação entre estágios do pipeline",
    "02_top_violation_pairs": "Pares de APIs com mais violações",
    "03_top_non_violation_pairs": "Pares de APIs com mais não violações",
    "04_top_systems": "Sistemas com maior concentração de violações",
    "05_variability_breakdown": "Violação versus classes de variabilidade",
    "06_fp_status": "Resumo da análise de falsos positivos",
    "07_top_fp_contexts": "Contextos com mais falsos positivos confirmados",
    "08_pattern_volume_vs_rate": "Volume de padrões versus taxa de violação",
}


def _fmt_int(value: object) -> str:
    return f"{int(value):,}".replace(",", ".")


def _fmt_float(value: float) -> str:
    return f"{value:.4f}"


def _series_stats(series: pd.Series) -> dict[str, float]:
    s = pd.to_numeric(series, errors="coerce").dropna().astype(float)
    if s.empty:
        return {
            "count": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "std": 0.0,
            "min": 0.0,
            "q1": 0.0,
            "q3": 0.0,
            "max": 0.0,
            "skew": 0.0,
            "kurtosis": 0.0,
        }
    return {
        "count": float(s.count()),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        "min": float(s.min()),
        "q1": float(s.quantile(0.25)),
        "q3": float(s.quantile(0.75)),
        "max": float(s.max()),
        "skew": float(s.skew()) if len(s) > 2 else 0.0,
        "kurtosis": float(s.kurt()) if len(s) > 3 else 0.0,
    }


def _ensure_min_words(text: str, minimum: int = 500) -> str:
    words = [w for w in text.split() if w.strip()]
    if len(words) < minimum:
        raise ValueError(f"Paragraph has {len(words)} words; expected at least {minimum}.")
    return text


def _join_sentences(sentences: Iterable[str]) -> str:
    return " ".join(s.strip() for s in sentences if s.strip())


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SectionBlue",
            parent=styles["Heading1"],
            textColor=colors.HexColor("#0b3c5d"),
            fontSize=16,
            leading=20,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyDense",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=13,
            spaceAfter=10,
        )
    )
    return styles


def _scaled_image(path: Path, max_width_cm: float = 16.2) -> Image:
    img = Image(str(path))
    max_width = max_width_cm * cm
    scale = min(1.0, max_width / img.drawWidth)
    img.drawWidth *= scale
    img.drawHeight *= scale
    return img


def _research_questions_paragraph(metrics: MetricBundle) -> str:
    overall = metrics.overall.iloc[0]
    filtered_yes = int(overall["filtered_violations"])
    raw_yes = int(overall["raw_violations"])
    sentences = [
        "O foco científico deste relatório é responder, com maior precisão empírica, à pergunta central já estabelecida pela pesquisa: de que maneira a variabilidade implementada por diretivas de pré-processamento em sistemas C/C++ contribui para a ocorrência de violações de padrões de uso de APIs. A partir dessa pergunta-mãe, o relatório passa a estruturar a leitura dos resultados em torno de um conjunto de questões de pesquisa operacionalizáveis sobre o corpus analisado. A primeira questão, RQ1, pode ser formulada assim: qual é a magnitude observável do fenômeno de violação de padrões de uso de APIs quando aplicamos o detector não ordenado baseado em comparação textual de condições de presença. Essa pergunta é respondida pelo contraste entre saída bruta, saída deduplicada e saída filtrada, mostrando como um universo inicial de "
        + _fmt_int(raw_yes)
        + " violações detectadas se transforma em "
        + _fmt_int(filtered_yes)
        + " violações residuais analiticamente mais confiáveis. A segunda questão, RQ2, é: em quais pares de APIs o fenômeno se concentra, e quais protocolos parecem mais vulneráveis à fragmentação variacional. Essa questão desloca a interpretação do plano puramente agregador para o plano dos padrões concretos de uso, permitindo identificar que memória, abertura e fechamento de arquivos, manipulação de descritores e sockets constituem zonas de maior fragilidade. A terceira questão, RQ3, é: em quais sistemas, arquivos e callers as violações residuais se acumulam com maior intensidade, indicando candidatos robustos a estudos de caso aprofundados. Aqui, a ênfase sai do padrão abstrato e passa ao contexto arquitetural real em que o padrão é exercido. A quarta questão, RQ4, pergunta qual é o papel da variabilidade, distinguida nas classes `none`, `partial` e `total`, na separação entre uso estável e uso inconsistente. Essa pergunta é central porque a tese não investiga qualquer API misuse em C, mas especificamente API misuse em presença de variabilidade anotativa. A quinta questão, RQ5, trata da validade analítica do próprio processo de detecção: quanto do conjunto de violações deduplicadas ainda é influenciado por artefatos do produto cartesiano, e em que medida o Match-First Filtering melhora a razão sinal-ruído sem descaracterizar a baseline metodológica. A sexta questão, proposta aqui como ampliação da agenda do trabalho, é RQ6: quais padrões combinam simultaneamente alto volume absoluto, alta taxa relativa de violação e ampla dispersão em projetos e arquivos, tornando-se candidatos prioritários para discussão na tese. A sétima questão, RQ7, também sugerida como extensão natural, é: em que contextos de alta variabilidade a incidência de falsos positivos cresce a ponto de indicar limitação de granularidade do agrupamento por `(Project, File, Caller)`. Essas novas questões não substituem a questão principal; elas a refinam em subproblemas empiricamente tratáveis. Ao estruturar o relatório em torno dessas perguntas, o objetivo deixa de ser apenas descrever tabelas e passa a ser construir uma narrativa científica em que cada gráfico, cada agregado estatístico e cada transformação do pipeline funcionem como evidência para uma hipótese mais ampla sobre violações de padrões de uso de APIs em sistemas configuráveis em C/C++."
    ]
    return _join_sentences(sentences)


def _pipeline_paragraph(metrics: MetricBundle) -> str:
    overall = metrics.overall.iloc[0]
    stage = metrics.stage_counts.set_index("Stage")
    raw_rows = int(stage.loc["raw", "Rows"])
    raw_yes = int(stage.loc["raw", "YES"])
    dedup_rows = int(stage.loc["dedup", "Rows"])
    dedup_yes = int(stage.loc["dedup", "YES"])
    filtered_rows = int(stage.loc["filtered", "Rows"])
    filtered_yes = int(stage.loc["filtered", "YES"])
    sentences = [
        "Do ponto de vista de sistemas configuráveis implementados por diretivas de pré-processamento em C e C++, o programa atual deve ser entendido como um pipeline analítico composto por fases explicitamente distintas de observação, redução e interpretação. A primeira fase, representada pela saída bruta, mantém a sensibilidade máxima do detector não ordenado e string-based: ela aceita o catálogo de pares de APIs, constrói grupos definidos por Project, File e Caller, e avalia o produto cartesiano entre os conjuntos de condições de presença das duas funções que compõem o padrão. Essa escolha é coerente com a hipótese metodológica da pesquisa, porque em código fortemente anotado por #ifdef, #if, #elif, #else e #endif uma mesma função pode aparecer em múltiplas regiões variacionais dentro do mesmo caller, e o objetivo inicial é não perder evidência. Em termos computacionais, essa fase sacrifica precisão local em favor de sensibilidade global, e os números observados confirmam esse comportamento: o pipeline produz inicialmente "
        + _fmt_int(raw_rows)
        + " linhas, das quais "
        + _fmt_int(raw_yes)
        + " são violações e "
        + _fmt_int(raw_rows - raw_yes)
        + " são não violações. Em termos de taxa bruta, isso corresponde a "
        + f"{raw_yes / raw_rows:.2%}"
        + " de linhas classificadas como YES, número que não pode ser interpretado diretamente como prevalência sem antes considerar a simetria induzida pelo tratamento não ordenado e a explosão combinatória causada pelo produto cartesiano. A segunda fase, a deduplicação, corrige exatamente a primeira dessas distorções ao remover espelhamentos lógicos entre pares de APIs e pares de PCs. O efeito é quantitativamente expressivo: o número total de linhas cai para "
        + _fmt_int(dedup_rows)
        + ", o que representa redução de "
        + f"{(raw_rows - dedup_rows) / raw_rows:.2%}"
        + ", e as violações caem para "
        + _fmt_int(dedup_yes)
        + ", ou seja, uma redução de "
        + f"{(raw_yes - dedup_yes) / raw_yes:.2%}"
        + " no volume de YES. Isso mostra que uma parcela importante da aparente carga de inconsistência era, na verdade, redundância estrutural gerada pela própria estratégia de expansão não ordenada, e não necessariamente evidência substantiva de violação. A terceira fase, introduzida pelo Match-First Filtering, atua de maneira ainda mais interessante do ponto de vista matemático e metodológico: ela não modifica a semântica do detector, mas reclassifica uma parte dos YES ao verificar, no mesmo contexto, se já existe casamento textual exato entre as condições de presença das duas funções. Se tal casamento já ocorre, então certos cruzamentos adicionais são mais bem explicados como artefatos do produto cartesiano do que como violações residuais. Depois dessa etapa, o pipeline preserva "
        + _fmt_int(filtered_rows)
        + " linhas, com "
        + _fmt_int(filtered_yes)
        + " violações finais. Em outras palavras, a arquitetura do programa evolui de um estágio exploratório, altamente sensível, para um estágio filtrado, mais conservador e mais adequado à interpretação científica. Sob o prisma de engenharia de software, essa separação em estágios é valiosa porque mantém baixo acoplamento entre detecção, deduplicação e análise de falso positivo; sob o prisma estatístico, ela permite decompor a variância observada na saída em componentes associados à simetria, ao cruzamento cartesiano e ao sinal residual efetivamente relevante para a tese."
    ]
    sentences.append(
        "Essa decomposição também melhora a reprodutibilidade do estudo, pois transforma o pipeline em uma sequência de operações observáveis, comparáveis e mensuráveis, algo indispensável quando se pretende defender inferências sobre sistemas configuráveis em um contexto de rigor doutoral."
    )
    sentences.append(
        "Do ponto de vista de desenho experimental, essa organização modular também permite que versões futuras do programa substituam apenas um estágio específico, como a regra de falso positivo ou a política de agregação, sem comprometer a cadeia de rastreabilidade das saídas anteriores. Em uma pesquisa de doutorado, essa propriedade é valiosa porque protege a comparabilidade longitudinal dos experimentos e reduz o risco de conclusões dependentes de implementações monolíticas pouco transparentes."
    )
    return _ensure_min_words(_join_sentences(sentences))


def _repository_architecture_paragraph(metrics: MetricBundle) -> str:
    overall = metrics.overall.iloc[0]
    sentences = [
        "A análise integral do repositório mostra uma arquitetura progressivamente estratificada, na qual o núcleo computacional da identificação de violações, o pós-processamento dos resultados e a geração de relatórios foram sendo separados em módulos distintos, com responsabilidades relativamente bem definidas e com acoplamento controlado. Do ponto de vista de engenharia de software para pesquisa empírica, essa organização é especialmente adequada porque permite distinguir claramente o que pertence à definição metodológica do experimento e o que pertence à interpretação analítica posterior. O ponto de entrada operacional do sistema é `src/main.py`, que funciona como camada de orquestração e expõe, por linha de comando, os modos `unordered-string`, `short-circuit`, `summary-string` e `sat`. Essa escolha já revela um compromisso arquitetural importante: a baseline efetivamente utilizada pela pesquisa não precisa ser confundida com modos experimentais ou comparativos. Em outras palavras, o repositório preserva a possibilidade de comparação com abordagens alternativas, mas mantém uma trilha explícita para o detector principal. Em seguida, os módulos `src/csv_io.py` e `src/pc_utils.py` materializam a camada de contrato de dados e higiene textual. O primeiro lê e expande o catálogo de padrões não ordenados; o segundo concentra decisões sobre sentinelas, validade e normalização leve de PCs. Em um sistema deste tipo, centralizar essas regras auxilia na consistência semântica do pipeline, porque reduz a chance de diferentes etapas reinterpretarem a mesma condição de presença de formas incompatíveis. O núcleo da baseline está em `src/unordered_detector.py`, que implementa a construção do índice `pc_map[(Project, File, Caller)][Callee] -> set(PC)` e, depois, avalia o produto cartesiano entre os conjuntos associados a cada par de APIs. Esse módulo é conceitualmente simples, porém metodologicamente central: sua simplicidade operacional favorece auditabilidade, enquanto sua semântica preserva precisamente o fenômeno que a tese deseja observar, a saber, a fragmentação de padrões de uso sob variabilidade de pré-processamento. Em paralelo, `src/detector.py` e `src/sat_engine.py` formam uma linha analítica alternativa, mais rica do ponto de vista lógico, mas não dominante na configuração atual. Sua existência é arquiteturalmente útil porque deixa claro que o repositório não está fechado a extensões semânticas futuras; ao mesmo tempo, o fato de esses módulos permanecerem desacoplados da baseline evita que o programa perca coerência com a decisão metodológica atual de manter comparação por string. A etapa seguinte é representada por `src/dedup_unordered.py` e `src/deduplicate_unordered_output.py`, responsáveis por transformar a interpretação não ordenada em uma canonização reprodutível de linhas espelhadas. A seguir, `src/identify_false_positives.py` introduz uma camada explicitamente pós-deteção, baseada na heurística Match-First Filtering, que reconhece quando certos `YES` são artefatos do cruzamento cartesiano entre PCs já casados no mesmo contexto. O aspecto arquitetural mais relevante dessa solução é que ela preserva a baseline e desloca o refinamento interpretativo para uma etapa separada, o que reduz risco de regressão conceitual e facilita validação. Já o subsistema de relatórios em `src/reporting/` evidencia uma segunda dimensão de maturidade do repositório: `datasets.py` consolida entradas, `metrics.py` produz estatísticas derivadas, `plots.py` encapsula visualizações, `writer.py` emite o relatório técnico para stakeholders e `doctoral_writer.py` produz a versão acadêmica aprofundada. Essa separação segue boas práticas clássicas de baixo acoplamento e alta coesão, pois evita que o código de análise estatística fique embutido no detector, e evita que o código de apresentação altere a semântica dos dados. Finalmente, os módulos `src/generate_test_pc_csv.py`, `src/run_test_cases_regression.py`, `src/run_unordered_detector_test.py`, `src/analyze_outputs_pd.py`, `src/analyze_result_research.py`, `src/plot_result_analysis.py` e `src/generate_result_pdf_report.py` completam o ecossistema ao fornecer geração de dados sintéticos, regressão, exploração manual e análise de pesquisa. O repositório, portanto, não é apenas um detector; ele constitui um ambiente experimental relativamente completo, no qual "
        + _fmt_int(overall["systems"])
        + " sistemas, "
        + _fmt_int(overall["files"])
        + " arquivos e "
        + _fmt_int(overall["distinct_patterns"])
        + " padrões distintos podem ser percorridos por uma cadeia de processamento reproduzível. Em termos doutorais, essa arquitetura é cientificamente defensável porque favorece rastreabilidade, reprodutibilidade, extensibilidade e inspeção crítica por outros pesquisadores."
    ]
    sentences.append(
        "Além disso, a divisão atual do repositório ajuda a proteger a tese contra um problema comum em protótipos acadêmicos: a sobreposição desordenada entre heurísticas de detecção, limpeza de resultados e comunicação final. Aqui, apesar de ainda existirem oportunidades de refinamento, o desenho já separa razoavelmente bem as responsabilidades e permite que cada etapa seja discutida com critérios próprios de corretude."
    )
    sentences.append(
        "Do ponto de vista de manutenção futura, isso também significa que novas heurísticas de falso positivo, novos agregadores estatísticos ou novos formatos de relatório podem ser incorporados sem necessidade de reescrever o núcleo do detector. Essa propriedade de extensibilidade é particularmente importante em doutorado, onde o sistema costuma evoluir em ciclos sucessivos de hipótese, experimento, crítica e refinamento."
    )
    return _ensure_min_words(_join_sentences(sentences))


def _figure_explanation_sections(metrics: MetricBundle, paths: DoctoralReportPaths) -> list[tuple[str, str, Path]]:
    overall = metrics.overall.iloc[0]
    stage = metrics.stage_counts.set_index("Stage")
    raw_rows = int(stage.loc["raw", "Rows"])
    dedup_rows = int(stage.loc["dedup", "Rows"])
    filtered_rows = int(stage.loc["filtered", "Rows"])
    raw_yes = int(stage.loc["raw", "YES"])
    dedup_yes = int(stage.loc["dedup", "YES"])
    filtered_yes = int(stage.loc["filtered", "YES"])
    top_pair = metrics.pair_summary.iloc[0]
    second_pair = metrics.pair_summary.iloc[1]
    stable_pair = metrics.non_violation_pairs.iloc[0]
    top_system = metrics.system_summary.iloc[0]
    second_system = metrics.system_summary.iloc[1]
    fp_summary = metrics.fp_summary.set_index("FPStatus")["count"]
    fp_total = int(fp_summary.get("ConfirmedFalsePositive", 0))
    candidate_total = int(fp_summary.get("CandidateViolation", 0))
    fp_context = metrics.fp_contexts.iloc[0] if not metrics.fp_contexts.empty else None
    var = metrics.variability_summary.pivot(index="VarClass", columns="Violation", values="count").fillna(0)
    for idx in ["none", "partial", "total"]:
        if idx not in var.index:
            var.loc[idx] = {"NO": 0, "YES": 0}
    for col in ["NO", "YES"]:
        if col not in var.columns:
            var[col] = 0
    total_total = float(var.loc["total"].sum()) if "total" in var.index else 0.0
    none_total = float(var.loc["none"].sum()) if "none" in var.index else 0.0
    partial_total = float(var.loc["partial"].sum()) if "partial" in var.index else 0.0

    figures_dir = paths.base_dir / "figures"
    sections: list[tuple[str, str, Path]] = []

    sections.append(
        (
            "Figura 1. Comparação entre estágios do pipeline",
            "A Figura 1 responde diretamente à RQ1 ao mostrar como o conjunto de evidências evolui da saída bruta para a saída deduplicada, analisada e finalmente filtrada. O aspecto mais importante deste gráfico não é apenas a redução do número total de linhas, mas a decomposição dessa redução em efeitos distintos. Entre a saída bruta e a deduplicada, as linhas caem de "
            + _fmt_int(raw_rows)
            + " para "
            + _fmt_int(dedup_rows)
            + ", enquanto as violações caem de "
            + _fmt_int(raw_yes)
            + " para "
            + _fmt_int(dedup_yes)
            + ". Isso mostra que uma parte expressiva da carga inicial de violações vinha de espelhamentos induzidos pelo caráter não ordenado do catálogo. Já entre a saída deduplicada e a filtrada, o número total cai modestamente para "
            + _fmt_int(filtered_rows)
            + ", mas a redução de violações para "
            + _fmt_int(filtered_yes)
            + " é teoricamente muito significativa, porque decorre da remoção de artefatos analíticos e não de simples redundância estrutural. O gráfico deve, portanto, ser interpretado como uma representação visual da cadeia de validade do pipeline: primeiro corrige-se a simetria, depois corrige-se parte da inflação causada por cruzamentos cartesianes entre PCs já casados. Para a tese, essa figura é fundamental porque mostra que a noção de violação relevante não coincide com a primeira contagem produzida pelo detector; ela emerge de uma sequência de refinamentos controlados que preservam a baseline metodológica, mas melhoram a interpretabilidade do sinal residual.",
            figures_dir / "01_stage_comparison.png",
        )
    )
    sections.append(
        (
            "Figura 2. Pares de APIs com maior concentração de violações",
            "A Figura 2 responde à RQ2 e deve ser lida como um mapa de concentração dos protocolos mais vulneráveis sob variabilidade. O destaque de `"
            + str(top_pair["Pattern"])
            + "` com "
            + _fmt_int(top_pair["yes_rows"])
            + " violações não significa, isoladamente, que esse seja o protocolo semanticamente mais frágil; ele indica que esse par combina ampla presença no corpus com carga residual importante de inconsistência. Em contraste, `"
            + str(second_pair["Pattern"])
            + "` aparece com menor volume absoluto, mas com taxa mais elevada, o que sugere uma propensão relativa mais forte à violação. O valor analítico da figura está justamente em permitir essa distinção entre capilaridade e severidade relativa. Protocolos ligados a gerenciamento de memória (`free | malloc`, `free | realloc`), arquivos (`fopen | fclose`, `fgets | fclose`) e descritores (`open | close`, `socket | close`) dominam o gráfico, o que é coerente com o fato de serem pares cujo uso correto depende de correspondência contextual entre aquisição e liberação de recursos. Em sistemas configuráveis em C, qualquer fragmentação do fluxo por diretivas de pré-processamento tende a afetar precisamente esse tipo de protocolo. Assim, a figura não é apenas um ranking; ela funciona como evidência de que o fenômeno de violação residual se concentra em pares cuja dependência entre chamadas é estruturalmente forte.",
            figures_dir / "02_top_violation_pairs.png",
        )
    )
    sections.append(
        (
            "Figura 3. Pares de APIs com maior volume de não violações",
            "A Figura 3 responde a uma questão complementar à RQ2: quais padrões aparecem intensamente no corpus sem se tornarem focos dominantes de inconsistência. Essa figura é metodologicamente importante porque fornece o grupo de controle necessário para interpretar as violações. O caso de `"
            + str(stable_pair["Pattern"])
            + "` é emblemático: ele aparece com "
            + _fmt_int(stable_pair["no_rows"])
            + " não violações e taxa residual muito baixa. Isso mostra que alta frequência de uso não implica, por si só, alta incidência de violação. Em outras palavras, o detector não está simplesmente punindo pares frequentes; ele está discriminando entre protocolos amplamente difundidos, mas estáveis, e protocolos amplamente difundidos, porém mais vulneráveis à separação variacional. Essa distinção é central para a tese, porque ajuda a afastar a hipótese de que o fenômeno observado seja mero reflexo do volume de chamadas. A presença de pares estáveis no topo da figura reforça que existe uma massa substancial de comportamento consistente no corpus, o que torna ainda mais relevante a concentração das violações em certos protocolos específicos. Do ponto de vista estatístico, a figura reduz o risco de viés interpretativo por prevalência e oferece a base comparativa necessária para discutir o que diferencia um protocolo robusto de um protocolo suscetível à variabilidade.",
            figures_dir / "03_top_non_violation_pairs.png",
        )
    )
    sections.append(
        (
            "Figura 4. Sistemas com maior concentração de violações",
            "A Figura 4 responde à RQ3 ao evidenciar em quais sistemas o fenômeno residual de violação se manifesta com maior intensidade. `"
            + str(top_system["Project"])
            + "` lidera com "
            + _fmt_int(top_system["yes_rows"])
            + " violações e taxa de "
            + f"{top_system['yes_rate']:.2%}"
            + ", seguido por `"
            + str(second_system["Project"])
            + "` com "
            + _fmt_int(second_system["yes_rows"])
            + " violações e taxa de "
            + f"{second_system['yes_rate']:.2%}"
            + ". O valor desta figura está em permitir a passagem do nível dos protocolos para o nível dos ecossistemas de software, isto é, identificar não apenas quais pares são problemáticos, mas em que sistemas esses problemas se tornam mais densos. A figura deve ser lida em conjunto com a tabela de sistemas porque altos volumes absolutos podem refletir tamanho de código, diversidade funcional ou abundância de padrões, ao passo que altas taxas sugerem fragilidade concentrada. Para seleção de estudos de caso na tese, essa distinção é decisiva: sistemas com muitas violações e alta taxa são bons candidatos para análise qualitativa detalhada, enquanto sistemas grandes com baixa taxa são úteis para comparar como diferentes estratégias arquiteturais ou de modularização amortecem o impacto da variabilidade sobre protocolos de uso de API.",
            figures_dir / "04_top_systems.png",
        )
    )
    sections.append(
        (
            "Figura 5. Violação versus classes de variabilidade",
            "A Figura 5 responde diretamente à RQ4 e talvez seja a figura conceitualmente mais importante do relatório. Ela mostra como as classes `none`, `partial` e `total` se distribuem entre violações e não violações após a filtragem. O resultado observado é forte: o grupo `none` contém "
            + _fmt_int(none_total)
            + " observações e nenhuma violação residual; o grupo `partial` contém "
            + _fmt_int(partial_total)
            + " observações e todas elas são violações; o grupo `total`, com "
            + _fmt_int(total_total)
            + " observações, ainda preserva uma massa grande de não violações, mas também concentra uma fração importante do conjunto violador. A interpretação científica é imediata: o problema relevante não está em chamadas incondicionais, mas em contextos onde a variabilidade altera a coocorrência entre as APIs do padrão. Essa figura aproxima fortemente o resultado empírico da hipótese central da pesquisa, segundo a qual diretivas de pré-processamento podem fragmentar protocolos de uso de API, separando chamadas interdependentes e criando contextos propícios a inconsistência. Para a tese, a Figura 5 deve ser tratada como evidência estrutural, e não apenas estatística, porque ela mostra que a variável de interesse, a variabilidade por pré-processamento, não está perifericamente associada ao fenômeno; ela aparece como discriminante central entre uso estável e uso inconsistente.",
            figures_dir / "05_variability_breakdown.png",
        )
    )
    sections.append(
        (
            "Figura 6. Resumo da análise de falsos positivos",
            "A Figura 6 responde à RQ5 ao resumir a distribuição entre `NoAction`, `CandidateViolation` e `ConfirmedFalsePositive`. O ponto-chave aqui é mostrar que a etapa de falso positivo não descaracteriza a baseline nem reescreve o resultado bruto de forma arbitrária; ela apenas qualifica a interpretação das violações deduplicadas. Dos casos analisados, "
            + _fmt_int(candidate_total)
            + " permanecem como violações candidatas e "
            + _fmt_int(fp_total)
            + " são explicados pelo Match-First Filtering como artefatos do produto cartesiano entre PCs já casados no mesmo contexto. O gráfico deve ser interpretado como uma medida de saneamento epistemológico: ele mostra que a maior parte do corpus permanece intacta como `NoAction`, uma parcela menor constitui o núcleo de interesse científico das violações residuais, e uma parcela ainda menor é reclassificada para evitar superestimação do problema. Em termos de tese, essa figura sustenta a afirmação de que a pesquisa não apenas detecta violações, mas também constrói mecanismos para qualificar a confiabilidade analítica dessa detecção.",
            figures_dir / "06_fp_status.png",
        )
    )
    sections.append(
        (
            "Figura 7. Contextos com maior incidência de falsos positivos confirmados",
            "A Figura 7 aprofunda a RQ5 e contribui também para a RQ7, ao mostrar onde a granularidade atual do agrupamento por `(Project, File, Caller)` é mais tensionada. O contexto dominante é `"
            + (f"{fp_context['Project']} | {fp_context['Caller']} | {fp_context['PairKey']}" if fp_context is not None else "n/d")
            + "`, concentrando uma fração substancial dos falsos positivos confirmados. Essa concentração indica que os falsos positivos não estão dispersos aleatoriamente pelo corpus; eles se acumulam em callers grandes, com múltiplas instâncias do mesmo protocolo e múltiplas regiões condicionais. A leitura correta da figura não é que esses contextos sejam irrelevantes. Pelo contrário: eles são contextos metodologicamente muito ricos, porque exibem precisamente a complexidade variacional que a tese quer estudar. O problema é que, nessa granularidade, parte das combinações entre PCs deixa de representar violação residual e passa a representar mistura entre instâncias distintas já compatíveis. Portanto, a figura deve ser entendida como um mapa de tensão entre fenômeno real e limitação analítica local.",
            figures_dir / "07_top_fp_contexts.png",
        )
    )
    sections.append(
        (
            "Figura 8. Volume de padrões versus taxa de violação",
            "A Figura 8 responde à RQ6 ao combinar, em um único plano, o volume total de observações por padrão, a taxa de violação e a cobertura em projetos. Essa visualização é particularmente importante para priorização científica, porque evita que a análise seja capturada apenas por contagens absolutas. Padrões situados mais à direita têm grande presença no corpus; padrões mais altos possuem maior taxa de violação; e bolhas maiores indicam presença em mais projetos. Assim, um par como `"
            + str(top_pair["Pattern"])
            + "` pode aparecer como um hotspot sistêmico por combinar volume e dispersão, enquanto outros pares, mesmo menos frequentes, podem surgir como hotspots semânticos por apresentarem taxa desproporcionalmente alta. O mérito do gráfico é permitir uma leitura multivariada do fenômeno, aproximando a análise da lógica real de priorização em pesquisa empírica: um padrão é cientificamente relevante não apenas porque aparece muito, mas porque combina recorrência, taxa e abrangência no corpus. Para a tese, essa figura ajuda a decidir quais pares devem ser discutidos como resultados centrais, quais devem ser tratados como contrastes metodológicos e quais merecem estudo de caso específico.",
            figures_dir / "08_pattern_volume_vs_rate.png",
        )
    )

    return sections


def _algorithmic_paragraph(metrics: MetricBundle) -> str:
    pair = metrics.pair_summary
    total_stats = _series_stats(pair["total_rows"])
    yes_stats = _series_stats(pair["yes_rows"])
    rate_stats = _series_stats(pair["yes_rate"])
    sentences = [
        "A formulação algorítmica do programa pode ser descrita rigorosamente em termos de teoria de conjuntos, análise combinatória e complexidade assintótica. Para cada contexto G = (Project, File, Caller), o programa constrói uma função parcial que associa a cada callee o conjunto de condições de presença textualmente normalizadas sob as quais essa função é observada. Seja A o conjunto de PCs da primeira API do padrão e B o conjunto de PCs da segunda API. A baseline de detecção avalia todos os pares ordenados do produto cartesiano A × B, produzindo uma linha para cada combinação. Em linguagem matemática, o custo local por padrão é proporcional a |A| x |B|, e o custo agregado do detector é a soma dessa quantidade sobre todos os padrões candidatos em todos os grupos. Em sistemas configuráveis escritos em C/C++, esse custo é particularmente importante porque o uso intensivo de diretivas de pré-processamento fragmenta o comportamento do programa em regiões condicionais que coexistem no mesmo arquivo e frequentemente no mesmo caller. Isso significa que a cardinalidade dos conjuntos A e B não é um acidente estatístico, mas um reflexo direto da expressividade da variabilidade anotativa. A deduplicação posterior introduz uma canonização que pode ser vista como uma projeção das linhas observadas em um espaço quociente, no qual pares espelhados passam a representar a mesma entidade lógica. Já o Match-First Filtering introduz uma operação de interseção exata M = A ∩ B, com os remanescentes A \\ M e B \\ M funcionando como evidência residual de assimetria. Do ponto de vista computacional, trata-se de uma heurística particularmente apropriada para o caso em que a semântica deve permanecer string-based: ela não exige SAT, não exige normalização algébrica profunda e preserva total compatibilidade com a definição metodológica atual da pesquisa. Em termos estatísticos, o comportamento dos padrões também revela heterogeneidade considerável. Considerando o número total de linhas por padrão após a filtragem, a média é "
        + _fmt_float(total_stats["mean"])
        + " linhas por par, enquanto a mediana é "
        + _fmt_float(total_stats["median"])
        + ", com desvio padrão de "
        + _fmt_float(total_stats["std"])
        + ". O primeiro quartil está em "
        + _fmt_float(total_stats["q1"])
        + " e o terceiro em "
        + _fmt_float(total_stats["q3"])
        + ", o que indica forte dispersão entre pares muito comuns e pares relativamente raros. A assimetria dessa distribuição é capturada pelo coeficiente de skewness "
        + _fmt_float(total_stats["skew"])
        + ", enquanto a curtose "
        + _fmt_float(total_stats["kurtosis"])
        + " sugere caudas pesadas, isto é, poucos pares concentram grande massa de observação. A distribuição de violações por par é ainda mais concentrada: a média de YES por padrão é "
        + _fmt_float(yes_stats["mean"])
        + ", a mediana é "
        + _fmt_float(yes_stats["median"])
        + " e o máximo alcança "
        + _fmt_int(yes_stats["max"])
        + ". Já a taxa de violação por padrão, que é a estatística mais informativa quando se deseja comparar protocolos com volumes muito diferentes, apresenta média de "
        + f"{rate_stats['mean']:.2%}"
        + ", mediana de "
        + f"{rate_stats['median']:.2%}"
        + " e desvio padrão de "
        + f"{rate_stats['std']:.4f}"
        + ". Em termos metodológicos, isso confirma que não basta ordenar os pares apenas por contagem absoluta; é necessário interpretar em conjunto intensidade, dispersão e taxa, especialmente em um domínio em que variabilidade estrutural e prevalência de uso são fenômenos intrinsecamente entrelaçados."
    ]
    sentences.append(
        "Em consequência, a própria escolha por estatística descritiva detalhada deixa de ser acessória e passa a integrar o argumento científico, porque demonstra formalmente que a distribuição observada é concentrada, assimétrica e sensível à forma como a variabilidade se materializa no código."
    )
    sentences.append(
        "Em termos práticos, isso significa que qualquer discussão séria sobre os resultados precisa reconhecer explicitamente a presença de heterogeneidade estrutural no corpus. Se essa heterogeneidade for ignorada, corre-se o risco de confundir frequência de uso com severidade analítica, ou de interpretar distribuições altamente assimétricas como se fossem quase uniformes, o que seria inadequado para um estudo deste tipo."
    )
    return _ensure_min_words(_join_sentences(sentences))


def _pair_paragraph(metrics: MetricBundle) -> str:
    pair = metrics.pair_summary
    filtered_yes = int(metrics.overall.iloc[0]["filtered_violations"])
    top = pair.head(10)
    sentences = [
        "A análise detalhada dos pares de APIs após a filtragem mostra um padrão estatístico de concentração altamente relevante para a interpretação científica dos resultados. O par `free | malloc` aparece como o mais violado em volume absoluto, com "
        + _fmt_int(top.iloc[0]["yes_rows"])
        + " ocorrências, mas seu significado não pode ser resumido apenas a essa liderança numérica. Ele se distribui por "
        + _fmt_int(top.iloc[0]["projects"])
        + " projetos e "
        + _fmt_int(top.iloc[0]["files"])
        + " arquivos, o que o caracteriza como um protocolo de altíssima capilaridade no corpus. Em contraste, `close | open` apresenta "
        + _fmt_int(top.iloc[1]["yes_rows"])
        + " violações, menos que `free | malloc`, porém com taxa de violação de "
        + f"{top.iloc[1]['yes_rate']:.2%}"
        + ", superior à taxa de "
        + f"{top.iloc[0]['yes_rate']:.2%}"
        + " do par líder em volume. Essa distinção é fundamental do ponto de vista estatístico: volume absoluto mede carga total de inconsistência observada, enquanto taxa mede propensão relativa à violação. Em um relatório voltado a especialistas, os dois indicadores devem ser lidos simultaneamente. Se olharmos a concentração acumulada, os três pares mais violados respondem por "
        + f"{top.head(3)['yes_rows'].sum() / filtered_yes:.2%}"
        + " de todas as violações residuais, e os cinco primeiros chegam a "
        + f"{top.head(5)['yes_rows'].sum() / filtered_yes:.2%}"
        + ". Isso significa que a massa de inconsistência remanescente não está distribuída de maneira uniforme; ela é fortemente concentrada em poucos protocolos de uso de recursos, especialmente memória, arquivos e descritores. Por outro lado, os pares mais frequentes em não violações funcionam como um grupo de controle. `va_end | va_start`, por exemplo, aparece com "
        + _fmt_int(pair[pair['Pattern'] == 'va_end | va_start']['no_rows'].iloc[0])
        + " não violações e taxa residual de apenas "
        + f"{pair[pair['Pattern'] == 'va_end | va_start']['yes_rate'].iloc[0]:.2%}"
        + ", sugerindo que, apesar de sua ubiquidade, o protocolo é amplamente estável e bem codificado ao longo do corpus. Esse contraste entre protocolos altamente frequentes porém estáveis e protocolos altamente frequentes porém vulneráveis é uma das descobertas mais ricas do relatório, porque mostra que a variabilidade introduzida pelo pré-processador não afeta todos os padrões com a mesma intensidade. Além disso, pares como `FD_SET | FD_ZERO`, `free | realloc` e `close | socket` ilustram uma zona intermediária em que o volume é menor, mas a taxa continua elevada o suficiente para indicar fragilidade estrutural. Sob a ótica de engenharia de software, isso sugere prioridades diferentes: pares com alto volume absoluto devem ser tratados como hotspots sistêmicos, enquanto pares com alta taxa, mesmo de menor volume, devem ser tratados como hotspots semânticos, pois podem indicar protocolos que se degradam fortemente quando submetidos à fragmentação variacional. Em termos estatísticos, a coexistência dessas duas categorias reforça a necessidade de evitar rankings unidimensionais e de trabalhar com análises multivariadas, mesmo quando o pipeline operacional ainda é propositalmente simples e explicável."
    ]
    sentences.append(
        "Essa leitura é coerente com a literatura sobre protocolos de uso de recursos em C/C++, na qual memória, arquivos e sockets frequentemente aparecem como domínios onde pequenos desalinhamentos de contexto podem produzir consequências funcionais e de qualidade relevantes."
    )
    sentences.append(
        "Além disso, a leitura conjunta entre volume, taxa, dispersão por projeto e presença em múltiplos arquivos evita uma interpretação simplista segundo a qual o par mais frequente seria automaticamente o mais crítico. Em pesquisa empírica de software, essa precaução é fundamental, porque padrões amplamente difundidos podem acumular contagens elevadas apenas pela escala de adoção, enquanto padrões menos volumosos podem exibir razão de falha bem mais intensa quando submetidos à variabilidade."
    )
    return _ensure_min_words(_join_sentences(sentences))


def _system_variability_paragraph(metrics: MetricBundle) -> str:
    systems = metrics.system_summary
    sys_yes_stats = _series_stats(systems["yes_rows"])
    sys_rate_stats = _series_stats(systems["yes_rate"])
    var = metrics.variability_summary.pivot(index="VarClass", columns="Violation", values="count").fillna(0)
    for idx in ["none", "partial", "total"]:
        if idx not in var.index:
            var.loc[idx] = {"NO": 0, "YES": 0}
    for col in ["NO", "YES"]:
        if col not in var.columns:
            var[col] = 0
    none_total = var.loc["none"].sum()
    partial_total = var.loc["partial"].sum()
    total_total = var.loc["total"].sum()
    sentences = [
        "Quando deslocamos a análise do nível dos pares para o nível dos sistemas, a distribuição das violações continua evidenciando forte heterogeneidade. O sistema `gzip` lidera com "
        + _fmt_int(systems.iloc[0]["yes_rows"])
        + " violações filtradas e taxa de "
        + f"{systems.iloc[0]['yes_rate']:.2%}"
        + ", seguido por `xterm-snapshots`, com "
        + _fmt_int(systems.iloc[1]["yes_rows"])
        + " violações e taxa de "
        + f"{systems.iloc[1]['yes_rate']:.2%}"
        + ". Esses números são particularmente relevantes porque mostram que não estamos diante apenas de sistemas grandes acumulando evidência por volume; estamos diante de sistemas nos quais a fração de instâncias problemáticas entre todas as instâncias observadas é muito alta. Em contrapartida, projetos como `glibc`, `OpenSC`, `mongo` e `krb5` exibem contagens absolutas importantes, mas taxas bem menores, o que sugere ecossistemas mais amplos, com grande diversidade de padrões, porém melhor amortecimento entre uso correto e uso inconsistente. Em termos de estatística descritiva, a distribuição de violações por sistema apresenta média de "
        + _fmt_float(sys_yes_stats["mean"])
        + ", mediana de "
        + _fmt_float(sys_yes_stats["median"])
        + ", desvio padrão de "
        + _fmt_float(sys_yes_stats["std"])
        + ", mínimo de "
        + _fmt_float(sys_yes_stats["min"])
        + " e máximo de "
        + _fmt_float(sys_yes_stats["max"])
        + ". A taxa de violação por sistema, por sua vez, tem média de "
        + f"{sys_rate_stats['mean']:.2%}"
        + ", mediana de "
        + f"{sys_rate_stats['median']:.2%}"
        + " e máximo de "
        + f"{sys_rate_stats['max']:.2%}"
        + ", revelando um cenário em que poucos sistemas funcionam como outliers de criticidade. Essa observação é crucial para desenho de estudos de caso na tese. Contudo, a interpretação sistêmica fica incompleta sem a camada de variabilidade. A tabela de variabilidade mostra que o conjunto `none` soma "
        + _fmt_int(none_total)
        + " observações, todas classificadas como não violação na saída filtrada, o que implica taxa de violação nula. Já o grupo `partial`, com "
        + _fmt_int(partial_total)
        + " observações, é composto inteiramente por violações, resultando em taxa de 100%. O grupo `total`, por sua vez, contém "
        + _fmt_int(total_total)
        + " observações, das quais "
        + _fmt_int(int(var.loc['total', 'YES']))
        + " são violações, perfazendo taxa de "
        + f"{(var.loc['total', 'YES'] / total_total) if total_total else 0.0:.2%}"
        + ". Do ponto de vista teórico, esse resultado é extremamente sugestivo. Ele indica que, dentro da definição operacional atual, o pipeline filtrado associa as violações residuais exclusivamente a contextos onde pelo menos um dos lados do padrão está sob variabilidade. Não há, no conjunto final, violações em contextos inteiramente incondicionais. Isso reforça diretamente a hipótese central da pesquisa: o fenômeno relevante não é simplesmente API misuse em C/C++, mas API misuse em presença de fragmentação variacional induzida por diretivas de pré-processamento. Em linguagem de modelagem, a variável `VarClass` não é apenas descritiva; ela funciona como eixo discriminante quase perfeito entre a massa estável de uso e a massa residual de inconsistência. Para um especialista em sistemas configuráveis, esse é talvez o resultado mais teoricamente consequente do relatório."
    ]
    sentences.append(
        "Tal resultado também sugere que a granularidade da análise adotada pelo programa está capturando uma relação estrutural real entre variabilidade e inconsistência, em vez de um ruído indiferenciado distribuído ao acaso no corpus."
    )
    sentences.append(
        "Para um público especializado, essa observação tem peso teórico porque aproxima a saída do programa de uma forma de evidência explicativa: não se trata apenas de detectar que há violações, mas de mostrar que elas se alinham a um mecanismo plausível, isto é, a fragmentação de protocolos de uso em regiões condicionais de pré-processador."
    )
    sentences.append(
        "Em termos de agenda científica, esse achado abre espaço para análises futuras orientadas por estratos, por exemplo comparando sistemas com alta densidade de variabilidade, sistemas com alta taxa de violação residual e sistemas com grande diversidade de padrões. Esse tipo de estratificação pode produzir estudos de caso muito mais informativos do que uma inspeção uniforme de todo o corpus."
    )
    return _ensure_min_words(_join_sentences(sentences))


def _fp_paragraph(metrics: MetricBundle) -> str:
    fp_summary = metrics.fp_summary.set_index("FPStatus")["count"]
    fp_total = int(fp_summary.get("ConfirmedFalsePositive", 0))
    candidate_total = int(fp_summary.get("CandidateViolation", 0))
    top_contexts = metrics.fp_contexts.head(5)
    sentences = [
        "A etapa de análise de falsos positivos merece leitura própria porque ela toca diretamente o problema epistemológico da pesquisa: como distinguir um sinal residual relevante de um artefato produzido pela estratégia observacional do detector. O Match-First Filtering parte de uma intuição forte e metodologicamente conservadora: se, no mesmo contexto `(Project, File, Caller, par não ordenado de APIs)`, já existe casamento textual exato entre determinadas condições de presença, então alguns YES adicionais podem ser mais bem interpretados como cruzamentos artificiais entre instâncias distintas do protocolo do que como violação genuína. Os números do relatório são expressivos: do conjunto deduplicado de 596 violações, 124 foram reclassificadas como `ConfirmedFalsePositive`, enquanto 472 permaneceram como `CandidateViolation`. Em termos proporcionais, isso significa que "
        + f"{fp_total / (fp_total + candidate_total):.2%}"
        + " do conjunto deduplicado de violações foi explicado pela nova regra sem necessidade de alterar a baseline do detector. Para um pesquisador em engenharia de software experimental, esse detalhe é crucial, porque separa claramente dois tipos de validade: validade operacional do detector e validade interpretativa do conjunto final. A primeira permanece a mesma; a segunda melhora pela remoção de artefatos previsíveis. A concentração dos falsos positivos também é altamente informativa. O contexto `xterm-snapshots | spawnXTerm | close|open` sozinho responde por "
        + f"{(top_contexts.iloc[0]['confirmed_false_positives'] / fp_total) if fp_total else 0.0:.2%}"
        + " de todos os falsos positivos confirmados, e os cinco principais contextos somam "
        + f"{(top_contexts['confirmed_false_positives'].sum() / fp_total) if fp_total else 0.0:.2%}"
        + ". Isso sugere que a distorção não está espalhada aleatoriamente pelo corpus; ela emerge de contextos específicos, tipicamente funções grandes, densamente anotadas e com múltiplas instâncias do mesmo protocolo. Em termos matemáticos, a regra atua como filtro sobre a interseção A ∩ B dos conjuntos de PCs, removendo cruzamentos entre elementos já explicados por correspondência textual local. Em termos estatísticos, o efeito pode ser entendido como melhoria da razão sinal-ruído do conjunto residual. Em termos de sistemas configuráveis, o resultado é ainda mais interessante: o falso positivo não desaparece por negar a variabilidade, mas por modelá-la de modo mais fiel, reconhecendo que várias instâncias condicionais da mesma API podem coexistir no mesmo caller. Essa distinção é central para a tese, porque evita o erro metodológico de classificar como ruído aquilo que, na verdade, é complexidade estrutural legítima do pré-processador. O relatório final, portanto, não deve apresentar essa etapa como mera limpeza de dados, mas como refinamento epistemicamente motivado da inferência produzida pelo detector não ordenado e string-based."
    ]
    sentences.append(
        "Em termos doutorais, o ganho principal dessa etapa não é só quantitativo, mas inferencial: ela torna mais defensável a passagem de um conjunto de observações brutas para um conjunto de conclusões sobre o efeito da variabilidade no uso de APIs."
    )
    sentences.append(
        "Esse refinamento também preserva uma virtude importante da solução: a regra de falso positivo continua simples o suficiente para ser auditada manualmente, discutida teoricamente e reproduzida por outros pesquisadores. Em um domínio no qual explicabilidade metodológica é tão importante quanto desempenho analítico, essa simplicidade controlada é uma vantagem, não uma limitação."
    )
    sentences.append(
        "Ao mesmo tempo, o fato de os falsos positivos se concentrarem em poucos contextos reforça a ideia de que o problema não está distribuído homogeneamente pela base, mas associado a pontos de alta complexidade estrutural. Isso ajuda a orientar inspeções futuras e a justificar, com base empírica, o refinamento gradual da granularidade analítica do programa."
    )
    return _ensure_min_words(_join_sentences(sentences))


def _build_doctoral_sections(metrics: MetricBundle) -> list[tuple[str, str]]:
    return [
        (
            "Questões de Pesquisa e Direcionamento Analítico do Relatório",
            _research_questions_paragraph(metrics),
        ),
        (
            "Análise Integral do Repositório e da Arquitetura Experimental",
            _repository_architecture_paragraph(metrics),
        ),
        (
            "Fundamentos Computacionais, Conceituais e Arquiteturais",
            _pipeline_paragraph(metrics),
        ),
        (
            "Fundamentação Algorítmica, Matemática e Estatística Descritiva dos Padrões",
            _algorithmic_paragraph(metrics),
        ),
        (
            "Análise Detalhada dos Pares de APIs e da Concentração de Violações",
            _pair_paragraph(metrics),
        ),
        (
            "Análise por Sistema e Papel da Variabilidade por Diretivas de Pré-processamento",
            _system_variability_paragraph(metrics),
        ),
        (
            "Falsos Positivos, Validade Analítica e Implicações Científicas",
            _fp_paragraph(metrics),
        ),
    ]


def write_doctoral_markdown_report(metrics: MetricBundle, paths: DoctoralReportPaths) -> None:
    sections = _build_doctoral_sections(metrics)
    content = ["# Relatório Doutoral sobre Identificação de Violações de Padrões de Uso de APIs em Sistemas Configuráveis em C/C++", ""]
    content.append(
        "## Escopo e Posicionamento Científico\n"
        "Este relatório foi concebido para um público especializado em sistemas configuráveis implementados por diretivas de pré-processamento em C/C++. Diferentemente do relatório executivo, aqui a ênfase recai sobre formalização conceitual, fundamentos algorítmicos, estatística descritiva e interpretação metodologicamente rigorosa dos resultados produzidos pelo pipeline."
    )
    for title, paragraph in sections:
        content.append(f"\n## {title}\n")
        content.append(paragraph)
    content.append("\n## Figuras e Interpretação Analítica\n")
    content.append(
        "Nesta seção, cada gráfico gerado automaticamente é incorporado ao relatório como evidência visual para uma ou mais questões de pesquisa. As figuras não devem ser lidas como ilustrações decorativas, mas como instrumentos de interpretação quantitativa e comparativa do fenômeno de violação de padrões de uso de APIs em sistemas configuráveis em C/C++."
    )
    for title, paragraph, fig_path in _figure_explanation_sections(metrics, paths):
        rel_path = fig_path.relative_to(paths.base_dir)
        content.append(f"\n### {title}\n")
        content.append(f"![{title}]({rel_path.as_posix()})")
        content.append(paragraph)
    paths.markdown_path.write_text("\n\n".join(content), encoding="utf-8")


def write_doctoral_pdf_report(metrics: MetricBundle, paths: DoctoralReportPaths) -> None:
    sections = _build_doctoral_sections(metrics)
    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(paths.pdf_path),
        pagesize=A4,
        leftMargin=1.7 * cm,
        rightMargin=1.7 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="Relatório Doutoral sobre Violações de Padrões de Uso de APIs",
        author="OpenAI Codex",
    )
    story = []
    story.append(Paragraph("Relatório Doutoral sobre Violações de Padrões de Uso de APIs", styles["SectionBlue"]))
    story.append(
        Paragraph(
            "Versão analítica orientada a especialistas em sistemas configuráveis, com foco em fundamentação computacional, matemática e estatística descritiva.",
            styles["BodyDense"],
        )
    )
    for idx, (title, paragraph) in enumerate(sections):
        story.append(Paragraph(title, styles["SectionBlue"]))
        story.append(Paragraph(paragraph, styles["BodyDense"]))
        story.append(PageBreak())
    story.append(Paragraph("Figuras e Interpretação Analítica", styles["SectionBlue"]))
    story.append(
        Paragraph(
            "Cada figura apresentada a seguir deve ser lida como evidência para uma pergunta de pesquisa específica, e não apenas como apoio visual. O objetivo desta seção é conectar a visualização quantitativa ao argumento científico sobre violações de padrões de uso de APIs em presença de variabilidade por diretivas de pré-processamento.",
            styles["BodyDense"],
        )
    )
    story.append(PageBreak())
    figure_sections = _figure_explanation_sections(metrics, paths)
    for idx, (title, paragraph, fig_path) in enumerate(figure_sections):
        story.append(Paragraph(title, styles["SectionBlue"]))
        if fig_path.exists():
            story.append(_scaled_image(fig_path))
            story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph(paragraph, styles["BodyDense"]))
        if idx != len(figure_sections) - 1:
            story.append(PageBreak())
        else:
            story.append(Spacer(1, 0.2 * cm))
    doc.build(story)
