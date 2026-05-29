# 14 — Arquitetura do Backend NestJS

**Data:** 2026-05-29  
**Versão:** 1.0  
**Stack:** NestJS 11 · Prisma 7 · PostgreSQL · TypeScript 5 · JWT · bcrypt

---

## 1. Visão Geral

O backend do Maternar é uma API REST desenvolvida com **NestJS v11** seguindo os princípios de **Clean Architecture** com separação em camadas: HTTP (Controllers/DTOs), Application (Services) e Infraestrutura (Database/Integrations).

A API é responsável por:

- Registro e autenticação de gestantes
- Gestão de perfil com enriquecimento geográfico via CEP
- Persistência de dados via PostgreSQL (Prisma ORM)
- Futura integração com o serviço de IA (Worker Flask via RabbitMQ)

---

## 2. Estrutura de Módulos

```
src/
├── main.ts                          # Bootstrap: ValidationPipe + ApiExceptionFilter
├── app.module.ts                    # Módulo raiz
│
├── auth/                            # Módulo de Autenticação
│   ├── application/
│   │   └── auth.service.ts          # Lógica de login (bcrypt compare + JWT sign)
│   ├── domain/
│   │   └── auth.types.ts            # Tipos TypeScript do payload JWT
│   ├── http/
│   │   ├── auth.controller.ts       # POST /auth/login
│   │   ├── auth.dto.ts              # LoginLocalDto (email, password)
│   │   ├── guards/
│   │   │   └── jwt-auth.guard.ts    # Guard com tratamento de TOKEN_EXPIRED
│   │   ├── strategies/
│   │   │   └── jwt-strategy.ts      # Passport JWT Strategy
│   │   └── decorators/
│   │       └── current-user.decorator.ts  # @CurrentUser()
│   └── auth.module.ts               # Importa UserModule, PassportModule, JwtModule
│
├── users/                           # Módulo de Usuários
│   ├── application/
│   │   └── user.service.ts          # create(), findUserByEmail(), retrieveUserProfile()
│   ├── http/
│   │   ├── user.controller.ts       # POST /users/register · GET /users/profile
│   │   └── user.dto.ts              # UserDto, UserProfileDto
│   └── user.module.ts
│
├── pregnancies/                     # Módulo de Gestações
│   ├── application/
│   │   └── pregnancy.service.ts
│   └── http/
│       └── pregnancy.controller.ts, pregnancy.dto.ts
│
├── questionnaires/                  # Módulo de Check-ins (Questionários)
│   ├── application/
│   │   └── questionnaire.service.ts
│   └── http/
│       └── questionnaire.controller.ts, questionnaire.dto.ts
│
├── integrations/
│   └── viacep/                      # Integração ViaCEP
│       ├── viacep.service.ts        # Fetch com timeout (5s) + tratamento de erros
│       ├── viacep.module.ts
│       └── interfaces/
│           └── IViaCepAdressProvider.ts
│
├── database/
│   ├── database.module.ts           # Global DatabaseModule
│   └── database.service.ts          # PrismaClient wrapper
│
└── common/
    ├── api-exception.ts             # ApiException (envelope padrão de erro)
    └── api-exception.filter.ts      # Global exception filter
```

---

## 3. Endpoints da API

### 3.1 Autenticação

#### `POST /auth/login`

Autentica uma gestante com email e senha.

**Request:**

```json
{
  "email": "maria@exemplo.com",
  "password": "Abc!2345"
}
```

**Response 200:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expiresIn": 60
}
```

**Response 401:**

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Credenciais inválidas."
  }
}
```

---

### 3.2 Usuários

#### `POST /users/register`

Cria uma nova conta de gestante. Internamente:

1. Verifica unicidade do e-mail
2. Busca dados de endereço via ViaCEP (tolerante a falhas)
3. Gera hash bcrypt da senha
4. Persiste usuário e localização em transação atômica (Prisma nested write)

**Request:**

```json
{
  "name": "Maria Silva",
  "email": "maria@exemplo.com",
  "password": "Abc!2345",
  "birthDate": "2026-09-20",
  "zipCode": "01001000"
}
```

**Campos opcionais no schema (não expostos no DTO atual):** `phone`, `height`, `weight`, `previousPregnancies`, `educationLevel`, `hadPreviousComplication`

**Response 201:**

```json
{
  "message": "User created successfully"
}
```

**Response 409:** Email já cadastrado  
**Response 400:** CEP inválido ou não encontrado

---

#### `GET /users/profile`

Retorna o perfil da gestante autenticada. Requer `Authorization: Bearer <token>`.

**Response 200:**

```json
{
  "id": "187a903a-2256-4b71-b76a-1d92d4c15b03",
  "name": "Maria Silva",
  "email": "maria@exemplo.com",
  "zipCode": "01001000",
  "birthDate": "2026-09-20T00:00:00.000Z",
  "createdAt": "2026-04-29T01:50:48.740Z"
}
```

---

### 3.3 Gestações

#### `POST /pregnancy/create`

Cria um novo ciclo gestacional para a usuária autenticada. Se `dumStartDate` for enviado, a API calcula automaticamente a data prevista do parto (DPP) somando 280 dias.

**Request:**

```json
{
  "dumStartDate": "2026-03-01T00:00:00.000Z"
}
```

#### `GET /pregnancy`

Retorna a lista de todas as gestações cadastradas pela usuária, ordenadas da mais recente para a mais antiga.

---

### 3.4 Questionários (Check-ins)

#### `POST /questionnaires/:pregnancyId/submit`

Registra um check-in de saúde vinculado a uma gestação específica. Atualmente, os dados são salvos parcialmente enquanto aguardam a integração com o worker de Inteligência Artificial para definição do `clusterId`.

**Request (Obrigatório):**

```json
{
  "currentWeight": 65.2,
  "currentAppointments": 1,
  "hadNewComplications": false,
  "antiHivFlag": 1
}
```

#### `GET /questionnaires/pregnancy/:pregnancyId`

Retorna todo o histórico de questionários respondidos para uma gestação específica, permitindo ao app móvel desenhar gráficos de evolução de peso e histórico de acompanhamento.

---

### 3.5 Envelope de Erro Padrão

Todos os erros retornam no formato:

```json
{
  "error": {
    "code": "CODIGO_ERRO",
    "message": "Descrição legível para o usuário"
  }
}
```

| Código                | HTTP | Cenário                                         |
| --------------------- | ---- | ----------------------------------------------- |
| `INVALID_CREDENTIALS` | 401  | Email ou senha incorretos                       |
| `UNAUTHORIZED`        | 401  | Token ausente ou inválido                       |
| `TOKEN_EXPIRED`       | 401  | Token JWT expirado                              |
| `INVALID_ZIP_CODE`    | 400  | CEP com formato inválido ou não encontrado      |
| `VIACEP_UNAVAILABLE`  | 503  | API ViaCEP indisponível (não bloqueia cadastro) |

---

## 4. Modelo de Dados

### 4.1 Tabela `users`

| Coluna                      | Tipo            | Obrigatório | Descrição                      |
| --------------------------- | --------------- | ----------- | ------------------------------ |
| `id`                        | UUID            | Sim         | PK gerado automaticamente      |
| `name`                      | String          | Sim         | Nome completo                  |
| `email`                     | String (unique) | Sim         | E-mail de login                |
| `password`                  | String          | Sim         | Hash bcrypt                    |
| `phone`                     | String?         | Não         | Telefone com DDD               |
| `height`                    | Decimal?        | Não         | Altura em metros               |
| `pre_gestational_weight`    | Decimal?        | Não         | Peso antes da gestação em kg   |
| `previous_pregnancies`      | Int?            | Não         | Gestações anteriores           |
| `education_level`           | Int             | Sim         | Nível de escolaridade (1-5)    |
| `race_color`                | Int             | Sim         | Auto-declaração raça/cor (1-5) |
| `zip_code`                  | String          | Sim         | CEP (somente dígitos)          |
| `had_previous_complication` | Boolean?        | Não         | Complicação anterior           |
| `birth_date`                | Date            | Sim         | Data de nascimento da gestante |
| `created_at`                | DateTime        | Sim         | Criação do registro            |
| `updated_at`                | DateTime        | Sim         | Última modificação             |

### 4.2 Tabela `user_locations`

| Coluna       | Tipo       | Obrigatório | Descrição                      |
| ------------ | ---------- | ----------- | ------------------------------ |
| `id`         | UUID       | Sim         | PK                             |
| `user_id`    | UUID       | Sim         | FK → users.id (CASCADE DELETE) |
| `city`       | String     | Sim         | Município (via ViaCEP)         |
| `uf`         | VarChar(2) | Sim         | UF (via ViaCEP)                |
| `region`     | String?    | Não         | Região do Brasil               |
| `ibge_code`  | String?    | Não         | Código IBGE do município       |
| `created_at` | DateTime   | Sim         | Data de criação                |

---

## 5. Fluxo de Autenticação

```
Cliente                          NestJS                        PostgreSQL
  │                                │                               │
  │── POST /auth/login ───────────►│                               │
  │   { email, password }          │── findUnique(email) ─────────►│
  │                                │◄─ User ──────────────────────│
  │                                │                               │
  │                                │── bcrypt.compare()            │
  │                                │   (compara hash armazenado)   │
  │                                │                               │
  │                                │── jwtService.signAsync()      │
  │                                │   (assina payload com secret) │
  │                                │                               │
  │◄── { access_token, expiresIn }─│                               │
  │                                │                               │
  │── GET /users/profile ─────────►│                               │
  │   Authorization: Bearer <jwt>  │── JwtStrategy.validate()      │
  │                                │   (verifica assinatura/exp)   │
  │                                │                               │
  │                                │── findUnique(id) ────────────►│
  │                                │◄─ User ──────────────────────│
  │◄── UserProfileDto ─────────────│                               │
```

---

## 6. Integração ViaCEP

O serviço `ViaCepService` implementa a interface `IViaCepAdressProvider` com:

- **Timeout:** 5 segundos (AbortController)
- **Retry:** Não aplicado (falha silenciosa em SERVICE_UNAVAILABLE)
- **Validação:** CEP deve ter exatamente 8 dígitos numéricos
- **Comportamento em falha:**
  - `BAD_REQUEST` (CEP inválido): bloqueia o cadastro
  - `SERVICE_UNAVAILABLE` (API fora do ar): cadastro prossegue sem dados de localização

---

## 7. Testes

### Estrutura de testes

```
test/
├── jest-unit.json              # Config Jest para unit tests
├── jest-e2e.json               # Config Jest para E2E
└── unit/
    ├── auth/
    │   ├── application/auth.service.spec.ts
    │   ├── guards/jwt-auth.guard.spec.ts
    │   ├── http/auth.controller.spec.ts
    │   └── jwt-strategy.spec.ts
    ├── common/
    │   └── api-exception.filter.spec.ts
    ├── integrations/viacep/
    │   └── viacep.service.spec.ts
    └── users/
        ├── application/user.service.spec.ts
        └── http/user.controller.spec.ts
```

### Comandos

```bash
npm test              # Unit tests
npm run test:cov      # Cobertura
npm run test:e2e      # End-to-End
npm run test:watch    # Watch mode
```

---

## 8. Configuração e Deploy

### Variáveis de Ambiente

| Variável       | Obrigatória | Descrição                                 |
| -------------- | ----------- | ----------------------------------------- |
| `DATABASE_URL` | Sim         | Connection string PostgreSQL              |
| `JWT_SECRET`   | Sim         | Chave de assinatura JWT (mínimo 32 bytes) |
| `PORT`         | Não         | Porta da API (padrão: 3000)               |

### Docker Compose

O arquivo `docker-compose.yml` sobe apenas o PostgreSQL. O NestJS roda localmente via `npm run start:dev` no desenvolvimento.

```bash
docker-compose up -d          # Sobe PostgreSQL
npx prisma migrate dev        # Aplica migrations
npx prisma generate           # Gera Prisma Client
npm run start:dev             # Inicia API em modo watch
```

---

## 9. Dependências Principais

| Pacote              | Versão  | Finalidade                      |
| ------------------- | ------- | ------------------------------- |
| `@nestjs/core`      | ^11.0.1 | Framework principal             |
| `@nestjs/jwt`       | ^11.0.2 | Geração e validação de JWT      |
| `@nestjs/passport`  | ^11.0.5 | Estratégia de autenticação      |
| `passport-jwt`      | ^4.0.1  | Estratégia JWT para Passport    |
| `@prisma/client`    | ^7.6.0  | ORM e client do banco           |
| `bcrypt`            | ^6.0.0  | Hash de senhas                  |
| `class-validator`   | ^0.15.1 | Validação de DTOs               |
| `class-transformer` | ^0.5.1  | Transformação de objetos        |
| `@nestjs/config`    | ^4.0.3  | Gestão de variáveis de ambiente |

---

## 10. Pendências e Próximos Passos

- [ ] Implementar refresh token (ver [doc 13 — Segurança](./13-Especificacoes_de_Seguranca.md))
- [ ] Adicionar Helmet.js e configuração de CORS explícita
- [ ] Adicionar rate limiting com `@nestjs/throttler`
- [x] Implementar endpoints de `pregnancies` e `questionnaires` (CRUD básico)
- [ ] Implementar integração RabbitMQ para envio de dados ao Worker de IA
- [ ] Atualizar status da gestação e salvar retorno do cluster IA após resposta do Worker
- [ ] Adicionar endpoints LGPD: `GET /users/my-data`, `DELETE /users/me`
- [ ] Configurar versionamento de API (`/v1/`)
- [ ] Implementar logging estruturado com contexto de segurança
