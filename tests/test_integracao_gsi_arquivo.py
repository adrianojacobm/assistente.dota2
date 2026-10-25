from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from assistente.aplicacao.configurar_integracao_gsi import (
    ConfigurarIntegracaoGSI,
    ConfirmacaoReparoGSI,
    EstadoConfiguracaoGSI,
)
from assistente.aplicacao.contratos import ConsultaCancelada, JogoNaoEncontrado
from assistente.infraestrutura import integracao_gsi_arquivo as modulo
from assistente.infraestrutura.integracao_gsi_arquivo import (
    NOME_ARQUIVO_GSI,
    IntegracaoGSIArquivo,
    gerar_configuracao_gsi,
)
from assistente.infraestrutura.steam import InstalacaoDota, interpretar_vdf


class TestarArquivoGSI(TestCase):
    def setUp(self) -> None:
        self.temporario = TemporaryDirectory(prefix="assistente-gsi-")
        self.addCleanup(self.temporario.cleanup)
        self.pasta = Path(self.temporario.name)
        self.jogo = self.pasta / "Dota ação"
        self.jogo.mkdir()
        self.localizar = Mock(return_value=InstalacaoDota(self.jogo, self.jogo / "dota2", ()))
        self.integracao = IntegracaoGSIArquivo(self.localizar, 4000)
        self.caso = ConfigurarIntegracaoGSI(self.integracao)
        self.caminho = self.jogo / "game/dota/cfg/gamestate_integration" / NOME_ARQUIVO_GSI

    def gravar(self, conteudo: bytes) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_bytes(conteudo)

    def preparar_conflito(self) -> ConfirmacaoReparoGSI:
        self.gravar(b'"Configuracao manual" { "uri" "http://127.0.0.1:9999" }')
        resultado = self.integracao.verificar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.CONFLITO)
        assert resultado.reparo is not None
        return resultado.reparo

    def test_verificacao_ausente_nao_cria_nenhuma_pasta(self) -> None:
        resultado = self.integracao.verificar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.AUSENTE)
        self.assertEqual(resultado.caminho, str(self.caminho))
        self.assertFalse(self.caminho.parent.exists())
        self.localizar.assert_called_once()

    def test_criacao_usa_porta_configurada_e_campos_consumidos_pelo_assistente(self) -> None:
        integracao = IntegracaoGSIArquivo(self.localizar, 45231)
        resultado = integracao.configurar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.CRIADO)
        dados = interpretar_vdf(self.caminho.read_text(encoding="utf-8"))["Assistente Dota 2"]
        self.assertEqual(dados["uri"], "http://127.0.0.1:45231")
        self.assertEqual(dados["data"], dict.fromkeys(("provider", "map", "player", "hero"), "1"))
        self.assertEqual(dados["heartbeat"], "30.0")
        self.assertEqual(integracao.verificar().estado, EstadoConfiguracaoGSI.CONFIGURADO)
        self.assertIsNone(resultado.copia_seguranca)
        self.localizar.assert_called_with()

    def test_portas_invalidas_sao_rejeitadas_sem_descoberta_ou_gravacao(self) -> None:
        for porta in (0, -1, 65536, True, 4.5, "4000"):
            with self.subTest(porta=porta), self.assertRaises(ValueError):
                IntegracaoGSIArquivo(self.localizar, porta)
        self.localizar.assert_not_called()
        self.assertFalse(self.caminho.parent.exists())

    def test_arquivo_compativel_preserva_bytes_personalizacoes_e_data_de_modificacao(self) -> None:
        texto = gerar_configuracao_gsi(4000).replace(
            '"Assistente Dota 2"', '"Meu nome personalizado"',
        ).replace('"30.0"', '"10.0"').replace(
            '"http://127.0.0.1:4000"', '"http://127.0.0.1:4000/"',
        ).replace('"hero" "1"', '"hero" "1"\n        "items" "1"')
        original = b"\xef\xbb\xbf" + ("// Meu comentário\n" + texto).encode("utf-8")
        self.gravar(original)
        data = self.caminho.stat().st_mtime_ns
        for _ in range(2):
            self.assertEqual(self.integracao.configurar().estado, EstadoConfiguracaoGSI.CONFIGURADO)
        self.assertEqual(self.caminho.read_bytes(), original)
        self.assertEqual(self.caminho.stat().st_mtime_ns, data)
        self.assertEqual(list(self.caminho.parent.iterdir()), [self.caminho])

    def test_conflito_nao_e_sobrescrito_sem_confirmacao(self) -> None:
        self.preparar_conflito()
        original = self.caminho.read_bytes()
        resultado = self.integracao.configurar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.CONFLITO)
        self.assertIn("mesma porta", resultado.erro)
        self.assertEqual(self.caminho.read_bytes(), original)
        self.assertEqual(list(self.caminho.parent.iterdir()), [self.caminho])

    def test_arquivo_invalido_ou_ambiguo_exige_confirmacao(self) -> None:
        valido = gerar_configuracao_gsi(4000)
        variantes = (
            b"\xff", b"", b'"chave" {', b'"chave" "valor"',
            valido.replace('"hero" "1"', '"hero" "0"').encode(),
            valido.replace('"timeout" "5.0"', '"timeout" "nan"').encode(),
            valido.replace('"buffer" "0.1"', '"buffer" "-1"').encode(),
            valido.replace('"heartbeat" "30.0"', '"heartbeat" "0"').encode(),
            valido.replace('"map" "1"', '"map" "0"\n        "map" "1"').encode(),
            valido.replace('"map" "1"', '"map" "1"\n        "MAP" "0"').encode(),
        )
        for conteudo in variantes:
            with self.subTest(conteudo=conteudo):
                self.gravar(conteudo)
                resultado = self.integracao.configurar()
                self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.CONFLITO)
                self.assertIsNotNone(resultado.reparo)
                self.assertEqual(self.caminho.read_bytes(), conteudo)

    def test_reparo_guarda_backup_exato_sem_modificar_outros_arquivos(self) -> None:
        confirmacao = self.preparar_conflito()
        original = self.caminho.read_bytes()
        outro = self.caminho.with_name("gamestate_integration_outro.cfg")
        outro.write_bytes(b"Integracao de outro aplicativo")
        resultado = self.integracao.configurar(confirmacao)
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.REPARADO)
        self.assertEqual(Path(resultado.copia_seguranca).read_bytes(), original)
        self.assertEqual(Path(resultado.copia_seguranca).suffix, ".bak")
        self.assertEqual(self.caminho.read_text(encoding="utf-8"), gerar_configuracao_gsi(4000))
        self.assertEqual(outro.read_bytes(), b"Integracao de outro aplicativo")
        self.assertFalse(list(self.caminho.parent.glob("*.tmp")))
        self.assertEqual(len(list(self.caminho.parent.glob("*.cfg"))), 2)

    def test_edicao_apos_confirmacao_exige_nova_confirmacao(self) -> None:
        confirmacao = self.preparar_conflito()
        alterado = b'"Outra configuracao" { "uri" "http://127.0.0.1:2222" }'
        self.caminho.write_bytes(alterado)
        resultado = self.integracao.configurar(confirmacao)
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.CONFLITO)
        self.assertNotEqual(resultado.reparo, confirmacao)
        self.assertEqual(self.caminho.read_bytes(), alterado)
        self.assertFalse(list(self.caminho.parent.glob("*.bak")))

    def test_arquivo_removido_apos_confirmacao_nao_e_recriado_sem_nova_acao(self) -> None:
        confirmacao = self.preparar_conflito()
        self.caminho.unlink()
        self.assertEqual(self.integracao.configurar(confirmacao).estado, EstadoConfiguracaoGSI.AUSENTE)
        self.assertFalse(self.caminho.exists())

    def test_mudanca_de_instalacao_invalida_a_confirmacao(self) -> None:
        confirmacao = self.preparar_conflito()
        outra = self.pasta / "Outra instalação"
        outra.mkdir()
        self.localizar.return_value = InstalacaoDota(outra, outra / "dota2", ())
        resultado = self.integracao.configurar(confirmacao)
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.AUSENTE)
        self.assertTrue(self.caminho.exists())
        self.assertFalse((outra / "game").exists())

    def test_criacao_concorrente_nao_e_sobrescrita(self) -> None:
        criar = modulo._criar_exclusivo
        concorrente = b'"Outra configuracao" { "uri" "http://127.0.0.1:2222" }'

        def criar_apos_outro(caminho: Path, conteudo: bytes) -> None:
            caminho.write_bytes(concorrente)
            criar(caminho, conteudo)

        with patch.object(modulo, "_criar_exclusivo", side_effect=criar_apos_outro):
            resultado = self.integracao.configurar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.CONFLITO)
        self.assertEqual(self.caminho.read_bytes(), concorrente)

    def test_edicao_durante_reparo_preserva_arquivo_e_informa_backup(self) -> None:
        confirmacao = self.preparar_conflito()
        original = self.caminho.read_bytes()
        alterado = b'"Configuracao nova" { "uri" "http://127.0.0.1:2222" }'
        chamadas = 0

        def verificar_ativa() -> None:
            nonlocal chamadas
            chamadas += 1
            if chamadas == 3:
                self.caminho.write_bytes(alterado)

        resultado = self.integracao.configurar(confirmacao, verificar_ativa)
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.CONFLITO)
        self.assertEqual(self.caminho.read_bytes(), alterado)
        self.assertEqual(Path(resultado.copia_seguranca).read_bytes(), original)
        self.assertFalse(list(self.caminho.parent.glob("*.tmp")))

    def test_falha_na_substituicao_preserva_original_e_backup(self) -> None:
        confirmacao = self.preparar_conflito()
        original = self.caminho.read_bytes()
        with patch.object(modulo.os, "replace", side_effect=PermissionError("Somente leitura")):
            resultado = self.caso.executar(confirmacao)
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertEqual(self.caminho.read_bytes(), original)
        self.assertEqual(Path(resultado.copia_seguranca).read_bytes(), original)
        self.assertFalse(list(self.caminho.parent.glob("*.tmp")))

    def test_falha_no_backup_nao_altera_arquivo(self) -> None:
        confirmacao = self.preparar_conflito()
        original = self.caminho.read_bytes()
        with patch.object(modulo.tempfile, "mkstemp", side_effect=OSError("Disco cheio")):
            resultado = self.caso.executar(confirmacao)
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertEqual(self.caminho.read_bytes(), original)
        self.assertEqual(list(self.caminho.parent.iterdir()), [self.caminho])

    def test_falha_ao_preparar_novo_conteudo_preserva_backup_e_remove_temporario(self) -> None:
        confirmacao = self.preparar_conflito()
        original = self.caminho.read_bytes()
        fsync = modulo.os.fsync
        chamadas = 0

        def sincronizar(descritor: int) -> None:
            nonlocal chamadas
            chamadas += 1
            if chamadas == 2:
                raise OSError("Disco cheio")
            fsync(descritor)

        with patch.object(modulo.os, "fsync", side_effect=sincronizar):
            resultado = self.caso.executar(confirmacao)
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertEqual(self.caminho.read_bytes(), original)
        self.assertEqual(Path(resultado.copia_seguranca).read_bytes(), original)
        self.assertFalse(list(self.caminho.parent.glob("*.tmp")))

    def test_falha_de_gravacao_remove_apenas_novo_arquivo_incompleto(self) -> None:
        with patch.object(modulo.os, "fsync", side_effect=OSError("Disco cheio")):
            resultado = self.caso.executar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertFalse(self.caminho.exists())
        self.assertIn("Disco cheio", resultado.erro)

    def test_leitura_sem_permissao_informa_caminho_sem_impedir_demais_recursos(self) -> None:
        with patch.object(modulo, "_ler_arquivo", side_effect=PermissionError("Sem permissão")):
            resultado = self.caso.verificar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertEqual(resultado.caminho, str(self.caminho))
        self.assertIn("Sem permissão", resultado.erro)

    def test_ausencia_do_jogo_e_erro_especifico_sem_gravacao(self) -> None:
        self.localizar.side_effect = JogoNaoEncontrado("Jogo não encontrado.")
        resultado = self.caso.executar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertIn("Jogo não encontrado", resultado.erro)
        self.assertFalse(self.caminho.parent.exists())

    def test_arquivo_grande_nao_e_substituido(self) -> None:
        conteudo = b"x" * (modulo.LIMITE_CONFIGURACAO_BYTES + 1)
        self.gravar(conteudo)
        resultado = self.caso.executar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertEqual(self.caminho.read_bytes(), conteudo)
        self.assertIsNone(resultado.reparo)

    def test_destino_nao_regular_e_recusado_sem_tentar_ler(self) -> None:
        self.caminho.mkdir(parents=True)
        resultado = self.caso.executar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertTrue(self.caminho.is_dir())

    def test_link_de_arquivo_nao_e_seguido_nem_substituido(self) -> None:
        alvo = self.pasta / "arquivo-pessoal.cfg"
        alvo.write_bytes(b"Preservar")
        self.caminho.parent.mkdir(parents=True)
        try:
            self.caminho.symlink_to(alvo)
        except (OSError, NotImplementedError) as erro:
            self.skipTest(f"Criação de links indisponível neste sistema: {erro}")
        resultado = self.caso.executar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertTrue(self.caminho.is_symlink())
        self.assertEqual(alvo.read_bytes(), b"Preservar")

    def test_pasta_redirecionada_para_fora_do_jogo_e_recusada(self) -> None:
        externa = self.pasta / "pasta-pessoal"
        externa.mkdir()
        pai = self.jogo / "game/dota"
        pai.mkdir(parents=True)
        try:
            (pai / "cfg").symlink_to(externa, target_is_directory=True)
        except (OSError, NotImplementedError) as erro:
            self.skipTest(f"Criação de links indisponível neste sistema: {erro}")
        resultado = self.caso.executar()
        self.assertEqual(resultado.estado, EstadoConfiguracaoGSI.FALHA)
        self.assertEqual(list(externa.iterdir()), [])

    def test_cancelamento_apos_descoberta_impede_criacao_de_pastas(self) -> None:
        with self.assertRaises(ConsultaCancelada):
            self.integracao.configurar(verificar_ativa=Mock(side_effect=ConsultaCancelada()))
        self.assertFalse(self.caminho.parent.exists())

    def test_cancelamento_de_reparo_remove_temporario_e_preserva_original(self) -> None:
        confirmacao = self.preparar_conflito()
        original = self.caminho.read_bytes()
        with self.assertRaises(ConsultaCancelada):
            self.integracao.configurar(confirmacao, Mock(side_effect=[None, None, ConsultaCancelada()]))
        self.assertEqual(self.caminho.read_bytes(), original)
        self.assertFalse(list(self.caminho.parent.glob("*.tmp")))
        self.assertEqual(len(list(self.caminho.parent.glob("*.bak"))), 1)

    def test_duplicadas_podem_ser_rejeitadas_sem_mudar_compatibilidade_do_leitor_steam(self) -> None:
        texto = '"x" { "chave" "a" "chave" "b" }'
        self.assertEqual(interpretar_vdf(texto), {"x": {"chave": "b"}})
        with self.assertRaises(ValueError):
            interpretar_vdf(texto, rejeitar_duplicadas=True)

    def test_disponibilidade_e_reavaliada_sem_preferencia_configurado(self) -> None:
        self.integracao.configurar()
        self.assertEqual(self.integracao.verificar().estado, EstadoConfiguracaoGSI.CONFIGURADO)
        self.caminho.unlink()
        self.assertEqual(self.integracao.verificar().estado, EstadoConfiguracaoGSI.AUSENTE)
