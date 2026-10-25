# -*- coding: utf-8 -*-
"""Eventos e cálculos puros da partida."""
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import TypedDict

AVISOS_POR_FUNCAO = {
    "CARRY": frozenset({"bounty", "catapulta"}),
    "MID": frozenset({"agua", "bounty", "lotus", "sabedoria"}),
    "OFFLANE": frozenset({"bounty", "lotus", "sabedoria", "catapulta"}),
    "SUP": frozenset({"stack", "pull", "agua", "bounty", "lotus", "sabedoria", "tormentor"}),
}


@dataclass(frozen=True)
class Evento:
    chave: str
    rotulo: str
    abrev: str
    nome_hud: str
    fala: str
    primeiro: int
    intervalo: int
    antecedencia: int
    inicio: float = float("-inf")
    fim: float = float("inf")
    ajustavel: bool = True


EVENTOS = (
    Evento("stack", "Stack", "Stk:", "STACK", "Hora do stack", 120, 60, 20, inicio=60, fim=2100),
    Evento("pull", "Pull", "Pull:", "PULL", "Hora do pull", 78, 30, 10, inicio=60, fim=900),
    Evento("agua", "Runa", "Runa:", "RUNA", "Runa de água/power", 120, 120, 25),
    Evento("bounty", "Bounty", "Bnty:", "BOUNTY", "Runa de bounty", 0, 240, 25),
    Evento("lotus", "Lótus", "Lót:", "LÓTUS", "Hora da lótus", 180, 180, 20),
    Evento("sabedoria", "Sabedoria", "Sab:", "XP", "Santuário de sabedoria", 420, 420, 20),
    Evento("tormentor", "Tormentor", "Torm:", "", "Hora do tormentor", 1200, 0, 30),
    Evento("catapulta", "Catapulta", "Cat:", "", "Onda de catapulta", 300, 300, 10, fim=600, ajustavel=False),
)
EVENTOS_HUD = [e for e in EVENTOS if e.nome_hud]


def calcular_metas(
    tempo: int, bench: Mapping[str, object] | None = None, modo: str = "CARRY",
) -> dict[str, int]:
    """Metas derivadas do percentil normalizado da OpenDota quando disponível.

    LH e denies são metas acumuladas (taxa por minuto × minutos decorridos).
    GPM/XPM são taxas e, portanto, são comparadas diretamente com a taxa do
    percentil selecionado; não são multiplicadas por tempo nem por fatores de
    função. A efetividade do filtro core/support depende do contrato do provedor.
    """
    if tempo <= 0:
        return {"lh": 0, "dn": 0, "gpm": 0, "xpm": 0, "k": 0, "d": 0, "a": 0}

    minutos = tempo / 60.0
    bench = bench if isinstance(bench, Mapping) else {}

    def taxa(chave: str, fallback: float) -> float:
        valor = bench.get(chave)
        try:
            valor = float(valor) if isinstance(valor, (str, int, float)) else fallback
            return valor if isfinite(valor) and valor >= 0 else fallback
        except (ValueError, OverflowError):
            return fallback

    # Fallbacks abaixo só são usados se a API não tiver aquele percentil.
    lh_taxa = taxa("lh_min", 7.0 * (0.35 if modo == "SUP" else 1.0))
    dn_taxa = taxa("dn_min", 1.8 if modo == "MID" else (0.5 if modo == "SUP" else 1.5))
    gpm_meta = taxa("gpm", 350 + minutos * 8)
    xpm_meta = taxa("xpm", (400 + minutos * 10) * (1.1 if modo == "MID" else (0.8 if modo == "SUP" else 1.0)))
    kills_taxa = taxa("k_min", 0.35 if modo != "SUP" else 0.20)
    assists_taxa = taxa("a_min", 0.95 if modo == "SUP" else (0.8 if modo == "MID" else 0.6))

    return {
        "lh": int(round(minutos * lh_taxa)),
        "dn": int(round(minutos * dn_taxa)),
        "gpm": int(round(gpm_meta)),
        "xpm": int(round(xpm_meta)),
        "k": int(round(minutos * kills_taxa)),
        "d": int(round(minutos * 0.25)),
        "a": int(round(minutos * assists_taxa)),
    }


class InstantaneoPartida(TypedDict):
    conectado: bool
    em_partida: bool
    tempo: int
    heroi: str
    lh: int
    dn: int
    gpm: int
    xpm: int
    k: int
    d: int
    a: int
    ultimo_post: float
    sem_sinal: bool


@dataclass(frozen=True)
class AtualizacaoPartida:
    em_partida: bool
    identificador: str | None = None
    pre_jogo: bool = False
    tempo: int = 0
    heroi: str = "Aguardando..."
    ultimos_golpes: int = 0
    negacoes: int = 0
    ouro_minuto: int = 0
    experiencia_minuto: int = 0
    abates: int = 0
    mortes: int = 0
    assistencias: int = 0

    def __post_init__(self) -> None:
        if any(valor < 0 for valor in (
            self.ultimos_golpes, self.negacoes, self.ouro_minuto, self.experiencia_minuto,
            self.abates, self.mortes, self.assistencias,
        )):
            raise ValueError("Estatísticas da partida não podem ser negativas.")


def segundos_para_evento(evento: Evento, tempo: int) -> int:
    if tempo <= evento.primeiro:
        return evento.primeiro - tempo
    return (-(tempo - evento.primeiro)) % evento.intervalo if evento.intervalo else -1


def avaliar_eventos(
    tempo: int, ativos: Mapping[str, bool], antecedencias: Mapping[str, int],
) -> str:
    frases = [
        evento.fala for evento in EVENTOS
        if ativos.get(evento.chave) and evento.inicio <= tempo <= evento.fim
        and segundos_para_evento(evento, tempo) == antecedencias.get(evento.chave, evento.antecedencia)
    ]
    return ", e ".join(frases)
