# 12 — Documentação Completa dos Datasets DATASUS — Projeto Maternar

> Última atualização: 2026-05-24
> Fontes: documentações oficiais SVS/MS, DATASUS, PCDaS/Fiocruz, Portal de Dados Abertos SUS, IBGE Metadados
> Pipeline: `ApiDatasus/main.py` → parquet → `ApiDatasus/db_loader.py` → PostgreSQL (`maternar.datasus.*`)

---

## Visão Geral dos Sistemas

| Sistema | Tabela PostgreSQL | Registros | Cobertura | Granularidade |
|---------|-------------------|-----------|-----------|---------------|
| SINAN | `datasus.sinan_agravos_gestantes` | 1.322.606 | 2014–2026 | 1 linha por notificação de agravo |
| SIM | `datasus.sim_mortalidade_materna` | 15.711.535 | 2014–2025 | 1 linha por óbito materno (CID O00–O99) |
| CNES | `datasus.cnes_estabelecimentos` | 8.528.568 | 2014–2025 | 1 linha por estabelecimento por competência |
| SIA | `datasus.sia_prenatal` | 20.477.352 | 2014–2026 | 1 linha por procedimento pré-natal aprovado |
| SISVAN | `datasus.sisvan_gestante` | 1.201.675 | 2010–2023 | 1 linha por atendimento nutricional de gestante |
| **TOTAL** | — | **47.241.736** | — | — |

---

## 1. SINAN — Sistema de Informação de Agravos de Notificação

### 1.1 Descrição oficial

O SINAN é o sistema nacional de vigilância epidemiológica, gerenciado pela Secretaria de Vigilância em Saúde (SVS/MS). Seu objetivo é "coletar, transmitir e disseminar dados gerados rotineiramente pelo sistema de vigilância epidemiológica das três esferas de governo" por meio de rede informatizada de notificação e investigação de doenças compulsórias.

**Dois subsistemas paralelos:**
- **SINAN Net** (offline) — cobre a maioria das doenças; arquivos DBC/DBF via FTP DATASUS
- **SINAN Online** (tempo real) — cobre dengue e chikungunya; atualização diária

**Base legal:** Portaria GM/MS nº 217/2023 (Lista Nacional de Notificação Compulsória)
**Responsável:** Coordenação-Geral de Vigilância em Saúde (SVS/MS)

**Download no projeto:** `pysus` → FTP DATASUS, nível nacional (arquivos AAUU\_AGRAVO.dbc)

### 1.2 Agravos coletados no projeto

| Código | Descrição | CID-10 | Filtro aplicado |
|--------|-----------|--------|-----------------|
| SIFG | Sífilis em Gestante | A51/Z34 | Agravo exclusivo — sem filtro adicional |
| SIFC | Sífilis Congênita | A50 | Agravo exclusivo — sem filtro adicional |
| TOXG | Toxoplasmose Gestacional | O98.6 | Agravo exclusivo — sem filtro adicional |
| TOXC | Toxoplasmose Congênita | P37.1 | Agravo exclusivo — sem filtro adicional |
| DENG | Dengue | A90 | `CS_GESTANT IN (1,2,3,4)` |
| ZIKA | Zika Vírus | A92.8 | `CS_GESTANT IN (1,2,3,4)` |
| HEPA | Hepatites Virais | B15–B19 | `CS_GESTANT IN (1,2,3,4)` |
| CHIK | Chikungunya | A92.0 | `CS_GESTANT IN (1,2,3,4)` |

### 1.3 Schema PostgreSQL — `datasus.sinan_agravos_gestantes`

| Coluna | Tipo PostgreSQL | Campo original SINAN | Descrição | Domínio / Exemplo |
|--------|-----------------|----------------------|-----------|-------------------|
| `id` | BIGSERIAL PK | — | Identificador gerado pelo pipeline | — |
| `agravo` | VARCHAR(4) NOT NULL | — | Código do agravo (derivado do arquivo) | SIFG, SIFC, TOXG, TOXC, DENG, ZIKA, HEPA, CHIK |
| `ano` | SMALLINT NOT NULL | — | Ano da notificação (derivado do arquivo) | 2014–2026 |
| `dt_notific` | VARCHAR(8) | `DT_NOTIFIC` | Data de notificação | DDMMAAAA (ex: 15062024) |
| `sg_uf_not` | VARCHAR(2) | `SG_UF_NOT` | Código IBGE da UF de notificação | 35 (SP), 33 (RJ), 41 (PR) |
| `id_municip` | VARCHAR(6) | `ID_MUNICIP` | Código IBGE do município de notificação | 355240 |
| `dt_nasc` | VARCHAR(8) | `DT_NASC` | Data de nascimento da paciente | DDMMAAAA |
| `cs_sexo` | VARCHAR(1) | `CS_SEXO` | Sexo biológico | M=Masculino, F=Feminino, I=Ignorado |
| `cs_gestant` | SMALLINT | `CS_GESTANT` | Status gestacional | 1=1º Trimestre, 2=2º Trimestre, 3=3º Trimestre, 4=Idade gestacional ignorada, 5=Não, 6=Não se aplica, 9=Ignorado |
| `cs_raca` | SMALLINT | `CS_RACA` | Raça/Cor | 1=Branca, 2=Preta, 3=Amarela, 4=Parda, 5=Indígena, 9=Ignorado |
| `cs_escol_n` | SMALLINT | `CS_ESCOL_N` | Escolaridade (anos de estudo) | 0=Nenhuma, 1=1–3 anos, 2=4–7 anos, 3=8–11 anos, 4=12 e mais, 9=Ignorado |
| `sg_uf` | VARCHAR(2) | `SG_UF` | Código IBGE da UF de residência | 35, 33, 41 |
| `id_mn_resi` | VARCHAR(6) | `ID_MN_RESI` | Código IBGE do município de residência | 355240 |
| `dado_raw` | JSONB | (todas as colunas) | Registro completo original (todas as colunas do arquivo) | `{"TP_NOT":"2","ID_AGRAVO":"A501",...}` |
| `inserted_at` | TIMESTAMPTZ | — | Timestamp da carga no banco | 2026-05-17T22:04:36Z |

**Índices:** `(agravo, ano)`, `(id_municip)`, `(cs_gestant)`, `(sg_uf_not)`

### 1.4 Campos específicos por agravo (disponíveis em `dado_raw`)

#### SIFG — Sífilis em Gestante (~32 colunas)

| Campo SINAN | Descrição | Domínio |
|-------------|-----------|---------|
| `TRIMESTRE` | Trimestre gestacional ao diagnóstico | 1=1º Tri, 2=2º Tri, 3=3º Tri, 4=IG ignorada |
| `TPEXAME_1` | Tipo do 1º exame sorológico | 1=Treponêmico, 2=Não-treponêmico (VDRL/RPR), 3=Ambos, 9=Ignorado |
| `TPEXAME_2` | Tipo do 2º exame sorológico | idem |
| `RESUL_1` | Resultado do 1º teste | 1=Reagente, 2=Não reagente, 3=Inconclusivo, 9=Ignorado |
| `TITU_1` | Titulação do 1º teste não-treponêmico | 1:1, 1:2, 1:4, 1:8... |
| `TRATAMENT` | Esquema de tratamento materno | 1=Penicilina 2,4MUI, 2=Penicilina 4,8MUI, 3=Penicilina 7,2MUI, 4=Outro, 5=Não realizado, 9=Ignorado |
| `TRAT_PARC` | Tratamento do parceiro | idem |
| `CLASSI_FIN` | Classificação final do caso | 1=Confirmado laboratorial, 2=Confirmado clínico-epidemiológico, 5=Descartado |

#### SIFC — Sífilis Congênita (~64 colunas)

| Campo SINAN | Descrição | Domínio |
|-------------|-----------|---------|
| `DT_NASC_MN` | Data de nascimento da mãe | DDMMAAAA |
| `DIAG_MAE` | Momento do diagnóstico materno | 1=Pré-natal, 2=Parto/curetagem, 3=Pós-parto, 4=Não realizado, 9=Ignorado |
| `TRAT_MAE` | Tratamento materno | 1=Penicilina 2,4MUI, 2=Penicilina 4,8MUI, 3=Penicilina 7,2MUI, 4=Outro, 5=Não realizado, 9=Ignorado |
| `TP_PARTO` | Tipo de parto | 1=Vaginal, 2=Cesariana, 9=Ignorado |
| `PESO` | Peso ao nascer (gramas) | numérico |
| `SEMANA_GES` | Semanas gestacionais ao parto | numérico |
| `MANIFESTA` | Manifestações clínicas no RN | 1=Sim, 2=Não, 9=Ignorado |
| `CLAS_CONG` | Classificação da sífilis congênita | 1=Recente, 2=Tardia, 3=Natimorto, 9=Ignorado |
| `LABC_SANGU` | Sangue do RN — resultado | 1=Reagente, 2=Não reagente, 9=Ignorado |
| `LABC_LIQUO` | Líquor do RN — resultado | idem |

#### TOXG / TOXC — Toxoplasmose Gestacional / Congênita (~38 colunas)

| Campo SINAN | Descrição | Domínio |
|-------------|-----------|---------|
| `IGM_MAE` | IgM materno | 1=Reagente, 2=Não reagente, 3=Inconclusivo, 9=Ignorado |
| `IGG_MAE` | IgG materno | idem |
| `AVIDEZ` | Teste de avidez de IgG | 1=Alta avidez, 2=Baixa avidez, 3=Inconclusivo, 9=Ignorado |
| `TRIMEST_DG` | Trimestre ao diagnóstico | 1=1º Tri, 2=2º Tri, 3=3º Tri, 9=Ignorado |
| `TRATAMENT` | Tratamento realizado | 1=Espiramicina, 2=Sulfadiazina+pirimetamina+ácido folínico, 3=Outro, 4=Não realizado, 9=Ignorado |
| `IGM_RN` | IgM neonatal (TOXC) | 1=Reagente, 2=Não reagente, 9=Ignorado |
| `MANIFESTAC` | Manifestações clínicas (TOXC) | 1=Sim (+ subcampos: coriorretinite, calcificações), 2=Não, 9=Ignorado |
| `EVOLUCAO` | Evolução do caso | 1=Cura, 2=Óbito pelo agravo, 3=Óbito por outra causa, 4=Perda seguimento, 9=Ignorado |

#### DENG / ZIKA / CHIK — Arboviroses (~80–121 colunas)

| Campo SINAN | Descrição | Domínio |
|-------------|-----------|---------|
| `FEBRE` | Febre presente | 1=Sim, 2=Não |
| `MIALGIA` | Mialgia | 1=Sim, 2=Não |
| `CEFALEIA` | Cefaleia | 1=Sim, 2=Não |
| `EXANTEMA` | Exantema | 1=Sim, 2=Não |
| `ARTRALGIA` | Artralgia | 1=Sim, 2=Não |
| `CONJUNTVIT` | Conjuntivite não purulenta | 1=Sim, 2=Não |
| `HOSPITALIZ` | Hospitalização | 1=Sim, 2=Não, 9=Ignorado |
| `S1_IGM` | IgM sorologia amostra 1 | 1=Reagente, 2=Não reagente, 3=Inconclusivo, 4=Não realizado, 9=Ignorado |
| `RESUL_PCR` | Resultado PCR | 1=Positivo, 2=Negativo, 3=Inconclusivo, 4=Não realizado, 9=Ignorado |
| `NS1_N` | Antígeno NS1 (dengue) | 1=Positivo, 2=Negativo, 3=Inconclusivo, 4=Não realizado |
| `SOROTIPO` | Sorotipo (dengue) | 1=DENV1, 2=DENV2, 3=DENV3, 4=DENV4, 5=Não realizado |
| `CON_DOENCA` | Doença notificada | 1=Dengue, 2=Chikungunya, 3=Zika |
| `PLAQ_MENOR` | Menor contagem de plaquetas | numérico (células/mm³) |
| `CLASSI_FIN` | Classificação final | 1=Dengue, 2=Dengue c/sinais de alarme, 3=Dengue grave, 4=Chikungunya, 5=Descartado |
| `ALRM_HIPOT` | Sinal de alarme — hipotensão | 1=Sim, 2=Não |
| `ALRM_PLAQ` | Sinal de alarme — plaquetopenia | 1=Sim, 2=Não |
| `GRAV_PULSO` | Sinal de gravidade — pulso | 1=Sim, 2=Não |

#### HEPA — Hepatites Virais (~45 colunas)

| Campo SINAN | Descrição | Domínio |
|-------------|-----------|---------|
| `TP_HEPATIT` | Tipo de hepatite | 1=A, 2=B, 3=C, 4=D (Delta), 5=E, 6=Não especificada |
| `HBSAG` | HBsAg (hepatite B) | 1=Reagente, 2=Não reagente, 3=Inconclusivo, 9=Ignorado |
| `ANTIHBC_M` | Anti-HBc IgM | idem |
| `ANTI_VHC` | Anti-HCV | idem |
| `RNA_VHC` | RNA do HCV | 1=Detectável, 2=Não detectável, 3=Não realizado, 9=Ignorado |
| `ANTIVHA` | Anti-HAV IgM | 1=Reagente, 2=Não reagente, 3=Inconclusivo, 9=Ignorado |
| `VACINAÇÃO` | Vacinação HBV | 1=Completo (3 doses), 2=Incompleto, 3=Não vacinado, 9=Ignorado |
| `TRAT_ATUAL` | Em tratamento | 1=Sim, 2=Não, 9=Ignorado |
| `CARGA_VIRA` | Carga viral | numérico |
| `GESTANTE` | Gestante ao momento da notificação | 1=Sim, 2=Não, 9=Ignorado |

### 1.5 Cobertura e limitações

- **Cobertura geográfica:** Nacional — todos os 5.570 municípios
- **Cobertura temporal:** Varia por agravo; SIFG/SIFC desde 2007; TOXG/TOXC desde 2019; arboviroses desde 2014
- **Subnotificação estimada:** 30–60% para muitas doenças
- **Qualidade:** Campos de encerramento frequentemente incompletos (encerramento tardio); inconsistência entre SINAN Net e SINAN Online
- **Espírito Santo:** usa e-SUS SINAN separado para dengue desde 2020 — pode gerar lacuna nos dados nacionais

### 1.6 Links oficiais

- Portal SINAN: http://portalsinan.saude.gov.br
- FTP DATASUS: ftp://ftp.datasus.gov.br/dissemin/publicos/SINAN/
- Dicionário Sífilis Gestante: http://portalsinan.saude.gov.br/images/documentos/Agravos/Sifilis-Ges/DIC_DADOS_Gestante_Sifilis_v5.pdf
- Dicionário Sífilis Congênita: http://portalsinan.saude.gov.br/images/documentos/Agravos/Sifilis-Con/DIC_DADOS_Sifilis_Congenita_v5.pdf
- Dicionário Dengue/Chikungunya Online: http://portalsinan.saude.gov.br/images/documentos/Agravos/Dengue/DIC_DADOS_ONLINE.pdf
- Dicionário Hepatites Virais: http://portalsinan.saude.gov.br/images/documentos/Agravos/Hepatites%20Virais/DIC_DADOS_Hepatite_v5.pdf
- Metadados IBGE: https://ces.ibge.gov.br/base-de-dados/metadados/ministerio-da-saude/sistema-de-informacoes-de-agravos-de-notificacao-sinan

---

## 2. SIM — Sistema de Informações sobre Mortalidade

### 2.1 Descrição oficial

O SIM é o sistema nacional de mortalidade, criado pelo DATASUS/MS em 1975 e operacional desde 1976 — o mais antigo sistema de informação em saúde do Brasil. Obtém regularmente dados sobre mortalidade para subsidiar a gestão em saúde pública. As causas de óbito são codificadas segundo a CID-10. Para mortalidade materna especificamente, é a principal fonte de dados para cálculo da Razão de Mortalidade Materna (RMM), usando o Capítulo XV (O00–O99) e óbitos maternos tardios (O96, O97).

**Instrumento de coleta:** Declaração de Óbito (DO) — formulário padronizado tríplice, preenchido pelo médico assistente ou, na ausência, por duas testemunhas. Há três variantes: DO (geral), DOM (maternos) e DOFET (fetais).

**Base legal:** Portaria SVS/MS nº 116/2009
**Responsável:** CGIAE — Coordenação-Geral de Informações e Análise Epidemiológicas, SVS/MS

**Download no projeto:** `pysus` → FTP DATASUS, por estado e ano (arquivos DOUF\_AAAA.dbc)

**Filtro aplicado:** mantidos apenas óbitos com `OBITOGRAV` preenchido **OU** `CAUSABAS` iniciando com "O" (CID-10 O00–O99).

### 2.2 Schema PostgreSQL — `datasus.sim_mortalidade_materna`

| Coluna | Tipo PostgreSQL | Campo original SIM | Descrição | Domínio / Exemplo |
|--------|-----------------|-------------------|-----------|-------------------|
| `id` | BIGSERIAL PK | — | Identificador gerado | — |
| `estado` | CHAR(2) NOT NULL | — | UF do arquivo (derivado do nome) | SP, RJ, MG |
| `ano` | SMALLINT NOT NULL | — | Ano do óbito (derivado do arquivo) | 2014–2025 |
| `causabas` | VARCHAR(10) | `CAUSABAS` | CID-10 da causa básica do óbito | O140 (pré-eclâmpsia), O210 (vômitos), O720 (hemorragia pós-parto) |
| `causabas_o` | VARCHAR(10) | `CAUSABAS_O` | CID-10 original antes de recodificação | — |
| `obitograv` | SMALLINT | `OBITOGRAV` | Óbito durante a gravidez | 1=Sim, 2=Não, 9=Ignorado |
| `obitopuerp` | SMALLINT | `OBITOPUERP` | Óbito no puerpério | 1=Sim até 42 dias, 2=Sim de 43 dias a 1 ano, 3=Não, 9=Ignorado |
| `dtobito` | VARCHAR(8) | `DTOBITO` | Data do óbito | DDMMAAAA |
| `dtnasc` | VARCHAR(8) | `DTNASC` | Data de nascimento | DDMMAAAA |
| `sexo` | SMALLINT | `SEXO` | Sexo | 0=Ignorado, 1=Masculino, 2=Feminino |
| `racacor` | SMALLINT | `RACACOR` | Raça/Cor | 1=Branca, 2=Preta, 3=Amarela, 4=Parda, 5=Indígena, 9=Ignorado |
| `esc` | SMALLINT | `ESC` | Escolaridade (anos) | 1=Nenhuma, 2=1–3 anos, 3=4–7 anos, 4=8–11 anos, 5=12 e mais, 9=Ignorado |
| `esc2010` | SMALLINT | `ESC2010` | Escolaridade escala 2010 | 0=Sem instrução, 1=Fundamental incompleto, 2=Fundamental completo, 3=Médio incompleto, 4=Médio completo, 5=Superior incompleto, 6=Superior completo, 9=Ignorado |
| `codmunres` | VARCHAR(6) | `CODMUNRES` | Código IBGE do município de residência | 330455 |
| `codmunocor` | VARCHAR(6) | `CODMUNOCOR` | Código IBGE do município de ocorrência | 330455 |
| `gestacao` | SMALLINT | `GESTACAO` | Semanas gestacionais na data do óbito | 1=<22 semanas, 2=22–27 sem, 3=28–31 sem, 4=32–36 sem, 5=37–41 sem, 6=42 sem e mais, 9=Ignorado |
| `semanagest` | VARCHAR(10) | `SEMANAGEST` | Semana gestacional em texto | 39 |
| `tpmorteoco` | SMALLINT | `TPMORTEOCO` | Local/tipo de ocorrência do óbito | 1=Hospital, 2=Outro estab. saúde, 3=Domicílio, 4=Via pública, 5=Outros, 9=Ignorado |
| `dado_raw` | JSONB | (todas) | Registro completo original | — |
| `inserted_at` | TIMESTAMPTZ | — | Timestamp da carga | — |

**Índices:** `(estado, ano)`, `(causabas)`, `(codmunres)`

### 2.3 Faixas CID-10 para mortalidade materna (Capítulo XV)

| Código | Descrição |
|--------|-----------|
| O00–O08 | Gravidez terminada em aborto |
| O10–O16 | Edema, proteinúria e transtornos hipertensivos na gravidez (ex: O14=Pré-eclâmpsia) |
| O20–O29 | Outras afecções maternas relacionadas com a gravidez |
| O30–O48 | Assistência à mãe por afecções fetais e problemas obstétricos |
| O60–O75 | Complicações do trabalho de parto e do parto |
| O85–O92 | Complicações relacionadas principalmente ao puerpério |
| O94–O99 | Outras afecções obstétricas (ex: O98=Doenças infecciosas e parasitárias) |
| O96 | Morte materna tardia (43 dias a 1 ano após parto) |
| O97 | Sequelas de causa obstétrica direta (mais de 1 ano) |

### 2.4 Variáveis maternas específicas no `dado_raw`

| Campo DO | Descrição | Domínio |
|----------|-----------|---------|
| `OBITOPARTO` | Óbito em relação ao parto | 1=Antes, 2=Durante, 3=Depois, 9=Ignorado |
| `GRAVIDEZ` | Tipo de gravidez | 1=Única, 2=Dupla, 3=Tripla e mais, 9=Ignorado |
| `PARTO` | Tipo de parto | 1=Vaginal, 2=Cesariano, 9=Ignorado |
| `ASSISTMED` | Assistência médica recebida | 1=Com assistência, 2=Sem assistência, 9=Ignorado |
| `NECROPSIA` | Necrópsia realizada | 1=Sim, 2=Não, 9=Ignorado |
| `CIRCOBITO` | Circunstância do óbito (violência) | 1=Acidente, 2=Suicídio, 3=Homicídio, 4=Outros, 9=Ignorado |
| `LINHAA`–`LINHAE` | Causa em cada linha da DO (CID-10) | Códigos CID-10 |

### 2.5 Cobertura e limitações

- **Cobertura geográfica:** Nacional; desagregação municipal
- **Cobertura temporal:** 1979 (parcial); completo nacionalmente desde 1994; CID-10 a partir de 1996
- **Sub-registro:** estimado em ~10–15% nacional; maior no Norte/Nordeste
- **Subnotificação materna:** óbitos maternos frequentemente codificados em outros capítulos CID-10
- **Campos 43/44 (`OBITOGRAV`/`OBITOPUERP`):** frequentemente em branco em óbitos extra-hospitalares
- **Defasagem:** ~1,5 ano entre o ano do óbito e publicação final anual

### 2.6 Links oficiais

- DATASUS Mortalidade: https://datasus.saude.gov.br/mortalidade-desde-1996-pela-cid-10/
- Portal SIM: http://sim.saude.gov.br/
- FTP DATASUS: ftp://ftp.datasus.gov.br/dissemin/publicos/SIM/
- Dicionário tabela DOM (SVS): https://svs.aids.gov.br/download/Dicionario_de_Dados_SIM_tabela_DOM.pdf
- Estrutura SIM (CGIAE): https://diaad.s3.sa-east-1.amazonaws.com/sim/Mortalidade_Geral+-+Estrutura.pdf
- PCDaS/Fiocruz: https://pcdas.icict.fiocruz.br/conjunto-de-dados/sistema-de-informacoes-de-mortalidade-sim/dicionario-de-variaveis/
- Metadados IBGE: https://ces.ibge.gov.br/base-de-dados/metadados/ministerio-da-saude/sistema-de-informacoes-de-mortalidade-sim.html

---

## 3. CNES — Cadastro Nacional de Estabelecimentos de Saúde

### 3.1 Descrição oficial

O CNES é o registro oficial nacional de estabelecimentos de saúde, criado em 2000 e tornado obrigatório pela Portaria GM/MS nº 1.646/2006. Cobre todos os estabelecimentos de saúde do país (públicos e privados) quanto à capacidade instalada e força de trabalho, independentemente de vinculação ao SUS. É a base operacional de mais de 112 sistemas de informação de saúde (SIA, SIH, e-SUS APS, SINAN, etc.).

**Responsável:** COSIH — Coordenação de Sistemas de Informação Hospitalar, DATASUS/SE/MS
**Atualização:** mínimo mensal pelos gestores municipais via SCNES

**Download no projeto:** `pysus` → FTP DATASUS, por estado, ano e mês — snapshots de janeiro (mes=1) e julho (mes=7) (arquivos DCGRUPOestadoAAMM.dbc)

### 3.2 Schema PostgreSQL — `datasus.cnes_estabelecimentos`

| Coluna | Tipo PostgreSQL | Campo original CNES | Descrição | Domínio / Exemplo |
|--------|-----------------|---------------------|-----------|-------------------|
| `id` | BIGSERIAL PK | — | Identificador gerado | — |
| `estado` | CHAR(2) NOT NULL | — | UF (derivada do arquivo) | SP, RJ, AM |
| `ano` | SMALLINT NOT NULL | — | Ano do snapshot | 2014–2025 |
| `mes` | SMALLINT NOT NULL | — | Mês do snapshot | 1 (janeiro) ou 7 (julho) |
| `grupo` | VARCHAR(2) NOT NULL | — | Grupo do arquivo | ST=Estabelecimentos, DC=Dados Complementares, LT=Leitos |
| `codmunicipio` | VARCHAR(6) | `CODMUNICIPIO` / `CO_MUNICIP` | Código IBGE do município | 350950 |
| `cnes` | VARCHAR(7) | `CNES` / `CO_CNES` | Código CNES do estabelecimento | 2030408 |
| `tp_unidade` | VARCHAR(2) | `TP_UNIDADE` / `TPUNIDADE` | Tipo de unidade (ver tabela abaixo) | 05=Hospital Geral, 01=Posto de Saúde |
| `qt_leito_obs` | INTEGER | `QT_LEITO_OBS` | Quantidade de leitos obstétricos | 4 |
| `co_latitude` | DECIMAL(10,6) | `CO_LATITUDE` / `LATITUDE` | Latitude geográfica | -23.550520 |
| `co_longitude` | DECIMAL(10,6) | `CO_LONGITUDE` / `LONGITUDE` | Longitude geográfica | -46.633309 |
| `dado_raw` | JSONB | (todas) | Registro completo | — |
| `inserted_at` | TIMESTAMPTZ | — | Timestamp da carga | — |

**Índices:** `(estado, ano, mes)`, `(codmunicipio)`, `(tp_unidade)`

### 3.3 Tipos de unidade (TP_UNIDADE) — domínio completo relevante

| Código | Descrição |
|--------|-----------|
| 01 | Posto de Saúde |
| 02 | Centro de Saúde / Unidade Básica de Saúde |
| 04 | Policlínica |
| 05 | Hospital Geral |
| 07 | Hospital Especializado |
| 15 | Unidade Mista |
| 36 | Clínica / Centro de Especialidade |
| 39 | Unidade de Apoio Diagnose e Terapia (SADT Isolado) |
| 61 | Centro de Parto Normal Isolado |
| 65 | Pronto Socorro Geral |
| 67 | Pronto Socorro Especializado |
| 70 | Centro de Atenção Psicossocial (CAPS) |
| 73 | Pronto Atendimento (UPA) |
| 79 | Unidade de Vigilância em Saúde |
| 83 | Polo de Academia da Saúde |
| 84 | Unidade Exec. Atenção Primária à Saúde |

### 3.4 Campos relevantes em `dado_raw` (grupo ST — ~30 colunas)

| Campo CNES | Descrição | Domínio |
|------------|-----------|---------|
| `NOMEFANT` | Nome fantasia do estabelecimento | texto livre |
| `NOMEPAD` | Nome oficial registrado | texto livre |
| `ESFERA_A` | Esfera administrativa | 1=Federal, 2=Estadual, 3=Municipal, 4=Privado |
| `TP_PREST` | Tipo de prestador | 1=Público federal, 2=Público estadual, 3=Público municipal, 4=Filantrópico, 5=Privado |
| `VINC_SUS` | Vinculação ao SUS | 1=Sim, 2=Não |
| `TURNO_AT` | Turno de atendimento | 1=Turnos, 2=24h contínuo, 3=Turnos e plantão, 4=Por agendamento |
| `NIV_HIER` | Nível de hierarquia | 1=Atenção básica, 2=Policlínica, 3=Hospital geral... |
| `URGEMERG` | Pronto-socorro / emergência | 1=Sim, 0=Não |
| `CENTROBS` | Centro obstétrico | 1=Sim, 0=Não |
| `CENTRNEO` | Unidade neonatal | 1=Sim, 0=Não |
| `AV_ACRED` | Acreditação hospitalar | 1=Sim, 2=Não, 9=Ignorado |
| `COD_CEP` | CEP do estabelecimento | 8 dígitos |

### 3.5 Campos relevantes em `dado_raw` (grupo LT — leitos)

| Campo CNES | Descrição | Domínio |
|------------|-----------|---------|
| `CODLEITO` | Código da especialidade do leito | código DATASUS |
| `QTLEITP1` | Leitos cirúrgicos existentes | numérico |
| `QTLEITP2` | Leitos clínicos existentes | numérico |
| `QTLEITP3` | Leitos complementares (UTI/UCI) existentes | numérico |
| `QTLEITSU1` | Leitos cirúrgicos SUS | numérico |
| `QTLEITSU2` | Leitos clínicos SUS | numérico |
| `QTLEITSU3` | Leitos complementares SUS | numérico |
| `TP_LEITO` | Tipo do leito | 1=Cirúrgico, 2=Clínico, 3=Complementar, 4=Obstétrico, 5=Pediátrico |

> **Definições importantes:**
> - **Leitos existentes:** leitos habitualmente utilizados para internação, mesmo que temporariamente indisponíveis (informado pelo gestor)
> - **Leitos SUS:** leitos ativos disponíveis para internação SUS
> - **Leitos não-SUS:** calculado automaticamente como (existentes − SUS)

### 3.6 Uso no modelo K-Means do Maternar

- `co_latitude` / `co_longitude`: calculada distância Haversine entre o município da gestante e a maternidade com leito obstétrico mais próxima → feature `DISTANCIA_UTI`
- `qt_leito_obs` + `tp_unidade`: avaliar capacidade instalada obstétrica por município → feature `LEITOS_OBS_MUN`
- `VINC_SUS + CENTROBS`: identificar maternidades SUS com centro obstétrico

### 3.7 Cobertura e limitações

- **Cobertura:** Todos estabelecimentos de saúde do Brasil (públicos e privados)
- **Temporal:** Mensal desde agosto 2005 (PCDaS); projeto usa Jan e Jul de cada ano
- **Dados autodeclarados:** sujeitos a sub-registro e atraso de atualização
- **Coordenadas:** qualidade variável; Portaria 359/2019 mandou georreferenciamento mas conformidade incompleta
- **Leitos:** capacidade registrada ≠ ocupação real

### 3.8 Links oficiais

- Portal CNES: https://cnes.datasus.gov.br
- Documentação CNES: https://cnes.datasus.gov.br/pages/downloads/documentacao.jsp
- Wiki Saúde CNES: https://wiki.saude.gov.br/cnes/index.php/Página_principal
- Notas Técnicas (TABNET): http://tabnet.datasus.gov.br/cgi/cnes/NT_Estabelecimentos.htm
- PCDaS Dicionário: https://pcdas.icict.fiocruz.br/conjunto-de-dados/cadastro-nacional-de-estabelecimentos-de-saude/dicionario-de-variaveis/
- FTP DATASUS: ftp://ftp.datasus.gov.br/dissemin/publicos/CNES/

---

## 4. SIA — Sistema de Informações Ambulatoriais (Pré-Natal)

### 4.1 Descrição oficial

O SIA foi estabelecido pela Portaria GM/MS nº 896 (29/06/1990) e é operacional desde julho de 1994. Registra todos os procedimentos ambulatoriais do SUS por meio de dois instrumentos: **BPA** (Boletim de Produção Ambulatorial) e **APAC** (Autorização de Procedimentos de Alta Complexidade/Custo).

**Responsável:** DRAC/SAS/MS — Departamento de Regulação, Avaliação e Controle
**Codificação:** SIGTAP — Sistema de Gerenciamento da Tabela de Procedimentos, Medicamentos e OPM do SUS (http://sigtap.datasus.gov.br)

**Nota sobre SISPreNatal:** o SISPreNatal (prontuário individual de pré-natal) não está disponível via FTP/pysus. O SIA/PA é o melhor proxy público para mensurar volume e cobertura de consultas pré-natais por município.

**Download no projeto:** `pysus` → FTP DATASUS, grupo PA (Produção Ambulatorial), por estado e mês (arquivos PAUURAAMM.dbc), filtrado pelos procedimentos SIGTAP de pré-natal

### 4.2 Modalidades do BPA

| Modalidade | Identificação do paciente | Uso no projeto |
|------------|---------------------------|----------------|
| **BPA-C** (Consolidado) | Sem ID individual | Maioria das consultas básicas |
| **BPA-I** (Individualizado) | CNS, data nasc., sexo, município | Procedimentos com identificação |
| **APAC** | Individual + dados clínicos | Alta complexidade (autorização prévia) |

### 4.3 Schema PostgreSQL — `datasus.sia_prenatal`

| Coluna | Tipo PostgreSQL | Campo original SIA | Descrição | Domínio / Exemplo |
|--------|-----------------|-------------------|-----------|-------------------|
| `id` | BIGSERIAL PK | — | Identificador gerado | — |
| `estado` | CHAR(2) NOT NULL | — | UF (derivada do arquivo) | SP, MT, PA |
| `ano` | SMALLINT NOT NULL | — | Ano da competência | 2014–2026 |
| `mes` | SMALLINT NOT NULL | — | Mês da competência | 1–12 |
| `pa_cmp` | VARCHAR(6) | `PA_CMP` | Competência (AAAAMM) | 202401 |
| `pa_coduni` | VARCHAR(7) | `PA_CODUNI` | Código CNES da unidade executante | 2030408 |
| `pa_munpcn` | VARCHAR(6) | `PA_MUNPCN` | Código IBGE do município do paciente | 350950 |
| `pa_proc_id` | VARCHAR(10) | `PA_PROC_ID` | Código do procedimento SIGTAP | 0301010072 |
| `pa_sexo` | VARCHAR(1) | `PA_SEXO` | Sexo do paciente | M=Masculino, F=Feminino, I=Ignorado |
| `pa_idade` | SMALLINT | `PA_IDADE` | Idade do paciente (anos) | 28 |
| `pa_racacor` | VARCHAR(2) | `PA_RACACOR` | Raça/Cor | 01=Branca, 02=Preta, 03=Parda, 04=Amarela, 05=Indígena |
| `pa_qtdpro` | INTEGER | `PA_QTDPRO` | Quantidade produzida (apresentada) | 45 |
| `pa_qtdapr` | INTEGER | `PA_QTDAPR` | Quantidade aprovada (paga pelo SUS) | 45 |
| `dado_raw` | JSONB | (todas) | Registro completo SIA/PA | — |
| `inserted_at` | TIMESTAMPTZ | — | Timestamp da carga | — |

**Índices:** `(estado, ano, mes)`, `(pa_munpcn)`, `(pa_proc_id)`

### 4.4 Procedimentos pré-natais filtrados (SIGTAP)

| Código SIGTAP | Descrição | Grupo SIGTAP |
|---------------|-----------|--------------|
| 0301010072 | Consulta pré-natal (baixo risco) | 03=Clínica, 01=Atenção básica |
| 0301010036 | Consulta pré-natal alto risco (1ª) | 03=Clínica, 01=Especializada |
| 0209010061 | Ultrassom obstétrico 1º trimestre | 02=Diagnose |
| 0209010070 | Ultrassom obstétrico 2º/3º trimestre | 02=Diagnose |
| 0202050025 | VDRL (sífilis) | 02=Diagnose |
| 0214010015 | Anti-HIV | 02=Diagnose |
| 0202010597 | Glicemia em jejum na gestação | 02=Diagnose |
| 0202010473 | Hemoglobina/Hematócrito | 02=Diagnose |
| 0202010201 | Toxoplasmose IgG/IgM | 02=Diagnose |
| 0202050017 | EAS/Urocultura | 02=Diagnose |
| 0301060029 | Consulta de puerpério | 03=Clínica |
| 0211010050 | Tipagem ABO-Rh | 02=Diagnose |
| 0202030300 | Teste de Coombs | 02=Diagnose |

### 4.5 Estrutura do código SIGTAP

Formato: **GG.SS.FF.PPPP-D** (10 dígitos sem pontuação):
- **GG** = Grupo (03=Clínica, 02=Diagnose, 06=Obstetrícia)
- **SS** = Subgrupo
- **FF** = Forma de organização
- **PPPP** = Sequencial do procedimento
- **D** = Dígito verificador

### 4.6 Campos relevantes em `dado_raw`

| Campo SIA | Descrição | Domínio |
|-----------|-----------|---------|
| `PA_TPFIN` | Tipo de financiamento | 1=Atenção básica, 2=Alta complexidade, 3=MAC programado, 4=FAEC, 5=ISS |
| `PA_NIVCPL` | Nível de complexidade | 1=Atenção básica, 2=Média complexidade, 3=Alta complexidade |
| `PA_CIDPRI` | CID-10 diagnóstico principal | Z34=Supervisão gravidez normal, Z35=Supervisão gravidez de alto risco |
| `PA_CNSMED` | CNS do profissional (BPA-I) | 15 dígitos |
| `PA_CBOCOD` | CBO do profissional | 6 dígitos (ex: 225125=Médico ginecologista) |
| `PA_DTATEN` | Data do atendimento (BPA-I) | AAAAMMDD |
| `PA_VALAPR` | Valor aprovado (R$) | float |
| `PA_GESTAO` | Município gestor | código IBGE 6 dígitos |

### 4.7 Cobertura e limitações

- **Cobertura geográfica:** Nacional — apenas procedimentos SUS
- **Temporal:** BPA-C desde julho 1994; BPA-I individual a partir de 2008
- **Apenas SUS:** exclui setor privado e planos de saúde
- **BPA-C sem identificação individual:** maioria das consultas básicas
- **Município de pactuação ≠ município de residência:** `PA_MUNPCN` pode ser o município da unidade, não do paciente
- **Incentivo financeiro:** pode gerar upcoding (procedimentos de maior complexidade registrados)
- **Filtro do projeto:** apenas `PA_SEXO = 'F'`; `PA_QTDAPR > 0`

### 4.8 Links oficiais

- DATASUS SIA: https://datasus.saude.gov.br/acesso-a-informacao/producao-ambulatorial-sia-sus/
- Wiki SIA: https://wiki.saude.gov.br/sia/index.php/Página_principal
- SIGTAP: http://sigtap.datasus.gov.br/
- Notas Técnicas TABNET: http://tabnet.datasus.gov.br/cgi/sia/padescr.htm
- FTP DATASUS: ftp://ftp.datasus.gov.br/dissemin/publicos/SIASUS/
- Metadados IBGE: https://ces.ibge.gov.br/base-de-dados/metadados/ministerio-da-saude/sistema-de-informacoes-ambulatoriais-do-sus-sia-sus.html

---

## 5. SISVAN — Sistema de Vigilância Alimentar e Nutricional

### 5.1 Descrição oficial

O SISVAN é o sistema nacional de vigilância alimentar e nutricional, estabelecido no Brasil nos anos 1970 e totalmente eletrônico desde 2008. Gerenciado pela CGAN (Coordenação-Geral de Alimentação e Nutrição) sob a SAPS/MS (Secretaria de Atenção Primária à Saúde). Consolida dados sobre estado nutricional e marcadores de consumo alimentar registrados na Atenção Primária à Saúde (APS).

**Fontes de dados:**
1. **e-SUS APS:** dados antropométricos e de consumo alimentar inseridos nas UBS, domicílios e equipamentos sociais
2. **SIGPBF/PBF:** dados antropométricos de beneficiários do Bolsa Família/Auxílio Brasil

**Download no projeto:** CSV anual (OpenDataSUS / Portal de Dados Abertos do SUS) — arquivos `sisvan_estado_nutricional_AAAA.csv`
**Filtro gestante:** `DS_IMC_PRE_GESTACIONAL` preenchido e diferente de "0" (~3,5% das linhas de cada arquivo)
**Encoding:** latin-1; decimal brasileiro (vírgula → ponto antes de converter)

### 5.2 Schema PostgreSQL — `datasus.sisvan_gestante`

| Coluna | Tipo PostgreSQL | Campo original SISVAN | Descrição | Domínio / Exemplo |
|--------|-----------------|----------------------|-----------|-------------------|
| `id` | BIGSERIAL PK | — | Identificador gerado | — |
| `ano` | SMALLINT NOT NULL | — | Ano do atendimento (derivado do arquivo) | 2010–2023 |
| `nu_cns` | VARCHAR(15) | `nu_cns` / `NU_CNS` | Cartão Nacional de Saúde (anonimizado; ausente no formato CSV) | — |
| `co_municipio_ibge` | VARCHAR(7) | `CO_MUNICIPIO_IBGE` | Código IBGE do município | 3550308 (SP capital) |
| `nu_competencia_aaaamm` | VARCHAR(6) | `NU_COMPETENCIA` | Competência mês/ano (AAAAMM) | 202203 |
| `nu_semana_gestacional` | SMALLINT | `NU_SEMANAS_GESTACAO` | Semana gestacional no atendimento (ausente no formato CSV) | 1–42 |
| `nu_peso` | DECIMAL(6,2) | `NU_PESO` | Peso em kg | 68.50 |
| `nu_altura` | DECIMAL(5,2) | `NU_ALTURA` | Altura em metros | 1.62 |
| `nu_imc` | DECIMAL(6,2) | `DS_IMC` | IMC calculado (kg/m²) | 26.10 |
| `ds_st_nutricional` | VARCHAR(50) | `CO_ESTADO_NUTRI_ADULTO` / `CO_ESTADO_NUTRI_IMC_SEMGEST` | Estado nutricional codificado (ver tabela 5.4) | 2 (Adequado) |
| `nu_imc_pre_gestacional` | DECIMAL(6,2) | `DS_IMC_PRE_GESTACIONAL` | IMC pré-gestacional declarado | 24.50 |
| `ds_acompanhamento` | VARCHAR(50) | `DT_ACOMPANHAMENTO` | Data do acompanhamento (reaproveitado no CSV) | 20220315 |
| `co_raca_cor` | SMALLINT | `CO_RACA_COR` | Raça/Cor | 1=Branca, 2=Preta, 3=Amarela, 4=Parda, 5=Indígena |
| `nu_escolaridade` | SMALLINT | `CO_ESCOLARIDADE` | Escolaridade | 1=Nenhuma, 2=Fundamental incompleto, 3=Fundamental completo, 4=Médio, 5=Superior |
| `dado_raw` | JSONB | (todas) | Registro completo original | — |
| `inserted_at` | TIMESTAMPTZ | — | Timestamp da carga | — |

**Índices:** `(ano)`, `(co_municipio_ibge)`, `(nu_semana_gestacional)`

### 5.3 Fases de vida (CO_FASE_VIDA) — contexto

| Código | Descrição |
|--------|-----------|
| 1 | Criança (0–10 anos) |
| 2 | Adolescente (10–19 anos) |
| 3 | Adulto (20–59 anos) |
| 4 | Idoso (60+ anos) |
| **5** | **Gestante** ← filtro aplicado no projeto |

### 5.4 Classificação do estado nutricional da gestante

#### Por IMC/Semana Gestacional — Curva de Atalah / CONMAI 2023 (CO_ESTADO_NUTRI_IMC_SEMGEST)

| Código | Categoria | IMC relativo à curva |
|--------|-----------|----------------------|
| 1 | Baixo peso | Abaixo do limite inferior para a semana gestacional |
| 2 | Adequado | Dentro da faixa normal para a semana gestacional |
| 3 | Sobrepeso | Acima do limite superior normal |
| 4 | Obesidade | Acima do limiar de obesidade para a semana gestacional |

#### IMC Pré-gestacional — Pontos de corte OMS adulto (DS_IMC_PRE_GESTACIONAL)

| Categoria | IMC (kg/m²) |
|-----------|-------------|
| Baixo peso | < 18,5 |
| Adequado/Eutrófico | 18,5 – 24,9 |
| Sobrepeso | 25,0 – 29,9 |
| Obesidade | ≥ 30,0 |

#### IMC Adulto geral (CO_ESTADO_NUTRI_ADULTO) — para registros não-gestante na mesma tabela

| Código | Categoria | IMC (kg/m²) |
|--------|-----------|-------------|
| 1 | Magreza grau III | < 16,0 |
| 2 | Magreza grau II | 16,0 – 16,9 |
| 3 | Magreza grau I | 17,0 – 18,4 |
| 4 | Eutrofia | 18,5 – 24,9 |
| 5 | Sobrepeso | 25,0 – 29,9 |
| 6 | Obesidade grau I | 30,0 – 34,9 |
| 7 | Obesidade grau II | 35,0 – 39,9 |
| 8 | Obesidade grau III | ≥ 40,0 |

### 5.5 Diferenças entre formatos de arquivo

| Característica | Formato parquet (pysus) | Formato CSV (OpenDataSUS) |
|----------------|-------------------------|---------------------------|
| Fonte | FTP DATASUS via pysus | Portal de Dados Abertos (CKAN) |
| Encoding | UTF-8 (parquet) | latin-1 |
| Decimal | ponto | vírgula (normalizado pelo pipeline) |
| Semana gestacional | `nu_semana_gestacional` presente | **ausente** → `NULL` no banco |
| CNS | `nu_cns` presente | **ausente** → `NULL` no banco |
| Cobertura | 2019–2024 | 2010–2023 |
| Tamanho por ano | ~100–500 MB | 4–16 GB (população total, não só gestantes) |
| Filtro gestante | `DS_FASE_VIDA = 'GESTANTE'` | `DS_IMC_PRE_GESTACIONAL != "" and != "0"` |

> **Implicação para análise:** registros carregados de CSV (2010–2020) não possuem `nu_semana_gestacional` — para análise por semana gestacional, utilizar apenas registros do formato parquet (2019 em diante).

### 5.6 Uso no modelo K-Means do Maternar

- `nu_peso` / `nu_altura` → Entrada para cálculo de IMC gestacional
- `nu_imc` / `nu_imc_pre_gestacional` → Feature `IMC_GESTACIONAL` do modelo
- `ds_st_nutricional` → Label de estado nutricional para validação dos clusters
- `nu_semana_gestacional` → Estratificação temporal do risco nutricional ao longo da gestação
- `co_municipio_ibge` → Linkage geográfico com outras bases

**Curva de Atalah:** o app Maternar usa a classificação SISVAN/CONMAI 2023 para orientar ganho de peso adequado semana a semana, com alertas personalizados por trimestre gestacional.

### 5.7 Cobertura e limitações

- **Cobertura geográfica:** Nacional; desagregação municipal
- **Temporal:** 2008–2023; projeto carregou 2010–2023 (1.201.675 gestantes)
- **Viés de seleção:** reflete mulheres que frequentam UBS — não representa a população geral
- **IMC pré-gestacional:** baseado em peso autorreferido ou aferição precoce (≤13 semanas); pode ter erro de mensuração
- **Duplicação:** possível quando a mesma gestante registrada em e-SUS e no PBF
- **Setor privado ausente:** gestantes com plano de saúde ou consultas privadas não estão representadas
- **CSV 2010–2018:** semana gestacional ausente → `NULL` em `nu_semana_gestacional`

### 5.8 Links oficiais

- Portal de Dados Abertos SISVAN: https://dadosabertos.saude.gov.br/dataset/sisvan-estado-nutricional
- Dicionário de Dados PDF: https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SISVAN/estado_nutricional/Dicion%C3%A1rio+de+Dados+-+Estado+Nutricional.pdf
- DATASUS Notas Técnicas: http://tabnet.datasus.gov.br/cgi/SISVAN/CNV/notas_sisvan.html
- Ministério da Saúde SISVAN: https://www.gov.br/saude/pt-br/composicao/saps/vigilancia-alimentar-e-nutricional/sisvan
- Guia coleta antropométrica: https://bvsms.saude.gov.br/bvs/publicacoes/orientacoes_coleta_analise_dados_antropometricos.pdf

---

## 6. Integração entre datasets — chaves de linkage

| Chave | SINAN | SIM | CNES | SIA | SISVAN |
|-------|-------|-----|------|-----|--------|
| Município (IBGE 6 dig.) | `id_municip` | `codmunres` | `codmunicipio` | `pa_munpcn` | `co_municipio_ibge` |
| Ano/Mês | `ano` | `ano` | `ano + mes` | `ano + mes` | `nu_competencia_aaaamm` |
| Estabelecimento (CNES) | `dado_raw.ID_UNIDADE` | `dado_raw.CODESTAB` | `cnes` | `pa_coduni` | — |
| Gestação | `cs_gestant` | `obitograv / obitopuerp` | — | `pa_proc_id` (Z34.x) | filtro aplicado |

> **Privacidade:** SINAN, SIM e SISVAN são anonimizados nos dados abertos. SIA BPA-I contém CNS mas é de acesso restrito. Não é possível linkage individual entre sistemas nos dados abertos.

---

## 7. Queries analíticas de referência

```sql
-- Agravos gestantes por ano e tipo
SELECT agravo, ano, COUNT(*) AS notificacoes
FROM datasus.sinan_agravos_gestantes
GROUP BY agravo, ano ORDER BY agravo, ano;

-- Mortalidade materna por causa principal e estado
SELECT estado, ano, causabas, COUNT(*) AS obitos
FROM datasus.sim_mortalidade_materna
WHERE causabas LIKE 'O%'
GROUP BY estado, ano, causabas ORDER BY obitos DESC LIMIT 20;

-- Maternidades com leito obstétrico por município
SELECT codmunicipio, COUNT(*) AS n_estabelecimentos,
       SUM(qt_leito_obs) AS leitos_obs_total
FROM datasus.cnes_estabelecimentos
WHERE tp_unidade IN ('05','07','15','61') AND qt_leito_obs > 0
GROUP BY codmunicipio ORDER BY leitos_obs_total DESC;

-- Cobertura pré-natal por município (consultas aprovadas)
SELECT pa_munpcn, ano, SUM(pa_qtdapr) AS consultas_aprovadas
FROM datasus.sia_prenatal
WHERE pa_proc_id = '0301010072'
GROUP BY pa_munpcn, ano ORDER BY consultas_aprovadas DESC LIMIT 20;

-- Estado nutricional gestante por faixa de semana
SELECT
  CASE
    WHEN nu_semana_gestacional <= 13 THEN '1º Trimestre'
    WHEN nu_semana_gestacional <= 27 THEN '2º Trimestre'
    WHEN nu_semana_gestacional <= 42 THEN '3º Trimestre'
    ELSE 'Semana ignorada'
  END AS trimestre,
  ds_st_nutricional AS estado_nutricional,
  COUNT(*) AS n,
  ROUND(AVG(nu_imc)::numeric, 2) AS imc_medio,
  ROUND(AVG(nu_peso)::numeric, 1) AS peso_medio_kg
FROM datasus.sisvan_gestante
WHERE nu_semana_gestacional BETWEEN 1 AND 42
GROUP BY 1, 2 ORDER BY 1, 3 DESC;

-- Tendência de sífilis gestacional por raça/cor (2014–2024)
SELECT ano, cs_raca,
  CASE cs_raca
    WHEN 1 THEN 'Branca' WHEN 2 THEN 'Preta'
    WHEN 4 THEN 'Parda'  WHEN 5 THEN 'Indígena' ELSE 'Outras/Ignorado'
  END AS raca,
  COUNT(*) AS casos
FROM datasus.sinan_agravos_gestantes
WHERE agravo = 'SIFG'
GROUP BY ano, cs_raca ORDER BY ano, cs_raca;
```

---

## 8. Arquitetura do pipeline

```
FTP DATASUS / Portal de Dados Abertos SUS
        ↓
  ApiDatasus/main.py
  (pysus + pandas + pyarrow)
        ↓
  dados_datasus/
  ├── SINAN/  SINAN_{AGRAVO}_{ANO}.parquet  (raw pysus → consolidado)
  ├── SIM/    SIM_MATERNO_{UF}_{ANO}.parquet
  ├── CNES/   CNES_{GRUPO}_{UF}_{ANO}_{MES}.parquet
  ├── SIA_PRENATAL/  SIA_PRENATAL_{UF}_{ANO}_{MES}.parquet
  └── SISVAN/ sisvan_estado_nutricional_{ANO}.csv
        ↓
  ApiDatasus/db_loader.py
  (psycopg2 + execute_values em batches de 5.000)
  → cada arquivo é EXCLUÍDO do disco após carga bem-sucedida
  → pipeline_manifest.json registra downloaded/loaded
        ↓
  PostgreSQL — banco: maternar | schema: datasus
  ├── sinan_agravos_gestantes   (1.322.606 registros)
  ├── sim_mortalidade_materna   (15.711.535 registros)
  ├── cnes_estabelecimentos     (8.528.568 registros)
  ├── sia_prenatal              (20.477.352 registros)
  └── sisvan_gestante           (1.201.675 registros)
                                ─────────────────────
                    TOTAL:      47.241.736 registros
```
