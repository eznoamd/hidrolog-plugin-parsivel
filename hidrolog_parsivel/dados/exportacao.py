"""Exportacao do Parsivel: CSV e NetCDF (CF-1.8).

As leituras sao lidas do banco em blocos (TAMANHO_BLOCO) e escritas a cada
bloco, entao um periodo grande nao fica todo na memoria.

NetCDF com a biblioteca netCDF4 (e nao xarray): ela escreve direto num
arquivo com a dimensao `time` ilimitada, acrescentando bloco a bloco; o
xarray monta o Dataset inteiro na memoria antes de gravar (ou exige dask).
Tambem e uma dependencia so (o xarray precisaria de pandas + h5netcdf).
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

import numpy as np
from parsivelreader import (
    DIAMETRO_CLASSES,
    LARGURA_DIAMETRO,
    LARGURA_VELOCIDADE,
    N_CLASSES,
    VELOCIDADE_CLASSES,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from hidrolog_nucleo.plugin import ContextoExportacao, FormatoExportacao, ResultadoExportacao
from .conversao import bytes_para_matriz, bytes_para_vetor
from .modelos import ParsivelLeitura

TAMANHO_BLOCO = 2000

FORMATOS = [
    FormatoExportacao("csv", "CSV (uma linha por leitura, sem os vetores)", ".csv", "text/csv"),
    FormatoExportacao("netcdf", "NetCDF-4 (CF-1.8, com N(D), v(D) e matriz 93)", ".nc", "application/x-netcdf"),
]

# atributo -> (campo do Parsivel, sufixo da unidade no CSV, units CF, long_name, tipo)
# tipo: "f" float, "i" inteiro, "s" texto
VARIAVEIS = {
    "intensidade_chuva":           ("01", "mm_h", "mm h-1", "intensidade de chuva", "f"),
    "chuva_acumulada":             ("02", "mm", "mm", "chuva acumulada desde que o sensor ligou (volta a 0 em 300 mm)", "f"),
    "codigo_synop_wawa":           ("03", "", "1", "tempo presente SYNOP wawa (tabela 4680)", "i"),
    "codigo_synop_ww":             ("04", "", "1", "tempo presente SYNOP ww (tabela 4677)", "i"),
    "codigo_metar":                ("05", "", "", "tempo presente METAR/SPECI (tabela 4678)", "s"),
    "refletividade":               ("07", "dBZ", "dBZ", "refletividade radar (-9.999 = sem gota)", "f"),
    "visibilidade_mor":            ("08", "m", "m", "visibilidade MOR", "f"),
    "intervalo_amostragem":        ("09", "s", "s", "intervalo de amostragem", "f"),
    "amplitude_laser":             ("10", "", "1", "amplitude do sinal da faixa de laser", "f"),
    "n_particulas":                ("11", "", "1", "particulas detectadas e validadas", "f"),
    "temperatura_sensor":          ("12", "C", "degree_Celsius", "temperatura dentro da carcaca do sensor", "f"),
    "numero_serie":                ("13", "", "", "numero de serie do sensor", "s"),
    "firmware_iop":                ("14", "", "", "versao do firmware IOP", "s"),
    "firmware_dsp":                ("15", "", "", "versao do firmware DSP", "s"),
    "corrente_aquecimento":        ("16", "A", "A", "corrente de aquecimento das cabecas", "f"),
    "tensao":                      ("17", "V", "V", "tensao de alimentacao", "f"),
    "status_sensor":               ("18", "", "1", "status do sensor (0 OK, 1 lentes sujas, 2 sem medida utilizavel, 3 laser danificado)", "i"),
    "inicio_medida":               ("19", "", "", "inicio da medida (DD.MM.YYYY_hh:mm:ss)", "s"),
    "hora_sensor":                 ("20", "", "", "hora do sensor (hh:mm:ss)", "s"),
    "data_sensor":                 ("21", "", "", "data do sensor (DD.MM.YYYY)", "s"),
    "chuva_absoluta":              ("24", "mm", "mm", "chuva absoluta (no modo do XLink: chuva da leitura)", "f"),
    "codigo_erro":                 ("25", "", "", "codigo de erro", "s"),
    "temperatura_placa":           ("26", "C", "degree_Celsius", "temperatura da placa de circuito", "f"),
    "temperatura_cabeca_direita":  ("27", "C", "degree_Celsius", "temperatura da cabeca direita", "f"),
    "temperatura_cabeca_esquerda": ("28", "C", "degree_Celsius", "temperatura da cabeca esquerda", "f"),
    "intensidade_16bit_30":        ("30", "mm_h", "mm h-1", "intensidade de chuva 16 bit (max 30 mm/h)", "f"),
    "intensidade_16bit_1200":      ("31", "mm_h", "mm h-1", "intensidade de chuva 16 bit (max 1200 mm/h)", "f"),
    "chuva_acumulada_16bit":       ("32", "mm", "mm", "chuva acumulada 16 bit", "f"),
    "energia_cinetica":            ("34", "J_m2_h", "J m-2 h-1", "energia cinetica", "f"),
    "n_particulas_total":          ("60", "", "1", "todas as particulas detectadas, inclusive as nao validadas", "f"),
}

PREENCHIMENTO_FLOAT = -9999.0
PREENCHIMENTO_INT = -9999
PREENCHIMENTO_RAW = -1


def cabecalho_csv() -> list[str]:
    colunas = ["tempo", "arquivo", "corrompido"]
    for attr, (_, sufixo, *_resto) in VARIAVEIS.items():
        colunas.append(f"{attr}_{sufixo}" if sufixo else attr)
    return colunas + ["qualidade"]


def _blocos(sessao: Session, equipamento_id: int, inicio, fim) -> Iterator[list[ParsivelLeitura]]:
    filtros = [ParsivelLeitura.equipamento_id == equipamento_id]
    if inicio is not None:
        filtros.append(ParsivelLeitura.tempo >= inicio)
    if fim is not None:
        filtros.append(ParsivelLeitura.tempo <= fim)
    consulta = (select(ParsivelLeitura).where(*filtros).order_by(ParsivelLeitura.tempo)
                .execution_options(yield_per=TAMANHO_BLOCO))
    for particao in sessao.scalars(consulta).partitions():
        # o mapa de identidade da sessao guarda referencias fracas: os
        # objetos de um bloco ja escrito sao liberados
        yield particao


def _formatar(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return repr(valor)        # ponto decimal, sem perder precisao
    return str(valor)


def exportar_csv(sessao: Session, equipamento_id: int, inicio, fim, destino: Path,
                 contexto: Optional[ContextoExportacao] = None) -> ResultadoExportacao:
    qualidade = contexto.qualidade if contexto is not None else (lambda _t: "")
    resultado = ResultadoExportacao()
    with open(destino, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f, delimiter=",", lineterminator="\n")
        escritor.writerow(cabecalho_csv())
        for bloco in _blocos(sessao, equipamento_id, inicio, fim):
            for l in bloco:
                escritor.writerow([l.tempo.isoformat(), l.arquivo, int(l.corrompido)] +
                                  [_formatar(getattr(l, attr)) for attr in VARIAVEIS] + [qualidade(l.tempo)])
            _acumular(resultado, bloco)
    return resultado


def _acumular(resultado: ResultadoExportacao, bloco: list) -> None:
    if not bloco:
        return
    resultado.leituras += len(bloco)
    resultado.inicio = resultado.inicio or bloco[0].tempo
    resultado.fim = bloco[-1].tempo


UNIDADE_TEMPO = "seconds since 1970-01-01 00:00:00"


def exportar_netcdf(sessao: Session, equipamento_id: int, inicio, fim, destino: Path,
                    contexto: Optional[ContextoExportacao] = None) -> ResultadoExportacao:
    import netCDF4

    equipamento = contexto.equipamento
    qualidade_de = contexto.qualidade
    resultado = ResultadoExportacao()
    with netCDF4.Dataset(destino, "w", format="NETCDF4") as nc:
        nc.Conventions = "CF-1.8"
        nc.title = f"OTT Parsivel2 - {equipamento.nome}"
        if contexto.instituicao:
            nc.institution = contexto.instituicao
        nc.source = "OTT Parsivel2 via datalogger XLink 500 (cartao SD)"
        nc.equipamento = equipamento.nome
        nc.numero_serie = equipamento.numero_serie or ""
        nc.local = equipamento.local or ""
        nc.date_created = datetime.now().isoformat(timespec="seconds")
        nc.history = f"{nc.date_created} gerado pelo Hidrolog"
        nc.comment = ("tempo = horario do relogio do XLink, do nome do arquivo, sem fuso. "
                      "Campos que os arquivos antigos (ate out/2026) nao tem ficam com _FillValue.")

        nc.createDimension("time", None)
        nc.createDimension("diametro", N_CLASSES)
        nc.createDimension("velocidade", N_CLASSES)
        nc.createDimension("nv", 2)

        tempo = nc.createVariable("time", "f8", ("time",))
        tempo.units = UNIDADE_TEMPO
        tempo.calendar = "standard"
        tempo.standard_name = "time"
        tempo.long_name = "tempo da leitura (relogio do XLink, sem fuso)"
        tempo.axis = "T"

        for nome, centros, larguras, unidade, descricao in (
            ("diametro", DIAMETRO_CLASSES, LARGURA_DIAMETRO, "mm", "diametro equivalente da particula"),
            ("velocidade", VELOCIDADE_CLASSES, LARGURA_VELOCIDADE, "m s-1", "velocidade de queda da particula"),
        ):
            v = nc.createVariable(nome, "f4", (nome,))
            v[:] = centros
            v.units = unidade
            v.long_name = f"{descricao}: centro da classe (manual do Parsivel2, Apendice C)"
            v.bounds = f"{nome}_limites"
            w = nc.createVariable(f"{nome}_largura", "f4", (nome,))
            w[:] = larguras
            w.units = unidade
            w.long_name = f"{descricao}: largura da classe"
            b = nc.createVariable(f"{nome}_limites", "f4", (nome, "nv"))
            b[:] = np.column_stack([centros - larguras / 2, centros + larguras / 2])

        arquivo = nc.createVariable("arquivo", str, ("time",))
        arquivo.long_name = "arquivo .txt de origem no cartao SD"
        corrompido = nc.createVariable("corrompido", "i1", ("time",))
        corrompido.long_name = "leitura corrompida (sem 90, 91 ou 93 completos)"
        corrompido.flag_values = np.array([0, 1], dtype="i1")
        corrompido.flag_meanings = "valida corrompida"
        corrompido.units = "1"

        qualidade = nc.createVariable("qualidade", str, ("time",))
        qualidade.long_name = ("regras de qualidade que marcaram a leitura (codigos separados por ';'; "
                               "vazio = nenhuma). As regras nunca alteram os dados.")

        variaveis = {}
        for attr, (campo, _sufixo, unidade, descricao, tipo) in VARIAVEIS.items():
            if tipo == "f":
                v = nc.createVariable(attr, "f8", ("time",), fill_value=PREENCHIMENTO_FLOAT)
            elif tipo == "i":
                v = nc.createVariable(attr, "i4", ("time",), fill_value=PREENCHIMENTO_INT)
            else:
                v = nc.createVariable(attr, str, ("time",))
            v.long_name = descricao
            v.campo_parsivel = campo
            if unidade:
                v.units = unidade
            variaveis[attr] = (v, tipo)

        n_d = nc.createVariable("N_d", "f4", ("time", "diametro"), fill_value=np.float32(PREENCHIMENTO_FLOAT),
                                zlib=True, chunksizes=(TAMANHO_BLOCO, N_CLASSES))
        n_d.long_name = "espectro de tamanho de gotas N(D), log10 (campo 90; -9.999 = sem gota na classe)"
        n_d.units = "log10(m-3 mm-1)"
        n_d.campo_parsivel = "90"
        v_d = nc.createVariable("v_d", "f4", ("time", "diametro"), fill_value=np.float32(PREENCHIMENTO_FLOAT),
                                zlib=True, chunksizes=(TAMANHO_BLOCO, N_CLASSES))
        v_d.long_name = "velocidade media de queda por classe de diametro (campo 91)"
        v_d.units = "m s-1"
        v_d.campo_parsivel = "91"
        raw = nc.createVariable("raw", "i2", ("time", "velocidade", "diametro"),
                                fill_value=np.int16(PREENCHIMENTO_RAW), zlib=True,
                                chunksizes=(256, N_CLASSES, N_CLASSES))
        raw.long_name = "contagem de particulas por classe de velocidade e diametro (campo 93)"
        raw.units = "1"
        raw.campo_parsivel = "93"

        for bloco in _blocos(sessao, equipamento_id, inicio, fim):
            if not bloco:
                continue
            i, n = resultado.leituras, len(bloco)
            fatia = slice(i, i + n)
            tempo[fatia] = netCDF4.date2num([l.tempo for l in bloco], UNIDADE_TEMPO, "standard")
            arquivo[fatia] = np.array([l.arquivo for l in bloco], dtype=object)
            corrompido[fatia] = np.array([int(l.corrompido) for l in bloco], dtype="i1")
            qualidade[fatia] = np.array([qualidade_de(l.tempo) for l in bloco], dtype=object)
            for attr, (var, tipo) in variaveis.items():
                valores = [getattr(l, attr) for l in bloco]
                if tipo == "f":
                    var[fatia] = np.array([PREENCHIMENTO_FLOAT if x is None else x for x in valores], dtype="f8")
                elif tipo == "i":
                    var[fatia] = np.array([PREENCHIMENTO_INT if x is None else x for x in valores], dtype="i4")
                else:
                    var[fatia] = np.array(["" if x is None else x for x in valores], dtype=object)
            n_d[fatia] = _empilhar([bytes_para_vetor(l.n_d) for l in bloco], (N_CLASSES,), PREENCHIMENTO_FLOAT, "f4")
            v_d[fatia] = _empilhar([bytes_para_vetor(l.v_d) for l in bloco], (N_CLASSES,), PREENCHIMENTO_FLOAT, "f4")
            raw[fatia] = _empilhar([bytes_para_matriz(l.raw) for l in bloco], (N_CLASSES, N_CLASSES),
                                   PREENCHIMENTO_RAW, "i2")
            _acumular(resultado, bloco)
    return resultado


def _empilhar(itens: list[Optional[np.ndarray]], forma: tuple, preenchimento, dtype) -> np.ndarray:
    saida = np.full((len(itens),) + forma, preenchimento, dtype=dtype)
    for i, item in enumerate(itens):
        if item is not None:
            saida[i] = item
    return saida


def exportar(sessao: Session, equipamento_id: int, inicio, fim, formato: str, destino: Path,
             contexto: ContextoExportacao) -> ResultadoExportacao:
    if formato == "csv":
        return exportar_csv(sessao, equipamento_id, inicio, fim, destino, contexto)
    if formato == "netcdf":
        return exportar_netcdf(sessao, equipamento_id, inicio, fim, destino, contexto)
    raise ValueError(f"formato desconhecido: {formato}")
