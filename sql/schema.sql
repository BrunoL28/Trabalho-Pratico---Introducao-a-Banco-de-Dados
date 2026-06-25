-- ============================================================================
-- schema.sql Projeto Físico: Fraudes PIX contestadas via MED (BCB)
-- ----------------------------------------------------------------------------
-- Dialeto : PostgreSQL 14+
-- Fontes  : API Olinda / Pix Dados Abertos (Banco Central do Brasil)
--           - EstatisticasFraudesPix        (agregado nacional mensal)
--           - ChavesPix                     (por instituição / ISPB)
--           - TransacoesPixPorMunicipio     (por município / UF / região)
--
-- O script é idempotente: pode ser reexecutado com segurança (DROP ... CASCADE
-- antes de cada criação). Execução recomendada:
--   psql -U <usuario> -d <banco> -f sql/schema.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- 0. LIMPEZA (ordem inversa de dependência é resolvida pelo CASCADE)
-- ============================================================================
DROP TABLE IF EXISTS transacao_municipio    CASCADE;
DROP TABLE IF EXISTS chave_pix_instituicao  CASCADE;
DROP TABLE IF EXISTS bloqueio_cautelar      CASCADE;
DROP TABLE IF EXISTS nao_devolucao_med      CASCADE;
DROP TABLE IF EXISTS devolucao_med          CASCADE;
DROP TABLE IF EXISTS fraude_med             CASCADE;
DROP TABLE IF EXISTS instituicao            CASCADE;
DROP TABLE IF EXISTS municipio              CASCADE;
DROP TABLE IF EXISTS estado                 CASCADE;
DROP TABLE IF EXISTS regiao                 CASCADE;
DROP TABLE IF EXISTS periodo                CASCADE;

DROP TYPE IF EXISTS tipo_devolucao_enum   CASCADE;
DROP TYPE IF EXISTS motivo_nao_dev_enum   CASCADE;
DROP TYPE IF EXISTS desfecho_bloqueio_enum CASCADE;
DROP TYPE IF EXISTS natureza_usuario_enum CASCADE;
DROP TYPE IF EXISTS papel_transacao_enum  CASCADE;

-- ============================================================================
-- 1. TIPOS ENUMERADOS
--    Domínios fechados do negócio: viram tipos nativos para garantir
--    integridade no nível do SGBD (impossível inserir categoria inválida).
-- ============================================================================
CREATE TYPE tipo_devolucao_enum    AS ENUM ('INTEGRAL', 'PARCIAL');
CREATE TYPE motivo_nao_dev_enum    AS ENUM ('SALDO_INSUFICIENTE', 'CONTA_ENCERRADA', 'OUTROS');
CREATE TYPE desfecho_bloqueio_enum AS ENUM ('LIBERADO', 'DEVOLVIDO');
CREATE TYPE natureza_usuario_enum  AS ENUM ('PF', 'PJ');
CREATE TYPE papel_transacao_enum   AS ENUM ('PAGADOR', 'RECEBEDOR');

-- ============================================================================
-- 2. DIMENSÃO TEMPORAL
-- ============================================================================
CREATE TABLE periodo (
    id_periodo       INTEGER  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ano              SMALLINT NOT NULL CHECK (ano BETWEEN 2020 AND 2100),
    mes              SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    -- Coluna para facilitar filtros de
    -- intervalo de datas sem risco de divergir de (ano, mes).
    data_competencia DATE     GENERATED ALWAYS AS (make_date(ano, mes, 1)) STORED,

    CONSTRAINT uq_periodo_ano_mes UNIQUE (ano, mes)
);

COMMENT ON TABLE periodo IS
    'Dimensão temporal na granularidade mensal (competência dos dados do BCB).';

-- ============================================================================
-- 3. HIERARQUIA GEOGRÁFICA  (regiao -> estado -> municipio)
-- ============================================================================
CREATE TABLE regiao (
    sigla_regiao VARCHAR(2)  PRIMARY KEY,                 -- N, NE, SE, S, CO
    nome         VARCHAR(20) NOT NULL UNIQUE
);

COMMENT ON TABLE regiao IS 'Macrorregiões do Brasil (IBGE).';

CREATE TABLE estado (
    codigo_ibge  SMALLINT    PRIMARY KEY,                 -- ex.: 31 = MG
    sigla_uf     CHAR(2)     NOT NULL UNIQUE,
    nome         VARCHAR(30) NOT NULL,
    sigla_regiao VARCHAR(2)  NOT NULL
                 REFERENCES regiao (sigla_regiao),

    CONSTRAINT ck_estado_codigo_ibge CHECK (codigo_ibge BETWEEN 11 AND 53)
);

COMMENT ON TABLE estado IS 'Unidades federativas, codificadas pelo IBGE.';

CREATE TABLE municipio (
    codigo_ibge        INTEGER     PRIMARY KEY,           -- 7 dígitos IBGE
    nome               VARCHAR(60) NOT NULL,
    codigo_ibge_estado SMALLINT    NOT NULL
                       REFERENCES estado (codigo_ibge),

    -- Os 2 primeiros dígitos do código do município identificam a UF.
    CONSTRAINT ck_municipio_pertence_uf
        CHECK (codigo_ibge / 100000 = codigo_ibge_estado)
);

COMMENT ON TABLE municipio IS 'Municípios brasileiros, codificados pelo IBGE.';

CREATE INDEX idx_municipio_estado ON municipio (codigo_ibge_estado);

-- ============================================================================
-- 4. INSTITUIÇÕES FINANCEIRAS
-- ============================================================================
CREATE TABLE instituicao (
    ispb CHAR(8)      PRIMARY KEY,
    nome VARCHAR(120) NOT NULL,

    -- ISPB é um identificador numérico de 8 dígitos com zeros à esquerda.
    CONSTRAINT ck_instituicao_ispb CHECK (ispb ~ '^[0-9]{8}$')
);

COMMENT ON TABLE instituicao IS
    'Participantes do arranjo PIX, identificados pelo ISPB (Identificador de '
    'Sistema de Pagamentos Brasileiro).';

-- ============================================================================
-- 5. FATO PRINCIPAL: FRAUDE / MED  (1 linha por mês — agregado nacional)
-- ============================================================================
CREATE TABLE fraude_med (
    id_periodo                   INTEGER PRIMARY KEY
                                 REFERENCES periodo (id_periodo),

    -- Contestações
    qtd_pix_contestados          BIGINT         NOT NULL CHECK (qtd_pix_contestados          >= 0),
    qtd_contestacoes_aceitas     BIGINT         NOT NULL CHECK (qtd_contestacoes_aceitas     >= 0),
    qtd_contestacoes_rejeitadas  BIGINT         NOT NULL CHECK (qtd_contestacoes_rejeitadas  >= 0),
    taxa_aceitas_por_100mil      NUMERIC(12, 8) NOT NULL CHECK (taxa_aceitas_por_100mil      >= 0),

    -- Marcações de fraude na base de chaves/usuários
    qtd_usuarios_marcados_fraude BIGINT         NOT NULL CHECK (qtd_usuarios_marcados_fraude >= 0),
    qtd_chaves_marcadas_fraude   BIGINT         NOT NULL CHECK (qtd_chaves_marcadas_fraude   >= 0),

    -- Valores monetários consolidados
    valor_contestados_aceitos    NUMERIC(18, 2) NOT NULL CHECK (valor_contestados_aceitos    >= 0),
    valor_residual_nao_devolvido NUMERIC(18, 2) NOT NULL CHECK (valor_residual_nao_devolvido >= 0),

    -- Métrica oficial publicada pelo BCB (mantida por fidelidade à fonte).
    -- Nota: a soma aceitas+rejeitadas pode divergir em até ~10 unidades do
    -- total contestado por arredondamento nos dados do BCB; a validação
    -- é feita em src/transform.py, onde inconsistências viram WARNING.
    percentual_devolucao         NUMERIC(9, 6)  NOT NULL CHECK (percentual_devolucao BETWEEN 0 AND 100)
);

COMMENT ON TABLE fraude_med IS
    'Consolidado mensal nacional das transações PIX contestadas por suspeita '
    'de fraude via Mecanismo Especial de Devolução (MED).';

-- ----------------------------------------------------------------------------
-- 5.1 Detalhamento: devoluções efetivadas pelo MED
-- ----------------------------------------------------------------------------
CREATE TABLE devolucao_med (
    id_periodo     INTEGER             NOT NULL
                   REFERENCES fraude_med (id_periodo),
    tipo_devolucao tipo_devolucao_enum NOT NULL,
    quantidade     BIGINT              NOT NULL CHECK (quantidade >= 0),
    valor          NUMERIC(18, 2)      NOT NULL CHECK (valor      >= 0),

    CONSTRAINT pk_devolucao_med PRIMARY KEY (id_periodo, tipo_devolucao)
);

COMMENT ON TABLE devolucao_med IS
    'Devoluções concluídas via MED no mês, abertas por tipo (integral/parcial).';

-- ----------------------------------------------------------------------------
-- 5.2 Detalhamento: contestações aceitas porém NÃO devolvidas
-- ----------------------------------------------------------------------------
CREATE TABLE nao_devolucao_med (
    id_periodo INTEGER             NOT NULL
               REFERENCES fraude_med (id_periodo),
    motivo     motivo_nao_dev_enum NOT NULL,
    quantidade BIGINT              NOT NULL CHECK (quantidade >= 0),
    valor      NUMERIC(18, 2)      NOT NULL CHECK (valor      >= 0),

    CONSTRAINT pk_nao_devolucao_med PRIMARY KEY (id_periodo, motivo)
);

COMMENT ON TABLE nao_devolucao_med IS
    'Valores não recuperados pelo MED no mês, abertos por motivo '
    '(saldo insuficiente, conta encerrada, outros).';

-- ----------------------------------------------------------------------------
-- 5.3 Detalhamento: bloqueios cautelares
-- ----------------------------------------------------------------------------
CREATE TABLE bloqueio_cautelar (
    id_periodo INTEGER                NOT NULL
               REFERENCES fraude_med (id_periodo),
    desfecho   desfecho_bloqueio_enum NOT NULL,
    quantidade BIGINT                 NOT NULL CHECK (quantidade >= 0),
    valor      NUMERIC(18, 2)         NOT NULL CHECK (valor      >= 0),

    CONSTRAINT pk_bloqueio_cautelar PRIMARY KEY (id_periodo, desfecho)
);

COMMENT ON TABLE bloqueio_cautelar IS
    'Transações bloqueadas cautelarmente no mês, abertas por desfecho '
    '(liberadas ao recebedor ou devolvidas ao pagador).';

-- ============================================================================
-- 6. FATO: CHAVES PIX POR INSTITUIÇÃO
--    Snapshot mensal da base de chaves de cada participante.
-- ============================================================================
CREATE TABLE chave_pix_instituicao (
    id_periodo       INTEGER               NOT NULL
                     REFERENCES periodo (id_periodo),
    ispb             CHAR(8)               NOT NULL
                     REFERENCES instituicao (ispb),
    natureza_usuario natureza_usuario_enum NOT NULL,
    tipo_chave       VARCHAR(30)           NOT NULL,
    qtd_chaves       INTEGER               NOT NULL CHECK (qtd_chaves >= 0),

    CONSTRAINT pk_chave_pix_instituicao
        PRIMARY KEY (id_periodo, ispb, natureza_usuario, tipo_chave)
);

COMMENT ON TABLE chave_pix_instituicao IS
    'Quantidade de chaves PIX registradas por instituição, natureza do '
    'usuário e tipo de chave, na competência mensal.';

CREATE INDEX idx_chave_pix_ispb    ON chave_pix_instituicao (ispb);
CREATE INDEX idx_chave_pix_periodo ON chave_pix_instituicao (id_periodo);

-- ============================================================================
-- 7. FATO: TRANSAÇÕES PIX POR MUNICÍPIO
--    Grupos repetitivos do CSV (PF/PJ x Pagador/Recebedor) normalizados
--    em linhas categorizadas — 1 linha por combinação.
-- ============================================================================
CREATE TABLE transacao_municipio (
    id_periodo            INTEGER               NOT NULL
                          REFERENCES periodo (id_periodo),
    codigo_ibge_municipio INTEGER               NOT NULL
                          REFERENCES municipio (codigo_ibge),
    papel                 papel_transacao_enum  NOT NULL,
    natureza              natureza_usuario_enum NOT NULL,
    valor                 NUMERIC(18, 2)        NOT NULL CHECK (valor          >= 0),
    qtd_transacoes        BIGINT                NOT NULL CHECK (qtd_transacoes >= 0),
    qtd_pessoas           BIGINT                NOT NULL CHECK (qtd_pessoas    >= 0),

    CONSTRAINT pk_transacao_municipio
        PRIMARY KEY (id_periodo, codigo_ibge_municipio, papel, natureza)
);

COMMENT ON TABLE transacao_municipio IS
    'Volumetria mensal de transações PIX por município, papel do usuário '
    'no fluxo (pagador/recebedor) e natureza (PF/PJ).';

CREATE INDEX idx_transacao_municipio_geo     ON transacao_municipio (codigo_ibge_municipio);
CREATE INDEX idx_transacao_municipio_periodo ON transacao_municipio (id_periodo);

-- ============================================================================
-- 8. CARGA DAS DIMENSÕES GEOGRÁFICAS FIXAS
--    Regiões e UFs são domínios estáveis do IBGE: carregados junto ao DDL
--    para que o pipeline de ingestão dependa apenas de dados dinâmicos.
-- ============================================================================
INSERT INTO regiao (sigla_regiao, nome) VALUES
    ('N',  'Norte'),
    ('NE', 'Nordeste'),
    ('SE', 'Sudeste'),
    ('S',  'Sul'),
    ('CO', 'Centro-Oeste');

INSERT INTO estado (codigo_ibge, sigla_uf, nome, sigla_regiao) VALUES
    (11, 'RO', 'Rondônia',            'N'),
    (12, 'AC', 'Acre',                'N'),
    (13, 'AM', 'Amazonas',            'N'),
    (14, 'RR', 'Roraima',             'N'),
    (15, 'PA', 'Pará',                'N'),
    (16, 'AP', 'Amapá',               'N'),
    (17, 'TO', 'Tocantins',           'N'),
    (21, 'MA', 'Maranhão',            'NE'),
    (22, 'PI', 'Piauí',               'NE'),
    (23, 'CE', 'Ceará',               'NE'),
    (24, 'RN', 'Rio Grande do Norte', 'NE'),
    (25, 'PB', 'Paraíba',             'NE'),
    (26, 'PE', 'Pernambuco',          'NE'),
    (27, 'AL', 'Alagoas',             'NE'),
    (28, 'SE', 'Sergipe',             'NE'),
    (29, 'BA', 'Bahia',               'NE'),
    (31, 'MG', 'Minas Gerais',        'SE'),
    (32, 'ES', 'Espírito Santo',      'SE'),
    (33, 'RJ', 'Rio de Janeiro',      'SE'),
    (35, 'SP', 'São Paulo',           'SE'),
    (41, 'PR', 'Paraná',              'S'),
    (42, 'SC', 'Santa Catarina',      'S'),
    (43, 'RS', 'Rio Grande do Sul',   'S'),
    (50, 'MS', 'Mato Grosso do Sul',  'CO'),
    (51, 'MT', 'Mato Grosso',         'CO'),
    (52, 'GO', 'Goiás',               'CO'),
    (53, 'DF', 'Distrito Federal',    'CO');

COMMIT;
