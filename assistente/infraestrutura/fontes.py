"""Tradução dos formatos dos provedores para modelos internos."""

from collections.abc import Callable, Mapping
from math import isfinite

from assistente.aplicacao.contratos import AmostrasDisponiveis, ErroIntegracao
from assistente.dominio.catalogo import COMPONENTES_SOLTOS
from assistente.dominio.modelos import BuildObservada, Confronto, Funcao, ItemObservado

from . import cliente_dota2protracker, cliente_opendota

ITENS_OCULTOS = {
    "observer ward", "sentry ward", "observer and sentry wards", "town portal scroll",
    "teleport scroll", "teleportation scroll", "tp scroll", "recipe",
}


def numero_finito(valor: object, padrao: float = 0.0) -> float:
    if not isinstance(valor, (str, int, float)) or isinstance(valor, bool):
        return padrao
    try:
        numero = float(valor)
    except (ValueError, OverflowError):
        return padrao
    return numero if isfinite(numero) else padrao


def percentual_normalizado(valor: object) -> float:
    percentual = numero_finito(valor)
    if percentual > 1:
        percentual /= 100
    return max(0.0, min(1.0, percentual))


def _lista(valor: object) -> list[object]:
    return list(valor) if isinstance(valor, (list, tuple)) else []


def _nome_item(identificador: object, catalogo: Mapping[int, str]) -> str | None:
    try:
        if isinstance(identificador, (int, str)) and not isinstance(identificador, bool):
            return catalogo.get(int(identificador))
    except ValueError:
        if isinstance(identificador, str):
            return identificador.removeprefix("item_").replace("_", " ").title()
    return None


def _identificadores_pacote(pacote: object) -> list[object]:
    if isinstance(pacote, (list, tuple)) and pacote:
        if isinstance(pacote[0], (list, tuple)):
            return list(pacote[0])
        if all(isinstance(item, (int, str)) for item in pacote):
            return list(pacote)
    if isinstance(pacote, dict):
        return _lista(pacote.get("items") or pacote.get("item_ids") or pacote.get("raw_item_ids"))
    return []


def normalizar_amostras(dados: object, catalogo: Mapping[int, str]) -> tuple[BuildObservada, ...]:
    amostras = []
    for registro in _lista(dados):
        if not isinstance(registro, dict):
            continue
        conteudo = registro.get("build_data")
        conteudo = conteudo if isinstance(conteudo, dict) else registro
        pacotes_crus = conteudo.get("starting_items_new") or conteudo.get("starting_items_combos") or []
        pacotes = []
        for pacote in _lista(pacotes_crus):
            nomes = []
            for identificador in _identificadores_pacote(pacote):
                nome = _nome_item(identificador, catalogo)
                if nome is None:
                    # Não tornar um pacote artificialmente barato omitindo itens desconhecidos.
                    break
                if nome.strip().lower() not in ITENS_OCULTOS:
                    nomes.append(nome)
            else:
                pacotes.append(tuple(nomes))
        itens_por_id: dict[int, ItemObservado] = {}
        for chave in ("anchor_items", "anchor_items2", "items_mid_late"):
            for item in _lista(conteudo.get(chave)):
                if not isinstance(item, dict):
                    continue
                identificador = item.get("raw_item_id", item.get("item_id", item.get("id")))
                if not isinstance(identificador, (str, int)) or isinstance(identificador, bool):
                    continue
                try:
                    identificador = int(identificador)
                except ValueError:
                    continue
                nome = catalogo.get(identificador)
                minuto = numero_finito(item.get("avg_minute"), float("nan"))
                percentual = percentual_normalizado(
                    item.get("pr") if item.get("pr") is not None else item.get("pick_rate")
                )
                if (not nome or nome in COMPONENTES_SOLTOS or not isfinite(minuto)
                        or nome.lower() in ITENS_OCULTOS or percentual <= 0):
                    continue
                observado = ItemObservado(nome, minuto, percentual, max(0, numero_finito(item.get("count"))))
                anterior = itens_por_id.get(identificador)
                if anterior is None or (
                    observado.contagem, observado.percentual
                ) > (anterior.contagem, anterior.percentual):
                    itens_por_id[identificador] = observado
        partidas = max(0, int(numero_finito(registro.get("num_matches"))))
        taxa_vitoria = None
        if registro.get("win_rate") is not None:
            taxa_vitoria = percentual_normalizado(registro["win_rate"])
        elif partidas:
            taxa_vitoria = min(1, max(0, numero_finito(registro.get("num_wins")) / partidas))
        nome_build = registro.get("name") or registro.get("label") or registro.get("archetype")
        amostras.append(BuildObservada(
            str(nome_build or "build mais frequente"), partidas, tuple(pacotes),
            tuple(itens_por_id.values()), taxa_vitoria, bool(pacotes_crus),
        ))
    return tuple(amostras)


def normalizar_taxas_meta(dados: object) -> dict[int, float]:
    taxas = {}
    for registro in _lista(dados):
        if not isinstance(registro, dict):
            continue
        identificador = int(numero_finito(registro.get("id")))
        if identificador <= 0:
            continue
        escolhas = sum(
            max(0, int(numero_finito(registro.get(chave)))) for chave in ("7_pick", "8_pick", "pro_pick")
        )
        vitorias = sum(
            max(0, int(numero_finito(registro.get(chave)))) for chave in ("7_win", "8_win", "pro_win")
        )
        if vitorias > escolhas:
            continue
        taxas[identificador] = vitorias / escolhas if escolhas else 0.5
    return taxas


def normalizar_confrontos(dados: object) -> tuple[Confronto, ...]:
    confrontos = []
    for registro in _lista(dados):
        if not isinstance(registro, dict):
            continue
        try:
            confronto = Confronto(
                int(numero_finito(registro.get("hero_id"))),
                int(numero_finito(registro.get("games_played"))),
                int(numero_finito(registro.get("wins"))),
            )
        except ValueError:
            continue
        confrontos.append(confronto)
    return tuple(confrontos)


def normalizar_papeis(dados: object) -> dict[int, tuple[str, ...]]:
    if not isinstance(dados, dict):
        return {}
    return {
        identificador: tuple(papel for papel in _lista(registro.get("roles")) if isinstance(papel, str))
        for identificador, registro in dados.items()
        if isinstance(identificador, int) and isinstance(registro, dict)
    }


class FonteDota2ProTracker:
    def obter(
        self, heroi_id: int, funcao: Funcao,
        verificar_ativa: Callable[[], None] | None = None,
    ) -> AmostrasDisponiveis:
        if verificar_ativa is not None:
            verificar_ativa()
        try:
            dados = cliente_dota2protracker.obter_builds(heroi_id, funcao.value)
        except cliente_dota2protracker.ErroDota2ProTracker as erro:
            raise ErroIntegracao(str(erro)) from erro
        if not dados:
            return AmostrasDisponiveis((), {})
        if verificar_ativa is not None:
            verificar_ativa()
        catalogo = cliente_opendota.obter_catalogo_itens()
        if not catalogo:
            raise ErroIntegracao("Build D2PT recebida, mas o catálogo de itens não carregou.")
        if verificar_ativa is not None:
            verificar_ativa()
        precos = cliente_opendota.obter_catalogo_precos_itens()
        return AmostrasDisponiveis(normalizar_amostras(dados, catalogo), precos)


class ClienteDadosDota:
    def obter_benchmarks(self, heroi_id: int, funcao: Funcao) -> dict[str, object] | None:
        return cliente_opendota.obter_benchmarks(heroi_id, funcao.value)

    def obter_taxas_meta(self) -> dict[int, float]:
        dados = cliente_opendota.obter_hero_stats()
        if not isinstance(dados, list):
            raise ErroIntegracao("Não foi possível consultar as estatísticas de heróis.")
        return normalizar_taxas_meta(dados)

    def obter_papeis(self) -> dict[int, tuple[str, ...]]:
        dados = cliente_opendota.obter_catalogo_heroes()
        if not dados:
            raise ErroIntegracao("Não foi possível consultar os arquétipos dos heróis.")
        return normalizar_papeis(dados)

    def obter_confrontos(self, heroi_id: int) -> tuple[Confronto, ...]:
        dados = cliente_opendota.obter_matchups(heroi_id)
        if not isinstance(dados, list):
            raise ErroIntegracao("Não foi possível consultar os confrontos do herói.")
        return normalizar_confrontos(dados)
