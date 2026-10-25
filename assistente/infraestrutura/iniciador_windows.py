import ctypes
import logging
import ntpath
import shutil
from pathlib import Path

from assistente.aplicacao.contratos import ErroInicializacao

from .iniciador_steam import ErroInspecaoProcesso, IniciadorSteam
from .steam import InstalacaoDota, localizar_instalacao

REGISTRO = logging.getLogger(__name__)


def raizes_steam_windows() -> tuple[tuple[Path, tuple[str, ...]], ...]:
    import winreg

    raizes: list[tuple[Path, tuple[str, ...]]] = []
    for origem in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for visao in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(origem, r"Software\Valve\Steam", 0, winreg.KEY_READ | visao) as chave:
                    valores: dict[str, str] = {}
                    for nome in ("SteamPath", "InstallPath", "SteamExe"):
                        try:
                            valor, _ = winreg.QueryValueEx(chave, nome)
                            if isinstance(valor, str) and valor and "\x00" not in valor:
                                valores[nome] = valor
                        except FileNotFoundError:
                            continue
                    diretorio = valores.get("SteamPath") or valores.get("InstallPath")
                    executavel = valores.get("SteamExe")
                    if diretorio or executavel:
                        raiz = Path(diretorio) if diretorio else Path(executavel or "").parent
                        caminho = Path(executavel) if executavel else raiz / "steam.exe"
                        raizes.append((raiz, (str(caminho),)))
            except OSError as erro:
                REGISTRO.debug("Entrada Steam do Registro indisponível: %s", erro)
    encontrado = shutil.which("steam.exe")
    if encontrado:
        raizes.append((Path(encontrado).parent, (encontrado,)))
    if not raizes:
        raise ErroInicializacao("Cliente Steam não encontrado no Registro nem no PATH do Windows.")
    return tuple(dict.fromkeys(raizes))


def localizar_dota_windows() -> InstalacaoDota:
    return localizar_instalacao(raizes_steam_windows(), ("game/bin/win64/dota2.exe",))


class EntradaProcessoWindows(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_uint32), ("cntUsage", ctypes.c_uint32),
        ("th32ProcessID", ctypes.c_uint32), ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", ctypes.c_uint32), ("cntThreads", ctypes.c_uint32),
        ("th32ParentProcessID", ctypes.c_uint32), ("pcPriClassBase", ctypes.c_int32),
        ("dwFlags", ctypes.c_uint32), ("szExeFile", ctypes.c_wchar * 260),
    ]


def _carregar_api() -> ctypes.CDLL:
    biblioteca = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    biblioteca.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    biblioteca.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    for nome in ("Process32FirstW", "Process32NextW"):
        funcao = getattr(biblioteca, nome)
        funcao.argtypes = [ctypes.c_void_p, ctypes.POINTER(EntradaProcessoWindows)]
        funcao.restype = ctypes.c_int
    biblioteca.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    biblioteca.OpenProcess.restype = ctypes.c_void_p
    biblioteca.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32),
    ]
    biblioteca.QueryFullProcessImageNameW.restype = ctypes.c_int
    biblioteca.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    biblioteca.GetExitCodeProcess.restype = ctypes.c_int
    biblioteca.CloseHandle.argtypes = [ctypes.c_void_p]
    biblioteca.CloseHandle.restype = ctypes.c_int
    return biblioteca


def procurar_pid_windows(executavel: Path) -> int | None:
    try:
        biblioteca = _carregar_api()
    except (OSError, AttributeError) as erro:
        raise ErroInspecaoProcesso(f"API de processos Windows indisponível: {erro}") from erro
    captura = biblioteca.CreateToolhelp32Snapshot(2, 0)
    if not captura or captura == ctypes.c_void_p(-1).value:
        raise ErroInspecaoProcesso("Não foi possível listar os processos Windows.")
    entrada = EntradaProcessoWindows()
    entrada.dwSize = ctypes.sizeof(entrada)
    esperado = ntpath.normcase(str(executavel.resolve()))
    acesso_negado = False
    try:
        tem_processo = biblioteca.Process32FirstW(captura, ctypes.byref(entrada))
        while tem_processo:
            if entrada.szExeFile.lower() == executavel.name.lower():
                processo = biblioteca.OpenProcess(0x1000, False, entrada.th32ProcessID)
                if processo:
                    try:
                        tamanho = ctypes.c_uint32(32768)
                        caminho = ctypes.create_unicode_buffer(tamanho.value)
                        if biblioteca.QueryFullProcessImageNameW(processo, 0, caminho, ctypes.byref(tamanho)):
                            if ntpath.normcase(ntpath.normpath(caminho.value)) == esperado:
                                codigo_saida = ctypes.c_uint32()
                                if biblioteca.GetExitCodeProcess(processo, ctypes.byref(codigo_saida)):
                                    if codigo_saida.value == 259:  # STILL_ACTIVE
                                        return int(entrada.th32ProcessID)
                                else:
                                    acesso_negado = True
                        else:
                            acesso_negado = True
                    finally:
                        biblioteca.CloseHandle(processo)
                else:
                    acesso_negado = True
            tem_processo = biblioteca.Process32NextW(captura, ctypes.byref(entrada))
        codigo = getattr(ctypes, "get_last_error")()
        if codigo != 18:  # ERROR_NO_MORE_FILES
            raise ErroInspecaoProcesso(f"Consulta de processos Windows interrompida (erro {codigo}).")
        if acesso_negado:
            raise ErroInspecaoProcesso("Sem permissão para identificar um processo chamado dota2.exe.")
    finally:
        biblioteca.CloseHandle(captura)
    return None


def criar_iniciador_windows() -> IniciadorSteam:
    return IniciadorSteam(localizar_dota_windows, procurar_pid_windows)
