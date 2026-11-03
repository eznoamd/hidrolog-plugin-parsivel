"""Regras de qualidade do Parsivel (plano, secao 11.1). Nenhuma altera dados:
elas so marcam leituras, envios e o equipamento.

Leitura:      status 18 != 0; particulas (11) != soma da matriz 93; intensidade
              acima do limite fisico.
Envio:        leituras faltando (pelo campo 09 ou, sem ele, pelo intervalo padrao); relogio do
              sensor (20/21) desviando do XLink (nome do arquivo).
Equipamento:  sem dados ha N dias; tensao (17) baixa nas ultimas 24 h de dados;
              amplitude do laser (10) caindo.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select

from hidrolog_nucleo.plugin import Ocorrencia, Regra

from .dados.conversao import bytes_para_matriz
from .dados.modelos import ParsivelLeitura as L


def _particulas_vs_matriz(ctx) -> list[Ocorrencia]:
    """Campo 11 (particulas validadas) diferente da soma da matriz 93."""
    tolerancia = ctx.parametros["tolerancia_pct"] / 100
    minimo = ctx.parametros["diferenca_minima"]
    saida = []
    for linha in ctx.linhas:
        n, raw = linha.get("n_particulas"), linha.get("raw")
        if n is None or raw is None:
            continue
        soma = float(bytes_para_matriz(raw).sum())
        diferenca = abs(n - soma)
        if diferenca > minimo and diferenca > tolerancia * max(n, soma):
            saida.append(Ocorrencia(f"campo 11 = {n:.0f} partículas, mas a matriz 93 soma {soma:.0f}",
                                    linha["tempo"]))
    return saida


def _intervalo_das_leituras(ctx) -> float | None:
    """Intervalo de amostragem mais comum (campo 09) nas leituras do periodo, ou
    None se elas nao trazem o campo (dados do script antigo do XLink)."""
    valores = sorted(ctx.sessao.scalars(select(L.intervalo_amostragem).where(
        L.equipamento_id == ctx.equipamento.id, L.tempo >= ctx.inicio, L.tempo <= ctx.fim,
        L.intervalo_amostragem.isnot(None), L.intervalo_amostragem > 0)))
    return float(valores[len(valores) // 2]) if valores else None


def _leituras_faltando(ctx) -> list[Ocorrencia]:
    """Lacunas maiores que fator x intervalo de amostragem no periodo do envio.
    O intervalo vem do campo 09 das leituras; sem ele, do parametro intervalo_padrao_s."""
    if ctx.inicio is None or ctx.fim is None:
        return []
    lido = _intervalo_das_leituras(ctx)
    intervalo = lido or float(ctx.parametros["intervalo_padrao_s"])
    origem = "campo 09" if lido else "padrão para dados sem o campo 09"
    limite = intervalo * ctx.parametros["fator_lacuna"]
    tempos = list(ctx.sessao.scalars(select(L.tempo).where(L.equipamento_id == ctx.equipamento.id,
                                                           L.tempo >= ctx.inicio, L.tempo <= ctx.fim)
                                     .order_by(L.tempo)))
    lacunas = [(a, b) for a, b in zip(tempos, tempos[1:]) if (b - a).total_seconds() > limite]
    if not lacunas:
        return []
    faltando = sum(round((b - a).total_seconds() / intervalo) - 1 for a, b in lacunas)
    if faltando < ctx.parametros["minimo_faltando"]:
        return []
    a, b = max(lacunas, key=lambda par: par[1] - par[0])
    return [Ocorrencia(f"{faltando} leitura(s) faltando em {len(lacunas)} lacuna(s) (intervalo de "
                       f"{intervalo:.0f} s, {origem}); a maior: {a:%d/%m/%Y %H:%M} a {b:%d/%m/%Y %H:%M}", a)]


def _deriva_relogio(ctx) -> list[Ocorrencia]:
    """Relogio do sensor (campos 20/21) desviando do relogio do XLink (nome do arquivo)."""
    if ctx.inicio is None:
        return []
    linhas = ctx.sessao.execute(select(L.tempo, L.data_sensor, L.hora_sensor).where(
        L.equipamento_id == ctx.equipamento.id, L.tempo >= ctx.inicio, L.tempo <= ctx.fim,
        L.hora_sensor.isnot(None), L.data_sensor.isnot(None)))
    pior = None
    for tempo, data, hora in linhas:
        try:
            sensor = datetime.strptime(f"{data} {hora}", "%d.%m.%Y %H:%M:%S")
        except ValueError:
            continue
        desvio = (sensor - tempo).total_seconds()
        if pior is None or abs(desvio) > abs(pior[0]):
            pior = (desvio, tempo)
    if pior is None or abs(pior[0]) <= ctx.parametros["tolerancia_s"]:
        return []
    return [Ocorrencia(f"o relógio do sensor chegou a {pior[0]:+.0f} s do relógio do XLink "
                       f"(tolerância {ctx.parametros['tolerancia_s']:.0f} s)", pior[1])]


def _ultima_leitura(ctx):
    return ctx.sessao.scalar(select(func.max(L.tempo)).where(L.equipamento_id == ctx.equipamento.id))


def _sem_dados(ctx) -> list[Ocorrencia]:
    ultima = _ultima_leitura(ctx)
    dias = ctx.parametros["dias"]
    if ultima is None or ctx.agora - ultima <= timedelta(days=dias):
        return []
    atraso = (ctx.agora - ultima).days
    return [Ocorrencia(f"sem dados há {atraso} dias (última leitura em {ultima:%d/%m/%Y %H:%M}; "
                       f"limite {dias} dias)", ultima)]


def _tensao_baixa(ctx) -> list[Ocorrencia]:
    ultima = _ultima_leitura(ctx)
    if ultima is None:
        return []
    minima = ctx.sessao.scalar(select(func.min(L.tensao)).where(
        L.equipamento_id == ctx.equipamento.id, L.tempo >= ultima - timedelta(hours=24), L.tensao.isnot(None)))
    limite = ctx.parametros["minimo_v"]
    if minima is None or minima >= limite:
        return []
    return [Ocorrencia(f"tensão de alimentação chegou a {minima:.1f} V nas últimas 24 h de dados "
                       f"(mínimo {limite:.1f} V)", ultima)]


def _laser_caindo(ctx) -> list[Ocorrencia]:
    ultima = _ultima_leitura(ctx)
    if ultima is None:
        return []
    def media(ini, fim):
        return ctx.sessao.scalar(select(func.avg(L.amplitude_laser)).where(
            L.equipamento_id == ctx.equipamento.id, L.tempo > ini, L.tempo <= fim, L.amplitude_laser.isnot(None)))
    recente = media(ultima - timedelta(hours=24), ultima)
    antes = media(ultima - timedelta(days=8), ultima - timedelta(hours=24))
    if recente is None or antes is None or antes <= 0:
        return []
    queda = (antes - recente) / antes * 100
    if queda < ctx.parametros["queda_pct"]:
        return []
    return [Ocorrencia(f"amplitude do laser caiu {queda:.0f}% (média {antes:.0f} na semana anterior, "
                       f"{recente:.0f} nas últimas 24 h): limpe as lentes", ultima)]


REGRAS = (
    Regra("status_sensor", "Status do sensor diferente de 0 (campo 18)", nivel="leitura", severidade="suspeita",
          coluna="status_sensor", operador="!=", limite=0,
          mensagem="status do sensor {valor} (campo 18): 1 lentes sujas, 2 sem medida, 3 laser danificado"),
    Regra("particulas_vs_matriz", "Partículas (campo 11) diferentes da soma da matriz 93", nivel="leitura",
          severidade="suspeita", parametros={"tolerancia_pct": 5.0, "diferenca_minima": 2},
          funcao=_particulas_vs_matriz,
          ajuda_parametros={"tolerancia_pct": "diferença relativa aceita (%)",
                            "diferenca_minima": "diferença absoluta aceita (partículas)"}),
    Regra("intensidade_impossivel", "Intensidade acima do limite físico (campo 01)", nivel="leitura",
          severidade="suspeita", parametros={"limite_mm_h": 300.0}, coluna="intensidade_chuva", operador=">",
          limite="limite_mm_h", mensagem="intensidade de {valor:.1f} mm/h acima de {limite_mm_h:.0f} mm/h",
          ajuda_parametros={"limite_mm_h": "intensidade máxima aceitável (mm/h)"}),
    Regra("leituras_faltando", "Leituras faltando no período do envio", nivel="envio", severidade="aviso",
          parametros={"fator_lacuna": 1.5, "minimo_faltando": 1, "intervalo_padrao_s": 120.0},
          funcao=_leituras_faltando,
          ajuda_parametros={"fator_lacuna": "lacuna = intervalo esperado × este fator",
                            "minimo_faltando": "avisa a partir de quantas leituras faltando",
                            "intervalo_padrao_s": "intervalo usado quando as leituras não trazem o campo 09 "
                                                  "(script antigo do XLink) (s)"}),
    Regra("deriva_relogio", "Relógio do sensor desviando do XLink (campos 20/21)", nivel="envio",
          severidade="aviso", parametros={"tolerancia_s": 60.0}, funcao=_deriva_relogio,
          ajuda_parametros={"tolerancia_s": "desvio aceito (s)"}),
    Regra("sem_dados", "Sem dados há muitos dias", nivel="equipamento", severidade="alerta",
          parametros={"dias": 7}, funcao=_sem_dados, ajuda_parametros={"dias": "dias sem leitura"}),
    Regra("tensao_baixa", "Tensão de alimentação baixa (campo 17)", nivel="equipamento", severidade="alerta",
          parametros={"minimo_v": 11.0}, funcao=_tensao_baixa,
          ajuda_parametros={"minimo_v": "tensão mínima nas últimas 24 h de dados (V)"}),
    Regra("laser_caindo", "Amplitude do laser caindo (campo 10)", nivel="equipamento", severidade="alerta",
          parametros={"queda_pct": 20.0}, funcao=_laser_caindo,
          ajuda_parametros={"queda_pct": "queda da média das últimas 24 h em relação à semana anterior (%)"}),
)
