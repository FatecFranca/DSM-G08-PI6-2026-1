# 03 - Arquitetura de Dados e IA: Maternar

> **Última atualização:** 2026-05-25
> **Status:** Modelo treinado e validado — K-Means K=3 com 378.969 gestantes (DATASUS 2014–2016).

---

## 1. Visão Geral do Modelo

O motor de classificação utiliza o algoritmo **K-Means K=3** (Clustering Não Supervisionado)
para segmentar perfis de gestantes em 3 grupos de risco. O treinamento foi realizado em Python 3.12
com dados históricos do DATASUS e a inferência ocorre em tempo real via **API Flask**.

### Decisão: K=3 (não K=4)

Após análise comparativa com 4 algoritmos (K-Means, Agglomerative Ward, GMM, Mini-Batch K-Means)
e os critérios Silhouette, Calinski-Harabász, Davies-Bouldin, Gap Statistic e estabilidade:

- K=3 supera K=4 em **3/3 métricas internas**
- Silhouette K=3: **0.2873** vs K=4: 0.2139
- Maior interpretabilidade clínica (3 alertas em vez de 4)

---

## 2. Fontes de Dados

| Base | Variáveis utilizadas | Linkage |
|------|---------------------|---------|
| **SISVAN** | nu_peso, nu_altura, nu_imc, nu_imc_pre_gestacional, raca_cor, escolaridade, estado_nutricional | Individual |
| **SINAN** | taxa_sifilis_gest (→ log1p), taxa_toxo_gest | Município/ano |
| **SIM** | taxa_mortalidade_materna (CID O%) | Município/ano |
| **SIA** | consultas pré-natal → cobertura_prenatal_log | Município/ano |
| **CNES** | contagem de hospitais por município | Município/ano |

> **Nota:** SIH/SUS e SNIS foram descartados após análise de dados — ausência de linkage individual
> confiável com o SISVAN. A infraestrutura hospitalar é capturada via CNES.

---

## 3. Pipeline de Dados (Executado)

```
SISVAN (individual) ──┐
SINAN (município/ano) ─┤
SIM   (município/ano) ─┼─→ PostgreSQL (schema: datasus)
SIA   (município/ano) ─┤         ↓
CNES  (município/ano) ─┘   preprocess_k3.py
                                  ↓
                         RobustScaler + PCA (90% → 8 comp.)
                                  ↓
                         KMeans(K=3, n_init=20) → kmeans_k3.pkl
                                  ↓
                         PostgreSQL (schema: ml_maternar)
                         cluster_km3 (0/1/2) por gestante
```

### Etapas detalhadas

1. **Extração:** Leitura direta do PostgreSQL (schema `datasus`) — dados importados via pipeline DATASUS
2. **Limpeza:** Remoção de inconsistências biológicas + capping IQR
3. **Feature engineering:** Cálculo de ganho_imc, log1p(taxa_sifilis), cobertura pré-natal, flags
4. **Linkage:** Join individual (SISVAN) × municipal (SINAN + SIM + SIA + CNES)
5. **Normalização:** RobustScaler nas 9 features contínuas
6. **Redução:** PCA 90% variância → 8 componentes
7. **Clustering:** K-Means K=3 (k-means++, n_init=20, random_state=42)
8. **Exportação:** PKL do modelo + scaler + parquets + atualização PostgreSQL

---

## 4. Features de Inferência (Input do App → API Flask)

| Feature | Como coletar no App | Fonte treino |
|---------|---------------------|-------------|
| `nu_peso` | Peso informado pela gestante (kg) | SISVAN |
| `nu_altura` | Altura informada (m) | SISVAN |
| `nu_imc_pre_gestacional` | IMC pré-gestacional informado ou calculado | SISVAN |
| `raca_cor` | Auto-declaração (1-5) | SISVAN |
| `escolaridade` | Escolaridade (1-5) | SISVAN |
| `log_taxa_sifilis_gest` | Consultado via `cod_municipio` no banco | SINAN/município |
| `cnes_hospitais` | Consultado via `cod_municipio` | CNES/município |
| `cobertura_prenatal_log` | Consultado via `cod_municipio` | SIA/município |

**Features calculadas automaticamente:**
- `nu_imc = nu_peso / nu_altura²`
- `ganho_imc = nu_imc - nu_imc_pre_gestacional`
- `est_nut_*` e `raca_*`: one-hot encoding automático

---

## 5. Arquitetura da Solução (3 Camadas)

```
┌─────────────────────────────────────────────────────────────┐
│  App Flutter                                                │
│  • Coleta: peso, altura, IMC pré, raça, escolaridade, CEP  │
│  • Exibe: cluster, recomendações, histórico                 │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS / JSON
┌──────────────────────▼──────────────────────────────────────┐
│  Backend Nest.js                                            │
│  • Autenticação JWT | Persistência PostgreSQL               │
│  • Histórico de classificações | Notificações Push          │
│  • Proxy para API Flask                                     │
└──────────────────────┬──────────────────────────────────────┘
                       │ Internal HTTP
┌──────────────────────▼──────────────────────────────────────┐
│  API Flask (Python 3.12)                                    │
│  • Carrega kmeans_k3.pkl + scaler_maternar.pkl              │
│  • Normaliza via RobustScaler                               │
│  • Projeta via PCA (8 componentes)                          │
│  • Prediz cluster → retorna {id, nome, recomendações}       │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Mapeamento de Clusters (Saída da IA)

| ID | Nome Clínico | % Base | IMC Atual | IMC Pré | Hospitais/município |
|----|-------------|--------|-----------|---------|---------------------|
| **0** | Obesidade Gestacional | 27.3% | 34.0 | 31.0 | 2.0 |
| **1** | Eutrofia / Baixo Peso | 71.2% | 24.6 | 22.7 | 2.0 |
| **2** | Acesso Diferenciado | 1.5% | 26.7 | 24.9 | **8.6** |

### Recomendações por cluster

**Cluster 0 — Obesidade Gestacional (alto risco nutricional)**
- Alerta: Risco elevado de diabetes gestacional e hipertensão
- Ação: Encaminhar para nutricionista especializado em gestação
- Ação: Monitoramento intensivo de ganho de peso (consultas mensais)
- Ação: Rastreamento de pré-eclâmpsia

**Cluster 1 — Eutrofia / Baixo Peso (risco moderado/baixo)**
- Alerta: Monitorar ganho de peso (pode ser insuficiente em baixo peso)
- Ação: Orientação nutricional básica
- Ação: Garantir mínimo de 6 consultas pré-natal
- Informação: Perfil de menor risco na base

**Cluster 2 — Acesso Diferenciado (gestante de referência)**
- Contexto: Gestante em município com alta infraestrutura hospitalar
- Alerta: Taxa de sífilis gestacional mais elevada no município
- Ação: Verificar exames de VDRL/anti-HIV
- Ação: Pode necessitar de acompanhamento especializado (encaminhamento)

---

## 7. Endpoint de Inferência (Flask)

```python
# POST /api/ia/classificar
# Body:
{
  "nu_peso": 72.0,
  "nu_altura": 1.62,
  "nu_imc_pre_gestacional": 24.1,
  "raca_cor": 4,        # 1=Branca, 2=Preta, 3=Amarela, 4=Parda, 5=Indígena
  "escolaridade": 3,    # 1-5 (1=sem escolaridade, 5=superior)
  "cod_municipio": "350950"  # IBGE 7 dígitos
}

# Response:
{
  "cluster_id": 1,
  "cluster_nome": "Eutrofia / Baixo Peso",
  "nivel_risco": "moderado",
  "recomendacoes": [...],
  "metricas": {
    "nu_imc_calculado": 27.4,
    "ganho_imc": 3.3,
    "percentil_imc": 0.62
  }
}
```

---

## 8. Modelos e Artefatos

| Arquivo | Descrição |
|---------|-----------|
| `kmeans_k3.pkl` | Modelo K-Means (K=3, k-means++, n_init=20) — scikit-learn |
| `scaler_maternar.pkl` | RobustScaler ajustado nos dados de treino |
| `pca_maternar.pkl` | PCA (8 componentes, 90% variância) |
| `centroides_kmeans_k3.csv` | Centroides em escala original (referência clínica) |

---

## 9. Métricas de Qualidade do Modelo

| Métrica | Valor | Interpretação |
|---------|-------|--------------|
| Silhouette Score | 0.2873 | Razoável (>0.2) — esperado em dados epidemiológicos |
| Calinski-Harabász | 102.169 | Clusters bem definidos |
| Davies-Bouldin | 1.188 | Baixa sobreposição entre clusters |
| ARI hold-out (10%) | 0.999 | Estabilidade excelente — atribuição praticamente idêntica ao modelo completo |
| IC 95% Silhouette | [0.285, 0.290] | Baixa variância — solução robusta |
| Estabilidade (20 seeds) | σ < 0.0001 | Determinístico na prática |
