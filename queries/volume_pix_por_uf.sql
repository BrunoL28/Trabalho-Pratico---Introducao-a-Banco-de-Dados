-- Volume transacionado via PIX por UF, com corte de relevância.
-- Padrão: agregações SUM/COUNT agrupadas por UF/região; HAVING descarta UFs
--         abaixo de valor_minimo (em R$).
-- Parâmetros: :ano           → ano de referência (NULL = período completo)
--             :valor_minimo  → corte mínimo de valor total (ex.: 0.0)

SELECT e.sigla_uf,
       r.nome                                  AS regiao,
       SUM(t.valor)                            AS valor_total,
       SUM(t.qtd_transacoes)                   AS total_transacoes,
       COUNT(DISTINCT t.codigo_ibge_municipio) AS municipios_ativos
  FROM transacao_municipio t
  JOIN municipio m ON m.codigo_ibge = t.codigo_ibge_municipio
  JOIN estado    e ON e.codigo_ibge = m.codigo_ibge_estado
  JOIN regiao    r ON r.sigla_regiao = e.sigla_regiao
  JOIN periodo   p ON p.id_periodo = t.id_periodo
 WHERE (:ano IS NULL OR p.ano = :ano)
 GROUP BY e.sigla_uf, r.nome
HAVING SUM(t.valor) >= :valor_minimo
 ORDER BY valor_total DESC
