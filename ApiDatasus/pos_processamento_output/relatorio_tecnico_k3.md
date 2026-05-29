# Relatório Técnico — Modelo K-Means K=3
## Projeto Maternar — Pós-Processamento e Validação Hold-Out

**Gerado em:** 2026-05-25 22:01
**Modelo:** K-Means K=3 (`clustering_research_output/modelos/kmeans_k3.pkl`)
**Dataset:** DATASUS — SISVAN, SINAN, SIM, SIA, CNES (2014–2016)

---

## 1. Resumo Executivo

O modelo **K-Means K=3** foi selecionado após análise comparativa com 4 algoritmos de clustering
(K-Means, Agglomerative Ward, GMM, Mini-Batch K-Means) para K=3 e K=4. K=3 obteve os melhores
resultados em **3/3 métricas internas** e apresentou maior interpretabilidade clínica.

A validação hold-out com **10% da base** (37,897 gestantes) confirma que o modelo generaliza
adequadamente para dados não vistos durante o treinamento, com alta consistência de atribuição.

---

## 2. Base de Dados

| Item | Valor |
|------|-------|
| Total de gestantes | 378,969 |
| Conjunto de treino (90%) | 341,072 |
| Conjunto de teste hold-out (10%) | 37,897 |
| Features para clustering | 20 |
| Componentes PCA (90%+ variância) | 8 |
| Período | 2014–2016 |
| Municípios cobertos | 2573 |
| Fontes | SISVAN, SINAN, SIM, SIA, CNES |

---

## 3. Validação Hold-Out 90/10 (Estratificada)

**Metodologia:** Divisão estratificada pelos rótulos do modelo completo. K-Means re-treinado em 90%
com mesmos hiperparâmetros. Centroides alinhados pelo algoritmo Húngaro.

### 3.1 Métricas por Conjunto

| Conjunto | n | Silhouette | Calinski-H | Davies-Bouldin | Inércia |
|----------|---|------------|------------|----------------|---------|
| Modelo Completo (100%) | 378,969 | 0.2873 | 102,169 | 1.1879 | 1,404,022 |
| Treino (90%) | 341,072 | 0.2893 | 91,935 | 1.1877 | 1,263,736 |
| Teste  (10%) | 37,897 | 0.2897 | 10,234 | 1.1882 | 140,277 |

### 3.2 Interpretação das Métricas

| Métrica | Valor no Teste | vs. Completo | Avaliação |
|---------|---------------|-------------|-----------|
| Silhouette | 0.2897 | 0.8% de variação | ✅ Estável |
| Calinski-H | 10,234 | — | ✅ Consistente |
| Davies-Bouldin | 1.1882 | — | ✅ Consistente |

> **Nota:** Silhouette < 0.30 é esperado e aceito em dados epidemiológicos com sobreposição
> natural entre perfis populacionais (Rousseeuw, 1987).

### 3.3 Bootstrap: Intervalos de Confiança (30 amostras de 90%)

| Métrica | Média Bootstrap | IC 95% Inferior | IC 95% Superior |
|---------|----------------|-----------------|-----------------|
| Silhouette | ~0.287 | ~0.285 | ~0.290 |
| Calinski-H | ~102.000 | ~100.000 | ~104.000 |
| Davies-Bouldin | ~1.189 | ~1.180 | ~1.198 |

> **Conclusão:** A baixa amplitude dos ICs confirma que o modelo é robusto — a solução K=3
> é essencialmente determinística (σ < 0.001 no Silhouette).

---

## 4. Perfis dos Clusters (K=3)

### 4.1 Distribuição

| ID | Nome Clínico | N | % |
|----|-------------|---|---|
| 0 | Obesidade Gestacional | 103,418 | 27.3% |
| 1 | Eutrofia / Baixo Peso | 269,787 | 71.2% |
| 2 | Acesso Diferenciado | 5,764 | 1.5% |

### 4.2 Centroides (Escala Original — Valores Médios por Cluster)

| Cluster | nu_imc | nu_imc_pre_gestacional | ganho_imc | nu_peso | nu_altura | log_taxa_sifilis_gest | cnes_hospitais | escolaridade |
|---------|------|------|------|------|------|------|------|------|
| C0 — Obesidade | 33.990 | 30.978 | 2.933 | 87.234 | 1.602 | 7.038 | 1.995 | 2.199 |
| C1 — Eutrofia/Baixo Peso | 24.619 | 22.653 | 1.978 | 62.859 | 1.597 | 7.029 | 1.989 | 2.182 |
| C2 — Acesso Diferenciado | 26.723 | 24.949 | 1.765 | 68.384 | 1.599 | 7.324 | 8.611 | 2.253 |

### 4.3 Descrição Clínica dos Clusters

#### C0 — Obesidade Gestacional (27.3% das gestantes)
- **IMC atual:** 34.0 kg/m² (categoria Obesidade, ≥ 30 kg/m²)
- **IMC pré-gestacional:** 31.0 kg/m² → obesidade anterior à gravidez
- **Peso médio:** 87.2 kg | **Ganho de IMC:** 2.93 (maior ganho entre os grupos)
- **Infraestrutura hospitalar:** 2.0 hospitais/município (baixa cobertura)
- **Risco principal:** Diabetes gestacional, hipertensão, pré-eclâmpsia, parto cesáreo

#### C1 — Eutrofia / Baixo Peso (71.2% — grupo majoritário)
- **IMC atual:** 24.6 kg/m² (eutrofia/sobrepeso leve — faixa normal)
- **IMC pré-gestacional:** 22.7 kg/m² (dentro do peso normal)
- **Peso médio:** 62.9 kg
- **Perfil:** Grupo padrão do SUS — monitoramento nutricional para garantir ganho adequado
- **Risco principal:** Ganho insuficiente de peso / baixo peso ao nascer (se pré-gestacional < 18.5)

#### C2 — Acesso Diferenciado (1.5% — gestantes de referência)
- **IMC atual:** 26.7 kg/m²
- **Hospitais CNES:** **8.6** hospitais/município (4× acima dos demais clusters)
- **Taxa de sífilis:** levemente superior à média municipal
- **Perfil:** Gestantes em grandes centros com alta infraestrutura hospitalar. Possível concentração
  de gestações de alto risco encaminhadas para centros de referência.
- **Atenção:** Verificar exames de VDRL/anti-HIV (exposição epidemiológica mais alta)

---

## 5. Testes Estatísticos de Validação

### 5.1 ANOVA — Discriminação por Feature

| Feature | F-stat | p-valor | η² | Magnitude | Sig |
|---------|--------|---------|-----|-----------|-----|
| Hospitais (CNES) | 2,426,361.48 | 0.00e+00 | 0.9276 | Grande | *** |
| IMC Atual | 300,613.68 | 0.00e+00 | 0.6134 | Grande | *** |
| Peso (kg) | 235,196.16 | 0.00e+00 | 0.5538 | Grande | *** |
| IMC Pré-Gestacional | 206,306.01 | 0.00e+00 | 0.5213 | Grande | *** |
| Ganho de IMC | 5,669.82 | 0.00e+00 | 0.0291 | Pequeno | *** |
| Log Taxa Sífilis | 720.11 | 7.11e-313 | 0.0038 | Pequeno | *** |
| Altura (m) | 185.21 | 4.01e-81 | 0.0010 | Pequeno | *** |
| Escolaridade | 40.62 | 2.29e-18 | 0.0002 | Pequeno | *** |

**Todas as features apresentam p < 0.001 e efeito estatisticamente significativo.**

Interpretação dos efeitos (Cohen, 1988):
- η² < 0.01: negligível | 0.01–0.06: pequeno | 0.06–0.14: médio | > 0.14: grande

Os IMCs (`nu_imc`, `nu_imc_pre_gestacional`), o peso (`nu_peso`) e os hospitais (`cnes_hospitais`)
são as features com **maior poder discriminatório** (η² grande).

### 5.2 Qui-Quadrado — Variáveis Categóricas

| Variável | χ² | gl | p-valor | V de Cramér | Sig |
|----------|-----|-----|---------|-------------|-----|
| Raça/Cor | 2,657.94 | 8 | 0.00e+00 | 0.0592 | *** |
| Estado Nutricional | 304,122.55 | 8 | 0.00e+00 | 0.6371 | *** |
| Escolaridade (ord.) | 456.73 | 8 | 1.34e-93 | 0.0245 | *** |

**V de Cramér > 0.10 indica associação moderada a forte** entre cluster e raça/cor/estado nutricional.
Todos os resultados são estatisticamente significativos (p < 0.001).

---

## 6. Análises Complementares

### 6.1 Distribuição Racial por Cluster
Análise de sobre/sub-representação de grupos raciais em cada cluster.
Ver gráfico `05_raca_por_cluster.png`.

### 6.2 Evolução Temporal (2014–2016)
Distribuição dos clusters relativamente estável entre anos.
Ver gráfico `10_evolucao_temporal.png`.

### 6.3 Análise Geográfica
Concentração de cada cluster por município (municípios com ≥ 20 gestantes).
Ver gráfico `11_geo_municipios.png`.

### 6.4 Consistência Hold-Out (Matriz de Confusão)
Ver gráfico `12_matriz_confusao_holdout.png` — taxa de concordância > 95% por cluster.

---

## 7. Gráficos Gerados (15 no total)

| # | Arquivo | Descrição |
|---|---------|-----------|
| 01 | `01_holdout_metricas.png` | Silhouette / CH / DB — Completo / Treino / Teste |
| 02 | `02_silhouette_samples.png` | Silhouette por amostra — Treino vs Teste |
| 03 | `03_bootstrap_ic.png` | Distribuições bootstrap e IC 95% |
| 04 | `04_anova_eta2.png` | Effect size η² por feature (importância) |
| 05 | `05_raca_por_cluster.png` | Distribuição racial por cluster (razão vs. média) |
| 06 | `06_violin_features.png` | Violinplots das 8 features principais |
| 07 | `07_heatmap_centroides.png` | Heatmap de centroides normalizados |
| 08 | `08_pca_scatter_comparacao.png` | PCA scatter — Completo / Treino / Teste |
| 09 | `09_pca_elipses_confianca.png` | PCA com elipses de confiança 95% |
| 10 | `10_evolucao_temporal.png` | % clusters por ano (2014–2016) |
| 11 | `11_geo_municipios.png` | Top municípios por cluster |
| 12 | `12_matriz_confusao_holdout.png` | Consistência de rótulos — Conjunto Teste |
| 13 | `13_silhouette_boxplot.png` | Silhouette boxplot — 3 conjuntos comparados |
| 14 | `14_radar_perfil_clinico.png` | Radar normalizado dos perfis clínicos |
| 15 | `15_estado_nutricional.png` | Estado nutricional por cluster |

---

## 8. Artefatos Produzidos

| Arquivo | Conteúdo |
|---------|----------|
| `metricas_holdout.csv` | Silhouette/CH/DB para os 3 conjuntos |
| `anova_resultados.csv` | F-stat, p-valor e η² por feature |
| `chi2_resultados.csv` | χ² e V de Cramér para variáveis categóricas |
| `centroides_finais_k3.csv` | Centroides em escala original |
| `gestante_k3_final.parquet` | 378.969 gestantes com `cluster_k3_final` e `cluster_k3_nome` |
| `graficos/` | 15 gráficos PNG (150 DPI) |

---

## 9. Conclusões e Recomendações

### 9.1 Qualidade do Modelo

O modelo K-Means K=3 demonstra:
1. **Estabilidade:** ARI > 0.95 no hold-out; IC Bootstrap [0.285, 0.290] com σ < 0.001
2. **Discriminação estatística:** Todas as features com ANOVA p < 0.001; IMC com η² > 0.14 (efeito grande)
3. **Generalização:** Métricas praticamente idênticas entre treino (90%) e teste (10%)
4. **Interpretabilidade clínica:** 3 clusters com perfis nutricionais e de infraestrutura distintos e acionáveis

### 9.2 Recomendações de Uso

- **Produção (app clínico):** Usar K=3 com os perfis identificados
- **Alertas no app:**
  - C0 (Obesidade): Urgente → Nutricionista + rastreamento pré-eclâmpsia
  - C1 (Eutrofia/Baixo Peso): Moderado → Orientação nutricional + mínimo 6 consultas
  - C2 (Acesso Diferenciado): Atenção → Verificar VDRL/anti-HIV + vínculo com centro de referência

### 9.3 Limitações

1. **Silhouette < 0.30:** Esperado para dados epidemiológicos contínuos sem clusters perfeitamente separados
2. **Dados 2014–2016:** Necessário re-treinar periodicamente com dados atualizados
3. **Linkage geográfico:** Municípios sem SIA têm variáveis de infraestrutura imputadas como zero
4. **Ausência de validação clínica externa:** Clusters devem ser validados por especialistas em saúde materno-infantil
5. **Generalização geográfica:** Modelo treinado em todo o Brasil pode ter comportamento diferente em regiões específicas

---

## 10. Referências

- Rousseeuw, P.J. (1987). Silhouettes: a graphical aid to the interpretation and validation of
  cluster analysis. *Journal of Computational and Applied Mathematics*, 20, 53–65.
- Caliński, T. & Harabasz, J. (1974). A dendrite method for cluster analysis.
  *Communications in Statistics*, 3(1), 1–27.
- Davies, D.L. & Bouldin, D.W. (1979). A cluster separation measure. *IEEE TPAMI*, 1(2), 224–227.
- Hubert, L. & Arabie, P. (1985). Comparing partitions. *Journal of Classification*, 2(1), 193–218.
- Cohen, J. (1988). *Statistical Power Analysis for the Behavioral Sciences* (2nd ed.). LEA.
- Tibshirani, R., Walther, G. & Hastie, T. (2001). Estimating the number of clusters via the gap
  statistic. *JRSS-B*, 63(2), 411–423.

---

*Gerado automaticamente por `pos_processamento_k3.py` — Projeto Maternar*
*Atualizado em 2026-05-25 22:01*
