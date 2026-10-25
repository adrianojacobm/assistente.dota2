import logging
import queue
import sys
import threading

REGISTRO = logging.getLogger(__name__)


class Voz:
    def __init__(self) -> None:
        self.fila: queue.Queue[str | None] = queue.Queue(maxsize=32)
        self.disponivel = sys.platform == "win32"
        self._encerrada = threading.Event()
        self._trabalhador: threading.Thread | None = None
        if self.disponivel:
            self._trabalhador = threading.Thread(target=self._executar, name="voz-sapi", daemon=True)
            self._trabalhador.start()

    def falar(self, texto: str) -> None:
        if not self.disponivel or self._encerrada.is_set() or not texto:
            return
        try:
            self.fila.put_nowait(texto)
        except queue.Full:
            REGISTRO.warning("Fila de voz cheia; aviso descartado.")

    def encerrar(self) -> None:
        self._encerrada.set()
        self.disponivel = False
        while True:
            try:
                self.fila.get_nowait()
            except queue.Empty:
                break
        try:
            self.fila.put_nowait(None)
        except queue.Full:
            REGISTRO.debug("Fila já sinalizada para encerramento.")
        if self._trabalhador is not None:
            self._trabalhador.join(timeout=2)

    def _executar(self) -> None:
        com_iniciado = False
        locutor = None
        voz = None
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            com_iniciado = True
            locutor = win32com.client.Dispatch("SAPI.SpVoice")
            locutor.Rate, locutor.Volume = 2, 100
            for voz in locutor.GetVoices():
                descricao = voz.GetDescription().lower()
                if "portuguese" in descricao or "brasil" in descricao:
                    locutor.Voice = voz
                    break
            while not self._encerrada.is_set():
                texto = self.fila.get()
                if texto is None:
                    break
                # SAPI assíncrono permite interromper a fala durante o fechamento.
                locutor.Speak(texto, 1)
                while not locutor.WaitUntilDone(100):
                    if self._encerrada.is_set():
                        locutor.Speak("", 3)
                        return
        except Exception:
            # Fronteira COM: HRESULTs variam conforme a instalação do Windows.
            REGISTRO.exception("Voz SAPI indisponível.")
        finally:
            self.disponivel = False
            locutor = voz = None
            if com_iniciado:
                pythoncom.CoUninitialize()
