"""Instala somente o arquivo GSI do assistente, sem alterar as demais integrações."""

import hashlib
import logging
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import replace
from math import isfinite
from pathlib import Path

from assistente.aplicacao.configurar_integracao_gsi import (
    ConfirmacaoReparoGSI,
    EstadoConfiguracaoGSI,
    ResultadoConfiguracaoGSI,
)
from assistente.aplicacao.contratos import ErroConfiguracaoGSI, ErroInicializacao

from .steam import InstalacaoDota, interpretar_vdf

REGISTRO = logging.getLogger(__name__)
NOME_ARQUIVO_GSI = "gamestate_integration_assistente.cfg"
LIMITE_CONFIGURACAO_BYTES = 64 * 1024
CAMPOS_GSI = ("provider", "map", "player", "hero")


def gerar_configuracao_gsi(porta: int) -> str:
    if isinstance(porta, bool) or not isinstance(porta, int) or not 1 <= porta <= 65535:
        raise ValueError("A porta GSI deve estar entre 1 e 65535.")
    campos = "\n".join(f'        "{campo}" "1"' for campo in CAMPOS_GSI)
    return (
        "// Gerado pelo Assistente Dota 2.\n"
        '"Assistente Dota 2"\n{\n'
        f'    "uri" "http://127.0.0.1:{porta}"\n'
        '    "timeout" "5.0"\n'
        '    "buffer" "0.1"\n'
        '    "throttle" "0.2"\n'
        '    "heartbeat" "30.0"\n'
        f'    "data"\n    {{\n{campos}\n    }}\n}}\n'
    )


def _motivo_incompatibilidade(conteudo: bytes, uri: str) -> str | None:
    try:
        dados = interpretar_vdf(conteudo.decode("utf-8-sig"), rejeitar_duplicadas=True)
    except (UnicodeError, ValueError) as erro:
        return f"Não foi possível interpretar o arquivo: {erro}"
    if len(dados) != 1 or not isinstance(configuracao := next(iter(dados.values())), dict):
        return "O arquivo deve conter um único objeto de configuração GSI."
    endereco = configuracao.get("uri")
    if not isinstance(endereco, str) or endereco.rstrip("/") != uri:
        return f"O destino deve ser {uri}, a mesma porta do servidor do assistente."
    campos = configuracao.get("data")
    if not isinstance(campos, dict) or any(campos.get(campo) != "1" for campo in CAMPOS_GSI):
        return "Os campos provider, map, player e hero precisam estar habilitados."
    for chave in ("timeout", "buffer", "throttle", "heartbeat"):
        valor = configuracao.get(chave)
        try:
            if not isinstance(valor, str):
                raise ValueError("Valor ausente ou não textual.")
            numero = float(valor)
            if not isfinite(numero) or numero < 0 or (chave in ("timeout", "heartbeat") and numero == 0):
                raise ValueError("Valor fora dos limites.")
        except ValueError:
            return f"O parâmetro {chave} está ausente ou inválido."
    return None


def _ler_arquivo(caminho: Path) -> bytes | None:
    try:
        situacao = caminho.lstat()
        if not stat.S_ISREG(situacao.st_mode):
            raise ErroConfiguracaoGSI(
                "O destino GSI não é um arquivo regular; não será seguido.", str(caminho),
            )
        opcoes = (
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_BINARY", 0)
        )
        descritor = os.open(caminho, opcoes)
    except FileNotFoundError:
        return None
    with os.fdopen(descritor, "rb") as arquivo:
        aberto = os.fstat(arquivo.fileno())
        if not stat.S_ISREG(aberto.st_mode) or not os.path.samestat(situacao, aberto):
            raise ErroConfiguracaoGSI("O arquivo GSI mudou durante a leitura.", str(caminho))
        conteudo = arquivo.read(LIMITE_CONFIGURACAO_BYTES + 1)
        depois = os.fstat(arquivo.fileno())
        if (aberto.st_size, aberto.st_mtime_ns) != (depois.st_size, depois.st_mtime_ns):
            raise ErroConfiguracaoGSI(
                "O arquivo GSI foi editado durante a leitura; verifique novamente.", str(caminho),
            )
    if len(conteudo) > LIMITE_CONFIGURACAO_BYTES:
        raise ErroConfiguracaoGSI("Arquivo GSI acima de 64 KiB; não será substituído.", str(caminho))
    return conteudo


def _remover_temporario(caminho: Path) -> None:
    try:
        caminho.unlink()
    except OSError:
        REGISTRO.warning("Não foi possível remover o arquivo temporário %s.", caminho, exc_info=True)


def _gravar_temporario(pasta: Path, conteudo: bytes, sufixo: str) -> Path:
    descritor, nome = tempfile.mkstemp(prefix=".assistente-gsi-", suffix=sufixo, dir=pasta)
    caminho = Path(nome)
    try:
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
    except BaseException:
        _remover_temporario(caminho)
        raise
    return caminho


def _criar_exclusivo(caminho: Path, conteudo: bytes) -> None:
    identidade: os.stat_result | None = None
    try:
        with caminho.open("xb") as arquivo:
            identidade = os.fstat(arquivo.fileno())
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
    except BaseException:
        try:
            # Nunca remova um arquivo que tenha substituído aquele criado por nós.
            if identidade is not None and os.path.samestat(identidade, caminho.lstat()):
                caminho.unlink()
        except FileNotFoundError:
            REGISTRO.debug("Arquivo GSI incompleto já removido: %s", caminho)
        except OSError:
            REGISTRO.warning("Não foi possível remover o arquivo GSI incompleto %s.", caminho, exc_info=True)
        raise


class IntegracaoGSIArquivo:
    def __init__(self, localizar: Callable[[], InstalacaoDota], porta: int) -> None:
        self._localizar = localizar
        self._conteudo = gerar_configuracao_gsi(porta).encode("utf-8")
        self._uri = f"http://127.0.0.1:{porta}"

    def _destino(self) -> tuple[Path, Path]:
        try:
            instalacao = self._localizar()
        except (ErroInicializacao, OSError) as erro:
            raise ErroConfiguracaoGSI(f"Não foi possível localizar a instalação do Dota 2: {erro}") from erro
        try:
            raiz = instalacao.diretorio.resolve(strict=True)
            if not raiz.is_dir():
                raise OSError("A instalação não é um diretório.")
        except (OSError, RuntimeError) as erro:
            raise ErroConfiguracaoGSI(f"Não foi possível localizar a instalação do Dota 2: {erro}") from erro
        caminho = raiz / "game/dota/cfg/gamestate_integration" / NOME_ARQUIVO_GSI
        self._validar_destino(caminho, raiz)
        return raiz, caminho

    @staticmethod
    def _validar_destino(caminho: Path, raiz: Path) -> None:
        try:
            pasta = caminho.parent.resolve()
            link = caminho.is_symlink()
        except (OSError, RuntimeError) as erro:
            raise ErroConfiguracaoGSI(f"Destino GSI inacessível: {erro}", str(caminho)) from erro
        if not pasta.is_relative_to(raiz):
            raise ErroConfiguracaoGSI("A pasta GSI aponta para fora da instalação do jogo.", str(caminho))
        if link:
            raise ErroConfiguracaoGSI(
                "O arquivo GSI é um link; não será seguido nem substituído.", str(caminho),
            )

    def _inspecionar(self, caminho: Path) -> tuple[ResultadoConfiguracaoGSI, bytes | None]:
        conteudo = _ler_arquivo(caminho)
        if conteudo is None:
            return ResultadoConfiguracaoGSI(EstadoConfiguracaoGSI.AUSENTE, str(caminho)), None
        motivo = _motivo_incompatibilidade(conteudo, self._uri)
        if motivo is None:
            return ResultadoConfiguracaoGSI(EstadoConfiguracaoGSI.CONFIGURADO, str(caminho)), conteudo
        confirmacao = ConfirmacaoReparoGSI(str(caminho), hashlib.sha256(conteudo).hexdigest())
        return ResultadoConfiguracaoGSI(
            EstadoConfiguracaoGSI.CONFLITO, str(caminho), erro=motivo, reparo=confirmacao,
        ), conteudo

    def verificar(self) -> ResultadoConfiguracaoGSI:
        _, caminho = self._destino()
        try:
            return self._inspecionar(caminho)[0]
        except OSError as erro:
            raise ErroConfiguracaoGSI(f"Não foi possível ler o arquivo GSI: {erro}", str(caminho)) from erro

    def configurar(
        self, confirmacao: ConfirmacaoReparoGSI | None = None,
        verificar_ativa: Callable[[], None] | None = None,
    ) -> ResultadoConfiguracaoGSI:
        raiz, caminho = self._destino()
        # A descoberta pode consultar a Steam Flatpak. Reconfira o encerramento antes de gravar.
        verificar = verificar_ativa or (lambda: None)
        verificar()
        copia: Path | None = None
        try:
            atual, conteudo = self._inspecionar(caminho)
            if atual.estado == EstadoConfiguracaoGSI.CONFIGURADO:
                return atual
            if confirmacao is not None and atual.reparo != confirmacao:
                return atual
            if atual.estado == EstadoConfiguracaoGSI.CONFLITO:
                if confirmacao is None:
                    return atual
                assert conteudo is not None
                verificar()
                copia = _gravar_temporario(caminho.parent, conteudo, ".bak")
                temporario = _gravar_temporario(caminho.parent, self._conteudo, ".tmp")
                try:
                    verificar()
                    # Uma edição entre a confirmação e a gravação exige nova confirmação.
                    recente, _ = self._inspecionar(caminho)
                    if recente.reparo != confirmacao:
                        return replace(recente, copia_seguranca=str(copia))
                    self._validar_destino(caminho, raiz)
                    os.replace(temporario, caminho)
                finally:
                    if temporario.exists():
                        _remover_temporario(temporario)
                return ResultadoConfiguracaoGSI(
                    EstadoConfiguracaoGSI.REPARADO, str(caminho), copia_seguranca=str(copia),
                )
            verificar()
            caminho.parent.mkdir(parents=True, exist_ok=True)
            self._validar_destino(caminho, raiz)
            verificar()
            try:
                # Criação exclusiva: um arquivo surgido após a verificação nunca é sobrescrito.
                _criar_exclusivo(caminho, self._conteudo)
            except FileExistsError:
                return self._inspecionar(caminho)[0]
            return ResultadoConfiguracaoGSI(EstadoConfiguracaoGSI.CRIADO, str(caminho))
        except ErroConfiguracaoGSI as erro:
            if copia is not None:
                raise ErroConfiguracaoGSI(str(erro), erro.caminho, str(copia)) from erro
            raise
        except OSError as erro:
            raise ErroConfiguracaoGSI(
                f"Não foi possível configurar o GSI: {erro}", str(caminho),
                str(copia) if copia is not None else None,
            ) from erro
