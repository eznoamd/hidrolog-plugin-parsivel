"""Ficha do Parsivel: campos que o cadastro do equipamento acrescenta aos comuns.

Nenhum é digitado: todos vêm das leituras e aparecem na aba Cadastro, no bloco
"Informado pelo sensor". O intervalo de amostragem vem do campo 09 (script novo
do XLink); para os dados do script antigo, que não têm o campo, a regra de
leituras faltando usa o parâmetro `intervalo_padrao_s` (120 s, o agendamento
do script antigo), ajustável pela aba Qualidade.
"""

from hidrolog_nucleo.plugin import Campo

VERSAO_FICHA = 2

FICHA = (
    Campo("intervalo_amostragem_s", "Intervalo de amostragem", tipo="inteiro", unidade="s",
          somente_leitura=True, origem="leituras", coluna="intervalo_amostragem",
          ajuda="Lido do campo 09 das leituras (arquivos a partir de nov/2026)."),
    Campo("firmware", "Versão do firmware", tipo="texto", somente_leitura=True, origem="leituras",
          coluna="firmware_iop", ajuda="Lida do campo 14 das leituras (arquivos a partir de nov/2026)."),
    Campo("numero_serie_lido", "Nº de série nas leituras", tipo="texto", somente_leitura=True,
          origem="leituras", coluna="numero_serie",
          ajuda="Lido do campo 13 das leituras (arquivos a partir de nov/2026)."),
)


def migrar_atributos(atributos: dict, versao_antiga: int) -> dict:
    """v1 → v2: o intervalo esperado e a altura do feixe deixaram de ser digitados
    no cadastro (o intervalo passou a vir do campo 09)."""
    if versao_antiga < 2:
        atributos = {k: v for k, v in atributos.items() if k not in ("intervalo_esperado_s", "altura_instalacao_m")}
    return atributos
