# 16 - Guia de Integração: Frontend (Flutter) x Backend (NestJS)

Este guia documenta o fluxo completo da API construída para o projeto Maternar. Ele serve como referência para os desenvolvedores Front-end conectarem o aplicativo móvel ao backend, consumindo corretamente as rotas, enviando os _payloads_ esperados e tratando as respostas (inclusive os JSONs complexos devolvidos pela Inteligência Artificial).

---

## 📌 Informações Gerais

- **Base URL:** `http://localhost:3000` (ou a URL de produção).
- **Autenticação:** O sistema utiliza JWT (JSON Web Token). Após o login, a maioria das rotas exigirá o envio do token no cabeçalho da requisição:
  ```http
  Authorization: Bearer <seu_token_aqui>
  ```
- **Content-Type:** Sempre envie as requisições POST/PUT com o cabeçalho `Content-Type: application/json`.

---

## 1️⃣ Fluxo de Usuário e Autenticação

### 1.1 Cadastro de Gestante

**Rota:** `POST /users/register`  
**Autenticação:** Não necessária.

**Payload (Body):**

```json
{
  "name": "Maria Silva",
  "email": "maria@example.com",
  "password": "SenhaForte123!",
  "zipCode": "01001-000",
  "birthDate": "1995-05-15",
  "educationLevel": 3,
  "raceColor": 4,
  "phone": "11999999999",
  "height": 1.65,
  "preGestationalWeight": 65.5,
  "previousPregnancies": 1,
  "hadPreviousComplication": false
}
```

_Nota:_ O Backend limpará o `zipCode` e fará a consulta no ViaCEP automaticamente para salvar a localização.

**Resposta de Sucesso (201 Created):**

```json
{
  "message": "User created successfully"
}
```

### 1.2 Login

**Rota:** `POST /auth/login`  
**Autenticação:** Não necessária.

**Payload (Body):**

```json
{
  "email": "maria@example.com",
  "password": "SenhaForte123!"
}
```

**Resposta de Sucesso (201/200):**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5c...",
  "expiresIn": 3600
}
```

_Dica Front-end:_ Salve este `access_token` no Flutter (idealmente usando `flutter_secure_storage`) para anexar nas próximas requisições.

### 1.3 Obter Perfil Logado

**Rota:** `GET /users/profile`  
**Autenticação:** `Bearer Token` obrigatório.

**Resposta de Sucesso (200 OK):**

```json
{
  "id": "uuid-do-usuario",
  "name": "Maria Silva",
  "email": "maria@example.com",
  "height": 1.65,
  "preGestationalWeight": 65.5
  // ... outros dados do usuário
}
```

---

## 2️⃣ Fluxo de Gestação

Como uma usuária pode engravidar mais de uma vez ao longo da vida, os dados são separados. Toda gestante precisa ter uma gestação ativa criada para poder responder questionários.

### 2.1 Criar Gestação

**Rota:** `POST /pregnancy/create`  
**Autenticação:** `Bearer Token` obrigatório.

**Payload (Body):**

```json
{
  "dumStartDate": "2026-01-10"
}
```

_Nota:_ A DUM (Data da Última Menstruação) é opcional, mas recomendada. O backend calcula a Data Prevista do Parto (+280 dias) com base nela.

**Resposta (201 Created):**

```json
{
  "id": "uuid-da-gestacao",
  "dumStartDate": "2026-01-10T00:00:00.000Z",
  "estimatedDueDate": "2026-10-17T00:00:00.000Z",
  "status": "ativa",
  "createdAt": "2026-06-06T10:00:00.000Z"
}
```

### 2.2 Listar Gestações da Usuária (Para a Home/Dashboard)

**Rota:** `GET /pregnancy`  
**Autenticação:** `Bearer Token` obrigatório.

**Resposta (200 OK):**
Retorna um _array_ ordenado da mais recente para a mais antiga.

```json
[
  {
    "id": "uuid-da-gestacao",
    "dumStartDate": "2026-01-10T00:00:00.000Z",
    "estimatedDueDate": "2026-10-17T00:00:00.000Z",
    "status": "ativa",
    "currentClusterName": "Caminho Seguro",
    "createdAt": "2026-06-06T10:00:00.000Z"
  }
]
```

_Dica Front-end:_ Utilize o primeiro item dessa lista na tela inicial. Repare que ele traz o `currentClusterName` (Cache de Classificação). Com isso, você pode exibir o status atual da gestante sem precisar fazer requisições extras pesadas.

---

## 3️⃣ Fluxo de Questionário, IA e Dicas (Timeline)

Aqui reside o coração (Event Sourcing) do app. A gestante preenche o check-in na tela, e o NestJS aciona a IA Python em tempo real via RabbitMQ para devolver dicas exclusivas.

### 3.1 Enviar Check-in (Submissão do Questionário)

**Rota:** `POST /questionnaires/{pregnancyId}/submit`  
**Autenticação:** `Bearer Token` obrigatório.

**Payload (Body):**

```json
{
  "currentWeight": 68.2,
  "currentAppointments": 2,
  "hadNewComplications": false,
  "antiHivFlag": 1
}
```

**Resposta de Sucesso (201 Created):**
O backend devolve o resultado processado da IA. Note que as recomendações já vêm separadas por categoria.

```json
{
  "id": "uuid-da-resposta",
  "message": "Questionário classificado com sucesso!",
  "responseDate": "2026-06-06T10:05:00.000Z",
  "cluster": {
    "cluster_id": 1,
    "cluster_nome": "Eutrofia / Baixo Peso",
    "cluster_nome_app": "Caminho Seguro",
    "nivel_risco": "moderado",
    "cor_hex": "#A8D8EA",
    "recomendacoes": [
      {
        "categoria": "nutricao",
        "texto": "Monitorar ganho de peso e focar em proteínas."
      },
      {
        "categoria": "exames",
        "texto": "Realizar teste de glicemia na 24ª semana."
      }
    ],
    "metricas": {
      "nu_imc_calculado": 25.04,
      "ganho_imc": 1.1,
      "estado_nutricional": "adequado"
    }
  }
}
```

**Possível Resposta de Erro Tratada (503 Service Unavailable):**
Caso a fila RabbitMQ demore muito, para proteger os dados da usuária, o questionário é salvo parcialmente e esse erro amigável é retornado:

```json
{
  "statusCode": 503,
  "code": "CLASSIFICATION_TIMEOUT",
  "message": "Questionário salvo. A classificação ocorrerá em instantes devido a alta demanda."
}
```

_Dica Front-end:_ Se cair no Catch e receber esse erro, exiba um alerta verde ou amarelo para a usuária, pois os dados _foram salvos_. Não é um erro crítico no nível de perder informação.

### 3.2 Listar Histórico / Diário de Questionários (A Tela de Dicas)

**Rota:** `GET /questionnaires/pregnancy/{pregnancyId}`  
**Autenticação:** `Bearer Token` obrigatório.

**Resposta (200 OK):**
Retorna um array com todo o histórico (Timeline) da usuária. É aqui que o Flutter vai montar os "cards" das respostas antigas com as dicas que foram fornecidas naquela época.

```json
[
  {
    "id": "uuid-da-resposta-recente",
    "pregnancyId": "uuid-da-gestacao",
    "currentWeight": 68.2,
    "currentAppointments": 2,
    "hadNewComplications": false,
    "antiHivFlag": 1,
    "clusterId": 1,
    "clusterName": "Caminho Seguro",
    "riskLevel": "moderado",
    "hexColor": "#A8D8EA",
    "calculatedImc": 25.04,
    "recommendations": [
      {
        "categoria": "nutricao",
        "texto": "Monitorar ganho de peso e focar em proteínas."
      },
      {
        "categoria": "exames",
        "texto": "Realizar teste de glicemia na 24ª semana."
      }
    ],
    "metrics": {
      "nu_imc_calculado": 25.04,
      "ganho_imc": 1.1,
      "estado_nutricional": "adequado"
    },
    "responseDate": "2026-06-06T10:05:00.000Z"
  },
  {
    "id": "uuid-da-resposta-antiga",
    "pregnancyId": "uuid-da-gestacao",
    "currentWeight": 65.5,
    "currentAppointments": 0,
    "hadNewComplications": false,
    "antiHivFlag": 0,
    "clusterId": 0,
    "clusterName": "Cuidado Integral",
    "riskLevel": "alto",
    "hexColor": "#FFB347",
    "calculatedImc": 24.05,
    "recommendations": [
      {
        "categoria": "consultas",
        "texto": "Marque a primeira consulta imediatamente."
      }
    ],
    "metrics": {
      "nu_imc_calculado": 24.05,
      "ganho_imc": 0,
      "estado_nutricional": "adequado"
    },
    "responseDate": "2026-05-10T08:30:00.000Z"
  }
]
```
