from collections.abc import Sequence
from math import isfinite

from assistente.aplicacao.consultar_recomendacoes import ResultadoConsulta
from assistente.dominio.catalogo import IDS_HEROIS
from assistente.dominio.modelos import Build, CounterPick, Funcao, ItemQuantidade


def rotulo_referencia(benchmark: dict[str, object] | None, chaves: tuple[str, ...]) -> str:
    if benchmark is None:
        return "Estimativa"
    for chave in chaves:
        valor = benchmark.get(chave)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not isfinite(valor) or valor < 0:
            return "Estimativa"
    percentil = benchmark.get("percentil", 0.5)
    if isinstance(percentil, (int, float)) and isfinite(percentil) and 0 <= percentil <= 1:
        return f"P{percentil*100:.0f}"
    return "Estimativa"


def formatar_quantidades(itens: Sequence[ItemQuantidade]) -> tuple[str, ...]:
    return tuple(
        f"{item.nome} ×{item.quantidade}" if item.quantidade > 1 else item.nome
        for item in itens
    )


def formatar_counter_picks(
    candidatos: Sequence[CounterPick], funcao: Funcao, possui_alvos: bool,
) -> str:
    if not possui_alvos:
        return "Selecione pelo menos 1 inimigo (Lane 1/2 ou Ameaça) para calcular counter-picks."
    if not candidatos:
        return "Sem dados suficientes de matchup retornados pela OpenDota para esses heróis."
    linhas = [f"🎯 TOP PICKS ({funcao.value}) — matchup agregado + meta atual:"]
    for candidato in candidatos:
        linhas.append(
            f"• {candidato.heroi:<18} | vs alvos: {candidato.percentual_confronto:4.1f}% | "
            f"meta geral: {candidato.percentual_meta:4.1f}% ({candidato.jogos} jogos)"
        )
    linhas.append(
        "Nota: roles da OpenDota são arquétipos; o filtro MID é aproximado, não lane_role por partida."
    )
    return "\n".join(linhas)


def dados_build(
    heroi: str, funcao: Funcao, build: Build | None, erro: str = "", orcamento: int = 600,
) -> dict[str, object]:
    mensagem = ""
    if build is None:
        if heroi not in IDS_HEROIS:
            mensagem = "Herói não encontrado."
        elif erro:
            mensagem = (
                f"Não foi possível consultar a build: {erro}. "
                "A build não foi substituída por dados de outra fonte."
            )
        else:
            mensagem = f"Sem build Dota2ProTracker para {heroi} como {funcao.rotulo} (pos {funcao.posicao})."
    dados: dict[str, object] = {
        "heroi": heroi, "perfil": funcao.rotulo.upper(), "start": "", "early": "",
        "mid": "", "late": "", "core": "", "alertas": [], "analise_matchup": "",
        "fonte": "", "observacao": mensagem, "situacionais": [], "opcoes": [],
        "amostra": 0, "custo_saida": None, "erro": mensagem,
    }
    if build is None:
        return dados
    saida = formatar_quantidades(build.saida)
    situacionais = [
        f"{item.nome} — {item.percentual*100:.0f}% · {item.fase.rotulo} · média {item.minuto:.0f}m"
        for item in build.situacionais
    ]
    info = [
        f"Fonte: Dota2ProTracker · posição pos {funcao.posicao} · "
        f"{build.observada.partidas} partidas na build selecionada.",
        "Fonte do site: partidas recentes de alto MMR/pro players; "
        "janela móvel conforme disponibilidade do herói e da função.",
        "Core ordenado pelo tempo médio de compra; itens menos frequentes ficam como situacionais no painel.",
    ]
    if build.observada.taxa_vitoria is not None:
        info.append(f"Win rate da build: {build.observada.taxa_vitoria*100:.1f}%.")
    if saida:
        info.append(
            f"Saída mais comum dentro do orçamento: {', '.join(saida)} — "
            f"{build.custo_saida}/{orcamento} de ouro."
        )
    elif build.observada.pacotes_informados:
        info.append(f"Nenhum pacote inicial pôde ser confirmado dentro do orçamento de {orcamento} ouro.")
    else:
        info.append("O site não forneceu combinações de Saída estruturadas para esta build.")
    dados.update({
        "start": " → ".join(saida), "early": " → ".join(build.inicio),
        "mid": " → ".join(build.meio), "late": " → ".join(build.final),
        "core": "\n".join((
            f"EARLY: {' → '.join(build.inicio)}", f"MID: {' → '.join(build.meio)}",
            f"LATE: {' → '.join(build.final)}",
        )),
        "analise_matchup": (
            f"Build D2PT selecionada: {build.observada.nome}. "
            "Os counters por inimigo são calculados separadamente."
        ),
        "fonte": "Dota2ProTracker JSON API", "observacao": "\n".join(info),
        "situacionais": situacionais, "amostra": build.observada.partidas,
        "custo_saida": build.custo_saida,
    })
    return dados


def formatar_painel(resultado: ResultadoConsulta) -> str:
    consulta = resultado.consulta
    dados = dados_build(
        consulta.heroi, consulta.funcao, resultado.build, resultado.erro_build,
    )
    linhas = [
        f"📋 BUILD ({consulta.heroi} - {consulta.funcao.rotulo.upper()}):",
        f"• Saída: {dados['start']}", f"• Early (<12m): {dados['early']}",
        f"• Mid (12–30m): {dados['mid']}", f"• Late (30m+): {dados['late']}",
        str(dados["observacao"]), "-" * 44,
    ]
    if resultado.build and resultado.build.situacionais:
        linhas.append("Situacionais D2PT (não são counters automáticos):")
        linhas.extend(
            f"• {item.nome} — {item.percentual*100:.0f}% · {item.fase.rotulo} · média {item.minuto:.0f}m"
            for item in resultado.build.situacionais[:18]
        )
    if resultado.detalhes_opcoes:
        linhas.append("COUNTERS CONTEXTUAIS POR LANE/AMEAÇA (heurísticas):")
        linhas.extend(f"• {detalhe}" for detalhe in resultado.detalhes_opcoes)
    if resultado.benchmark is None:
        linhas.append("Benchmarks indisponíveis; metas estimadas serão identificadas como estimativas.")
    linhas.extend(resultado.avisos)
    linhas.extend((
        "-" * 44, formatar_counter_picks(resultado.counter_picks, consulta.funcao, bool(consulta.alvos)),
    ))
    return "\n".join(linha for linha in linhas if linha)
