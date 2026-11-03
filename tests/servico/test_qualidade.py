"""Regras de qualidade do Parsivel (campos 01, 11/93, 17, 18, 09...)."""

import csv
import re

from app import servico

from .conftest import PASTA_DADOS

ARQ = PASTA_DADOS / "2026100804"


def _arquivo(nome: str, **campos) -> tuple[str, bytes]:
    """Um .txt real da amostra com alguns campos trocados (ou acrescentados)."""
    texto = (ARQ / nome).read_text()
    for campo, valor in campos.items():
        linha = f"{campo}:{valor}"
        if re.search(rf"^{campo}:", texto, re.M):
            texto = re.sub(rf"^{campo}:.*$", linha, texto, flags=re.M)
        else:
            texto += linha + "\n"
    return nome, texto.encode()


def _codigos(cadastro, eq_id, **kw):
    return sorted(o.codigo_regra for o in servico.listar_ocorrencias(cadastro, eq_id, **kw))


def test_regras_de_leitura_do_parsivel(cadastro, equipamento, banco, tmp_path):
    arquivos = [
        _arquivo("20261008040800.txt", **{"18": "1"}),                    # status 1 (lentes sujas)
        _arquivo("20261008041000.txt", **{"11": "09999"}),                # 11 != soma da 93
        _arquivo("20261008041200.txt", **{"01": "0450.000"}),             # intensidade impossivel
        _arquivo("20261008041400.txt"),                                   # normal
    ]
    resumo = servico.importar_arquivos(cadastro, equipamento.id, arquivos)
    assert resumo.novas == 4 and resumo.ocorrencias >= 3
    leitura = servico.listar_ocorrencias(cadastro, equipamento.id, nivel="leitura")
    assert sorted((o.codigo_regra, o.severidade, str(o.tempo)) for o in leitura) == [
        ("intensidade_impossivel", "suspeita", "2026-10-08 04:12:00"),
        ("particulas_vs_matriz", "suspeita", "2026-10-08 04:10:00"),
        ("status_sensor", "suspeita", "2026-10-08 04:08:00"),
    ]
    assert any("450,0" in o.mensagem or "450.0" in o.mensagem for o in leitura)
    suspeitas = servico.tempos_suspeitos(cadastro, equipamento.id)
    assert {t.strftime("%H:%M") for t in suspeitas} == {"04:08", "04:10", "04:12"}
    # reimportar nao duplica ocorrencias (so as leituras novas passam pelas regras de leitura)
    servico.importar_arquivos(cadastro, equipamento.id, arquivos)
    assert len(servico.listar_ocorrencias(cadastro, equipamento.id, nivel="leitura")) == 3
    # exportacao leva a coluna de qualidade
    r = servico.exportar(cadastro, equipamento.id, None, None, "csv", tmp_path)
    with open(r.caminho, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    assert [l["qualidade"] for l in linhas] == ["status_sensor", "particulas_vs_matriz", "intensidade_impossivel", ""]


def test_regras_de_envio_e_de_equipamento(cadastro, equipamento):
    servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS)       # 08/10 a 21/10, com lacunas
    abertas = servico.listar_ocorrencias(cadastro, equipamento.id)
    por_codigo = {o.codigo_regra: o for o in abertas}
    assert por_codigo["leituras_faltando"].nivel == "envio" and por_codigo["leituras_faltando"].severidade == "aviso"
    assert por_codigo["sem_dados"].nivel == "equipamento" and por_codigo["sem_dados"].severidade == "alerta"
    assert "sem dados há" in por_codigo["sem_dados"].mensagem
    resumo = servico.resumo_qualidade(cadastro)[equipamento.id]
    assert resumo.alertas == 1 and resumo.avisos >= 1
    # reavaliar nao duplica a ocorrencia aberta do equipamento
    servico.reavaliar_equipamentos()
    assert _codigos(cadastro, equipamento.id, nivel="equipamento") == ["sem_dados"]
    # com o limite maior, a condicao deixa de valer e a ocorrencia e resolvida sozinha
    servico.configurar_regra(cadastro, equipamento.id, "sem_dados", {"dias": 3650})
    assert _codigos(cadastro, equipamento.id, nivel="equipamento") == []
    resolvida = servico.listar_ocorrencias(cadastro, equipamento.id, abertas=False, nivel="equipamento")[0]
    assert resolvida.resolvida_em is not None and resolvida.resolvida_por == ""


def test_tensao_baixa(cadastro, equipamento):
    arquivos = [_arquivo(n, **{"17": "10.2"}) for n in ("20261008040800.txt", "20261008041000.txt")]
    servico.importar_arquivos(cadastro, equipamento.id, arquivos)
    assert "tensao_baixa" in _codigos(cadastro, equipamento.id, nivel="equipamento")



def test_regras_do_plugin(leitor, equipamento):
    regras = {r.codigo: r for r in servico.listar_regras(leitor, equipamento.id)}
    assert set(regras) == {"status_sensor", "particulas_vs_matriz", "intensidade_impossivel", "leituras_faltando",
                           "deriva_relogio", "sem_dados", "tensao_baixa", "laser_caindo"}
    assert regras["intensidade_impossivel"].parametros == {"limite_mm_h": 300.0}
