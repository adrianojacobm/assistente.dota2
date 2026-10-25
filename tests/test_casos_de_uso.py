from concurrent.futures import ThreadPoolExecutor
from unittest import TestCase
from unittest.mock import Mock

from assistente.aplicacao.consultar_recomendacoes import ConsultaRecomendacoes, ConsultarRecomendacoes
from assistente.aplicacao.contratos import AmostrasDisponiveis, ErroIntegracao
from assistente.aplicacao.processar_partida import ProcessarPartida
from assistente.apresentacao.formatacao import formatar_painel
from assistente.dominio.modelos import BuildObservada, Funcao
from assistente.dominio.partida import AtualizacaoPartida
from assistente.infraestrutura.estado_compartilhado import Estado


class TestarConsulta(TestCase):
    def setUp(self) -> None:
        self.fonte = Mock()
        self.fonte.obter.return_value = AmostrasDisponiveis((BuildObservada("exemplo", 100),), {})
        self.dados = Mock()
        self.dados.obter_benchmarks.return_value = {"gpm": 500}
        self.dados.obter_taxas_meta.return_value = {}
        self.dados.obter_papeis.return_value = {}
        self.dados.obter_confrontos.return_value = ()
        self.caso = ConsultarRecomendacoes(self.fonte, self.dados)

    def test_offlane_chega_intacto_a_todas_as_regras(self) -> None:
        resultado = self.caso.executar(
            ConsultaRecomendacoes("Sven", Funcao.ROTA_DIFICIL, ameaca="Phantom Assassin")
        )
        self.fonte.obter.assert_called_once_with(18, Funcao.ROTA_DIFICIL)
        self.dados.obter_benchmarks.assert_called_once_with(18, Funcao.ROTA_DIFICIL)
        self.assertIn("Heaven's Halberd", resultado.opcoes)
        self.assertNotIn("Monkey King Bar", resultado.opcoes)

    def test_erro_da_build_nao_impede_opcoes_e_benchmarks(self) -> None:
        self.fonte.obter.side_effect = ErroIntegracao("403")
        resultado = self.caso.executar(
            ConsultaRecomendacoes("Sven", Funcao.SUPORTE, ameaca="Phantom Assassin")
        )
        self.assertIsNone(resultado.build)
        self.assertIn("403", resultado.erro_build)
        self.assertEqual(resultado.benchmark, {"gpm": 500})
        self.assertIn("Ghost Scepter", resultado.opcoes)

    def test_erro_secundario_nao_descarta_build_valida(self) -> None:
        self.dados.obter_taxas_meta.side_effect = ErroIntegracao("Sem estatísticas")
        resultado = self.caso.executar(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR, ameaca="Axe"))
        self.assertIsNotNone(resultado.build)
        self.assertIn("Sem estatísticas", resultado.avisos)

    def test_sem_alvos_nao_consulta_counters_externos(self) -> None:
        self.caso.executar(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR))
        self.dados.obter_taxas_meta.assert_not_called()
        self.dados.obter_confrontos.assert_not_called()

    def test_alvos_repetidos_sao_consultados_uma_vez(self) -> None:
        self.caso.executar(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR, ("Axe", "Axe"), "Axe"))
        self.dados.obter_confrontos.assert_called_once_with(2)

    def test_sem_benchmark_nao_reutiliza_resultado_anterior(self) -> None:
        consulta = ConsultaRecomendacoes("Sven", Funcao.CARREGADOR)
        self.assertIsNotNone(self.caso.executar(consulta).benchmark)
        self.dados.obter_benchmarks.return_value = None
        resultado = self.caso.executar(consulta)
        self.assertIsNone(resultado.benchmark)
        self.assertIn("Benchmarks indisponíveis", formatar_painel(resultado))


class TestarProcessamentoPartida(TestCase):
    def setUp(self) -> None:
        self.voz = Mock()
        self.estado = Estado(relogio=lambda: 100)
        self.assistente = ProcessarPartida(self.estado, self.voz, lambda: 100)

    def atualizar(self, partida: str | None, tempo: int, pre_jogo: bool = False) -> None:
        self.assistente.processar(AtualizacaoPartida(True, partida, pre_jogo, tempo, "Sven"))

    def test_nova_partida_reinicia_buybacks(self) -> None:
        self.atualizar("1", 900)
        self.assistente.registrar_buyback(0)
        self.atualizar("2", 0)
        self.assertEqual(self.assistente.bb_timers, [0] * 10)
        self.assertEqual(self.assistente.bb_avisados, [False] * 10)

    def test_post_antigo_nao_reabre_partida_encerrada(self) -> None:
        self.atualizar("1", 900)
        self.atualizar("2", 0)
        self.atualizar("1", 901)
        self.assertEqual(self.estado.snapshot()["tempo"], 0)

    def test_pausa_e_post_atrasado_nao_reiniciam_buyback(self) -> None:
        self.atualizar("1", 600)
        self.assistente.registrar_buyback(0)
        self.atualizar("1", 600)
        self.atualizar("1", 599)
        self.assertEqual(self.assistente.bb_timers[0], 1080)
        self.assertEqual(self.estado.snapshot()["tempo"], 600)

    def test_sem_id_reinicia_so_em_pre_jogo_confirmado(self) -> None:
        self.atualizar(None, 600)
        self.assistente.registrar_buyback(0)
        self.atualizar(None, 599)
        self.assertEqual(self.assistente.bb_timers[0], 1080)
        self.atualizar(None, -60, pre_jogo=True)
        self.assertEqual(self.assistente.bb_timers[0], 0)

    def test_posts_concorrentes_nao_duplicam_fala(self) -> None:
        configuracao = self.assistente.obter_configuracao()
        configuracao["voz"] = {"stack": True}
        configuracao["antecedencias"] = {"stack": 20}
        self.assistente.configurar(configuracao)
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: self.atualizar("1", 100), range(20)))
        self.voz.falar.assert_called_once_with("Hora do stack")

    def test_selecao_zero_nao_suprime_aviso_no_pre_jogo_negativo(self) -> None:
        configuracao = self.assistente.obter_configuracao()
        configuracao["voz"] = {"bounty": True}
        self.assistente.configurar(configuracao)
        self.atualizar("1", 0, pre_jogo=True)
        self.atualizar("1", -60, pre_jogo=True)
        self.atualizar("1", -25, pre_jogo=True)
        self.voz.falar.assert_called_once_with("Runa de bounty")

    def test_aviso_buyback_nao_depende_de_frame_exato(self) -> None:
        self.atualizar("1", 600)
        self.assistente.registrar_buyback(0)
        self.assistente.atualizar_buybacks(1051, 0)
        self.assistente.atualizar_buybacks(1052, 0)
        self.voz.falar.assert_called_once_with("Buyback da Esquerda voltando em 30 segundos")

    def test_configuracao_retornada_nao_permite_mutacao_compartilhada(self) -> None:
        configuracao = self.assistente.obter_configuracao()
        configuracao["voz"].clear()
        self.assertTrue(self.assistente.obter_configuracao()["voz"])

    def test_buyback_nao_usado_fica_pronto_no_pre_jogo(self) -> None:
        self.atualizar("1", -60, pre_jogo=True)
        self.assertEqual(self.assistente.atualizar_buybacks(-60, 0), (0,) * 5)

    def test_posts_apos_encerramento_nao_alteram_estado_nem_voz(self) -> None:
        self.assistente.encerrar()
        self.assistente.encerrar()
        self.atualizar("1", 100)
        self.assertFalse(self.estado.snapshot()["conectado"])
        self.voz.falar.assert_not_called()
        self.voz.encerrar.assert_called_once()

    def test_cinco_funcoes_preservam_seus_avisos(self) -> None:
        for funcao, esperados in (
            (Funcao.CARREGADOR, {"bounty", "catapulta"}),
            (Funcao.MEIO, {"agua", "bounty", "lotus", "sabedoria"}),
            (Funcao.ROTA_DIFICIL, {"bounty", "lotus", "sabedoria", "catapulta"}),
            (Funcao.SUPORTE, {"stack", "pull", "agua", "bounty", "lotus", "sabedoria", "tormentor"}),
            (
                Funcao.SUPORTE_PRINCIPAL,
                {"stack", "pull", "agua", "bounty", "lotus", "sabedoria", "tormentor"},
            ),
        ):
            with self.subTest(funcao=funcao):
                self.assistente.selecionar_funcao(funcao)
                configuracao = self.assistente.obter_configuracao()
                self.assertEqual(configuracao["modo"], funcao.value)
                self.assertEqual(
                    {chave for chave, ativo in configuracao["voz"].items() if ativo}, esperados,
                )

    def test_sem_sinal_nao_muta_estado_armazenado(self) -> None:
        self.atualizar("1", 600)
        self.estado._relogio = lambda: 200
        self.assertFalse(self.estado.snapshot()["em_partida"])
        self.estado._relogio = lambda: 100
        self.assertTrue(self.estado.snapshot()["em_partida"])
