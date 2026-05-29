# Relatório de Pré-Processamento — Maternar
    **Gerado em:** 2026-05-24 15:45:57
    **Responsável:** Pipeline de ML — Projeto Maternar

    ---

    ## 1. Objetivo

    Pré-processar os dados dos 5 sistemas DATASUS do Projeto Maternar para alimentar
    o modelo K-Means de clusterização de perfis de risco gestacional. O foco é nas
    **mulheres grávidas e todos os fatores associados à gestação** que possam impactar
    o resultado clínico e o acompanhamento pré-natal.

    ---

    ## 2. Fontes de dados utilizadas

    | Sistema | Tabela PostgreSQL | Papel no modelo |
    |---------|-------------------|-----------------|
    | SISVAN | `datasus.sisvan_gestante` | Dados individuais — espinha do dataset |
    | SINAN  | `datasus.sinan_agravos_gestantes` | Taxas de agravos por município/ano |
    | SIM    | `datasus.sim_mortalidade_materna` | Taxa de mortalidade materna por município/ano |
    | SIA    | `datasus.sia_prenatal` | Cobertura pré-natal e exames por município/ano |
    | CNES   | `datasus.cnes_estabelecimentos` | Infraestrutura obstétrica por município/ano |

    ---

    ## 3. Estratégia de pré-processamento

    ### 3.1 Arquitetura do dataset

    ```
    SISVAN (individual) ← JOIN por (municipio_ibge 6-dígitos, ano) ← SINAN + SIM + SIA + CNES
    ```

    - **SISVAN** fornece os registros individuais (~1.2M gestantes)
    - **SINAN/SIM/SIA/CNES** são agregados a nível municipal via SQL (tabela `municipio_risco`)
    - O join enriquece cada gestante com o contexto de risco do seu município

    ### 3.2 Por que SQL para as agregações?

    SIA (32 GB) e SIM (30 GB) são grandes demais para carga completa em memória.
    Toda a sumarização foi feita diretamente no PostgreSQL, trazendo apenas os
    resultados agregados para Python.

    ---

    ## 4. Registros processados

    | Indicador | Valor |
    |-----------|-------|
    | Gestantes individuais (SISVAN) | 378,969 |
    | Municípios cobertos | 3,479 |
    | Anos cobertos | 2014–2016 (3 anos) |
    | Features finais (para cluster) | 20 |
    | Municípios na tabela de risco | 3,479 |

    ---

    ## 5. Distribuição por ano

    | Ano | Gestantes |
    |-----|-----------|
    | 2014 | 146,612 |
| 2015 | 128,491 |
| 2016 | 103,866 |

    ---

    ## 6. Estado Nutricional das Gestantes

    | Categoria | Quantidade | % |
    |-----------|------------|---|
    | Baixo Peso | 4,340 | 1.5% |
| Adequado | 95,085 | 31.8% |
| Sobrepeso | 108,583 | 36.3% |
| Obesidade I | 61,603 | 20.6% |
| Obesidade II | 21,707 | 7.3% |
| Obesidade III | 7,898 | 2.6% |

    ---

    ## 7. Valores ausentes (antes da imputação)

    | Feature | % ausente |
    |---------|-----------|
    | `taxa_toxo_gest` | 96.01% |
| `taxa_mortalidade_materna` | 96.01% |
| `taxa_sifilis_cong` | 96.01% |
| `taxa_sifilis_gest` | 96.01% |
| `sinan_toxo_gest` | 95.55% |
| `sinan_sifilis_gest` | 95.55% |
| `sinan_dengue` | 95.55% |
| `sinan_zika` | 95.55% |
| `flag_vdrl` | 95.55% |
| `log_taxa_sifilis_gest` | 95.55% |
| `sia_consultas_prenatal` | 95.55% |
| `sim_obitos_maternos` | 95.55% |
| `flag_anti_hiv` | 95.55% |
| `flag_ultrassom` | 95.55% |
| `tem_dado_sia` | 95.55% |
| `cnes_hospitais` | 95.55% |
| `escolaridade` | 48.76% |
| `estado_nutricional_raw` | 21.04% |
| `estado_nutricional_cod` | 21.04% |
| `raca_cor` | 12.85% |

    **Estratégia de imputação:**
    - Variáveis contínuas individuais (IMC, peso, altura): **mediana**
    - Variáveis ordinais (escolaridade, raça): **moda**
    - Taxas contextuais municipais: **mediana** (municípios sem dado recebem valor mediano)
    - Flags de cobertura (VDRL, HIV, ultrassom): **0** (ausência = sem cobertura)

    ---

    ## 8. Tratamento de Outliers — IQR Capping (fator 2.0)

    Valores extremos nas variáveis contínuas foram "cappados" pelo método IQR×2.0
    (Winsorization). Isso preserva todos os registros e neutraliza os extremos sem
    distorcer o cálculo de distância do K-Means.

    ---

    ## 9. Codificação de variáveis

    | Tipo | Variáveis | Tratamento |
    |------|-----------|------------|
    | Contínuas | IMC, peso, altura, taxas de risco | RobustScaler (mediana=0, IQR=1) |
    | Ordinal | Escolaridade | Inteiro preservando hierarquia |
    | Nominal — Estado nutricional | Baixo peso / Adequado / Sobrepeso / Obesidade | One-Hot Encoding (sem drop_first) |
    | Nominal — Raça/cor | Branca / Preta / Amarela / Parda / Indígena | One-Hot Encoding |
    | Binárias | flag_vdrl, flag_anti_hiv, flag_ultrassom | 0/1 sem escala |

    **Por que RobustScaler?**
    O K-Means é sensível à escala. O RobustScaler usa mediana e IQR em vez de
    média e desvio-padrão, sendo robusto a distribuições assimétricas e outliers
    residuais — características típicas de dados epidemiológicos brasileiros.

    **Por que OHE sem drop_first?**
    Em clustering não há problema de multicolinearidade. Remover uma categoria
    (como `drop_first=True`) esconderia um perfil inteiro do algoritmo.

    ---

    ## 10. Features finais para o K-Means

    ### Individuais (SISVAN)
    | Feature | Descrição |
    |---------|-----------|
    | `nu_imc` | IMC atual na aferição |
    | `nu_imc_pre_gestacional` | IMC pré-gestacional |
    | `ganho_imc` | Diferença IMC atual − pré-gestacional |
    | `nu_peso` | Peso em kg |
    | `nu_altura` | Altura em metros |
    | `escolaridade` | Escolaridade (1=Nenhuma…5=Superior) |
    | `est_nut_*` | OHE estado nutricional (4 flags) |
    | `raca_*` | OHE raça/cor (5 flags) |

    ### Contextuais municipais (SINAN + SIM + SIA + CNES)
    | Feature | Fonte | Descrição |
    |---------|-------|-----------|
    | `taxa_sifilis_gest` | SINAN | Casos SIFG / 1.000 consultas pré-natais |
    | `taxa_toxo_gest` | SINAN | Casos TOXG / 1.000 consultas |
    | `taxa_mortalidade_materna` | SIM | Óbitos maternos / 1.000 consultas |
    | `cobertura_prenatal_log` | SIA | log(1 + consultas pré-natais aprovadas) |
    | `cnes_leitos_obs` | CNES | Leitos obstétricos registrados |
    | `flag_vdrl` | SIA | 1 se VDRL foi ofertado no município/ano |
    | `flag_anti_hiv` | SIA | 1 se Anti-HIV foi ofertado |
    | `flag_ultrassom` | SIA | 1 se ultrassom obstétrico foi ofertado |

    ---

    ## 11. Tabelas criadas no PostgreSQL

    | Tabela | Descrição | Linhas |
    |--------|-----------|--------|
    | `ml_maternar.municipio_risco` | Indicadores de risco por município/ano | 3,479+ |
    | `ml_maternar.gestante_features` | Dataset individual limpo (escala real) | 378,969 |
    | `ml_maternar.gestante_para_cluster` | Dataset encodado + normalizado (K-Means) | 378,969 |

    ---

    ## 12. Arquivos gerados

    | Arquivo | Descrição |
    |---------|-----------|
    | `preprocess_output/gestante_features.parquet` | Dataset individual — escala real |
    | `preprocess_output/gestante_para_cluster.parquet` | Dataset pronto para K-Means |
    | `preprocess_output/scaler_maternar.pkl` | RobustScaler serializado |
    | `preprocess_output/graficos/01_valores_ausentes.png` | Mapa de nulos |
    | `preprocess_output/graficos/02_distribuicao_imc.png` | Histogramas IMC |
    | `preprocess_output/graficos/03_estado_nutricional.png` | Estado nutricional |
    | `preprocess_output/graficos/04_raca_cor.png` | Raça/cor |
    | `preprocess_output/graficos/05_escolaridade.png` | Escolaridade |
    | `preprocess_output/graficos/06_distribuicao_ano.png` | Volume por ano |
    | `preprocess_output/graficos/07_correlacao.png` | Mapa de correlação |
    | `preprocess_output/graficos/08_boxplots_antes_capping.png` | Outliers pré-capping |
    | `preprocess_output/graficos/09_taxa_sifilis_por_ano.png` | Tendência sífilis |
    | `preprocess_output/graficos/10_cobertura_prenatal_ano.png` | Cobertura pré-natal |
    | `preprocess_output/graficos/11_boxplots_pos_capping.png` | Boxplots pós-capping |
    | `preprocess_output/graficos/12_variancia_features.png` | Variância por feature |
    | `preprocess_output/graficos/13_distribuicao_pos_normalizacao.png` | Distribuição pós-escala |

    ---

    ## 13. Próximo passo — Clustering K-Means

    ```python
    import pandas as pd, joblib
    from sklearn.cluster import KMeans

    df = pd.read_parquet("preprocess_output/gestante_para_cluster.parquet")
    scaler = joblib.load("preprocess_output/scaler_maternar.pkl")

    kmeans = KMeans(n_clusters=4, random_state=42, n_init=20)
    labels = kmeans.fit_predict(df)

    # Interpretar centroides na escala original
    centroides_raw = scaler.inverse_transform(kmeans.cluster_centers_[:, :len(scaler.center_)])
    ```

    ---
    *Gerado automaticamente por `preprocessing_maternar.py` — Projeto Maternar*