"""RegistroParsivel <-> linha da tabela parsivel_leitura, e o formato dos vetores.

Formato dos binarios (tudo little-endian, recuperavel so com numpy):

    n_d (90), v_d (91): 32 valores float32 seguidos, 128 bytes, sem zlib
                        (128 bytes nao compensam comprimir).
    raw (93):           zlib( 1024 valores int16, ordem C de uma matriz
                        32x32 [velocidade, diametro] ).
                        O campo 93 tem 3 digitos por classe (0-999), entao
                        cabe em int16; como a matriz e quase toda zero, o
                        zlib leva os 2048 bytes a algumas dezenas.

Os campos 90 e 91 tem 3 casas decimais; na volta os valores sao
arredondados para 3 casas, o que devolve exatamente o float64 que a
parsivelreader leu do arquivo.

Ler sem esta biblioteca:

    np.frombuffer(linha.n_d, "<f4")
    np.frombuffer(zlib.decompress(linha.raw), "<i2").reshape(32, 32)
"""

from __future__ import annotations

import dataclasses
import zlib
from typing import Optional

import numpy as np
from parsivelreader import N_CLASSES, RegistroParsivel

_DTYPE_VETOR = np.dtype("<f4")
_DTYPE_MATRIZ = np.dtype("<i2")
_CASAS_DECIMAIS = 3

# atributos do RegistroParsivel que viram colunas com o mesmo nome
_ESCALARES = [
    f.name for f in dataclasses.fields(RegistroParsivel)
    if f.name not in ("tempo", "arquivo", "corrompido", "N_d", "v_d", "raw")
]


def vetor_para_bytes(vetor: Optional[np.ndarray]) -> Optional[bytes]:
    if vetor is None:
        return None
    vetor = np.asarray(vetor)
    if vetor.shape != (N_CLASSES,):
        raise ValueError(f"vetor com forma {vetor.shape}, esperado ({N_CLASSES},)")
    return vetor.astype(_DTYPE_VETOR).tobytes()


def bytes_para_vetor(dados: Optional[bytes]) -> Optional[np.ndarray]:
    if dados is None:
        return None
    vetor = np.frombuffer(dados, dtype=_DTYPE_VETOR).astype(float)
    return np.round(vetor, _CASAS_DECIMAIS)


def matriz_para_bytes(matriz: Optional[np.ndarray]) -> Optional[bytes]:
    if matriz is None:
        return None
    matriz = np.asarray(matriz)
    if matriz.shape != (N_CLASSES, N_CLASSES):
        raise ValueError(f"matriz com forma {matriz.shape}, esperado ({N_CLASSES}, {N_CLASSES})")
    limite = np.iinfo(_DTYPE_MATRIZ)
    if np.any(matriz != np.round(matriz)) or matriz.min() < limite.min or matriz.max() > limite.max:
        raise ValueError("matriz 93 com valor que nao e contagem inteira de 16 bits")
    return zlib.compress(matriz.astype(_DTYPE_MATRIZ).tobytes())


def bytes_para_matriz(dados: Optional[bytes]) -> Optional[np.ndarray]:
    if dados is None:
        return None
    matriz = np.frombuffer(zlib.decompress(dados), dtype=_DTYPE_MATRIZ)
    return matriz.reshape(N_CLASSES, N_CLASSES).astype(float)


def registro_para_linha(registro: RegistroParsivel) -> dict:
    """Dict com as colunas da tabela parsivel_leitura (sem ids)."""
    linha = {attr: getattr(registro, attr) for attr in _ESCALARES}
    linha.update(
        tempo = registro.tempo,
        arquivo = registro.arquivo,
        corrompido = registro.corrompido,
        n_d = vetor_para_bytes(registro.N_d),
        v_d = vetor_para_bytes(registro.v_d),
        raw = matriz_para_bytes(registro.raw),
    )
    return linha


def leitura_para_registro(leitura) -> RegistroParsivel:
    """Linha de parsivel_leitura (ParsivelLeitura ou Row) -> RegistroParsivel,
    pronto para pr.concatenar() e os graficos da parsivelreader."""
    return RegistroParsivel(
        tempo = leitura.tempo,
        arquivo = leitura.arquivo,
        corrompido = leitura.corrompido,
        N_d = bytes_para_vetor(leitura.n_d),
        v_d = bytes_para_vetor(leitura.v_d),
        raw = bytes_para_matriz(leitura.raw),
        **{attr: getattr(leitura, attr) for attr in _ESCALARES},
    )
