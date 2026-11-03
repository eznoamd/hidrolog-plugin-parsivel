"""Interface do Parsivel: as abas da pagina do equipamento.

Este modulo e leve de proposito (o nucleo o importa ao montar a pagina): a
parsivelreader.graficos, o matplotlib e as abas so sao importados quando
uma aba e criada.
"""

from hidrolog_nucleo.plugin import Aba


def _fabrica(classe: str):
    def criar(contexto):
        from . import abas
        return getattr(abas, classe)(contexto)
    return criar


ABAS = [
    Aba("visao", "Visão geral", _fabrica("AbaVisao"), icone="layout-dashboard",
        descricao="Resumo do período selecionado."),
    Aba("serie", "Série temporal", _fabrica("AbaSerie"), icone="chart-line",
        descricao="Intensidade, chuva acumulada, Dm e refletividade; eventos sombreados."),
    Aba("eventos", "Eventos de chuva", _fabrica("AbaEventos"), icone="cloud-rain",
        descricao="Selecione um evento para ver o espectro N(D) ao longo do tempo."),
    Aba("matriz", "Matriz D × V", _fabrica("AbaMatriz"), icone="grid-3x3",
        descricao="Gotas por classe de diâmetro e velocidade (campo 93), somando as leituras do período."),
    Aba("diagnostico", "Diagnóstico", _fabrica("AbaDiagnostico"), icone="activity",
        descricao="Saúde do equipamento: status, laser, temperaturas, alimentação e partículas."),
]
