from collections.abc import Callable
from dataclasses import dataclass, field

from assistente.dominio.catalogo import IDS_HEROIS
from assistente.dominio.counters import recomendar_itens_counter
from assistente.dominio.modelos import Build, CounterPick, Funcao
from assistente.dominio.recomendacoes import classificar_counter_picks, montar_build

from .contratos import DadosDota, ErroIntegracao, FonteBuilds


@dataclass(frozen=True)
class ConsultaRecomendacoes:
    heroi: str
    funcao: Funcao
    adversarios_lane: tuple[str, ...] = ()
    ameaca: str | None = None

    @property
    def alvos(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            nome for nome in (*self.adversarios_lane, self.ameaca)
            if nome and nome != "Nenhum" and nome in IDS_HEROIS
        ))


@dataclass
class ResultadoConsulta:
    consulta: ConsultaRecomendacoes
    build: Build | None = None
    erro_build: str = ""
    benchmark: dict[str, object] | None = None
    counter_picks: tuple[CounterPick, ...] = ()
    opcoes: tuple[str, ...] = ()
    detalhes_opcoes: tuple[str, ...] = ()
    avisos: list[str] = field(default_factory=list)


def consultar_build(
    heroi: str, funcao: Funcao, fonte: FonteBuilds,
    orcamento: int = 600, percentual_core: float = 0.50,
    verificar_ativa: Callable[[], None] | None = None,
) -> tuple[Build | None, str]:
    identificador = IDS_HEROIS.get(heroi)
    if identificador is None:
        return None, "Herói não encontrado."
    try:
        if verificar_ativa is not None:
            verificar_ativa()
            disponiveis = fonte.obter(identificador, funcao, verificar_ativa)
            verificar_ativa()
        else:
            disponiveis = fonte.obter(identificador, funcao)
    except ErroIntegracao as erro:
        return None, str(erro)
    build = montar_build(
        heroi, funcao, disponiveis.amostras, disponiveis.precos, orcamento, percentual_core,
    )
    return build, ""


class ConsultarRecomendacoes:
    def __init__(
        self, fonte: FonteBuilds, dados_dota: DadosDota,
        orcamento: int = 600, percentual_core: float = 0.50, minimo_jogos: int = 15,
    ) -> None:
        self._fonte = fonte
        self._dados_dota = dados_dota
        self._orcamento = orcamento
        self._percentual_core = percentual_core
        self._minimo_jogos = minimo_jogos

    def executar(
        self, consulta: ConsultaRecomendacoes,
        verificar_ativa: Callable[[], None] | None = None,
    ) -> ResultadoConsulta:
        resultado = ResultadoConsulta(consulta)
        resultado.build, resultado.erro_build = consultar_build(
            consulta.heroi, consulta.funcao, self._fonte, self._orcamento, self._percentual_core,
            verificar_ativa,
        )
        identificador = IDS_HEROIS.get(consulta.heroi)
        if identificador is None:
            return resultado
        opcoes, detalhes = recomendar_itens_counter(
            consulta.adversarios_lane, consulta.ameaca, consulta.funcao.value,
        )
        resultado.opcoes, resultado.detalhes_opcoes = tuple(opcoes), tuple(detalhes)
        if verificar_ativa is not None:
            verificar_ativa()
        try:
            resultado.benchmark = self._dados_dota.obter_benchmarks(identificador, consulta.funcao)
        except ErroIntegracao as erro:
            resultado.avisos.append(str(erro))
        if not consulta.alvos:
            return resultado
        taxas: dict[int, float] = {}
        papeis: dict[int, tuple[str, ...]] = {}
        if verificar_ativa is not None:
            verificar_ativa()
        try:
            taxas = self._dados_dota.obter_taxas_meta()
        except ErroIntegracao as erro:
            resultado.avisos.append(str(erro))
        if verificar_ativa is not None:
            verificar_ativa()
        try:
            papeis = self._dados_dota.obter_papeis()
        except ErroIntegracao as erro:
            resultado.avisos.append(str(erro))
        confrontos = {}
        for inimigo in consulta.alvos:
            if verificar_ativa is not None:
                verificar_ativa()
            try:
                confrontos[inimigo] = self._dados_dota.obter_confrontos(IDS_HEROIS[inimigo])
            except ErroIntegracao as erro:
                resultado.avisos.append(f"{inimigo}: {erro}")
        resultado.counter_picks = classificar_counter_picks(
            confrontos, consulta.ameaca, consulta.funcao, taxas, papeis, self._minimo_jogos,
        )
        return resultado
