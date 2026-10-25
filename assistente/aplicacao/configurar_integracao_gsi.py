from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from .contratos import ErroConfiguracaoGSI, IntegracaoGSI


class EstadoConfiguracaoGSI(Enum):
    AUSENTE = "ausente"
    CONFIGURADO = "configurado"
    CRIADO = "criado"
    REPARADO = "reparado"
    CONFLITO = "conflito"
    FALHA = "falha"


@dataclass(frozen=True)
class ConfirmacaoReparoGSI:
    caminho: str
    assinatura: str


@dataclass(frozen=True)
class ResultadoConfiguracaoGSI:
    estado: EstadoConfiguracaoGSI
    caminho: str | None = None
    erro: str | None = None
    reparo: ConfirmacaoReparoGSI | None = None
    copia_seguranca: str | None = None

    def __post_init__(self) -> None:
        if self.estado != EstadoConfiguracaoGSI.FALHA and not self.caminho:
            raise ValueError("O resultado da configuração precisa identificar o arquivo.")
        if self.estado == EstadoConfiguracaoGSI.FALHA and not self.erro:
            raise ValueError("Uma falha precisa informar sua causa.")
        if self.estado == EstadoConfiguracaoGSI.REPARADO and not self.copia_seguranca:
            raise ValueError("Um reparo precisa preservar uma cópia de segurança.")
        if self.reparo is not None and (
            self.estado != EstadoConfiguracaoGSI.CONFLITO or self.reparo.caminho != self.caminho
        ):
            raise ValueError("A confirmação deve corresponder ao arquivo em conflito.")


class ConfigurarIntegracaoGSI:
    """Consulta a configuração; somente uma ação explícita pode gravá-la."""

    def __init__(self, integracao: IntegracaoGSI) -> None:
        self._integracao = integracao

    def verificar(self) -> ResultadoConfiguracaoGSI:
        try:
            return self._integracao.verificar()
        except ErroConfiguracaoGSI as erro:
            return self._falha(erro)

    def executar(
        self, confirmacao: ConfirmacaoReparoGSI | None = None,
        verificar_ativa: Callable[[], None] | None = None,
    ) -> ResultadoConfiguracaoGSI:
        try:
            return self._integracao.configurar(confirmacao, verificar_ativa)
        except ErroConfiguracaoGSI as erro:
            return self._falha(erro)

    @staticmethod
    def _falha(erro: ErroConfiguracaoGSI) -> ResultadoConfiguracaoGSI:
        return ResultadoConfiguracaoGSI(
            EstadoConfiguracaoGSI.FALHA, caminho=erro.caminho, erro=str(erro),
            copia_seguranca=erro.copia_seguranca,
        )
