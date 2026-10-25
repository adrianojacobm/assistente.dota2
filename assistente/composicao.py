"""Único ponto que conecta casos de uso, adaptadores e interface."""

import logging
import sys
import time
from typing import TYPE_CHECKING

from . import configuracao
from .aplicacao.configurar_integracao_gsi import ConfigurarIntegracaoGSI
from .aplicacao.consultar_recomendacoes import ConsultarRecomendacoes
from .aplicacao.contratos import (
    ConfiguracaoGSIEmSegundoPlano,
    InicializacaoEmSegundoPlano,
    PlataformaJanelas,
    SaidaVoz,
)
from .aplicacao.iniciar_dota import IniciarDota
from .aplicacao.processar_partida import ProcessarPartida
from .apresentacao.servidor_gsi import ServidorGSI
from .infraestrutura.configuracao_gsi_em_segundo_plano import ExecutorConfiguracaoGSI
from .infraestrutura.consultas_em_segundo_plano import ExecutorConsultas
from .infraestrutura.estado_compartilhado import Estado
from .infraestrutura.fontes import ClienteDadosDota, FonteDota2ProTracker
from .infraestrutura.inicializacao_em_segundo_plano import ExecutorInicializacao
from .infraestrutura.plataforma import (
    SistemaNaoSuportado,
    criar_iniciador_dota,
    criar_integracao_gsi,
    criar_plataforma_janelas,
    criar_saida_voz,
    identificar_sistema,
)
from .infraestrutura.preferencias_json import PreferenciasJson

if TYPE_CHECKING:
    import tkinter as tk
    from .apresentacao.painel import PainelPrincipal


def criar_painel(
    janela: "tk.Tk", assistente: ProcessarPartida, plataforma: PlataformaJanelas,
    inicializacao: InicializacaoEmSegundoPlano,
    integracao_gsi: ConfiguracaoGSIEmSegundoPlano | None = None,
) -> "PainelPrincipal":
    from .apresentacao.painel import PainelPrincipal

    caso_de_uso = ConsultarRecomendacoes(
        FonteDota2ProTracker(), ClienteDadosDota(), configuracao.ORCAMENTO_SAIDA_INICIAL,
        configuracao.PERCENTUAL_CORE_ITEM, configuracao.MIN_JOGOS_MATCHUP,
    )
    consultas = ExecutorConsultas(caso_de_uso.executar)
    try:
        return PainelPrincipal(
            janela, assistente, consultas, PreferenciasJson(), plataforma,
            configuracao.ANTECEDENCIA_MIN, configuracao.ANTECEDENCIA_MAX,
            inicializacao=inicializacao,
            integracao_gsi=integracao_gsi,
        )
    except Exception:
        consultas.encerrar()
        raise


def executar() -> int:
    try:
        identificar_sistema()
    except SistemaNaoSuportado as erro:
        print(str(erro), file=sys.stderr)
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
    voz: SaidaVoz | None = None
    assistente: ProcessarPartida | None = None
    plataforma: PlataformaJanelas | None = None
    inicializacao: ExecutorInicializacao | None = None
    integracao_gsi: ExecutorConfiguracaoGSI | None = None
    painel: PainelPrincipal | None = None
    servidor: ServidorGSI | None = None
    try:
        plataforma = criar_plataforma_janelas()
        voz = criar_saida_voz()
        assistente = ProcessarPartida(Estado(configuracao.SEM_SINAL_S), voz, time.time)
        iniciador = criar_iniciador_dota()
        try:
            inicializacao = ExecutorInicializacao(
                IniciarDota(iniciador), configuracao.PRAZO_INICIALIZACAO_DOTA_S,
                configuracao.INTERVALO_VERIFICACAO_DOTA_S,
            )
        except Exception:
            iniciador.encerrar()
            raise
        servidor = ServidorGSI(("127.0.0.1", configuracao.PORTA_GSI), assistente.processar)
        servidor.iniciar()
        integracao_gsi = ExecutorConfiguracaoGSI(
            ConfigurarIntegracaoGSI(criar_integracao_gsi(servidor.server_port)),
        )
        painel = criar_painel(janela, assistente, plataforma, inicializacao, integracao_gsi)
        janela.mainloop()
    except Exception:
        logging.getLogger(__name__).exception("Não foi possível executar o assistente desktop.")
        return 1
    finally:
        if painel is not None:
            painel.encerrar()
        if inicializacao is not None:
            inicializacao.encerrar()
        if integracao_gsi is not None:
            integracao_gsi.encerrar()
        if assistente is not None:
            assistente.encerrar()
        elif voz is not None:
            voz.encerrar()
        if servidor is not None:
            servidor.encerrar()
        if plataforma is not None:
            plataforma.encerrar()
        try:
            janela.destroy()
        except tk.TclError:
            logging.getLogger(__name__).debug("Janela já encerrada.")
    return 0
