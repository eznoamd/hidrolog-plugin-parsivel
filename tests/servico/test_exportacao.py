"""Exportacao do Parsivel: CSV com os campos escalares e NetCDF CF-1.8 (ida e volta)."""

import csv
from datetime import datetime

import netCDF4
import numpy as np
import parsivelreader as pr
import pytest

from app import servico
from hidrolog_parsivel.dados import consultas as parsivel

from .conftest import N_ARQUIVOS, PASTA_DADOS


@pytest.fixture
def com_dados(cadastro, equipamento):
    servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS)
    return equipamento


def test_formatos(com_dados):
    assert [f.codigo for f in servico.listar_formatos_exportacao(com_dados.id)] == ["csv", "netcdf"]


def test_csv(leitor, com_dados, tmp_path):
    resumo = servico.exportar(leitor, com_dados.id, None, None, "csv", tmp_path)
    assert resumo.leituras == N_ARQUIVOS and resumo.tamanho_bytes > 0
    assert resumo.caminho.endswith(".csv")
    with open(resumo.caminho, encoding="utf-8", newline="") as f:
        linhas = list(csv.reader(f))
    cabecalho = linhas[0]
    assert cabecalho[:3] == ["tempo", "arquivo", "corrompido"]
    for coluna in ("intensidade_chuva_mm_h", "refletividade_dBZ", "temperatura_sensor_C",
                   "energia_cinetica_J_m2_h", "intervalo_amostragem_s", "status_sensor"):
        assert coluna in cabecalho
    assert not {"N_d", "v_d", "raw", "n_d"} & set(cabecalho)
    assert len(linhas) == N_ARQUIVOS + 1
    primeira = dict(zip(cabecalho, linhas[1]))
    assert primeira["tempo"] == "2026-10-08T04:08:00"
    registro = pr.ler_arquivo(PASTA_DADOS / "2026100804" / "20261008040800.txt")
    assert float(primeira["intensidade_chuva_mm_h"]) == registro.intensidade_chuva
    assert primeira["intervalo_amostragem_s"] == ""      # formato antigo: sem o campo 09


def test_netcdf_ida_e_volta(leitor, com_dados, tmp_path):
    destino = tmp_path / "saida.nc"
    resumo = servico.exportar(leitor, com_dados.id, None, None, "netcdf", destino)
    assert resumo.caminho == str(destino) and resumo.leituras == N_ARQUIVOS
    registros = parsivel.buscar_registros(leitor, com_dados.id)
    with netCDF4.Dataset(destino) as nc:
        assert nc.Conventions == "CF-1.8"
        assert "institution" not in nc.ncattrs()            # instalação sem pasta de marca
        assert nc.equipamento == "Parsivel teste" and nc.numero_serie == "450123"
        assert {d: len(nc.dimensions[d]) for d in ("time", "diametro", "velocidade")} == \
            {"time": N_ARQUIVOS, "diametro": 32, "velocidade": 32}
        assert np.allclose(nc["diametro"][:], pr.DIAMETRO_CLASSES)
        assert np.allclose(nc["velocidade_largura"][:], pr.LARGURA_VELOCIDADE)
        for nome in ("intensidade_chuva", "N_d", "v_d", "raw", "time"):
            assert nc[nome].units and nc[nome].long_name if nome != "time" else nc[nome].units
        tempos = netCDF4.num2date(nc["time"][:], nc["time"].units, only_use_cftime_datetimes=False,
                                  only_use_python_datetimes=True)
        assert [t.replace(tzinfo=None) for t in tempos] == [r.tempo for r in registros]
        assert list(nc["arquivo"][:]) == [r.arquivo for r in registros]
        intensidade = nc["intensidade_chuva"][:]
        assert np.allclose(intensidade, [r.intensidade_chuva for r in registros])
        assert nc["intervalo_amostragem"][:].mask.all()   # formato antigo: tudo _FillValue
        for i, r in enumerate(registros):
            assert bool(nc["corrompido"][i]) == r.corrompido
            assert np.allclose(nc["N_d"][i], r.N_d, atol=1e-4)
            assert np.allclose(nc["v_d"][i], r.v_d, atol=1e-4)
            if r.raw is None:
                assert nc["raw"][i].mask.all()
            else:
                assert np.array_equal(nc["raw"][i], r.raw)


def test_filtro_de_periodo(leitor, com_dados, tmp_path):
    resumo = servico.exportar(leitor, com_dados.id, datetime(2026, 10, 8), datetime(2026, 10, 8, 4, 12),
                              "netcdf", tmp_path)
    assert resumo.leituras == 3
    assert (resumo.inicio, resumo.fim) == (datetime(2026, 10, 8, 4, 8), datetime(2026, 10, 8, 4, 12))
    assert resumo.caminho.endswith("_202610080000_202610080412.nc")
    vazio = servico.exportar(leitor, com_dados.id, datetime(2030, 1, 1), None, "csv", tmp_path / "v.csv")
    assert vazio.leituras == 0 and vazio.inicio is None


def test_netcdf_institution_vem_da_marca_da_instalacao(leitor, com_dados, tmp_path, monkeypatch):
    marca = tmp_path / "marca"
    marca.mkdir()
    (marca / "marca.toml").write_text('[laboratorio]\nsigla = "LAB"\nnome = "Laboratório X"\n'
                                      '[instituicao]\nsigla = "UNIV"\n', encoding="utf-8")
    monkeypatch.setenv("HIDROLOG_MARCA_DIR", str(marca))
    destino = tmp_path / "saida.nc"
    servico.exportar(leitor, com_dados.id, None, None, "netcdf", destino)
    with netCDF4.Dataset(destino) as nc:
        assert nc.institution == "Laboratório X (LAB); UNIV"

