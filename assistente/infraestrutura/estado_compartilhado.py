import threading
import time
from collections.abc import Callable
from typing import cast

from assistente.dominio.partida import AtualizacaoPartida, InstantaneoPartida


class Estado:
    def __init__(self, sem_sinal_s: float = 90, relogio: Callable[[], float] = time.time) -> None:
        self._trava = threading.Lock()
        self.lock = self._trava  # Nome público usado pelo Estado anterior.
        self._relogio = relogio
        self._sem_sinal_s = sem_sinal_s
        self._dados: InstantaneoPartida = {
            "conectado": False, "em_partida": False, "tempo": -999,
            "heroi": "Aguardando...", "lh": 0, "dn": 0, "gpm": 0,
            "xpm": 0, "k": 0, "d": 0, "a": 0, "ultimo_post": 0.0, "sem_sinal": False,
        }

    def aplicar(self, atualizacao: AtualizacaoPartida, recebido_em: float) -> None:
        with self._trava:
            self._dados.update(conectado=True, em_partida=atualizacao.em_partida, ultimo_post=recebido_em)
            if atualizacao.em_partida:
                self._dados.update(
                    tempo=atualizacao.tempo, heroi=atualizacao.heroi,
                    lh=atualizacao.ultimos_golpes, dn=atualizacao.negacoes,
                    gpm=atualizacao.ouro_minuto, xpm=atualizacao.experiencia_minuto,
                    k=atualizacao.abates, d=atualizacao.mortes, a=atualizacao.assistencias,
                )

    def atualizar(self, **alteracoes: object) -> None:
        """Entrada de compatibilidade para consumidores do antigo Estado."""
        with self._trava:
            dados: dict[str, object] = dict(self._dados)
            for chave, valor in alteracoes.items():
                if chave not in dados:
                    raise KeyError(chave)
                esperado = type(dados[chave])
                if not isinstance(valor, esperado):
                    raise ValueError(f"Tipo inválido para {chave}.")
            dados.update(alteracoes)
            self._dados = cast(InstantaneoPartida, dados)

    def snapshot(self) -> InstantaneoPartida:
        with self._trava:
            dados = self._dados.copy()
        dados["sem_sinal"] = dados["conectado"] and self._relogio() - dados["ultimo_post"] > self._sem_sinal_s
        if dados["sem_sinal"]:
            dados["em_partida"] = False
        return dados
