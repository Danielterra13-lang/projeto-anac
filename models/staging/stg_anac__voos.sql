with fonte as (
    select * from {{ source('raw_anac', 'microdados_bruto') }}
)

select
    -- identificação da empresa
    empresa_sigla,
    empresa_nome,
    empresa_nacionalidade,

    -- período
    safe_cast(ano as int64) as ano,
    safe_cast(mes as int64) as mes,

    -- origem
    aeroporto_de_origem_sigla as aeroporto_origem_sigla,
    aeroporto_de_origem_nome as aeroporto_origem_nome,
    nullif(trim(aeroporto_de_origem_uf), '') as aeroporto_origem_uf,
    nullif(trim(aeroporto_de_origem_regiao), '') as aeroporto_origem_regiao,
    aeroporto_de_origem_pais as aeroporto_origem_pais,
    aeroporto_de_origem_continente as aeroporto_origem_continente,

    -- destino
    aeroporto_de_destino_sigla as aeroporto_destino_sigla,
    aeroporto_de_destino_nome as aeroporto_destino_nome,
    nullif(trim(aeroporto_de_destino_uf), '') as aeroporto_destino_uf,
    nullif(trim(aeroporto_de_destino_regiao), '') as aeroporto_destino_regiao,
    aeroporto_de_destino_pais as aeroporto_destino_pais,
    aeroporto_de_destino_continente as aeroporto_destino_continente,

    -- classificação do voo
    natureza,
    grupo_de_voo as grupo_voo,

    -- métricas de demanda e oferta
    safe_cast(passageiros_pagos as int64) as passageiros_pagos,
    safe_cast(passageiros_gratis as int64) as passageiros_gratis,
    safe_cast(carga_paga_kg as float64) as carga_paga_kg,
    safe_cast(carga_gratis_kg as float64) as carga_gratis_kg,
    safe_cast(correio_kg as float64) as correio_kg,
    safe_cast(ask as float64) as ask,
    safe_cast(rpk as float64) as rpk,
    safe_cast(atk as float64) as atk,
    safe_cast(rtk as float64) as rtk,
    safe_cast(combustivel_litros as float64) as combustivel_litros,
    safe_cast(distancia_voada_km as float64) as distancia_voada_km,
    safe_cast(decolagens as int64) as decolagens,
    safe_cast(carga_paga_km as float64) as carga_paga_km,
    safe_cast(carga_gratis_km as float64) as carga_gratis_km,
    safe_cast(correio_km as float64) as correio_km,
    safe_cast(assentos as int64) as assentos,
    safe_cast(payload as float64) as payload,
    safe_cast(horas_voadas as float64) as horas_voadas,
    safe_cast(bagagem_kg as float64) as bagagem_kg

from fonte
where safe_cast(ano as int64) is not null
  and safe_cast(mes as int64) is not null