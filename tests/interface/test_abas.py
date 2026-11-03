"""Página do equipamento Parsivel: as 5 abas do plugin com dados (sem seletor de
equipamento dentro delas), o período no cabeçalho e os estados vazios."""

from datetime import date

from app import servico
from design.componentes import FiguraIncorporada, SeletorEquipamentoPeriodo

from .conftest import entrar, esperar_tarefas, importar

ABAS = ["visao", "serie", "eventos", "matriz", "diagnostico"]


def abrir_aba(pagina, qtbot, chave):
    pagina.abas.ir_para(chave)
    esperar_tarefas(qtbot)
    aba = pagina.abas.widget(chave)
    qtbot.waitUntil(lambda: aba.conteudo.isVisible() or aba.sem_dados.isVisible(), timeout=10000)
    return aba


def test_abas_do_parsivel_com_dados(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "parsivel", "Parsivel 1", numero_serie="450123", local="Telhado")
    importar(master, eq.id)
    shell = entrar(janela, qtbot, "ler")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    assert pagina.titulo.text() == "Parsivel 1"
    assert pagina.subtitulo.text() == "OTT Parsivel2 · nº 450123 · Telhado"
    assert pagina.abas.titulos() == ["Visão geral", "Série temporal", "Eventos de chuva", "Matriz D × V",
                                     "Diagnóstico", "Qualidade", "Envios", "Exportar", "Cadastro"]   # leitura: sem Importar
    assert pagina.periodo.valores() == (date(2026, 10, 8), date(2026, 10, 21))
    for chave in ABAS:
        aba = abrir_aba(pagina, qtbot, chave)
        assert aba.conteudo.isVisible(), chave
        assert aba.resultado.n == 12                     # 13 lidas, 1 corrompida descartada
        assert not aba.findChildren(SeletorEquipamentoPeriodo)       # nenhum seletor dentro da aba
        assert not aba.aviso.isVisible(), aba.aviso.texto.text()
        figs = aba.conteudo.findChildren(FiguraIncorporada)
        assert figs, chave
        for f in figs:
            if f.figura is not None:
                assert f.figura._suptitle is None or not f.figura._suptitle.get_visible()
    eventos = pagina.abas.widget("eventos")
    assert eventos.tabela.linhas() and eventos.figura.figura is not None
    diag = pagina.abas.widget("diagnostico")
    assert "formato antigo" in " ".join(w.texto.text() for w in diag.conteudo.findChildren(type(diag.aviso)))
    # o cache é compartilhado entre as abas (mesmo contexto)
    assert diag.cache.em_cache(diag.contexto) is not None
    # o equipamento entrou nos Recentes
    assert "equipamento.%d" % eq.id in shell._secoes["recentes"].paginas[0].chave


def test_periodo_sem_leituras_mostra_estado_vazio(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "parsivel", "Parsivel 1")
    importar(master, eq.id)
    entrar(janela, qtbot, "admin")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    abrir_aba(pagina, qtbot, "visao")
    pagina.definir_periodo(date(2026, 10, 1), date(2026, 10, 2))
    esperar_tarefas(qtbot)
    visao = pagina.abas.widget("visao")
    qtbot.waitUntil(lambda: visao.sem_dados.isVisible(), timeout=10000)
    assert "não tem leituras válidas" in visao.sem_dados.vazio.descricao.text()
    # o período vale para as outras abas
    serie = abrir_aba(pagina, qtbot, "serie")
    assert serie.sem_dados.isVisible()
    pagina.periodo_completo()
    esperar_tarefas(qtbot)
    qtbot.waitUntil(lambda: serie.conteudo.isVisible(), timeout=10000)


def test_importacao_atualiza_a_pagina(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "parsivel", "Parsivel 1")
    entrar(janela, qtbot, "cad")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    visao = abrir_aba(pagina, qtbot, "visao")
    assert visao.sem_dados.isVisible()
    importar(master, eq.id)
    janela.ctx.dados_alterados.emit("envios")
    esperar_tarefas(qtbot)
    qtbot.waitUntil(lambda: visao.conteudo.isVisible(), timeout=10000)
    assert pagina.periodo.valores() == (date(2026, 10, 8), date(2026, 10, 21))
    envios = pagina.abas.ir_para("envios")
    assert len(envios.tabela.linhas()) == 1


def test_abas_comuns(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "parsivel", "Parsivel 1", numero_serie="450123")
    shell = entrar(janela, qtbot, "cad")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    imp = pagina.abas.ir_para("importar")
    assert imp.equipamento.currentData() == eq.id and not imp.equipamento.isEnabled()
    exp = pagina.abas.ir_para("exportar")
    assert exp.seletor.equipamento.currentData() == eq.id and exp.formato.count() == 2
    cad = pagina.abas.ir_para("cadastro")
    assert cad.valores_sensor["Nº de série registrado"] == "450123" and cad.editar.isVisible()
    d = cad.abrir_edicao()
    d.nome.setText("Parsivel renomeado")
    d.botao_confirmar.click()
    qtbot.waitUntil(lambda: pagina.titulo.text() == "Parsivel renomeado", timeout=5000)
    assert shell._paginas["equipamento.%d" % eq.id].botao.text() == "Parsivel renomeado"


def test_recentes_guardados_por_usuario(usuarios, master, janela, qtbot):
    eqs = [servico.criar_equipamento(master, "parsivel", f"Parsivel {i}") for i in range(7)]
    entrar(janela, qtbot, "ler")
    for eq in eqs:
        janela.ctx.abrir_equipamento(eq.id)
    recentes = [p.titulo for p in janela.shell._secoes["recentes"].paginas]
    assert recentes == ["Parsivel 6", "Parsivel 5", "Parsivel 4", "Parsivel 3", "Parsivel 2"]
    janela.encerrar_sessao()
    shell = entrar(janela, qtbot, "ler")
    assert [p.titulo for p in shell._secoes["recentes"].paginas] == recentes
