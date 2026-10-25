"""Integração X11/XWayland, chamada somente pela thread da interface."""

import ctypes
import ctypes.util
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

REGISTRO = logging.getLogger(__name__)


class ErroX11(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int), ("display", ctypes.c_void_p),
        ("resourceid", ctypes.c_ulong), ("serial", ctypes.c_ulong),
        ("error_code", ctypes.c_ubyte), ("request_code", ctypes.c_ubyte), ("minor_code", ctypes.c_ubyte),
    ]


TratadorErroX11 = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ErroX11))


def _configurar_x11(biblioteca: ctypes.CDLL) -> None:
    assinaturas = {
        "XOpenDisplay": ([ctypes.c_char_p], ctypes.c_void_p),
        "XCloseDisplay": ([ctypes.c_void_p], ctypes.c_int),
        "XDefaultRootWindow": ([ctypes.c_void_p], ctypes.c_ulong),
        "XInternAtom": ([ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int], ctypes.c_ulong),
        "XFree": ([ctypes.c_void_p], ctypes.c_int),
        "XSync": ([ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
        "XSetErrorHandler": ([ctypes.c_void_p], ctypes.c_void_p),
        "XQueryTree": ([
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
            ctypes.POINTER(ctypes.c_uint),
        ], ctypes.c_int),
        "XGetWindowProperty": ([
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
            ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
        ], ctypes.c_int),
    }
    for nome, (argumentos, retorno) in assinaturas.items():
        funcao = getattr(biblioteca, nome)
        funcao.argtypes, funcao.restype = argumentos, retorno


class PlataformaLinux:
    def __init__(self) -> None:
        self._x11: ctypes.CDLL | None = None
        self._xfixes: ctypes.CDLL | None = None
        self._conexao: int | None = None
        self._raiz = 0
        self.foco_disponivel = False
        self.clique_transparente_disponivel = False
        avisos: list[str] = []
        try:
            nome = ctypes.util.find_library("X11")
            if not nome:
                raise OSError("Biblioteca X11 não encontrada.")
            self._x11 = ctypes.CDLL(nome)
            _configurar_x11(self._x11)
            self._conexao = self._x11.XOpenDisplay(None)
            if not self._conexao:
                self._conexao = None
                raise OSError("Display X11 indisponível.")
            self._raiz = self._x11.XDefaultRootWindow(self._conexao)
            self.foco_disponivel = bool(self._x11.XInternAtom(self._conexao, b"_NET_ACTIVE_WINDOW", True))
            self._configurar_regiao_entrada()
        except (OSError, AttributeError) as erro:
            REGISTRO.warning("Integração X11 limitada: %s", erro)
            avisos.append(str(erro))
        if not self.foco_disponivel:
            avisos.append("Foco automático indisponível. Destrave os overlays para exibição manual.")
        if not self.clique_transparente_disponivel:
            avisos.append("Clique transparente indisponível; overlays podem interceptar cliques.")
        if os.environ.get("WAYLAND_DISPLAY"):
            avisos.append("Wayland: foco e overlays limitados a X11/XWayland e ao suporte do compositor.")
        self.avisos = tuple(avisos)

    def _configurar_regiao_entrada(self) -> None:
        nome = ctypes.util.find_library("Xfixes")
        if not nome:
            return
        self._xfixes = ctypes.CDLL(nome)
        assinaturas = {
            "XFixesQueryVersion": ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                                   ctypes.POINTER(ctypes.c_int)], ctypes.c_int),
            "XFixesCreateRegion": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int], ctypes.c_ulong),
            "XFixesSetWindowShapeRegion": ([ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_ulong], None),
            "XFixesDestroyRegion": ([ctypes.c_void_p, ctypes.c_ulong], None),
        }
        for nome_funcao, (argumentos, retorno) in assinaturas.items():
            funcao = getattr(self._xfixes, nome_funcao)
            funcao.argtypes, funcao.restype = argumentos, retorno
        maior, menor = ctypes.c_int(2), ctypes.c_int(0)
        self.clique_transparente_disponivel = bool(
            self._xfixes.XFixesQueryVersion(self._conexao, ctypes.byref(maior), ctypes.byref(menor))
            and maior.value >= 2
        )

    @contextmanager
    def _proteger(self) -> Iterator[list[int]]:
        assert self._x11 is not None and self._conexao is not None
        erros: list[int] = []

        def registrar(conexao: int, erro: ctypes.c_void_p) -> int:
            dados = ctypes.cast(erro, ctypes.POINTER(ErroX11)).contents
            erros.append(dados.error_code)
            return 0

        tratador = TratadorErroX11(registrar)
        anterior = self._x11.XSetErrorHandler(ctypes.cast(tratador, ctypes.c_void_p))
        try:
            yield erros
        finally:
            # Janelas em foco podem desaparecer entre a consulta e a leitura.
            self._x11.XSync(self._conexao, False)
            self._x11.XSetErrorHandler(anterior)
            if erros:
                REGISTRO.debug("Requisição X11 não concluída: %s", erros)

    def identificar(self, identificador_tk: int) -> int:
        if self._x11 is None or self._conexao is None:
            return identificador_tk
        identificador = identificador_tk
        with self._proteger():
            for _ in range(8):
                raiz, pai = ctypes.c_ulong(), ctypes.c_ulong()
                filhos = ctypes.POINTER(ctypes.c_ulong)()
                quantidade = ctypes.c_uint()
                sucesso = self._x11.XQueryTree(
                    self._conexao, identificador, ctypes.byref(raiz), ctypes.byref(pai),
                    ctypes.byref(filhos), ctypes.byref(quantidade),
                )
                if filhos:
                    self._x11.XFree(filhos)
                if not sucesso or not pai.value or pai.value == raiz.value:
                    break
                identificador = pai.value
        return identificador

    def aplicar_transparencia(self, identificador: int, ativar: bool) -> None:
        if not self.clique_transparente_disponivel or self._xfixes is None or self._conexao is None:
            return
        with self._proteger():
            regiao = self._xfixes.XFixesCreateRegion(self._conexao, None, 0) if ativar else 0
            try:
                self._xfixes.XFixesSetWindowShapeRegion(self._conexao, identificador, 2, 0, 0, regiao)
            finally:
                if regiao:
                    self._xfixes.XFixesDestroyRegion(self._conexao, regiao)

    def _propriedade(self, janela: int, nome: bytes) -> bytes | tuple[int, ...] | None:
        assert self._x11 is not None
        atomo = self._x11.XInternAtom(self._conexao, nome, True)
        if not atomo:
            return None
        tipo, quantidade, restante = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_ulong()
        formato = ctypes.c_int()
        dados = ctypes.POINTER(ctypes.c_ubyte)()
        try:
            codigo = self._x11.XGetWindowProperty(
                self._conexao, janela, atomo, 0, 1024, False, 0, ctypes.byref(tipo),
                ctypes.byref(formato), ctypes.byref(quantidade), ctypes.byref(restante), ctypes.byref(dados),
            )
            if codigo != 0 or not dados:
                return None
            if formato.value == 8:
                return ctypes.string_at(dados, quantidade.value)
            if formato.value == 32:
                numeros = ctypes.cast(dados, ctypes.POINTER(ctypes.c_ulong))
                return tuple(numeros[indice] for indice in range(quantidade.value))
        finally:
            if dados:
                self._x11.XFree(dados)
        return None

    def em_foco(self) -> bool:
        if not self.foco_disponivel or self._conexao is None:
            return False
        em_foco = False
        with self._proteger() as erros:
            ativa = self._propriedade(self._raiz, b"_NET_ACTIVE_WINDOW")
            if isinstance(ativa, tuple) and ativa and ativa[0]:
                pid = self._propriedade(ativa[0], b"_NET_WM_PID")
                if isinstance(pid, tuple) and pid == (os.getpid(),):
                    em_foco = True
                else:
                    titulo = self._propriedade(ativa[0], b"_NET_WM_NAME")
                    if not isinstance(titulo, bytes):
                        titulo = self._propriedade(ativa[0], b"WM_NAME")
                    em_foco = (
                        isinstance(titulo, bytes) and "dota 2" in titulo.decode("utf-8", "replace").lower()
                    )
        return em_foco and not erros

    def encerrar(self) -> None:
        if self._conexao is not None and self._x11 is not None:
            self._x11.XCloseDisplay(self._conexao)
            self._conexao = None
