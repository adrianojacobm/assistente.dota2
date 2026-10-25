"""Seleção das integrações sem carregar bibliotecas nativas na importação."""

import sys

from assistente.aplicacao.contratos import IniciadorDota, IntegracaoGSI, PlataformaJanelas, SaidaVoz


class SistemaNaoSuportado(RuntimeError):
    """Não existe adaptador para o sistema operacional informado."""


def identificar_sistema() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "linux":
        return "linux"
    raise SistemaNaoSuportado(f"Sistema não suportado: {sys.platform}. Use Windows ou Linux.")


def criar_iniciador_dota() -> IniciadorDota:
    if identificar_sistema() == "windows":
        from .iniciador_windows import criar_iniciador_windows

        return criar_iniciador_windows()
    from .iniciador_linux import criar_iniciador_linux

    return criar_iniciador_linux()


def criar_integracao_gsi(porta: int) -> IntegracaoGSI:
    sistema = identificar_sistema()
    from .integracao_gsi_arquivo import IntegracaoGSIArquivo

    if sistema == "windows":
        from .iniciador_windows import localizar_dota_windows

        return IntegracaoGSIArquivo(localizar_dota_windows, porta)
    from .iniciador_linux import localizar_dota_linux

    return IntegracaoGSIArquivo(localizar_dota_linux, porta)


def criar_plataforma_janelas() -> PlataformaJanelas:
    if identificar_sistema() == "windows":
        from .plataforma_windows import PlataformaWindows

        return PlataformaWindows()
    from .plataforma_linux import PlataformaLinux

    return PlataformaLinux()


def criar_saida_voz() -> SaidaVoz:
    if identificar_sistema() == "windows":
        from .voz_windows import Voz

        return Voz()
    from .voz_linux import VozLinux

    return VozLinux()
