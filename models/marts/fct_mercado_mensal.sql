with voos as (
    select * from {{ ref('stg_anac__voos') }}
)

select
    ano,
    mes,
    natureza,
    empresa_sigla,
    empresa_nome,
    empresa_nacionalidade,

    sum(decolagens) as total_decolagens,
    sum(passageiros_pagos) as total_passageiros_pagos,
    sum(ask) as total_ask,
    sum(rpk) as total_rpk

from voos
group by 1, 2, 3, 4, 5, 6