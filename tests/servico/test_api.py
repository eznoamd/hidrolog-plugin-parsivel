"""Rotas da API do Parsivel (/parsivel/...)."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import criar_app

from .conftest import N_ARQUIVOS, SENHA


def _token(cliente, login):
    resposta = cliente.post("/login", json={"login": login, "senha": SENHA})
    assert resposta.status_code == 200, resposta.text
    return {"Authorization": f"Bearer {resposta.json()['token']}"}


@pytest.fixture
def cliente(banco, master, cadastro, leitor, equipamento):
    with TestClient(criar_app(iniciar_banco=False)) as c:
        yield c


def test_leitura_nao_envia_mas_consulta_e_exporta(cliente, equipamento, zip_sd):
    cab = _token(cliente, "ler")
    resposta = cliente.post(f"/equipamentos/{equipamento.id}/envios", headers=cab,
                            files={"arquivos": ("SD.zip", zip_sd.read_bytes(), "application/zip")})
    assert resposta.status_code == 403
    assert cliente.post("/usuarios", headers=_token(cliente, "cad"),
                        json={"login": "x", "nome": "x", "senha": SENHA}).status_code == 403

    resposta = cliente.post(f"/equipamentos/{equipamento.id}/envios/local", headers=_token(cliente, "cad"),
                            json={"caminho": str(zip_sd)})
    assert resposta.json()["canal"] == "local" and resposta.json()["novas"] == N_ARQUIVOS

    assert len(cliente.get("/envios", headers=cab).json()) == 1
    resumo = cliente.get(f"/parsivel/equipamentos/{equipamento.id}/resumo", headers=cab).json()
    assert (resumo["leituras"], resumo["validas"], resumo["corrompidas"]) == (N_ARQUIVOS, 12, 1)
    leituras = cliente.get(f"/parsivel/equipamentos/{equipamento.id}/leituras", headers=cab,
                           params={"inicio": "2026-10-08T00:00:00", "fim": "2026-10-08T23:59:59",
                                   "vetores": "true"}).json()
    assert len(leituras) == 7 and len(leituras[0]["raw"]) == 32

    resposta = cliente.get("/exportar", headers=cab, params={"equipamento_id": equipamento.id, "formato": "csv"})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "attachment" in resposta.headers["content-disposition"]
    assert resposta.text.splitlines()[0].startswith("tempo,arquivo,corrompido,intensidade_chuva_mm_h")
    assert len(resposta.text.splitlines()) == N_ARQUIVOS + 1

