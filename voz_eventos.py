# -*- coding: utf-8 -*-
"""Timers de evento (stack/pull/runa/etc.), texto-pra-voz (SAPI) e o Estado compartilhado da partida."""
import queue
import threading
import time
from dataclasses import dataclass

import config


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


def calcular_metas(tempo, bench=None, modo="CARRY"):
    """Metas derivadas do percentil normalizado da OpenDota quando disponível.

    LH e denies são metas acumuladas (taxa por minuto × minutos decorridos).
    GPM/XPM são taxas e, portanto, são comparadas diretamente com a taxa do
    percentil selecionado; não são multiplicadas por tempo nem por fatores de
    função, porque a consulta de benchmark já é filtrada por core/support.
    """
    if tempo <= 0:
        return {"lh": 0, "dn": 0, "gpm": 0, "xpm": 0, "k": 0, "d": 0, "a": 0}

    minutos = tempo / 60.0
    bench = bench if isinstance(bench, dict) else {}

    def taxa(chave, fallback):
        valor = bench.get(chave)
        try:
            valor = float(valor)
            return valor if valor >= 0 else fallback
        except (TypeError, ValueError):
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


class Voz:
    def __init__(self):
        self.fila = queue.Queue()
        self.disponivel = True
        threading.Thread(target=self._worker, daemon=True).start()

    def falar(self, texto):
        if self.disponivel:
            self.fila.put(texto)

    def _worker(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Rate, speaker.Volume = 2, 100
            for v in speaker.GetVoices():
                if "portuguese" in v.GetDescription().lower() or "brasil" in v.GetDescription().lower():
                    speaker.Voice = v
                    break
            while True:
                texto = self.fila.get()
                if texto is None:
                    break
                speaker.Speak(texto)
        except Exception:
            self.disponivel = False


class Estado:
    def __init__(self):
        self.lock = threading.Lock()
        self._d = {
            "conectado": False, "em_partida": False, "tempo": -999,
            "heroi": "Aguardando...", "lh": 0, "dn": 0, "gpm": 0,
            "xpm": 0, "k": 0, "d": 0, "a": 0, "ultimo_post": 0.0,
        }

    def atualizar(self, **kw):
        with self.lock:
            self._d.update(kw)

    def snapshot(self):
        with self.lock:
            d = dict(self._d)
        d["sem_sinal"] = d["conectado"] and (time.time() - d["ultimo_post"] > config.SEM_SINAL_S)
        if d["sem_sinal"]:
            d["em_partida"] = False
        return d
