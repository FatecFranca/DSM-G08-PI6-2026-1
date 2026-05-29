# 09 - Pipeline de Treinamento e Mineração

## 1. Objetivo

Descrever o processo **executado** de treinamento do modelo K-Means K=3 com microdados do DATASUS
para identificar perfis de risco gestacional no Projeto Maternar.

> **Status:** Pipeline executado com sucesso em 2026-05-25.
> **Base:** 378.969 gestantes (SISVAN + SINAN + SIM + SIA + CNES — 2014–2016).

---

## 2. Ambiente e Ferramentas

| Item | Especificação |
|------|--------------|
| Ambiente | Python 3.12 + Jupyter Notebook (local) |
| Banco de dados | PostgreSQL 15 — Docker — porta 5435 — banco `maternar` |
| Bibliotecas | Pandas, Scikit-learn, Seaborn, Matplotlib, NumPy, Joblib, Psycopg2 |
| Normalização | `RobustScaler` (mediana/IQR, robusto a outliers epidemiológicos) |
| Redução dimensional | `PCA` (90% variância → 8 componentes) |
| Algoritmo | `KMeans` (k-means++, n_init=20, max_iter=500, random_state=42) |

---

## 3. Fontes de Dados e Linkage

A chave de cruzamento é **município/ano** — todas as bases são agregadas por `(co_municipio_ibge, ano)`.

| Base | Variáveis extraídas | Granularidade |
|------|---------------------|---------------|
| **SISVAN** | nu_peso, nu_altura, nu_imc, nu_imc_pre_gestacional, raca_cor, escolaridade, estado_nutricional | Individual |
| **SINAN** | taxa_sifilis_gest, taxa_toxo_gest, taxa_dengue, taxa_zika | Município/ano |
| **SIM** | taxa_mortalidade_materna (CID O%) | Município/ano |
| **SIA** | sia_consultas_prenatal, cobertura_prenatal_log | Município/ano |
| **CNES** | cnes_hospitais (contagem de hospitais) | Município/ano |

---

## 4. Engenharia de Features

### 4.1 Pré-processamento (SISVAN Individual)

1. **Limpeza biológica:** Remove registros com IMC < 10 ou > 80, altura < 1.30 ou > 2.15 m (5.826 removidos)
2. **Ganho de IMC:** `ganho_imc = nu_imc - nu_imc_pre_gestacional`
3. **Tratamento de nulos:** Mediana por grupo nutricional para variáveis contínuas; 0 para variáveis municipais sem cobertura
4. **Capping IQR:** Limites [Q1 − 1.5×IQR, Q3 + 1.5×IQR] aplicados em 7 variáveis

### 4.2 Transformações

| Feature | Transformação | Motivo |
|---------|--------------|--------|
| `taxa_sifilis_gest` | `log1p(taxa)` | 97% de zeros → IQR=0 com RobustScaler |
| `sia_consultas_prenatal` | `log1p(consultas)` | Distribuição fortemente assimétrica |
| Binárias (raça, estado nutricional) | One-hot encoding | Compatibilidade com distância euclidiana |

### 4.3 Features Finais para Clustering (20 features)

| Tipo | Features |
|------|---------|
| **Contínuas escaladas** | nu_imc, nu_imc_pre_gestacional, ganho_imc, nu_peso, nu_altura, log_taxa_sifilis_gest, cnes_hospitais, cobertura_prenatal_log, escolaridade |
| **Binárias estado nutricional** | est_nut_baixo_peso, est_nut_adequado, est_nut_sobrepeso, est_nut_obesidade |
| **Binárias raça/cor** | raca_branca, raca_preta, raca_amarela, raca_parda, raca_indigena |
| **Binárias flags** | flag_anti_hiv, tem_dado_sia |

---

## 5. Normalização e Redução Dimensional

```
RobustScaler (mediana/IQR) → 20 features
    ↓
PCA (n_components=0.90, random_state=42)
    ↓
8 componentes principais (PC1=29% var., PC2=14% var.)
Variância acumulada: 90.0%
```

**Justificativa do RobustScaler:** Dados epidemiológicos possuem outliers extremos mesmo após capping.
O RobustScaler (normalização por mediana/IQR) é mais resistente do que StandardScaler (média/desvio-padrão).

---

## 6. Seleção do Número de Clusters (K)

### Metodologia comparativa (4 modelos × 2 valores de K)

| Modelo | K=3 Silhouette | K=4 Silhouette | Vencedor |
|--------|----------------|----------------|---------|
| K-Means | **0.2873** | 0.2139 | K=3 |
| Agglomerative Ward | **0.2692** | 0.1930 | K=3 |
| GMM (full covariance) | **0.2718** | 0.1995 | K=3 |
| Mini-Batch K-Means | **0.2001** | 0.2142 | K=3/K=4 |

**K=3 selecionado:** Vence em 3/3 métricas internas (Silhouette, Calinski-Harabász, Davies-Bouldin).

### Critérios utilizados

| Critério | Resultado |
|---------|-----------|
| Elbow (Inércia) | Inflexão em K=3 |
| Silhouette máximo | K=3 (0.287) |
| Calinski-Harabász máximo | K=3 (102.169) |
| Davies-Bouldin mínimo | K=3 (1.188) |
| Gap Statistic | Curva crescente (K=3 e K=4 próximos) |
| Estabilidade (20 seeds) | σ < 0.0001 para ambos |

---

## 7. Treinamento do Modelo Final (K=3)

```python
from sklearn.cluster import KMeans

km_final = KMeans(
    n_clusters=3,
    init='k-means++',   # inicialização inteligente
    n_init=20,           # 20 inicializações independentes
    max_iter=500,
    random_state=42,
    algorithm='lloyd'
)
km_final.fit(X_pca)  # X_pca: 378.969 × 8 (PCA 90%)
```

**Métricas do modelo completo:**

| Métrica | Valor |
|---------|-------|
| Silhouette Score | 0.2873 |
| Calinski-Harabász | 102.169 |
| Davies-Bouldin | 1.188 |
| Inércia (WCSS) | 1.404.022 |
| Tempo de treino | ~3.0 segundos |

---

## 8. Perfis dos Clusters (K=3)

| ID | Nome Clínico | N | % | IMC Atual | IMC Pré | Hospitais |
|----|-------------|---|---|-----------|---------|-----------|
| 0 | Obesidade Gestacional | 103.418 | 27.3% | 34.0 | 31.0 | 2.0 |
| 1 | Eutrofia / Baixo Peso | 269.787 | 71.2% | 24.6 | 22.7 | 2.0 |
| 2 | Acesso Diferenciado | 5.764 | 1.5% | 26.7 | 24.9 | **8.6** |

**Interpretação clínica:**

- **C0 — Obesidade Gestacional:** Gestantes com IMC ≥ 30 pré-gestacional e ganho excessivo.
  Maior risco de diabetes gestacional, hipertensão e parto cesareo.

- **C1 — Eutrofia / Baixo Peso:** Grupo majoritário. IMC pré-gestacional na faixa normal/baixo.
  Necessita monitoramento nutricional para garantir ganho adequado.

- **C2 — Acesso Diferenciado:** Gestantes em municípios com alta concentração hospitalar (CNES=8.6×
  acima da média). Possivelmente gestações de alto risco encaminhadas para centros de referência.
  Apresenta taxa de sífilis gestacional levemente superior.

---

## 9. Validação Hold-Out (10%)

| Conjunto | n | Silhouette | Davies-Bouldin | ARI vs. Modelo Completo |
|---------|---|------------|----------------|------------------------|
| Modelo Completo (100%) | 378.969 | 0.2873 | 1.188 | — |
| Treino (90%) | 341.072 | 0.2893 | 1.1877 | 0.999 |
| Teste (10%) | 37.897 | 0.2897 | 1.1882 | 0.999 |

> **IC 95% Bootstrap (30 amostras de 90%):** Silhouette ∈ [0.285, 0.290]
> Variância σ < 0.001 — solução altamente estável.

---

## 10. Artefatos do Pipeline

| Arquivo | Conteúdo | Uso |
|---------|----------|-----|
| `clustering_research_output/modelos/kmeans_k3.pkl` | Modelo K-Means treinado (K=3) | Inferência na API Flask |
| `preprocess_output/scaler_maternar.pkl` | RobustScaler ajustado | Normalização no endpoint |
| `clustering_research_output/tabelas/centroides_kmeans_k3.csv` | Centroides em escala original | Referência clínica |
| `pos_processamento_output/gestante_k3_final.parquet` | 378.969 gestantes com cluster_k3_final | Dataset final |
| `KDD_Maternar_Research.ipynb` | Notebook de pesquisa completo (49 células) | Reprodutibilidade |
| `pos_processamento_output/relatorio_tecnico_k3.md` | Relatório técnico detalhado | Documentação científica |

---

## 11. Esquema de Inferência na API Flask

Para classificar uma nova gestante, a API deve:

1. Receber: `{nu_peso, nu_altura, nu_imc_pre_gestacional, raca_cor, escolaridade, cod_municipio}`
2. Calcular: `nu_imc = nu_peso / nu_altura²`, `ganho_imc = nu_imc - nu_imc_pre_gestacional`
3. Buscar variáveis municipais no PostgreSQL: `log_taxa_sifilis_gest`, `cnes_hospitais`, `cobertura_prenatal_log`
4. Montar o vetor de 20 features (contínuas + binárias)
5. Aplicar `scaler_maternar.pkl` nas features contínuas
6. Aplicar PCA (8 componentes)
7. Chamar `kmeans_k3.pkl.predict(X_pca)` → cluster 0, 1 ou 2
8. Retornar `{cluster_id, cluster_nome, recomendacoes}`

---

## 12. Qualidade e Limitações

- **Silhouette < 0.30:** Esperado em dados epidemiológicos com sobreposição natural entre perfis.
- **Dados 2014–2016:** Necessário re-treinar com dados mais recentes para manter acurácia.
- **Ausência de validação externa:** Os clusters precisam ser validados por especialistas em saúde materno-infantil.
- **Linkage geográfico:** Gestantes sem cobertura de SIA têm variáveis de infraestrutura imputadas como zero.

---

*Atualizado em 2026-05-25 — Dados reais do pipeline executado com 378.969 gestantes.*
