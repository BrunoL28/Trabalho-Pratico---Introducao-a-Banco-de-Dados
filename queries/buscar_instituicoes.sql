-- Localiza instituições participantes do PIX pelo nome (busca parcial).
-- Padrão: projeção simples com filtro WHERE ... ILIKE.
-- Parâmetros: :padrao  → fragmento de nome (ex.: '%Itaú%')

SELECT ispb,
       nome
  FROM instituicao
 WHERE nome ILIKE :padrao
 ORDER BY nome
