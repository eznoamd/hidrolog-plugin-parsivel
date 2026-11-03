"""Abas do Parsivel na pagina do equipamento: visao geral, serie temporal,
eventos de chuva, matriz D x V (+ DSD media) e diagnostico.

Cada aba recebe o ContextoAba pronto (equipamento, periodo, usuario,
consultas): nao tem seletor de equipamento nem de periodo. Os dados
(buscar_dados, no formato de pr.concatenar) sao carregados numa thread e
ficam num cache por sessao (estado.py). Os graficos sao os da
parsivelreader.graficos, com o estilo do tema e sem o suptitle."""

from __future__ import annotations

import numpy as np
import parsivelreader as pr
from parsivelreader import graficos
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from design.componentes import (
    Carregando, Cartao, CartaoMetrica, Coluna, EstadoVazio, FaixaAviso, FiguraIncorporada, Selo, TabelaFiltravel, formatos,
    rotulo,
)
from design.tema import DIMENSAO, ESPACO, cor

from .estado import CacheParsivel, Resultado, para_datetime

LINHAS_EVENTOS_VISIVEIS = 8

# Escala de status do Parsivel (campo 18): fica no plugin, nao no nucleo.
STATUS_PARSIVEL = {
    0: ("0 · OK", "sucesso", False, "Funcionamento normal."),
    1: ("1 · Lente suja", "alerta", False, "Lentes sujas: a medição continua, mas limpe o sensor."),
    2: ("2 · Sem medida", "erro", False, "Lentes muito sujas: nenhuma medida utilizável."),
    3: ("3 · Laser danificado", "erro", True, "Laser danificado: o sensor precisa de manutenção."),
}


def sem_suptitulo(fig):
    """Esconde o suptitle das figuras da biblioteca: no app ele repetiria o
    titulo da aba (e nao ocupa espaco no constrained_layout)."""
    if fig is not None and getattr(fig, "_suptitle", None) is not None:
        fig._suptitle.set_visible(False)
        fig._suptitle.set_in_layout(False)
    return fig


def destacar_suspeitas(fig, r: Resultado):
    """Marca as leituras suspeitas (regras de qualidade) no primeiro painel da
    serie temporal (intensidade). Os dados nao mudam: e so um destaque."""
    mascara = r.mascara_suspeitas()
    if fig is None or not mascara.any() or not fig.axes:
        return fig
    ax = fig.axes[0]
    tempos = r.dados["tempo"][mascara]
    valores = np.nan_to_num(np.asarray(r.dados["intensidade_chuva"], dtype=float)[mascara], nan=0.0)
    ax.scatter(tempos, valores, s=22, marker="o", facecolors="none", edgecolors=cor("alerta"), linewidths=1.4,
               zorder=5, label=f"suspeita ({int(mascara.sum())})")
    ax.legend(loc="upper right", fontsize="small")
    return fig


def figura(fig, titulo: str | None = None, altura: int = 480) -> FiguraIncorporada:
    return FiguraIncorporada(sem_suptitulo(fig), titulo, altura_minima=altura)


def _sem_dado(v) -> bool:
    return v is None or (isinstance(v, np.ndarray) and (v.size == 0 or np.isnan(v).all()))


def _apagar_layout(layout) -> None:
    """Tira tudo do layout ja (esconde e solta do pai) e apaga depois."""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout():
            _apagar_layout(item.layout())


class _AbaParsivel(QWidget):
    """Estados (carregando / sem leituras / conteudo) e o conteudo, refeito a
    cada carga com `montar(resultado, layout)`."""

    titulo = ""
    descricao = ""

    def __init__(self, contexto):
        super().__init__()
        self.contexto = contexto
        self.cache = CacheParsivel.da_sessao(contexto)
        self.resultado: Resultado | None = None
        self._chave_mostrada = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACO["lg"])
        self.corpo = lay
        self.aviso = FaixaAviso(fechavel=True)
        lay.addWidget(self.aviso)
        self.carregando = Cartao()
        self.carregando.corpo.addWidget(Carregando("Carregando as leituras do período…"))
        self.carregando.setMinimumHeight(220)
        lay.addWidget(self.carregando)
        self.sem_dados = self._vazio("Nenhuma leitura neste período", "", "cloud-rain")
        self.conteudo = QWidget()
        self.conteudo_layout = QVBoxLayout(self.conteudo)
        self.conteudo_layout.setContentsMargins(0, 0, 0, 0)
        self.conteudo_layout.setSpacing(ESPACO["lg"])
        lay.addWidget(self.conteudo)
        lay.addStretch(1)
        self._mostrar(None)
        self.atualizar(contexto)

    def _vazio(self, titulo, descricao, icone) -> Cartao:
        v = EstadoVazio(titulo, descricao, icone)
        c = Cartao()
        c.vazio = v
        c.corpo.addWidget(v)
        self.corpo.addWidget(c)
        return c

    def _mostrar(self, qual: QWidget | None) -> None:
        for w in (self.carregando, self.sem_dados, self.conteudo):
            w.setVisible(w is qual)

    # ------------------------------------------------------------------ ciclo
    def atualizar(self, contexto, forcar: bool = False) -> None:
        """Novo contexto (periodo, filtro ou dados mudaram). Recarrega se preciso."""
        self.contexto = contexto
        chave = contexto.chave()
        if not forcar and chave == self._chave_mostrada and self.resultado is not None:
            return
        self._chave_mostrada = chave
        if self.cache.em_cache(contexto) is None:
            self._mostrar(self.carregando)
        self.cache.carregar(contexto, lambda r, c=chave: self._carregado(c, r), self._falhou)

    def _carregado(self, chave, r: Resultado) -> None:
        if chave != self._chave_mostrada:
            return  # chegou depois de outra escolha
        self.resultado = r
        self.aviso.limpar()
        if r.n == 0:
            ini = formatos.data(r.inicio) if r.inicio else "o início"
            fim = formatos.data(r.fim) if r.fim else "hoje"
            texto = (f"{r.equipamento.nome} não tem leituras válidas entre {ini} e {fim}. Escolha outro período"
                     + (" ou importe os dados do cartão SD." if self.contexto.pode("cadastro") else "."))
            if r.ocultadas:
                texto += f" {formatos.inteiro(r.ocultadas)} leitura(s) suspeita(s) estão ocultas pelo filtro."
            self.sem_dados.vazio.descricao.setText(texto)
            self.sem_dados.vazio.descricao.show()
            self._mostrar(self.sem_dados)
            return
        _apagar_layout(self.conteudo_layout)
        try:
            self.montar(r, self.conteudo_layout)
        except Exception as erro:  # noqa: BLE001
            self._erro(erro, f"montar {type(self).__name__}")
        self._mostrar(self.conteudo)

    def _falhou(self, erro) -> None:
        self._mostrar(None)
        self._erro(erro, "dados do Parsivel")

    def _erro(self, erro, onde: str) -> None:
        tratar = self.contexto.tratar_erro
        self.aviso.mostrar(tratar(erro, onde) if tratar else str(erro), "erro")

    def legenda(self, texto: str = "") -> None:
        r = self.resultado
        padrao = "Gráficos da parsivelreader com o estilo do app. Leituras corrompidas ficam fora dos gráficos."
        if r is not None and r.suspeitas and not self.contexto.ocultar_suspeitas:
            padrao += " Leituras suspeitas (regras de qualidade) aparecem com destaque."
        if r is not None and r.ocultadas:
            padrao += f" {formatos.inteiro(r.ocultadas)} leitura(s) suspeita(s) ocultas pelo filtro."
        self.conteudo_layout.addWidget(rotulo(texto or padrao, "legenda", quebra=True))

    def montar(self, r: Resultado, lay: QVBoxLayout) -> None:
        raise NotImplementedError


def grade_metricas(cartoes: list[QWidget]):
    from PySide6.QtWidgets import QGridLayout

    grade = QGridLayout()
    grade.setSpacing(ESPACO["lg"])
    for i, c in enumerate(cartoes):
        grade.addWidget(c, 0, i)
        grade.setColumnStretch(i, 1)
    return grade


# ============================================================================
class AbaVisao(_AbaParsivel):
    titulo = "Visão geral"
    descricao = "Resumo do período selecionado."

    def montar(self, r: Resultado, lay) -> None:
        d = r.dados
        chuva = float(np.nansum(pr.chuva_por_leitura(d)))
        intensidade = d["intensidade_chuva"]
        if _sem_dado(intensidade):
            imax, quando = None, ""
        else:
            imax = float(np.nanmax(intensidade))
            quando = f"em {formatos.data_hora(para_datetime(d['tempo'][int(np.nanargmax(intensidade))]))}"
        res = r.resumo
        lay.addLayout(grade_metricas([
            CartaoMetrica("Chuva no período", chuva, "mm", casas=1, nome_icone="cloud-rain",
                          descricao=formatos.periodo(para_datetime(d["tempo"][0]), para_datetime(d["tempo"][-1]))),
            CartaoMetrica("Intensidade máxima", imax, "mm/h", casas=1, nome_icone="gauge", descricao=quando),
            CartaoMetrica("Eventos de chuva", len(r.eventos), "eventos", casas=0, nome_icone="droplets",
                          descricao="≥ 0,2 mm; gotas a menos de 30 min"),
            CartaoMetrica("Leituras válidas", r.n, "leituras", casas=0, nome_icone="database",
                          descricao=f"{formatos.inteiro(res.corrompidas if res else d['descartados'])} corrompida(s) "
                                    "guardada(s) para diagnóstico"),
        ]))
        fig = destacar_suspeitas(sem_suptitulo(graficos.grafico_serie_temporal(d, r.eventos)), r)
        lay.addWidget(figura(fig, "Série temporal", 600))
        self.legenda()


class AbaSerie(_AbaParsivel):
    titulo = "Série temporal"
    descricao = "Intensidade, chuva acumulada, Dm e refletividade; eventos sombreados."

    def montar(self, r: Resultado, lay) -> None:
        fig = destacar_suspeitas(sem_suptitulo(graficos.grafico_serie_temporal(r.dados, r.eventos)), r)
        lay.addWidget(figura(fig, None, 720))
        if _sem_dado(r.dados["refletividade"]):
            lay.addWidget(FaixaAviso("Estes arquivos não têm o campo 07 (refletividade): o último painel fica vazio. "
                                     "Os arquivos gravados até out/2026 não trazem esse campo.", "info"))
        self.legenda()


def colunas_eventos() -> list[Coluna]:
    return [
        Coluna("n", "Nº", "inteiro"),
        Coluna("inicio", "Início", "data_hora"),
        Coluna("fim", "Fim", "data_hora"),
        Coluna("duracao", "Duração", "mono"),
        Coluna("chuva", "Chuva", "numero", unidade="mm", casas=1),
        Coluna("imax", "Intensidade máx.", "numero", unidade="mm/h", casas=1),
        Coluna("leituras", "Leituras com gota", "inteiro"),
        Coluna("vazio", "", estica=True, formatar=lambda _: ""),
    ]


class AbaEventos(_AbaParsivel):
    titulo = "Eventos de chuva"
    descricao = "Selecione um evento para ver o espectro N(D) ao longo do tempo."

    def __init__(self, contexto):
        self.tabela: TabelaFiltravel | None = None
        self.figura: FiguraIncorporada | None = None
        super().__init__(contexto)

    def montar(self, r: Resultado, lay) -> None:
        linhas = []
        for i, e in enumerate(r.eventos):
            ini, fim = para_datetime(e["inicio"]), para_datetime(e["fim"])
            linhas.append({"n": i + 1, "inicio": ini, "fim": fim, "duracao": formatos.duracao(fim - ini),
                           "chuva": e["chuva_total_mm"], "imax": e["intensidade_maxima"],
                           "leituras": e["n_registros_validos"], "vazio": "", "_ev": e})
        self.tabela = TabelaFiltravel(colunas_eventos(), mostrar_busca=False, titulo_vazio="Nenhum evento no período",
                                      descricao_vazio="Nenhuma chuva passou de 0,2 mm neste período.",
                                      icone_vazio="cloud-rain")
        self.tabela.definir_linhas(linhas)
        visiveis = min(max(len(linhas), 1), LINHAS_EVENTOS_VISIVEIS)
        altura = visiveis * DIMENSAO["altura_linha_tabela"] + DIMENSAO["altura_linha_tabela"] + 2 + \
            DIMENSAO["altura_controle"] + ESPACO["sm"] + ESPACO["xs"]
        self.tabela.setFixedHeight(altura if linhas else 260)
        lay.addWidget(self.tabela)
        self.figura = FiguraIncorporada(titulo="Evento", altura_minima=560)
        self.figura.definir_vazio("Nenhum evento selecionado", "Escolha um evento na tabela.")
        self.figura.setVisible(bool(linhas))
        lay.addWidget(self.figura)
        self.tabela.selecao_alterada.connect(self._mostrar_evento)
        self.legenda("Evento: leituras com gota a menos de 30 min uma da outra, com pelo menos 0,2 mm de chuva "
                     "(parsivelreader.detectar_eventos).")
        if linhas:
            self.tabela.tabela.selectRow(0)

    def _mostrar_evento(self, sel) -> None:
        if not sel or self.resultado is None:
            return
        e = sel[0]
        self.figura.titulo.setText(f"Evento {e['n']} · {formatos.periodo(e['inicio'], e['fim'])} · "
                                   f"{formatos.numero(e['chuva'], 1, 'mm')}")
        self.figura.titulo.show()
        self.figura.definir_figura(sem_suptitulo(graficos.grafico_evento(self.resultado.dados, e["_ev"])))


class AbaMatriz(_AbaParsivel):
    titulo = "Matriz D × V"
    descricao = "Gotas por classe de diâmetro e velocidade (campo 93), somando as leituras do período."

    def montar(self, r: Resultado, lay) -> None:
        lay.addWidget(figura(graficos.grafico_matriz(r.dados), "Matriz D × V", 620))
        lay.addWidget(figura(graficos.grafico_dsd_media(r.dados), "Distribuição média N(D)", 440))
        self.legenda("A curva vermelha é a velocidade terminal da chuva (Atlas et al., 1973). Gotas muito acima "
                     "ou abaixo dela costumam ser respingo, granizo ou ruído. A DSD média usa as leituras com "
                     "R ≥ 0,1 mm/h (campo 90).")


CAMPOS_NOVOS = "03–10, 13–16, 18, 22, 23, 26–29, 33, 35 e 60"


class AbaDiagnostico(_AbaParsivel):
    titulo = "Diagnóstico"
    descricao = "Saúde do equipamento: status, laser, temperaturas, alimentação e partículas."

    def montar(self, r: Resultado, lay) -> None:
        d = r.dados

        def media(chave):
            v = d.get(chave)
            return None if _sem_dado(v) else float(np.nanmean(v))

        st = d["status_sensor"]
        ultimo = None if _sem_dado(st) else int(st[~np.isnan(st)][-1])
        antigo = _sem_dado(st) and _sem_dado(d["amplitude_laser"])
        if antigo:
            lay.addWidget(FaixaAviso(
                f"Estes dados vêm do formato antigo do cartão (até out/2026) e não têm os campos {CAMPOS_NOVOS}. "
                "Os cartões e painéis desses campos aparecem vazios.", "info"))
        status = STATUS_PARSIVEL.get(ultimo)
        lay.addLayout(grade_metricas([
            CartaoMetrica("Status do sensor", status[0] if status else None,
                          descricao="última leitura · campo 18" if status else "sem o campo 18 nestes dados",
                          nome_icone="activity",
                          selo=status[:2] if status else ("Sem dado", "neutro")),
            CartaoMetrica("Amplitude do laser", media("amplitude_laser"), "", casas=0, nome_icone="gauge",
                          descricao="média · campo 10" if media("amplitude_laser") is not None
                          else "sem o campo 10 nestes dados"),
            CartaoMetrica("Temperatura da carcaça", media("temperatura_sensor"), "°C", casas=1,
                          nome_icone="activity", descricao="média do período · campo 12"),
            CartaoMetrica("Tensão de alimentação", media("tensao"), "V", casas=2, nome_icone="activity",
                          descricao="média do período · campo 17"),
        ]))
        escala = Cartao("Escala de status do Parsivel2 (campo 18)")
        lin = QHBoxLayout()
        lin.setSpacing(ESPACO["xl"])
        for texto, tom, solido, desc in STATUS_PARSIVEL.values():
            col = QVBoxLayout()
            col.setSpacing(ESPACO["xs"])
            col.addWidget(Selo(texto, tom, solido), 0, Qt.AlignmentFlag.AlignLeft)
            col.addWidget(rotulo(desc, "legenda", quebra=True))
            lin.addLayout(col, 1)
        escala.corpo.addLayout(lin)
        lay.addWidget(escala)
        lay.addWidget(figura(graficos.grafico_diagnostico(d), None, 900))
        self.legenda()
