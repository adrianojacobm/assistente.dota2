import http.client
import json
import socket
import threading
from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from assistente.apresentacao.servidor_gsi import (
    LIMITE_CORPO_BYTES, DotaGSIHandler, ServidorGSI, interpretar_gsi,
)


def dados_gsi() -> dict:
    return {
        "map": {"matchid": "1", "clock_time": 100, "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"},
        "hero": {"name": "npc_dota_hero_antimage"}, "player": {"last_hits": 10},
    }


class TestarFronteiraGSI(TestCase):
    def executar_post(self, corpo: bytes, tamanho: str | None = None) -> DotaGSIHandler:
        handler = DotaGSIHandler.__new__(DotaGSIHandler)
        handler.headers = {"Content-Length": tamanho or str(len(corpo))}
        handler.rfile, handler.wfile = BytesIO(corpo), BytesIO()
        handler.server = SimpleNamespace(processar_atualizacao=Mock())
        handler._responder = Mock()
        handler.do_POST()
        return handler

    def test_json_invalido_recebe_400(self) -> None:
        handler = self.executar_post(b"{")
        self.assertEqual(handler._responder.call_args.args[0], 400)
        handler.server.processar_atualizacao.assert_not_called()

    def test_estrutura_invalida_recebe_400(self) -> None:
        for corpo in (b"[]", b'{"map": []}', b'{"player": "invalido"}'):
            self.assertEqual(self.executar_post(corpo)._responder.call_args.args[0], 400)

    def test_comprimento_invalido_e_corpo_grande_sao_rejeitados(self) -> None:
        self.assertEqual(self.executar_post(b"{}", "abc")._responder.call_args.args[0], 400)
        resposta = self.executar_post(b"{}", str(LIMITE_CORPO_BYTES + 1))._responder
        self.assertEqual(resposta.call_args.args[0], 413)

    def test_payload_valido_e_encaminhado_sem_global(self) -> None:
        handler = self.executar_post(json.dumps(dados_gsi()).encode())
        self.assertEqual(handler._responder.call_args.args[0], 200)
        atualizacao = handler.server.processar_atualizacao.call_args.args[0]
        self.assertEqual(atualizacao.heroi, "Anti-Mage")
        self.assertEqual(atualizacao.ultimos_golpes, 10)

    def test_valores_nao_finitos_sao_rejeitados(self) -> None:
        dados = dados_gsi()
        dados["map"]["clock_time"] = float("nan")
        with self.assertRaises(ValueError):
            interpretar_gsi(dados)

    def test_ausencia_de_partida_e_aceita(self) -> None:
        self.assertFalse(interpretar_gsi({}).em_partida)

    def test_servidor_real_local_recebe_post_e_encerra(self) -> None:
        atualizacoes = []
        servidor = ServidorGSI(("127.0.0.1", 0), atualizacoes.append)
        servidor.iniciar()
        conexao = http.client.HTTPConnection(*servidor.server_address, timeout=2)
        try:
            conexao.request("POST", "/", json.dumps(dados_gsi()), {"Content-Type": "application/json"})
            resposta = conexao.getresponse()
            self.assertEqual(resposta.status, 200)
            resposta.read()
            self.assertEqual(atualizacoes[0].heroi, "Anti-Mage")
        finally:
            conexao.close()
            servidor.encerrar()
        self.assertFalse(servidor._trabalhador.is_alive())

    def test_excesso_de_conexoes_recebe_503_sem_nova_thread(self) -> None:
        servidor = ServidorGSI(("127.0.0.1", 0), Mock(), maximo_conexoes=1)
        servidor._vagas.acquire()
        servidor.iniciar()
        conexao = http.client.HTTPConnection(*servidor.server_address, timeout=2)
        try:
            conexao.request("POST", "/", "{}")
            resposta = conexao.getresponse()
            self.assertEqual(resposta.status, 503)
            resposta.read()
            servidor.processar_atualizacao.assert_not_called()
        finally:
            conexao.close()
            servidor._vagas.release()
            servidor.encerrar()

    def test_fechamento_encerra_conexao_com_corpo_incompleto(self) -> None:
        servidor = ServidorGSI(("127.0.0.1", 0), Mock())
        aceitou = threading.Event()
        processar = servidor.process_request

        def registrar(conexao: socket.socket, endereco: tuple[str, int]) -> None:
            processar(conexao, endereco)
            aceitou.set()

        servidor.process_request = registrar
        servidor.iniciar()
        conexao = socket.create_connection(servidor.server_address, timeout=2)
        try:
            conexao.sendall(b"POST / HTTP/1.0\r\nContent-Length: 100\r\n\r\n{")
            self.assertTrue(aceitou.wait(timeout=2))
            servidor.encerrar()
            self.assertFalse(servidor._conexoes)
        finally:
            conexao.close()
            servidor.encerrar()
