# 06 - Fluxo e Telas da Aplicação: Maternar

## 1. Mapa de Telas (User Flow)
O fluxo da aplicação é desenhado para ser linear e de fácil compreensão.

1.  **Splash Screen:** Logo e boas-vindas.
2.  **Onboarding:** 3 telas rápidas explicando o propósito do app (Prevenção e Cuidado).
3.  **Login/Cadastro:** E-mail/Senha ou Login Social.
4.  **Questionário de Perfil:** Perguntas clínicas e sociodemográficas (Input para o K-Means).
5.  **Home (Dashboard):** Acompanhamento da gestação e resultado do cluster.
6.  **Trilha de Conhecimento:** Feed de dicas personalizadas.
7.  **Calendário de Exames:** Datas importantes e lembretes de consultas.
8.  **Perfil da Gestante:** Dados pessoais e histórico médico.

## 2. Descrição das Telas Principais

### Tela 01: Questionário Dinâmico
*   **Elementos:** Barra de progresso, perguntas de múltipla escolha com ícones explicativos.
*   **Dados coletados:** Peso, altura, IMC pré-gestacional, raça/cor, escolaridade, município (CEP).
*   **Interação:** Após a última pergunta, o app exibe uma animação de "Calculando seu perfil de cuidado...".

### Tela 02: Dashboard (Home)
*   **Topo:** Saudação ("Olá, [Nome]! Você está na [12ª] semana.")
*   **Card de Status (Acolhedor):** Exibe o nome acolhedor do cluster com ilustração suave:
    *   C0 → **"Cuidado Integral"** (laranja suave)
    *   C1 → **"Caminho Seguro"** (azul suave)
    *   C2 → **"Atenção Redobrada"** (amarelo pastel)
*   **Progress Bar:** Idade gestacional com marcos de desenvolvimento do bebê.
*   **Atalhos:** Botão rápido para "Dica do Dia" e "Próxima Consulta".

### Tela 03: Trilha de Cuidado (Dicas)
*   **Layout:** Feed de cartões verticais (tipo Instagram/Pinterest).
*   **Conteúdo:** Título chamativo, imagem ilustrativa e resumo da dica.
*   **Personalização por cluster:**
    *   "Cuidado Integral" → dicas focadas em nutrição, controle de peso, sinais de alerta.
    *   "Caminho Seguro" → dicas de bem-estar, importância das consultas, desenvolvimento do bebê.
    *   "Atenção Redobrada" → dicas sobre exames (VDRL, anti-HIV), direitos no SUS, rede de referência.

### Tela 04: Calendário e Lembretes
*   **Visual:** Lista cronológica de eventos.
*   **Funcionalidade:** Adicionar lembretes para exames de sangue, ultrassom e consultas mensais.

## 3. Diretrizes Visuais para Desenvolvimento (Flutter)
*   **Widgets:** Usar `Material Design 3`.
*   **Animações:** Transições suaves entre as telas do questionário para reduzir a percepção de carga cognitiva.
*   **Feedback Visual:** Uso de cores nos cards conforme o cluster (Laranja, Azul, Amarelo — ver Doc 04).

## 4. Protótipo de Baixa Fidelidade (Estrutura)
```text
[ HOME ]
----------------------------------
| (Foto) Olá, Maria!             |
| 24ª Semana de Gestação         |
----------------------------------
| [ CARD: CAMINHO SEGURO ]       |
| "Tudo está correndo bem!"      |
----------------------------------
| [ DICA DO DIA ]                |
| Coma frutas ricas em ferro...  |
----------------------------------
| [ MENU: Home | Dicas | Perfil ]|
----------------------------------
```
