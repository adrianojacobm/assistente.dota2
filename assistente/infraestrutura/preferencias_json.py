import logging
from pathlib import Path

from assistente.aplicacao.contratos import Preferencias

from .cache_json import gravar_json, ler_json

REGISTRO = logging.getLogger(__name__)
ARQUIVO_PREFERENCIAS = Path(__file__).resolve().parents[2] / "preferencias_overlay.json"


class PreferenciasJson:
    def __init__(self, caminho: Path = ARQUIVO_PREFERENCIAS) -> None:
        self._caminho = caminho

    def carregar(self) -> Preferencias:
        resultado: Preferencias = {"posicoes": {}, "visibilidade": {}}
        dados = ler_json(self._caminho)
        if not isinstance(dados, dict):
            return resultado
        posicoes = dados.get("posicoes")
        if isinstance(posicoes, dict):
            for chave, posicao in posicoes.items():
                if not isinstance(chave, str) or not isinstance(posicao, dict):
                    continue
                try:
                    x, y = int(posicao["x"]), int(posicao["y"])
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
                resultado["posicoes"][chave] = {"x": x, "y": y}
        visibilidade = dados.get("visibilidade")
        if isinstance(visibilidade, dict):
            resultado["visibilidade"] = {
                chave: valor for chave, valor in visibilidade.items()
                if isinstance(chave, str) and isinstance(valor, bool)
            }
        return resultado

    def salvar(self, preferencias: Preferencias) -> bool:
        sucesso = gravar_json(self._caminho, preferencias)
        if not sucesso:
            REGISTRO.warning("Não foi possível salvar as preferências em %s.", self._caminho)
        return sucesso
