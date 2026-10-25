import ast
import subprocess
import sys
from pathlib import Path
from unittest import TestCase

RAIZ = Path(__file__).resolve().parents[1]


def modulos_importados(caminho: Path) -> tuple[str, ...]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    modulos = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.extend(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom):
            modulo = no.module or ""
            modulos.append(modulo)
            modulos.extend(f"{modulo}.{alias.name}" if modulo else alias.name for alias in no.names)
    return tuple(modulos)


class TestarArquitetura(TestCase):
    def test_dominio_nao_importa_infraestrutura_nem_frameworks(self) -> None:
        proibidos = (
            "requests", "tkinter", "threading", "queue", "config", "opendota_client", "d2pt_client",
            "os", "pathlib", "ctypes", "socket", "assistente.aplicacao", "assistente.infraestrutura",
            "assistente.apresentacao", "assistente.configuracao",
        )
        for caminho in (RAIZ / "assistente/dominio").glob("*.py"):
            for modulo in modulos_importados(caminho):
                self.assertFalse(modulo.startswith(proibidos), f"{caminho}: {modulo}")

    def test_aplicacao_nao_importa_clientes_concretos(self) -> None:
        proibidos = (
            "assistente.infraestrutura", "assistente.apresentacao", "requests", "tkinter",
            "subprocess", "ctypes", "winreg", "platform", "sys", "os", "pathlib",
        )
        for caminho in (RAIZ / "assistente/aplicacao").glob("*.py"):
            for modulo in modulos_importados(caminho):
                self.assertFalse(modulo.startswith(proibidos), f"{caminho}: {modulo}")

    def test_apresentacao_nao_importa_adaptadores_concretos(self) -> None:
        proibidos = ("assistente.infraestrutura", "requests", "opendota_client", "d2pt_client")
        for caminho in (RAIZ / "assistente/apresentacao").glob("*.py"):
            for modulo in modulos_importados(caminho):
                self.assertFalse(modulo.startswith(proibidos), f"{caminho}: {modulo}")

    def test_importacao_canonica_nao_inicia_rede_threads_ou_gui(self) -> None:
        codigo = """
import sys
import threading
import requests
import subprocess
import ctypes
def proibido(*args, **kwargs):
    raise AssertionError('Efeito colateral durante importação')
requests.get = proibido
threading.Thread.start = proibido
subprocess.Popen = proibido
ctypes.CDLL = proibido
import app
import assistente.configuracao
import assistente.composicao
import assistente.infraestrutura.fontes
import assistente.infraestrutura.steam
import assistente.infraestrutura.iniciador_linux
import assistente.infraestrutura.iniciador_windows
import assistente.infraestrutura.plataforma_linux
import assistente.infraestrutura.voz_linux
import assistente.infraestrutura.integracao_gsi_arquivo
import assistente.infraestrutura.configuracao_gsi_em_segundo_plano
import assistente.aplicacao.configurar_integracao_gsi
assert 'tkinter' not in sys.modules
"""
        resultado = subprocess.run(
            [sys.executable, "-B", "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)

    def test_sintaxe_do_pacote_e_compativel_com_python_310(self) -> None:
        for caminho in (RAIZ / "assistente").rglob("*.py"):
            ast.parse(caminho.read_text(encoding="utf-8"), feature_version=(3, 10))

    def test_apenas_ponto_de_entrada_python_permanece_na_raiz(self) -> None:
        self.assertEqual(sorted(caminho.name for caminho in RAIZ.glob("*.py")), ["app.py"])

    def test_pacote_e_testes_nao_importam_modulos_antigos(self) -> None:
        antigos = {
            "config", "build_engine", "counter_engine", "d2pt_client", "hero_data", "hero_tags",
            "matchup_engine", "opendota_client", "overlays", "voz_eventos", "assistente_dota",
        }
        caminhos = [RAIZ / "app.py", *(RAIZ / "assistente").rglob("*.py"), *(RAIZ / "tests").rglob("*.py")]
        for caminho in caminhos:
            for modulo in modulos_importados(caminho):
                self.assertNotIn(modulo.split(".")[0], antigos, f"{caminho}: {modulo}")

    def test_caminhos_dos_dados_continuam_na_raiz(self) -> None:
        from assistente.infraestrutura import cliente_dota2protracker, cliente_opendota, preferencias_json

        self.assertEqual(cliente_dota2protracker.CACHE_DIR, RAIZ / "cache/d2pt")
        self.assertEqual(Path(cliente_opendota._CACHE_DIR), RAIZ / "cache_opendota")
        self.assertEqual(preferencias_json.ARQUIVO_PREFERENCIAS, RAIZ / "preferencias_overlay.json")
