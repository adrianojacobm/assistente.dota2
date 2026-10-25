"""Persistência JSON atômica; indisponibilidade de cache não impede o aplicativo."""

import json
import logging
import os
import tempfile
from pathlib import Path

REGISTRO = logging.getLogger(__name__)


def ler_json(caminho: Path) -> object | None:
    try:
        with caminho.open(encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as erro:
        REGISTRO.debug("JSON indisponível em %s: %s", caminho, erro)
        return None


def gravar_json(caminho: Path, dados: object) -> bool:
    temporario: Path | None = None
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=caminho.parent,
            prefix=f".{caminho.name}.", suffix=".tmp", delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            json.dump(dados, arquivo, ensure_ascii=False, allow_nan=False, indent=2)
        os.replace(temporario, caminho)
        return True
    except (OSError, TypeError, ValueError) as erro:
        REGISTRO.debug("Não foi possível gravar %s: %s", caminho, erro)
        return False
    finally:
        if temporario is not None:
            try:
                temporario.unlink(missing_ok=True)
            except OSError as erro:
                REGISTRO.debug("Temporário indisponível para limpeza: %s", erro)
