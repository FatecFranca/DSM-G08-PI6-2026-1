# 10 - Entrega da 1ª Sprint: Projeto Maternar (27/03/2026)

### Autores
*   Gabriel Araujo de Pádua
*   Guilherme Dilio de Souza
*   Sheila Alves de Araujo

---

### 1. Escopo e Requisitos
*   **Objetivo:** Aplicativo móvel para classificação de perfil de cuidado gestacional e fornecimento de orientações personalizadas.
*   **RFs Principais:** Cadastro de gestante, questionário dinâmico (clínico/socioeconômico), motor de IA para classificação e feed de dicas.
*   **RNFs Principais:** Resposta da IA < 500ms, criptografia de dados de saúde (LGPD), arquitetura de microserviços.

### 2. Modelagem e Arquitetura
*   **Arquitetura 3 Camadas:**
    1.  **Mobile:** Flutter (Dart) para interface e experiência do usuário.
    2.  **Negócio/API:** NestJS (TypeScript) + PostgreSQL para gestão de usuários e persistência.
    3.  **IA/Inferência:** Flask (Python) para execução do modelo K-Means treinado.

### 3. Repositório e Back-end
*   **Repositório:** Estrutura inicial criada no GitHub com separação de pastas para `Document`, `src` (NestJS) e scripts de IA.
*   **Frameworks:** Node.js (v20+), TypeScript (v5.5.3) e NestJS (planejado para escalabilidade do backend).

### 4. Protótipo Front-end (Telas Estáticas)
*   Fluxo definido: Splash -> Onboarding -> Cadastro -> Questionário -> Dashboard (Home).
*   Design humanizado focado em acolhimento, utilizando cores pastéis e linguagem simplificada.

### 5. Banco de Dados (PostgreSQL)
*   **Modelagem Detalhada:** Documento [11-Modelagem_de_Banco_de_Dados.md](11-Modelagem_de_Banco_de_Dados.md).
*   **Estrutura Principal:**
    *   `Users`: Dados de perfil e login.
    *   `Gestacao`: Ciclos gestacionais (1:N com Usuário).
    *   `Questionario_Resposta`: Inputs para a IA (Ligado à Gestação).
    *   `Clusters`: Perfis de cuidado definidos pelo K-Means.
    *   `Dicas`: Feed de conteúdo (N:N com Clusters).

### 6. Computação em Nuvem II (Definição e Justificativa)
*   **Serviços:** AWS (Amazon Web Services) ou Google Cloud Platform (GCP).
*   **Componentes:** 
    *   **EC2/App Engine:** Hospedagem das APIs NestJS e Flask.
    *   **RDS/Cloud SQL:** Instância gerenciada de PostgreSQL para alta disponibilidade.
    *   **S3/Cloud Storage:** Armazenamento de mídia e modelos `.pkl` exportados.
*   **Justificativa:** Escalabilidade automática para suportar picos de uso e conformidade com padrões globais de segurança.

### 7. Mineração de Dados (K-Means) — Resultados Executados

> **Atualizado em 2026-05-25 com resultados reais do pipeline executado.**

*   **Base de Dados:** SISVAN + SINAN + SIM + SIA + CNES (2014–2016). Total: **378.969 gestantes** de **3.479 municípios**.
*   **Técnica:** K-Means K=3 — selecionado após análise comparativa com 4 algoritmos (K-Means, Agglomerative Ward, GMM, Mini-Batch K-Means) e critérios Silhouette, Calinski-Harabász, Davies-Bouldin, Gap Statistic.
*   **Normalização:** RobustScaler + PCA (90% variância → 8 componentes).
*   **Hiperparâmetros:** `n_init=20, k-means++, max_iter=500, random_state=42`.

#### Clusters Definidos (K=3):

| ID | Nome | N | % | Característica Principal |
|----|------|---|---|-------------------------|
| 0 | **Obesidade Gestacional** | 103.418 | 27.3% | IMC pré-gestacional ≥ 31 — alto risco metabólico |
| 1 | **Eutrofia / Baixo Peso** | 269.787 | 71.2% | Grupo majoritário — monitoramento nutricional |
| 2 | **Acesso Diferenciado** | 5.764 | 1.5% | Municípios com alta infraestrutura hospitalar |

#### Validação:
*   Silhouette Score: **0.2873** | Calinski-Harabász: **102.169** | Davies-Bouldin: **1.188**
*   Hold-out 10%: ARI = 0.999 (treino) e 0.999 (teste) — consistência praticamente perfeita
*   IC 95% Bootstrap: Silhouette ∈ [0.285, 0.290] (estabilidade confirmada)
