"""Único ponto que conecta casos de uso, adaptadores e interface."""

import logging
import sys
import time
from typing import TYPE_CHECKING

from . import configuracao
from .aplicacao.consultar_recomendacoes import ConsultarRecomendacoes
from .aplicacao.processar_partida import ProcessarPartida
from .apresentacao.servidor_gsi import ServidorGSI
from .infraestrutura.consultas_em_segundo_plano import ExecutorConsultas
from .infraestrutura.estado_compartilhado import Estado
from .infraestrutura.fontes import ClienteDadosDota, FonteDota2ProTracker
from .infraestrutura.plataforma_windows import PlataformaWindows, recursos_nativos_disponiveis
from .infraestrutura.preferencias_json import PreferenciasJson
from .infraestrutura.voz_windows import Voz

if TYPE_CHECKING:
    import tkinter as tk
    from .apresentacao.painel import PainelPrincipal


def criar_painel(janela: "tk.Tk", assistente: ProcessarPartida) -> "PainelPrincipal":
    from .apresentacao.painel import PainelPrincipal

    caso_de_uso = ConsultarRecomendacoes(
        FonteDota2ProTracker(), ClienteDadosDota(), configuracao.ORCAMENTO_SAIDA_INICIAL,
        configuracao.PERCENTUAL_CORE_ITEM, configuracao.MIN_JOGOS_MATCHUP,
    )
    consultas = ExecutorConsultas(caso_de_uso.executar)
    try:
        return PainelPrincipal(
            janela, assistente, consultas, PreferenciasJson(), PlataformaWindows(),
            configuracao.ANTECEDENCIA_MIN, configuracao.ANTECEDENCIA_MAX,
        )
    except Exception:
        consultas.encerrar()
        raise


def executar() -> int:
    if not recursos_nativos_disponiveis():
        print(
            "A interface nativa requer Windows (Win32/SAPI). "
            "O domínio e os testes podem ser usados em outras plataformas.", file=sys.stderr,
        )
        return 1
    try:
        import tkinter as tk
    except ImportError as erro:
        print(f"Tkinter indisponível. Instale uma distribuição Python com Tcl/Tk: {erro}", file=sys.stderr)
        return 1
    try:
        janela = tk.Tk()
    except tk.TclError as erro:
        print(f"Não foi possível iniciar a interface: {erro}", file=sys.stderr)
        return 1
    assistente = ProcessarPartida(Estado(configuracao.SEM_SINAL_S), Voz(), time.time)
    painel: PainelPrincipal | None = None
    servidor: ServidorGSI | None = None
    try:
        servidor = ServidorGSI(("127.0.0.1", configuracao.PORTA_GSI), assistente.processar)
        servidor.iniciar()
        painel = criar_painel(janela, assistente)
        janela.mainloop()
    except OSError:
        logging.getLogger(__name__).exception("Não foi possível iniciar o servidor GSI.")
        return 1
    finally:
        if painel is not None:
            painel.consultas.encerrar()
        assistente.encerrar()
        if servidor is not None:
            servidor.encerrar()
        try:
            janela.destroy()
        except tk.TclError:
            logging.getLogger(__name__).debug("Janela já encerrada.")
    return 0
