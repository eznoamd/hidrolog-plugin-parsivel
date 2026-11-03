"""Ingestao do Parsivel: o SD do XLink 500 tem um AAAAMMDDHHMMSS.txt por
leitura (o nome e o horario da coleta), em pastas AAAAMMDDHH. O parsing e
todo da parsivelreader (pr.ler_conteudo).

reconhecer: cada .txt com nome de data vira uma unidade; os logs do XLink e
            do Parsivel e qualquer outro arquivo vao para os ignorados; o
            campo 13 (numero de serie) e o 14 (firmware) da leitura mais
            recente viram metadados.
ler:        1 unidade -> 1 leitura (linha da tabela parsivel_leitura).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath

import parsivelreader as pr
from hidrolog_nucleo.plugin import PlanoImportacao, Recusa, Unidade

from .conversao import registro_para_linha

MENSAGEM_RECUSA = ("nenhuma leitura do Parsivel neste envio: os dados do cartao SD sao arquivos "
                   "AAAAMMDDHHMMSS.txt (ex. 2026102116/20261021160000.txt)")


def _motivo_ignorado(caminho: str) -> str:
    nome = PurePosixPath(caminho).name.lower()
    if "xlink" in caminho.lower():
        return "log do XLink"
    if nome == "parsivel_erros.log":
        return "log de erros do Parsivel"
    return "nao e uma leitura do Parsivel"


def _eh_data(nome: str) -> bool:
    """AAAAMMDDHHMMSS.txt forma uma data? (sem strptime: sao ~11 mil por cartao)"""
    s = nome[:14]
    try:
        datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]), int(s[12:14]))
        return True
    except ValueError:
        return False


def reconhecer(arvore, verificar: bool = False):
    unidades, ignorados = [], []
    for arquivo in arvore:
        if not pr.eh_arquivo_parsivel(arquivo.nome):
            ignorados.append((arquivo, _motivo_ignorado(arquivo.caminho)))
        elif not _eh_data(arquivo.nome):
            ignorados.append((arquivo, "nome com 14 digitos que nao e uma data"))
        else:
            unidades.append(Unidade(arquivo.caminho, [arquivo]))
    if not unidades:
        return Recusa(MENSAGEM_RECUSA)
    plano = PlanoImportacao(unidades=unidades, ignorados=ignorados)
    if not verificar:
        ultima = max(unidades, key=lambda u: u.arquivo.nome).arquivo
        registro = pr.ler_conteudo(ultima.texto(), nome_arquivo=ultima.nome)
        if registro.numero_serie:
            plano.metadados["numero_serie"] = registro.numero_serie.strip()
        if registro.firmware_iop:
            plano.metadados["firmware"] = registro.firmware_iop.strip()
    return plano


def ler(unidade: Unidade):
    arquivo = unidade.arquivo
    texto = arquivo.ler().decode("utf-8", errors="replace")
    yield registro_para_linha(pr.ler_conteudo(texto, nome_arquivo=arquivo.nome))
