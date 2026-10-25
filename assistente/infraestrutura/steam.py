"""Descoberta limitada aos metadados KeyValues das bibliotecas Steam."""

import logging
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from assistente.aplicacao.contratos import ErroInicializacao, JogoNaoEncontrado

REGISTRO = logging.getLogger(__name__)
LIMITE_METADADOS_BYTES = 1024 * 1024


@dataclass(frozen=True)
class InstalacaoDota:
    diretorio: Path
    executavel: Path
    comando_steam: tuple[str, ...]


def _tokens(texto: str) -> Iterator[str]:
    indice = 0
    while indice < len(texto):
        caractere = texto[indice]
        if caractere.isspace():
            indice += 1
        elif texto.startswith("//", indice):
            fim = texto.find("\n", indice)
            indice = len(texto) if fim == -1 else fim + 1
        elif caractere in "{}":
            yield caractere
            indice += 1
        elif caractere == '"':
            indice += 1
            partes: list[str] = []
            while indice < len(texto) and texto[indice] != '"':
                if texto[indice] == "\\" and indice + 1 < len(texto) and texto[indice + 1] in '\\"':
                    indice += 1
                partes.append(texto[indice])
                indice += 1
            if indice == len(texto):
                raise ValueError("Texto Steam sem fechamento de aspas.")
            # Prefixo distingue uma string contendo uma chave de um delimitador.
            yield "s:" + "".join(partes)
            indice += 1
        else:
            inicio = indice
            while indice < len(texto) and not texto[indice].isspace() and texto[indice] not in '{}"':
                indice += 1
            yield "s:" + texto[inicio:indice]


def interpretar_vdf(texto: str, rejeitar_duplicadas: bool = False) -> dict[str, object]:
    tokens = iter(_tokens(texto))

    def objeto(profundidade: int, aninhado: bool) -> dict[str, object]:
        if profundidade > 32:
            raise ValueError("Metadados Steam profundos demais.")
        dados: dict[str, object] = {}
        chaves_vistas: set[str] = set()
        for chave in tokens:
            if chave == "}" and aninhado:
                return dados
            if not chave.startswith("s:"):
                raise ValueError("Chave Steam inválida.")
            if rejeitar_duplicadas:
                normalizada = chave[2:].casefold()
                if normalizada in chaves_vistas:
                    raise ValueError(f"Chave KeyValues duplicada: {chave[2:]}.")
                chaves_vistas.add(normalizada)
            valor = next(tokens, None)
            if valor == "{":
                dados[chave[2:]] = objeto(profundidade + 1, True)
            elif valor is not None and valor.startswith("s:"):
                dados[chave[2:]] = valor[2:]
            else:
                raise ValueError("Valor Steam ausente ou inválido.")
        if aninhado:
            raise ValueError("Objeto Steam sem fechamento.")
        return dados

    return objeto(0, False)


def ler_vdf(caminho: Path) -> dict[str, object]:
    with caminho.open("rb") as arquivo:
        conteudo = arquivo.read(LIMITE_METADADOS_BYTES + 1)
    if len(conteudo) > LIMITE_METADADOS_BYTES:
        raise ValueError("Metadados Steam acima do limite.")
    return interpretar_vdf(conteudo.decode("utf-8-sig"))


def bibliotecas_steam(raiz: Path) -> tuple[Path, ...]:
    bibliotecas = [raiz]
    arquivo = raiz / "steamapps/libraryfolders.vdf"
    try:
        dados = ler_vdf(arquivo).get("libraryfolders")
        if not isinstance(dados, dict):
            raise ValueError("Lista de bibliotecas Steam inválida.")
        for indice, biblioteca in dados.items():
            if not isinstance(indice, str) or not indice.isdigit():
                continue
            caminho = biblioteca.get("path") if isinstance(biblioteca, dict) else biblioteca
            if isinstance(caminho, str) and caminho and "\x00" not in caminho:
                pasta = Path(caminho)
                if pasta.is_absolute():
                    bibliotecas.append(pasta)
    except FileNotFoundError:
        REGISTRO.debug("Lista de bibliotecas não encontrada: %s", arquivo)
    except (OSError, ValueError) as erro:
        REGISTRO.warning("Não foi possível ler %s: %s", arquivo, erro)
    return tuple(dict.fromkeys(bibliotecas))


def localizar_instalacao(
    raizes: Iterable[tuple[Path, tuple[str, ...]]], candidatos: tuple[str, ...],
) -> InstalacaoDota:
    visitadas: set[tuple[Path, tuple[str, ...]]] = set()
    sem_cliente: InstalacaoDota | None = None
    for raiz, comando in raizes:
        for biblioteca in bibliotecas_steam(raiz):
            try:
                identidade = (biblioteca.resolve(), comando)
                if identidade in visitadas:
                    continue
                visitadas.add(identidade)
                manifesto = ler_vdf(biblioteca / "steamapps/appmanifest_570.acf").get("AppState")
                if not isinstance(manifesto, dict) or manifesto.get("appid") != "570":
                    raise ValueError("Manifesto não identifica o Dota 2 (570).")
                nome = manifesto.get("installdir")
                if (
                    not isinstance(nome, str) or not nome.strip() or nome in (".", "..")
                    or any(caractere in nome for caractere in "/\\:\x00")
                ):
                    raise ValueError("Diretório do jogo inválido no manifesto Steam.")
                pasta = biblioteca / "steamapps/common" / nome
                for relativo in candidatos:
                    executavel = pasta / relativo
                    if executavel.is_file():
                        instalacao = InstalacaoDota(pasta.resolve(), executavel.resolve(), comando)
                        try:
                            validar_comando(comando)
                        except ErroInicializacao:
                            # Preserva a descoberta para inspeção de um jogo já aberto.
                            if sem_cliente is None:
                                sem_cliente = instalacao
                            break
                        return instalacao
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as erro:
                REGISTRO.warning("Biblioteca Steam ignorada (%s): %s", biblioteca, erro)
    if sem_cliente is not None:
        return sem_cliente
    raise JogoNaoEncontrado("Dota 2 não encontrado nas bibliotecas Steam acessíveis.")


def validar_comando(comando: tuple[str, ...]) -> None:
    if not comando:
        raise ErroInicializacao("Instalação do jogo encontrada, mas o cliente Steam está indisponível.")
    if any(not argumento or "\x00" in argumento for argumento in comando):
        raise ErroInicializacao("Comando Steam inválido.")
    executavel = Path(comando[0])
    try:
        if not executavel.is_absolute() or not executavel.is_file():
            raise ErroInicializacao("Executável do cliente Steam não encontrado.")
        if not os.access(executavel, os.X_OK):
            raise ErroInicializacao("Sem permissão para executar o cliente Steam.")
    except OSError as erro:
        raise ErroInicializacao(f"Não foi possível acessar o cliente Steam: {erro}") from erro
