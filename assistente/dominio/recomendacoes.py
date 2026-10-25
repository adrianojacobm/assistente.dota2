from collections import Counter
from collections.abc import Mapping, Sequence
from math import isfinite

from .catalogo import HEROIS_POR_ID
from .modelos import Build, BuildObservada, Confronto, CounterPick, Fase, Funcao, ItemQuantidade

PAPEIS_POR_FUNCAO = {
    "CARRY": {"Carry"},
    "MID": {"Carry", "Nuker"},
    "OFFLANE": {"Carry", "Nuker", "Initiator", "Durable", "Disabler"},
    "SUP": {"Support"},
}
BOTAS_COMPLETAS = {
    "Power Treads", "Phase Boots", "Arcane Boots", "Tranquil Boots",
    "Boots of Travel", "Boots of Travel 2",
}


def montar_build(
    heroi: str,
    funcao: Funcao,
    amostras: Sequence[BuildObservada],
    precos: Mapping[str, int],
    orcamento: int = 600,
    percentual_core: float = 0.50,
) -> Build | None:
    if orcamento < 0 or not isfinite(percentual_core) or not 0 <= percentual_core <= 1:
        raise ValueError("Orçamento ou percentual de core inválido.")
    if not amostras:
        return None
    observada = max(amostras, key=lambda amostra: amostra.partidas)
    pacote: tuple[str, ...] = ()
    custo_saida = None
    for candidato in observada.pacotes:
        if not candidato or any(nome not in precos or precos[nome] < 0 for nome in candidato):
            continue
        custo = sum(precos[nome] for nome in candidato)
        if custo <= orcamento:
            pacote, custo_saida = candidato, custo
            break
    saida = tuple(ItemQuantidade(nome, quantidade) for nome, quantidade in Counter(pacote).items())
    vistos = {nome.casefold() for nome in pacote}
    fases: dict[Fase, tuple[str, ...]] = {}
    situacionais = []
    for fase in Fase:
        candidatos = [item for item in observada.itens if item.fase == fase]
        core = sorted(
            (item for item in candidatos if item.percentual >= percentual_core),
            key=lambda item: (item.minuto, -item.percentual),
        )
        nomes = []
        for item in core:
            if item.nome.casefold() not in vistos:
                nomes.append(item.nome)
                vistos.add(item.nome.casefold())
        fases[fase] = tuple(nomes)
        opcionais = sorted(
            (item for item in candidatos if 0.05 <= item.percentual < percentual_core),
            key=lambda item: (-item.percentual, item.minuto),
        )
        situacionais.extend(opcionais[:8])
    nomes_progressao = {nome for nomes in fases.values() for nome in nomes}
    if BOTAS_COMPLETAS.intersection(nomes_progressao) and "boots of speed" not in vistos:
        fases[Fase.INICIO] = ("Boots of Speed", *fases[Fase.INICIO])
    return Build(
        heroi, funcao, observada, saida,
        fases[Fase.INICIO], fases[Fase.MEIO], fases[Fase.FINAL],
        tuple(sorted(situacionais, key=lambda item: (item.fase.value, -item.percentual))),
        custo_saida,
    )


def classificar_counter_picks(
    confrontos: Mapping[str, Sequence[Confronto]],
    ameaca: str | None,
    funcao: Funcao,
    taxas_meta: Mapping[int, float],
    papeis_herois: Mapping[int, Sequence[str]],
    minimo_jogos: int = 15,
) -> tuple[CounterPick, ...]:
    placar: dict[int, tuple[float, float, int]] = {}
    for inimigo, resultados in confrontos.items():
        peso = 1.5 if inimigo == ameaca else 1.0
        for confronto in resultados:
            if confronto.jogos < minimo_jogos or confronto.heroi_id not in HEROIS_POR_ID:
                continue
            vitorias, jogos, total = placar.get(confronto.heroi_id, (0.0, 0.0, 0))
            placar[confronto.heroi_id] = (
                vitorias + (confronto.jogos - confronto.vitorias_inimigo) * peso,
                jogos + confronto.jogos * peso,
                total + confronto.jogos,
            )
    aceitos = PAPEIS_POR_FUNCAO[funcao.perfil_counter]
    ranking = []
    for identificador, (vitorias, jogos, total) in placar.items():
        papeis = set(papeis_herois.get(identificador, ()))
        if jogos <= 0 or (papeis and not papeis.intersection(aceitos)):
            continue
        percentual = 100 * vitorias / jogos
        meta = 100 * taxas_meta.get(identificador, 0.50)
        ranking.append(CounterPick(
            HEROIS_POR_ID[identificador], percentual, meta, total,
            percentual * 0.7 + meta * 0.3,
        ))
    return tuple(sorted(ranking, key=lambda candidato: candidato.pontuacao, reverse=True)[:6])
