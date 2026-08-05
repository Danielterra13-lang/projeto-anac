# Malha Aérea Brasileira — Dados Estatísticos ANAC

Pipeline de dados completo sobre o transporte aéreo brasileiro, cobrindo 2000 até o mês mais recente disponível. Conta a história do crescimento da malha aérea, do colapso da pandemia em 2020 e da recuperação que veio depois, com um dashboard interativo publicado no GitHub Pages.

**Dashboard ao vivo:** https://danielterra13-lang.github.io/projeto-anac/

<img width="1882" height="900" alt="image" src="https://github.com/user-attachments/assets/e00924f1-231c-450b-88e8-bf09d1ff41bd" />


<img width="1882" height="900" alt="image" src="https://github.com/user-attachments/assets/73ce4c70-20de-4858-a782-adb57080b898" />


## O problema

Dados públicos de transporte aéreo costumam ser tratados como planilha estática: alguém baixa o CSV, monta um gráfico no Excel e para ali. Esse projeto trata o mesmo dado como um pipeline de verdade: ingestão, transformação em camadas, exportação automatizada e um front-end que consome dados versionados, não uma cópia manual.

O recorte de 26 anos também permite contar uma história que uma foto do "mês atual" não conta: a malha aérea brasileira cresceu de forma constante entre 2000 e 2019, perdeu mais da metade do volume de passageiros em 2020, e levou até 2023-2024 pra recuperar o patamar pré-pandemia.

## Stack

BigQuery · dbt · Python (pandas) · GitHub Actions · Leaflet.js · Chart.js · HTML/CSS/JS vanilla · GitHub Pages

## Arquitetura do pipeline

```
CSV bruto (ANAC, sistemas.anac.gov.br)
    └─> Google Cloud Storage (bucket portfolio-anac-raw-data)
        └─> BigQuery, tabela raw (raw_anac.microdados_bruto, tudo STRING)
            └─> dbt staging (stg_anac__voos: cast, limpeza, normalização)
                └─> dbt marts (fct_rotas_mensal, fct_mercado_mensal)
                    └─> exportar_dados.py (BigQuery -> JSON)
                        └─> data/*.json
                            └─> index.html (dashboard estático, GitHub Pages)
```

GitHub Actions automatiza as duas últimas etapas (dbt run + exportar_dados.py) no dia 20 de cada mês, com opção de disparo manual. A ingestão do CSV bruto é manual, ver seção **Atualizando os dados brutos** abaixo.

## Decisões técnicas e por quê

**Esquema manual, tudo como STRING na tabela raw.** Em vez de deixar o BigQuery detectar tipos automaticamente na carga do CSV, o esquema foi definido campo a campo como STRING. Isso evita que o load falhe por um valor inesperado em alguma linha, e empurra a responsabilidade de conversão de tipo pra dentro do dbt, onde é possível tratar erro linha a linha com `safe_cast` em vez de abortar a carga inteira.

**Camada intermediate pulada de propósito.** Os marts (`fct_rotas_mensal`, `fct_mercado_mensal`) fazem apenas uma agregação a partir do staging, sem lógica de negócio intermediária que justifique uma camada própria. Adicionar `intermediate/` aqui seria estrutura por estrutura, não uma necessidade real do case.

**Coordenadas de aeroporto via pandas, não como dimensão no BigQuery.** O enriquecimento com latitude/longitude (fonte: OurAirports) acontece no script Python, depois que os dados já saíram do warehouse. A decisão foi manter o BigQuery focado em dados de negócio, e deixar preocupação de visualização (plotar ponto num mapa) fora dele.

**Top 150 rotas por ano no mapa.** O dataset completo tem mais de 1 milhão de linhas; plotar todas as rotas de 26 anos no navegador não escala. O corte para as 150 rotas com mais passageiros por ano reduziu o JSON de rotas de ~400MB para ~3MB sem perder o traço principal da história (crescimento, colapso, recuperação).

**Service account restrita para o GitHub Actions.** A automação usa uma service account própria (`github-actions-anac`) com permissão apenas de leitura de dados e execução de jobs no BigQuery (`BigQuery Data Viewer` + `BigQuery Job User`), separada da service account usada localmente, que tem permissão de administração. Se a chave do GitHub vazar, o dano possível é limitado.

## Bugs reais encontrados e como foram resolvidos

Esses três problemas só apareceram depois que o dashboard já estava no ar, ao inspecionar visualmente os gráficos de região. Documentar como foram rastreados importa mais do que fingir que os dados chegaram limpos de primeira.

**1. Uma linha de cabeçalho do CSV entrou como dado.** O gráfico "Passageiros por região" mostrava uma categoria chamada literalmente `AEROPORTO_DE_ORIGEM_UF`, com um único registro por trás. Investigação: o campo `ano`/`mes` dessa linha vinha `NULL` depois do `safe_cast`, mas o filtro original do staging (`where ano is not null and ano != ''`) checava o texto bruto antes da conversão, não o resultado dela, então a linha passava disfarçada. Correção: o filtro passou a checar o resultado do próprio `safe_cast`, o que pega qualquer linha que não converte pra número, seja ela um cabeçalho, uma linha em branco, ou outro tipo de ruído de concatenação de arquivo.

**2. Espaço em branco disfarçado de valor válido.** Depois do primeiro conserto, uma segunda categoria fantasma apareceu no mesmo gráfico, um valor de região igual a `" "` (um único espaço). Como string não vazia é "truthy" em JavaScript, o filtro de frontend que descarta categoria vazia (`if (!cat) return`) não pegava esse caso. Correção: `nullif(trim(campo), '')` no staging, aplicado em UF e região de origem e destino, transformando qualquer variação de espaço em branco em `NULL` de verdade antes do dado sair do warehouse.

**3. `NaN` de ponto flutuante quebrando a conversão pra inteiro.** O script de exportação de composição de empresas por rota (`exportar_empresas_por_rota`) quebrava com `TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NAType'` em rotas onde uma métrica vinha nula. Correção: checagem explícita de nulo (`pd.notna(...)`) antes da conversão, com valor padrão zero.

O padrão dos três: nenhum era um bug de lógica de negócio, eram três formas diferentes do mesmo tipo de problema, dado sujo que passa por um filtro pensado pra outro formato de sujeira. A lição prática foi filtrar pelo resultado da conversão de tipo, não pelo texto bruto antes dela.

## Atualizando os dados brutos

O GitHub Actions automatiza transformação e exportação, mas não a ingestão do CSV bruto. A ANAC publica um arquivo único com a série histórica completa (não incremental), então atualizar os dados exige repetir manualmente:

1. Baixar o `Dados_Estatisticos.csv` atualizado em [sistemas.anac.gov.br](https://sistemas.anac.gov.br) (dados abertos, seção de estatísticas de transporte aéreo).
2. Subir o arquivo para o bucket `portfolio-anac-raw-data` no Cloud Storage, substituindo o anterior.
3. No BigQuery, recarregar a tabela `raw_anac.microdados_bruto` a partir do bucket, usando **sobrescrever** (write disposition `WRITE_TRUNCATE`), nunca anexar, já que o CSV novo já contém todo o histórico anterior. Mesmo esquema manual da carga original (todas as colunas como STRING), 1 linha de cabeçalho ignorada, delimitador ponto e vírgula, codificação UTF-8.
4. A partir daí, o GitHub Actions assume: `dbt run` reprocessa staging e marts, `exportar_dados.py` gera os JSONs novos, e o commit automático atualiza o dashboard.

Automatizar essa etapa também é possível, por exemplo com uma Cloud Function disparada por agendamento que baixa o CSV direto da URL da ANAC e recarrega a tabela antes do `dbt run`. Ficou de fora do escopo deste projeto por ora; é o próximo passo natural se o pipeline for além de portfólio.

## Trade-offs e limitações conhecidas

- **Ingestão do CSV bruto é manual**, ver seção acima. Todo o resto do pipeline (transformação, exportação, publicação) é automático.
- **Filtro por companhia aérea não existe na visão regional** (só existe no mapa de rotas). Ficou para uma próxima iteração do case, documentado como tal no próprio dashboard.
- **`qtd_empresas` foi descartado da exportação anual de rotas**, porque somar contagens distintas mensais infla o número (uma mesma empresa contada em cada mês em que operou a rota). Métrica só existe no recorte mensal, onde é correta.
- **Camada `intermediate` do dbt não existe**, decisão consciente dado que os marts fazem apenas uma agregação direta do staging.

## Estrutura do repositório

- `index.html` — dashboard estático (mapa Leaflet + gráficos Chart.js)
- `exportar_dados.py` — exporta os marts do BigQuery para os JSONs consumidos pelo dashboard
- `models/staging/stg_anac__voos.sql` — normalização, cast e limpeza de dados
- `models/marts/fct_rotas_mensal.sql`, `models/marts/fct_mercado_mensal.sql` — agregações de negócio
- `data/` — JSONs gerados (rotas, empresas por rota, mercado, regional, metadata)
- `.github/workflows/` — automação mensal via GitHub Actions
- `dbt_project.yml` — configuração do projeto dbt

## Fonte dos dados

ANAC — Agência Nacional de Aviação Civil, Dados Estatísticos do Transporte Aéreo (sistemas.anac.gov.br). Dados públicos, cobertura 2000 até o mês mais recente disponível.
