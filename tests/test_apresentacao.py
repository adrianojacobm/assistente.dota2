import importlib
import sys
from types import ModuleType
from unittest import TestCase
from unittest.mock import Mock, patch

from assistente.aplicacao.consultar_recomendacoes import ConsultaRecomendacoes, ResultadoConsulta
from assistente.apresentacao.formatacao import dados_build, formatar_painel, rotulo_referencia
from assistente.dominio.modelos import BuildObservada, Funcao, ItemQuantidade
from assistente.dominio.recomendacoes import montar_build


class TestarFormatacao(TestCase):
    def test_erro_nao_e_armazenado_como_item(self) -> None:
        dados = dados_build("Sven", Funcao.CARREGADOR, None, "HTTP 403")
        for fase in ("start", "early", "mid", "late"):
            self.assertEqual(dados[fase], "")
        self.assertIn("403", dados["observacao"])

    def test_painel_usa_limites_reais_da_build(self) -> None:
        texto = formatar_painel(ResultadoConsulta(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR)))
        self.assertIn("Early (<12m)", texto)
        self.assertIn("Mid (12–30m)", texto)
        self.assertIn("Late (30m+)", texto)

    def test_estimativa_nao_e_rotulada_como_percentil(self) -> None:
        self.assertEqual(rotulo_referencia(None, ("gpm",)), "Estimativa")
        self.assertEqual(rotulo_referencia({"gpm": float("inf")}, ("gpm",)), "Estimativa")
        self.assertEqual(rotulo_referencia({"gpm": 500, "percentil": 0.8}, ("gpm",)), "P80")
        self.assertEqual(rotulo_referencia({"gpm": 500}, ("gpm", "xpm")), "Estimativa")


class TestarControladoresSemGUI(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Estes testes não validam widgets ou Win32: somente a coordenação da GUI.
        tk_simulado = ModuleType("tkinter")
        tk_simulado.ttk = ModuleType("tkinter.ttk")
        tk_simulado.TclError = type("TclError", (Exception,), {})
        with patch.dict(sys.modules, {"tkinter": tk_simulado, "tkinter.ttk": tk_simulado.ttk}):
            cls.painel_tipo = importlib.import_module("assistente.apresentacao.painel").PainelPrincipal
            cls.build_tipo = importlib.import_module(
                "assistente.apresentacao.sobreposicoes"
            ).SobreposicaoBuild

    def setUp(self) -> None:
        self.painel = self.painel_tipo.__new__(self.painel_tipo)
        self.painel._fechado = False
        self.painel._identificador_consulta = 1
        self.painel._resultado_atual = Mock(benchmark={"gpm": 999})
        self.painel.sobreposicoes = {
            chave: Mock() for chave in ("build", "timers", "stats", "bb_esquerda", "bb_direita")
        }
        self.painel.build = self.painel.sobreposicoes["build"]
        self.painel.consultas = Mock()
        self.painel.consultas.solicitar.return_value = 2
        self.painel._escrever = Mock()
        self.painel._agendar = Mock()

    def test_nova_consulta_limpa_build_e_benchmark_anteriores(self) -> None:
        self.painel.selecoes = {
            chave: Mock(get=Mock(return_value=valor))
            for chave, valor in (
                ("heroi", "Sven"), ("lane1", "Nenhum"), ("lane2", "Nenhum"), ("ameaca", "Phantom Assassin"),
            )
        }
        self.painel.cb_funcao = Mock(get=Mock(return_value="Offlane"))
        self.painel._funcoes_por_rotulo = {"Offlane": Funcao.ROTA_DIFICIL}
        self.painel._consultar()
        self.assertIsNone(self.painel._resultado_atual)
        resultado = self.painel.sobreposicoes["build"].atualizar.call_args.args[0]
        self.assertIsNone(resultado.build)
        self.assertEqual(resultado.consulta.funcao, Funcao.ROTA_DIFICIL)

    def test_resultado_antigo_nao_chega_aos_widgets(self) -> None:
        resultado = ResultadoConsulta(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR))
        self.painel.consultas.obter_resultados.return_value = [(0, resultado)]
        self.painel._receber_resultados()
        self.painel.sobreposicoes["build"].atualizar.assert_not_called()

    def test_resultado_recente_e_aplicado_na_thread_da_interface(self) -> None:
        resultado = ResultadoConsulta(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR), erro_build="HTTP 403")
        self.painel.consultas.obter_resultados.return_value = [(1, resultado)]
        self.painel._receber_resultados()
        self.assertIs(self.painel._resultado_atual, resultado)
        self.painel.sobreposicoes["build"].atualizar.assert_called_once_with(resultado)

    def test_sobreposicao_falha_mostra_tracos_nao_mensagem_como_item(self) -> None:
        sobreposicao = self.build_tipo.__new__(self.build_tipo)
        sobreposicao.titulo, sobreposicao.texto = Mock(), Mock()
        resultado = ResultadoConsulta(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR), erro_build="HTTP 403")
        sobreposicao.atualizar(resultado)
        texto = sobreposicao.texto.configure.call_args.kwargs["text"]
        self.assertNotIn("403", texto)
        self.assertIn("SAÍDA: —", texto)

    def test_fechamento_cancela_callbacks_e_encerra_recursos(self) -> None:
        self.painel._agendamentos = {"1", "2"}
        self.painel._salvar_preferencias = Mock()
        self.painel.assistente, self.painel.janela = Mock(), Mock()
        self.painel._ao_fechar()
        self.assertEqual(self.painel.janela.after_cancel.call_count, 2)
        self.painel.consultas.encerrar.assert_called_once()
        self.painel.assistente.encerrar.assert_called_once()
        self.assertTrue(self.painel._fechado)

    def test_sobreposicao_preserva_quantidades_da_build_estruturada(self) -> None:
        build = montar_build(
            "Sven", Funcao.CARREGADOR,
            (BuildObservada("exemplo", 10, (("Tango", "Iron Branch", "Iron Branch"),)),),
            {"Tango": 90, "Iron Branch": 50},
        )
        self.assertEqual(build.saida, (ItemQuantidade("Tango", 1), ItemQuantidade("Iron Branch", 2)))
        sobreposicao = self.build_tipo.__new__(self.build_tipo)
        sobreposicao.titulo, sobreposicao.texto = Mock(), Mock()
        resultado = ResultadoConsulta(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR), build=build)
        sobreposicao.atualizar(resultado)
        self.assertIn("SAÍDA: Tango, Iron Branch ×2", sobreposicao.texto.configure.call_args.kwargs["text"])
