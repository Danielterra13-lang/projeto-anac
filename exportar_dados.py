import json
import os
import io
import math
from datetime import datetime, timezone

import pandas as pd
import requests
from google.cloud import bigquery

PROJETO = "portfolio-anac"
DATASET = "dbt_staging"

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"


def limpar_nan(obj):
    # JSON padrao nao aceita NaN. Python escreve NaN sem aspas, o que quebra
    # o parser do navegador. Troca por None (fica "null" no JSON), que e valido.
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: limpar_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [limpar_nan(v) for v in obj]
    return obj


def carregar_coordenadas():
    resposta = requests.get(AIRPORTS_URL, timeout=60)
    resposta.raise_for_status()
    df = pd.read_csv(io.StringIO(resposta.text))
    df = df[["ident", "latitude_deg", "longitude_deg"]].dropna()
    df = df.drop_duplicates(subset="ident")
    return df.set_index("ident")[["latitude_deg", "longitude_deg"]].to_dict("index")


def exportar_rotas(client, coordenadas, top_n=150):
    query = f"""
        SELECT *
        FROM `{PROJETO}.{DATASET}.fct_rotas_mensal`
    """
    df = client.query(query).to_dataframe()

    colunas_dimensao = [
        "ano", "natureza",
        "aeroporto_origem_sigla", "aeroporto_origem_nome", "aeroporto_origem_uf",
        "aeroporto_origem_regiao", "aeroporto_origem_pais",
        "aeroporto_destino_sigla", "aeroporto_destino_nome", "aeroporto_destino_uf",
        "aeroporto_destino_regiao", "aeroporto_destino_pais",
    ]
    colunas_soma = [
        "total_decolagens", "total_passageiros_pagos", "total_passageiros_gratis",
        "total_passageiros", "total_carga_paga_kg", "total_ask", "total_rpk",
    ]

    anual = df.groupby(colunas_dimensao, dropna=False)[colunas_soma].sum().reset_index()
    anual["load_factor"] = anual["total_rpk"] / anual["total_ask"]

    anual["rank_no_ano"] = anual.groupby("ano")["total_passageiros"].rank(method="first", ascending=False)
    anual = anual[anual["rank_no_ano"] <= top_n].drop(columns="rank_no_ano")

    anual["origem_lat"] = anual["aeroporto_origem_sigla"].map(lambda x: coordenadas.get(x, {}).get("latitude_deg"))
    anual["origem_lon"] = anual["aeroporto_origem_sigla"].map(lambda x: coordenadas.get(x, {}).get("longitude_deg"))
    anual["destino_lat"] = anual["aeroporto_destino_sigla"].map(lambda x: coordenadas.get(x, {}).get("latitude_deg"))
    anual["destino_lon"] = anual["aeroporto_destino_sigla"].map(lambda x: coordenadas.get(x, {}).get("longitude_deg"))

    return anual


def exportar_empresas_por_rota(client, rotas_df, top_n_empresas=5):
    # So buscamos empresa por rota para as rotas que ja entraram no corte
    # das top 150 por ano (a mesma logica de "so o que aparece no mapa").
    chaves_validas = set(
        zip(rotas_df["ano"], rotas_df["aeroporto_origem_sigla"], rotas_df["aeroporto_destino_sigla"])
    )

    query = f"""
        SELECT
            ano,
            aeroporto_origem_sigla,
            aeroporto_destino_sigla,
            empresa_sigla,
            empresa_nome,
            SUM(passageiros_pagos) AS total_passageiros_pagos
        FROM `{PROJETO}.{DATASET}.stg_anac__voos`
        WHERE aeroporto_origem_sigla IS NOT NULL AND aeroporto_origem_sigla != ''
          AND aeroporto_destino_sigla IS NOT NULL AND aeroporto_destino_sigla != ''
        GROUP BY 1, 2, 3, 4, 5
    """
    df = client.query(query).to_dataframe()

    df["chave"] = list(zip(df["ano"], df["aeroporto_origem_sigla"], df["aeroporto_destino_sigla"]))
    df = df[df["chave"].isin(chaves_validas)]

    resultado = {}
    for chave, grupo in df.groupby("chave"):
        ano, origem, destino = chave
        total_rota = grupo["total_passageiros_pagos"].sum()
        top = grupo.sort_values("total_passageiros_pagos", ascending=False).head(top_n_empresas)
        lista = []
        for _, linha in top.iterrows():
            pct = linha["total_passageiros_pagos"] / total_rota if total_rota else None
            lista.append({
                "sigla": linha["empresa_sigla"],
                "nome": linha["empresa_nome"],
                "passageiros_pagos": int(linha["total_passageiros_pagos"]),
                "pct": pct,
            })
        chave_str = f"{int(ano)}|{origem}|{destino}"
        resultado[chave_str] = lista

    return resultado


def exportar_mercado(client):
    query = f"""
        SELECT *
        FROM `{PROJETO}.{DATASET}.fct_mercado_mensal`
    """
    df = client.query(query).to_dataframe()
    return df.to_dict(orient="records")


def exportar_regional(client):
    query = f"""
        SELECT *
        FROM `{PROJETO}.{DATASET}.fct_rotas_mensal`
    """
    df = client.query(query).to_dataframe()

    colunas_dimensao = ["ano", "mes", "aeroporto_origem_uf", "aeroporto_origem_regiao"]
    colunas_soma = [
        "total_decolagens", "total_passageiros_pagos", "total_passageiros_gratis",
        "total_passageiros", "total_carga_paga_kg", "total_ask", "total_rpk",
    ]

    regional = df[df["aeroporto_origem_uf"].notna() & (df["aeroporto_origem_uf"] != "")]
    regional = regional.groupby(colunas_dimensao, dropna=False)[colunas_soma].sum().reset_index()
    regional["load_factor"] = regional["total_rpk"] / regional["total_ask"]

    return regional.to_dict(orient="records")


def salvar_json(dados, caminho):
    dados = limpar_nan(dados)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, default=str)


def main():
    client = bigquery.Client(project=PROJETO)

    print("Baixando coordenadas de aeroportos...")
    coordenadas = carregar_coordenadas()

    print("Exportando rotas anuais...")
    rotas_df = exportar_rotas(client, coordenadas)
    salvar_json(rotas_df.to_dict(orient="records"), "data/rotas_mensal.json")

    print("Exportando empresas por rota...")
    empresas_por_rota = exportar_empresas_por_rota(client, rotas_df)
    salvar_json(empresas_por_rota, "data/rotas_empresas.json")

    print("Exportando mercado mensal...")
    mercado = exportar_mercado(client)
    salvar_json(mercado, "data/mercado_mensal.json")

    print("Exportando indicadores regionais...")
    regional = exportar_regional(client)
    salvar_json(regional, "data/regional_mensal.json")

    metadata = {"atualizado_em": datetime.now(timezone.utc).isoformat()}
    salvar_json(metadata, "data/metadata.json")

    print(f"Exportado: {len(rotas_df)} rotas, {len(empresas_por_rota)} rotas com empresas, "
          f"{len(mercado)} registros de mercado, {len(regional)} registros regionais.")


if __name__ == "__main__":
    main()