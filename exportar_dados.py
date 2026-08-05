import json
import os
import io
from datetime import datetime, timezone

import pandas as pd
import requests
from google.cloud import bigquery

PROJETO = "portfolio-anac"
DATASET = "dbt_staging"

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"


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

    # Agrega de mensal para anual. qtd_empresas foi removida aqui de propósito:
    # contar distinct por mês e somar infla o número (mesma empresa conta várias vezes).
    # Se precisar desse dado por ano, calcular direto da stg_anac__voos, não a partir daqui.
    anual = df.groupby(colunas_dimensao, dropna=False)[colunas_soma].sum().reset_index()
    anual["load_factor"] = anual["total_rpk"] / anual["total_ask"]

    anual["rank_no_ano"] = anual.groupby("ano")["total_passageiros"].rank(method="first", ascending=False)
    anual = anual[anual["rank_no_ano"] <= top_n].drop(columns="rank_no_ano")

    anual["origem_lat"] = anual["aeroporto_origem_sigla"].map(lambda x: coordenadas.get(x, {}).get("latitude_deg"))
    anual["origem_lon"] = anual["aeroporto_origem_sigla"].map(lambda x: coordenadas.get(x, {}).get("longitude_deg"))
    anual["destino_lat"] = anual["aeroporto_destino_sigla"].map(lambda x: coordenadas.get(x, {}).get("latitude_deg"))
    anual["destino_lon"] = anual["aeroporto_destino_sigla"].map(lambda x: coordenadas.get(x, {}).get("longitude_deg"))

    return anual.to_dict(orient="records")

def exportar_mercado(client):
    query = f"""
        SELECT *
        FROM `{PROJETO}.{DATASET}.fct_mercado_mensal`
    """
    df = client.query(query).to_dataframe()
    return df.to_dict(orient="records")


def salvar_json(dados, caminho):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, default=str)


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

    # Usa UF/região de origem como recorte geográfico.
    # Voos internacionais (origem fora do Brasil) não têm UF/região preenchida
    # e ficam de fora dessa visão, o que é esperado: essa métrica é sobre embarque no Brasil.
    regional = df[df["aeroporto_origem_uf"].notna() & (df["aeroporto_origem_uf"] != "")]
    regional = regional.groupby(colunas_dimensao, dropna=False)[colunas_soma].sum().reset_index()
    regional["load_factor"] = regional["total_rpk"] / regional["total_ask"]

    return regional.to_dict(orient="records")






def main():
    client = bigquery.Client(project=PROJETO)

    print("Baixando coordenadas de aeroportos...")
    coordenadas = carregar_coordenadas()

    print("Exportando rotas mensais...")
    rotas = exportar_rotas(client, coordenadas)
    salvar_json(rotas, "data/rotas_mensal.json")

    print("Exportando mercado mensal...")
    mercado = exportar_mercado(client)
    salvar_json(mercado, "data/mercado_mensal.json")

    print("Exportando indicadores regionais...")
    regional = exportar_regional(client)
    salvar_json(regional, "data/regional_mensal.json")    

    metadata = {"atualizado_em": datetime.now(timezone.utc).isoformat()}
    salvar_json(metadata, "data/metadata.json")

    print(f"Exportado: {len(rotas)} rotas, {len(mercado)} registros de mercado.")


if __name__ == "__main__":
    main()