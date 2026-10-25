import ctypes
import os
import subprocess
import threading
from unittest import TestCase
from unittest.mock import Mock, patch

from assistente.infraestrutura import plataforma_linux, voz_linux


class TestarJanelasLinux(TestCase):
    def setUp(self) -> None:
        self.plataforma = plataforma_linux.PlataformaLinux.__new__(plataforma_linux.PlataformaLinux)
        self.plataforma._x11 = Mock()
        self.plataforma._xfixes = Mock()
        self.plataforma._conexao = 1
        self.plataforma._raiz = 2
        self.plataforma.foco_disponivel = True
        self.plataforma.clique_transparente_disponivel = True

    def test_sem_x11_informa_limitacoes_sem_acessar_biblioteca(self) -> None:
        with (
            patch.object(plataforma_linux.ctypes.util, "find_library", return_value=None),
            self.assertLogs("assistente.infraestrutura.plataforma_linux", "WARNING"),
        ):
            plataforma = plataforma_linux.PlataformaLinux()
        self.assertFalse(plataforma.foco_disponivel)
        self.assertFalse(plataforma.clique_transparente_disponivel)
        self.assertTrue(any("Destrave" in aviso for aviso in plataforma.avisos))
        self.assertFalse(plataforma.em_foco())
        plataforma.encerrar()

    def test_display_ausente_nao_tenta_fechar_ponteiro_nulo(self) -> None:
        biblioteca = Mock()
        biblioteca.XOpenDisplay.return_value = None
        with (
            patch.object(plataforma_linux.ctypes.util, "find_library", return_value="libX11.so"),
            patch.object(plataforma_linux.ctypes, "CDLL", return_value=biblioteca),
            self.assertLogs("assistente.infraestrutura.plataforma_linux", "WARNING"),
        ):
            plataforma = plataforma_linux.PlataformaLinux()
        plataforma.encerrar()
        biblioteca.XCloseDisplay.assert_not_called()

    def test_propriedade_x11_libera_memoria_alocada(self) -> None:
        biblioteca = self.plataforma._x11
        biblioteca.XInternAtom.return_value = 3
        texto = ctypes.create_string_buffer(b"Dota 2")

        def consultar(*argumentos: object) -> int:
            ctypes.cast(argumentos[8], ctypes.POINTER(ctypes.c_int)).contents.value = 8
            ctypes.cast(argumentos[9], ctypes.POINTER(ctypes.c_ulong)).contents.value = 6
            ponteiro = ctypes.cast(argumentos[11], ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)))
            ponteiro[0] = ctypes.cast(texto, ctypes.POINTER(ctypes.c_ubyte))
            return 0

        biblioteca.XGetWindowProperty.side_effect = consultar
        self.assertEqual(self.plataforma._propriedade(7, b"_NET_WM_NAME"), b"Dota 2")
        biblioteca.XFree.assert_called_once()

    def test_clique_transparente_define_e_restaura_regiao_de_entrada(self) -> None:
        biblioteca = self.plataforma._xfixes
        biblioteca.XFixesCreateRegion.return_value = 42
        self.plataforma.aplicar_transparencia(7, True)
        biblioteca.XFixesSetWindowShapeRegion.assert_called_with(1, 7, 2, 0, 0, 42)
        biblioteca.XFixesDestroyRegion.assert_called_once_with(1, 42)
        self.plataforma.aplicar_transparencia(7, False)
        biblioteca.XFixesSetWindowShapeRegion.assert_called_with(1, 7, 2, 0, 0, 0)

    def test_foco_reconhece_o_proprio_assistente(self) -> None:
        with patch.object(self.plataforma, "_propriedade", side_effect=[(7,), (os.getpid(),)]):
            self.assertTrue(self.plataforma.em_foco())

    def test_foco_reconhece_dota_mas_nao_outro_aplicativo(self) -> None:
        for titulo, esperado in ((b"Dota 2", True), (b"Editor", False)):
            with patch.object(self.plataforma, "_propriedade", side_effect=[(7,), (999999,), titulo]):
                self.assertEqual(self.plataforma.em_foco(), esperado)

    def test_conexao_e_fechada_apenas_uma_vez(self) -> None:
        biblioteca = self.plataforma._x11
        self.plataforma.encerrar()
        self.plataforma.encerrar()
        biblioteca.XCloseDisplay.assert_called_once_with(1)
        self.assertFalse(self.plataforma.em_foco())

    def test_identifica_janela_externa_do_tk_sem_subir_ate_a_raiz(self) -> None:
        def consultar(
            conexao: int, janela: int, raiz: object, pai: object, filhos: object, quantidade: object,
        ) -> int:
            ctypes.cast(raiz, ctypes.POINTER(ctypes.c_ulong)).contents.value = 2
            ctypes.cast(pai, ctypes.POINTER(ctypes.c_ulong)).contents.value = 7 if janela == 3 else 2
            return 1

        self.plataforma._x11.XQueryTree.side_effect = consultar
        self.assertEqual(self.plataforma.identificar(3), 7)


class TestarVozLinux(TestCase):
    def test_sem_espeak_nao_inicia_trabalhador(self) -> None:
        with (
            patch.object(voz_linux.shutil, "which", return_value=None),
            patch.object(voz_linux.threading.Thread, "start") as iniciar,
            self.assertLogs("assistente.infraestrutura.voz_linux", "WARNING"),
        ):
            voz = voz_linux.VozLinux()
        self.assertFalse(voz.disponivel)
        iniciar.assert_not_called()
        voz.encerrar()

    def test_texto_e_enviado_por_stdin_sem_shell(self) -> None:
        falou = threading.Event()
        processo = Mock(returncode=0)
        processo.poll.return_value = 0
        processo.communicate.side_effect = lambda *args, **kwargs: falou.set()
        with (
            patch.object(voz_linux.shutil, "which", return_value="/cliente/espeak-ng"),
            patch.object(voz_linux.subprocess, "Popen", return_value=processo) as popen,
        ):
            voz = voz_linux.VozLinux()
            try:
                voz.falar("Hora do stack; $(comando)")
                self.assertTrue(falou.wait(timeout=2))
            finally:
                voz.encerrar()
        self.assertEqual(popen.call_args.args[0], ["/cliente/espeak-ng", "-v", "pt-br", "--stdin"])
        self.assertFalse(popen.call_args.kwargs["shell"])
        self.assertEqual(processo.communicate.call_args.args[0], "Hora do stack; $(comando)")
        processo.terminate.assert_not_called()

    def test_fechamento_interrompe_apenas_sintetizador_proprio(self) -> None:
        iniciou = threading.Event()
        processo = Mock()
        ativo = True

        def comunicar(*args: object, **kwargs: object) -> None:
            iniciou.set()
            if ativo:
                raise subprocess.TimeoutExpired("espeak-ng", 0.1)

        def terminar() -> None:
            nonlocal ativo
            ativo = False

        processo.communicate.side_effect = comunicar
        processo.poll.side_effect = lambda: None if ativo else 0
        processo.terminate.side_effect = terminar
        with (
            patch.object(voz_linux.shutil, "which", return_value="/cliente/espeak-ng"),
            patch.object(voz_linux.subprocess, "Popen", return_value=processo),
        ):
            voz = voz_linux.VozLinux()
            voz.falar("Teste")
            self.assertTrue(iniciou.wait(timeout=2))
            voz.encerrar()
        processo.terminate.assert_called_once()
        self.assertFalse(voz._trabalhador.is_alive())
