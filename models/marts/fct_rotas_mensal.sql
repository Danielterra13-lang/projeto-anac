with voos as (
    select * from {{ ref('stg_anac__voos') }}
)

select
    ano,
    mes,
    natureza,
    aeroporto_origem_sigla,
    aeroporto_origem_nome,
    aeroporto_origem_uf,
    aeroporto_origem_regiao,
    aeroporto_origem_pais,
    aeroporto_destino_sigla,
    aeroporto_destino_nome,
    aeroporto_destino_uf,
    aeroporto_destino_regiao,
    aeroporto_destino_pais,

    count(distinct empresa_sigla) as qtd_empresas,
    sum(decolagens) as total_decolagens,
    sum(passageiros_pagos) as total_passageiros_pagos,
    sum(passageiros_gratis) as total_passageiros_gratis,
    sum(passageiros_pagos) + sum(passageiros_gratis) as total_passageiros,
    sum(carga_paga_kg) as total_carga_paga_kg,
    sum(ask) as total_ask,
    sum(rpk) as total_rpk,
    safe_divide(sum(rpk), sum(ask)) as load_factor

from voos
where aeroporto_origem_sigla is not null and aeroporto_origem_sigla != ''
  and aeroporto_destino_sigla is not null and aeroporto_destino_sigla != ''
group by 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13