# -*- coding: utf-8 -*-
"""Janelas flutuantes (overlays) desenhadas sobre o jogo. Não fazem nenhuma chamada de rede."""
import ctypes
import tkinter as tk
import re

from voz_eventos import EVENTOS_HUD, calcular_metas


def aplicar_click_through(hwnd, ativar):
    try:
        estilo = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        estilo |= 0x00080000 | 0x08000000
        if ativar:
            estilo |= 0x00000020
        else:
            estilo &= ~0x00000020
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, estilo)
    except Exception:
        pass


class BaseOverlay:
    def __init__(self, root, pos_x, pos_y, click_through=True, alpha=0.66):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True, "-alpha", alpha)
        self.win.geometry(f"+{pos_x}+{pos_y}")

        self.container = tk.Frame(self.win, bg="#0b0d13", highlightbackground="#f59e0b", highlightthickness=2)
        self.container.pack(fill="both", expand=True)

        # Por segurança, overlays iniciam travadas; destrave no painel para mover.
        self.travado = True
        self.click_through = click_through
        self.visivel = True
        self.ativado = True
        self.win.bind("<ButtonPress-1>", self._iniciar_arraste)
        self.win.bind("<B1-Motion>", self._arrastar)
        self.win.update_idletasks()

    def obter_posicao(self):
        try:
            return {"x": int(self.win.winfo_x()), "y": int(self.win.winfo_y())}
        except Exception:
            return {"x": 20, "y": 100}

    def definir_posicao(self, x, y):
        try:
            self.win.geometry(f"+{int(x)}+{int(y)}")
        except (TypeError, ValueError, tk.TclError):
            pass

    def get_hwnd(self):
        hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
        return hwnd if hwnd != 0 else self.win.winfo_id()

    def _iniciar_arraste(self, e):
        if not self.travado:
            self.offset_x, self.offset_y = e.x, e.y

    def _arrastar(self, e):
        if not self.travado:
            self.win.geometry(f"+{self.win.winfo_x() + e.x - self.offset_x}+{self.win.winfo_y() + e.y - self.offset_y}")

    def alternar_trava(self, travado):
        self.travado = travado
        self.container.configure(
            highlightbackground="#1f2937" if travado else "#f59e0b",
            highlightthickness=1 if travado else 2,
        )
        if self.click_through:
            self.win.after(50, lambda: aplicar_click_through(self.get_hwnd(), travado))

    def atualizar_visibilidade(self, mostrar):
        self.ativado = bool(mostrar)
        if mostrar != self.visivel:
            if mostrar:
                self.win.deiconify()
                if self.click_through and self.travado:
                    self.win.after(50, lambda: aplicar_click_through(self.get_hwnd(), True))
            else:
                self.win.withdraw()
            self.visivel = mostrar


class OverlayTimers(BaseOverlay):
    def __init__(self, root):
        super().__init__(root, 350, 65)
        self.labels = {}
        for ev in EVENTOS_HUD:
            bloco = tk.Frame(self.container, bg="#0b0d13", padx=4, pady=2)
            bloco.pack(side="left")
            lbl = tk.Label(bloco, text=f"{ev.nome_hud}: --", font=("Consolas", 9, "bold"), fg="#e5e7eb", bg="#0b0d13")
            lbl.pack()
            self.labels[ev.chave] = (bloco, lbl)

    def atualizar(self, snap, configs):
        t = snap["tempo"]
        for ev in EVENTOS_HUD:
            if t <= ev.primeiro:
                seg = ev.primeiro - t
            elif ev.intervalo == 0:
                seg = 0
            else:
                seg = (-(t - ev.primeiro)) % ev.intervalo

            bloco, lbl = self.labels[ev.chave]
            if t < 0 and ev.chave in ("stack", "pull"):
                txt, bg, fg = "AGUARD", "#0b0d13", "#6b7280"
            else:
                txt = f"{seg}s" if seg < 60 else f"{seg // 60}:{seg % 60:02d}"
                ant = configs["antecedencias"].get(ev.chave, ev.antecedencia)
                if seg <= 8:
                    bg, fg = "#991b1b", "#fef08a"
                elif seg <= ant:
                    bg, fg = "#78350f", "#fde047"
                else:
                    bg, fg = "#0b0d13", "#e5e7eb"
            bloco.configure(bg=bg)
            lbl.configure(text=f"{ev.nome_hud} {txt}", bg=bg, fg=fg)


class OverlayStats(BaseOverlay):
    def __init__(self, root):
        super().__init__(root, 15, 120)
        f = tk.Frame(self.container, bg="#0b0d13")
        f.pack(padx=6, pady=4)
        self.lbls = {}
        for idx, chave in enumerate(["LH/DN", "GPM", "XPM", "K/D/A"]):
            lbl = tk.Label(f, text=f"{chave}: --", font=("Consolas", 9, "bold"), bg="#0b0d13", fg="#e5e7eb")
            lbl.grid(row=idx, column=0, sticky="w", pady=1)
            self.lbls[chave] = lbl

    def atualizar(self, snap, bench, modo):
        modo_metas = "SUP" if modo in ("SUP", "HARD_SUPPORT") else ("CARRY" if modo == "OFFLANE" else modo)
        m = calcular_metas(snap["tempo"], bench, modo_metas)

        def cor(at, mt):
            return "#4ade80" if at >= mt else "#f87171"

        self.lbls["LH/DN"].configure(text=f"LH/DN: {snap['lh']}/{snap['dn']} (P50:{m['lh']}/{m['dn']})", fg=cor(snap["lh"], m["lh"]))
        self.lbls["GPM"].configure(text=f"GPM: {snap['gpm']} (P50:{m['gpm']})", fg=cor(snap["gpm"], m["gpm"]))
        self.lbls["XPM"].configure(text=f"XPM: {snap['xpm']} (P50:{m['xpm']})", fg=cor(snap["xpm"], m["xpm"]))
        kda_cor = "#4ade80" if (snap["k"] + snap["a"]) >= snap["d"] else "#f87171"
        self.lbls["K/D/A"].configure(text=f"K/D/A: {snap['k']}/{snap['d']}/{snap['a']} (P50:{m['k']}/{m['d']}/{m['a']})", fg=kda_cor)


def _itens_overlay(valor):
    """Extrai somente nomes de itens; nunca leva explicações para a overlay."""
    if isinstance(valor, (list, tuple, set)):
        partes = [str(x).strip() for x in valor]
    else:
        texto = str(valor or "").strip()
        if not texto:
            return []
        texto_lower = texto.lower()
        if any(p in texto_lower for p in (
            "sem amostra", "analisando partidas", "consultando partidas",
            "não encontrado", "nao encontrado", "sem dados", "aguardando análise",
        )):
            return []
        partes = re.split(r"\s*→\s*|,|\n", texto)
    saida = []
    for parte in partes:
        nome = str(parte).strip().strip("•- ")
        nome_lower = nome.lower()
        if not nome or any(p in nome_lower for p in (
            "sem amostra", "analisando", "consultando", "fonte:", "vs ", "jogo(s)",
            "gotas infundidas", "gota infundida", "comprada no early",
        )):
            continue
        if nome_lower in {"town portal scroll", "teleport scroll", "teleportation scroll", "tp scroll"}:
            continue
        if nome not in saida:
            saida.append(nome)
    return saida


class OverlayBuild(BaseOverlay):
    def __init__(self, root):
        super().__init__(root, 15, 225)
        self.lbl_titulo = tk.Label(self.container, text="📋 BUILD", font=("Segoe UI", 8, "bold"), fg="#fbbf24", bg="#0b0d13")
        self.lbl_titulo.pack(anchor="nw", padx=6, pady=(3, 1))
        self.lbl_texto = tk.Label(
            self.container, text="Carregando...", font=("Segoe UI", 9, "bold"),
            fg="#e5e7eb", bg="#0b0d13", justify="left", anchor="nw", wraplength=370,
        )
        self.lbl_texto.pack(padx=6, pady=(1, 4))

    def atualizar(self, dados):
        if not dados:
            return
        self.lbl_titulo.configure(text=f"📋 BUILD ({dados.get('perfil', '')}): {dados.get('heroi', '').upper()}")
        fases = (
            ("🟢 SAÍDA", dados.get("start", "")),
            ("🟡 EARLY", dados.get("early", "")),
            ("🟠 MID", dados.get("mid", "")),
            ("🔴 LATE", dados.get("late", "")),
            ("⚔ OPÇÕES", dados.get("opcoes", [])),
        )
        linhas = []
        for rotulo, valor in fases:
            nomes = _itens_overlay(valor)
            linhas.append(f"{rotulo}: {', '.join(nomes) if nomes else '—'}")
        # Overlay intencionalmente limpa: detalhes de matchup continuam no painel app.
        self.lbl_texto.configure(text="\n".join(linhas))


class OverlayBuybacksBar(BaseOverlay):
    def __init__(self, root, pos_x, pos_y, assistente, offset):
        super().__init__(root, pos_x, pos_y, click_through=False)
        self.a, self.offset = assistente, offset
        f = tk.Frame(self.container, bg="#0b0d13")
        f.pack(padx=2, pady=1)
        self.botoes = []
        for i in range(5):
            idx = self.offset + i
            btn = tk.Button(f, text="RDY", font=("Consolas", 8, "bold"), bg="#166534", fg="white", relief="flat", width=5, command=lambda x=idx: self._registrar(x))
            btn.pack(side="left", padx=10, pady=1)
            self.botoes.append(btn)

    def _registrar(self, idx):
        self.a.bb_timers[idx] = self.a.estado.snapshot()["tempo"] + 480
        self.a.bb_avisados[idx] = False

    def atualizar(self, snap):
        t = snap["tempo"]
        for i in range(5):
            idx = self.offset + i
            restante = self.a.bb_timers[idx] - t
            if restante <= 0:
                self.botoes[i].configure(text="RDY", bg="#166534")
            else:
                m, s = divmod(restante, 60)
                self.botoes[i].configure(text=f"{m}:{s:02d}", bg="#991b1b")
                if restante == 30 and not self.a.bb_avisados[idx]:
                    ts = "Esquerda" if self.offset == 0 else "Direita"
                    self.a.voz.falar(f"Buyback da {ts} voltando em 30 segundos")
                    self.a.bb_avisados[idx] = True
