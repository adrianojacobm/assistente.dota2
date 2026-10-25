from dataclasses import FrozenInstanceError
from unittest import TestCase

from assistente.dominio.catalogo import IDS_HEROIS, formatar_nome_heroi
from assistente.dominio.modelos import BuildObservada, Confronto, Funcao, ItemObservado, ItemQuantidade
from assistente.dominio.partida import calcular_metas
from assistente.dominio.recomendacoes import classificar_counter_picks, montar_build
from assistente.infraestrutura.fontes import normalizar_amostras


class TestarRegrasDoDominio(TestCase):
    def test_aliases_gsi_correspondem_ao_catalogo(self) -> None:
        for identificador, nome in (
            ("antimage", "Anti-Mage"), ("queenofpain", "Queen of Pain"),
            ("vengefulspirit", "Vengeful Spirit"), ("rattletrap", "Clockwerk"),
        ):
            with self.subTest(identificador=identificador):
                recebido = formatar_nome_heroi(f"npc_dota_hero_{identificador}")
                self.assertEqual(recebido, nome)
                self.assertIn(recebido, IDS_HEROIS)

    def test_modelos_imutaveis_e_quantidade_valida(self) -> None:
        item = ItemQuantidade("Tango", 2)
        with self.assertRaises(FrozenInstanceError):
            item.quantidade = 3
        with self.assertRaises(ValueError):
            ItemQuantidade("Tango", 0)

    def test_rejeita_estatisticas_nao_finitas(self) -> None:
        for numero in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(numero=numero), self.assertRaises(ValueError):
                ItemObservado("Magic Wand", numero, 0.6)

    def test_metas_usam_estimativa_para_infinito(self) -> None:
        esperado = calcular_metas(600)
        for numero in (float("inf"), float("nan"), -1):
            self.assertEqual(calcular_metas(600, {"gpm": numero})["gpm"], esperado["gpm"])

    def test_benchmark_com_formato_errado_preserva_estimativa_legada(self) -> None:
        esperado = calcular_metas(600)
        for benchmark in ("inválido", [500], None):
            with self.subTest(benchmark=benchmark):
                self.assertEqual(calcular_metas(600, benchmark), esperado)

    def test_fronteiras_das_fases(self) -> None:
        amostra = BuildObservada("exemplo", 10, itens=(
            ItemObservado("A", 11.99, 0.5), ItemObservado("B", 12, 0.5),
            ItemObservado("C", 29.99, 0.5), ItemObservado("D", 30, 0.5),
        ))
        build = montar_build("Sven", Funcao.CARREGADOR, [amostra], {})
        self.assertEqual(build.inicio, ("A",))
        self.assertEqual(build.meio, ("B", "C"))
        self.assertEqual(build.final, ("D",))

    def test_item_inicial_nao_reaparece_na_progressao(self) -> None:
        amostra = BuildObservada("exemplo", 10, (("Magic Wand",),), (ItemObservado("Magic Wand", 5, 0.7),))
        build = montar_build("Sven", Funcao.CARREGADOR, [amostra], {"Magic Wand": 450})
        self.assertEqual(build.saida, (ItemQuantidade("Magic Wand", 1),))
        self.assertEqual(build.inicio, ())

    def test_bota_inicial_nao_e_injetada_novamente(self) -> None:
        amostra = BuildObservada(
            "exemplo", 10, (("Boots of Speed",),), (ItemObservado("Power Treads", 5, 0.7),),
        )
        build = montar_build("Sven", Funcao.CARREGADOR, [amostra], {"Boots of Speed": 500})
        self.assertEqual(build.inicio, ("Power Treads",))

    def test_desempate_preserva_ordem_da_fonte_sem_mutar_entrada(self) -> None:
        amostras = [BuildObservada("primeira", 100), BuildObservada("segunda", 100)]
        build = montar_build("Sven", Funcao.CARREGADOR, amostras, {})
        self.assertEqual(build.observada.nome, "primeira")
        self.assertEqual([amostra.nome for amostra in amostras], ["primeira", "segunda"])

    def test_confronto_invalido_nao_produz_percentuais_absurdos(self) -> None:
        with self.assertRaises(ValueError):
            Confronto(18, 10, 11)

    def test_filtro_de_arquetipos_preserva_offlane(self) -> None:
        candidatos = classificar_counter_picks(
            {"Lina": [Confronto(2, 100, 40)]}, "Lina", Funcao.ROTA_DIFICIL,
            {}, {2: ("Initiator",)},
        )
        self.assertEqual(candidatos[0].heroi, "Axe")

    def test_hard_support_nao_vira_carry(self) -> None:
        self.assertEqual(Funcao.SUPORTE_PRINCIPAL.perfil_counter, "SUP")
        self.assertEqual(Funcao.SUPORTE_PRINCIPAL.posicao, 5)

    def test_normalizacao_descarta_numeros_nao_finitos_da_fonte(self) -> None:
        amostras = normalizar_amostras([{"num_matches": 10, "anchor_items": [
            {"raw_item_id": 1, "avg_minute": float("inf"), "pr": 0.9},
            {"raw_item_id": 2, "avg_minute": 10, "pr": float("nan")},
        ]}], {1: "Magic Wand", 2: "Power Treads"})
        self.assertEqual(amostras[0].itens, ())

    def test_pacote_com_id_desconhecido_nao_vira_combo_incompleto(self) -> None:
        amostras = normalizar_amostras([{"num_matches": 10, "starting_items_new": [
            [[1, 999], {}], [[1, 1], {}],
        ]}], {1: "Tango"})
        build = montar_build("Sven", Funcao.CARREGADOR, amostras, {"Tango": 90})
        self.assertEqual(build.saida, (ItemQuantidade("Tango", 2),))
        self.assertEqual(build.custo_saida, 180)
