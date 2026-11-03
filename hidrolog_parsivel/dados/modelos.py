"""Tabela do plugin Parsivel: parsivel_leitura.

Uma linha por arquivo .txt do SD. Unica por (equipamento, tempo): reenviar
o mesmo SD, ou um SD que se sobrepoe a um envio anterior, nao duplica nada.
O numero do campo do Parsivel fica no comentario de cada coluna."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from hidrolog_nucleo.plugin import Base


class ParsivelLeitura(Base):
    """Um arquivo .txt do SD. Campos que o arquivo nao tem ficam NULL (os
    arquivos antigos so tem 01, 02, 11, 12, 17, 19-21, 24, 25, 30-32, 34 e
    90-93). Os vetores 90/91 e a matriz 93 ficam em bytes: ver conversao.py."""

    __tablename__ = "parsivel_leitura"
    __table_args__ = (UniqueConstraint("equipamento_id", "tempo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"))
    envio_id: Mapped[int] = mapped_column(ForeignKey("envio.id"), index=True)
    tempo: Mapped[datetime] = mapped_column(DateTime, comment="do nome do arquivo, relogio do XLink, sem fuso")
    arquivo: Mapped[str] = mapped_column(Text)
    corrompido: Mapped[bool] = mapped_column(Boolean, comment="sem 90, 91 ou 93 completos")

    # medidas
    intensidade_chuva: Mapped[Optional[float]] = mapped_column(Float, comment="01, mm/h")
    chuva_acumulada: Mapped[Optional[float]] = mapped_column(Float, comment="02, mm desde que o sensor ligou")
    codigo_synop_wawa: Mapped[Optional[int]] = mapped_column(Integer, comment="03, tabela 4680")
    codigo_synop_ww: Mapped[Optional[int]] = mapped_column(Integer, comment="04, tabela 4677")
    codigo_metar: Mapped[Optional[str]] = mapped_column(Text, comment="05, tabela 4678")
    refletividade: Mapped[Optional[float]] = mapped_column(Float, comment="07, dBZ (-9.999 = sem gota)")
    visibilidade_mor: Mapped[Optional[float]] = mapped_column(Float, comment="08, m")
    intervalo_amostragem: Mapped[Optional[float]] = mapped_column(Float, comment="09, s")
    n_particulas: Mapped[Optional[float]] = mapped_column(Float, comment="11, particulas validadas")
    temperatura_sensor: Mapped[Optional[float]] = mapped_column(Float, comment="12, C, dentro da carcaca")
    tensao: Mapped[Optional[float]] = mapped_column(Float, comment="17, V")
    inicio_medida: Mapped[Optional[str]] = mapped_column(Text, comment="19, DD.MM.YYYY_hh:mm:ss")
    hora_sensor: Mapped[Optional[str]] = mapped_column(Text, comment="20, hh:mm:ss")
    data_sensor: Mapped[Optional[str]] = mapped_column(Text, comment="21, DD.MM.YYYY")
    chuva_absoluta: Mapped[Optional[float]] = mapped_column(Float, comment="24, mm (no XLink: chuva da leitura)")
    codigo_erro: Mapped[Optional[str]] = mapped_column(Text, comment="25")
    intensidade_16bit_30: Mapped[Optional[float]] = mapped_column(Float, comment="30, mm/h")
    intensidade_16bit_1200: Mapped[Optional[float]] = mapped_column(Float, comment="31, mm/h")
    chuva_acumulada_16bit: Mapped[Optional[float]] = mapped_column(Float, comment="32, mm")
    energia_cinetica: Mapped[Optional[float]] = mapped_column(Float, comment="34, J/(m2 h)")
    n_particulas_total: Mapped[Optional[float]] = mapped_column(Float, comment="60, inclusive as nao validadas")
    n_d: Mapped[Optional[bytes]] = mapped_column(LargeBinary, comment="90, 32 x float32 LE, log10(1/(m3 mm))")
    v_d: Mapped[Optional[bytes]] = mapped_column(LargeBinary, comment="91, 32 x float32 LE, m/s")
    raw: Mapped[Optional[bytes]] = mapped_column(LargeBinary, comment="93, zlib(32x32 int16 LE) [velocidade, diametro]")

    # diagnostico do sensor
    amplitude_laser: Mapped[Optional[float]] = mapped_column(Float, comment="10")
    corrente_aquecimento: Mapped[Optional[float]] = mapped_column(Float, comment="16, A")
    status_sensor: Mapped[Optional[int]] = mapped_column(Integer, comment="18, 0 OK, 1 lentes sujas, 2 sem medida, 3 laser danificado")
    temperatura_placa: Mapped[Optional[float]] = mapped_column(Float, comment="26, C")
    temperatura_cabeca_direita: Mapped[Optional[float]] = mapped_column(Float, comment="27, C")
    temperatura_cabeca_esquerda: Mapped[Optional[float]] = mapped_column(Float, comment="28, C")
    numero_serie: Mapped[Optional[str]] = mapped_column(Text, comment="13")
    firmware_iop: Mapped[Optional[str]] = mapped_column(Text, comment="14")
    firmware_dsp: Mapped[Optional[str]] = mapped_column(Text, comment="15")
