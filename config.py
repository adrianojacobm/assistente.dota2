# -*- coding: utf-8 -*-
"""Configurações centrais do Assistente de Dota 2."""

PORTA_GSI = 4000
SEM_SINAL_S = 90
ANTECEDENCIA_MIN, ANTECEDENCIA_MAX = 5, 55

HEADERS_API = {"User-Agent": "AssistenteDota2/1.0 (uso pessoal)"}
OPENDOTA_BASE = "https://api.opendota.com/api"

INTERVALO_MIN_ENTRE_CHAMADAS_S = 1.1
TIMEOUT_REQUEST_S = 6

# Itens listados por fase. Start é maior porque consumíveis e componentes iniciais
# são compras legítimas, não devem ser removidos como componentes de receita.
MAX_ITENS_START = 12
MAX_ITENS_EARLY = 8
MAX_ITENS_MID = 6
MAX_ITENS_LATE = 6

CACHE_TTL_ITEM_POPULARITY_S = 60 * 30
CACHE_TTL_MATCHUPS_S = 60 * 30
CACHE_TTL_CATALOGO_S = 60 * 60 * 6
CACHE_TTL_BENCHMARKS_S = 60 * 60

MIN_JOGOS_MATCHUP = 15
PERCENTIL_BENCHMARK = 0.50  # mediana (P50) real retornada pela OpenDota

# Análise de itens de matchup: limitada para respeitar a API pública/rate-limit.
# Build baseada nas últimas partidas profissionais realmente parseadas.
PARTIDAS_PRO_POR_BUILD = 100
TAMANHO_PAGINA_PARTIDAS_HEROI = 100
MAX_HISTORICO_HEROI_SCAN = 5000  # limite de segurança para paginação de partidas do herói
ORCAMENTO_SAIDA_INICIAL = 600
PERCENTUAL_CORE_ITEM = 0.50  # item core só aparece na progressão principal se ocorrer em >= 50% dos jogos
MIN_PERCENTUAL_SITUACIONAL = 0.15

# Legados mantidos por compatibilidade com configurações antigas.
MAX_PARTIDAS_MATCHUP_SCAN = 20
MAX_PARTIDAS_RANKED_SCAN = 24
MIN_RANKED_AVERAGE_TIER = 80  # Immortal (OpenDota rank tier 80–85)
MIN_PARTIDAS_MATCHUP_ITENS = 2
MIN_PARTIDAS_ROLE_BUILD = 3
CACHE_TTL_PARTIDAS_HEROI_S = 60 * 60 * 6
CACHE_TTL_DETALHE_PARTIDA_S = 60 * 60 * 24
