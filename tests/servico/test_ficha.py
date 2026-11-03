"""Ficha do Parsivel: so campos lidos das leituras, migracao v1 -> v2 e o
intervalo de amostragem (campo 09) usado na regra de lacunas."""

from app import servico

from .conftest import PASTA_DADOS


def test_parsivel_so_tem_campos_das_leituras(cadastro):
    campos = {c.chave: c for c in servico.ficha_do_tipo("parsivel")}
    assert set(campos) == {"intervalo_amostragem_s", "firmware", "numero_serie_lido"}
    assert all(c.origem == "leituras" for c in campos.values())
    eq = servico.criar_equipamento(cadastro, "parsivel", "P1", latitude="-29,7", longitude=-53.71)
    assert eq.atributos == {} and eq.versao_ficha == 2


def test_parsivel_ficha_v1_perde_intervalo_e_altura():
    from hidrolog_parsivel.ficha import migrar_atributos

    antigos = {"intervalo_esperado_s": 60, "altura_instalacao_m": 1.2, "firmware": "2.11.6"}
    assert migrar_atributos(dict(antigos), 1) == {"firmware": "2.11.6"}
    assert migrar_atributos(dict(antigos), 2) == antigos


def test_campos_somente_leitura_vem_das_leituras(cadastro):
    eq = servico.criar_equipamento(cadastro, "parsivel", "P1", atributos={"firmware": "digitado"})
    assert "firmware" not in eq.atributos                     # nao editavel: o digitado e ignorado
    novo = (PASTA_DADOS / "2026100804" / "20261008041600.txt").read_bytes() + b"09:00120\n13:450994\n14:2.11.6\n"
    servico.importar_arquivos(cadastro, eq.id, [("20261008041600.txt", novo)])
    eq = servico.obter_equipamento(cadastro, eq.id)
    assert eq.atributos["firmware"] == "2.11.6" and eq.atributos["numero_serie_lido"] == "450994"
    assert eq.atributos["intervalo_amostragem_s"] == 120
    # dados antigos (sem os campos 13/14) nao apagam o que ja se sabe
    servico.importar_caminho(cadastro, eq.id, PASTA_DADOS / "2026101417")
    assert servico.obter_equipamento(cadastro, eq.id).atributos["firmware"] == "2.11.6"


def _lacunas(cadastro, eq_id):
    return [o for o in servico.listar_ocorrencias(cadastro, eq_id) if o.codigo_regra == "leituras_faltando"]


def test_leituras_faltando_usa_o_campo_09(cadastro):
    """Com o campo 09 (script novo), o intervalo vem das leituras; sem ele
    (script antigo), vale o padrao do plugin (120 s). Nada e digitado."""
    pasta = PASTA_DADOS / "2026100804"
    nomes = ["20261008040800.txt", "20261008041000.txt", "20261008041400.txt"]   # buraco de 4 min antes da 3a
    antigo = servico.criar_equipamento(cadastro, "parsivel", "Script antigo")
    servico.importar_arquivos(cadastro, antigo.id, [(n, (pasta / n).read_bytes()) for n in nomes])
    [o] = _lacunas(cadastro, antigo.id)
    assert "1 leitura(s) faltando" in o.mensagem and "120 s, padrão" in o.mensagem
    novo = servico.criar_equipamento(cadastro, "parsivel", "Script novo")
    servico.importar_arquivos(cadastro, novo.id, [(n, (pasta / n).read_bytes() + b"09:00060\n") for n in nomes])
    [o] = _lacunas(cadastro, novo.id)
    assert "60 s, campo 09" in o.mensagem
    assert servico.obter_equipamento(cadastro, novo.id).atributos["intervalo_amostragem_s"] == 60

