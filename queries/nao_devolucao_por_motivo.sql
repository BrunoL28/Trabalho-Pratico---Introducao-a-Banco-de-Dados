-- Quanto o MED deixa de recuperar, consolidado por motivo da falha.
-- Padrão: agregação simples GROUP BY sobre tabela de detalhamento.

SELECT n.motivo,
       SUM(n.quantidade) AS total_ocorrencias,
       SUM(n.valor)      AS valor_total
  FROM nao_devolucao_med n
 GROUP BY n.motivo
 ORDER BY valor_total DESC
