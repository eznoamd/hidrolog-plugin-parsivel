"""Consultas do plugin Parsivel (leitura+): Plugin.consultas. Mesmo contrato da camada de
servico do nucleo: recebem o Usuario de app.servico.autenticar() e devolvem
dados soltos da sessao.

    from hidrolog_parsivel.dados import consultas as parsivel
    from parsivelreader import graficos

    dados = parsivel.buscar_dados(usuario, equipamento_id, inicio, fim)
    graficos.grafico_serie_temporal(dados)      # mesmo formato de pr.concatenar()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import parsivelreader as pr
from parsivelreader import RegistroParsivel
from sqlalchemy import Integer, cast, func, select

from hidrolog_nucleo.plugin import Usuario, obter_equipamento_orm, sessao_autorizada
from .conversao import bytes_para_matriz, bytes_para_vetor, leitura_para_registro
from .modelos import ParsivelLeitura

CODIGO = "parsivel"


@dataclass(frozen=True)
class ResumoLeituras:
    equipamento_id: int
    leituras: int
    validas: int
    corrompidas: int
    inicio: Optional[datetime]
    fim: Optional[datetime]


def _filtros(equipamento_id, inicio, fim, incluir_corrompidas=True):
    filtros = [ParsivelLeitura.equipamento_id == equipamento_id]
    if inicio is not None:
        filtros.append(ParsivelLeitura.tempo >= inicio)
    if fim is not None:
        filtros.append(ParsivelLeitura.tempo <= fim)
    if not incluir_corrompidas:
        filtros.append(ParsivelLeitura.corrompido.is_(False))
    return filtros


def _consultar(usuario, equipamento_id, inicio, fim, incluir_corrompidas, limite=None):
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        obter_equipamento_orm(sessao, equipamento_id, CODIGO)
        consulta = (select(ParsivelLeitura)
                    .where(*_filtros(equipamento_id, inicio, fim, incluir_corrompidas))
                    .order_by(ParsivelLeitura.tempo))
        if limite is not None:
            consulta = consulta.limit(limite)
        return list(sessao.scalars(consulta))


def buscar_registros(usuario: Usuario, equipamento_id: int, inicio: Optional[datetime] = None,
                     fim: Optional[datetime] = None, incluir_corrompidas: bool = True) -> list[RegistroParsivel]:
    """Leituras em [inicio, fim] como RegistroParsivel (parsivelreader), em ordem de tempo."""
    return [leitura_para_registro(l) for l in _consultar(usuario, equipamento_id, inicio, fim, incluir_corrompidas)]


def buscar_dados(usuario: Usuario, equipamento_id: int, inicio: Optional[datetime] = None,
                 fim: Optional[datetime] = None) -> dict:
    """Leituras em [inicio, fim] no formato de pr.concatenar(): dict de
    arrays numpy (tempo, um array por campo, N_d, v_d, raw, intervalo, D,
    vel, descartados), pronto para pr.detectar_eventos() e
    parsivelreader.graficos. As corrompidas ficam de fora (contadas em
    "descartados"), como no concatenar."""
    return pr.concatenar(buscar_registros(usuario, equipamento_id, inicio, fim))


def resumo_leituras(usuario: Usuario, equipamento_id: int, inicio: Optional[datetime] = None,
                    fim: Optional[datetime] = None) -> ResumoLeituras:
    """Quantas leituras (validas/corrompidas) o equipamento tem e o periodo coberto."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        obter_equipamento_orm(sessao, equipamento_id, CODIGO)
        total, corrompidas, primeira, ultima = sessao.execute(
            select(
                func.count(ParsivelLeitura.id),
                func.coalesce(func.sum(cast(ParsivelLeitura.corrompido, Integer)), 0),
                func.min(ParsivelLeitura.tempo),
                func.max(ParsivelLeitura.tempo),
            ).where(*_filtros(equipamento_id, inicio, fim))
        ).one()
        return ResumoLeituras(equipamento_id, total, total - corrompidas, corrompidas, primeira, ultima)


_FORA_DO_DICT = {"n_d", "v_d", "raw", "id"}


def buscar_leituras(usuario: Usuario, equipamento_id: int, inicio: Optional[datetime] = None,
                    fim: Optional[datetime] = None, limite: Optional[int] = None,
                    incluir_vetores: bool = False) -> list[dict]:
    """Leituras como dicts simples (para JSON/tabelas), corrompidas incluidas.
    Com incluir_vetores, n_d/v_d viram listas de 32 e raw lista 32x32."""
    saida = []
    for leitura in _consultar(usuario, equipamento_id, inicio, fim, True, limite):
        dados = {c.key: getattr(leitura, c.key) for c in ParsivelLeitura.__table__.columns
                 if c.key not in _FORA_DO_DICT}
        if incluir_vetores:
            for chave, conversao in (("n_d", bytes_para_vetor), ("v_d", bytes_para_vetor),
                                     ("raw", bytes_para_matriz)):
                valor = conversao(getattr(leitura, chave))
                dados[chave] = None if valor is None else valor.tolist()
        saida.append(dados)
    return saida
