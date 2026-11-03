"""Fixtures dos testes do plugin pela camada de servico do Hidrolog: banco
temporario, um usuario de cada perfil, um equipamento Parsivel e copias do
cartao SD de amostra (as 13 leituras reais de hidrolog_parsivel/amostra)."""

import shutil
import zipfile
from pathlib import Path

import pytest
from argon2 import PasswordHasher

from app import servico
from app.config import Configuracao
from app.nucleo import seguranca
from app.nucleo.administracao import criar_master

# 13 leituras reais (formato antigo); 20261011051200.txt nao tem a linha 93 (corrompida)
PASTA_DADOS = Path(__file__).resolve().parents[2] / "hidrolog_parsivel" / "amostra"
N_ARQUIVOS = 13
SENHA = "senha-de-teste"

# argon2 barato nos testes (o padrao leva ~0,1 s por hash de proposito)
seguranca._hasher = PasswordHasher(time_cost=1, memory_cost=64, parallelism=1)


def config_teste(url: str, **mudancas) -> Configuracao:
    valores = dict(database_url=url, max_descompactado=64 * 1024 * 1024, max_arquivo_leitura=1024 * 1024,
                   max_arquivos=100_000, processos=1)
    valores.update(mudancas)
    return Configuracao(**valores)


@pytest.fixture
def banco(tmp_path):
    b = servico.iniciar(config=config_teste(f"sqlite:///{tmp_path / 'teste.db'}"))
    yield b
    servico.encerrar()


@pytest.fixture
def master(banco):
    criar_master(banco, "admin", "Administrador", SENHA)
    return servico.autenticar("admin", SENHA)


@pytest.fixture
def cadastro(master):
    servico.criar_usuario(master, "cad", "Cadastro", SENHA, "cadastro")
    return servico.autenticar("cad", SENHA)


@pytest.fixture
def leitor(master):
    servico.criar_usuario(master, "ler", "Leitura", SENHA, "leitura")
    return servico.autenticar("ler", SENHA)


@pytest.fixture
def equipamento(cadastro):
    return servico.criar_equipamento(cadastro, "parsivel", "Parsivel teste", numero_serie="450123")


@pytest.fixture
def pasta_sd(tmp_path):
    """Copia do SD: as leituras + os arquivos que nao sao leituras."""
    destino = tmp_path / "SD"
    shutil.copytree(PASTA_DADOS, destino, ignore=shutil.ignore_patterns("LEIA-ME*"))
    (destino / "parsivel_erros.log").write_text("20261008041600 resposta invalida nos campos: 93\n")
    log = destino / "Sutron" / "XLink" / "LogBackup"
    log.mkdir(parents=True)
    (log / "Sutron_XLink_log_backup_.csv").write_text("data;evento\n")
    return destino


@pytest.fixture
def zip_sd(tmp_path, pasta_sd):
    """ZIP do SD com nomes no estilo do Windows (separador "\\")."""
    caminho = tmp_path / "SD.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in sorted(pasta_sd.rglob("*")):
            if arq.is_file():
                info = zipfile.ZipInfo.from_file(arq)
                # o nome vai depois de criar a entrada: no Windows, o ZipInfo troca "\\" por "/"
                info.filename = arq.relative_to(pasta_sd).as_posix().replace("/", "\\")
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, arq.read_bytes())
    return caminho
