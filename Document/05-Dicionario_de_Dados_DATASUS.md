# 05 - Dicionário de Dados DATASUS: Maternar

## 1. Visão Geral dos Sistemas Utilizados

O pipeline do Maternar coleta dados de seis sistemas do DATASUS, cada um alimentando um aspecto do modelo K-Means ou do contexto clínico da gestante.

| Sistema | Tabela PostgreSQL (`datasus.*`) | Função no Projeto |
| :--- | :--- | :--- |
| SINAN | `sinan_agravos_gestantes` | Doenças notificáveis em gestantes (sífilis, dengue, zika...) |
| SIM | `sim_mortalidade_materna` | Correlação dos clusters com óbitos maternos |
| CNES | `cnes_estabelecimentos` | Feature de distância à maternidade/UBS |
| SIA | `sia_prenatal` | Proxy de adesão ao pré-natal por procedimento |
| SISVAN | `sisvan_gestante` | IMC gestacional e estado nutricional por semana |

---

## 2. Mapeamento de Variáveis para o Modelo ML

Variáveis que entram diretamente nas features do K-Means ou são coletadas no app:

| Campo DATASUS | Sistema | Descrição | Mapeamento no App |
| :--- | :--- | :--- | :--- |
| `nu_peso` / `nu_altura` | SISVAN | Peso e altura da gestante | Coleta de peso/altura no cadastro |
| `nu_imc` | SISVAN | IMC calculado por semana gestacional | Calculado pelo Flask (Curva de Atalah) |
| `CO_LATITUDE` / `CO_LONGITUDE` | CNES | Coordenadas do estabelecimento | Calculado via CEP da gestante |
| `PA_PROC_ID` | SIA | Código do procedimento pré-natal | Proxy de cobertura por município |

---

## 3. SINAN — Agravos Notificáveis em Gestantes

Um registro por notificação de doença. Dados nacionais (sem divisão por estado).

### Agravos Coletados

| Código | Agravo | Relevância Gestacional |
| :--- | :--- | :--- |
| SIFG | Sífilis em Gestante | Transmissão vertical → sífilis congênita |
| SIFC | Sífilis Congênita | Desfecho fetal da sífilis não tratada |
| TOXG | Toxoplasmose Gestacional | Risco de dano neurológico fetal |
| TOXC | Toxoplasmose Congênita | Desfecho fetal |
| DENG | Dengue em Gestante | Complicações no parto e prematuridade |
| ZIKA | Zika Vírus | Microcefalia / Síndrome congênita |
| HEPA | Hepatites Virais | Transmissão vertical (HBV/HCV) |
| CHIK | Chikungunya | Complicações na gestação |

> **Filtro aplicado:** para agravos não exclusivos de gestantes (DENG, ZIKA, HEPA, CHIK), apenas registros com `CS_GESTANT` in (1, 2, 3, 4) são mantidos.

### Colunas Principais

| Coluna | Descrição | Valores |
| :--- | :--- | :--- |
| `agravo` | Código do agravo (campo do pipeline) | SIFG, SIFC, TOXG... |
| `DT_NOTIFIC` | Data de notificação | DDMMAAAA |
| `SG_UF_NOT` | UF de notificação | Sigla |
| `ID_MUNICIP` | Município de notificação | Código IBGE 6 dígitos |
| `CS_GESTANT` | Trimestre gestacional | 1=1º tri, 2=2º tri, 3=3º tri, 4=IG ignorada, 5=Não |
| `CS_RACA` | Raça/cor | 1–5 (padrão IBGE) |
| `CS_ESCOL_N` | Escolaridade | Código SINAN |

---

## 4. SIM — Mortalidade Materna

Óbitos filtrados por CID-10 O00–O99 (causas obstétricas diretas e indiretas). Usado para validar se os clusters de maior risco correlacionam com desfechos fatais.

### Colunas Principais

| Coluna | Descrição | Valores |
| :--- | :--- | :--- |
| `CAUSABAS` | Causa básica do óbito | CID-10 (ex: O14 = Pré-eclâmpsia) |
| `OBITOGRAV` | Óbito ocorreu durante gravidez | 1=Sim, 2=Não, 9=Ignorado |
| `OBITOPUERP` | Óbito no puerpério | 1=Até 42 dias, 2=43d–1ano, 3=Não |
| `SEMANAGEST` | Semana gestacional no óbito | Numérico |
| `RACACOR` | Raça/cor da falecida | 1–5 (padrão IBGE) |
| `ESC2010` | Escolaridade | 1–5 |
| `CODMUNRES` | Município de residência | Código IBGE 6 dígitos |

---

## 5. CNES — Estabelecimentos de Saúde

Snapshots semestrais (janeiro e julho) dos estabelecimentos de saúde por estado. Alimenta a feature de cobertura assistencial no modelo.

### Colunas Principais

| Coluna | Descrição | Uso no Modelo |
| :--- | :--- | :--- |
| `CODMUNICIPIO` | Código IBGE do município | Linkage para calcular cobertura |
| `CNES` | Código nacional do estabelecimento | Identificador único |
| `TP_UNIDADE` | Tipo de unidade | 1=Hospital, 2=UBS, 5=Maternidade... |
| `QT_LEITO_OBS` | Leitos obstétricos disponíveis | Feature `LEITOS_OBS_MUN` |
| `CO_LATITUDE` / `CO_LONGITUDE` | Coordenadas geográficas | Feature `DISTANCIA_UTI` |

> **Feature derivada:** `DISTANCIA_UTI` = distância euclidiana (ou Haversine) entre o município de residência da gestante e a maternidade com leito obstétrico mais próxima.

---

## 6. SIA — Proxy SISPreNatal (Produção Ambulatorial)

O SISPreNatal não exporta microdados via FTP. O SIA registra todos os procedimentos ambulatoriais do SUS, incluindo os de pré-natal, e é usado como proxy de adesão.

### Procedimentos Pré-Natais Filtrados (SIGTAP)

| Código | Procedimento |
| :--- | :--- |
| 0301010072 | Consulta pré-natal |
| 0209010061 | Ultrassom obstétrico 1º trimestre |
| 0209010070 | Ultrassom obstétrico 2º/3º trimestre |
| 0202050025 | VDRL na gestação |
| 0214010015 | Anti-HIV na gestação |
| 0202010597 | Glicemia em jejum na gestação |
| 0202010201 | Toxoplasmose IgG/IgM |
| 0301060029 | Consulta de puerpério (42 dias) |

### Colunas Principais

| Coluna | Descrição |
| :--- | :--- |
| `PA_MUNPCN` | Município do paciente (código IBGE) |
| `PA_PROC_ID` | Código do procedimento realizado |
| `PA_SEXO` | Sexo do paciente (F = feminino) |
| `PA_IDADE` | Idade do paciente |
| `PA_QTDPRO` | Quantidade produzida |
| `PA_QTDAPR` | Quantidade aprovada pelo SUS |

---

## 7. SISVAN — Estado Nutricional de Gestantes

Dados de acompanhamento nutricional por semana gestacional. Disponíveis via basedosdados.org (não via FTP do DATASUS).

### Colunas Principais

| Coluna | Descrição | Uso no Modelo |
| :--- | :--- | :--- |
| `nu_semana_gestacional` | Semana gestacional na aferição | Contexto temporal do IMC |
| `nu_peso` | Peso atual (kg) | Feature de ganho de peso |
| `nu_altura` | Altura (m) | Base para cálculo do IMC |
| `nu_imc` | IMC calculado | Feature `IMC_GESTACIONAL` |
| `ds_st_nutricional` | Estado nutricional | Baixo Peso / Eutrófico / Sobrepeso / Obesidade |
| `nu_imc_pre_gestacional` | IMC pré-gestacional | Base para projeção de ganho adequado |
| `co_municipio_ibge` | Código IBGE do município | Linkage geográfico |

> **Curva de Atalah:** o IMC é classificado de acordo com a curva de Atalah (padrão SISVAN), que define faixas de IMC aceitáveis por semana gestacional. O app usa essa classificação para orientar ganho de peso adequado.

---

## 8. Filtros de Qualidade no Treinamento

- **Temporal:** Registros de 2019 a 2024 (preferencial); banco contém 2010–2026 conforme disponibilidade por sistema.
- **Geográfico:** Manter apenas registros com código de município válido (6 dígitos, código IBGE existente).
- **SISVAN — semana gestacional:** usar apenas registros com `nu_semana_gestacional IS NOT NULL` (dados do formato parquet, 2019+); registros carregados do formato CSV (2010–2018) têm esse campo NULL.

---

## 9. Registros no banco (estado atual — 2026-05-24)

| Sistema | Tabela | Registros |
|---------|--------|-----------|
| SINAN | `datasus.sinan_agravos_gestantes` | 1.322.606 |
| SIM | `datasus.sim_mortalidade_materna` | 15.711.535 |
| CNES | `datasus.cnes_estabelecimentos` | 8.528.568 |
| SIA | `datasus.sia_prenatal` | 20.477.352 |
| SISVAN | `datasus.sisvan_gestante` | 1.201.675 |
| **TOTAL** | — | **47.241.736** |

> Para documentação completa de cada dataset (todos os campos, domínios, fontes oficiais, queries analíticas): ver `Document/12-Documentacao_Datasets_DATASUS.md`
