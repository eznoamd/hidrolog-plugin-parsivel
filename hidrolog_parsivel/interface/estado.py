"""Dados das abas do Parsivel: carregados numa thread (contexto.executar) e
guardados num cache por sessao, compartilhado entre as abas, pela chave do
contexto (equipamento, periodo, filtro de qualidade, versao dos dados)."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import numpy as np
import parsivelreader as pr

TAMANHO_CACHE = 4
CHAVE_EXTRAS = "parsivel"


@dataclass
class Resultado:
    equipamento: object
    inicio: Optional[datetime]
    fim: Optional[datetime]
    dados: dict
    eventos: list = field(default_factory=list)
    resumo: object = None
    suspeitas: set = field(default_factory=set)      # tempos das leituras suspeitas (regras de qualidade)
    ocultadas: int = 0                                # suspeitas tiradas pelo filtro "ocultar suspeitas"

    @property
    def n(self) -> int:
        return len(self.dados["tempo"])

    def mascara_suspeitas(self) -> np.ndarray:
        """True nas leituras de `dados` marcadas como suspeitas."""
        if not self.suspeitas or not self.n:
            return np.zeros(self.n, dtype=bool)
        return np.array([para_datetime(t) in self.suspeitas for t in self.dados["tempo"]], dtype=bool)


def para_datetime(v) -> datetime:
    if isinstance(v, datetime):
        return v
    return np.datetime64(v, "us").astype(datetime)


def filtrar(dados: dict, manter: np.ndarray) -> dict:
    """Mesmo dict de pr.concatenar so com as leituras marcadas em `manter`."""
    n = len(dados["tempo"])
    saida = {}
    for chave, valor in dados.items():
        if isinstance(valor, np.ndarray) and valor.ndim >= 1 and valor.shape[0] == n:
            saida[chave] = valor[manter]
        else:
            saida[chave] = valor
    return saida


def carregar_dados(contexto) -> Resultado:
    """Roda numa thread: leituras do periodo, suspeitas e eventos de chuva."""
    consultas = contexto.consultas
    eq = contexto.equipamento
    dados = consultas.buscar_dados(contexto.usuario, eq.id, contexto.inicio, contexto.fim)
    resumo = consultas.resumo_leituras(contexto.usuario, eq.id, contexto.inicio, contexto.fim)
    suspeitas = set(contexto.suspeitas() or ())
    ocultadas = 0
    if suspeitas and len(dados["tempo"]) and contexto.ocultar_suspeitas:
        marcadas = np.array([para_datetime(t) in suspeitas for t in dados["tempo"]], dtype=bool)
        if marcadas.any():
            ocultadas = int(marcadas.sum())
            dados = filtrar(dados, ~marcadas)
    eventos = pr.detectar_eventos(dados) if len(dados["tempo"]) else []
    return Resultado(eq, contexto.inicio, contexto.fim, dados, eventos, resumo, suspeitas, ocultadas)


class CacheParsivel:
    """Um por sessao (em contexto.sessao.extras): resultados por chave do contexto."""

    def __init__(self):
        self._cache: "OrderedDict[tuple, Resultado]" = OrderedDict()
        self._pendentes: dict[tuple, list] = {}

    @classmethod
    def da_sessao(cls, contexto) -> "CacheParsivel":
        extras = getattr(contexto.sessao, "extras", None)
        if extras is None:
            return cls()
        if CHAVE_EXTRAS not in extras:
            extras[CHAVE_EXTRAS] = cls()
        return extras[CHAVE_EXTRAS]

    def em_cache(self, contexto) -> Optional[Resultado]:
        return self._cache.get(contexto.chave())

    def carregar(self, contexto, ao_concluir: Callable[[Resultado], None],
                 ao_falhar: Callable[[BaseException], None]) -> None:
        chave = contexto.chave()
        if chave in self._cache:
            self._cache.move_to_end(chave)
            ao_concluir(self._cache[chave])
            return
        if chave in self._pendentes:
            self._pendentes[chave].append((ao_concluir, ao_falhar))
            return
        self._pendentes[chave] = [(ao_concluir, ao_falhar)]
        if contexto.executar is None:          # sem thread (ex. kit de conformidade): na hora
            try:
                resultado = carregar_dados(contexto)
            except Exception as erro:  # noqa: BLE001
                self._falhou(chave, erro)
                return
            self._pronto(chave, resultado)
            return
        contexto.executar(carregar_dados, contexto, ao_concluir=lambda r, c=chave: self._pronto(c, r),
                          ao_falhar=lambda e, c=chave: self._falhou(c, e), nome="dados do Parsivel")

    def _pronto(self, chave, resultado: Resultado) -> None:
        self._cache[chave] = resultado
        while len(self._cache) > TAMANHO_CACHE:
            self._cache.popitem(last=False)
        for ok, _ in self._pendentes.pop(chave, []):
            ok(resultado)

    def _falhou(self, chave, erro) -> None:
        for _, falha in self._pendentes.pop(chave, []):
            falha(erro)
