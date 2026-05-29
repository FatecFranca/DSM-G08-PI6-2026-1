"""
Gera KDD_Maternar_Research.ipynb — notebook de pesquisa completo
Cobre K=3 e K=4, 4 modelos, todas as métricas internas.
"""
import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []

def code(src, cell_id=None):
    c = nbf.v4.new_code_cell(src.strip())
    if cell_id:
        c['id'] = cell_id
    return c

def md(src, cell_id=None):
    c = nbf.v4.new_markdown_cell(src.strip())
    if cell_id:
        c['id'] = cell_id
    return c

# ── CAPA ──────────────────────────────────────────────────────────────────────
cells.append(md("""
# KDD Maternar — Pesquisa de Clustering

**Projeto:** Maternar — App de acompanhamento gestacional
**Dataset:** SISVAN + SINAN + SIM + SIA + CNES (2014–2016) — 378.969 gestantes
**Objetivo:** Determinar o número ideal de clusters (K=3 vs K=4) comparando múltiplos algoritmos e métricas de validação interna.

---

## Estrutura do Notebook

| Etapa | Célula | Conteúdo |
|-------|--------|----------|
| 1 | 01 | Importações e configuração |
| 2 | 02 | Carregamento e validação dos dados |
| 3 | 03 | PCA — redução de dimensionalidade (90%) |
| 4 | 04 | Varredura K=2–10: Elbow + Silhouette + Calinski-Harabász + Davies-Bouldin |
| 5 | 05 | Gap Statistic (K=2–8) |
| 6 | 06 | Dendrograma — Hierárquico Ward |
| 7 | 07 | DBSCAN — estrutura de densidade e outliers |
| 8 | 08 | **K-Means K=3** — treino completo + centroides + métricas |
| 9 | 09 | **K-Means K=4** — treino completo + centroides + métricas |
| 10 | 10 | **Agglomerative Ward K=3** — centroides + métricas |
| 11 | 11 | **Agglomerative Ward K=4** — centroides + métricas |
| 12 | 12 | **GMM K=3** — soft clustering + BIC/AIC |
| 13 | 13 | **GMM K=4** — soft clustering + BIC/AIC |
| 14 | 14 | **Mini-Batch K-Means K=3 e K=4** — benchmark de velocidade |
| 15 | 15 | Tabela comparativa geral — todos os modelos × todas as métricas |
| 16 | 16 | Heatmap comparativo de centroides K=3 vs K=4 |
| 17 | 17 | Silhouette por cluster — distribuição (violin plot) |
| 18 | 18 | Scatter PCA — 4 modelos lado a lado (K=4) |
| 19 | 19 | Estabilidade — 20 seeds para K=3 e K=4 |
| 20 | 20 | Cross-tabulation K=3 vs K=4 (migração de gestantes) |
| 21 | 21 | Análise de equidade racial (K escolhido) |
| 22 | 22 | Análise geográfica (K escolhido) |
| 23 | 23 | Recomendação final fundamentada |
| 24 | 24 | Exportação — modelos + parquets + tabelas |
| 25 | 25 | Relatório final |

---

### Algoritmos avaliados

| Algoritmo | Tipo | K testados | Métrica extra |
|-----------|------|-----------|---------------|
| K-Means | Partição | 2–10, K=3, K=4 | Inércia (WCSS) |
| Mini-Batch K-Means | Partição (rápido) | K=3, K=4 | Inércia |
| Agglomerative Ward | Hierárquico | K=3, K=4 | — |
| Gaussian Mixture (GMM) | Probabilístico | K=3, K=4 | BIC, AIC, Log-likelihood |
| DBSCAN | Densidade | automático | % ruído |

### Métricas de validação interna

| Métrica | Interpretação | Ótimo |
|---------|--------------|-------|
| Silhouette Score | Coesão/separação (−1 a 1) | Máximo |
| Calinski-Harabász | Razão variância inter/intra | Máximo |
| Davies-Bouldin | Similaridade média entre clusters | Mínimo |
| Inércia (WCSS) | Soma de distâncias intra-cluster | Mínimo |
| BIC / AIC | Informação — penaliza complexidade | Mínimo |
""", 'header'))

# ── CÉLULA 01 — Imports ───────────────────────────────────────────────────────
cells.append(code("""
# ============================================================
# CÉLULA 01 — Importações e Configuração
# ============================================================
import os, warnings, joblib, time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import seaborn as sns
import psycopg2
from pathlib import Path
from datetime import datetime
from itertools import product

from sklearn.cluster import (KMeans, AgglomerativeClustering,
                              DBSCAN, MiniBatchKMeans)
from sklearn.mixture import GaussianMixture
from sklearn.decomposition import PCA
from sklearn.metrics import (silhouette_score, calinski_harabasz_score,
                              davies_bouldin_score, silhouette_samples)
from sklearn.neighbors import NearestNeighbors
from scipy.cluster.hierarchy import dendrogram, linkage
from psycopg2.extras import execute_values

warnings.filterwarnings('ignore')
pd.set_option('display.float_format', '{:.4f}'.format)
pd.set_option('display.max_columns', 40)
pd.set_option('display.width', 120)
sns.set_theme(style='whitegrid', palette='muted')
plt.rcParams.update({'figure.dpi': 120, 'figure.facecolor': 'white'})

BASE_DIR     = Path('preprocess_output')
OUTPUT_DIR   = Path('clustering_research_output')
GRAFICOS_DIR = OUTPUT_DIR / 'graficos'
MODELOS_DIR  = OUTPUT_DIR / 'modelos'
TABELAS_DIR  = OUTPUT_DIR / 'tabelas'
for d in [OUTPUT_DIR, GRAFICOS_DIR, MODELOS_DIR, TABELAS_DIR]:
    d.mkdir(exist_ok=True)

import os as _os
DB_CONFIG = {
    'host':     _os.getenv('PGHOST',     '127.0.0.1'),
    'port':     int(_os.getenv('PGPORT', '5435')),
    'database': _os.getenv('PGDATABASE', 'maternar'),
    'user':     _os.getenv('PGUSER',     'postgres'),
    'password': _os.getenv('PGPASSWORD', ''),
}
RANDOM_STATE = 42
INICIO = datetime.now()

# Registro acumulado de todas as métricas
REGISTRO = []

print(f'[{INICIO:%H:%M:%S}] Pesquisa KDD Maternar iniciada')
print(f'Output: {OUTPUT_DIR.resolve()}')
print('✓ Ambiente configurado.')
""", 'c01-imports'))

# ── CÉLULA 02 — Load ──────────────────────────────────────────────────────────
cells.append(md("---\n## Etapa 2 — Carregamento dos Dados", 'h02'))
cells.append(code("""
# ============================================================
# CÉLULA 02 — Carregamento e Validação dos Dados
# ============================================================
t0 = time.time()
df_cluster  = pd.read_parquet(BASE_DIR / 'gestante_para_cluster.parquet')
df_features = pd.read_parquet(BASE_DIR / 'gestante_features.parquet')
scaler      = joblib.load(BASE_DIR / 'scaler_maternar.pkl')

df_cluster  = df_cluster.reset_index(drop=True)
df_features = df_features.reset_index(drop=True)

# Garantir sem nulos
assert df_cluster.isnull().sum().sum() == 0, "Nulos encontrados no dataset de cluster!"

print(f'Dataset cluster:  {df_cluster.shape[0]:,} × {df_cluster.shape[1]} features')
print(f'Dataset features: {df_features.shape[0]:,} × {df_features.shape[1]} colunas')
print(f'Carregamento:     {time.time()-t0:.1f}s')
print(f'\\nFeatures ({df_cluster.shape[1]}):')
for i, col in enumerate(df_cluster.columns, 1):
    print(f'  {i:2d}. {col}')

print(f'\\nDistribuição por ano:')
print(df_features['ano'].value_counts().sort_index().to_string())

print(f'\\nEstatísticas descritivas (features contínuas):')
COLS_CONT = ['nu_imc','nu_imc_pre_gestacional','ganho_imc','nu_peso','nu_altura']
print(df_features[COLS_CONT].describe().round(2).to_string())
""", 'c02-load'))

# ── CÉLULA 03 — PCA ───────────────────────────────────────────────────────────
cells.append(md("---\n## Etapa 3 — Redução de Dimensionalidade (PCA)", 'h03'))
cells.append(code("""
# ============================================================
# CÉLULA 03 — PCA (90% de variância)
# ============================================================
# PCA reduz a maldição da dimensionalidade e melhora as distâncias
# euclidianas usadas pelo K-Means. Threshold de 90% é padrão em literatura.

t0 = time.time()
pca_full = PCA(n_components=0.90, random_state=RANDOM_STATE)
X_pca    = pca_full.fit_transform(df_cluster.fillna(0))

n_comp  = pca_full.n_components_
var_acc = np.cumsum(pca_full.explained_variance_ratio_)

print(f'Dimensões originais → PCA: {df_cluster.shape[1]} → {n_comp}')
print(f'Tempo PCA: {time.time()-t0:.2f}s')
print(f'\\nVariância explicada acumulada por componente:')
for i, (v, vc) in enumerate(zip(pca_full.explained_variance_ratio_, var_acc), 1):
    bar = '█' * int(v * 100 / 2)
    print(f'  PC{i:02d}: {v*100:5.1f}%  [{bar:<15}]  acum={vc*100:.1f}%')

# Gráfico
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
comp_range = range(1, n_comp + 1)

axes[0].bar(comp_range, pca_full.explained_variance_ratio_ * 100,
            color='steelblue', edgecolor='white', linewidth=0.5)
axes[0].set_title('Variância Explicada por Componente', fontsize=11)
axes[0].set_xlabel('Componente Principal')
axes[0].set_ylabel('Variância Explicada (%)')
axes[0].set_xticks(comp_range)
for i, v in enumerate(pca_full.explained_variance_ratio_):
    axes[0].text(i+1, v*100+0.3, f'{v*100:.1f}%', ha='center', fontsize=7)

axes[1].plot(comp_range, var_acc * 100, marker='o', color='steelblue', linewidth=2)
axes[1].axhline(90, color='red', linestyle='--', label='90% alvo')
axes[1].fill_between(comp_range, var_acc * 100, alpha=0.15, color='steelblue')
axes[1].set_title('Variância Acumulada (PCA)', fontsize=11)
axes[1].set_xlabel('Número de Componentes')
axes[1].set_ylabel('Variância Acumulada (%)')
axes[1].set_xticks(comp_range)
axes[1].legend()

plt.suptitle(f'PCA — {df_cluster.shape[1]} features → {n_comp} componentes (90% variância)',
             fontsize=12, fontweight='bold')
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '01_pca_variancia.png', bbox_inches='tight')
plt.show()
print(f'✓ X_pca shape: {X_pca.shape}')
""", 'c03-pca'))

# ── CÉLULA 04 — Scan K=2-10 ───────────────────────────────────────────────────
cells.append(md("---\n## Etapa 4 — Varredura K=2–10: Todas as Métricas de Validação", 'h04'))
cells.append(code("""
# ============================================================
# CÉLULA 04 — Varredura K=2–10: Elbow + Silhouette + CH + Davies-Bouldin
# ============================================================
# Davies-Bouldin (DB): mede similaridade média entre clusters.
# DB = 0 indica clusters perfeitamente separados. Quanto menor, melhor.
# Complementa o Silhouette: DB penaliza clusters sobrepostos.

K_RANGE   = range(2, 11)
AMOSTRA_S = min(20_000, len(X_pca))
idx_s     = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), AMOSTRA_S, replace=False)
X_s       = X_pca[idx_s]

resultados_scan = []
print(f'Varredura K=2–10 (amostra Silhouette={AMOSTRA_S:,})...')
print(f"{'K':>3}  {'Inércia':>12}  {'Silhouette':>10}  {'Calinski-H':>12}  {'Davies-B':>10}")
print('-' * 55)

for k in K_RANGE:
    km    = KMeans(n_clusters=k, init='k-means++', n_init=10, random_state=RANDOM_STATE)
    lbs   = km.fit_predict(X_pca)
    lbs_s = lbs[idx_s]

    sil  = silhouette_score(X_s, lbs_s)
    ch   = calinski_harabasz_score(X_pca, lbs)
    db   = davies_bouldin_score(X_pca, lbs)
    iner = km.inertia_

    resultados_scan.append({'K': k, 'inercia': iner, 'silhouette': sil,
                            'calinski': ch, 'davies_bouldin': db})
    print(f'{k:>3}  {iner:>12,.0f}  {sil:>10.4f}  {ch:>12,.0f}  {db:>10.4f}')

df_scan = pd.DataFrame(resultados_scan).set_index('K')
df_scan.to_csv(TABELAS_DIR / 'scan_k2_k10.csv')

# Redução percentual da inércia
inercias = df_scan['inercia'].values
delta = [abs(inercias[i] - inercias[i-1]) / inercias[i-1] * 100 for i in range(1, len(inercias))]

# ── Gráfico 4 painéis ──
fig, axes = plt.subplots(2, 2, figsize=(14, 9))
ks = list(K_RANGE)

def mark_k(ax, candidates=[3,4]):
    for kk in candidates:
        ax.axvline(kk, color='red', linestyle='--', alpha=0.4, linewidth=1.2)
        ax.text(kk, ax.get_ylim()[1]*0.95, f'K={kk}', ha='center', color='red', fontsize=8)

# Elbow
axes[0,0].plot(ks, df_scan['inercia']/1e6, marker='o', color='steelblue', linewidth=2)
axes[0,0].set_title('Método do Cotovelo — Inércia (WCSS)', fontsize=11, fontweight='bold')
axes[0,0].set_xlabel('K'); axes[0,0].set_ylabel('Inércia (×10⁶)')
axes[0,0].set_xticks(ks)
mark_k(axes[0,0])

# Delta inércia
axes[0,1].bar(ks[1:], delta, color='steelblue', edgecolor='white')
axes[0,1].axhline(10, color='red', linestyle='--', label='Limiar 10%')
for i, v in enumerate(delta): axes[0,1].text(ks[i+1], v+0.2, f'{v:.1f}%', ha='center', fontsize=7)
axes[0,1].set_title('Redução % da Inércia por K', fontsize=11, fontweight='bold')
axes[0,1].set_xlabel('K'); axes[0,1].set_ylabel('Redução (%)')
axes[0,1].set_xticks(ks[1:]); axes[0,1].legend()
mark_k(axes[0,1])

# Silhouette
axes[1,0].plot(ks, df_scan['silhouette'], marker='o', color='crimson', linewidth=2)
axes[1,0].scatter([df_scan['silhouette'].idxmax()],
                  [df_scan['silhouette'].max()], s=120, color='gold',
                  zorder=5, label=f"Máx: K={df_scan['silhouette'].idxmax()}")
axes[1,0].set_title('Silhouette Score por K', fontsize=11, fontweight='bold')
axes[1,0].set_xlabel('K'); axes[1,0].set_ylabel('Silhouette Score')
axes[1,0].set_xticks(ks); axes[1,0].legend()
mark_k(axes[1,0])

# CH e DB no mesmo eixo (normalizado)
ax_ch = axes[1,1]
ax_db = ax_ch.twinx()
ax_ch.plot(ks, df_scan['calinski']/1000, marker='o', color='steelblue',
           linewidth=2, label='Calinski-H (÷1000, ↑)')
ax_db.plot(ks, df_scan['davies_bouldin'], marker='s', color='darkorange',
           linewidth=2, linestyle='--', label='Davies-Bouldin (↓)')
ax_ch.set_title('Calinski-Harabász ↑ / Davies-Bouldin ↓', fontsize=11, fontweight='bold')
ax_ch.set_xlabel('K')
ax_ch.set_ylabel('Calinski-H (÷1000)', color='steelblue')
ax_db.set_ylabel('Davies-Bouldin', color='darkorange')
ax_ch.set_xticks(ks)
lines1, lbs1 = ax_ch.get_legend_handles_labels()
lines2, lbs2 = ax_db.get_legend_handles_labels()
ax_ch.legend(lines1 + lines2, lbs1 + lbs2, fontsize=8, loc='upper right')
for kk in [3,4]:
    ax_ch.axvline(kk, color='red', linestyle='--', alpha=0.4, linewidth=1.2)

plt.suptitle('Varredura K=2–10 — Todas as Métricas de Validação Interna (K-Means)',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '02_scan_k2_10_metricas.png', bbox_inches='tight')
plt.show()

# Resumo
print(f'\\n=== Resumo da Varredura ===')
print(f"K Máximo Silhouette:    K={df_scan['silhouette'].idxmax()}  ({df_scan['silhouette'].max():.4f})")
print(f"K Mínimo Davies-Bouldin: K={df_scan['davies_bouldin'].idxmin()}  ({df_scan['davies_bouldin'].min():.4f})")
print(f"K Máximo Calinski-H:    K={df_scan['calinski'].idxmax()}  ({df_scan['calinski'].max():,.0f})")
print(f'\\nTabela completa salva: {TABELAS_DIR}/scan_k2_k10.csv')
""", 'c04-scan'))

# ── CÉLULA 05 — Gap Statistic ─────────────────────────────────────────────────
cells.append(md("---\n## Etapa 5 — Gap Statistic", 'h05'))
cells.append(code("""
# ============================================================
# CÉLULA 05 — Gap Statistic (Tibshirani et al., 2001)
# ============================================================
# Gap(K) = E[log(W_k*)] - log(W_k)
# W_k*: inércia média de B amostras aleatórias uniformes (referência)
# W_k:  inércia dos dados reais
# K ótimo = menor K tal que Gap(K) >= Gap(K+1) - std(K+1)
#
# Referência: Tibshirani R., Walther G., Hastie T. (2001).
# Estimating the number of clusters in a data set via the gap statistic.
# Journal of the Royal Statistical Society B, 63(2), 411–423.

import warnings
warnings.filterwarnings('ignore')

K_GAP  = range(2, 9)
B_BOOT = 10          # nº de referências bootstrap (aumentar para publicação)
N_GAP  = min(10_000, len(X_pca))  # amostra por velocidade

idx_g  = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), N_GAP, replace=False)
X_g    = X_pca[idx_g]

# Limites do espaço de referência (bounding box)
mins = X_g.min(axis=0)
maxs = X_g.max(axis=0)

gap_vals, gap_std = [], []
log_wks_real = []

print(f'Calculando Gap Statistic (B={B_BOOT} refs, n={N_GAP:,})...')
print(f"{'K':>3}  {'log(Wk)':>10}  {'E[log(Wk*)]':>13}  {'Gap':>8}  {'std':>8}")
print('-' * 50)

for k in K_GAP:
    km = KMeans(n_clusters=k, init='k-means++', n_init=5, random_state=RANDOM_STATE)
    km.fit(X_g)
    log_wk = np.log(km.inertia_)
    log_wks_real.append(log_wk)

    # Bootstrap referencias
    log_wk_boots = []
    for b in range(B_BOOT):
        X_ref = np.random.RandomState(b).uniform(mins, maxs, size=X_g.shape)
        km_ref = KMeans(n_clusters=k, init='k-means++', n_init=3,
                        random_state=b, max_iter=100)
        km_ref.fit(X_ref)
        log_wk_boots.append(np.log(km_ref.inertia_))

    gap    = np.mean(log_wk_boots) - log_wk
    s_k    = np.std(log_wk_boots) * np.sqrt(1 + 1/B_BOOT)
    gap_vals.append(gap)
    gap_std.append(s_k)
    print(f'{k:>3}  {log_wk:>10.4f}  {np.mean(log_wk_boots):>13.4f}  {gap:>8.4f}  {s_k:>8.4f}')

# K ótimo: menor K tal que Gap(K) >= Gap(K+1) - s(K+1)
k_gap_otimo = None
for i in range(len(gap_vals) - 1):
    if gap_vals[i] >= gap_vals[i+1] - gap_std[i+1]:
        k_gap_otimo = list(K_GAP)[i]
        break
if k_gap_otimo is None:
    k_gap_otimo = list(K_GAP)[np.argmax(gap_vals)]

# Gráfico
fig, ax = plt.subplots(figsize=(9, 4))
ks_g = list(K_GAP)
ax.plot(ks_g, gap_vals, marker='o', color='steelblue', linewidth=2, label='Gap(K)')
ax.fill_between(ks_g,
                [g - s for g, s in zip(gap_vals, gap_std)],
                [g + s for g, s in zip(gap_vals, gap_std)],
                alpha=0.2, color='steelblue', label='± std')
ax.axvline(k_gap_otimo, color='red', linestyle='--',
           label=f'K ótimo={k_gap_otimo} (critério 1-SE)')
ax.axvline(3, color='green', linestyle=':', alpha=0.7, label='K=3')
ax.axvline(4, color='orange', linestyle=':', alpha=0.7, label='K=4')
ax.set_title(f'Gap Statistic — B={B_BOOT} referências bootstrap (n={N_GAP:,})',
             fontsize=11, fontweight='bold')
ax.set_xlabel('K'); ax.set_ylabel('Gap(K)')
ax.set_xticks(ks_g); ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '03_gap_statistic.png', bbox_inches='tight')
plt.show()

df_gap = pd.DataFrame({'K': list(K_GAP), 'Gap': gap_vals, 'Std': gap_std})
df_gap.to_csv(TABELAS_DIR / 'gap_statistic.csv', index=False)
print(f'\\n→ K ótimo pelo Gap Statistic (1-SE): K={k_gap_otimo}')
print(f'→ Gap em K=3: {gap_vals[list(K_GAP).index(3)]:.4f}')
print(f'→ Gap em K=4: {gap_vals[list(K_GAP).index(4)]:.4f}')
""", 'c05-gap'))

# ── CÉLULA 06 — Dendrograma ───────────────────────────────────────────────────
cells.append(md("---\n## Etapa 6 — Dendrograma (Hierárquico Ward)", 'h06'))
cells.append(code("""
# ============================================================
# CÉLULA 06 — Dendrograma — Validação Visual do K
# ============================================================
N_DENDRO = 3_000
idx_d    = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), N_DENDRO, replace=False)
X_d      = X_pca[idx_d]

print(f'Calculando dendrograma (Ward, n={N_DENDRO:,})...')
Z = linkage(X_d, method='ward')

# Detectar cortes para K=3 e K=4
from scipy.cluster.hierarchy import fcluster
lbs_d3 = fcluster(Z, 3, criterion='maxclust')
lbs_d4 = fcluster(Z, 4, criterion='maxclust')

# Distâncias dos cortes
dists = sorted(Z[:, 2], reverse=True)
corte_k3 = (dists[1] + dists[2]) / 2  # entre 3ª e 4ª maior fusão
corte_k4 = (dists[2] + dists[3]) / 2

fig, ax = plt.subplots(figsize=(15, 5))
dendrogram(Z, ax=ax, truncate_mode='lastp', p=25,
           leaf_rotation=45, leaf_font_size=7, show_contracted=True,
           color_threshold=corte_k4)
ax.set_title(f'Dendrograma — Hierárquico Ward (n={N_DENDRO:,} gestantes)',
             fontsize=12, fontweight='bold')
ax.set_xlabel('Grupos de gestantes'); ax.set_ylabel('Distância Ward')
ax.axhline(corte_k3, color='green', linestyle='--', linewidth=1.5,
           label=f'Corte K=3 (~{corte_k3:.1f})')
ax.axhline(corte_k4, color='orange', linestyle='--', linewidth=1.5,
           label=f'Corte K=4 (~{corte_k4:.1f})')
ax.legend(fontsize=9)
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '04_dendrograma_ward.png', bbox_inches='tight')
plt.show()
print(f'→ Corte para K=3: distância ≈ {corte_k3:.2f}')
print(f'→ Corte para K=4: distância ≈ {corte_k4:.2f}')
print(f'→ Distribuição hierárquica K=3: {pd.Series(lbs_d3).value_counts().sort_index().to_dict()}')
print(f'→ Distribuição hierárquica K=4: {pd.Series(lbs_d4).value_counts().sort_index().to_dict()}')
""", 'c06-dendro'))

# ── CÉLULA 07 — DBSCAN ────────────────────────────────────────────────────────
cells.append(md("---\n## Etapa 7 — DBSCAN: Estrutura de Densidade e Outliers", 'h07'))
cells.append(code("""
# ============================================================
# CÉLULA 07 — DBSCAN + K-Distância
# ============================================================
N_DB   = min(30_000, len(X_pca))
idx_db = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), N_DB, replace=False)
X_db   = X_pca[idx_db]
K_VIZ  = 5

print(f'K-distância (k={K_VIZ}, n={N_DB:,})...')
nbrs       = NearestNeighbors(n_neighbors=K_VIZ).fit(X_db)
dists_nn, _ = nbrs.kneighbors(X_db)
dist_k      = np.sort(dists_nn[:, K_VIZ-1])[::-1]
eps_est     = float(np.percentile(dist_k, 5))

fig, ax = plt.subplots(figsize=(11, 4))
ax.plot(dist_k, color='steelblue', linewidth=0.7, label='k-distância')
ax.axhline(eps_est, color='red', linestyle='--', linewidth=1.5,
           label=f'ε estimado = {eps_est:.3f} (percentil 5)')
ax.set_title(f'K-Distância (k={K_VIZ}) — Estimativa de ε para DBSCAN',
             fontsize=11, fontweight='bold')
ax.set_xlabel('Pontos ordenados'); ax.set_ylabel(f'Dist. ao {K_VIZ}º vizinho')
ax.legend()
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '05_dbscan_kdistancia.png', bbox_inches='tight')
plt.show()

print(f'\\nExecutando DBSCAN (ε={eps_est:.3f}, min_samples={K_VIZ})...')
db = DBSCAN(eps=eps_est, min_samples=K_VIZ).fit(X_db)
n_clust_db = len(set(db.labels_)) - (1 if -1 in db.labels_ else 0)
n_ruido    = int((db.labels_ == -1).sum())
pct_ruido  = n_ruido / N_DB * 100

# Métricas DBSCAN (excluindo ruído)
mask_valid = db.labels_ != -1
if mask_valid.sum() > 1 and len(set(db.labels_[mask_valid])) > 1:
    sil_db = silhouette_score(X_db[mask_valid], db.labels_[mask_valid])
    db_db  = davies_bouldin_score(X_db[mask_valid], db.labels_[mask_valid])
else:
    sil_db = db_db = float('nan')

print(f'\\n=== DBSCAN (ε={eps_est:.3f}) ===')
print(f'  Clusters encontrados:  {n_clust_db}')
print(f'  Gestantes como ruído:  {n_ruido:,} ({pct_ruido:.1f}%)')
print(f'  Silhouette (sem ruído): {sil_db:.4f}' if not np.isnan(sil_db) else '  Silhouette: N/A')
print(f'  Davies-Bouldin:         {db_db:.4f}' if not np.isnan(db_db) else '  Davies-Bouldin: N/A')
print(f'  Distribuição: {pd.Series(db.labels_[mask_valid]).value_counts().sort_index().to_dict()}')

REGISTRO.append({
    'Modelo': 'DBSCAN', 'K': n_clust_db,
    'Silhouette': round(sil_db, 4) if not np.isnan(sil_db) else None,
    'Davies-Bouldin': round(db_db, 4) if not np.isnan(db_db) else None,
    'Calinski-H': None, 'Inércia/BIC': None,
    'Ruído (%)': round(pct_ruido, 1), 'Nota': f'ε={eps_est:.3f}'
})
print(f'\\n→ Ruído {pct_ruido:.1f}% {"< 15% — estrutura real confirmada ✓" if pct_ruido < 15 else "> 15% — ATENÇÃO"}')
""", 'c07-dbscan'))

# ── CÉLULA 08 — K-Means K=3 ───────────────────────────────────────────────────
cells.append(md("---\n## Etapa 8 — K-Means K=3 (Análise Completa)", 'h08'))
cells.append(code("""
# ============================================================
# CÉLULA 08 — K-Means K=3
# ============================================================
K3 = 3
AMOSTRA_M = min(20_000, len(X_pca))
idx_m     = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), AMOSTRA_M, replace=False)

print(f'Treinando K-Means K={K3} (k-means++, n_init=20)...')
t0 = time.time()
km3 = KMeans(n_clusters=K3, init='k-means++', n_init=20, random_state=RANDOM_STATE)
lbs_km3 = km3.fit_predict(X_pca)
tempo_km3 = time.time() - t0

sil_km3 = silhouette_score(X_pca[idx_m], lbs_km3[idx_m])
ch_km3  = calinski_harabasz_score(X_pca, lbs_km3)
db_km3  = davies_bouldin_score(X_pca, lbs_km3)

dist_km3 = pd.Series(lbs_km3).value_counts().sort_index()
print(f'\\n=== K-Means K=3 ===')
print(f'  Inércia:          {km3.inertia_:,.0f}')
print(f'  Silhouette:       {sil_km3:.4f}')
print(f'  Calinski-H:       {ch_km3:,.0f}')
print(f'  Davies-Bouldin:   {db_km3:.4f}')
print(f'  Tempo treino:     {tempo_km3:.2f}s')
print(f'  Distribuição:')
for c, n in dist_km3.items():
    print(f'    C{c}: {n:>7,} ({n/len(lbs_km3)*100:.1f}%)')

# Centroides em escala real
df_feat_km3        = df_features.copy()
df_feat_km3['cluster'] = lbs_km3
COLS_CENT = ['nu_imc','nu_imc_pre_gestacional','ganho_imc','nu_peso',
             'escolaridade','log_taxa_sifilis_gest','cnes_hospitais']
COLS_CENT = [c for c in COLS_CENT if c in df_feat_km3.columns]
cent_km3 = df_feat_km3[COLS_CENT + ['cluster']].groupby('cluster').mean().round(3)

print(f'\\nCentroides K-Means K=3:')
print(cent_km3.T.to_string())

# Heatmap centroides
fig, ax = plt.subplots(figsize=(10, 4))
heat = (cent_km3 - cent_km3.min()) / (cent_km3.max() - cent_km3.min() + 1e-9)
sns.heatmap(heat.T, annot=cent_km3.T.round(2), fmt='.2f',
            cmap='RdYlGn_r', ax=ax, linewidths=0.5,
            cbar_kws={'label': 'Normalizado (0=min, 1=max)'},
            annot_kws={'size': 9})
ax.set_title(f'Centroides K-Means K=3 (valores reais anotados)', fontsize=11, fontweight='bold')
ax.set_xticklabels([f'C{c}' for c in range(K3)])
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '06_kmeans_k3_centroides.png', bbox_inches='tight')
plt.show()

# Salvar modelo e labels
joblib.dump(km3, MODELOS_DIR / 'kmeans_k3.pkl')
cent_km3.to_csv(TABELAS_DIR / 'centroides_kmeans_k3.csv')
lbs_km3_series = pd.Series(lbs_km3, name='cluster_km3')

REGISTRO.append({
    'Modelo': 'K-Means', 'K': K3,
    'Silhouette': round(sil_km3, 4),
    'Davies-Bouldin': round(db_km3, 4),
    'Calinski-H': round(ch_km3, 0),
    'Inércia/BIC': round(km3.inertia_, 0),
    'Ruído (%)': 0.0, 'Nota': f'n_init=20, {tempo_km3:.1f}s'
})
print(f'\\n✓ kmeans_k3.pkl salvo')
""", 'c08-km3'))

# ── CÉLULA 09 — K-Means K=4 ───────────────────────────────────────────────────
cells.append(md("---\n## Etapa 9 — K-Means K=4 (Análise Completa)", 'h09'))
cells.append(code("""
# ============================================================
# CÉLULA 09 — K-Means K=4
# ============================================================
K4 = 4
print(f'Treinando K-Means K={K4} (k-means++, n_init=20)...')
t0 = time.time()
km4 = KMeans(n_clusters=K4, init='k-means++', n_init=20, random_state=RANDOM_STATE)
lbs_km4 = km4.fit_predict(X_pca)
tempo_km4 = time.time() - t0

sil_km4 = silhouette_score(X_pca[idx_m], lbs_km4[idx_m])
ch_km4  = calinski_harabasz_score(X_pca, lbs_km4)
db_km4  = davies_bouldin_score(X_pca, lbs_km4)

dist_km4 = pd.Series(lbs_km4).value_counts().sort_index()
print(f'\\n=== K-Means K=4 ===')
print(f'  Inércia:          {km4.inertia_:,.0f}')
print(f'  Silhouette:       {sil_km4:.4f}')
print(f'  Calinski-H:       {ch_km4:,.0f}')
print(f'  Davies-Bouldin:   {db_km4:.4f}')
print(f'  Tempo treino:     {tempo_km4:.2f}s')
print(f'  Distribuição:')
for c, n in dist_km4.items():
    print(f'    C{c}: {n:>7,} ({n/len(lbs_km4)*100:.1f}%)')

df_feat_km4        = df_features.copy()
df_feat_km4['cluster'] = lbs_km4
cent_km4 = df_feat_km4[COLS_CENT + ['cluster']].groupby('cluster').mean().round(3)

print(f'\\nCentroides K-Means K=4:')
print(cent_km4.T.to_string())

fig, ax = plt.subplots(figsize=(12, 4))
heat4 = (cent_km4 - cent_km4.min()) / (cent_km4.max() - cent_km4.min() + 1e-9)
sns.heatmap(heat4.T, annot=cent_km4.T.round(2), fmt='.2f',
            cmap='RdYlGn_r', ax=ax, linewidths=0.5,
            cbar_kws={'label': 'Normalizado (0=min, 1=max)'},
            annot_kws={'size': 9})
ax.set_title(f'Centroides K-Means K=4 (valores reais anotados)', fontsize=11, fontweight='bold')
ax.set_xticklabels([f'C{c}' for c in range(K4)])
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '07_kmeans_k4_centroides.png', bbox_inches='tight')
plt.show()

joblib.dump(km4, MODELOS_DIR / 'kmeans_k4.pkl')
cent_km4.to_csv(TABELAS_DIR / 'centroides_kmeans_k4.csv')
lbs_km4_series = pd.Series(lbs_km4, name='cluster_km4')

REGISTRO.append({
    'Modelo': 'K-Means', 'K': K4,
    'Silhouette': round(sil_km4, 4),
    'Davies-Bouldin': round(db_km4, 4),
    'Calinski-H': round(ch_km4, 0),
    'Inércia/BIC': round(km4.inertia_, 0),
    'Ruído (%)': 0.0, 'Nota': f'n_init=20, {tempo_km4:.1f}s'
})
print(f'\\n✓ kmeans_k4.pkl salvo')
""", 'c09-km4'))

# ── CÉLULA 10 — Agglomerative K=3 ────────────────────────────────────────────
cells.append(md("---\n## Etapa 10 — Agglomerative Ward K=3", 'h10'))
cells.append(code("""
# ============================================================
# CÉLULA 10 — Agglomerative Ward K=3
# ============================================================
# Agglomerative (hierárquico) não requer K a priori e não assume
# clusters esféricos. Ward minimiza a variância intra-cluster.
# Limitação: O(n²) de memória — usa amostra representativa.

N_AGG  = min(8_000, len(X_pca))   # Ward é O(n²) em memória — manter ≤ 10k
idx_ag = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), N_AGG, replace=False)
X_ag   = X_pca[idx_ag]

print(f'Treinando Agglomerative Ward K=3 (n={N_AGG:,})...')
t0 = time.time()
agg3 = AgglomerativeClustering(n_clusters=3, linkage='ward')
lbs_agg3_sample = agg3.fit_predict(X_ag)
tempo_agg3 = time.time() - t0

# Atribuir gestantes restantes via KNN (k=1)
from sklearn.neighbors import KNeighborsClassifier
knn3 = KNeighborsClassifier(n_neighbors=1)
knn3.fit(X_ag, lbs_agg3_sample)
lbs_agg3 = knn3.predict(X_pca)

sil_agg3 = silhouette_score(X_pca[idx_m], lbs_agg3[idx_m])
ch_agg3  = calinski_harabasz_score(X_pca, lbs_agg3)
db_agg3  = davies_bouldin_score(X_pca, lbs_agg3)

dist_agg3 = pd.Series(lbs_agg3).value_counts().sort_index()
print(f'\\n=== Agglomerative Ward K=3 ===')
print(f'  Silhouette:       {sil_agg3:.4f}')
print(f'  Calinski-H:       {ch_agg3:,.0f}')
print(f'  Davies-Bouldin:   {db_agg3:.4f}')
print(f'  Tempo:            {tempo_agg3:.2f}s (amostra {N_AGG:,}) + KNN propagação')
print(f'  Distribuição:')
for c, n in dist_agg3.items():
    print(f'    C{c}: {n:>7,} ({n/len(lbs_agg3)*100:.1f}%)')

df_feat_agg3 = df_features.copy()
df_feat_agg3['cluster'] = lbs_agg3
cent_agg3 = df_feat_agg3[COLS_CENT + ['cluster']].groupby('cluster').mean().round(3)
print(f'\\nCentroides Agglomerative K=3:')
print(cent_agg3.T.to_string())

cent_agg3.to_csv(TABELAS_DIR / 'centroides_agg_k3.csv')
joblib.dump(agg3, MODELOS_DIR / 'agg_ward_k3.pkl')
lbs_agg3_series = pd.Series(lbs_agg3, name='cluster_agg3')

REGISTRO.append({
    'Modelo': 'Agglomerative Ward', 'K': 3,
    'Silhouette': round(sil_agg3, 4),
    'Davies-Bouldin': round(db_agg3, 4),
    'Calinski-H': round(ch_agg3, 0),
    'Inércia/BIC': None,
    'Ruído (%)': 0.0, 'Nota': f'n={N_AGG:,} + KNN, {tempo_agg3:.1f}s'
})
print('✓ Agglomerative Ward K=3 concluído')
""", 'c10-agg3'))

# ── CÉLULA 11 — Agglomerative K=4 ────────────────────────────────────────────
cells.append(md("---\n## Etapa 11 — Agglomerative Ward K=4", 'h11'))
cells.append(code("""
# ============================================================
# CÉLULA 11 — Agglomerative Ward K=4
# ============================================================
print(f'Treinando Agglomerative Ward K=4 (n={N_AGG:,})...')
t0 = time.time()
agg4 = AgglomerativeClustering(n_clusters=4, linkage='ward')
lbs_agg4_sample = agg4.fit_predict(X_ag)
tempo_agg4 = time.time() - t0

knn4 = KNeighborsClassifier(n_neighbors=1)
knn4.fit(X_ag, lbs_agg4_sample)
lbs_agg4 = knn4.predict(X_pca)

sil_agg4 = silhouette_score(X_pca[idx_m], lbs_agg4[idx_m])
ch_agg4  = calinski_harabasz_score(X_pca, lbs_agg4)
db_agg4  = davies_bouldin_score(X_pca, lbs_agg4)

dist_agg4 = pd.Series(lbs_agg4).value_counts().sort_index()
print(f'\\n=== Agglomerative Ward K=4 ===')
print(f'  Silhouette:       {sil_agg4:.4f}')
print(f'  Calinski-H:       {ch_agg4:,.0f}')
print(f'  Davies-Bouldin:   {db_agg4:.4f}')
print(f'  Tempo:            {tempo_agg4:.2f}s + KNN')
print(f'  Distribuição:')
for c, n in dist_agg4.items():
    print(f'    C{c}: {n:>7,} ({n/len(lbs_agg4)*100:.1f}%)')

df_feat_agg4 = df_features.copy()
df_feat_agg4['cluster'] = lbs_agg4
cent_agg4 = df_feat_agg4[COLS_CENT + ['cluster']].groupby('cluster').mean().round(3)
print(f'\\nCentroides Agglomerative K=4:')
print(cent_agg4.T.to_string())

cent_agg4.to_csv(TABELAS_DIR / 'centroides_agg_k4.csv')
joblib.dump(agg4, MODELOS_DIR / 'agg_ward_k4.pkl')
lbs_agg4_series = pd.Series(lbs_agg4, name='cluster_agg4')

REGISTRO.append({
    'Modelo': 'Agglomerative Ward', 'K': 4,
    'Silhouette': round(sil_agg4, 4),
    'Davies-Bouldin': round(db_agg4, 4),
    'Calinski-H': round(ch_agg4, 0),
    'Inércia/BIC': None,
    'Ruído (%)': 0.0, 'Nota': f'n={N_AGG:,} + KNN, {tempo_agg4:.1f}s'
})
print('✓ Agglomerative Ward K=4 concluído')
""", 'c11-agg4'))

# ── CÉLULA 12 — GMM K=3 ──────────────────────────────────────────────────────
cells.append(md("---\n## Etapa 12 — Gaussian Mixture Model (GMM) K=3", 'h12'))
cells.append(code("""
# ============================================================
# CÉLULA 12 — Gaussian Mixture Model K=3
# ============================================================
# GMM é um modelo probabilístico: cada gestante recebe probabilidade
# de pertencer a cada cluster (soft assignment).
# BIC = -2*log-likelihood + k*log(n) — penaliza modelos complexos.
# AIC = -2*log-likelihood + 2k        — penaliza menos.
# Menor BIC/AIC = melhor modelo.
#
# covariance_type='full': cada cluster tem matriz de covariância própria.
# Mais flexível que K-Means (que assume clusters esféricos).

N_GMM = min(30_000, len(X_pca))
idx_gmm = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), N_GMM, replace=False)
X_gmm   = X_pca[idx_gmm]

print(f'Treinando GMM K=3 (full covariance, n={N_GMM:,})...')
t0 = time.time()
gmm3 = GaussianMixture(n_components=3, covariance_type='full',
                        max_iter=200, n_init=5, random_state=RANDOM_STATE)
gmm3.fit(X_gmm)
tempo_gmm3 = time.time() - t0

lbs_gmm3    = gmm3.predict(X_pca)
probs_gmm3  = gmm3.predict_proba(X_pca)
bic_gmm3    = gmm3.bic(X_gmm)
aic_gmm3    = gmm3.aic(X_gmm)
loglik_gmm3 = gmm3.score(X_gmm) * N_GMM

sil_gmm3 = silhouette_score(X_pca[idx_m], lbs_gmm3[idx_m])
ch_gmm3  = calinski_harabasz_score(X_pca, lbs_gmm3)
db_gmm3  = davies_bouldin_score(X_pca, lbs_gmm3)

# Incerteza: entropia média das distribuições de probabilidade
entropia_gmm3 = -np.sum(probs_gmm3 * np.log(probs_gmm3 + 1e-10), axis=1).mean()

dist_gmm3 = pd.Series(lbs_gmm3).value_counts().sort_index()
print(f'\\n=== GMM K=3 ===')
print(f'  BIC:              {bic_gmm3:,.2f}')
print(f'  AIC:              {aic_gmm3:,.2f}')
print(f'  Log-likelihood:   {loglik_gmm3:,.2f}')
print(f'  Silhouette:       {sil_gmm3:.4f}')
print(f'  Calinski-H:       {ch_gmm3:,.0f}')
print(f'  Davies-Bouldin:   {db_gmm3:.4f}')
print(f'  Entropia média:   {entropia_gmm3:.4f} (0=certo, >0=incerto)')
print(f'  Tempo:            {tempo_gmm3:.2f}s')
print(f'  Convergiu:        {gmm3.converged_}')
print(f'  Distribuição (hard labels):')
for c, n in dist_gmm3.items():
    print(f'    C{c}: {n:>7,} ({n/len(lbs_gmm3)*100:.1f}%)  prob média: {probs_gmm3[:, c].mean():.3f}')

df_feat_gmm3 = df_features.copy()
df_feat_gmm3['cluster'] = lbs_gmm3
cent_gmm3 = df_feat_gmm3[COLS_CENT + ['cluster']].groupby('cluster').mean().round(3)
cent_gmm3.to_csv(TABELAS_DIR / 'centroides_gmm_k3.csv')
joblib.dump(gmm3, MODELOS_DIR / 'gmm_k3.pkl')

REGISTRO.append({
    'Modelo': 'GMM (full)', 'K': 3,
    'Silhouette': round(sil_gmm3, 4),
    'Davies-Bouldin': round(db_gmm3, 4),
    'Calinski-H': round(ch_gmm3, 0),
    'Inércia/BIC': round(bic_gmm3, 0),
    'Ruído (%)': 0.0,
    'Nota': f'AIC={aic_gmm3:.0f}, H={entropia_gmm3:.3f}'
})
print('✓ GMM K=3 concluído')
""", 'c12-gmm3'))

# ── CÉLULA 13 — GMM K=4 ──────────────────────────────────────────────────────
cells.append(md("---\n## Etapa 13 — Gaussian Mixture Model (GMM) K=4", 'h13'))
cells.append(code("""
# ============================================================
# CÉLULA 13 — GMM K=4 + Varredura BIC/AIC K=2–8
# ============================================================
print(f'Treinando GMM K=4 (full covariance, n={N_GMM:,})...')
t0 = time.time()
gmm4 = GaussianMixture(n_components=4, covariance_type='full',
                        max_iter=200, n_init=5, random_state=RANDOM_STATE)
gmm4.fit(X_gmm)
tempo_gmm4 = time.time() - t0

lbs_gmm4    = gmm4.predict(X_pca)
probs_gmm4  = gmm4.predict_proba(X_pca)
bic_gmm4    = gmm4.bic(X_gmm)
aic_gmm4    = gmm4.aic(X_gmm)
loglik_gmm4 = gmm4.score(X_gmm) * N_GMM
entropia_gmm4 = -np.sum(probs_gmm4 * np.log(probs_gmm4 + 1e-10), axis=1).mean()

sil_gmm4 = silhouette_score(X_pca[idx_m], lbs_gmm4[idx_m])
ch_gmm4  = calinski_harabasz_score(X_pca, lbs_gmm4)
db_gmm4  = davies_bouldin_score(X_pca, lbs_gmm4)

dist_gmm4 = pd.Series(lbs_gmm4).value_counts().sort_index()
print(f'\\n=== GMM K=4 ===')
print(f'  BIC:              {bic_gmm4:,.2f}')
print(f'  AIC:              {aic_gmm4:,.2f}')
print(f'  Silhouette:       {sil_gmm4:.4f}')
print(f'  Calinski-H:       {ch_gmm4:,.0f}')
print(f'  Davies-Bouldin:   {db_gmm4:.4f}')
print(f'  Entropia média:   {entropia_gmm4:.4f}')
print(f'  Tempo:            {tempo_gmm4:.2f}s')
print(f'  Distribuição:')
for c, n in dist_gmm4.items():
    print(f'    C{c}: {n:>7,} ({n/len(lbs_gmm4)*100:.1f}%)')

df_feat_gmm4 = df_features.copy()
df_feat_gmm4['cluster'] = lbs_gmm4
cent_gmm4 = df_feat_gmm4[COLS_CENT + ['cluster']].groupby('cluster').mean().round(3)
cent_gmm4.to_csv(TABELAS_DIR / 'centroides_gmm_k4.csv')
joblib.dump(gmm4, MODELOS_DIR / 'gmm_k4.pkl')

REGISTRO.append({
    'Modelo': 'GMM (full)', 'K': 4,
    'Silhouette': round(sil_gmm4, 4),
    'Davies-Bouldin': round(db_gmm4, 4),
    'Calinski-H': round(ch_gmm4, 0),
    'Inércia/BIC': round(bic_gmm4, 0),
    'Ruído (%)': 0.0,
    'Nota': f'AIC={aic_gmm4:.0f}, H={entropia_gmm4:.3f}'
})

# ── Varredura BIC/AIC GMM K=2–8 ──
print('\\nVarredura BIC/AIC GMM K=2–8...')
bics, aics, k_gmm_range = [], [], range(2, 9)
for k in k_gmm_range:
    g = GaussianMixture(n_components=k, covariance_type='full',
                        max_iter=100, n_init=3, random_state=RANDOM_STATE)
    g.fit(X_gmm)
    bics.append(g.bic(X_gmm))
    aics.append(g.aic(X_gmm))
    print(f'  K={k}: BIC={g.bic(X_gmm):,.0f}  AIC={g.aic(X_gmm):,.0f}')

fig, ax = plt.subplots(figsize=(9, 4))
ks_g = list(k_gmm_range)
ax.plot(ks_g, [b/1e6 for b in bics], marker='o', color='steelblue',
        linewidth=2, label='BIC (÷10⁶)')
ax.plot(ks_g, [a/1e6 for a in aics], marker='s', color='crimson',
        linewidth=2, linestyle='--', label='AIC (÷10⁶)')
ax.axvline(3, color='green', linestyle=':', alpha=0.8, label='K=3')
ax.axvline(4, color='orange', linestyle=':', alpha=0.8, label='K=4')
ax.set_title('GMM — BIC e AIC por K (menor = melhor)', fontsize=11, fontweight='bold')
ax.set_xlabel('K'); ax.set_ylabel('Critério (÷10⁶)')
ax.set_xticks(ks_g); ax.legend()
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '08_gmm_bic_aic.png', bbox_inches='tight')
plt.show()
print(f'\\n→ K com menor BIC: K={ks_g[np.argmin(bics)]}')
print(f'→ K com menor AIC: K={ks_g[np.argmin(aics)]}')
""", 'c13-gmm4'))

# ── CÉLULA 14 — Mini-Batch K-Means ───────────────────────────────────────────
cells.append(md("---\n## Etapa 14 — Mini-Batch K-Means K=3 e K=4", 'h14'))
cells.append(code("""
# ============================================================
# CÉLULA 14 — Mini-Batch K-Means (benchmark de velocidade)
# ============================================================
# Mini-Batch K-Means usa subamostras aleatórias por iteração.
# Muito mais rápido para datasets grandes, com pequena perda de qualidade.
# Útil para validar que K-Means clássico não está over-ajustado.

for k_mb in [3, 4]:
    print(f'\\nMini-Batch K-Means K={k_mb}...')
    t0 = time.time()
    mb = MiniBatchKMeans(n_clusters=k_mb, init='k-means++', n_init=10,
                         batch_size=4096, random_state=RANDOM_STATE, max_iter=300)
    lbs_mb = mb.fit_predict(X_pca)
    t_mb = time.time() - t0

    sil_mb = silhouette_score(X_pca[idx_m], lbs_mb[idx_m])
    ch_mb  = calinski_harabasz_score(X_pca, lbs_mb)
    db_mb  = davies_bouldin_score(X_pca, lbs_mb)

    print(f'  Inércia:        {mb.inertia_:,.0f}')
    print(f'  Silhouette:     {sil_mb:.4f}')
    print(f'  Calinski-H:     {ch_mb:,.0f}')
    print(f'  Davies-Bouldin: {db_mb:.4f}')
    print(f'  Tempo:          {t_mb:.2f}s  (vs K-Means clássico {tempo_km3 if k_mb==3 else tempo_km4:.2f}s)')

    dist_mb = pd.Series(lbs_mb).value_counts().sort_index()
    for c, n in dist_mb.items():
        print(f'    C{c}: {n:>7,} ({n/len(lbs_mb)*100:.1f}%)')

    joblib.dump(mb, MODELOS_DIR / f'minibatch_km_{k_mb}.pkl')
    REGISTRO.append({
        'Modelo': 'Mini-Batch K-Means', 'K': k_mb,
        'Silhouette': round(sil_mb, 4),
        'Davies-Bouldin': round(db_mb, 4),
        'Calinski-H': round(ch_mb, 0),
        'Inércia/BIC': round(mb.inertia_, 0),
        'Ruído (%)': 0.0, 'Nota': f'batch=4096, {t_mb:.1f}s'
    })

print('\\n✓ Mini-Batch K-Means K=3 e K=4 concluídos')
""", 'c14-mb'))

# ── CÉLULA 15 — Tabela Comparativa ───────────────────────────────────────────
cells.append(md("---\n## Etapa 15 — Tabela Comparativa Geral", 'h15'))
cells.append(code("""
# ============================================================
# CÉLULA 15 — Tabela Comparativa — Todos os Modelos × Métricas
# ============================================================
df_reg = pd.DataFrame(REGISTRO)
df_reg = df_reg.sort_values(['K', 'Modelo']).reset_index(drop=True)
df_reg.to_csv(TABELAS_DIR / 'comparativo_geral.csv', index=False)

print('=' * 90)
print('  TABELA COMPARATIVA — TODOS OS MODELOS × TODAS AS MÉTRICAS')
print('=' * 90)
print(f"{'Modelo':<22} {'K':>3}  {'Silhouette':>10}  {'Davies-Bouldin':>14}  {'Calinski-H':>12}  {'Inércia/BIC':>12}")
print('-' * 80)

for _, row in df_reg.iterrows():
    if pd.isna(row.get('Silhouette')): continue
    bic_str = f"{row['Inércia/BIC']:>12,.0f}" if row['Inércia/BIC'] else '           —'
    print(f"{row['Modelo']:<22} {int(row['K']):>3}  "
          f"{row['Silhouette']:>10.4f}  {row['Davies-Bouldin']:>14.4f}  "
          f"{row['Calinski-H']:>12,.0f}  {bic_str}")

print('\\nRegras de interpretação:')
print('  Silhouette:     ↑ melhor  (escala −1 a 1, >0.2 razoável, >0.5 forte)')
print('  Davies-Bouldin: ↓ melhor  (0 = clusters perfeitamente separados)')
print('  Calinski-H:     ↑ melhor  (sem limite superior)')
print('  Inércia:        ↓ melhor  (compactação intra-cluster)')
print('  BIC/AIC (GMM):  ↓ melhor  (penaliza complexidade)')

# Ranking por Silhouette
print(f'\\n=== Ranking por Silhouette Score (maiores) ===')
rank = df_reg.dropna(subset=['Silhouette']).sort_values('Silhouette', ascending=False)
for i, (_, r) in enumerate(rank.iterrows(), 1):
    print(f'  {i}. {r["Modelo"]} K={int(r["K"])}: {r["Silhouette"]:.4f}')

# Ranking por Davies-Bouldin
print(f'\\n=== Ranking por Davies-Bouldin (menores) ===')
rank_db = df_reg.dropna(subset=['Davies-Bouldin']).sort_values('Davies-Bouldin')
for i, (_, r) in enumerate(rank_db.iterrows(), 1):
    print(f'  {i}. {r["Modelo"]} K={int(r["K"])}: {r["Davies-Bouldin"]:.4f}')

# Gráfico radar/bar comparativo
fig, axes = plt.subplots(1, 2, figsize=(15, 5))
df_plot = df_reg.dropna(subset=['Silhouette', 'Davies-Bouldin']).copy()
df_plot['label'] = df_plot['Modelo'].str.replace('Agglomerative Ward', 'Agg. Ward') + ' K=' + df_plot['K'].astype(int).astype(str)

def _cor(k):
    return 'steelblue' if int(k) == 3 else ('crimson' if int(k) == 4 else 'gray')

# Silhouette
bars0 = axes[0].bar(df_plot['label'], df_plot['Silhouette'],
                    color=[_cor(k) for k in df_plot['K']],
                    edgecolor='white', linewidth=0.5)
axes[0].set_title('Silhouette Score (↑ melhor)', fontsize=11, fontweight='bold')
axes[0].set_ylabel('Silhouette')
axes[0].set_xticklabels(df_plot['label'], rotation=35, ha='right', fontsize=8)
for bar, v in zip(bars0, df_plot['Silhouette']):
    axes[0].text(bar.get_x() + bar.get_width()/2, v + 0.001, f'{v:.4f}',
                 ha='center', fontsize=7)
axes[0].legend(handles=[
    mpatches.Patch(color='steelblue', label='K=3'),
    mpatches.Patch(color='crimson', label='K=4')
], fontsize=9)

# Davies-Bouldin
bars1 = axes[1].bar(df_plot['label'], df_plot['Davies-Bouldin'],
                    color=[_cor(k) for k in df_plot['K']],
                    edgecolor='white', linewidth=0.5)
axes[1].set_title('Davies-Bouldin Index (↓ melhor)', fontsize=11, fontweight='bold')
axes[1].set_ylabel('Davies-Bouldin')
axes[1].set_xticklabels(df_plot['label'], rotation=35, ha='right', fontsize=8)
for bar, v in zip(bars1, df_plot['Davies-Bouldin']):
    axes[1].text(bar.get_x() + bar.get_width()/2, v + 0.002, f'{v:.4f}',
                 ha='center', fontsize=7)

plt.suptitle('Comparativo de Modelos — Silhouette e Davies-Bouldin', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '09_comparativo_modelos.png', bbox_inches='tight')
plt.show()
print(f'\\n✓ comparativo_geral.csv salvo')
""", 'c15-compare'))

# ── CÉLULA 16 — Centroides K=3 vs K=4 ────────────────────────────────────────
cells.append(md("---\n## Etapa 16 — Heatmap Comparativo K=3 vs K=4", 'h16'))
cells.append(code("""
# ============================================================
# CÉLULA 16 — Heatmap Comparativo de Centroides K=3 vs K=4
# ============================================================
fig, axes = plt.subplots(1, 2, figsize=(16, 4))

def plot_heatmap(ax, cent_df, title, k):
    heat = (cent_df - cent_df.min()) / (cent_df.max() - cent_df.min() + 1e-9)
    sns.heatmap(heat.T, annot=cent_df.T.round(2), fmt='.2f',
                cmap='RdYlGn_r', ax=ax, linewidths=0.5,
                cbar_kws={'label': 'Normalizado'}, annot_kws={'size': 9})
    ax.set_title(title, fontsize=11, fontweight='bold')
    ax.set_xticklabels([f'C{c}' for c in range(k)])

plot_heatmap(axes[0], cent_km3, 'K-Means K=3 — Centroides', 3)
plot_heatmap(axes[1], cent_km4, 'K-Means K=4 — Centroides', 4)

plt.suptitle('Comparativo de Centroides — K=3 vs K=4 (valores reais anotados)',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '10_centroides_k3_vs_k4.png', bbox_inches='tight')
plt.show()

# Tabela de diferenças
print('=== Diferença de perfis K=3 vs K=4 ===')
print('K=3 agrega quais perfis?')
print('Centroides K=3 (resumo):')
for c in range(K3):
    imc = cent_km3.loc[c, 'nu_imc'] if 'nu_imc' in cent_km3.columns else '—'
    peso = cent_km3.loc[c, 'nu_peso'] if 'nu_peso' in cent_km3.columns else '—'
    n   = (lbs_km3 == c).sum()
    print(f'  C{c}: IMC={imc:.1f}, Peso={peso:.0f}kg, n={n:,}')

print('\\nCentroides K=4 (resumo):')
for c in range(K4):
    imc = cent_km4.loc[c, 'nu_imc'] if 'nu_imc' in cent_km4.columns else '—'
    peso = cent_km4.loc[c, 'nu_peso'] if 'nu_peso' in cent_km4.columns else '—'
    n   = (lbs_km4 == c).sum()
    print(f'  C{c}: IMC={imc:.1f}, Peso={peso:.0f}kg, n={n:,}')
""", 'c16-heat-compare'))

# ── CÉLULA 17 — Silhouette por cluster ───────────────────────────────────────
cells.append(md("---\n## Etapa 17 — Distribuição Silhouette por Cluster (Violin)", 'h17'))
cells.append(code("""
# ============================================================
# CÉLULA 17 — Silhouette por Cluster — Violin Plot
# ============================================================
# Silhouette individual revela quais clusters têm gestantes
# "mal alocadas" (silhouette < 0) — indica sobreposição local.

N_SIL   = min(15_000, len(X_pca))
idx_sil = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), N_SIL, replace=False)

fig, axes = plt.subplots(1, 2, figsize=(15, 5))

for ax, lbs, k, title, cent in [
    (axes[0], lbs_km3, K3, 'K-Means K=3', cent_km3),
    (axes[1], lbs_km4, K4, 'K-Means K=4', cent_km4),
]:
    sil_vals = silhouette_samples(X_pca[idx_sil], lbs[idx_sil])
    df_sil = pd.DataFrame({'cluster': lbs[idx_sil], 'silhouette': sil_vals})

    parts = ax.violinplot(
        [df_sil[df_sil['cluster'] == c]['silhouette'].values for c in range(k)],
        positions=range(k), showmedians=True, showmeans=False
    )
    for pc in parts['bodies']:
        pc.set_alpha(0.7)
    ax.axhline(0, color='red', linestyle='--', linewidth=1, label='Silhouette=0')
    ax.set_title(f'{title} — Distribuição Silhouette por Cluster', fontsize=10, fontweight='bold')
    ax.set_xlabel('Cluster')
    ax.set_ylabel('Silhouette (amostral)')
    ax.set_xticks(range(k))
    ax.set_xticklabels([f'C{c}\\nn={int((lbs==c).sum()):,}' for c in range(k)], fontsize=8)
    ax.legend(fontsize=8)

    # Médias por cluster
    print(f'\\n{title} — Silhouette médio por cluster:')
    for c in range(k):
        s_c = df_sil[df_sil['cluster'] == c]['silhouette']
        pct_neg = (s_c < 0).mean() * 100
        print(f'  C{c}: média={s_c.mean():.4f} | negativas={pct_neg:.1f}%')

plt.suptitle('Silhouette Individual por Cluster — K=3 vs K=4', fontsize=12, fontweight='bold')
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '11_silhouette_por_cluster.png', bbox_inches='tight')
plt.show()
""", 'c17-violin'))

# ── CÉLULA 18 — Scatter 4 modelos ────────────────────────────────────────────
cells.append(md("---\n## Etapa 18 — Scatter PCA: 4 Modelos (K=4)", 'h18'))
cells.append(code("""
# ============================================================
# CÉLULA 18 — Scatter PCA — 4 Modelos com K=4
# ============================================================
N_SC = min(8_000, len(X_pca))
idx_sc = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), N_SC, replace=False)
X_sc   = X_pca[idx_sc]

modelos_scatter = [
    ('K-Means K=4', lbs_km4),
    ('Agglomerative K=4', lbs_agg4),
    ('GMM K=4', lbs_gmm4),
    ('K-Means K=3', lbs_km3),
]

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
axes = axes.flatten()
CORES_K4 = sns.color_palette('Set1', 4)
CORES_K3 = sns.color_palette('Set2', 3)

for ax, (titulo, lbs) in zip(axes, modelos_scatter):
    k_plot = len(set(lbs))
    cores  = CORES_K3 if k_plot == 3 else CORES_K4
    for c in range(k_plot):
        mask = lbs[idx_sc] == c
        ax.scatter(X_sc[mask, 0], X_sc[mask, 1], s=3, alpha=0.35,
                   color=cores[c], label=f'C{c} ({mask.sum():,})')
    # Centroides PCA
    for c in range(k_plot):
        cx = X_pca[lbs == c, 0].mean()
        cy = X_pca[lbs == c, 1].mean()
        ax.scatter(cx, cy, marker='X', s=180, color='black', zorder=5)
        ax.text(cx, cy + 0.15, f'C{c}', fontsize=9, fontweight='bold', ha='center')
    ax.set_title(titulo, fontsize=11, fontweight='bold')
    ax.set_xlabel(f'PC1 ({pca_full.explained_variance_ratio_[0]*100:.1f}%)')
    ax.set_ylabel(f'PC2 ({pca_full.explained_variance_ratio_[1]*100:.1f}%)')
    ax.legend(fontsize=7, markerscale=3, loc='upper right')

plt.suptitle(f'Comparativo Visual — 4 Modelos no Espaço PCA (n={N_SC:,})',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '12_scatter_4_modelos.png', bbox_inches='tight')
plt.show()
""", 'c18-scatter'))

# ── CÉLULA 19 — Estabilidade ─────────────────────────────────────────────────
cells.append(md("---\n## Etapa 19 — Estabilidade: K=3 vs K=4 (20 Seeds)", 'h19'))
cells.append(code("""
# ============================================================
# CÉLULA 19 — Análise de Estabilidade (20 seeds) — K=3 vs K=4
# ============================================================
N_ST     = min(15_000, len(X_pca))
idx_st   = np.random.RandomState(RANDOM_STATE).choice(len(X_pca), N_ST, replace=False)
X_st     = X_pca[idx_st]
N_SEEDS  = 20

resultados_estab = {3: [], 4: []}

for k_est in [3, 4]:
    print(f'\\nEstabilidade K={k_est} ({N_SEEDS} seeds, n={N_ST:,})...')
    print(f"{'Seed':>4}  {'Silhouette':>10}  {'Inércia':>12}")
    for seed in range(N_SEEDS):
        km_s = KMeans(n_clusters=k_est, init='k-means++', n_init=5, random_state=seed)
        lbs_s = km_s.fit_predict(X_st)
        s = silhouette_score(X_st, lbs_s)
        resultados_estab[k_est].append({'seed': seed, 'silhouette': s,
                                         'inercia': km_s.inertia_})
        print(f'  {seed:>2d}:  {s:.4f}  {km_s.inertia_:>12,.0f}')

for k_est in [3, 4]:
    sils = [r['silhouette'] for r in resultados_estab[k_est]]
    print(f'\\n  K={k_est}: μ={np.mean(sils):.4f}  σ={np.std(sils):.5f}  '
          f'{"ESTÁVEL ✓" if np.std(sils) < 0.005 else "ATENÇÃO ⚠"}')

# Gráfico
fig, axes = plt.subplots(2, 2, figsize=(14, 8))
for row, k_est in enumerate([3, 4]):
    sils   = [r['silhouette'] for r in resultados_estab[k_est]]
    inercs = [r['inercia']    for r in resultados_estab[k_est]]
    mu_s, sd_s = np.mean(sils), np.std(sils)
    mu_i       = np.mean(inercs)

    ax = axes[row, 0]
    ax.plot(range(N_SEEDS), sils, marker='o', color='crimson', linewidth=1.5)
    ax.axhline(mu_s, color='red', linestyle='--',
               label=f'μ={mu_s:.4f} ± σ={sd_s:.5f}')
    ax.fill_between(range(N_SEEDS), mu_s - sd_s, mu_s + sd_s,
                    alpha=0.15, color='crimson')
    ax.set_title(f'Silhouette — K={k_est} (20 seeds)', fontsize=10, fontweight='bold')
    ax.set_xlabel('Seed'); ax.set_ylabel('Silhouette')
    ax.set_xticks(range(N_SEEDS)); ax.legend(fontsize=8)

    ax2 = axes[row, 1]
    ax2.plot(range(N_SEEDS), [i/1e6 for i in inercs], marker='s',
             color='steelblue', linewidth=1.5)
    ax2.axhline(mu_i/1e6, color='steelblue', linestyle='--',
                label=f'μ={mu_i/1e6:.3f}M')
    ax2.set_title(f'Inércia — K={k_est} (20 seeds)', fontsize=10, fontweight='bold')
    ax2.set_xlabel('Seed'); ax2.set_ylabel('Inércia (×10⁶)')
    ax2.set_xticks(range(N_SEEDS)); ax2.legend(fontsize=8)

plt.suptitle('Estabilidade do K-Means — K=3 vs K=4 (20 seeds aleatórios)',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '13_estabilidade_k3_k4.png', bbox_inches='tight')
plt.show()

# Registrar
for k_est in [3, 4]:
    sils = [r['silhouette'] for r in resultados_estab[k_est]]
    REGISTRO.append({
        'Modelo': f'K-Means Estabilidade', 'K': k_est,
        'Silhouette': round(np.mean(sils), 4),
        'Davies-Bouldin': None, 'Calinski-H': None, 'Inércia/BIC': None,
        'Ruído (%)': 0, 'Nota': f'μ={np.mean(sils):.4f} σ={np.std(sils):.5f}'
    })
""", 'c19-stability'))

# ── CÉLULA 20 — Cross-tab K=3 vs K=4 ─────────────────────────────────────────
cells.append(md("---\n## Etapa 20 — Cross-Tabulation K=3 vs K=4", 'h20'))
cells.append(code("""
# ============================================================
# CÉLULA 20 — Cross-Tabulation: como gestantes migram K=3→K=4
# ============================================================
# Mostra quais clusters do K=3 são "quebrados" pelo K=4.
# Clusters do K=4 que surgem de apenas 1 cluster K=3 são subdivisões.
# Clusters do K=4 que misturam dois clusters K=3 são fusões invertidas.

df_cross = pd.DataFrame({'km3': lbs_km3, 'km4': lbs_km4})
tabela_cross = pd.crosstab(df_cross['km3'], df_cross['km4'],
                            margins=True, margins_name='TOTAL')
tabela_pct   = pd.crosstab(df_cross['km3'], df_cross['km4'], normalize='index') * 100

print('=== Cross-Tabulation K=3 × K=4 (contagem) ===')
print(tabela_cross.to_string())

print('\\n=== Cross-Tabulation K=3 × K=4 (% por linha — como K=3 se distribui em K=4) ===')
print(tabela_pct.round(1).to_string())

# Heatmap
fig, axes = plt.subplots(1, 2, figsize=(13, 4))

sns.heatmap(tabela_pct, annot=True, fmt='.1f', cmap='Blues',
            ax=axes[0], linewidths=0.5,
            cbar_kws={'label': '% de C(K=3) em C(K=4)'})
axes[0].set_title('K=3 → K=4: distribuição % (por linha)', fontsize=10, fontweight='bold')
axes[0].set_xlabel('Cluster K=4'); axes[0].set_ylabel('Cluster K=3')

# Contagem normalizada por coluna (como K=4 veio do K=3)
tabela_col = pd.crosstab(df_cross['km3'], df_cross['km4'], normalize='columns') * 100
sns.heatmap(tabela_col, annot=True, fmt='.1f', cmap='Oranges',
            ax=axes[1], linewidths=0.5,
            cbar_kws={'label': '% de C(K=4) vinda de C(K=3)'})
axes[1].set_title('K=4 ← K=3: origem % (por coluna)', fontsize=10, fontweight='bold')
axes[1].set_xlabel('Cluster K=4'); axes[1].set_ylabel('Cluster K=3')

plt.suptitle('Cross-Tabulation: Migração de Gestantes entre K=3 e K=4',
             fontsize=12, fontweight='bold')
plt.tight_layout()
plt.savefig(GRAFICOS_DIR / '14_crosstab_k3_k4.png', bbox_inches='tight')
plt.show()

tabela_cross.to_csv(TABELAS_DIR / 'crosstab_k3_k4.csv')
print('\\n→ Interpretação:')
print('  Uma linha de K=3 com >80% em um único K=4 = subdivisão clara.')
print('  Uma linha de K=3 distribuída em vários K=4 = cluster heterogêneo no K=3.')
""", 'c20-crosstab'))

# ── CÉLULA 21 — Equidade Racial ───────────────────────────────────────────────
cells.append(md("---\n## Etapa 21 — Análise de Equidade Racial", 'h21'))
cells.append(code("""
# ============================================================
# CÉLULA 21 — Análise de Equidade Racial (ambos K=3 e K=4)
# ============================================================
RACA_MAP = {1: 'Branca', 2: 'Preta', 3: 'Amarela', 4: 'Parda', 5: 'Indígena'}

if 'raca_cor' in df_features.columns:
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    for row, (lbs, k, titulo) in enumerate([
        (lbs_km3, K3, 'K-Means K=3'),
        (lbs_km4, K4, 'K-Means K=4'),
    ]):
        df_r = df_features[['raca_cor']].copy()
        df_r['cluster']    = lbs
        df_r['raca_label'] = df_r['raca_cor'].map(RACA_MAP).fillna('Não inf.')

        raca_ct  = pd.crosstab(df_r['cluster'], df_r['raca_label'], normalize='index') * 100
        media_g  = df_r['raca_label'].value_counts(normalize=True) * 100
        razao_df = raca_ct.div(media_g, axis=1).fillna(0)

        raca_ct.plot(kind='bar', stacked=True, ax=axes[row, 0],
                     colormap='Set2', edgecolor='white', linewidth=0.3)
        axes[row, 0].set_title(f'{titulo} — Raça/Cor por Cluster (%)',
                               fontsize=10, fontweight='bold')
        axes[row, 0].set_xlabel('Cluster')
        axes[row, 0].set_ylabel('%')
        axes[row, 0].set_xticklabels([f'C{c}' for c in range(k)], rotation=0)
        axes[row, 0].legend(loc='upper right', fontsize=7)

        sns.heatmap(razao_df.T, annot=True, fmt='.2f', cmap='RdBu_r',
                    center=1.0, ax=axes[row, 1], linewidths=0.5,
                    cbar_kws={'label': 'Razão vs. média geral'},
                    annot_kws={'size': 8})
        axes[row, 1].set_title(f'{titulo} — Razão de Representação\\n(>1=sobrerepresentado)',
                               fontsize=10, fontweight='bold')
        axes[row, 1].set_xticklabels([f'C{c}' for c in range(k)])

        print(f'\\n=== {titulo} — Razão máxima de sobrerepresentação ===')
        for raca in razao_df.columns:
            max_c = razao_df[raca].idxmax()
            max_v = razao_df[raca].max()
            if max_v > 1.15:
                print(f'  {raca:10}: C{max_c} sobrerepresentado {max_v:.2f}×')

    plt.suptitle('Análise de Equidade Racial — K=3 vs K=4', fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(GRAFICOS_DIR / '15_equidade_racial_k3_k4.png', bbox_inches='tight')
    plt.show()
""", 'c21-equity'))

# ── CÉLULA 22 — Geo ───────────────────────────────────────────────────────────
cells.append(md("---\n## Etapa 22 — Análise Geográfica", 'h22'))
cells.append(code("""
# ============================================================
# CÉLULA 22 — Análise Geográfica — K=3 vs K=4
# ============================================================
if 'municipio' in df_features.columns:
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    for ax, (lbs, k, titulo) in zip(axes, [
        (lbs_km3, K3, 'K-Means K=3'),
        (lbs_km4, K4, 'K-Means K=4'),
    ]):
        df_m = df_features[['municipio']].copy()
        df_m['cluster'] = lbs
        mun_ct = df_m.groupby(['municipio', 'cluster']).size().unstack(fill_value=0)
        mun_ct['total'] = mun_ct.sum(axis=1)
        # Filtrar municípios com ≥20 gestantes
        mun_ct = mun_ct[mun_ct['total'] >= 20]

        # Cluster com maior concentração = cluster de maior IMC
        cluster_imc_max = df_features.assign(cluster=lbs).groupby('cluster')['nu_imc'].mean().idxmax()
        col_risco = cluster_imc_max
        if col_risco in mun_ct.columns:
            mun_ct['pct_risco'] = mun_ct[col_risco] / mun_ct['total'] * 100
            top15 = mun_ct.nlargest(15, 'pct_risco')
            top15['pct_risco'].plot(kind='barh', ax=ax, color='crimson', edgecolor='white')
            ax.set_title(f'{titulo}\\nTop 15 municípios (≥20 gest.) — Cluster {col_risco} (maior IMC)',
                         fontsize=9, fontweight='bold')
            ax.set_xlabel('% das gestantes no cluster de maior IMC')
            ax.axvline(50, color='black', linestyle='--', alpha=0.4, label='50%')
            ax.legend(fontsize=8)

    plt.suptitle('Concentração Geográfica — Cluster de Maior IMC por Município',
                 fontsize=12, fontweight='bold')
    plt.tight_layout()
    plt.savefig(GRAFICOS_DIR / '16_geo_municipios_k3_k4.png', bbox_inches='tight')
    plt.show()

    # Distribuição por ano
    if 'ano' in df_features.columns:
        print('\\n=== % por cluster por ano — K=3 ===')
        print(pd.crosstab(df_features['ano'], pd.Series(lbs_km3, name='cluster'),
                          normalize='index').mul(100).round(1).to_string())
        print('\\n=== % por cluster por ano — K=4 ===')
        print(pd.crosstab(df_features['ano'], pd.Series(lbs_km4, name='cluster'),
                          normalize='index').mul(100).round(1).to_string())
""", 'c22-geo'))

# ── CÉLULA 23 — Recomendação ──────────────────────────────────────────────────
cells.append(md("---\n## Etapa 23 — Recomendação Final Fundamentada", 'h23'))
cells.append(code("""
# ============================================================
# CÉLULA 23 — Recomendação Final
# ============================================================
print('=' * 70)
print('  RECOMENDAÇÃO FINAL — BASEADA EM EVIDÊNCIAS')
print('=' * 70)

df_final = pd.DataFrame(REGISTRO)
df_km = df_final[df_final['Modelo'] == 'K-Means'].copy()

r3 = df_km[df_km['K'] == 3].iloc[0]
r4 = df_km[df_km['K'] == 4].iloc[0]

print(f'\\n=== Métricas K-Means K=3 vs K=4 ===')
print(f'  Métrica           K=3         K=4     Vencedor')
print(f'  Silhouette:     {r3.Silhouette:.4f}       {r4.Silhouette:.4f}     {"K=3 ↑" if r3.Silhouette > r4.Silhouette else "K=4 ↑"}')
print(f'  Davies-Bouldin: {r3["Davies-Bouldin"]:.4f}       {r4["Davies-Bouldin"]:.4f}     {"K=3 ↓" if r3["Davies-Bouldin"] < r4["Davies-Bouldin"] else "K=4 ↓"}')
print(f'  Calinski-H:     {r3["Calinski-H"]:>8,.0f}   {r4["Calinski-H"]:>8,.0f}   {"K=3 ↑" if r3["Calinski-H"] > r4["Calinski-H"] else "K=4 ↑"}')
print(f'  Inércia:        {r3["Inércia/BIC"]:>8,.0f}   {r4["Inércia/BIC"]:>8,.0f}   {"K=3 menor" if r3["Inércia/BIC"] < r4["Inércia/BIC"] else "K=4 menor"}')

# Contagem de vitórias
k3_wins = sum([
    r3.Silhouette > r4.Silhouette,
    r3['Davies-Bouldin'] < r4['Davies-Bouldin'],
    r3['Calinski-H'] > r4['Calinski-H'],
])
k4_wins = 3 - k3_wins

print(f'\\nVitórias: K=3: {k3_wins}/3  |  K=4: {k4_wins}/3')

print(f'\\n=== Fatores de Decisão ===')
print('''
Critério                    K=3                         K=4
─────────────────────────────────────────────────────────────────
Métricas internas           Geralmente superior          Levemente inferior
Gap Statistic               Ver resultado Célula 05      Ver resultado Célula 05
GMM BIC                     Ver resultado Célula 13      Ver resultado Célula 13
Utilidade clínica           Perfis mais amplos           Distingue infra urbana
Complexidade operacional    3 alertas distintos          4 alertas distintos
Interpretabilidade          Mais simples                 Mais granular
Tamanho mínimo cluster      > 5%                         C1 = 1.5% (pequeno)
Estabilidade (20 seeds)     σ < 0.005 (ambos)           σ < 0.005 (ambos)
─────────────────────────────────────────────────────────────────
''')

k_recomendado = 3 if k3_wins >= 2 else 4
print(f'→ Recomendação técnica baseada em métricas: K={k_recomendado}')
print(f'→ Para publicação científica: reportar K=3 como principal, K=4 como sensibilidade')
print(f'→ Para uso clínico no app:    discutir com obstetra — ambos são válidos')
print(f'\\nNota: Silhouette < 0.30 é esperado em dados epidemiológicos contínuos.')
print(f'Não existe K "errado" — a escolha depende do objetivo operacional.')
""", 'c23-recommend'))

# ── CÉLULA 24 — Export ────────────────────────────────────────────────────────
cells.append(md("---\n## Etapa 24 — Exportação de Artefatos", 'h24'))
cells.append(code("""
# ============================================================
# CÉLULA 24 — Exportação Completa
# ============================================================
# Parquets com ambas as soluções
df_out = df_features.copy()
df_out['cluster_km3'] = lbs_km3
df_out['cluster_km4'] = lbs_km4
df_out['cluster_agg3'] = lbs_agg3
df_out['cluster_agg4'] = lbs_agg4
df_out['cluster_gmm3'] = lbs_gmm3
df_out['cluster_gmm4'] = lbs_gmm4
df_out.to_parquet(OUTPUT_DIR / 'gestante_todos_clusters.parquet', index=False)
print(f'✓ gestante_todos_clusters.parquet ({len(df_out):,} registros, {df_out.shape[1]} colunas)')

# Modelos já salvos — confirmar
modelos_salvos = list(MODELOS_DIR.glob('*.pkl'))
print(f'\\n✓ Modelos salvos ({len(modelos_salvos)}):')
for m in sorted(modelos_salvos): print(f'   {m.name}')

# Tabelas
tabelas_salvas = list(TABELAS_DIR.glob('*.csv'))
print(f'\\n✓ Tabelas salvas ({len(tabelas_salvas)}):')
for t in sorted(tabelas_salvas): print(f'   {t.name}')

# Gráficos
graficos_salvos = list(GRAFICOS_DIR.glob('*.png'))
print(f'\\n✓ Gráficos gerados ({len(graficos_salvos)}):')
for g in sorted(graficos_salvos): print(f'   {g.name}')

# Tabela final no PostgreSQL (K=3 e K=4)
print('\\nAtualizando PostgreSQL...')
try:
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        for col in ['cluster_km3', 'cluster_km4']:
            cur.execute(f'''
                ALTER TABLE ml_maternar.gestante_features
                ADD COLUMN IF NOT EXISTS {col} SMALLINT;
            ''')
        cur.execute('''
            ALTER TABLE ml_maternar.gestante_features
            ADD COLUMN IF NOT EXISTS _rn SERIAL;
        ''')
        conn.commit()
        for col, lbs in [('cluster_km3', lbs_km3), ('cluster_km4', lbs_km4)]:
            PAGE = 5000
            for start in range(0, len(lbs), PAGE):
                batch = [(int(lbs[i]), start + i + 1)
                         for i in range(min(PAGE, len(lbs) - start))]
                execute_values(cur,
                    f"UPDATE ml_maternar.gestante_features AS g "
                    f"SET {col} = v.c FROM (VALUES %s) AS v(c, rn) WHERE g._rn = v.rn",
                    batch)
            conn.commit()
        cur.execute("ALTER TABLE ml_maternar.gestante_features DROP COLUMN IF EXISTS _rn;")
        conn.commit()
    conn.close()
    print(f'✓ PostgreSQL: cluster_km3 e cluster_km4 atualizados ({len(lbs_km3):,} registros)')
except Exception as e:
    print(f'⚠ PostgreSQL: {e}')

FIM = datetime.now()
print(f'\\nDuração total: {(FIM - INICIO).seconds // 60}min {(FIM - INICIO).seconds % 60}s')
""", 'c24-export'))

# ── CÉLULA 25 — Relatório ─────────────────────────────────────────────────────
cells.append(md("""
---

# Relatório Final — KDD Maternar Research

## 1. Dataset

| Item | Valor |
|------|-------|
| Gestantes | 378.969 |
| Features originais | 20 |
| Componentes PCA (90%) | 8 |
| Período | 2014–2016 |
| Fontes | SISVAN, SINAN, SIM, SIA, CNES |

---

## 2. Modelos Avaliados

| Modelo | K=3 | K=4 |
|--------|-----|-----|
| K-Means | ✓ | ✓ |
| Mini-Batch K-Means | ✓ | ✓ |
| Agglomerative Ward | ✓ | ✓ |
| GMM (full covariance) | ✓ | ✓ |
| DBSCAN | automático | — |

---

## 3. Métricas Registradas

| Métrica | Fórmula/Referência |
|---------|-------------------|
| Silhouette Score | Rousseeuw (1987) |
| Calinski-Harabász | Caliński & Harabasz (1974) |
| Davies-Bouldin | Davies & Bouldin (1979) |
| Inércia (WCSS) | Soma de distâncias² intra-cluster |
| BIC/AIC | Critério de informação (GMM) |
| Gap Statistic | Tibshirani et al. (2001) |
| Estabilidade σ | Desvio padrão do Silhouette em 20 seeds |

---

## 4. Artefatos

```
clustering_research_output/
├── graficos/
│   ├── 01_pca_variancia.png
│   ├── 02_scan_k2_10_metricas.png
│   ├── 03_gap_statistic.png
│   ├── 04_dendrograma_ward.png
│   ├── 05_dbscan_kdistancia.png
│   ├── 06_kmeans_k3_centroides.png
│   ├── 07_kmeans_k4_centroides.png
│   ├── 08_gmm_bic_aic.png
│   ├── 09_comparativo_modelos.png
│   ├── 10_centroides_k3_vs_k4.png
│   ├── 11_silhouette_por_cluster.png
│   ├── 12_scatter_4_modelos.png
│   ├── 13_estabilidade_k3_k4.png
│   ├── 14_crosstab_k3_k4.png
│   ├── 15_equidade_racial_k3_k4.png
│   └── 16_geo_municipios_k3_k4.png
├── modelos/
│   ├── kmeans_k3.pkl / kmeans_k4.pkl
│   ├── agg_ward_k3.pkl / agg_ward_k4.pkl
│   ├── gmm_k3.pkl / gmm_k4.pkl
│   └── minibatch_km_3.pkl / minibatch_km_4.pkl
├── tabelas/
│   ├── scan_k2_k10.csv
│   ├── gap_statistic.csv
│   ├── comparativo_geral.csv
│   ├── crosstab_k3_k4.csv
│   └── centroides_*.csv (6 arquivos)
└── gestante_todos_clusters.parquet
```

---

## 5. Referências

- Rousseeuw, P.J. (1987). Silhouettes: a graphical aid to the interpretation and validation of cluster analysis. *Journal of Computational and Applied Mathematics*, 20, 53–65.
- Caliński, T. & Harabasz, J. (1974). A dendrite method for cluster analysis. *Communications in Statistics*, 3(1), 1–27.
- Davies, D.L. & Bouldin, D.W. (1979). A cluster separation measure. *IEEE TPAMI*, 1(2), 224–227.
- Tibshirani, R., Walther, G. & Hastie, T. (2001). Estimating the number of clusters in a data set via the gap statistic. *JRSS-B*, 63(2), 411–423.

---

*Gerado por `KDD_Maternar_Research.ipynb` — Projeto Maternar*
""", 'c25-report'))

# ── Montar notebook ───────────────────────────────────────────────────────────
nb.cells = cells
nb.metadata['kernelspec'] = {
    'display_name': 'Python 3',
    'language': 'python',
    'name': 'python3',
}
nb.metadata['language_info'] = {
    'name': 'python',
    'version': '3.12.0',
}

out = '/home/gabriel/WebstormProjects/Pi6dsmdenovo/ApiDatasus/KDD_Maternar_Research.ipynb'
with open(out, 'w', encoding='utf-8') as f:
    nbf.write(nb, f)

print(f'Notebook gerado: {out}')
print(f'Total de células: {len(nb.cells)}')
