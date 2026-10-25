import logging
import os
import shutil
import subprocess
from pathlib import Path

from .iniciador_steam import ErroInspecaoProcesso, IniciadorSteam
from .steam import InstalacaoDota, localizar_instalacao

REGISTRO = logging.getLogger(__name__)


def raizes_steam_linux() -> tuple[tuple[Path, tuple[str, ...]], ...]:
    casa = Path.home()
    dados = Path(os.environ.get("XDG_DATA_HOME") or casa / ".local/share")
    if not dados.is_absolute():
        dados = casa / ".local/share"
    steam = shutil.which("steam")
    raizes: list[tuple[Path, tuple[str, ...]]] = []
    pastas = (dados / "Steam", casa / ".local/share/Steam", casa / ".steam/root", casa / ".steam/steam")
    for raiz in dict.fromkeys(pastas):
        comando = (steam,) if steam else ()
        if not comando and (raiz / "steam.sh").is_file():
            comando = (str((raiz / "steam.sh").resolve()),)
        raizes.append((raiz, comando))
    pasta_flatpak = casa / ".var/app/com.valvesoftware.Steam"
    if pasta_flatpak.is_dir():
        comando_flatpak: tuple[str, ...] = ()
        flatpak = shutil.which("flatpak")
        if flatpak:
            try:
                consulta = subprocess.run(
                    [flatpak, "info", "com.valvesoftware.Steam"],
                    capture_output=True, timeout=3, check=False,
                )
                if consulta.returncode == 0:
                    comando_flatpak = (flatpak, "run", "com.valvesoftware.Steam")
            except (OSError, subprocess.TimeoutExpired) as erro:
                REGISTRO.warning("Não foi possível consultar a Steam Flatpak: %s", erro)
        for relativo in (".local/share/Steam", ".steam/steam", ".steam/root"):
            raizes.append((pasta_flatpak / relativo, comando_flatpak))
    return tuple(raizes)


def localizar_dota_linux() -> InstalacaoDota:
    return localizar_instalacao(
        raizes_steam_linux(),
        ("game/bin/linuxsteamrt64/dota2", "game/bin/linux64/dota2"),
    )


def procurar_pid_linux(executavel: Path, processos: Path = Path("/proc")) -> int | None:
    acesso_negado = False
    try:
        for pasta in processos.iterdir():
            if not pasta.name.isdigit():
                continue
            try:
                with (pasta / "comm").open(encoding="utf-8") as arquivo:
                    nome = arquivo.read(64).strip()
                if nome != executavel.name:
                    continue
                try:
                    # /proc/PID/exe referencia o arquivo mesmo dentro do Steam Runtime.
                    if (pasta / "exe").samefile(executavel):
                        return int(pasta.name)
                except PermissionError:
                    acesso_negado = True
            except (FileNotFoundError, ProcessLookupError):
                continue
            except PermissionError:
                REGISTRO.debug("Processo inacessível: %s", pasta.name)
        if acesso_negado:
            raise ErroInspecaoProcesso("Sem permissão para identificar um processo chamado dota2.")
    except OSError as erro:
        raise ErroInspecaoProcesso(f"Não foi possível consultar os processos Linux: {erro}") from erro
    return None


def criar_iniciador_linux() -> IniciadorSteam:
    return IniciadorSteam(localizar_dota_linux, procurar_pid_linux)
