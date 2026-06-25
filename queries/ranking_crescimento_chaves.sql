-- Instituições com maior crescimento mensal da base de chaves PIX.
-- Padrão: CTE de consolidação → LAG() (window function) para obter o mês
--         anterior → RANK() dentro de cada mês → subconsulta cortando top N.
-- O crescimento da base de chaves é proxy de exposição a fraude, pois o
-- dataset MED do BCB não abre fraude por instituição.
-- Parâmetros: :top_n → quantas instituições exibir por competência

WITH chaves_mes AS (
    SELECT c.ispb,
           p.data_competencia,
           SUM(c.qtd_chaves) AS total_chaves
      FROM chave_pix_instituicao c
      JOIN periodo p ON p.id_periodo = c.id_periodo
     GROUP BY c.ispb, p.data_competencia
),
variacao AS (
    SELECT ispb,
           data_competencia,
           total_chaves,
           LAG(total_chaves) OVER janela            AS chaves_mes_anterior,
           total_chaves
             - LAG(total_chaves) OVER janela        AS crescimento_absoluto
      FROM chaves_mes
    WINDOW janela AS (PARTITION BY ispb ORDER BY data_competencia)
)
SELECT data_competencia,
       posicao,
       nome,
       chaves_mes_anterior,
       total_chaves,
       crescimento_absoluto,
       ROUND(100.0 * crescimento_absoluto
             / NULLIF(chaves_mes_anterior, 0), 2) AS crescimento_pct
  FROM (
        SELECT v.*,
               i.nome,
               RANK() OVER (PARTITION BY v.data_competencia
                            ORDER BY v.crescimento_absoluto DESC) AS posicao
          FROM variacao v
          JOIN instituicao i ON i.ispb = v.ispb
         WHERE v.crescimento_absoluto IS NOT NULL
       ) ranqueadas
 WHERE posicao <= :top_n
 ORDER BY data_competencia, posicao
