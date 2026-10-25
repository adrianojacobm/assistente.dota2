from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypedDict

from assistente.dominio.modelos import BuildObservada, Confronto, Funcao
from assistente.dominio.partida import AtualizacaoPartida, InstantaneoPartida

if TYPE_CHECKING:
    from .consultar_recomendacoes import ConsultaRecomendacoes, ResultadoConsulta


class ErroIntegracao(RuntimeError):
    """Falha esperada de consulta ou validação de um serviço externo."""


class ConsultaCancelada(Exception):
    """A seleção mudou ou o aplicativo foi fechado durante a consulta."""


@dataclass
class AmostrasDisponiveis:
    amostras: tuple[BuildObservada, ...]
    precos: dict[str, int]


class FonteBuilds(Protocol):
    def obter(
        self, heroi_id: int, funcao: Funcao,
        verificar_ativa: Callable[[], None] | None = None,
    ) -> AmostrasDisponiveis: ...


class DadosDota(Protocol):
    def obter_benchmarks(self, heroi_id: int, funcao: Funcao) -> dict[str, object] | None: ...

    def obter_taxas_meta(self) -> dict[int, float]: ...

    def obter_papeis(self) -> dict[int, tuple[str, ...]]: ...

    def obter_confrontos(self, heroi_id: int) -> tuple[Confronto, ...]: ...


class EstadoPartida(Protocol):
    def aplicar(self, atualizacao: AtualizacaoPartida, recebido_em: float) -> None: ...

    def snapshot(self) -> InstantaneoPartida: ...


class SaidaVoz(Protocol):
    def falar(self, texto: str) -> None: ...

    def encerrar(self) -> None: ...


class ConsultasEmSegundoPlano(Protocol):
    def solicitar(self, consulta: "ConsultaRecomendacoes") -> int: ...

    def obter_resultados(self) -> list[tuple[int, "ResultadoConsulta"]]: ...

    def encerrar(self) -> None: ...


class Posicao(TypedDict):
    x: int
    y: int


class Preferencias(TypedDict):
    posicoes: dict[str, Posicao]
    visibilidade: dict[str, bool]


class ArmazenamentoPreferencias(Protocol):
    def carregar(self) -> Preferencias: ...

    def salvar(self, preferencias: Preferencias) -> bool: ...


class PlataformaJanelas(Protocol):
    def identificar(self, identificador_tk: int) -> int: ...

    def aplicar_transparencia(self, identificador: int, ativar: bool) -> None: ...

    def em_foco(self) -> bool: ...
