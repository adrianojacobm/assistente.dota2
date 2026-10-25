from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from assistente.aplicacao.contratos import ErroInicializacao, JogoNaoEncontrado
from assistente.aplicacao.iniciar_dota import EstadoExecucao
from assistente.infraestrutura import steam
from assistente.infraestrutura.iniciador_steam import ErroInspecaoProcesso, IniciadorSteam
from assistente.infraestrutura.steam import InstalacaoDota, interpretar_vdf, localizar_instalacao

if TYPE_CHECKING:
    import pytest


def preparar_instalacao(raiz: Path, relativo: str = "game/bin/linuxsteamrt64/dota2") -> Path:
    pasta = raiz / "steamapps/common/Dota personalizado"
    executavel = pasta / relativo
    executavel.parent.mkdir(parents=True)
    executavel.touch()
    (raiz / "steamapps/appmanifest_570.acf").write_text(
        '"AppState" { "appid" "570" "installdir" "Dota personalizado" }', encoding="utf-8",
    )
    return executavel


def preparar_iniciador(raiz: Path) -> tuple[IniciadorSteam, Mock, InstalacaoDota]:
    executavel = preparar_instalacao(raiz)
    cliente = raiz / "steam.exe"
    cliente.touch()
    cliente.chmod(0o755)
    instalacao = InstalacaoDota(executavel.parents[3], executavel, (str(cliente),))
    procurar = Mock(return_value=None)
    return IniciadorSteam(lambda: instalacao, procurar), procurar, instalacao


def test_vdf_preserva_escapes_chaves_em_strings_e_bibliotecas_antigas() -> None:
    dados = interpretar_vdf(r'''
        // Biblioteca Windows e formato antigo
        "libraryfolders" { "0" { "path" "D:\\Steam nova" } "1" "/mnt/jogos" }
        "rotulo" "{a} \"citado\""
    ''')
    assert dados["libraryfolders"] == {"0": {"path": "D:\\Steam nova"}, "1": "/mnt/jogos"}
    assert dados["rotulo"] == '{a} "citado"'


def test_vdf_rejeita_dados_truncados_e_profundidade_excessiva() -> None:
    import pytest

    for texto in ('"chave"', '"chave" {', '"chave" "sem fim', '}', '"x" }', '"a" {' * 34):
        with pytest.raises(ValueError):
            interpretar_vdf(texto)


def test_metadados_tem_limite_de_leitura(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import pytest

    arquivo = tmp_path / "dados.vdf"
    arquivo.write_text('"a" "valor"', encoding="utf-8")
    monkeypatch.setattr(steam, "LIMITE_METADADOS_BYTES", 4)
    with pytest.raises(ValueError, match="limite"):
        steam.ler_vdf(arquivo)


def test_localiza_biblioteca_secundaria_com_espacos_e_unicode(tmp_path: Path) -> None:
    raiz = tmp_path / "Steam"
    (raiz / "steamapps").mkdir(parents=True)
    biblioteca = tmp_path / "Biblioteca ação"
    esperado = preparar_instalacao(biblioteca)
    # as_posix evita depender do escape de caminhos do SO que executa o teste.
    (raiz / "steamapps/libraryfolders.vdf").write_text(
        f'"libraryfolders" {{ "0" {{ "path" "{raiz.as_posix()}" }} '
        f'"1" {{ "path" "{(tmp_path / "desmontada").as_posix()}" }} '
        f'"2" {{ "path" "{biblioteca.as_posix()}" }} }}', encoding="utf-8",
    )
    encontrado = localizar_instalacao(((raiz, ("steam",)),), ("game/bin/linuxsteamrt64/dota2",))
    assert encontrado.executavel == esperado.resolve()
    assert encontrado.diretorio.name == "Dota personalizado"


def test_manifesto_invalido_nao_impede_outra_biblioteca_valida(tmp_path: Path) -> None:
    ruim = tmp_path / "ruim"
    preparar_instalacao(ruim)
    (ruim / "steamapps/appmanifest_570.acf").write_text("incompleto", encoding="utf-8")
    boa = tmp_path / "boa"
    esperado = preparar_instalacao(boa)
    resultado = localizar_instalacao(((ruim, ()), (boa, ())), ("game/bin/linuxsteamrt64/dota2",))
    assert resultado.executavel == esperado.resolve()


def test_mesma_biblioteca_prefere_cliente_utilizavel(tmp_path: Path) -> None:
    esperado = preparar_instalacao(tmp_path)
    cliente = tmp_path / "steam.exe"
    cliente.touch()
    cliente.chmod(0o755)
    comando = (str(cliente),)
    resultado = localizar_instalacao(
        ((tmp_path, ()), (tmp_path, comando)), ("game/bin/linuxsteamrt64/dota2",),
    )
    assert resultado.executavel == esperado.resolve()
    assert resultado.comando_steam == comando


def test_executavel_ausente_gera_erro_especifico(tmp_path: Path) -> None:
    import pytest

    executavel = preparar_instalacao(tmp_path)
    executavel.unlink()
    with pytest.raises(JogoNaoEncontrado):
        localizar_instalacao(((tmp_path, ()),), ("game/bin/linuxsteamrt64/dota2",))


def test_manifesto_nao_pode_redirecionar_para_caminho_arbitrario(tmp_path: Path) -> None:
    import pytest

    preparar_instalacao(tmp_path)
    manifesto = tmp_path / "steamapps/appmanifest_570.acf"
    for nome in ("..", "../fora", "/fora", r"C:\\fora", "sub/pasta"):
        manifesto.write_text(f'"AppState" {{ "appid" "570" "installdir" "{nome}" }}', encoding="utf-8")
        with pytest.raises(JogoNaoEncontrado):
            localizar_instalacao(((tmp_path, ()),), ("game/bin/linuxsteamrt64/dota2",))


def test_lancamento_nao_confunde_pid_da_steam_com_dota(tmp_path: Path) -> None:
    iniciador, procurar, instalacao = preparar_iniciador(tmp_path)
    processo = Mock(pid=81)
    processo.poll.return_value = None
    with patch("assistente.infraestrutura.iniciador_steam.subprocess.Popen", return_value=processo) as popen:
        resultado = iniciador.iniciar()
    assert resultado.estado == EstadoExecucao.INICIADOR_ATIVO
    assert resultado.pid_iniciador == 81
    assert resultado.pid_jogo is None
    assert popen.call_args.args[0] == [*instalacao.comando_steam, "-applaunch", "570"]
    assert popen.call_args.kwargs["shell"] is False
    procurar.return_value = 99
    assert iniciador.consultar().pid_jogo == 99
    iniciador.encerrar()
    processo.terminate.assert_not_called()
    processo.kill.assert_not_called()
    processo.wait.assert_not_called()


def test_jogo_ja_aberto_nao_inicia_steam(tmp_path: Path) -> None:
    iniciador, procurar, _ = preparar_iniciador(tmp_path)
    procurar.return_value = 5
    with patch("assistente.infraestrutura.iniciador_steam.subprocess.Popen") as popen:
        resultado = iniciador.iniciar()
    assert resultado.estado == EstadoExecucao.EM_EXECUCAO
    assert resultado.pid_jogo == 5
    assert resultado.pid_iniciador is None
    popen.assert_not_called()


def test_comando_aceito_nao_comprova_execucao_e_nao_e_repetido(tmp_path: Path) -> None:
    iniciador, _, _ = preparar_iniciador(tmp_path)
    processo = Mock(pid=81)
    processo.poll.return_value = 0
    with patch("assistente.infraestrutura.iniciador_steam.subprocess.Popen", return_value=processo) as popen:
        primeiro = iniciador.iniciar()
        segundo = iniciador.iniciar()
    assert primeiro.estado == segundo.estado == EstadoExecucao.SOLICITADO
    assert segundo.pid_jogo is None
    popen.assert_called_once()


def test_falha_do_comando_steam_e_reportada(tmp_path: Path) -> None:
    iniciador, _, _ = preparar_iniciador(tmp_path)
    processo = Mock(pid=81)
    processo.poll.return_value = 17
    with patch("assistente.infraestrutura.iniciador_steam.subprocess.Popen", return_value=processo):
        resultado = iniciador.iniciar()
    assert resultado.estado == EstadoExecucao.FALHA
    assert "17" in (resultado.erro or "")
    assert resultado.pid_jogo is None
    assert resultado.pid_iniciador == 81


def test_falhas_de_popen_sao_traduzidas(tmp_path: Path) -> None:
    import pytest

    iniciador, _, _ = preparar_iniciador(tmp_path)
    for erro in (PermissionError("negado"), FileNotFoundError("ausente"), OSError("falhou")):
        with patch("assistente.infraestrutura.iniciador_steam.subprocess.Popen", side_effect=erro):
            with pytest.raises(ErroInicializacao):
                iniciador.iniciar()


def test_cliente_steam_invalido_nao_e_executado(tmp_path: Path) -> None:
    import pytest

    for comando in ((), ("steam",), (str(tmp_path / "ausente"),), ("\x00",)):
        with pytest.raises(ErroInicializacao):
            steam.validar_comando(comando)
    cliente = tmp_path / "steam.exe"
    cliente.touch()
    with (
        patch.object(steam.os, "access", return_value=False),
        pytest.raises(ErroInicializacao, match="permissão"),
    ):
        steam.validar_comando((str(cliente),))


def test_inspecao_inacessivel_nao_e_tratada_como_jogo_fechado(tmp_path: Path) -> None:
    iniciador, procurar, _ = preparar_iniciador(tmp_path)
    procurar.side_effect = ErroInspecaoProcesso("Permissão negada.")
    with patch("assistente.infraestrutura.iniciador_steam.subprocess.Popen") as popen:
        resultado = iniciador.iniciar()
    assert resultado.estado == EstadoExecucao.NAO_CONFIRMADO
    popen.assert_not_called()


def test_erro_de_acesso_ao_cliente_e_especifico(tmp_path: Path) -> None:
    import pytest

    with (
        patch.object(Path, "is_file", side_effect=PermissionError("negado")),
        pytest.raises(ErroInicializacao, match="acessar"),
    ):
        steam.validar_comando((str(tmp_path / "steam.exe"),))


def test_localizacao_e_reutilizada_e_revalidada(tmp_path: Path) -> None:
    import pytest

    executavel = preparar_instalacao(tmp_path)
    instalacao = InstalacaoDota(tmp_path, executavel, ())
    localizar = Mock(return_value=instalacao)
    iniciador = IniciadorSteam(localizar, Mock(return_value=None))
    iniciador.consultar()
    iniciador.consultar()
    localizar.assert_called_once()
    executavel.unlink()
    localizar.side_effect = JogoNaoEncontrado("Instalação removida.")
    with pytest.raises(JogoNaoEncontrado):
        iniciador.consultar()


def test_jogo_encerrado_pode_ser_aberto_novamente(tmp_path: Path) -> None:
    iniciador, procurar, _ = preparar_iniciador(tmp_path)
    procurar.return_value = 5
    assert iniciador.consultar().estado == EstadoExecucao.EM_EXECUCAO
    procurar.return_value = None
    assert iniciador.consultar().estado == EstadoExecucao.NAO_OBSERVADO
    processo = Mock(pid=10)
    processo.poll.return_value = 0
    with patch("assistente.infraestrutura.iniciador_steam.subprocess.Popen", return_value=processo) as popen:
        assert iniciador.iniciar().estado == EstadoExecucao.SOLICITADO
    popen.assert_called_once()
