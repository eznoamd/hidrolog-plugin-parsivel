"""Importacao de cartoes SD reais do Parsivel pelo nucleo: contagens, ignorados,
corrompidas, formato antigo e novo, nº de serie, vetores e buscar_dados."""

import zipfile

import numpy as np
import parsivelreader as pr
import pytest
from sqlalchemy import select

from app import servico
from app.nucleo.erros import EnvioRecusado
from hidrolog_parsivel.dados import consultas as parsivel
from hidrolog_parsivel.dados.conversao import (
    bytes_para_matriz, bytes_para_vetor, matriz_para_bytes, vetor_para_bytes)
from hidrolog_parsivel.dados.modelos import ParsivelLeitura

from .conftest import N_ARQUIVOS, PASTA_DADOS


def _confere_sd(resumo, canal, tipo):
    assert resumo.canal == canal and resumo.tipo == tipo
    assert resumo.arquivos_recebidos == N_ARQUIVOS + 2
    assert resumo.ignorados == 2
    assert resumo.leituras == N_ARQUIVOS
    assert resumo.validas == N_ARQUIVOS - 1 and resumo.corrompidas == 1
    assert resumo.novas == N_ARQUIVOS and resumo.duplicadas == 0
    assert str(resumo.inicio) == "2026-10-08 04:08:00" and str(resumo.fim) == "2026-10-21 16:00:00"
    assert "parsivel_erros.log" in resumo.arquivos_ignorados


def test_importar_pasta_local(cadastro, equipamento, pasta_sd):
    _confere_sd(servico.importar_caminho(cadastro, equipamento.id, pasta_sd), "local", "pasta")


def test_importar_zip_com_caminhos_do_windows(cadastro, equipamento, zip_sd):
    with zipfile.ZipFile(zip_sd) as z:
        # orig_filename: o nome como está no arquivo (no Windows, namelist() já troca "\\" por "/")
        assert any("\\" in i.orig_filename for i in z.infolist())
    resumo = servico.importar_caminho(cadastro, equipamento.id, zip_sd)
    _confere_sd(resumo, "local", "zip")
    assert "Sutron/XLink/LogBackup/Sutron_XLink_log_backup_.csv" in resumo.arquivos_ignorados


def test_importar_pasta_de_medicao(cadastro, equipamento):
    resumo = servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS / "2026100804")
    assert (resumo.leituras, resumo.novas, resumo.ignorados) == (7, 7, 0)


def test_reenvio_nao_duplica(cadastro, equipamento, zip_sd, pasta_sd):
    servico.importar_caminho(cadastro, equipamento.id, zip_sd)
    for origem in (zip_sd, pasta_sd):
        resumo = servico.importar_caminho(cadastro, equipamento.id, origem)
        assert resumo.novas == 0 and resumo.duplicadas == N_ARQUIVOS
    assert parsivel.resumo_leituras(cadastro, equipamento.id).leituras == N_ARQUIVOS
    assert len(servico.listar_envios(cadastro, equipamento.id)) == 3


def test_arquivos_ignorados(cadastro, equipamento):
    arq = PASTA_DADOS / "2026102116" / "20261021160000.txt"
    resumo = servico.importar_arquivos(cadastro, equipamento.id, [
        ("parsivel_erros.log", b"x"),
        ("Sutron_XLink_log_backup_.csv", b"x"),
        ("2026100804.txt", b"x"),
        ("20261399999999.txt", b"TYP OP4A\n01:0000.000\n"),     # 14 digitos que nao sao data
        ("20261021160000.txt", arq.read_bytes()),
    ])
    assert (resumo.arquivos_recebidos, resumo.ignorados, resumo.leituras, resumo.novas) == (5, 4, 1, 1)


def test_envio_sem_leituras_do_sensor_e_recusado(cadastro, equipamento):
    """O plugin reconhece a estrutura: sem nenhuma leitura do Parsivel, o envio
    e recusado com o motivo (e nada e registrado)."""
    with pytest.raises(EnvioRecusado, match="AAAAMMDDHHMMSS"):
        servico.importar_arquivos(cadastro, equipamento.id, [
            ("parsivel_erros.log", b"x"), ("Sutron_XLink_log_backup_.csv", b"x"),
            ("20261399999999.txt", b"TYP OP4A\n01:0000.000\n")])
    assert servico.listar_envios(cadastro) == []


def test_corrompida_guardada_com_o_que_deu_para_ler(cadastro, equipamento, banco):
    servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS / "2026101105")
    with banco.sessao() as sessao:
        linha = sessao.scalar(select(ParsivelLeitura).where(ParsivelLeitura.arquivo == "20261011051200.txt"))
        assert linha.corrompido and linha.raw is None
        assert linha.n_d is not None and linha.intensidade_chuva is not None
    dados = parsivel.buscar_dados(cadastro, equipamento.id)
    assert dados["descartados"] == 1 and len(dados["tempo"]) == 1


def test_formato_novo_e_antigo(cadastro, equipamento, banco):
    # campos novos (nov/2026), como CAMPOS_NOVOS dos testes da parsivelreader
    campos_novos = "03:61\n05:RA\n07:42.350\n09:00120\n13:450123\n18:1\n60:00003502\n"
    texto = (PASTA_DADOS / "2026100804" / "20261008041600.txt").read_bytes()
    servico.importar_arquivos(cadastro, equipamento.id, [
        ("20261008041600.txt", texto + campos_novos.encode()),
        ("20261008041800.txt", (PASTA_DADOS / "2026100804" / "20261008041800.txt").read_bytes()),
    ])
    with banco.sessao() as sessao:
        novo, antigo = sessao.scalars(select(ParsivelLeitura).order_by(ParsivelLeitura.tempo)).all()
        assert (novo.codigo_synop_wawa, novo.codigo_metar, novo.intervalo_amostragem) == (61, "RA", 120)
        assert (novo.numero_serie, novo.status_sensor, novo.n_particulas_total) == ("450123", 1, 3502)
        assert antigo.intervalo_amostragem is None and antigo.status_sensor is None
        assert antigo.numero_serie is None and antigo.intensidade_chuva is not None


def test_aviso_numero_de_serie_diferente(cadastro, equipamento):
    texto = (PASTA_DADOS / "2026100804" / "20261008041600.txt").read_bytes() + b"13:999999\n"
    resumo = servico.importar_arquivos(cadastro, equipamento.id, [("20261008041600.txt", texto)])
    assert resumo.avisos and "999999" in resumo.avisos[0]


def test_numero_de_serie_registrado_pela_primeira_importacao(cadastro):
    """Sem nº de série no cadastro, o da primeira importação que o trouxer fica
    registrado; a seguinte, com outro nº, gera o aviso de equipamento errado."""
    eq = servico.criar_equipamento(cadastro, "parsivel", "Parsivel sem serie")
    base = (PASTA_DADOS / "2026100804" / "20261008041600.txt").read_bytes()
    antigo = servico.importar_arquivos(cadastro, eq.id, [("20261008041400.txt", (PASTA_DADOS / "2026100804"
                                                          / "20261008041400.txt").read_bytes())])
    assert not antigo.avisos and servico.obter_equipamento(cadastro, eq.id).numero_serie is None
    resumo = servico.importar_arquivos(cadastro, eq.id, [("20261008041600.txt", base + b"13:450994\n")])
    assert any("450994 registrado" in a for a in resumo.avisos)
    assert servico.obter_equipamento(cadastro, eq.id).numero_serie == "450994"
    outro = servico.importar_arquivos(cadastro, eq.id, [("20261008041800.txt", (PASTA_DADOS / "2026100804"
                                                         / "20261008041800.txt").read_bytes() + b"13:999999\n")])
    assert any("999999" in a and "diferente do cadastrado" in a for a in outro.avisos)
    assert servico.obter_equipamento(cadastro, eq.id).numero_serie == "450994"


def test_ida_e_volta_vetores_e_matriz():
    for registro in pr.ler_pasta(PASTA_DADOS):
        for vetor in (registro.N_d, registro.v_d):
            assert np.array_equal(bytes_para_vetor(vetor_para_bytes(vetor)), vetor)
        if registro.raw is not None:
            dados = matriz_para_bytes(registro.raw)
            assert len(dados) < 2048    # zlib compensa: 32x32 int16 sem compressao = 2048 bytes
            assert np.array_equal(bytes_para_matriz(dados), registro.raw)
    with pytest.raises(ValueError):
        matriz_para_bytes(np.full((32, 32), 0.5))


def test_buscar_dados_igual_ao_concatenar_da_biblioteca(cadastro, equipamento, pasta_sd):
    servico.importar_caminho(cadastro, equipamento.id, pasta_sd)
    do_banco = parsivel.buscar_dados(cadastro, equipamento.id)
    da_biblioteca = pr.concatenar(pr.ler_pasta(PASTA_DADOS))
    assert do_banco.keys() == da_biblioteca.keys()
    for chave, esperado in da_biblioteca.items():
        obtido = do_banco[chave]
        if isinstance(esperado, np.ndarray) and esperado.dtype.kind == "f":
            assert np.array_equal(obtido, esperado, equal_nan=True), chave
        elif isinstance(esperado, np.ndarray):
            assert (obtido == esperado).all(), chave
        else:
            assert obtido == esperado, chave
    # intervalo de tempo
    from datetime import datetime
    so_outubro_8 = parsivel.buscar_dados(cadastro, equipamento.id, datetime(2026, 10, 8), datetime(2026, 10, 8, 23))
    assert len(so_outubro_8["tempo"]) == 7
    linhas = parsivel.buscar_leituras(cadastro, equipamento.id, limite=2, incluir_vetores=True)
    assert len(linhas) == 2 and np.array(linhas[0]["raw"]).shape == (32, 32)


def test_paralelo_da_o_mesmo_resultado(cadastro, equipamento, pasta_sd, monkeypatch, banco):
    """As unidades lidas nos processos do pool (o plugin importado pelo nome do
    modulo do manifesto) dao as mesmas linhas que a leitura neste processo."""
    from app.nucleo import paralelo
    original = paralelo.mapear_lotes
    monkeypatch.setattr(paralelo, "processos", 2)
    monkeypatch.setattr(paralelo, "mapear_lotes",
                        lambda f, itens, **kw: original(f, itens, tamanho_lote=4, minimo_paralelo=1))
    try:
        resumo = servico.importar_caminho(cadastro, equipamento.id, pasta_sd)
    finally:
        paralelo.encerrar()
    assert (resumo.leituras, resumo.novas, resumo.corrompidas) == (N_ARQUIVOS, N_ARQUIVOS, 1)
    with banco.sessao() as sessao:
        arquivos = sorted(sessao.scalars(select(ParsivelLeitura.arquivo)))
    assert arquivos == sorted(p.name for p in PASTA_DADOS.rglob("*.txt"))

