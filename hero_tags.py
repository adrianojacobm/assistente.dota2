# -*- coding: utf-8 -*-
"""Compatibilidade com a versão antiga; counters por tags genéricas foram desativados.

As antigas regras sugeriam itens por categorias amplas de heróis (por exemplo,
Blade Mail contra qualquer inimigo com burst físico), sem verificar função ou
partidas da matchup. O projeto agora usa matchup_engine.py, que consulta partidas
parseadas e se abstém quando a amostra não é suficiente.
"""


def tags_do_heroi(nome_heroi: str, roles_oficiais=None) -> set:
    """Mantida apenas para compatibilidade; não gera tags para recomendar itens."""
    return set()


def itens_situacionais(tags: set, modo: str):
    """Não sugere counters genéricos. A fonte válida é a análise de partidas."""
    return [], []
