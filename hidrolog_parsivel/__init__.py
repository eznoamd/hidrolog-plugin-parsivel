"""Plugin do OTT Parsivel2 (disdrometro, dados do cartao SD do XLink 500).

Um pacote so para o sensor inteiro: dados (tabela parsivel_leitura,
migracoes, ingestao, consultas, exportacao, rotas), ficha do cadastro,
regras de qualidade e interface (abas). A interface (PySide6) so e
importada sob demanda; o resto nao precisa de Qt.
"""

from pathlib import Path

from hidrolog_nucleo.plugin import Exportacao, Ingestao, Plugin, carregar_manifesto

from .dados import exportacao, ingestao
from .dados.modelos import ParsivelLeitura
from .ficha import FICHA, VERSAO_FICHA, migrar_atributos
from .regras import REGRAS

_PASTA = Path(__file__).parent


def _rotas():
    from .dados.rotas import rotas
    return rotas


PLUGIN = Plugin(
    manifesto=carregar_manifesto(__file__),
    modelos=(ParsivelLeitura,),
    migracoes=_PASTA / "dados" / "migracoes",
    ingestao=Ingestao(
        tabela=ParsivelLeitura,
        reconhecer=ingestao.reconhecer,
        ler=ingestao.ler,
        chave=("equipamento_id", "tempo"),
        coluna_tempo="tempo",
        coluna_corrompido="corrompido",
        coluna_numero_serie="numero_serie",
        leitura_paralela=True,
    ),
    ficha=FICHA,
    versao_ficha=VERSAO_FICHA,
    migrar_atributos=migrar_atributos,
    regras=REGRAS,
    consultas="hidrolog_parsivel.dados.consultas",
    exportacao=Exportacao(formatos=tuple(exportacao.FORMATOS), exportar=exportacao.exportar),
    interface="hidrolog_parsivel.interface",
    rotas=_rotas,
    amostra=_PASTA / "amostra",
)
