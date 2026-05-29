# 07 - Questionamento Estratégico ao Stakeholder (PO/PM Review)

Este documento contém perguntas críticas e agressivas direcionadas ao dono do projeto **Maternar**. O objetivo é eliminar ambiguidades, testar a viabilidade do modelo e garantir que o projeto não seja apenas "mais um app", mas uma solução de alto impacto.

## 1. Viabilidade de Negócio e Sustentabilidade
*   **Qual é o plano real de monetização ou sustentabilidade financeira?** Se o foco são gestantes do SUS (baixa renda), quem paga a conta no longo prazo? Existe um contrato previsto com o Ministério da Saúde ou prefeituras, ou o projeto morrerá quando o investimento inicial acabar?
*   **Como garantiremos o engajamento recorrente?** Apps de saúde têm taxas de abandono altíssimas após o primeiro mês. O que impede a gestante de desinstalar o app após descobrir seu "cluster"? Existe algum gatilho de retenção além de "dicas"?

## 2. Precisão da IA e Dados (O Calcanhar de Aquiles)
*   **Como lidaremos com o "Lixo entra, Lixo sai"?** Os dados do DATASUS (SINAN/SIM/SISVAN) têm atrasos de meses ou anos e muitas subnotificações. Como você garante que o modelo treinado em 2022 reflete a realidade de uma gestante em 2026?
*   **Cadê a validação clínica?** O algoritmo K-Means foi validado por obstetras? Se o app disser "Caminho Seguro" para uma gestante que venha a ter um desfecho negativo, quem assume a responsabilidade jurídica e ética?
*   **Variáveis Limitadas:** Estamos usando apenas 4 ou 5 variáveis para o K-Means. Isso não é raso demais para uma classificação de saúde? Por que não estamos cruzando com dados de geolocalização (proximidade de hospitais) ou saneamento básico?

## 3. Tecnologia e Integração
*   **Integração Real com o SUS:** O app será isolado ou enviará dados para o Prontuário Eletrônico do Cidadão (PEC/e-SUS)? Se o médico do posto não souber o que o app classificou, o valor preventivo cai pela metade. Qual é a estratégia de integração?
*   **Segurança e LGPD:** Estamos lidando com dados de saúde (sensíveis). Qual é o orçamento para auditoria de segurança? Um vazamento aqui não é apenas um problema técnico, é um processo judicial de grandes proporções.

## 4. UX e Barreiras de Acesso
*   **Alfabetismo Funcional:** Você afirma que o foco é baixa escolaridade. Já foi feito um teste de usabilidade real com gestantes que não completaram o ensino fundamental? O que é "acolhedor" para um desenvolvedor pode ser confuso para a usuária final.
*   **Acesso à Internet:** Muitas gestantes em vulnerabilidade extrema não têm planos de dados constantes. O app funciona 100% offline? Como os alertas de urgência chegarão se ela estiver sem créditos?

## 5. Escala e Visão de Futuro
*   **O "Pós-Parto":** O projeto se chama "Maternar", mas a documentação foca quase 100% na gestação/prematuridade. O que acontece após o nascimento? O app vira um rastreador de vacinas ou morre no parto?
*   **Diferencial Competitivo:** Já existem dezenas de apps de "semana a semana". O que o Maternar tem que o *BabyCenter* ou o app *Meu SUS Digital* não entregam, além de um agrupamento matemático de risco?

---
**Instrução ao Stakeholder:** Respostas vagas não serão aceitas. Precisamos de definições claras para prosseguir com a arquitetura técnica de forma segura.
