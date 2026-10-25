import logging
import queue
import shutil
import subprocess
import threading
import time

REGISTRO = logging.getLogger(__name__)


class VozLinux:
    def __init__(self) -> None:
        self._comando = shutil.which("espeak-ng")
        self.disponivel = self._comando is not None
        self.fila: queue.Queue[str | None] = queue.Queue(maxsize=32)
        self._encerrada = threading.Event()
        self._trabalhador: threading.Thread | None = None
        if self.disponivel:
            self._trabalhador = threading.Thread(target=self._executar, name="voz-espeak", daemon=True)
            self._trabalhador.start()
        else:
            REGISTRO.warning("Voz indisponível: instale espeak-ng para habilitar os avisos no Linux.")

    def falar(self, texto: str) -> None:
        if not self.disponivel or self._encerrada.is_set() or not texto:
            return
        try:
            self.fila.put_nowait(texto)
        except queue.Full:
            REGISTRO.warning("Fila de voz cheia; aviso descartado.")

    def _falar(self, texto: str) -> None:
        assert self._comando is not None
        processo = subprocess.Popen(
            [self._comando, "-v", "pt-br", "--stdin"], stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", shell=False,
        )
        entrada: str | None = texto
        limite = time.monotonic() + 15
        try:
            while True:
                try:
                    processo.communicate(entrada, timeout=0.1)
                    if processo.returncode != 0:
                        raise OSError(f"espeak-ng encerrou com código {processo.returncode}.")
                    return
                except subprocess.TimeoutExpired:
                    entrada = None
                    if self._encerrada.is_set():
                        return
                    if time.monotonic() >= limite:
                        REGISTRO.warning("Tempo limite do sintetizador excedido; fala interrompida.")
                        return
        finally:
            # Somente o sintetizador criado por este adaptador pode ser interrompido.
            if processo.poll() is None:
                try:
                    processo.terminate()
                except ProcessLookupError:
                    REGISTRO.debug("Sintetizador já encerrado antes da interrupção.")
                try:
                    processo.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        processo.kill()
                    except ProcessLookupError:
                        REGISTRO.debug("Sintetizador já encerrado antes da finalização forçada.")
                    processo.communicate(timeout=1)

    def _executar(self) -> None:
        try:
            while not self._encerrada.is_set():
                texto = self.fila.get()
                if texto is None:
                    return
                self._falar(texto)
        except Exception:
            REGISTRO.exception("Voz espeak-ng indisponível.")
            self.disponivel = False

    def encerrar(self) -> None:
        self.disponivel = False
        self._encerrada.set()
        while True:
            try:
                self.fila.get_nowait()
            except queue.Empty:
                break
        self.fila.put_nowait(None)
        if self._trabalhador is not None:
            self._trabalhador.join(timeout=3)
            if self._trabalhador.is_alive():
                REGISTRO.warning("O sintetizador ainda está encerrando.")
