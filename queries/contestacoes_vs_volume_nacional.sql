-- Taxa de contestação: PIX contestados a cada 100 mil transações nacionais.
-- Padrão: subconsulta correlacionada que agrega o volume nacional (recorte
--         municipal, papel PAGADOR) e a confronta com o consolidado do MED.

SELECT p.data_competencia,
       f.qtd_pix_contestados,
       vol.total_transacoes,
       ROUND(100000.0 * f.qtd_pix_contestados
             / NULLIF(vol.total_transacoes, 0), 2) AS contestados_por_100mil
  FROM fraude_med f
  JOIN periodo p ON p.id_periodo = f.id_periodo
  JOIN (
        SELECT id_periodo,
               SUM(qtd_transacoes) AS total_transacoes
          FROM transacao_municipio
         WHERE papel = 'PAGADOR'
         GROUP BY id_periodo
       ) vol ON vol.id_periodo = f.id_periodo
 ORDER BY p.data_competencia
