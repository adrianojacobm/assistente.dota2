"""Ponto de entrada do assistente desktop de Dota 2."""

import logging


def main() -> int:
    from assistente.composicao import executar

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return executar()


if __name__ == "__main__":
    raise SystemExit(main())
