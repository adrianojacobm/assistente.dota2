import json
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from assistente.aplicacao.consultar_recomendacoes import (
    ConsultaRecomendacoes, ConsultarRecomendacoes, ResultadoConsulta,
)
from assistente.aplicacao.contratos import AmostrasDisponiveis, ConsultaCancelada
from assistente.dominio.modelos import Funcao
from assistente.infraestrutura import cache_json
from assistente.infraestrutura import cliente_dota2protracker as d2pt
from assistente.infraestrutura import cliente_opendota as opendota
from assistente.infraestrutura.consultas_em_segundo_plano import ExecutorConsultas
from assistente.infraestrutura.fontes import FonteDota2ProTracker
from assistente.infraestrutura.preferencias_json import PreferenciasJson


class TestarCacheEClientes(TestCase):
    def setUp(self) -> None:
        diretorio = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
        temporario = tempfile.TemporaryDirectory(prefix="teste-dota-", dir=diretorio)
        self.addCleanup(temporario.cleanup)
        self.pasta = Path(temporario.name)
        remendos = [
            patch.object(d2pt, "CACHE_DIR", self.pasta / "d2pt"),
            patch.object(d2pt.time, "sleep"),
            patch.object(opendota, "_CACHE_DIR", str(self.pasta / "opendota")),
            patch.object(opendota, "_cache", {}),
            patch.object(requests, "get", side_effect=AssertionError("Rede externa proibida nos testes")),
        ]
        for remendo in remendos:
            remendo.start()
            self.addCleanup(remendo.stop)

    def test_json_atomico_nao_deixa_temporarios(self) -> None:
        caminho = self.pasta / "dados.json"
        self.assertTrue(cache_json.gravar_json(caminho, {"nome": "Lótus"}))
        self.assertEqual(cache_json.ler_json(caminho), {"nome": "Lótus"})
        self.assertEqual(list(self.pasta.glob("*.tmp")), [])

    def test_falha_de_gravacao_preserva_arquivo_anterior(self) -> None:
        caminho = self.pasta / "dados.json"
        cache_json.gravar_json(caminho, {"antes": True})
        with patch.object(cache_json.os, "replace", side_effect=PermissionError("bloqueado")):
            self.assertFalse(cache_json.gravar_json(caminho, {"depois": True}))
        self.assertEqual(cache_json.ler_json(caminho), {"antes": True})
        self.assertEqual(list(self.pasta.glob("*.tmp")), [])

    def test_cache_opendota_com_estrutura_errada_e_ignorado(self) -> None:
        caminho = Path(opendota._arquivo_cache("exemplo"))
        cache_json.gravar_json(caminho, [])
        self.assertIsNone(opendota._ler_cache_disco("exemplo", 60))

    def test_cache_opendota_mantem_formato_timestamp_data(self) -> None:
        opendota._gravar_cache_disco("exemplo", 100, [1, 2])
        with patch.object(opendota.time, "time", return_value=101):
            self.assertEqual(opendota._ler_cache_disco("exemplo", 60), (100, [1, 2]))

    def test_cache_expirado_nao_e_usado_em_falha_d2pt(self) -> None:
        caminho = d2pt.CACHE_DIR / "exemplo.json"
        cache_json.gravar_json(caminho, [{"num_matches": 100}])
        with patch.object(d2pt.time, "time", return_value=caminho.stat().st_mtime + 2000), \
             patch.object(requests, "get", return_value=Mock(status_code=403)):
            with self.assertRaises(d2pt.ErroDota2ProTracker):
                d2pt.obter_json("/exemplo", "exemplo")

    def test_cache_sem_permissao_nao_impede_d2pt(self) -> None:
        resposta = Mock(status_code=200)
        resposta.json.return_value = []
        with patch.object(d2pt, "gravar_json", return_value=False), \
             patch.object(requests, "get", return_value=resposta):
            self.assertEqual(d2pt.obter_json("/exemplo", "exemplo"), [])
        resposta.close.assert_called_once()

    def test_d2pt_reutiliza_cache_em_chamadas_concorrentes(self) -> None:
        resposta = Mock(status_code=200)
        resposta.json.return_value = [{"num_matches": 100}]
        barreira = threading.Barrier(4)

        def consultar(_: int) -> object:
            barreira.wait(timeout=2)
            return d2pt.obter_json("/exemplo", "exemplo")
        with (
            patch.object(requests, "get", return_value=resposta) as obter,
            ThreadPoolExecutor(max_workers=4) as executor,
        ):
            resultados = list(executor.map(consultar, range(4)))
        self.assertEqual(obter.call_count, 1)
        self.assertEqual(len(resultados), 4)

    def test_opendota_reutiliza_cache_em_chamadas_concorrentes(self) -> None:
        resposta = Mock(status_code=200)
        resposta.json.return_value = [1, 2]
        with (
            patch.object(requests, "get", return_value=resposta) as obter,
            ThreadPoolExecutor(max_workers=4) as executor,
        ):
            resultados = list(executor.map(
                lambda _: opendota._get("/exemplo", cache_key="exemplo", ttl=60), range(4),
            ))
        self.assertEqual(obter.call_count, 1)
        self.assertEqual(resultados, [[1, 2]] * 4)

    def test_d2pt_rejeita_json_e_formato_invalido(self) -> None:
        resposta = Mock(status_code=200)
        resposta.json.side_effect = ValueError("HTML")
        with patch.object(requests, "get", return_value=resposta), self.assertRaises(d2pt.ErroDota2ProTracker):
            d2pt.obter_json("/exemplo", "exemplo")
        with (
            patch.object(d2pt, "obter_json", return_value={"error": "bloqueado"}),
            self.assertRaises(d2pt.ErroDota2ProTracker),
        ):
            d2pt.obter_builds(18, "CARRY")

    def test_d2pt_aceita_variantes_estruturadas(self) -> None:
        variantes = (
            [{"num_matches": 1}], {"builds": [{"num_matches": 1}]},
            {"data": [{"num_matches": 1}]}, {"num_matches": 1},
        )
        for dados in variantes:
            with self.subTest(dados=dados), patch.object(d2pt, "obter_json", return_value=dados):
                self.assertEqual(d2pt.obter_builds(18, "CARRY"), [{"num_matches": 1}])

    def test_preferencias_invalidas_nao_quebram_carregamento(self) -> None:
        caminho = self.pasta / "preferencias.json"
        cache_json.gravar_json(caminho, {"posicoes": None, "visibilidade": []})
        self.assertEqual(PreferenciasJson(caminho).carregar(), {"posicoes": {}, "visibilidade": {}})

    def test_preferencias_preservam_posicoes_e_formato(self) -> None:
        caminho = self.pasta / "preferencias.json"
        dados = {"posicoes": {"build": {"x": 0, "y": -7}}, "visibilidade": {"build": False}}
        preferencias = PreferenciasJson(caminho)
        self.assertTrue(preferencias.salvar(dados))
        self.assertEqual(preferencias.carregar(), dados)
        self.assertEqual(json.loads(caminho.read_text(encoding="utf-8")), dados)

    def test_percentil_descarta_valores_nao_finitos(self) -> None:
        self.assertIsNone(opendota._valor_percentil([{"percentile": 0.5, "value": float("inf")}], 0.5))

    def test_cache_d2pt_invalido_nao_impede_consulta_valida(self) -> None:
        cache_json.gravar_json(d2pt.CACHE_DIR / "builds_18_pos1.json", {"error": "inválido"})
        resposta = Mock(status_code=200)
        resposta.json.return_value = [{"num_matches": 100}]
        with patch.object(requests, "get", return_value=resposta) as obter:
            self.assertEqual(d2pt.obter_builds(18, "CARRY"), [{"num_matches": 100}])
        obter.assert_called_once()

    def test_cache_opendota_com_tipo_errado_e_reconsultado(self) -> None:
        opendota._gravar_cache_disco("constants_items", opendota.time.time(), [])
        resposta = Mock(status_code=200)
        resposta.json.return_value = {"tango": {"id": 1, "dname": "Tango", "cost": 90}}
        with patch.object(requests, "get", return_value=resposta) as obter:
            self.assertEqual(opendota.obter_catalogo_itens(), {1: "Tango"})
        obter.assert_called_once()

    def test_timeout_d2pt_e_especifico_e_tem_timeout_configurado(self) -> None:
        with patch.object(requests, "get", side_effect=requests.Timeout("tempo excedido")) as obter:
            with self.assertRaises(d2pt.ErroDota2ProTracker):
                d2pt.obter_builds(18, "CARRY")
        self.assertEqual(obter.call_args.kwargs["timeout"], 20)

    def test_opendota_fecha_resposta_invalida_sem_cachear(self) -> None:
        resposta = Mock(status_code=200)
        resposta.json.side_effect = ValueError("HTML")
        with (
            patch.object(requests, "get", return_value=resposta),
            self.assertLogs(opendota.REGISTRO, "WARNING"),
        ):
            self.assertIsNone(opendota._get("/exemplo", cache_key="exemplo", ttl=60))
        resposta.close.assert_called_once()
        self.assertNotIn("exemplo", opendota._cache)

    def test_cancelamento_apos_d2pt_nao_inicia_catalogos(self) -> None:
        verificar = Mock(side_effect=[None, ConsultaCancelada()])
        with (
            patch.object(d2pt, "obter_builds", return_value=[{"num_matches": 100}]),
            patch.object(opendota, "obter_catalogo_itens") as catalogo,
        ):
            with self.assertRaises(ConsultaCancelada):
                FonteDota2ProTracker().obter(18, Funcao.CARREGADOR, verificar)
        catalogo.assert_not_called()


class TestarExecutorLimitado(TestCase):
    def test_substitui_pendentes_e_descarta_resultado_antigo(self) -> None:
        iniciado, liberar = threading.Event(), threading.Event()
        consultas_executadas = []
        def consultar(
            consulta: ConsultaRecomendacoes, verificar_ativa: Callable[[], None],
        ) -> ResultadoConsulta:
            consultas_executadas.append(consulta.heroi)
            if len(consultas_executadas) == 1:
                iniciado.set()
                self.assertTrue(liberar.wait(timeout=3))
            return ResultadoConsulta(consulta)
        executor = ExecutorConsultas(consultar)
        self.addCleanup(executor.encerrar)
        self.addCleanup(liberar.set)
        executor.solicitar(ConsultaRecomendacoes("primeiro", Funcao.CARREGADOR))
        self.assertTrue(iniciado.wait(timeout=2))
        for indice in range(20):
            ultimo = executor.solicitar(ConsultaRecomendacoes(str(indice), Funcao.CARREGADOR))
        liberar.set()
        identificador, resultado = executor._resultados.get(timeout=3)
        self.assertEqual(identificador, ultimo)
        self.assertEqual(resultado.consulta.heroi, "19")
        self.assertEqual(consultas_executadas, ["primeiro", "19"])

    def test_fechamento_descarta_trabalho_em_andamento(self) -> None:
        iniciado, liberar = threading.Event(), threading.Event()
        def consultar(
            consulta: ConsultaRecomendacoes, verificar_ativa: Callable[[], None],
        ) -> ResultadoConsulta:
            iniciado.set()
            liberar.wait(timeout=3)
            return ResultadoConsulta(consulta)
        executor = ExecutorConsultas(consultar)
        self.addCleanup(liberar.set)
        executor.solicitar(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR))
        self.assertTrue(iniciado.wait(timeout=2))
        executor.encerrar()
        liberar.set()
        executor._trabalhador.join(timeout=2)
        self.assertFalse(executor._trabalhador.is_alive())
        self.assertEqual(executor.obter_resultados(), [])
        with self.assertRaises(RuntimeError):
            executor.solicitar(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR))

    def test_selecao_nova_interrompe_etapas_http_da_consulta_obsoleta(self) -> None:
        iniciado, liberar = threading.Event(), threading.Event()
        fonte, dados = Mock(), Mock()
        fonte.obter.return_value = AmostrasDisponiveis((), {})
        dados.obter_benchmarks.return_value = None

        def obter_amostras(*args: object) -> AmostrasDisponiveis:
            if args[0] == 18:
                iniciado.set()
                self.assertTrue(liberar.wait(timeout=3))
            return AmostrasDisponiveis((), {})

        fonte.obter.side_effect = obter_amostras
        executor = ExecutorConsultas(ConsultarRecomendacoes(fonte, dados).executar)
        self.addCleanup(executor.encerrar)
        self.addCleanup(liberar.set)
        executor.solicitar(ConsultaRecomendacoes("Sven", Funcao.CARREGADOR, ameaca="Axe"))
        self.assertTrue(iniciado.wait(timeout=2))
        ultimo = executor.solicitar(ConsultaRecomendacoes("Lina", Funcao.MEIO))
        liberar.set()
        identificador, _ = executor._resultados.get(timeout=3)
        self.assertEqual(identificador, ultimo)
        dados.obter_benchmarks.assert_called_once_with(25, Funcao.MEIO)
        dados.obter_confrontos.assert_not_called()
