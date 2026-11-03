"""Fixtures dos testes das abas do Parsivel na janela do Hidrolog: offscreen, banco temporário (HIDROLOG_DADOS_DIR
num tmp), argon2 barato e a janela do app."""

from __future__ import annotations

import logging
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HIDROLOG_PROCESSOS"] = "1"
# o mapa do cadastro não busca ladrilhos na internet durante os testes
os.environ.setdefault("HIDROLOG_MAPA_OFFLINE", "1")

import pytest  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from app import servico  # noqa: E402
from app.nucleo import seguranca  # noqa: E402
from app.nucleo.administracao import criar_master  # noqa: E402
from design.tema import aplicar_tema  # noqa: E402

from hidrolog.nucleo import configuracao, tarefas  # noqa: E402

# 13 leituras reais do Parsivel (1 corrompida), da amostra do plugin
PASTA_DADOS = Path(__file__).resolve().parents[2] / "hidrolog_parsivel" / "amostra"
N_LEITURAS = 13
SENHA = "senha-de-teste"

# argon2 barato nos testes (o padrão leva ~0,1 s por hash de propósito)
seguranca._hasher = PasswordHasher(time_cost=1, memory_cost=64, parallelism=1)


@pytest.fixture(autouse=True)
def sem_erros_no_log(caplog):
    """Erro inesperado da interface vai só para o log (a tela mostra uma frase):
    nos testes, qualquer ERROR do logger "hidrolog" reprova."""
    yield
    erros = [r for r in caplog.records if r.name.startswith("hidrolog") and r.levelno >= logging.ERROR]
    assert not erros, "\n".join(f"{r.name}: {r.getMessage()}" for r in erros)


@pytest.fixture(scope="session", autouse=True)
def tema(qapp):
    tarefas.instalar_coleta_de_lixo(qapp)   # como no app: coleta de lixo só entre as tarefas
    aplicar_tema(qapp, "claro")
    return qapp


@pytest.fixture
def dados_dir(tmp_path, monkeypatch):
    pasta = tmp_path / "dados"
    monkeypatch.setenv("HIDROLOG_DADOS_DIR", str(pasta))
    configuracao.configurar_log()
    return pasta


@pytest.fixture
def banco(dados_dir, qapp):
    b = servico.iniciar()
    yield b
    tarefas.esperar_todas(60000)
    qapp.processEvents()
    servico.encerrar()


@pytest.fixture
def master(banco):
    criar_master(banco, "admin", "Administradora Teste", SENHA)
    return servico.autenticar("admin", SENHA)


@pytest.fixture
def usuarios(master):
    """Um usuário de cada perfil (logins: admin, cad, ler)."""
    servico.criar_usuario(master, "cad", "Carla Cadastro", SENHA, "cadastro")
    servico.criar_usuario(master, "ler", "Lúcio Leitura", SENHA, "leitura")
    return {"master": "admin", "cadastro": "cad", "leitura": "ler"}


@pytest.fixture
def janela(banco, qtbot):
    from hidrolog.aplicacao import JanelaHidrolog

    j = JanelaHidrolog(confirmar_saida=False)
    qtbot.addWidget(j)
    j.resize(1440, 900)
    j.show()
    return j


def entrar(janela, qtbot, login: str, senha: str = SENHA):
    """Faz login pela tela e espera a verificação em segundo plano terminar."""
    janela.login.usuario.setText(login)
    janela.login.senha.setText(senha)
    qtbot.mouseClick(janela.login.botao, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not janela.login.esta_ocupado, timeout=10000)
    return janela.shell


def esperar_tarefas(qtbot, timeout: int = 60000):
    qtbot.waitUntil(lambda: tarefas.ativas() == 0, timeout=timeout)


def importar(master, eq_id, caminho=PASTA_DADOS):
    return servico.importar_caminho(master, eq_id, caminho)
