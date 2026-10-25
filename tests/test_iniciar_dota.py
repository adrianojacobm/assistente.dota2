import threading
from unittest import TestCase
from unittest.mock import Mock

from assistente.aplicacao.contratos import ErroInicializacao, JogoNaoEncontrado
from assistente.aplicacao.iniciar_dota import EstadoExecucao, IniciarDota, ResultadoExecucao
from assistente.infraestrutura.inicializacao_em_segundo_plano import ExecutorInicializacao


class TestarIniciarDota(TestCase):
    def setUp(self) -> None:
        self.iniciador = Mock()
        self.caso = IniciarDota(self.iniciador)

    def test_delega_apenas_quando_nenhum_processo_foi_observado(self) -> None:
        self.iniciador.consultar.return_value = ResultadoExecucao(EstadoExecucao.NAO_OBSERVADO)
        esperado = ResultadoExecucao(EstadoExecucao.INICIADOR_ATIVO, pid_iniciador=7)
        self.iniciador.iniciar.return_value = esperado
        self.assertEqual(self.caso.executar(), esperado)
        self.iniciador.iniciar.assert_called_once_with()

    def test_jogo_existente_nao_e_reiniciado(self) -> None:
        esperado = ResultadoExecucao(EstadoExecucao.EM_EXECUCAO, pid_jogo=42)
        self.iniciador.consultar.return_value = esperado
        self.assertEqual(self.caso.executar(), esperado)
        self.iniciador.iniciar.assert_not_called()

    def test_solicitacao_pendente_nao_e_duplicada(self) -> None:
        self.iniciador.consultar.return_value = ResultadoExecucao(EstadoExecucao.SOLICITADO)
        self.assertEqual(self.caso.executar().estado, EstadoExecucao.SOLICITADO)
        self.iniciador.iniciar.assert_not_called()

    def test_jogo_nao_encontrado_retorna_falha_estruturada(self) -> None:
        self.iniciador.consultar.side_effect = JogoNaoEncontrado("Jogo não encontrado.")
        resultado = self.caso.executar()
        self.assertEqual(resultado.estado, EstadoExecucao.FALHA)
        self.assertEqual(resultado.erro, "Jogo não encontrado.")
        self.assertIsNone(resultado.pid_jogo)
        self.iniciador.iniciar.assert_not_called()

    def test_erro_de_inicializacao_preserva_caminho_conhecido(self) -> None:
        self.iniciador.consultar.return_value = ResultadoExecucao(
            EstadoExecucao.NAO_OBSERVADO, executavel="jogo/dota2",
        )
        self.iniciador.iniciar.side_effect = ErroInicializacao("Permissão negada.")
        resultado = self.caso.executar()
        self.assertEqual(resultado.estado, EstadoExecucao.FALHA)
        self.assertEqual(resultado.executavel, "jogo/dota2")
        self.assertIsNone(resultado.pid_jogo)

    def test_observacao_inconclusiva_nao_dispara_outro_jogo(self) -> None:
        self.iniciador.consultar.return_value = ResultadoExecucao(
            EstadoExecucao.NAO_CONFIRMADO, erro="Processos inacessíveis.",
        )
        self.assertEqual(self.caso.executar().estado, EstadoExecucao.NAO_CONFIRMADO)
        self.iniciador.iniciar.assert_not_called()

    def test_nao_permite_estado_em_execucao_sem_pid(self) -> None:
        with self.assertRaises(ValueError):
            ResultadoExecucao(EstadoExecucao.EM_EXECUCAO)
        with self.assertRaises(ValueError):
            ResultadoExecucao(EstadoExecucao.SOLICITADO, pid_iniciador=-1)


class TestarExecutorInicializacao(TestCase):
    def test_rejeita_prazos_e_intervalos_invalidos_sem_criar_thread(self) -> None:
        for prazo, intervalo in ((-1, 0.5), (1, 0), (float("nan"), 1), (1, float("inf"))):
            with self.subTest(prazo=prazo, intervalo=intervalo), self.assertRaises(ValueError):
                ExecutorInicializacao(Mock(), prazo, intervalo)

    def test_confirma_processo_sem_bloquear_solicitante(self) -> None:
        caso = Mock()
        caso.executar.return_value = ResultadoExecucao(EstadoExecucao.SOLICITADO, pid_iniciador=1)
        caso.consultar.return_value = ResultadoExecucao(EstadoExecucao.EM_EXECUCAO, pid_jogo=2)
        executor = ExecutorInicializacao(caso, prazo_s=1, intervalo_s=0.01)
        self.addCleanup(executor.encerrar)
        self.assertTrue(executor.solicitar())
        resultado = executor._resultados.get(timeout=2)
        while resultado.estado in (EstadoExecucao.SOLICITADO, EstadoExecucao.INICIADOR_ATIVO):
            resultado = executor._resultados.get(timeout=2)
        self.assertEqual(resultado.pid_jogo, 2)

    def test_prazo_excedido_nao_inventa_falha_nem_pid_do_jogo(self) -> None:
        caso = Mock()
        caso.executar.return_value = ResultadoExecucao(EstadoExecucao.INICIADOR_ATIVO, pid_iniciador=11)
        executor = ExecutorInicializacao(caso, prazo_s=0)
        self.addCleanup(executor.encerrar)
        executor.solicitar()
        resultado = executor._resultados.get(timeout=2)
        self.assertEqual(resultado.estado, EstadoExecucao.NAO_CONFIRMADO)
        self.assertEqual(resultado.pid_iniciador, 11)
        self.assertIsNone(resultado.pid_jogo)
        self.assertIsNone(resultado.erro)

    def test_nova_solicitacao_descarta_resultado_anterior_nao_consumido(self) -> None:
        caso = Mock()
        caso.executar.return_value = ResultadoExecucao(EstadoExecucao.EM_EXECUCAO, pid_jogo=1)
        executor = ExecutorInicializacao(caso)
        self.addCleanup(executor.encerrar)
        # Um resultado final pendente não pode ser entregue como resultado da próxima solicitação.
        executor._resultados.put_nowait(ResultadoExecucao(EstadoExecucao.EM_EXECUCAO, pid_jogo=9))
        executor.solicitar()
        resultado = executor._resultados.get(timeout=2)
        self.assertEqual(resultado.pid_jogo, 1)

    def test_limita_solicitacoes_e_descarta_resultados_apos_encerramento(self) -> None:
        iniciou, liberar = threading.Event(), threading.Event()
        caso = Mock()

        def executar() -> ResultadoExecucao:
            iniciou.set()
            self.assertTrue(liberar.wait(timeout=3))
            return ResultadoExecucao(EstadoExecucao.EM_EXECUCAO, pid_jogo=1)

        caso.executar.side_effect = executar
        executor = ExecutorInicializacao(caso)
        self.addCleanup(executor.encerrar)
        self.addCleanup(liberar.set)
        self.assertTrue(executor.solicitar())
        self.assertTrue(iniciou.wait(timeout=2))
        self.assertFalse(executor.solicitar())
        executor._encerrado.set()
        liberar.set()
        executor.encerrar()
        self.assertEqual(executor.obter_resultados(), [])
        self.assertFalse(executor.solicitar())
        caso.encerrar.assert_called_once()

    def test_erro_inesperado_e_registrado_e_traduzido(self) -> None:
        caso = Mock()
        caso.executar.side_effect = RuntimeError("defeito")
        executor = ExecutorInicializacao(caso)
        self.addCleanup(executor.encerrar)
        with self.assertLogs("assistente.infraestrutura.inicializacao_em_segundo_plano", "ERROR"):
            executor.solicitar()
            resultado = executor._resultados.get(timeout=2)
        self.assertEqual(resultado.estado, EstadoExecucao.FALHA)
