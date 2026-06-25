CREATE TABLE public.periodo (
  id_periodo integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  ano smallint NOT NULL CHECK (ano >= 2020 AND ano <= 2100),
  mes smallint NOT NULL CHECK (mes >= 1 AND mes <= 12),
  data_competencia date DEFAULT make_date((ano)::integer, (mes)::integer, 1),
  CONSTRAINT periodo_pkey PRIMARY KEY (id_periodo)
);

CREATE TABLE public.regiao (
  sigla_regiao character varying NOT NULL,
  nome character varying NOT NULL UNIQUE,
  CONSTRAINT regiao_pkey PRIMARY KEY (sigla_regiao)
);

CREATE TABLE public.estado (
  codigo_ibge smallint NOT NULL CHECK (codigo_ibge >= 11 AND codigo_ibge <= 53),
  sigla_uf character NOT NULL UNIQUE,
  nome character varying NOT NULL,
  sigla_regiao character varying NOT NULL,
  CONSTRAINT estado_pkey PRIMARY KEY (codigo_ibge),
  CONSTRAINT estado_sigla_regiao_fkey FOREIGN KEY (sigla_regiao) REFERENCES public.regiao(sigla_regiao)
);

CREATE TABLE public.municipio (
  codigo_ibge integer NOT NULL,
  nome character varying NOT NULL,
  codigo_ibge_estado smallint NOT NULL,
  CONSTRAINT municipio_pkey PRIMARY KEY (codigo_ibge),
  CONSTRAINT municipio_codigo_ibge_estado_fkey FOREIGN KEY (codigo_ibge_estado) REFERENCES public.estado(codigo_ibge)
);

CREATE TABLE public.instituicao (
  ispb character NOT NULL CHECK (ispb ~ '^[0-9]{8}$'::text),
  nome character varying NOT NULL,
  CONSTRAINT instituicao_pkey PRIMARY KEY (ispb)
);

CREATE TABLE public.fraude_med (
  id_periodo integer NOT NULL,
  qtd_pix_contestados bigint NOT NULL CHECK (qtd_pix_contestados >= 0),
  qtd_contestacoes_aceitas bigint NOT NULL CHECK (qtd_contestacoes_aceitas >= 0),
  qtd_contestacoes_rejeitadas bigint NOT NULL CHECK (qtd_contestacoes_rejeitadas >= 0),
  taxa_aceitas_por_100mil numeric NOT NULL CHECK (taxa_aceitas_por_100mil >= 0::numeric),
  qtd_usuarios_marcados_fraude bigint NOT NULL CHECK (qtd_usuarios_marcados_fraude >= 0),
  qtd_chaves_marcadas_fraude bigint NOT NULL CHECK (qtd_chaves_marcadas_fraude >= 0),
  valor_contestados_aceitos numeric NOT NULL CHECK (valor_contestados_aceitos >= 0::numeric),
  valor_residual_nao_devolvido numeric NOT NULL CHECK (valor_residual_nao_devolvido >= 0::numeric),
  percentual_devolucao numeric NOT NULL CHECK (percentual_devolucao >= 0::numeric AND percentual_devolucao <= 100::numeric),
  CONSTRAINT fraude_med_pkey PRIMARY KEY (id_periodo),
  CONSTRAINT fraude_med_id_periodo_fkey FOREIGN KEY (id_periodo) REFERENCES public.periodo(id_periodo)
);

CREATE TABLE public.devolucao_med (
  id_periodo integer NOT NULL,
  tipo_devolucao USER-DEFINED NOT NULL,
  quantidade bigint NOT NULL CHECK (quantidade >= 0),
  valor numeric NOT NULL CHECK (valor >= 0::numeric),
  CONSTRAINT devolucao_med_pkey PRIMARY KEY (id_periodo, tipo_devolucao),
  CONSTRAINT devolucao_med_id_periodo_fkey FOREIGN KEY (id_periodo) REFERENCES public.fraude_med(id_periodo)
);

CREATE TABLE public.nao_devolucao_med (
  id_periodo integer NOT NULL,
  motivo USER-DEFINED NOT NULL,
  quantidade bigint NOT NULL CHECK (quantidade >= 0),
  valor numeric NOT NULL CHECK (valor >= 0::numeric),
  CONSTRAINT nao_devolucao_med_pkey PRIMARY KEY (id_periodo, motivo),
  CONSTRAINT nao_devolucao_med_id_periodo_fkey FOREIGN KEY (id_periodo) REFERENCES public.fraude_med(id_periodo)
);

CREATE TABLE public.bloqueio_cautelar (
  id_periodo integer NOT NULL,
  desfecho USER-DEFINED NOT NULL,
  quantidade bigint NOT NULL CHECK (quantidade >= 0),
  valor numeric NOT NULL CHECK (valor >= 0::numeric),
  CONSTRAINT bloqueio_cautelar_pkey PRIMARY KEY (id_periodo, desfecho),
  CONSTRAINT bloqueio_cautelar_id_periodo_fkey FOREIGN KEY (id_periodo) REFERENCES public.fraude_med(id_periodo)
);

CREATE TABLE public.chave_pix_instituicao (
  id_periodo integer NOT NULL,
  ispb character NOT NULL,
  natureza_usuario USER-DEFINED NOT NULL,
  tipo_chave character varying NOT NULL,
  qtd_chaves integer NOT NULL CHECK (qtd_chaves >= 0),
  CONSTRAINT chave_pix_instituicao_pkey PRIMARY KEY (id_periodo, ispb, natureza_usuario, tipo_chave),
  CONSTRAINT chave_pix_instituicao_id_periodo_fkey FOREIGN KEY (id_periodo) REFERENCES public.periodo(id_periodo),
  CONSTRAINT chave_pix_instituicao_ispb_fkey FOREIGN KEY (ispb) REFERENCES public.instituicao(ispb)
);

CREATE TABLE public.transacao_municipio (
  id_periodo integer NOT NULL,
  codigo_ibge_municipio integer NOT NULL,
  papel USER-DEFINED NOT NULL,
  natureza USER-DEFINED NOT NULL,
  valor numeric NOT NULL CHECK (valor >= 0::numeric),
  qtd_transacoes bigint NOT NULL CHECK (qtd_transacoes >= 0),
  qtd_pessoas bigint NOT NULL CHECK (qtd_pessoas >= 0),
  CONSTRAINT transacao_municipio_pkey PRIMARY KEY (id_periodo, codigo_ibge_municipio, papel, natureza),
  CONSTRAINT transacao_municipio_id_periodo_fkey FOREIGN KEY (id_periodo) REFERENCES public.periodo(id_periodo),
  CONSTRAINT transacao_municipio_codigo_ibge_municipio_fkey FOREIGN KEY (codigo_ibge_municipio) REFERENCES public.municipio(codigo_ibge)
);
