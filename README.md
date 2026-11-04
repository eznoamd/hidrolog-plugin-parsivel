<h1 align="center">Hidrolog · plugin OTT Parsivel2</h1>

<p align="center">
Plugin do <a href="https://github.com/eznoamd/hidrolog">Hidrolog</a> para o disdrômetro <b>OTT Parsivel2</b> com datalogger
<b>XLink 500</b>: importa o cartão SD, confere a qualidade das leituras, mostra eventos de chuva e a
matriz D × V e exporta em CSV e NetCDF.
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="Hidrolog" src="https://img.shields.io/badge/Hidrolog-contrato%201.x-0A7BBB">
  <img alt="parsivelreader" src="https://img.shields.io/badge/parsivelreader-leitura-6BA81E">
  <img alt="NetCDF" src="https://img.shields.io/badge/NetCDF--4-CF--1.8-11557C">
  <img alt="PySide6" src="https://img.shields.io/badge/PySide6-Qt%206-41CD52?logo=qt&logoColor=white">
  <img alt="pytest" src="https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white">
</p>

## 🚀 Quick start

Com o Hidrolog já instalado, o plugin entra pelo gerenciador de plugins do app:

1. Entre com um usuário **master** e abra **Configurações → Plugins → Importar plugin**.
2. Escolha a origem:
   - **Repositório do GitHub**: o link (https://github.com/eznoamd/hidrolog-plugin-parsivel) e a versão (tag), por exemplo
     `v1.0.0`;
   - **Do computador**: o `hidrolog-plugin-parsivel-<versão>.zip` baixado da página de releases, ou
     a pasta dele descompactada.

   Os dois caminhos instalam o mesmo pacote: o `.zip` anexado à release, que já traz a
   `parsivelreader` dentro. O botão "Source code" da release **não** serve, porque não tem a
   biblioteca.
3. Confira a confirmação (OTT Parsivel2, versão, contrato `1.x`, a tabela `parsivel_leitura` e os
   campos do cadastro) e digite a senha do master.
4. **Reinicie o Hidrolog.** Na abertura, o app cria a tabela do plugin, com cópia de segurança do
   banco antes.

Para usar:

1. **Equipamentos → Novo equipamento**, tipo "OTT Parsivel2".
2. **Importar dados**: escolha o equipamento e a pasta do cartão SD do XLink, um `.zip` ou um
   `.rar` dela. Para testar sem um cartão, use a pasta `hidrolog_parsivel/amostra` deste
   repositório (13 leituras reais de out/2026, uma delas corrompida).
3. Abra o equipamento: as abas do plugin (abaixo), **Qualidade**, **Envios** e **Exportar**.

O plugin usa do app o `numpy`, o `netCDF4` e o `matplotlib`, que vêm no Hidrolog instalado; a
`parsivelreader` vem dentro do pacote. Atualizar é o mesmo caminho com uma versão nova; desativar ou remover o plugin nunca apaga os dados.

## Visão geral

O cartão SD do XLink 500 grava um arquivo `AAAAMMDDHHMMSS.txt` por leitura (o nome é o horário da
coleta), em pastas `AAAAMMDDHH`, junto com os logs do XLink e do Parsivel. O plugin reconhece as
leituras, ignora o resto e grava uma linha por leitura na tabela `parsivel_leitura`, com os campos
escalares em colunas e os vetores e a matriz em binário. Reimportar um cartão, ou outro que se
sobrepõe a ele, não duplica nada. A leitura dos arquivos é toda da `parsivelreader`
(`pr.ler_conteudo`): o plugin não refaz o parsing, e as consultas devolvem os dados no mesmo
formato de `pr.concatenar()`, prontos para os gráficos da biblioteca.

| Aba | O que mostra |
|---|---|
| **Visão geral** | Resumo do período selecionado. |
| **Série temporal** | Intensidade, chuva acumulada, Dm e refletividade, com os eventos sombreados. |
| **Eventos de chuva** | Tabela de eventos; ao selecionar um, o espectro N(D) ao longo do tempo. |
| **Matriz D × V** | Gotas por classe de diâmetro e velocidade (campo 93), somando o período. |
| **Diagnóstico** | Status, laser, temperaturas, alimentação e partículas. |

O cadastro do equipamento ganha três campos lidos das leituras (nada é digitado): intervalo de
amostragem (campo 09), firmware (14) e nº de série (13). Os arquivos antigos (até out/2026) não
trazem esses campos.

## Estrutura do repositório

```
hidrolog-plugin-parsivel/
├── hidrolog-plugin.toml     manifesto (o app lê sem executar código)
├── pyproject.toml           pacote e entry point: parsivel = hidrolog_parsivel:PLUGIN
├── requirements-dev.txt     ambiente de desenvolvimento (app, parsivelreader e plugin editáveis)
├── hidrolog_parsivel/
│   ├── __init__.py          o objeto PLUGIN, que junta tudo abaixo
│   ├── ficha.py             campos do cadastro (lidos das leituras)
│   ├── regras.py            regras de qualidade
│   ├── dados/
│   │   ├── modelos.py       tabela parsivel_leitura
│   │   ├── conversao.py     RegistroParsivel <-> linha, formato binário dos vetores
│   │   ├── ingestao.py      reconhecer (plano de importação) e ler (1 arquivo → 1 leitura)
│   │   ├── consultas.py     buscar_dados, buscar_registros, resumo_leituras, buscar_leituras
│   │   ├── exportacao.py    CSV e NetCDF
│   │   ├── rotas.py         rotas da API local
│   │   └── migracoes/       branch "parsivel" do Alembic
│   ├── interface/           as abas (único lugar que importa PySide6, sob demanda)
│   └── amostra/             13 leituras reais para os testes e o kit de conformidade
└── tests/
    ├── servico/             pela camada de serviço do Hidrolog
    └── interface/           as abas na janela do app (pytest-qt, offscreen)
```

## Funcionamento

### Ingestão

- **reconhecer**: cada `.txt` com nome de data vira uma unidade. `parsivel_erros.log`, os logs do
  XLink e qualquer outro arquivo vão para os ignorados sem serem lidos; um nome de 14 dígitos que
  não forma data também. O nº de série (13) e o firmware (14) da leitura mais recente viram
  metadados do envio. Sem nenhuma leitura, o envio é **recusado** com o motivo.
- **ler**: 1 arquivo → 1 leitura, com `pr.ler_conteudo`. Leitura paralela permitida.
- **chave**: `(equipamento_id, tempo)`. Duplicadas, inclusive dentro do próprio envio, são contadas
  e ignoradas; o mesmo dado enviado para **outro** equipamento entra normalmente.
- **tempo**: vem do nome do arquivo (relógio do XLink, sem fuso).
- **corrompidas** (sem os campos 90, 91 ou 93 completos): guardadas com o que foi possível ler e
  `corrompido = true`, para diagnóstico.

### Tabela `parsivel_leitura`

Uma linha por arquivo: `id`, `equipamento_id`, `envio_id`, `tempo`, `arquivo`, `corrompido` e uma
coluna por campo escalar do `RegistroParsivel`, com o número do campo no comentário da coluna
(`dados/modelos.py`). Campo que o arquivo não tem fica `NULL`: os arquivos antigos só têm 01, 02,
11, 12, 17, 19–21, 24, 25, 30–32, 34 e 90–93; os novos têm os 33 campos.

Vetores e matriz, todos little-endian (`dados/conversao.py`):

| Coluna | Campo | Formato |
|---|---|---|
| `n_d` | 90 | 32 × float32 (128 bytes) |
| `v_d` | 91 | 32 × float32 (128 bytes) |
| `raw` | 93 | `zlib(32 × 32 int16)`, ordem C `[velocidade, diâmetro]` |

O campo 93 vai de 0 a 999 e cabe em int16; como a matriz é quase toda zero, o zlib reduz os
2048 bytes a poucas dezenas. Os campos 90 e 91 têm 3 casas decimais, e `bytes_para_vetor`
arredonda na volta, devolvendo exatamente o float64 que a `parsivelreader` leu. Para ler direto
do banco, só com numpy:

```python
np.frombuffer(linha.n_d, "<f4")
np.frombuffer(zlib.decompress(linha.raw), "<i2").reshape(32, 32)
```

### Regras de qualidade

Rodam a cada importação e só marcam leituras, envios ou o equipamento: nunca alteram dados. Os
parâmetros são ajustáveis na aba **Qualidade**.

| Regra | Nível | Dispara quando | Padrão |
|---|---|---|---|
| `status_sensor` | leitura | status (18) ≠ 0 | |
| `particulas_vs_matriz` | leitura | partículas (11) ≠ soma da matriz 93 | 5% e 2 partículas |
| `intensidade_impossivel` | leitura | intensidade (01) acima do limite físico | 300 mm/h |
| `leituras_faltando` | envio | lacuna > fator × intervalo (campo 09 ou padrão) | 1,5 × 120 s |
| `deriva_relogio` | envio | relógio do sensor (20/21) longe do XLink | 60 s |
| `sem_dados` | equipamento | nenhuma leitura há N dias | 7 dias |
| `tensao_baixa` | equipamento | tensão (17) mínima nas últimas 24 h de dados | 11 V |
| `laser_caindo` | equipamento | amplitude (10) das últimas 24 h vs. semana anterior | queda de 20% |

### Consultas

Em `hidrolog_parsivel.dados.consultas`, perfil leitura:

| Função | Retorno |
|---|---|
| `buscar_dados(usuario, equipamento_id, inicio=None, fim=None)` | `dict` no formato de `pr.concatenar()`; corrompidas em `descartados` |
| `buscar_registros(..., incluir_corrompidas=True)` | `list[RegistroParsivel]` |
| `resumo_leituras(...)` | `ResumoLeituras(equipamento_id, leituras, validas, corrompidas, inicio, fim)` |
| `buscar_leituras(..., limite=None, incluir_vetores=False)` | `list[dict]`, para tabelas e JSON |

```python
from hidrolog_parsivel.dados import consultas as parsivel
from parsivelreader import graficos

dados = parsivel.buscar_dados(usuario, eq.id, inicio, fim)
graficos.grafico_serie_temporal(dados)
```

A API local expõe `GET /parsivel/equipamentos/{id}/resumo` e
`GET /parsivel/equipamentos/{id}/leituras` (`inicio`, `fim`, `limite` até 20000, `vetores`).

### Exportação

Os dois formatos leem o banco em blocos de 2000 leituras e escrevem a cada bloco, então períodos
longos não ficam inteiros na memória. As corrompidas entram, marcadas pela coluna `corrompido`.

**CSV** (`csv`): UTF-8, vírgula como separador, ponto decimal, uma linha por leitura, sem os
vetores nem a matriz. Campo vazio = o arquivo não tem o campo. A unidade vai no nome da coluna:

<details>
<summary>Colunas do CSV</summary>

| Coluna | Campo | Coluna | Campo |
|---|---|---|---|
| `tempo` (ISO 8601, sem fuso) | nome | `firmware_dsp` | 15 |
| `arquivo` | | `corrente_aquecimento_A` | 16 |
| `corrompido` (0/1) | | `tensao_V` | 17 |
| `intensidade_chuva_mm_h` | 01 | `status_sensor` | 18 |
| `chuva_acumulada_mm` | 02 | `inicio_medida` | 19 |
| `codigo_synop_wawa` | 03 | `hora_sensor` | 20 |
| `codigo_synop_ww` | 04 | `data_sensor` | 21 |
| `codigo_metar` | 05 | `chuva_absoluta_mm` | 24 |
| `refletividade_dBZ` | 07 | `codigo_erro` | 25 |
| `visibilidade_mor_m` | 08 | `temperatura_placa_C` | 26 |
| `intervalo_amostragem_s` | 09 | `temperatura_cabeca_direita_C` | 27 |
| `amplitude_laser` | 10 | `temperatura_cabeca_esquerda_C` | 28 |
| `n_particulas` | 11 | `intensidade_16bit_30_mm_h` | 30 |
| `temperatura_sensor_C` | 12 | `intensidade_16bit_1200_mm_h` | 31 |
| `numero_serie` | 13 | `chuva_acumulada_16bit_mm` | 32 |
| `firmware_iop` | 14 | `energia_cinetica_J_m2_h` | 34 |
| | | `n_particulas_total` | 60 |

</details>

**NetCDF** (`netcdf`): NetCDF-4, convenções CF-1.8, gerado com `netCDF4` (não xarray, que montaria
o Dataset inteiro na memória) com a dimensão `time` ilimitada, escrita bloco a bloco.

- **Dimensões**: `time` (ilimitada), `diametro` (32), `velocidade` (32), `nv` (2).
- **Coordenadas**: `time` (`seconds since 1970-01-01 00:00:00`, relógio do XLink, sem fuso),
  `diametro` (mm) e `velocidade` (m s-1) com os centros das classes, mais larguras e limites
  (`bounds`), tudo de `parsivelreader.classes`.
- **Por leitura**: `arquivo`, `corrompido` (int8 com `flag_values`/`flag_meanings`) e todos os
  escalares com os nomes do CSV sem o sufixo de unidade (`intensidade_chuva`, `refletividade`…),
  cada um com `units` (UDUNITS), `long_name` e `campo_parsivel`. Ausente = `_FillValue` -9999.
- **Espectros**: `N_d(time, diametro)` float32 em `log10(m-3 mm-1)` (campo 90; -9.999 = sem gota),
  `v_d(time, diametro)` float32 em m s-1 (campo 91) e `raw(time, velocidade, diametro)` int16 com
  as contagens do campo 93 (`_FillValue` -1 nas corrompidas), comprimido com zlib.
- **Atributos globais**: `Conventions`, `title`, `institution` (da pasta de marca da instalação,
  omitido sem ela), `source`, `equipamento`, `numero_serie`, `local`, `date_created`, `history`,
  `comment`.

## Desenvolvimento

O plugin depende do núcleo do Hidrolog e da `parsivelreader`, que estão em repositórios
próprios. Clone os três lado a lado:

```
projs/
├── hidrolog/
├── hidrolog-plugin-parsivel/   ← este repositório
└── parsivelreader/
```

O ambiente deste repositório instala o app, a biblioteca e o plugin em modo editável. O app
encontra o plugin pelo entry point `hidrolog.plugins`, sem passar pelo gerenciador:

```bash
cd hidrolog-plugin-parsivel
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt

export HIDROLOG_DADOS_DIR=/tmp/hidrolog-parsivel   # um banco só para o teste
venv/bin/python -m app criar-master --login admin --nome "Admin"
venv/bin/python -m hidrolog
```

### Pacote de distribuição

O app instalado não tem a `parsivelreader`, então o plugin é distribuído num `.zip` que a traz
dentro, ao lado de `hidrolog_parsivel` (o gerenciador põe a raiz do plugin no caminho de
importação). O repositório continua sem a cópia: o `.zip` é montado na hora da versão.

```bash
venv/bin/python empacotar.py      # dist/hidrolog-plugin-parsivel-<versão>.zip, com a parsivelreader do ambiente
```

O workflow `.github/workflows/pacote.yml` faz o mesmo a cada tag `v*` (ou à mão, em Actions →
Pacote do plugin), baixando a `parsivelreader` do repositório de mesmo dono, e anexa o `.zip` à
release. Antes de publicar a tag, atualize a `versao` no `hidrolog-plugin.toml` para o mesmo
número. Se o repositório da `parsivelreader` for privado, crie um token com leitura nele e salve
como secret `PARSIVELREADER_TOKEN`.

### Testes

```bash
QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest                    # testes do plugin
QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest --plugin=parsivel  # kit de conformidade do Hidrolog
```

- `tests/servico/`: importação da `amostra/` (contagens, ignorados, corrompidas, formatos antigo e
  novo, nº de série), ida e volta dos vetores e da matriz, `buscar_dados` igual a `pr.concatenar`,
  leitura paralela, ficha, regras, CSV, NetCDF e rotas da API.
- `tests/interface/`: as cinco abas na janela do Hidrolog.
- `tests/test_empacotar.py`: o `.zip` de distribuição traz a `parsivelreader` e o manifesto não a exige do app.

## Documentação

- [`https://github.com/eznoamd/hidrolog/`](https://github.com/eznoamd/hidrolog/): o app, a arquitetura e o funcionamento dos plugins.
- [`https://github.com/eznoamd/hidrolog/blob/main/exemplos/plugin-termometro/COMO-CRIAR-UM-PLUGIN.md`](https://github.com/eznoamd/hidrolog/blob/main/exemplos/plugin-termometro/COMO-CRIAR-UM-PLUGIN.md): o contrato que este plugin implementa.
- [`https://github.com/eznoamd/parsivelreader`](https://github.com/eznoamd/parsivelreader): leitura dos arquivos, classes de diâmetro e velocidade, eventos e gráficos.

## Licença

Ainda sem licença definida: todos os direitos reservados. Para usar ou adaptar o código, entre em
contato.
