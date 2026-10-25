import ctypes
import logging
import sys

REGISTRO = logging.getLogger(__name__)


def recursos_nativos_disponiveis() -> bool:
    return sys.platform == "win32"


def obter_identificador_janela(identificador_tk: int) -> int:
    if not recursos_nativos_disponiveis():
        return identificador_tk
    obter_pai = ctypes.windll.user32.GetParent
    obter_pai.argtypes = [ctypes.c_void_p]
    obter_pai.restype = ctypes.c_void_p
    return obter_pai(identificador_tk) or identificador_tk


def aplicar_clique_transparente(identificador: int, ativar: bool) -> None:
    if not recursos_nativos_disponiveis():
        return
    try:
        usuario = ctypes.windll.user32
        usuario.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        usuario.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        estilo = usuario.GetWindowLongW(identificador, -20) | 0x00080000 | 0x08000000
        estilo = estilo | 0x00000020 if ativar else estilo & ~0x00000020
        usuario.SetWindowLongW(identificador, -20, estilo)
    except OSError:
        REGISTRO.exception("Falha ao ajustar a interação da sobreposição.")


def dota_ou_painel_em_foco() -> bool:
    if not recursos_nativos_disponiveis():
        return False
    try:
        usuario = ctypes.windll.user32
        usuario.GetForegroundWindow.restype = ctypes.c_void_p
        identificador = usuario.GetForegroundWindow()
        if not identificador:
            return False
        usuario.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        tamanho = usuario.GetWindowTextLengthW(identificador)
        texto = ctypes.create_unicode_buffer(tamanho + 1)
        usuario.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        usuario.GetWindowTextW(identificador, texto, tamanho + 1)
        titulo = texto.value.lower()
        return any(nome in titulo for nome in ("dota 2", "assistente", "python"))
    except OSError:
        REGISTRO.exception("Falha ao consultar a janela em foco.")
        return False


class PlataformaWindows:
    avisos: tuple[str, ...] = ()

    def identificar(self, identificador_tk: int) -> int:
        return obter_identificador_janela(identificador_tk)

    def aplicar_transparencia(self, identificador: int, ativar: bool) -> None:
        aplicar_clique_transparente(identificador, ativar)

    def em_foco(self) -> bool:
        return dota_ou_painel_em_foco()

    def encerrar(self) -> None:
        """Win32 não mantém uma conexão de janelas aberta pelo adaptador."""
