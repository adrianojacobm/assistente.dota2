from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock, call, patch

from assistente.infraestrutura import iniciador_linux, iniciador_windows, plataforma
from assistente.infraestrutura.iniciador_steam import ErroInspecaoProcesso
from tests.test_steam import preparar_instalacao

if TYPE_CHECKING:
    import pytest


def test_detecta_windows_e_seleciona_estrategia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plataforma, "sys", SimpleNamespace(platform="win32"))
    assert plataforma.identificar_sistema() == "windows"
    iniciador = plataforma.criar_iniciador_dota()
    assert iniciador._localizar is iniciador_windows.localizar_dota_windows
    assert iniciador._procurar_pid is iniciador_windows.procurar_pid_windows
    integracao = plataforma.criar_integracao_gsi(4000)
    assert integracao._localizar is iniciador_windows.localizar_dota_windows
    with (
        patch("assistente.infraestrutura.plataforma_windows.PlataformaWindows") as janelas,
        patch("assistente.infraestrutura.voz_windows.Voz") as voz,
    ):
        assert plataforma.criar_plataforma_janelas() is janelas.return_value
        assert plataforma.criar_saida_voz() is voz.return_value


def test_detecta_linux_e_seleciona_estrategia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plataforma, "sys", SimpleNamespace(platform="linux"))
    assert plataforma.identificar_sistema() == "linux"
    iniciador = plataforma.criar_iniciador_dota()
    assert iniciador._localizar is iniciador_linux.localizar_dota_linux
    assert iniciador._procurar_pid is iniciador_linux.procurar_pid_linux
    integracao = plataforma.criar_integracao_gsi(4000)
    assert integracao._localizar is iniciador_linux.localizar_dota_linux
    with (
        patch("assistente.infraestrutura.plataforma_linux.PlataformaLinux") as janelas,
        patch("assistente.infraestrutura.voz_linux.VozLinux") as voz,
    ):
        assert plataforma.criar_plataforma_janelas() is janelas.return_value
        assert plataforma.criar_saida_voz() is voz.return_value


def test_sistemas_nao_suportados_sao_rejeitados(monkeypatch: pytest.MonkeyPatch) -> None:
    import pytest

    for sistema in ("darwin", "freebsd", "desconhecido"):
        monkeypatch.setattr(plataforma, "sys", SimpleNamespace(platform=sistema))
        for fabricar in (
            plataforma.criar_iniciador_dota, plataforma.criar_plataforma_janelas, plataforma.criar_saida_voz,
        ):
            with pytest.raises(plataforma.SistemaNaoSuportado):
                fabricar()
        with pytest.raises(plataforma.SistemaNaoSuportado):
            plataforma.criar_integracao_gsi(4000)


def test_linux_respeita_xdg_e_executavel_nativo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dados = tmp_path / "dados"
    esperado = preparar_instalacao(dados / "Steam")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(dados))
    monkeypatch.setattr(
        iniciador_linux.shutil, "which", lambda nome: "/cliente/steam" if nome == "steam" else None,
    )
    instalacao = iniciador_linux.localizar_dota_linux()
    assert instalacao.executavel == esperado.resolve()
    assert instalacao.comando_steam == ("/cliente/steam",)


def test_flatpak_usa_cliente_correspondente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raiz = tmp_path / ".var/app/com.valvesoftware.Steam/.local/share/Steam"
    esperado = preparar_instalacao(raiz)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "dados"))
    monkeypatch.setattr(
        iniciador_linux.shutil, "which", lambda nome: "/cliente/flatpak" if nome == "flatpak" else None,
    )
    with patch.object(iniciador_linux.subprocess, "run", return_value=Mock(returncode=0)) as consultar:
        instalacao = iniciador_linux.localizar_dota_linux()
    assert instalacao.executavel == esperado.resolve()
    assert instalacao.comando_steam == ("/cliente/flatpak", "run", "com.valvesoftware.Steam")
    assert consultar.call_args.kwargs["timeout"] == 3


def test_windows_descobre_steam_no_registro_e_localiza_jogo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    esperado = preparar_instalacao(tmp_path, "game/bin/win64/dota2.exe")
    registro = ModuleType("winreg")
    nomes = ("HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE", "KEY_WOW64_32KEY", "KEY_WOW64_64KEY", "KEY_READ")
    for indice, nome in enumerate(nomes):
        setattr(registro, nome, indice + 1)
    chave = Mock()
    contexto = Mock(__enter__=Mock(return_value=chave), __exit__=Mock(return_value=False))
    registro.OpenKey = Mock(return_value=contexto)

    def consultar(chave: object, nome: str) -> tuple[str, int]:
        if nome == "SteamPath":
            return str(tmp_path), 1
        raise FileNotFoundError(nome)

    registro.QueryValueEx = Mock(side_effect=consultar)
    monkeypatch.setitem(sys.modules, "winreg", registro)
    monkeypatch.setattr(iniciador_windows.shutil, "which", lambda nome: None)
    instalacao = iniciador_windows.localizar_dota_windows()
    assert instalacao.executavel == esperado.resolve()
    assert instalacao.comando_steam == (str(tmp_path / "steam.exe"),)
    assert registro.OpenKey.call_count == 4


def test_proc_identifica_arquivo_real_e_ignora_pid_da_steam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executavel = preparar_instalacao(tmp_path / "Steam")
    processos = tmp_path / "proc"
    for pid, nome in (("11", "steam"), ("12", "dota2")):
        pasta = processos / pid
        pasta.mkdir(parents=True)
        (pasta / "comm").write_text(nome, encoding="utf-8")
    comparacoes = []

    def mesmo_arquivo(caminho: Path, outro: Path) -> bool:
        comparacoes.append((caminho, outro))
        return caminho == processos / "12/exe" and outro == executavel

    monkeypatch.setattr(Path, "samefile", mesmo_arquivo)
    assert iniciador_linux.procurar_pid_linux(executavel, processos) == 12
    assert comparacoes == [(processos / "12/exe", executavel)]


def test_proc_inacessivel_gera_observacao_inconclusiva(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ErroInspecaoProcesso):
        iniciador_linux.procurar_pid_linux(tmp_path / "dota2", tmp_path / "ausente")


def test_inspecao_windows_fecha_handles_e_confere_caminho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executavel = preparar_instalacao(tmp_path, "game/bin/win64/dota2.exe")
    api = Mock()
    api.CreateToolhelp32Snapshot.return_value = 50
    api.OpenProcess.return_value = 60
    codigo_saida = 259

    def primeiro(captura: int, ponteiro: object) -> int:
        entrada = ctypes.cast(ponteiro, ctypes.POINTER(iniciador_windows.EntradaProcessoWindows)).contents
        entrada.szExeFile = "dota2.exe"
        entrada.th32ProcessID = 75
        return 1

    def imagem(processo: int, flags: int, caminho: object, tamanho: object) -> int:
        caminho.value = str(executavel.resolve())
        return 1

    def consultar_saida(processo: int, ponteiro: object) -> int:
        ctypes.cast(ponteiro, ctypes.POINTER(ctypes.c_uint32)).contents.value = codigo_saida
        return 1

    api.Process32FirstW.side_effect = primeiro
    api.Process32NextW.return_value = 0
    api.QueryFullProcessImageNameW.side_effect = imagem
    api.GetExitCodeProcess.side_effect = consultar_saida
    monkeypatch.setattr(iniciador_windows, "_carregar_api", lambda: api)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 18, raising=False)
    assert iniciador_windows.procurar_pid_windows(executavel) == 75
    assert api.CloseHandle.call_args_list == [call(60), call(50)]
    codigo_saida = 0
    assert iniciador_windows.procurar_pid_windows(executavel) is None
    assert api.CloseHandle.call_count == 4


def test_inspecao_windows_nao_inventa_pid_sem_permissao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pytest

    executavel = preparar_instalacao(tmp_path, "game/bin/win64/dota2.exe")
    api = Mock()
    api.CreateToolhelp32Snapshot.return_value = 50
    api.OpenProcess.return_value = None

    def primeiro(captura: int, ponteiro: object) -> int:
        entrada = ctypes.cast(ponteiro, ctypes.POINTER(iniciador_windows.EntradaProcessoWindows)).contents
        entrada.szExeFile = "dota2.exe"
        entrada.th32ProcessID = 75
        return 1

    api.Process32FirstW.side_effect = primeiro
    api.Process32NextW.return_value = 0
    monkeypatch.setattr(iniciador_windows, "_carregar_api", lambda: api)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 18, raising=False)
    with pytest.raises(ErroInspecaoProcesso):
        iniciador_windows.procurar_pid_windows(executavel)
    api.CloseHandle.assert_called_once_with(50)
