"""Rotas de consulta do Parsivel (casca fina sobre servico.py)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from hidrolog_nucleo.plugin import usuario_da_api

from . import consultas as servico

usuario_atual = usuario_da_api()

rotas = APIRouter(prefix="/parsivel", tags=["parsivel"])


@rotas.get("/equipamentos/{equipamento_id}/resumo")
def resumo(equipamento_id: int, inicio: Optional[datetime] = None, fim: Optional[datetime] = None,
           usuario=Depends(usuario_atual)):
    return servico.resumo_leituras(usuario, equipamento_id, inicio, fim)


@rotas.get("/equipamentos/{equipamento_id}/leituras")
def leituras(equipamento_id: int, inicio: Optional[datetime] = None, fim: Optional[datetime] = None,
             limite: int = Query(1000, ge=1, le=20000), vetores: bool = False,
             usuario=Depends(usuario_atual)):
    """Leituras em [inicio, fim] (ISO 8601, horario do XLink). vetores=true
    inclui n_d, v_d (32) e raw (32x32)."""
    return servico.buscar_leituras(usuario, equipamento_id, inicio, fim, limite, vetores)
