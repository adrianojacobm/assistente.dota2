import json
import logging
import math
import socket
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from assistente.dominio.catalogo import formatar_nome_heroi
from assistente.dominio.partida import AtualizacaoPartida

REGISTRO = logging.getLogger(__name__)
LIMITE_CORPO_BYTES = 1024 * 1024
ESTADOS_VALIDOS = {
    "DOTA_GAMERULES_STATE_PRE_GAME", "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
    "DOTA_GAMERULES_STATE_HERO_SELECTION", "DOTA_GAMERULES_STATE_STRATEGY_TIME",
}


def _objeto(dados: dict[str, object], chave: str) -> dict[str, object]:
    valor = dados.get(chave)
    if valor is None:
        return {}
    if not isinstance(valor, dict):
        raise ValueError(f"Campo {chave} deve ser um objeto.")
    return valor


def _inteiro(valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
        raise ValueError("Estatística GSI inválida.")
    try:
        numero = float(valor)
        if not math.isfinite(numero):
            raise ValueError("Estatística GSI não finita.")
        return int(numero)
    except (ValueError, OverflowError) as erro:
        raise ValueError("Estatística GSI inválida.") from erro


def interpretar_gsi(dados: object) -> AtualizacaoPartida:
    if not isinstance(dados, dict):
        raise ValueError("O corpo GSI deve ser um objeto JSON.")
    mapa, jogador = _objeto(dados, "map"), _objeto(dados, "player")
    identificador = mapa.get("matchid")
    identificador = (
        str(identificador)
        if isinstance(identificador, (int, str)) and str(identificador) not in ("", "0") else None
    )
    estado = mapa.get("game_state")
    if not isinstance(estado, str) or estado not in ESTADOS_VALIDOS or not jogador:
        return AtualizacaoPartida(False, identificador)
    heroi = _objeto(dados, "hero").get("name", "")
    if not isinstance(heroi, str):
        raise ValueError("Nome do herói inválido.")
    return AtualizacaoPartida(
        em_partida=True, identificador=identificador,
        pre_jogo=estado != "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
        tempo=_inteiro(mapa.get("clock_time", 0)), heroi=formatar_nome_heroi(heroi),
        ultimos_golpes=_inteiro(jogador.get("last_hits", 0)), negacoes=_inteiro(jogador.get("denies", 0)),
        ouro_minuto=_inteiro(jogador.get("gpm", 0)), experiencia_minuto=_inteiro(jogador.get("xpm", 0)),
        abates=_inteiro(jogador.get("kills", 0)), mortes=_inteiro(jogador.get("deaths", 0)),
        assistencias=_inteiro(jogador.get("assists", 0)),
    )


class DotaGSIHandler(BaseHTTPRequestHandler):
    server: "ServidorGSI"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format: str, *args: object) -> None:
        REGISTRO.debug(format, *args)

    def _responder(self, status: int, mensagem: str = "") -> None:
        corpo = mensagem.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        except OSError:
            REGISTRO.debug("Cliente GSI desconectou antes da resposta.", exc_info=True)

    def do_POST(self) -> None:
        tamanho_informado = self.headers.get("Content-Length")
        if tamanho_informado is None:
            self._responder(411, "Content-Length obrigatório.")
            return
        try:
            tamanho = int(tamanho_informado)
        except ValueError:
            self._responder(400, "Content-Length inválido.")
            return
        if tamanho > LIMITE_CORPO_BYTES:
            self._responder(413, "Corpo GSI acima do limite.")
            return
        if tamanho <= 0:
            self._responder(400, "Corpo GSI vazio.")
            return
        try:
            corpo = self.rfile.read(tamanho)
            if len(corpo) != tamanho:
                raise ValueError("Corpo GSI incompleto.")
            atualizacao = interpretar_gsi(json.loads(corpo.decode("utf-8")))
        except TimeoutError:
            self._responder(408, "Tempo de leitura excedido.")
            return
        except (UnicodeError, ValueError):
            self._responder(400, "Dados GSI inválidos.")
            return
        except RecursionError:
            self._responder(400, "Estrutura GSI profunda demais.")
            return
        except OSError:
            REGISTRO.debug("Conexão GSI encerrada durante a leitura.", exc_info=True)
            return
        try:
            self.server.processar_atualizacao(atualizacao)
        except Exception:
            REGISTRO.exception("Falha inesperada ao processar GSI.")
            self._responder(500, "Falha interna ao processar GSI.")
            return
        self._responder(200)


class ServidorGSI(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(
        self, endereco: tuple[str, int], processar: Callable[[AtualizacaoPartida], None],
        maximo_conexoes: int = 4,
    ) -> None:
        if maximo_conexoes < 1:
            raise ValueError("O limite de conexões precisa ser positivo.")
        self.processar_atualizacao = processar
        self._trabalhador: threading.Thread | None = None
        self._vagas = threading.BoundedSemaphore(maximo_conexoes)
        self._conexoes: set[socket.socket] = set()
        self._trava_conexoes = threading.Lock()
        self._encerrado = threading.Event()
        super().__init__(endereco, DotaGSIHandler)

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        if self._encerrado.is_set() or not self._vagas.acquire(blocking=False):
            try:
                request.settimeout(0.1)
                request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                REGISTRO.debug("Cliente GSI desconectado ao rejeitar conexão excedente.")
            finally:
                self.shutdown_request(request)
            return
        with self._trava_conexoes:
            self._conexoes.add(request)
        try:
            super().process_request(request, client_address)
        except Exception:
            self._liberar_conexao(request)
            raise

    def process_request_thread(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._liberar_conexao(request)

    def _liberar_conexao(self, conexao: socket.socket) -> None:
        with self._trava_conexoes:
            self._conexoes.discard(conexao)
        self._vagas.release()

    def iniciar(self) -> None:
        if self._trabalhador is not None or self._encerrado.is_set():
            raise RuntimeError("O servidor GSI não pode ser iniciado novamente.")
        self._trabalhador = threading.Thread(target=self.serve_forever, name="servidor-gsi", daemon=True)
        self._trabalhador.start()

    def encerrar(self) -> None:
        self._encerrado.set()
        if self._trabalhador is not None and self._trabalhador.is_alive():
            self.shutdown()
            self._trabalhador.join(timeout=2)
        with self._trava_conexoes:
            conexoes = tuple(self._conexoes)
        for conexao in conexoes:
            try:
                conexao.shutdown(socket.SHUT_RDWR)
            except OSError:
                REGISTRO.debug("Conexão GSI já encerrada.")
        self.server_close()
