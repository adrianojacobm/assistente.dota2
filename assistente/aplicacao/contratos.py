from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypedDict

from assistente.dominio.modelos import BuildObservada, Confronto, Funcao
from assistente.dominio.partida import AtualizacaoPartida, InstantaneoPartida

if TYPE_CHECKING:
    from .configurar_integracao_gsi import ConfirmacaoReparoGSI, ResultadoConfiguracaoGSI
    from .consultar_recomendacoes import ConsultaRecomendacoes, ResultadoConsulta
    from .iniciar_dota import ResultadoExecucao


class ErroIntegracao(RuntimeError):
    """Falha esperada de consulta ou validação de um serviço externo."""


class ConsultaCancelada(Exception):
    """A seleção mudou ou o aplicativo foi fechado durante a consulta."""


class ErroInicializacao(ErroIntegracao):
    """Falha esperada ao localizar ou solicitar a abertura do jogo."""


class JogoNaoEncontrado(ErroInicializacao):
    """Nenhuma instalação utilizável foi encontrada nas bibliotecas Steam."""


class ErroConfiguracaoGSI(ErroIntegracao):
    """Falha de descoberta, validação ou acesso ao arquivo GSI do assistente."""

    def __init__(
        self, mensagem: str, caminho: str | None = None, copia_seguranca: str | None = None,
    ) -> None:
        super().__init__(mensagem)
        self.caminho = caminho
        self.copia_seguranca = copia_seguranca


class IntegracaoGSI(Protocol):
    def verificar(self) -> "ResultadoConfiguracaoGSI": ...

    def configurar(
        self, confirmacao: "ConfirmacaoReparoGSI | None" = None,
        verificar_ativa: Callable[[], None] | None = None,
    ) -> "ResultadoConfiguracaoGSI": ...


class ConfiguracaoGSIEmSegundoPlano(Protocol):
    def solicitar(
        self, configurar: bool = False, confirmacao: "ConfirmacaoReparoGSI | None" = None,
    ) -> bool: ...

    def obter_resultados(self) -> list["ResultadoConfiguracaoGSI"]: ...

    def encerrar(self) -> None: ...


class IniciadorDota(Protocol):
    def iniciar(self) -> "ResultadoExecucao": ...

    def consultar(self) -> "ResultadoExecucao": ...

    def encerrar(self) -> None: ...


class InicializacaoEmSegundoPlano(Protocol):
    def solicitar(self) -> bool: ...

    def obter_resultados(self) -> list["ResultadoExecucao"]: ...

    def encerrar(self) -> None: ...


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
    @property
    def disponivel(self) -> bool: ...

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
    @property
    def avisos(self) -> tuple[str, ...]: ...

    def identificar(self, identificador_tk: int) -> int: ...

    def aplicar_transparencia(self, identificador: int, ativar: bool) -> None: ...

    def em_foco(self) -> bool: ...

    def encerrar(self) -> None: ...
