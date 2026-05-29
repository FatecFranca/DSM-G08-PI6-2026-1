# 02 - Especificação de Requisitos: Maternar

## 1. Requisitos Funcionais (RF)

### RF01 - Cadastro e Autenticação
*   O sistema deve permitir que a gestante se cadastre com Nome, E-mail, Senha e Data da última menstruação (DUM) ou idade gestacional informada.
*   Deve suportar login seguro via JWT.

### RF02 - Questionário Sociodemográfico, Clínico e Ambiental
*   A aplicação deve apresentar um questionário dinâmico para coletar:
    *   **Dados Pessoais:** Idade da mãe, Escolaridade (anos de estudo).
    *   **Histórico Gestacional:** Quantidade de gestações anteriores, Quantidade de consultas de pré-natal até o momento.
    *   **Dados Físicos:** Peso atual e Altura (para cálculo de IMC e ganho de peso).
    *   **Comorbidades:** Presença de comorbidades relatadas (Hipertensão, Diabetes, Pré-eclâmpsia/Infecções prévias).
    *   **Localização:** CEP ou Coordenadas (Latitude/Longitude) para identificar saneamento e maternidade próxima.

### RF03 - Motor de Classificação de Perfil
*   O sistema deve enviar os dados do questionário para o motor de IA.
*   O motor deve classificar a gestante em um dos **3 perfis de cuidado** definidos pelo K-Means K=3: **Cuidado Integral** (Obesidade Gestacional), **Caminho Seguro** (Eutrofia / Baixo Peso) ou **Atenção Redobrada** (Acesso Diferenciado).

### RF04 - Feed de Dicas Personalizadas
*   Com base no cluster atribuído, o app deve exibir um feed de cards com dicas de saúde, nutrição e lembretes de exames.

### RF05 - Painel de Acompanhamento
*   Exibir a evolução da idade gestacional e um contador regressivo para o parto (estimado).

### RF06 - Notificações Push
*   O sistema deve enviar lembretes semanais sobre o desenvolvimento do bebê e incentivo às consultas de pré-natal.

## 2. Requisitos Não Funcionais (RNF)

### RNF01 - Tempo de Resposta
*   A classificação de risco pela API não deve ultrapassar 500ms.

### RNF02 - Disponibilidade
*   O sistema deve estar disponível 99.5% do tempo.

### RNF03 - Segurança de Dados
*   Todos os dados sensíveis (saúde) devem ser criptografados em trânsito (HTTPS/TLS) e em repouso.
*   Conformidade básica com os princípios da LGPD.

### RNF04 - Arquitetura de Microserviços
*   O backend deve ser dividido em:
    *   **Gerenciamento (NestJS):** Regras de negócio, usuários e notificações.
    *   **Inteligência (Flask):** Motor de inferência K-Means e processamento de dados de IA.
*   A aplicação mobile deve ser desenvolvida em Flutter (Android/iOS).

### RNF05 - Usabilidade e Acessibilidade
*   A interface deve ser simples, com fontes legíveis e ícones intuitivos para usuárias de baixa escolaridade.
