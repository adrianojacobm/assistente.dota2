from dataclasses import dataclass
from enum import Enum
from math import isfinite


class Funcao(str, Enum):
    CARREGADOR = "CARRY"
    MEIO = "MID"
    ROTA_DIFICIL = "OFFLANE"
    SUPORTE = "SUP"
    SUPORTE_PRINCIPAL = "HARD_SUPPORT"

    @classmethod
    def normalizar(cls, valor: str | None) -> "Funcao":
        try:
            return cls((valor or "CARRY").upper())
        except ValueError:
            return cls.CARREGADOR

    @property
    def rotulo(self) -> str:
        return {
            self.CARREGADOR: "Carry", self.MEIO: "Mid",
            self.ROTA_DIFICIL: "Offlane", self.SUPORTE: "Support",
            self.SUPORTE_PRINCIPAL: "Hard Support",
        }[self]

    @property
    def posicao(self) -> int:
        return list(Funcao).index(self) + 1

    @property
    def perfil_counter(self) -> str:
        return "SUP" if self == self.SUPORTE_PRINCIPAL else self.value


class Fase(str, Enum):
    INICIO = "early"
    MEIO = "mid"
    FINAL = "late"

    @property
    def rotulo(self) -> str:
        return {
            self.INICIO: "Early (<12m)", self.MEIO: "Mid (12–30m)",
            self.FINAL: "Late (30m+)",
        }[self]


@dataclass(frozen=True)
class ItemObservado:
    nome: str
    minuto: float
    percentual: float
    contagem: float = 0

    def __post_init__(self) -> None:
        if not self.nome.strip():
            raise ValueError("O item precisa de nome.")
        if not all(isfinite(valor) for valor in (self.minuto, self.percentual, self.contagem)):
            raise ValueError("As estatísticas do item precisam ser finitas.")
        if not 0 <= self.percentual <= 1 or self.contagem < 0:
            raise ValueError("Frequência ou contagem de item inválida.")

    @property
    def fase(self) -> Fase:
        if self.minuto < 12:
            return Fase.INICIO
        return Fase.MEIO if self.minuto < 30 else Fase.FINAL


@dataclass(frozen=True)
class BuildObservada:
    nome: str
    partidas: int
    pacotes: tuple[tuple[str, ...], ...] = ()
    itens: tuple[ItemObservado, ...] = ()
    taxa_vitoria: float | None = None
    pacotes_informados: bool = False

    def __post_init__(self) -> None:
        if self.partidas < 0:
            raise ValueError("A amostra não pode ser negativa.")
        if self.taxa_vitoria is not None and (
            not isfinite(self.taxa_vitoria) or not 0 <= self.taxa_vitoria <= 1
        ):
            raise ValueError("Taxa de vitória inválida.")


@dataclass(frozen=True)
class ItemQuantidade:
    nome: str
    quantidade: int

    def __post_init__(self) -> None:
        if not self.nome.strip() or self.quantidade < 1:
            raise ValueError("Item ou quantidade inválida.")


@dataclass(frozen=True)
class Build:
    heroi: str
    funcao: Funcao
    observada: BuildObservada
    saida: tuple[ItemQuantidade, ...] = ()
    inicio: tuple[str, ...] = ()
    meio: tuple[str, ...] = ()
    final: tuple[str, ...] = ()
    situacionais: tuple[ItemObservado, ...] = ()
    custo_saida: int | None = None


@dataclass(frozen=True)
class Confronto:
    heroi_id: int
    jogos: int
    vitorias_inimigo: int

    def __post_init__(self) -> None:
        if self.jogos < 0 or not 0 <= self.vitorias_inimigo <= self.jogos:
            raise ValueError("Resultados de confronto inválidos.")


@dataclass(frozen=True)
class CounterPick:
    heroi: str
    percentual_confronto: float
    percentual_meta: float
    jogos: int
    pontuacao: float
