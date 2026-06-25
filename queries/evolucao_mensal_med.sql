-- Série mensal do MED: contestações, valores e devoluções por tipo.
-- Padrão: JOIN estrutural entre periodo, fraude_med e devolucao_med;
--         pivot condicional via FILTER.

SELECT p.data_competencia,
       f.qtd_pix_contestados,
       f.qtd_contestacoes_aceitas,
       f.valor_contestados_aceitos,
       f.percentual_devolucao,
       SUM(d.valor) FILTER (WHERE d.tipo_devolucao = 'INTEGRAL') AS valor_devolvido_integral,
       SUM(d.valor) FILTER (WHERE d.tipo_devolucao = 'PARCIAL')  AS valor_devolvido_parcial
  FROM periodo p
  JOIN fraude_med    f ON f.id_periodo = p.id_periodo
  JOIN devolucao_med d ON d.id_periodo = f.id_periodo
 GROUP BY p.data_competencia, f.qtd_pix_contestados,
          f.qtd_contestacoes_aceitas, f.valor_contestados_aceitos,
          f.percentual_devolucao
 ORDER BY p.data_competencia
