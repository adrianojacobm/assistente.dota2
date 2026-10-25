import runpy
import sys
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import ModuleType
from unittest import TestCase
from unittest.mock import Mock, patch

from assistente import composicao


class TestarCicloDeVida(TestCase):
    def setUp(self) -> None:
        for nome in (
            "identificar_sistema", "criar_saida_voz", "criar_plataforma_janelas",
            "criar_iniciador_dota", "ExecutorInicializacao",
            "criar_integracao_gsi", "ExecutorConfiguracaoGSI",
        ):
            remendo = patch.object(composicao, nome)
            setattr(self, nome, remendo.start())
            self.addCleanup(remendo.stop)

    def test_script_app_delega_execucao_e_preserva_codigo_de_saida(self) -> None:
        with (
            patch.object(composicao, "executar", return_value=7) as executar,
            patch("logging.basicConfig"),
            self.assertRaises(SystemExit) as saida,
        ):
            runpy.run_path(str(Path(__file__).resolve().parents[1] / "app.py"), run_name="__main__")
        executar.assert_called_once_with()
        self.assertEqual(saida.exception.code, 7)

    def test_plataforma_nao_suportada_nao_cria_janelas_nem_trabalhadores(self) -> None:
        saida = StringIO()
        self.identificar_sistema.side_effect = composicao.SistemaNaoSuportado("Sistema não suportado.")
        with (
            redirect_stderr(saida),
        ):
            self.assertEqual(composicao.executar(), 1)
        self.criar_saida_voz.assert_not_called()
        self.criar_plataforma_janelas.assert_not_called()
        self.criar_integracao_gsi.assert_not_called()
        self.ExecutorConfiguracaoGSI.assert_not_called()
        self.assertIn("não suportado", saida.getvalue())

    def test_tk_indisponivel_informa_erro_sem_iniciar_servicos(self) -> None:
        saida = StringIO()
        with (
            patch.dict(sys.modules, {"tkinter": None}),
            redirect_stderr(saida),
        ):
            self.assertEqual(composicao.executar(), 1)
        self.criar_saida_voz.assert_not_called()
        self.assertIn("Tkinter indisponível", saida.getvalue())

    def test_saida_da_interface_encerra_consultas_servidor_e_voz(self) -> None:
        tk = ModuleType("tkinter")
        tk.Tk = Mock()
        tk.TclError = type("TclError", (Exception,), {})
        with (
            patch.dict(sys.modules, {"tkinter": tk}),
            patch.object(composicao, "ServidorGSI") as servidor,
            patch.object(composicao, "criar_painel") as painel,
        ):
            self.assertEqual(composicao.executar(), 0)
        servidor.return_value.iniciar.assert_called_once()
        servidor.return_value.encerrar.assert_called_once()
        painel.return_value.encerrar.assert_called_once()
        self.ExecutorInicializacao.return_value.encerrar.assert_called_once()
        self.ExecutorConfiguracaoGSI.return_value.encerrar.assert_called_once()
        self.criar_saida_voz.return_value.encerrar.assert_called_once()
        self.criar_plataforma_janelas.return_value.encerrar.assert_called_once()
        tk.Tk.return_value.destroy.assert_called_once()

    def test_porta_ocupada_libera_recursos_ja_criados(self) -> None:
        tk = ModuleType("tkinter")
        tk.Tk = Mock()
        tk.TclError = type("TclError", (Exception,), {})
        with (
            patch.dict(sys.modules, {"tkinter": tk}),
            patch.object(composicao, "ServidorGSI", side_effect=OSError("Porta ocupada")),
            patch.object(composicao, "criar_painel") as painel,
            self.assertLogs("assistente.composicao", "ERROR"),
        ):
            self.assertEqual(composicao.executar(), 1)
        painel.assert_not_called()
        self.criar_saida_voz.return_value.encerrar.assert_called_once()
        self.ExecutorInicializacao.return_value.encerrar.assert_called_once()
        self.ExecutorConfiguracaoGSI.assert_not_called()
        self.criar_integracao_gsi.assert_not_called()
        self.criar_plataforma_janelas.return_value.encerrar.assert_called_once()
        tk.Tk.return_value.destroy.assert_called_once()

    def test_falha_no_painel_libera_todos_os_recursos(self) -> None:
        tk = ModuleType("tkinter")
        tk.Tk = Mock()
        tk.TclError = type("TclError", (Exception,), {})
        with (
            patch.dict(sys.modules, {"tkinter": tk}),
            patch.object(composicao, "ServidorGSI") as servidor,
            patch.object(composicao, "criar_painel", side_effect=RuntimeError("painel inválido")),
            self.assertLogs("assistente.composicao", "ERROR"),
        ):
            self.assertEqual(composicao.executar(), 1)
        servidor.return_value.encerrar.assert_called_once()
        self.criar_saida_voz.return_value.encerrar.assert_called_once()
        self.ExecutorInicializacao.return_value.encerrar.assert_called_once()
        self.ExecutorConfiguracaoGSI.return_value.encerrar.assert_called_once()
        self.criar_plataforma_janelas.return_value.encerrar.assert_called_once()
        tk.Tk.return_value.destroy.assert_called_once()

    def test_configuracao_gsi_usa_a_porta_efetiva_do_servidor(self) -> None:
        tk = ModuleType("tkinter")
        tk.Tk = Mock()
        tk.TclError = type("TclError", (Exception,), {})
        with (
            patch.dict(sys.modules, {"tkinter": tk}),
            patch.object(composicao, "ServidorGSI") as servidor,
            patch.object(composicao, "criar_painel"),
        ):
            servidor.return_value.server_port = 45231
            self.assertEqual(composicao.executar(), 0)
        self.criar_integracao_gsi.assert_called_once_with(45231)
