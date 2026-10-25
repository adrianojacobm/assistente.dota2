import sys
import threading
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from assistente.infraestrutura import plataforma_windows, voz_windows


class TestarRecursosWindowsSimulados(TestCase):
    def test_clique_transparente_preserva_estilo_e_pode_ser_desativado(self) -> None:
        usuario = Mock()
        usuario.GetWindowLongW.return_value = 0x100
        biblioteca = SimpleNamespace(user32=usuario)
        with (
            patch.object(plataforma_windows, "recursos_nativos_disponiveis", return_value=True),
            patch.object(plataforma_windows.ctypes, "windll", biblioteca, create=True),
        ):
            plataforma_windows.aplicar_clique_transparente(123, True)
            estilo_ativo = usuario.SetWindowLongW.call_args.args[2]
            self.assertTrue(estilo_ativo & 0x100)
            self.assertTrue(estilo_ativo & 0x20)
            usuario.GetWindowLongW.return_value = estilo_ativo
            plataforma_windows.aplicar_clique_transparente(123, False)
            self.assertFalse(usuario.SetWindowLongW.call_args.args[2] & 0x20)

    def test_sem_windows_nao_acessa_bibliotecas_nativas(self) -> None:
        with patch.object(plataforma_windows, "recursos_nativos_disponiveis", return_value=False):
            self.assertEqual(plataforma_windows.obter_identificador_janela(123), 123)
            self.assertFalse(plataforma_windows.dota_ou_painel_em_foco())
            plataforma_windows.aplicar_clique_transparente(123, True)

    def test_voz_inicializa_e_libera_com_na_mesma_thread(self) -> None:
        falou = threading.Event()
        threads_com = []
        locutor = Mock()
        locutor.GetVoices.return_value = []
        locutor.Speak.side_effect = lambda *args: falou.set()
        locutor.WaitUntilDone.return_value = True
        com = ModuleType("pythoncom")
        com.CoInitialize = lambda: threads_com.append(threading.get_ident())
        com.CoUninitialize = lambda: threads_com.append(threading.get_ident())
        pacote = ModuleType("win32com")
        cliente = ModuleType("win32com.client")
        cliente.Dispatch = Mock(return_value=locutor)
        pacote.client = cliente
        with (
            patch.dict(sys.modules, {"pythoncom": com, "win32com": pacote, "win32com.client": cliente}),
            patch.object(voz_windows.sys, "platform", "win32"),
        ):
            voz = voz_windows.Voz()
            try:
                voz.falar("Hora do stack")
                self.assertTrue(falou.wait(timeout=2))
            finally:
                voz.encerrar()
        self.assertFalse(voz._trabalhador.is_alive())
        self.assertEqual(len(threads_com), 2)
        self.assertEqual(threads_com[0], threads_com[1])
        self.assertNotEqual(threads_com[0], threading.get_ident())
        locutor.Speak.assert_called_once_with("Hora do stack", 1)
        voz.falar("Não deve falar")
        locutor.Speak.assert_called_once()
