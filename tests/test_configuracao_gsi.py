import threading
from collections.abc import Callable
from unittest import TestCase
from unittest.mock import Mock

from assistente.aplicacao.configurar_integracao_gsi import (
    ConfigurarIntegracaoGSI,
    ConfirmacaoReparoGSI,
    EstadoConfiguracaoGSI,
    ResultadoConfiguracaoGSI,
)
from assistente.aplicacao.contratos import ConsultaCancelada, ErroConfiguracaoGSI
from assistente.apresentacao.formatacao import (
    formatar_configuracao_gsi,
    formatar_sinal_gsi,
    resumo_configuracao_gsi,
)
from assistente.infraestrutura.configuracao_gsi_em_segundo_plano import ExecutorConfiguracaoGSI
from assistente.infraestrutura.estado_compartilhado import Estado


class TestarConfiguracaoGSI(TestCase):
    def test_verificacao_apenas_consulta_o_adaptador(self) -> None:
        integracao = Mock()
        integracao.verificar.return_value = ResultadoConfiguracaoGSI(
            EstadoConfiguracaoGSI.AUSENTE, "jogo/a.cfg",
        )
        caso = ConfigurarIntegracaoGSI(integracao)
        self.assertEqual(caso.verificar(), integracao.verificar.return_value)
        integracao.configurar.assert_not_called()

    def test_acao_encaminha_confirmacao_e_cancelamento(self) -> None:
        integracao = Mock()
        caso = ConfigurarIntegracaoGSI(integracao)
        confirmacao = ConfirmacaoReparoGSI("jogo/a.cfg", "assinatura")
        verificar = Mock()
        self.assertEqual(caso.executar(confirmacao, verificar), integracao.configurar.return_value)
        integracao.configurar.assert_called_once_with(confirmacao, verificar)

    def test_falhas_esperadas_preservam_caminho_e_backup(self) -> None:
        integracao = Mock()
        erro = ErroConfiguracaoGSI("Sem permissão.", "jogo/a.cfg", "jogo/copia.bak")
        integracao.verificar.side_effect = erro
        integracao.configurar.side_effect = erro
        caso = ConfigurarIntegracaoGSI(integracao)
        for resultado in (caso.verificar(), caso.executar()):
            self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
            self.assertEqual(resultado.caminho, "jogo/a.cfg")
            self.assertEqual(resultado.copia_seguranca, "jogo/copia.bak")
            self.assertIn("Sem permissão", resultado.erro)

    def test_cancelamento_nao_e_convertido_em_falha(self) -> None:
        integracao = Mock()
        integracao.configurar.side_effect = ConsultaCancelada()
        with self.assertRaises(ConsultaCancelada):
            ConfigurarIntegracaoGSI(integracao).executar()

    def test_resultado_rejeita_reparo_sem_backup_ou_confirmacao_de_outro_arquivo(self) -> None:
        with self.assertRaises(ValueError):
            ResultadoConfiguracaoGSI(EstadoConfiguracaoGSI.REPARADO, "jogo/a.cfg")
        with self.assertRaises(ValueError):
            ResultadoConfiguracaoGSI(
                EstadoConfiguracaoGSI.CONFLITO, "jogo/a.cfg",
                reparo=ConfirmacaoReparoGSI("outro.cfg", "assinatura"),
            )


class TestarFormatacaoGSI(TestCase):
    def test_arquivo_pronto_nao_comprova_conexao(self) -> None:
        resultado = ResultadoConfiguracaoGSI(EstadoConfiguracaoGSI.CONFIGURADO, "jogo/a.cfg")
        self.assertIn("não confirma", formatar_configuracao_gsi(resultado))
        self.assertIn("separadamente", resumo_configuracao_gsi(resultado))
        self.assertIn("aguardando dados", formatar_sinal_gsi(Estado().snapshot()))

    def test_sinal_distingue_menu_partida_e_dados_obsoletos(self) -> None:
        estado = Estado(sem_sinal_s=90, relogio=lambda: 100)
        estado.atualizar(conectado=True, ultimo_post=99.0)
        self.assertIn("aguardando partida", formatar_sinal_gsi(estado.snapshot()))
        estado.atualizar(em_partida=True)
        self.assertIn("dados da partida recebidos", formatar_sinal_gsi(estado.snapshot()))
        estado.atualizar(ultimo_post=1.0)
        self.assertIn("sem dados recentes", formatar_sinal_gsi(estado.snapshot()))

    def test_reparo_informa_backup_e_reinicio_condicional(self) -> None:
        resultado = ResultadoConfiguracaoGSI(
            EstadoConfiguracaoGSI.REPARADO, "jogo/a.cfg", copia_seguranca="jogo/copia.bak",
        )
        texto = formatar_configuracao_gsi(resultado)
        self.assertIn("jogo/copia.bak", texto)
        self.assertIn("Se o Dota já estava aberto", texto)


class TestarExecutorConfiguracaoGSI(TestCase):
    def test_confirmacao_nao_pode_ser_usada_em_uma_simples_verificacao(self) -> None:
        executor = ExecutorConfiguracaoGSI(Mock())
        self.addCleanup(executor.encerrar)
        with self.assertRaises(ValueError):
            executor.solicitar(confirmacao=ConfirmacaoReparoGSI("jogo/a.cfg", "assinatura"))

    def test_verificacao_padrao_nao_grava(self) -> None:
        caso = Mock()
        caso.verificar.return_value = ResultadoConfiguracaoGSI(EstadoConfiguracaoGSI.AUSENTE, "jogo/a.cfg")
        executor = ExecutorConfiguracaoGSI(caso)
        self.addCleanup(executor.encerrar)
        self.assertTrue(executor.solicitar())
        self.assertEqual(executor._resultados.get(timeout=2), caso.verificar.return_value)
        caso.executar.assert_not_called()

    def test_limita_solicitacoes_pendentes_e_nao_bloqueia_o_solicitante(self) -> None:
        iniciou, liberar = threading.Event(), threading.Event()
        caso = Mock()

        def verificar() -> ResultadoConfiguracaoGSI:
            iniciou.set()
            self.assertTrue(liberar.wait(timeout=3))
            return ResultadoConfiguracaoGSI(EstadoConfiguracaoGSI.AUSENTE, "jogo/a.cfg")

        caso.verificar.side_effect = verificar
        executor = ExecutorConfiguracaoGSI(caso)
        self.addCleanup(executor.encerrar)
        self.addCleanup(liberar.set)
        self.assertTrue(executor.solicitar())
        self.assertTrue(iniciou.wait(timeout=2))
        self.assertFalse(executor.solicitar(configurar=True))
        liberar.set()
        self.assertEqual(executor._resultados.get(timeout=2).estado, EstadoConfiguracaoGSI.AUSENTE)

    def test_acao_encaminha_confirmacao_e_descarta_resultado_anterior(self) -> None:
        caso = Mock()
        caso.executar.return_value = ResultadoConfiguracaoGSI(EstadoConfiguracaoGSI.CRIADO, "jogo/a.cfg")
        executor = ExecutorConfiguracaoGSI(caso)
        self.addCleanup(executor.encerrar)
        executor._resultados.put_nowait(ResultadoConfiguracaoGSI(EstadoConfiguracaoGSI.AUSENTE, "antigo.cfg"))
        confirmacao = ConfirmacaoReparoGSI("jogo/a.cfg", "assinatura")
        self.assertTrue(executor.solicitar(configurar=True, confirmacao=confirmacao))
        self.assertEqual(executor._resultados.get(timeout=2).estado, EstadoConfiguracaoGSI.CRIADO)
        caso.executar.assert_called_once_with(confirmacao, executor._verificar_ativa)

    def test_fechamento_cancela_gravacao_e_descarta_resultados(self) -> None:
        iniciou, liberar = threading.Event(), threading.Event()
        caso = Mock()

        def executar(
            confirmacao: ConfirmacaoReparoGSI | None, verificar: Callable[[], None],
        ) -> ResultadoConfiguracaoGSI:
            iniciou.set()
            self.assertTrue(liberar.wait(timeout=3))
            verificar()
            self.fail("Não deveria gravar após o fechamento.")

        caso.executar.side_effect = executar
        executor = ExecutorConfiguracaoGSI(caso)
        self.addCleanup(executor.encerrar)
        self.addCleanup(liberar.set)
        executor.solicitar(configurar=True)
        self.assertTrue(iniciou.wait(timeout=2))
        fechamento = threading.Thread(target=executor.encerrar)
        fechamento.start()
        self.assertTrue(executor._encerrado.wait(timeout=1))
        liberar.set()
        fechamento.join(timeout=2)
        self.assertFalse(fechamento.is_alive())
        self.assertFalse(executor._trabalhador.is_alive())
        self.assertEqual(executor.obter_resultados(), [])
        self.assertFalse(executor.solicitar())

    def test_erro_inesperado_e_registrado_sem_encerrar_a_interface(self) -> None:
        caso = Mock()
        caso.verificar.side_effect = RuntimeError("defeito")
        executor = ExecutorConfiguracaoGSI(caso)
        self.addCleanup(executor.encerrar)
        with self.assertLogs("assistente.infraestrutura.configuracao_gsi_em_segundo_plano", "ERROR"):
            executor.solicitar()
            resultado = executor._resultados.get(timeout=2)
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
