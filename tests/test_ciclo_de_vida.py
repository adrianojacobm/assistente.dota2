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
        with (
            patch.object(composicao, "recursos_nativos_disponiveis", return_value=False),
            patch.object(composicao, "Voz") as voz,
            redirect_stderr(saida),
        ):
            self.assertEqual(composicao.executar(), 1)
        voz.assert_not_called()
        self.assertIn("requer Windows", saida.getvalue())

    def test_tk_indisponivel_informa_erro_sem_iniciar_servicos(self) -> None:
        saida = StringIO()
        with (
            patch.object(composicao, "recursos_nativos_disponiveis", return_value=True),
            patch.dict(sys.modules, {"tkinter": None}),
            patch.object(composicao, "Voz") as voz,
            redirect_stderr(saida),
        ):
            self.assertEqual(composicao.executar(), 1)
        voz.assert_not_called()
        self.assertIn("Tkinter indisponível", saida.getvalue())

    def test_saida_da_interface_encerra_consultas_servidor_e_voz(self) -> None:
        tk = ModuleType("tkinter")
        tk.Tk = Mock()
        tk.TclError = type("TclError", (Exception,), {})
        with (
            patch.object(composicao, "recursos_nativos_disponiveis", return_value=True),
            patch.dict(sys.modules, {"tkinter": tk}),
            patch.object(composicao, "Voz") as voz,
            patch.object(composicao, "ServidorGSI") as servidor,
            patch.object(composicao, "criar_painel") as painel,
        ):
            self.assertEqual(composicao.executar(), 0)
        servidor.return_value.iniciar.assert_called_once()
        servidor.return_value.encerrar.assert_called_once()
        painel.return_value.consultas.encerrar.assert_called_once()
        voz.return_value.encerrar.assert_called_once()
        tk.Tk.return_value.destroy.assert_called_once()

    def test_porta_ocupada_libera_recursos_ja_criados(self) -> None:
        tk = ModuleType("tkinter")
        tk.Tk = Mock()
        tk.TclError = type("TclError", (Exception,), {})
        with (
            patch.object(composicao, "recursos_nativos_disponiveis", return_value=True),
            patch.dict(sys.modules, {"tkinter": tk}),
            patch.object(composicao, "Voz") as voz,
            patch.object(composicao, "ServidorGSI", side_effect=OSError("Porta ocupada")),
            patch.object(composicao, "criar_painel") as painel,
            self.assertLogs("assistente.composicao", "ERROR"),
        ):
            self.assertEqual(composicao.executar(), 1)
        painel.assert_not_called()
        voz.return_value.encerrar.assert_called_once()
        tk.Tk.return_value.destroy.assert_called_once()
