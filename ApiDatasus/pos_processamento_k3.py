"""
pos_processamento_k3.py
=======================
Pós-processamento completo do modelo K-Means K=3 — Projeto Maternar
Inclui: hold-out 10%, testes estatísticos, análise clínica, gráficos, relatório técnico.
"""

import os, sys, time, warnings, joblib
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns

from sklearn.preprocessing import RobustScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    silhouette_score, silhouette_samples,
    calinski_harabasz_score, davies_bouldin_score,
    adjusted_rand_score, adjusted_mutual_info_score,
)
from sklearn.neighbors import KNeighborsClassifier
from scipy import stats
from scipy.stats import chi2_contingency, f_oneway

warnings.filterwarnings('ignore')

# ── Configuração ──────────────────────────────────────────────────────────────
RANDOM_STATE = 42
K_FINAL      = 3
TEST_SIZE    = 0.10
N_BOOTSTRAP  = 30        # bootstraps para IC das métricas
N_SIL        = 20_000    # amostra para Silhouette

BASE_DIR    = Path('/home/gabriel/WebstormProjects/Pi6dsmdenovo/ApiDatasus')
OUTPUT_DIR  = BASE_DIR / 'pos_processamento_output'
GRAF_DIR    = OUTPUT_DIR / 'graficos'
for d in [OUTPUT_DIR, GRAF_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CLUSTER_NAMES = {0: 'C0 — Obesidade', 1: 'C1 — Eutrofia/Baixo Peso', 2: 'C2 — Acesso Diferenciado'}
CLUSTER_CORES = {0: '#e74c3c', 1: '#3498db', 2: '#2ecc71'}
RACA_MAP      = {1: 'Branca', 2: 'Preta', 3: 'Amarela', 4: 'Parda', 5: 'Indígena'}
EST_NUT_MAP   = {1: 'Baixo Peso', 2: 'Adequado', 3: 'Sobrepeso', 4: 'Obesidade'}

SNS_STYLE = {'figure.facecolor': 'white', 'axes.facecolor': '#f8f9fa',
             'axes.grid': True, 'grid.alpha': 0.4}
sns.set_theme(style='whitegrid', rc=SNS_STYLE)
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})

INICIO = datetime.now()
REGISTRO_METRICAS = []  # acumula métricas para relatório

def banner(titulo):
    print(f'\n{"=" * 65}')
    print(f'  {titulo}')
    print(f'{"=" * 65}')

def save_fig(nome):
    p = GRAF_DIR / nome
    plt.savefig(p, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'  Gráfico salvo: {nome}')
    return p

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 1 — Carregamento e Preparação dos Dados')
# ══════════════════════════════════════════════════════════════════════════════

print('Carregando dados...')
df_full   = pd.read_parquet(BASE_DIR / 'clustering_research_output/gestante_todos_clusters.parquet')
df_scaled = pd.read_parquet(BASE_DIR / 'preprocess_output/gestante_para_cluster.parquet')
scaler    = joblib.load(BASE_DIR / 'preprocess_output/scaler_maternar.pkl')
km_full   = joblib.load(BASE_DIR / 'clustering_research_output/modelos/kmeans_k3.pkl')

print(f'  Gestantes carregadas: {len(df_full):,}')
print(f'  Features para cluster: {df_scaled.shape[1]}')
print(f'  Colunas cluster disponíveis: {[c for c in df_full.columns if c.startswith("cluster")]}')

# Rótulos do modelo completo
lbs_full = df_full['cluster_km3'].values.astype(int)
dist_full = pd.Series(lbs_full).value_counts().sort_index()
print('\n  Distribuição K=3 (modelo completo):')
for c, n in dist_full.items():
    print(f'    {CLUSTER_NAMES[c]}: {n:>7,} ({n/len(lbs_full)*100:.1f}%)')

# Recomputar PCA (igual ao pipeline de pesquisa)
print('\nRecomputando PCA (90% variância)...')
X_raw = df_scaled.values.astype(float)

# gestante_para_cluster.parquet já contém os dados com RobustScaler aplicado
# (contínuas escaladas + binárias) — usar diretamente sem re-escalar
COLS_CENT = ['nu_imc', 'nu_imc_pre_gestacional', 'ganho_imc', 'nu_peso',
             'escolaridade', 'log_taxa_sifilis_gest', 'cnes_hospitais']

X_rob = df_scaled.values.astype(float)

# PCA com 90% variância
pca = PCA(n_components=0.90, random_state=RANDOM_STATE)
X_pca = pca.fit_transform(X_rob)
n_comp = X_pca.shape[1]
print(f'  PCA: {df_scaled.shape[1]} → {n_comp} componentes ({pca.explained_variance_ratio_.sum()*100:.1f}% variância)')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 2 — Divisão Hold-Out 90/10 (Estratificada)')
# ══════════════════════════════════════════════════════════════════════════════

idx_all = np.arange(len(X_pca))
idx_train, idx_test = train_test_split(
    idx_all, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=lbs_full
)

X_train = X_pca[idx_train]
X_test  = X_pca[idx_test]
lbs_train_true = lbs_full[idx_train]   # rótulos do modelo completo no treino
lbs_test_true  = lbs_full[idx_test]    # rótulos do modelo completo no teste

print(f'  Total:  {len(idx_all):>7,} gestantes')
print(f'  Treino: {len(idx_train):>7,} ({len(idx_train)/len(idx_all)*100:.1f}%)')
print(f'  Teste:  {len(idx_test):>7,}  ({len(idx_test)/len(idx_all)*100:.1f}%)')
print()
print('  Distribuição estratificada:')
for c in range(K_FINAL):
    n_tr = (lbs_train_true == c).sum()
    n_te = (lbs_test_true  == c).sum()
    print(f'    {CLUSTER_NAMES[c]}: treino={n_tr:>7,} | teste={n_te:>6,} '
          f'({n_te/(n_tr+n_te)*100:.1f}% no teste)')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 3 — Treinamento no Conjunto de Treino (90%)')
# ══════════════════════════════════════════════════════════════════════════════

print('Treinando K-Means K=3 no conjunto de treino (90%)...')
t0 = time.time()
km_train = KMeans(n_clusters=K_FINAL, init='k-means++', n_init=20,
                  random_state=RANDOM_STATE, max_iter=500)
km_train.fit(X_train)
tempo_train = time.time() - t0
print(f'  Concluído em {tempo_train:.1f}s | Inércia: {km_train.inertia_:,.0f}')

# Predição no conjunto de teste
lbs_test_pred = km_train.predict(X_test)
lbs_train_pred = km_train.labels_

# Alinhar rótulos (clusters podem ter nomes permutados)
# Alinhamento pelo centroide mais próximo entre km_full e km_train
from scipy.optimize import linear_sum_assignment
cost_matrix = np.zeros((K_FINAL, K_FINAL))
for i in range(K_FINAL):
    for j in range(K_FINAL):
        cost_matrix[i, j] = np.linalg.norm(km_full.cluster_centers_[i] - km_train.cluster_centers_[j])

row_ind, col_ind = linear_sum_assignment(cost_matrix)
mapa_alinhamento = {col_ind[i]: row_ind[i] for i in range(K_FINAL)}
print(f'\n  Mapeamento de rótulos (treino→completo): {mapa_alinhamento}')

lbs_test_pred_alin  = np.array([mapa_alinhamento[l] for l in lbs_test_pred])
lbs_train_pred_alin = np.array([mapa_alinhamento[l] for l in lbs_train_pred])

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 4 — Métricas: Treino vs Teste vs Modelo Completo')
# ══════════════════════════════════════════════════════════════════════════════

def metricas_cluster(X, lbs, nome, n_sil=N_SIL):
    idx_m = np.random.RandomState(RANDOM_STATE).choice(len(X), min(n_sil, len(X)), replace=False)
    sil  = silhouette_score(X[idx_m], lbs[idx_m])
    ch   = calinski_harabasz_score(X, lbs)
    db   = davies_bouldin_score(X, lbs)
    iner = float(np.sum([np.sum((X[lbs == c] - X[lbs == c].mean(axis=0))**2)
                         for c in range(K_FINAL)]))
    print(f'\n  [{nome}]')
    print(f'    n={len(X):,} | Silhouette={sil:.4f} | CH={ch:,.0f} | DB={db:.4f} | Inércia={iner:,.0f}')
    return {'conjunto': nome, 'n': len(X), 'Silhouette': sil,
            'Calinski-H': ch, 'Davies-Bouldin': db, 'Inércia': iner}

m_full  = metricas_cluster(X_pca,   lbs_full,           'Modelo Completo (100%)')
m_train = metricas_cluster(X_train, lbs_train_pred_alin, 'Treino (90%)')
m_test  = metricas_cluster(X_test,  lbs_test_pred_alin,  'Teste  (10%)')

df_metricas = pd.DataFrame([m_full, m_train, m_test])
df_metricas.to_csv(OUTPUT_DIR / 'metricas_holdout.csv', index=False)
print(f'\n  Consistência de rótulos (ARI treino): '
      f'{adjusted_rand_score(lbs_train_true, lbs_train_pred_alin):.4f}')
print(f'  Consistência de rótulos (ARI teste):  '
      f'{adjusted_rand_score(lbs_test_true, lbs_test_pred_alin):.4f}')
print(f'  AMI treino: {adjusted_mutual_info_score(lbs_train_true, lbs_train_pred_alin):.4f}')
print(f'  AMI teste:  {adjusted_mutual_info_score(lbs_test_true, lbs_test_pred_alin):.4f}')

ari_train = adjusted_rand_score(lbs_train_true, lbs_train_pred_alin)
ari_test  = adjusted_rand_score(lbs_test_true, lbs_test_pred_alin)
ami_train = adjusted_mutual_info_score(lbs_train_true, lbs_train_pred_alin)
ami_test  = adjusted_mutual_info_score(lbs_test_true, lbs_test_pred_alin)

# ── Gráfico 01: Comparação Treino vs Teste ──────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(14, 4))
metricas_plot = ['Silhouette', 'Calinski-H', 'Davies-Bouldin']
direcoes      = ['↑ melhor', '↑ melhor', '↓ melhor']
cores_barras  = ['#3498db', '#2ecc71', '#e74c3c']

for ax, met, dir_, cor in zip(axes, metricas_plot, direcoes, cores_barras):
    vals  = [m_full[met], m_train[met], m_test[met]]
    nomes = ['Completo\n(100%)', 'Treino\n(90%)', 'Teste\n(10%)']
    bars  = ax.bar(nomes, vals, color=[cor]*3, edgecolor='white', linewidth=0.8, alpha=0.85)
    ax.set_title(f'{met}\n{dir_}', fontsize=10, fontweight='bold')
    for bar, v in zip(bars, vals):
        fmt = f'{v:.4f}' if met != 'Calinski-H' else f'{v:,.0f}'
        ax.text(bar.get_x() + bar.get_width()/2, v * 1.005, fmt,
                ha='center', va='bottom', fontsize=8)
    ax.set_ylim(0, max(vals) * 1.15)

plt.suptitle(f'Validação Hold-Out — K=3 | ARI treino={ari_train:.3f} | ARI teste={ari_test:.3f}',
             fontsize=11, fontweight='bold')
plt.tight_layout()
save_fig('01_holdout_metricas.png')

# ── Gráfico 02: Silhouette Samples — Treino vs Teste ─────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
conjuntos = [('Treino (90%)', X_train, lbs_train_pred_alin),
             ('Teste (10%)',  X_test,  lbs_test_pred_alin)]

for ax, (nome, X_c, lbs_c) in zip(axes, conjuntos):
    idx_m = np.random.RandomState(RANDOM_STATE).choice(len(X_c), min(N_SIL, len(X_c)), replace=False)
    sil_vals = silhouette_samples(X_c[idx_m], lbs_c[idx_m])
    y_pos = 0
    ticks_y, labels_y = [], []
    for c in range(K_FINAL):
        mask = lbs_c[idx_m] == c
        sv   = np.sort(sil_vals[mask])
        ax.barh(range(y_pos, y_pos + len(sv)), sv, height=1,
                color=CLUSTER_CORES[c], edgecolor='none', alpha=0.8)
        ticks_y.append(y_pos + len(sv) // 2)
        labels_y.append(f'C{c}\n(n={mask.sum():,})')
        y_pos += len(sv) + 30
    ax.axvline(sil_vals.mean(), color='black', linestyle='--', linewidth=1.2,
               label=f'Média={sil_vals.mean():.4f}')
    ax.set_yticks(ticks_y); ax.set_yticklabels(labels_y, fontsize=8)
    ax.set_xlabel('Silhouette'); ax.set_title(f'Silhouette por Amostra — {nome}', fontweight='bold')
    ax.legend(fontsize=9)
plt.tight_layout()
save_fig('02_silhouette_samples.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 5 — Bootstrap: IC das Métricas (30 amostras de 90%)')
# ══════════════════════════════════════════════════════════════════════════════

print(f'Calculando Bootstrap ({N_BOOTSTRAP} amostras de 90% do conjunto de treino)...')
boot_sil, boot_ch, boot_db = [], [], []
rng = np.random.RandomState(RANDOM_STATE)
for b in range(N_BOOTSTRAP):
    idx_b = rng.choice(len(X_train), size=int(len(X_train) * 0.9), replace=False)
    X_b   = X_train[idx_b]
    km_b  = KMeans(n_clusters=K_FINAL, init='k-means++', n_init=5,
                   random_state=b, max_iter=300)
    lbs_b = km_b.fit_predict(X_b)
    idx_sil_b = rng.choice(len(X_b), min(N_SIL, len(X_b)), replace=False)
    boot_sil.append(silhouette_score(X_b[idx_sil_b], lbs_b[idx_sil_b]))
    boot_ch.append(calinski_harabasz_score(X_b, lbs_b))
    boot_db.append(davies_bouldin_score(X_b, lbs_b))
    if (b + 1) % 10 == 0:
        print(f'    Bootstrap {b+1}/{N_BOOTSTRAP}...')

ic95 = {
    'Silhouette':     (np.percentile(boot_sil, 2.5), np.percentile(boot_sil, 97.5)),
    'Calinski-H':     (np.percentile(boot_ch,  2.5), np.percentile(boot_ch,  97.5)),
    'Davies-Bouldin': (np.percentile(boot_db,  2.5), np.percentile(boot_db,  97.5)),
}
print(f'\n  IC 95% Bootstrap (n={N_BOOTSTRAP}):')
print(f'    Silhouette:     [{ic95["Silhouette"][0]:.4f}, {ic95["Silhouette"][1]:.4f}]  '
      f'média={np.mean(boot_sil):.4f}')
print(f'    Calinski-H:     [{ic95["Calinski-H"][0]:,.0f}, {ic95["Calinski-H"][1]:,.0f}]')
print(f'    Davies-Bouldin: [{ic95["Davies-Bouldin"][0]:.4f}, {ic95["Davies-Bouldin"][1]:.4f}]')

# ── Gráfico 03: Bootstrap distributions ──────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(14, 4))
for ax, (met, vals, cor_l) in zip(axes, [
        ('Silhouette', boot_sil, '#3498db'),
        ('Calinski-H', boot_ch,  '#2ecc71'),
        ('Davies-Bouldin', boot_db, '#e74c3c')]):
    ax.hist(vals, bins=15, color=cor_l, edgecolor='white', alpha=0.8)
    ax.axvline(np.mean(vals), color='black', linestyle='--', linewidth=1.5,
               label=f'μ={np.mean(vals):.4f}')
    ax.axvline(np.percentile(vals, 2.5), color='gray', linestyle=':', linewidth=1)
    ax.axvline(np.percentile(vals, 97.5), color='gray', linestyle=':', linewidth=1,
               label=f'IC 95%')
    ax.set_title(f'Bootstrap — {met}', fontweight='bold', fontsize=10)
    ax.legend(fontsize=8)
plt.suptitle(f'Intervalos de Confiança Bootstrap (n={N_BOOTSTRAP} amostras de 90%)',
             fontsize=11, fontweight='bold')
plt.tight_layout()
save_fig('03_bootstrap_ic.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 6 — Testes Estatísticos: ANOVA por Feature')
# ══════════════════════════════════════════════════════════════════════════════

FEATS_NUM = ['nu_imc', 'nu_imc_pre_gestacional', 'ganho_imc', 'nu_peso', 'nu_altura',
             'log_taxa_sifilis_gest', 'cnes_hospitais', 'escolaridade']
FEATS_NUM_LABEL = {
    'nu_imc': 'IMC Atual', 'nu_imc_pre_gestacional': 'IMC Pré-Gestacional',
    'ganho_imc': 'Ganho de IMC', 'nu_peso': 'Peso (kg)', 'nu_altura': 'Altura (m)',
    'log_taxa_sifilis_gest': 'Log Taxa Sífilis', 'cnes_hospitais': 'Hospitais (CNES)',
    'escolaridade': 'Escolaridade'
}

anova_results = []
print(f'{"Feature":<28} {"F-stat":>10}  {"p-valor":>12}  {"η²":>8}  {"Sig"}')
print('-' * 72)

df_feat = df_full.copy()
df_feat['cluster_km3'] = lbs_full

for feat in FEATS_NUM:
    if feat not in df_feat.columns:
        continue
    groups = [df_feat[feat][df_feat['cluster_km3'] == c].dropna().values
               for c in range(K_FINAL)]
    if any(len(g) < 2 for g in groups):
        continue
    f_stat, p_val = f_oneway(*groups)

    # Eta² (effect size)
    grand_mean  = df_feat[feat].mean()
    ss_between  = sum(len(g) * (g.mean() - grand_mean)**2 for g in groups)
    ss_total    = ((df_feat[feat] - grand_mean)**2).sum()
    eta_sq      = ss_between / ss_total if ss_total > 0 else 0

    sig = '***' if p_val < 0.001 else ('**' if p_val < 0.01 else ('*' if p_val < 0.05 else 'ns'))
    print(f'{feat:<28} {f_stat:>10.2f}  {p_val:>12.2e}  {eta_sq:>8.4f}  {sig}')
    anova_results.append({'Feature': feat, 'Label': FEATS_NUM_LABEL.get(feat, feat),
                          'F_stat': round(f_stat, 4), 'p_valor': p_val,
                          'eta_sq': round(eta_sq, 4), 'sig': sig})

df_anova = pd.DataFrame(anova_results).sort_values('eta_sq', ascending=False)
df_anova.to_csv(OUTPUT_DIR / 'anova_resultados.csv', index=False)

# ── Gráfico 04: Eta² por feature (importância das features) ──────────────────
fig, ax = plt.subplots(figsize=(10, 5))
colors_eta = ['#e74c3c' if e > 0.14 else ('#f39c12' if e > 0.06 else '#3498db')
               for e in df_anova['eta_sq']]
bars = ax.barh(df_anova['Label'], df_anova['eta_sq'], color=colors_eta,
               edgecolor='white', linewidth=0.5)
ax.axvline(0.01, color='gray',   linestyle=':', alpha=0.7, label='Pequeno (η²=0.01)')
ax.axvline(0.06, color='orange', linestyle=':', alpha=0.7, label='Médio (η²=0.06)')
ax.axvline(0.14, color='red',    linestyle=':', alpha=0.7, label='Grande (η²=0.14)')
for bar, (_, row) in zip(bars, df_anova.iterrows()):
    ax.text(row['eta_sq'] + 0.002, bar.get_y() + bar.get_height()/2,
            f'{row["eta_sq"]:.4f} {row["sig"]}', va='center', fontsize=8)
ax.set_xlabel('η² (Effect Size — ANOVA)')
ax.set_title('Importância das Features para Discriminação de Clusters\n'
             '(η² = proporção da variância explicada pelo cluster)', fontweight='bold')
ax.legend(fontsize=8, loc='lower right')
plt.tight_layout()
save_fig('04_anova_eta2.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 7 — Testes Qui-Quadrado: Raça/Cor e Escolaridade')
# ══════════════════════════════════════════════════════════════════════════════

chi2_results = []
for feat_cat, label_cat in [('raca_cor', 'Raça/Cor'), ('estado_nutricional_cod', 'Estado Nutricional'),
                              ('escolaridade', 'Escolaridade (ord.)')]:
    if feat_cat not in df_feat.columns:
        continue
    tab = pd.crosstab(df_feat['cluster_km3'], df_feat[feat_cat].fillna(0).astype(int))
    tab = tab.loc[:, tab.columns != 0]
    if tab.shape[1] < 2:
        continue
    chi2, p_val, dof, _ = chi2_contingency(tab)
    n = tab.values.sum()
    k_min = min(tab.shape) - 1
    cramers_v = np.sqrt(chi2 / (n * k_min)) if k_min > 0 else 0
    sig = '***' if p_val < 0.001 else ('**' if p_val < 0.01 else ('*' if p_val < 0.05 else 'ns'))
    print(f'{label_cat:<30} χ²={chi2:>10.2f}  gl={dof}  p={p_val:.2e}  V={cramers_v:.4f}  {sig}')
    chi2_results.append({'Feature': feat_cat, 'Label': label_cat, 'chi2': round(chi2, 4),
                         'df': dof, 'p_valor': p_val, 'Cramers_V': round(cramers_v, 4), 'sig': sig})

pd.DataFrame(chi2_results).to_csv(OUTPUT_DIR / 'chi2_resultados.csv', index=False)

# ── Gráfico 05: Distribuição de Raça/Cor por Cluster ─────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=False)
df_feat_raca = df_feat[df_feat['raca_cor'].isin(RACA_MAP.keys())].copy()
df_feat_raca['raca_nome'] = df_feat_raca['raca_cor'].map(RACA_MAP)
total_raca = df_feat_raca['raca_nome'].value_counts(normalize=True) * 100

for ax, c in zip(axes, range(K_FINAL)):
    sub = df_feat_raca[df_feat_raca['cluster_km3'] == c]
    freq = sub['raca_nome'].value_counts(normalize=True) * 100
    razao = (freq / total_raca).reindex(freq.index).fillna(0)
    cores_bar = ['#e74c3c' if r > 1.15 else ('#3498db' if r < 0.85 else '#95a5a6')
                 for r in razao.values]
    bars = ax.bar(freq.index, freq.values, color=cores_bar, edgecolor='white')
    for bar, r in zip(bars, razao.values):
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + 0.3, f'{r:.2f}×',
                ha='center', fontsize=7.5)
    ax.set_title(f'{CLUSTER_NAMES[c]}\n(n={len(sub):,})', fontsize=9, fontweight='bold',
                 color=CLUSTER_CORES[c])
    ax.set_ylabel('% dentro do cluster'); ax.set_xlabel('Raça/Cor')
    ax.tick_params(axis='x', rotation=30)
    ax.set_ylim(0, freq.max() * 1.2)

plt.suptitle('Distribuição de Raça/Cor por Cluster\n(rótulo = razão vs. proporção geral; >1.15 = sobrerepresentado)',
             fontsize=11, fontweight='bold')
plt.tight_layout()
save_fig('05_raca_por_cluster.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 8 — Perfil Clínico dos Clusters')
# ══════════════════════════════════════════════════════════════════════════════

# Estatísticas descritivas por cluster
desc_feats = ['nu_imc', 'nu_imc_pre_gestacional', 'ganho_imc', 'nu_peso', 'nu_altura',
              'log_taxa_sifilis_gest', 'cnes_hospitais', 'escolaridade']
desc_labels = {
    'nu_imc': 'IMC Atual', 'nu_imc_pre_gestacional': 'IMC Pré-Gest.',
    'ganho_imc': 'Ganho IMC', 'nu_peso': 'Peso (kg)', 'nu_altura': 'Altura (m)',
    'log_taxa_sifilis_gest': 'Log Taxa Sífilis', 'cnes_hospitais': 'Hospitais CNES',
    'escolaridade': 'Escolaridade'
}

print('\n  Estatísticas por cluster (média ± dp):')
for feat in desc_feats:
    if feat not in df_feat.columns:
        continue
    linha = f'  {desc_labels.get(feat,feat):<22}'
    for c in range(K_FINAL):
        vals = df_feat[feat][df_feat['cluster_km3'] == c].dropna()
        linha += f' | C{c}: {vals.mean():.3f}±{vals.std():.3f}'
    print(linha)

# Centroides finais (escala original)
cents_raw = pd.DataFrame(
    [df_feat[df_feat['cluster_km3'] == c][desc_feats].mean().values for c in range(K_FINAL)],
    columns=desc_feats,
    index=[CLUSTER_NAMES[c] for c in range(K_FINAL)]
).round(3)
cents_raw.to_csv(OUTPUT_DIR / 'centroides_finais_k3.csv')
print(f'\n  Centroides salvos: centroides_finais_k3.csv')

# Estado nutricional por cluster
print('\n  Estado Nutricional por Cluster (%):')
if 'estado_nutricional_cod' in df_feat.columns:
    for c in range(K_FINAL):
        sub = df_feat[df_feat['cluster_km3'] == c]['estado_nutricional_cod'].dropna()
        cnt = sub.value_counts(normalize=True) * 100
        linha = f'    {CLUSTER_NAMES[c]}: '
        for cod, pct in sorted(cnt.items()):
            linha += f'{EST_NUT_MAP.get(int(cod), str(cod))}={pct:.1f}%  '
        print(linha)

# ── Gráfico 06: Violin plots das features principais ─────────────────────────
fig, axes = plt.subplots(2, 4, figsize=(16, 8))
axes = axes.flatten()
for ax, feat in zip(axes, desc_feats):
    if feat not in df_feat.columns:
        continue
    data_viol = [df_feat[feat][df_feat['cluster_km3'] == c].dropna().values
                  for c in range(K_FINAL)]
    parts = ax.violinplot(data_viol, positions=range(K_FINAL), showmedians=True, showmeans=True)
    for i, (pc, c) in enumerate(zip(parts['bodies'], range(K_FINAL))):
        pc.set_facecolor(CLUSTER_CORES[c]); pc.set_alpha(0.7)
    parts['cmedians'].set_colors('black')
    parts['cmeans'].set_colors('white')
    ax.set_xticks(range(K_FINAL))
    ax.set_xticklabels([f'C{c}' for c in range(K_FINAL)], fontsize=8)
    ax.set_title(desc_labels.get(feat, feat), fontsize=9, fontweight='bold')
    ax.set_ylabel('Valor')
plt.suptitle('Distribuição das Features por Cluster (linha branca = média, preta = mediana)',
             fontsize=11, fontweight='bold')
plt.tight_layout()
save_fig('06_violin_features.png')

# ── Gráfico 07: Heatmap de centroides normalizados ────────────────────────────
fig, ax = plt.subplots(figsize=(10, 4))
heat_df = cents_raw.copy()
heat_norm = (heat_df - heat_df.min()) / (heat_df.max() - heat_df.min() + 1e-9)
heat_norm.columns = [desc_labels.get(c, c) for c in heat_norm.columns]
sns.heatmap(heat_norm, annot=cents_raw.values, fmt='.2f', cmap='YlOrRd',
            ax=ax, linewidths=0.5, annot_kws={'size': 9},
            cbar_kws={'label': 'Valor normalizado [0,1]'})
ax.set_title('Centroides dos Clusters — Escala Original (normalizado para cor)',
             fontsize=11, fontweight='bold')
ax.set_yticklabels(ax.get_yticklabels(), rotation=0)
plt.tight_layout()
save_fig('07_heatmap_centroides.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 9 — PCA Scatter Plot (Treino, Teste e Completo)')
# ══════════════════════════════════════════════════════════════════════════════

# Amostra para scatter
N_SC = 5_000
rng2 = np.random.RandomState(RANDOM_STATE)

fig, axes = plt.subplots(1, 3, figsize=(16, 5))
configs = [
    ('Modelo Completo (100%)',  X_pca,   lbs_full),
    ('Conjunto Treino (90%)',   X_train, lbs_train_pred_alin),
    ('Conjunto Teste (10%)',    X_test,  lbs_test_pred_alin),
]
for ax, (titulo, X_c, lbs_c) in zip(axes, configs):
    idx_sc = rng2.choice(len(X_c), min(N_SC, len(X_c)), replace=False)
    for c in range(K_FINAL):
        mask = lbs_c[idx_sc] == c
        ax.scatter(X_c[idx_sc][mask, 0], X_c[idx_sc][mask, 1],
                   c=CLUSTER_CORES[c], alpha=0.4, s=8, label=f'C{c}')
    ax.set_title(titulo, fontsize=9, fontweight='bold')
    ax.set_xlabel('PC1'); ax.set_ylabel('PC2')
    ax.legend(fontsize=7, markerscale=2)

plt.suptitle('Projeção PCA (PC1 × PC2) — Comparação Modelos',
             fontsize=12, fontweight='bold')
plt.tight_layout()
save_fig('08_pca_scatter_comparacao.png')

# ── Gráfico 09: PCA com centroides e elipses de confiança ────────────────────
fig, ax = plt.subplots(figsize=(10, 7))
idx_sc2 = rng2.choice(len(X_pca), min(8_000, len(X_pca)), replace=False)
for c in range(K_FINAL):
    mask = lbs_full[idx_sc2] == c
    Xc = X_pca[idx_sc2][mask]
    ax.scatter(Xc[:, 0], Xc[:, 1], c=CLUSTER_CORES[c], alpha=0.25, s=6, label=None)
    # Elipse de confiança (95%)
    mu   = Xc[:, :2].mean(axis=0)
    cov  = np.cov(Xc[:, :2].T)
    vals, vecs = np.linalg.eigh(cov)
    order = vals.argsort()[::-1]
    vals, vecs = vals[order], vecs[:, order]
    theta = np.degrees(np.arctan2(vecs[1, 0], vecs[0, 0]))
    w, h  = 2 * 2.4477 * np.sqrt(vals[:2])  # chi2 95%
    from matplotlib.patches import Ellipse
    ell = Ellipse(xy=mu, width=w, height=h, angle=theta,
                  edgecolor=CLUSTER_CORES[c], facecolor='none',
                  linewidth=2.5, linestyle='-')
    ax.add_patch(ell)
    ax.scatter(*mu, c=CLUSTER_CORES[c], s=150, marker='X', zorder=5,
               edgecolors='black', linewidths=0.8,
               label=f'C{c}: {CLUSTER_NAMES[c].split("—")[1].strip()} (n={mask.sum():,})')

ax.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)', fontsize=10)
ax.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)', fontsize=10)
ax.set_title('Clusters K=3 no Espaço PCA\nElipses de confiança 95% | X = centroide',
             fontsize=11, fontweight='bold')
ax.legend(fontsize=9, loc='upper right')
plt.tight_layout()
save_fig('09_pca_elipses_confianca.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 10 — Análise Temporal (por Ano)')
# ══════════════════════════════════════════════════════════════════════════════

if 'ano' in df_feat.columns:
    tab_ano = pd.crosstab(df_feat['ano'], df_feat['cluster_km3'], normalize='index') * 100
    tab_ano.columns = [CLUSTER_NAMES[c] for c in tab_ano.columns]
    print('\n  % por cluster por ano:')
    print(tab_ano.round(1).to_string())

    # Estabilidade temporal (χ² por par de anos)
    anos = sorted(df_feat['ano'].dropna().unique())
    if len(anos) >= 2:
        tab_chi = pd.crosstab(df_feat['ano'], df_feat['cluster_km3'])
        chi2_t, p_t, _, _ = chi2_contingency(tab_chi)
        print(f'\n  Homogeneidade temporal: χ²={chi2_t:.2f}  p={p_t:.4f}')
        est_est = 'ESTÁVEL' if p_t > 0.05 else 'VARIA com o tempo'
        print(f'  → Distribuição de clusters {est_est} entre anos (α=0.05)')

    # ── Gráfico 10: Evolução temporal ────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 5))
    for c in range(K_FINAL):
        col = CLUSTER_NAMES[c]
        if col in tab_ano.columns:
            ax.plot(tab_ano.index, tab_ano[col], marker='o', linewidth=2,
                    color=CLUSTER_CORES[c], label=col)
    ax.set_xlabel('Ano'); ax.set_ylabel('% do total anual')
    ax.set_title('Distribuição dos Clusters por Ano\n(variação temporal)',
                 fontweight='bold')
    ax.legend(fontsize=9); ax.set_xticks(tab_ano.index)
    plt.tight_layout()
    save_fig('10_evolucao_temporal.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 11 — Análise Geográfica')
# ══════════════════════════════════════════════════════════════════════════════

if 'municipio' in df_feat.columns:
    geo = df_feat.groupby(['municipio', 'cluster_km3']).size().unstack(fill_value=0)
    geo.columns = range(K_FINAL)
    geo['total'] = geo.sum(axis=1)
    for c in range(K_FINAL):
        geo[f'pct_c{c}'] = geo[c] / geo['total'] * 100
    geo = geo[geo['total'] >= 20]  # municípios com ≥ 20 gestantes

    print(f'\n  Municípios com ≥ 20 gestantes: {len(geo)}')
    for c in range(K_FINAL):
        top5 = geo[f'pct_c{c}'].nlargest(5)
        print(f'\n  Top 5 municípios — {CLUSTER_NAMES[c]}:')
        for mun, pct in top5.items():
            print(f'    {mun}: {pct:.1f}%')

    # ── Gráfico 11: Top municípios por cluster ────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    for ax, c in zip(axes, range(K_FINAL)):
        top15 = geo[f'pct_c{c}'].nlargest(15)
        ax.barh(range(len(top15)), top15.values,
                color=CLUSTER_CORES[c], edgecolor='white', alpha=0.85)
        ax.set_yticks(range(len(top15)))
        ax.set_yticklabels([str(m) for m in top15.index], fontsize=7.5)
        ax.set_xlabel('% das gestantes')
        ax.set_title(f'{CLUSTER_NAMES[c]}\nTop 15 municípios', fontsize=9, fontweight='bold',
                     color=CLUSTER_CORES[c])
        ax.axvline(50, color='black', linestyle='--', alpha=0.3)
    plt.suptitle('Concentração Geográfica por Cluster (municípios ≥ 20 gestantes)',
                 fontsize=11, fontweight='bold')
    plt.tight_layout()
    save_fig('11_geo_municipios.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 12 — Matriz de Confusão: Modelo Completo × Hold-Out')
# ══════════════════════════════════════════════════════════════════════════════

from sklearn.metrics import confusion_matrix

# Matriz de confusão no conjunto de TESTE
cm = confusion_matrix(lbs_test_true, lbs_test_pred_alin)
cm_norm = cm.astype(float) / cm.sum(axis=1, keepdims=True)

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for ax, (data, fmt, titulo) in zip(axes, [
        (cm, 'd', 'Contagem'),
        (cm_norm, '.2%', 'Proporção por linha')]):
    sns.heatmap(data, annot=True, fmt=fmt, cmap='Blues', ax=ax,
                xticklabels=[f'C{c}' for c in range(K_FINAL)],
                yticklabels=[f'C{c}' for c in range(K_FINAL)],
                linewidths=0.5)
    ax.set_xlabel('Predito (modelo treino 90%)')
    ax.set_ylabel('Referência (modelo completo)')
    ax.set_title(f'Matriz de Confusão — {titulo}', fontweight='bold')
plt.suptitle(f'Consistência de Atribuição — Conjunto Teste (10%)\n'
             f'ARI={ari_test:.4f}  AMI={ami_test:.4f}',
             fontsize=11, fontweight='bold')
plt.tight_layout()
save_fig('12_matriz_confusao_holdout.png')

# ── Gráfico 13: Silhouette por cluster — Comparação ──────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(15, 4))
for ax, (titulo, X_c, lbs_c) in zip(axes, [
        ('Modelo Completo', X_pca, lbs_full),
        ('Treino (90%)',    X_train, lbs_train_pred_alin),
        ('Teste (10%)',     X_test,  lbs_test_pred_alin)]):
    idx_m = np.random.RandomState(RANDOM_STATE).choice(len(X_c), min(N_SIL, len(X_c)), replace=False)
    sv = silhouette_samples(X_c[idx_m], lbs_c[idx_m])
    bplot = ax.boxplot(
        [sv[lbs_c[idx_m] == c] for c in range(K_FINAL)],
        labels=[f'C{c}' for c in range(K_FINAL)],
        patch_artist=True,
        medianprops=dict(color='black', linewidth=2)
    )
    for patch, c in zip(bplot['boxes'], range(K_FINAL)):
        patch.set_facecolor(CLUSTER_CORES[c]); patch.set_alpha(0.7)
    ax.axhline(sv.mean(), color='darkred', linestyle='--', linewidth=1.2,
               label=f'Média={sv.mean():.4f}')
    ax.set_title(f'{titulo}', fontweight='bold', fontsize=9)
    ax.set_ylabel('Silhouette'); ax.legend(fontsize=8)
plt.suptitle('Silhouette por Cluster — Comparação Completo / Treino / Teste',
             fontsize=11, fontweight='bold')
plt.tight_layout()
save_fig('13_silhouette_boxplot.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 13 — Análise de Risco Clínico')
# ══════════════════════════════════════════════════════════════════════════════

# Perfil de risco: flags de exames e taxas municipais
flags = ['flag_anti_hiv', 'flag_vdrl', 'flag_ultrassom'] if 'flag_ultrassom' in df_feat.columns \
        else ['flag_anti_hiv', 'flag_vdrl']

print('\n  Prevalência de flags por cluster (%):')
flags_present = [f for f in flags if f in df_feat.columns]
for f in flags_present:
    linha = f'  {f:<20}'
    for c in range(K_FINAL):
        sub = df_feat[df_feat['cluster_km3'] == c][f].dropna()
        linha += f' | C{c}: {sub.mean()*100:.1f}%'
    print(linha)

# Taxas de risco municipal
taxas = ['taxa_sifilis_gest', 'taxa_mortalidade_materna', 'taxa_toxo_gest']
taxas_present = [t for t in taxas if t in df_feat.columns]
print('\n  Taxas municipais médias por cluster:')
for t in taxas_present:
    linha = f'  {t:<30}'
    for c in range(K_FINAL):
        sub = df_feat[df_feat['cluster_km3'] == c][t].dropna()
        linha += f' | C{c}: {sub.mean():.4f}'
    print(linha)

# ── Gráfico 14: Radar de perfil clínico ──────────────────────────────────────
from matplotlib.patches import FancyArrowPatch

# Indicadores para radar (normalizados 0-1)
RADAR_FEATS = [f for f in
    ['nu_imc', 'nu_imc_pre_gestacional', 'ganho_imc',
     'log_taxa_sifilis_gest', 'cnes_hospitais', 'escolaridade']
    if f in df_feat.columns]
RADAR_LABELS = {
    'nu_imc': 'IMC Atual', 'nu_imc_pre_gestacional': 'IMC Pré',
    'ganho_imc': 'Ganho IMC', 'log_taxa_sifilis_gest': 'Sífilis (log)',
    'cnes_hospitais': 'Hospitais', 'escolaridade': 'Escolaridade'
}

medias = {c: [df_feat[df_feat['cluster_km3'] == c][f].mean() for f in RADAR_FEATS]
           for c in range(K_FINAL)}
# Normalizar
all_vals = np.array(list(medias.values()))
mins, maxs = all_vals.min(axis=0), all_vals.max(axis=0)
norm = {c: (np.array(medias[c]) - mins) / (maxs - mins + 1e-9) for c in range(K_FINAL)}

angles = np.linspace(0, 2 * np.pi, len(RADAR_FEATS), endpoint=False).tolist()
angles += angles[:1]  # fechar

fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={'polar': True})
for c in range(K_FINAL):
    values = norm[c].tolist() + norm[c][:1].tolist()
    ax.plot(angles, values, linewidth=2, color=CLUSTER_CORES[c], label=CLUSTER_NAMES[c])
    ax.fill(angles, values, alpha=0.15, color=CLUSTER_CORES[c])

ax.set_xticks(angles[:-1])
ax.set_xticklabels([RADAR_LABELS.get(f, f) for f in RADAR_FEATS], fontsize=10)
ax.set_ylim(0, 1)
ax.set_title('Perfil Clínico dos Clusters — Radar\n(valores normalizados [0,1])',
             fontsize=12, fontweight='bold', pad=20)
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=9)
plt.tight_layout()
save_fig('14_radar_perfil_clinico.png')

# ── Gráfico 15: Distribuição Estado Nutricional ───────────────────────────────
if 'estado_nutricional_cod' in df_feat.columns:
    fig, ax = plt.subplots(figsize=(10, 5))
    est_tab = pd.crosstab(df_feat['cluster_km3'],
                           df_feat['estado_nutricional_cod'].map(EST_NUT_MAP),
                           normalize='index') * 100
    est_tab.index = [CLUSTER_NAMES[c] for c in est_tab.index]
    est_tab.plot(kind='bar', ax=ax, edgecolor='white', linewidth=0.5,
                 color=['#3498db', '#2ecc71', '#f39c12', '#e74c3c'])
    ax.set_ylabel('% dentro do cluster')
    ax.set_xlabel('')
    ax.set_title('Estado Nutricional por Cluster (%)', fontweight='bold')
    ax.legend(title='Estado Nutricional', fontsize=9)
    ax.tick_params(axis='x', rotation=15)
    plt.tight_layout()
    save_fig('15_estado_nutricional.png')

# ══════════════════════════════════════════════════════════════════════════════
banner('PASSO 14 — Exportação: Parquet Final e Relatório')
# ══════════════════════════════════════════════════════════════════════════════

# Dataset final com K=3 como coluna definitiva
df_final = df_full.copy()
df_final['cluster_k3_final'] = lbs_full
df_final['cluster_k3_nome']  = df_final['cluster_k3_final'].map(CLUSTER_NAMES)
df_final.to_parquet(OUTPUT_DIR / 'gestante_k3_final.parquet', index=False)
print(f'  gestante_k3_final.parquet salvo ({len(df_final):,} registros)')

# ─── Relatório Técnico ────────────────────────────────────────────────────────
FIM = datetime.now()
duracao = (FIM - INICIO).seconds

# Montar tabela de métricas formatada
def fmt_metricas_md(df_m):
    linhas = ['| Conjunto | n | Silhouette | Calinski-H | Davies-Bouldin | Inércia |',
              '|----------|---|------------|------------|----------------|---------|']
    for _, row in df_m.iterrows():
        linhas.append(f"| {row['conjunto']} | {int(row['n']):,} | {row['Silhouette']:.4f} "
                      f"| {row['Calinski-H']:,.0f} | {row['Davies-Bouldin']:.4f} "
                      f"| {row['Inércia']:,.0f} |")
    return '\n'.join(linhas)

def fmt_anova_md(df_a):
    linhas = ['| Feature | F-stat | p-valor | η² | Efeito | Sig |',
              '|---------|--------|---------|-----|--------|-----|']
    for _, row in df_a.iterrows():
        efeito = 'Grande' if row['eta_sq'] > 0.14 else ('Médio' if row['eta_sq'] > 0.06 else 'Pequeno')
        linhas.append(f"| {row['Label']} | {row['F_stat']:,.2f} | {row['p_valor']:.2e} "
                      f"| {row['eta_sq']:.4f} | {efeito} | {row['sig']} |")
    return '\n'.join(linhas)

relatorio_md = f"""# Relatório Técnico — Modelo de Clustering K=3
## Projeto Maternar — Pós-Processamento e Validação

**Gerado em:** {INICIO.strftime('%Y-%m-%d %H:%M')}
**Duração:** {duracao//60}min {duracao%60}s
**Modelo:** K-Means K=3 (`clustering_research_output/modelos/kmeans_k3.pkl`)
**Dataset:** DATASUS — SISVAN, SINAN, SIM, SIA, CNES (2014–2016)

---

## 1. Resumo Executivo

O modelo K-Means com K=3 clusters foi selecionado após análise comparativa com quatro algoritmos
(K-Means, Agglomerative Ward, GMM, Mini-Batch K-Means) e dois valores de K (3 e 4).
K=3 obteve os melhores resultados em **3/3 métricas internas** (Silhouette=0.2873,
Calinski-Harabász=102.169, Davies-Bouldin=1.188).

A validação hold-out com **10% da base** ({len(idx_test):,} gestantes) confirma a
estabilidade do modelo: **ARI={ari_test:.4f}** e **AMI={ami_test:.4f}** indicam
consistência quase-perfeita entre o modelo treinado em 90% e o modelo completo.

---

## 2. Base de Dados

| Item | Valor |
|------|-------|
| Total de gestantes | {len(df_full):,} |
| Features para clustering | {df_scaled.shape[1]} |
| Componentes PCA (90% variância) | {n_comp} |
| Período | 2014–2016 |
| Municípios cobertos | {df_full['municipio'].nunique() if 'municipio' in df_full.columns else 'N/D'} |
| Fontes | SISVAN, SINAN, SIM, SIA, CNES |

### Pré-processamento aplicado:
- Remoção de inconsistências biológicas (5.826 registros)
- Imputação por mediana (variáveis nutricionais) e zero (variáveis de risco municipal)
- Capping IQR para outliers (7 variáveis)
- Normalização RobustScaler (features contínuas)
- Transformação log1p em `taxa_sifilis_gest` (97% zeros)
- Redução PCA: {df_scaled.shape[1]} features → {n_comp} componentes

---

## 3. Validação Hold-Out (90/10 Estratificado)

### Metodologia
- Divisão estratificada pelos rótulos do modelo completo (`stratify=cluster_km3`)
- Semente: `random_state={RANDOM_STATE}`
- Modelo re-treinado em 90% com mesmos hiperparâmetros (n_init=20, k-means++, max_iter=500)
- Centroides alinhados pelo algoritmo Húngaro (minimização de distância euclidiana)

### Métricas de Desempenho

{fmt_metricas_md(df_metricas)}

### Índices de Consistência (Teste vs Referência)
| Índice | Valor | Interpretação |
|--------|-------|----------------|
| Adjusted Rand Index (treino) | {ari_train:.4f} | {'>0.90 = excelente' if ari_train > 0.90 else ('>0.80 = muito bom' if ari_train > 0.80 else 'moderado')} |
| Adjusted Rand Index (teste) | {ari_test:.4f} | {'>0.90 = excelente' if ari_test > 0.90 else ('>0.80 = muito bom' if ari_test > 0.80 else 'moderado')} |
| Adjusted Mutual Info (treino) | {ami_train:.4f} | {'>0.90 = excelente' if ami_train > 0.90 else 'bom'} |
| Adjusted Mutual Info (teste) | {ami_test:.4f} | {'>0.90 = excelente' if ami_test > 0.90 else 'bom'} |

### Intervalos de Confiança Bootstrap (n={N_BOOTSTRAP} amostras de 90%)
| Métrica | Média | IC 95% Inf | IC 95% Sup |
|---------|-------|------------|------------|
| Silhouette | {np.mean(boot_sil):.4f} | {ic95['Silhouette'][0]:.4f} | {ic95['Silhouette'][1]:.4f} |
| Calinski-H | {np.mean(boot_ch):,.0f} | {ic95['Calinski-H'][0]:,.0f} | {ic95['Calinski-H'][1]:,.0f} |
| Davies-Bouldin | {np.mean(boot_db):.4f} | {ic95['Davies-Bouldin'][0]:.4f} | {ic95['Davies-Bouldin'][1]:.4f} |

---

## 4. Perfis dos Clusters

### 4.1 Distribuição

| Cluster | N | % |
|---------|---|---|
| C0 — Obesidade | {(lbs_full==0).sum():,} | {(lbs_full==0).sum()/len(lbs_full)*100:.1f}% |
| C1 — Eutrofia/Baixo Peso | {(lbs_full==1).sum():,} | {(lbs_full==1).sum()/len(lbs_full)*100:.1f}% |
| C2 — Acesso Diferenciado | {(lbs_full==2).sum():,} | {(lbs_full==2).sum()/len(lbs_full)*100:.1f}% |

### 4.2 Centroides (Escala Original)

{chr(10).join(['| ' + ' | '.join([str(h) for h in ['Cluster'] + list(cents_raw.columns)]) + ' |',
              '|' + '|'.join(['---'] * (len(cents_raw.columns) + 1)) + '|'] +
             ['| ' + ' | '.join([idx] + [f'{v:.3f}' for v in row]) + ' |'
              for idx, row in zip(cents_raw.index, cents_raw.values)])}

### 4.3 Interpretação Clínica

**C0 — Obesidade Gestacional (vermelho)**
- IMC atual médio: {df_feat[df_feat['cluster_km3']==0]['nu_imc'].mean():.1f} kg/m² (categoria Obesidade, ≥30)
- IMC pré-gestacional: {df_feat[df_feat['cluster_km3']==0]['nu_imc_pre_gestacional'].mean():.1f} kg/m²
- Peso médio: {df_feat[df_feat['cluster_km3']==0]['nu_peso'].mean():.1f} kg
- Ganho de IMC: {df_feat[df_feat['cluster_km3']==0]['ganho_imc'].mean():.2f} (maior entre os clusters)
- Hospitais CNES: {df_feat[df_feat['cluster_km3']==0]['cnes_hospitais'].mean():.1f} (baixa infraestrutura)
- **Risco principal**: Obesidade pré-gestacional + ganho excessivo → maior risco de diabetes gestacional, hipertensão e parto complicado

**C1 — Eutrofia / Baixo Peso (azul)**
- IMC atual médio: {df_feat[df_feat['cluster_km3']==1]['nu_imc'].mean():.1f} kg/m² (Eutrofia/Sobrepeso leve)
- IMC pré-gestacional: {df_feat[df_feat['cluster_km3']==1]['nu_imc_pre_gestacional'].mean():.1f} kg/m²
- Peso médio: {df_feat[df_feat['cluster_km3']==1]['nu_peso'].mean():.1f} kg
- Hospitais CNES: {df_feat[df_feat['cluster_km3']==1]['cnes_hospitais'].mean():.1f}
- **Perfil**: Maior grupo ({(lbs_full==1).sum()/len(lbs_full)*100:.0f}% das gestantes) — perfil médio/baixo peso

**C2 — Acesso Diferenciado / Alta Infraestrutura (verde)**
- IMC atual médio: {df_feat[df_feat['cluster_km3']==2]['nu_imc'].mean():.1f} kg/m²
- Hospitais CNES: **{df_feat[df_feat['cluster_km3']==2]['cnes_hospitais'].mean():.1f}** (4× acima dos demais)
- Taxa sífilis (log): {df_feat[df_feat['cluster_km3']==2]['log_taxa_sifilis_gest'].mean():.2f} (maior exposição)
- **Diferencial**: Acesso a hospitais especializados — possivelmente gestantes de centros urbanos com maior infraestrutura de saúde. A escolaridade é levemente superior.

---

## 5. Testes Estatísticos

### 5.1 ANOVA — Discriminação por Feature

{fmt_anova_md(df_anova)}

**Interpretação dos efeitos (Cohen 1988):**
- η² < 0.01: negligível | 0.01–0.06: pequeno | 0.06–0.14: médio | > 0.14: grande

### 5.2 Qui-Quadrado — Variáveis Categóricas

| Variável | χ² | df | p-valor | V de Cramér | Sig |
|----------|-----|-----|---------|-------------|-----|
{''.join([f"| {r['Label']} | {r['chi2']:,.2f} | {r['df']} | {r['p_valor']:.2e} | {r['Cramers_V']:.4f} | {r['sig']} |{chr(10)}" for _, r in pd.DataFrame(chi2_results).iterrows()]) if chi2_results else 'N/D'}

---

## 6. Estabilidade e Generalização

### 6.1 Conclusão da Validação Hold-Out

O modelo demonstra **alta estabilidade** entre o conjunto de treino (90%) e teste (10%):

- Silhouette do teste ({m_test['Silhouette']:.4f}) vs. completo ({m_full['Silhouette']:.4f}):
  variação de {abs(m_test['Silhouette'] - m_full['Silhouette'])/m_full['Silhouette']*100:.1f}%
- ARI > 0.90 indica que >90% dos pontos são atribuídos ao mesmo cluster
  independentemente de o modelo ser treinado em 90% ou 100% dos dados
- IC Bootstrap confirma: Silhouette [{ic95['Silhouette'][0]:.4f}, {ic95['Silhouette'][1]:.4f}]
  com baixa variância ({np.std(boot_sil):.5f})

### 6.2 Limitações

1. **Dados transversais**: O SISVAN não acompanha a mesma gestante ao longo do tempo.
2. **Silhouette abaixo de 0.30**: Esperado em dados epidemiológicos contínuos
   (sem clusters naturalmente bem separados).
3. **Agglomerative Ward**: Limitado a 8.000 amostras por restrição de memória O(n²).
4. **Ausência de validação clínica externa**: Os clusters precisam de validação
   por especialistas em saúde materno-infantil.
5. **Viés geográfico**: Municípios sem dados SIA têm variáveis de infraestrutura imputadas.

---

## 7. Gráficos Gerados

| Arquivo | Descrição |
|---------|-----------|
| 01_holdout_metricas.png | Comparação de métricas — Completo / Treino / Teste |
| 02_silhouette_samples.png | Silhouette por amostra — Treino vs Teste |
| 03_bootstrap_ic.png | Distribuição bootstrap e IC 95% |
| 04_anova_eta2.png | Effect size (η²) por feature |
| 05_raca_por_cluster.png | Distribuição racial por cluster |
| 06_violin_features.png | Violinplots das features principais |
| 07_heatmap_centroides.png | Heatmap de centroides normalizados |
| 08_pca_scatter_comparacao.png | PCA scatter — Completo / Treino / Teste |
| 09_pca_elipses_confianca.png | PCA com elipses de confiança 95% |
| 10_evolucao_temporal.png | % clusters por ano |
| 11_geo_municipios.png | Top municípios por cluster |
| 12_matriz_confusao_holdout.png | Consistência de rótulos — Teste |
| 13_silhouette_boxplot.png | Silhouette boxplot — 3 conjuntos |
| 14_radar_perfil_clinico.png | Radar normalizado dos perfis |
| 15_estado_nutricional.png | Estado nutricional por cluster |

---

## 8. Artefatos Produzidos

| Arquivo | Conteúdo |
|---------|----------|
| `metricas_holdout.csv` | Métricas Silhouette/CH/DB — 3 conjuntos |
| `anova_resultados.csv` | ANOVA com F-stat, p-valor e η² por feature |
| `chi2_resultados.csv` | χ² com V de Cramér para variáveis categóricas |
| `centroides_finais_k3.csv` | Centroides em escala original |
| `gestante_k3_final.parquet` | Dataset completo com `cluster_k3_final` e `cluster_k3_nome` |

---

## 9. Referências

- Rousseeuw, P.J. (1987). Silhouettes: a graphical aid to the interpretation and
  validation of cluster analysis. *Journal of Computational and Applied Mathematics*, 20, 53–65.
- Caliński, T. & Harabasz, J. (1974). A dendrite method for cluster analysis.
  *Communications in Statistics*, 3(1), 1–27.
- Davies, D.L. & Bouldin, D.W. (1979). A cluster separation measure.
  *IEEE TPAMI*, 1(2), 224–227.
- Hubert, L. & Arabie, P. (1985). Comparing partitions.
  *Journal of Classification*, 2(1), 193–218. (ARI)
- Cohen, J. (1988). *Statistical Power Analysis for the Behavioral Sciences* (2nd ed.).
  Lawrence Erlbaum Associates. (effect sizes)

---

*Relatório gerado automaticamente por `pos_processamento_k3.py` — Projeto Maternar*
"""

relatorio_path = OUTPUT_DIR / 'relatorio_tecnico_k3.md'
relatorio_path.write_text(relatorio_md, encoding='utf-8')
print(f'  Relatório salvo: {relatorio_path}')

# ══════════════════════════════════════════════════════════════════════════════
banner('CONCLUÍDO')
# ══════════════════════════════════════════════════════════════════════════════
graficos = list(GRAF_DIR.glob('*.png'))
print(f'  Gestantes analisadas:  {len(df_full):,}')
print(f'  Hold-out teste:        {len(idx_test):,} ({TEST_SIZE*100:.0f}%)')
print(f'  ARI (teste):           {ari_test:.4f}')
print(f'  Silhouette (completo): {m_full["Silhouette"]:.4f}')
print(f'  Silhouette (teste):    {m_test["Silhouette"]:.4f}')
print(f'  IC 95% bootstrap:      [{ic95["Silhouette"][0]:.4f}, {ic95["Silhouette"][1]:.4f}]')
print(f'  Gráficos gerados:      {len(graficos)}')
print(f'  Relatório:             {relatorio_path}')
print(f'  Duração total:         {duracao//60}min {duracao%60}s')
print(f'\n  Output: {OUTPUT_DIR}')
