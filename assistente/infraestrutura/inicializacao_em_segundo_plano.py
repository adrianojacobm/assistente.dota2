import logging
import queue
import threading
import time
from dataclasses import replace
from math import isfinite

from assistente.aplicacao.iniciar_dota import EstadoExecucao, IniciarDota, ResultadoExecucao

REGISTRO = logging.getLogger(__name__)
ESTADOS_PENDENTES = {EstadoExecucao.SOLICITADO, EstadoExecucao.INICIADOR_ATIVO}


class ExecutorInicializacao:
    """Uma solicitação por vez, com confirmação limitada e sem acesso a widgets."""

    def __init__(self, caso_de_uso: IniciarDota, prazo_s: float = 30, intervalo_s: float = 0.5) -> None:
        if not isfinite(prazo_s) or not isfinite(intervalo_s) or prazo_s < 0 or intervalo_s <= 0:
            raise ValueError("Prazo e intervalo de inicialização inválidos.")
        self._caso_de_uso = caso_de_uso
        self._prazo_s, self._intervalo_s = prazo_s, intervalo_s
        self._pedido = threading.Event()
        self._encerrado = threading.Event()
        self._trava = threading.Lock()
        self._ocupado = False
        self._resultados: queue.Queue[ResultadoExecucao] = queue.Queue(maxsize=1)
        self._trabalhador = threading.Thread(target=self._processar, name="iniciar-dota", daemon=True)
        self._trabalhador.start()

    def solicitar(self) -> bool:
        with self._trava:
            if self._ocupado or self._encerrado.is_set():
                return False
            self.obter_resultados()
            self._ocupado = True
            self._pedido.set()
            return True

    def obter_resultados(self) -> list[ResultadoExecucao]:
        try:
            return [self._resultados.get_nowait()]
        except queue.Empty:
            return []

    def _publicar(self, resultado: ResultadoExecucao, final: bool = False) -> None:
        with self._trava:
            if self._encerrado.is_set():
                return
            if final:
                self._ocupado = False
            self.obter_resultados()
            self._resultados.put_nowait(resultado)

    def _confirmar(self) -> None:
        resultado = self._caso_de_uso.executar()
        limite = time.monotonic() + self._prazo_s
        while resultado.estado in ESTADOS_PENDENTES:
            restante = limite - time.monotonic()
            if restante <= 0:
                resultado = replace(resultado, estado=EstadoExecucao.NAO_CONFIRMADO)
                break
            self._publicar(resultado)
            if self._encerrado.wait(min(self._intervalo_s, restante)):
                return
            resultado = self._caso_de_uso.consultar()
        self._publicar(resultado, final=True)

    def _processar(self) -> None:
        try:
            while True:
                self._pedido.wait()
                if self._encerrado.is_set():
                    return
                self._pedido.clear()
                try:
                    self._confirmar()
                except Exception:
                    REGISTRO.exception("Falha inesperada ao iniciar ou verificar o Dota 2.")
                    self._publicar(ResultadoExecucao(
                        EstadoExecucao.FALHA, erro="Erro inesperado. Consulte o registro do aplicativo.",
                    ), final=True)
        finally:
            self._caso_de_uso.encerrar()

    def encerrar(self) -> None:
        with self._trava:
            self._encerrado.set()
            self.obter_resultados()
            self._pedido.set()
        self._trabalhador.join(timeout=2)
        if self._trabalhador.is_alive():
            REGISTRO.warning("Aguardando o término da operação de inicialização em andamento.")
