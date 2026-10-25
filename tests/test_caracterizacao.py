"""Comportamentos preservados na arquitetura atual, com provedores simulados."""

from unittest import TestCase
from unittest.mock import Mock, patch

from assistente.aplicacao.consultar_recomendacoes import (
    ConsultaRecomendacoes, ConsultarRecomendacoes, consultar_build,
)
from assistente.aplicacao.contratos import AmostrasDisponiveis
from assistente.apresentacao.formatacao import dados_build, formatar_painel
from assistente.dominio.counters import recomendar_itens_counter
from assistente.dominio.modelos import Funcao
from assistente.dominio.partida import calcular_metas
from assistente.infraestrutura import cliente_dota2protracker, cliente_opendota
from assistente.infraestrutura.fontes import ClienteDadosDota, FonteDota2ProTracker


class TestarBuildExistente(TestCase):
    def setUp(self) -> None:
        self.catalogo = {
            1: "Tango", 2: "Iron Branch", 3: "Power Treads",
            4: "Black King Bar", 5: "Butterfly", 6: "Magic Wand",
            7: "Observer Ward", 8: "Town Portal Scroll",
        }
        self.precos = {"Tango": 90, "Iron Branch": 50, "Magic Wand": 450}
        self.builds = [{
            "num_matches": 100, "num_wins": 60,
            "build_data": {
                "starting_items_new": [[[6, 1, 2, 2], {}], [[1, 2, 2, 7, 8], {}]],
                "anchor_items": [
                    {"raw_item_id": 3, "avg_minute": 11, "pr": 0.70},
                    {"raw_item_id": 4, "avg_minute": 12, "pr": 50},
                    {"raw_item_id": 5, "avg_minute": 30, "pr": 0.20},
                ],
            },
        }]
        self.remendos = [
            patch.object(cliente_dota2protracker, "obter_builds", return_value=self.builds),
            patch.object(cliente_opendota, "obter_catalogo_itens", return_value=self.catalogo),
            patch.object(cliente_opendota, "obter_catalogo_precos_itens", return_value=self.precos),
        ]
        for remendo in self.remendos:
            remendo.start()
            self.addCleanup(remendo.stop)

    def consultar(self) -> dict[str, object]:
        build, erro = consultar_build("Sven", Funcao.CARREGADOR, FonteDota2ProTracker())
        return dados_build("Sven", Funcao.CARREGADOR, build, erro)

    def test_saida_respeita_orcamento_quantidades_e_filtros(self) -> None:
        resultado = self.consultar()
        self.assertEqual(resultado["start"], "Tango → Iron Branch ×2")
        self.assertEqual(resultado["custo_saida"], 190)

    def test_core_respeita_percentuais_e_fronteiras(self) -> None:
        resultado = self.consultar()
        self.assertEqual(resultado["early"], "Boots of Speed → Power Treads")
        self.assertEqual(resultado["mid"], "Black King Bar")
        self.assertEqual(resultado["late"], "")
        self.assertTrue(any("Butterfly" in item for item in resultado["situacionais"]))

    def test_maior_amostra_e_escolhida(self) -> None:
        self.builds.insert(0, {"num_matches": 1, "name": "amostra menor"})
        resultado = self.consultar()
        self.assertEqual(resultado["amostra"], 100)
        self.assertIn("60.0%", resultado["observacao"])

    def test_sem_preco_confirmado_nao_inventa_saida(self) -> None:
        self.precos.clear()
        resultado = self.consultar()
        self.assertEqual(resultado["start"], "")
        self.assertIsNone(resultado["custo_saida"])

    def test_falha_d2pt_nao_substitui_fonte(self) -> None:
        with (
            patch.object(
                cliente_dota2protracker, "obter_builds",
                side_effect=cliente_dota2protracker.ErroDota2ProTracker("HTTP 403"),
            ),
            patch.object(cliente_opendota, "obter_item_popularity") as agregado,
        ):
            resultado = self.consultar()
        agregado.assert_not_called()
        self.assertEqual(resultado["fonte"], "")


class TestarCountersExistentes(TestCase):
    def test_inversao_e_ponderacao_por_jogos(self) -> None:
        respostas = [
            [{"hero_id": 18, "games_played": 100, "wins": 40}],
            [{"hero_id": 18, "games_played": 20, "wins": 10}],
        ]
        fonte = Mock()
        fonte.obter.return_value = AmostrasDisponiveis((), {})
        caso = ConsultarRecomendacoes(fonte, ClienteDadosDota())
        with (
            patch.object(cliente_opendota, "obter_benchmarks", return_value=None),
            patch.object(cliente_opendota, "obter_hero_stats", return_value=[]),
            patch.object(cliente_opendota, "obter_catalogo_heroes", return_value={18: {"roles": ["Carry"]}}),
            patch.object(cliente_opendota, "obter_matchups", side_effect=respostas),
        ):
            resultado = caso.executar(
                ConsultaRecomendacoes("Sven", Funcao.CARREGADOR, ("Axe",), "Lina")
            )
        texto = formatar_painel(resultado)
        self.assertIn("57.7%", texto)
        self.assertIn("120 jogos", texto)

    def test_suporte_recebe_defesa_em_vez_de_mkb(self) -> None:
        itens, _ = recomendar_itens_counter(ameaca="Phantom Assassin", modo="SUP")
        self.assertIn("Ghost Scepter", itens)
        self.assertNotIn("Monkey King Bar", itens)

    def test_offlane_tem_perfil_proprio(self) -> None:
        itens, _ = recomendar_itens_counter(ameaca="Phantom Assassin", modo="OFFLANE")
        self.assertEqual(itens, ["Heaven's Halberd", "Shiva's Guard", "Ghost Scepter"])

    def test_deteccao_nao_aparece_sem_invisibilidade(self) -> None:
        itens, _ = recomendar_itens_counter(ameaca="Zeus", modo="SUP")
        self.assertNotIn("Dust of Appearance", itens)
        self.assertNotIn("Gem of True Sight", itens)


class TestarMetasExistentes(TestCase):
    def test_percentil_e_interpolado(self) -> None:
        self.assertEqual(cliente_opendota._valor_percentil([
            {"percentile": 0.25, "value": 400},
            {"percentile": 0.75, "value": 600},
        ], 0.5), 500)

    def test_taxas_de_benchmark_nao_sao_multiplicadas_por_tempo(self) -> None:
        metas = calcular_metas(600, {"gpm": 500, "xpm": 600, "lh_min": 2}, "SUP")
        self.assertEqual(metas["gpm"], 500)
        self.assertEqual(metas["xpm"], 600)
        self.assertEqual(metas["lh"], 20)

    def test_pre_jogo_tem_metas_zeradas(self) -> None:
        self.assertTrue(all(valor == 0 for valor in calcular_metas(-30).values()))
