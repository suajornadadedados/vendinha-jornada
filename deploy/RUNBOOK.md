# Runbook — o ambiente empacotado da Vendinha

> Este documento é escrito para quem **não** participou da sessão que o criou. Se algum passo
> aqui só funciona para quem já sabe o que ele faz, o runbook falhou — e a verificação
> independente da S-08 testa exatamente isso, subindo o ambiente só com o que está escrito aqui.

**O que este ambiente é:** o produto inteiro empacotado num `compose` — landing, painel do
operador, API, Postgres e Qdrant, com um nginx na frente servindo as telas e fazendo proxy da API.

**O que ele não é:** um site publicado. Não há TLS, não há domínio e não há autenticação de
verdade — o painel se protege com um token digitado à mão, que sem HTTPS trafega em claro.
**Este host não vai para a internet aberta** ([ADR-008](../docs/adr/ADR-008-deploy-ambiente-unico.md)).
Rode-o numa rede privada, numa VPN, ou atrás de um túnel SSH.

---

## 1. O que a máquina precisa ter

- Docker Engine com o plugin `compose` (v2).
- Git.
- ~4 GB livres de disco: as duas imagens somam cerca de 1 GB, e o resto é volume de dados.

Nada além disso. **Não é preciso ter Python, Node, `uv` nem `make` no host** — tudo o que compila
acontece dentro das imagens. É a diferença entre este ambiente e o `docker-compose.yml` da raiz,
que sobe só o banco e espera que você rode a API na sua máquina.

## 2. Subir do zero

```bash
git clone <o repositório> vendinha && cd vendinha
cp deploy/.env.example deploy/.env
```

Agora **preencha `deploy/.env`**. Os campos estão comentados um a um; estes cinco não têm default
e o ambiente não funciona sem eles:

| Campo | Como obter |
|---|---|
| `POSTGRES_PASSWORD` | `python -c "import secrets; print(secrets.token_urlsafe(24))"` — ou qualquer gerador |
| `OPERADOR_API_TOKEN` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `CONFIG_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ANTHROPIC_API_KEY` | console do provedor — é o modelo que conversa |
| `OPENAI_API_KEY` | console do provedor — **é o que transforma o catálogo em vetores** (ver §7) |

E ajuste `PUBLIC_BASE_URL` para o endereço real pelo qual o navegador alcança este host,
**terminando em `/api`** (§7 explica por quê). Se for acessar de outra máquina, troque
`localhost` pelo IP ou nome do host.

```bash
docker compose -f deploy/docker-compose.yml up -d --wait
```

O `--wait` só volta quando todos os healthchecks passam. Na primeira vez ele constrói as duas
imagens e roda o `bootstrap` — conte alguns minutos. Depois disso, abra:

- **`http://<host>:8080/`** — a landing, onde o cliente é atendido
- **`http://<host>:8080/admin`** — o painel do operador (peça o `OPERADOR_API_TOKEN` na tela)

Para conferir que ficou de pé:

```bash
docker compose -f deploy/docker-compose.yml ps          # todos `healthy`
curl -fsS http://localhost:8080/api/health              # {"status":"ok",...}
```

## 3. Operação do dia a dia

```bash
# Ver o que está acontecendo
docker compose -f deploy/docker-compose.yml logs -f api

# Reiniciar só a API (não derruba banco nem índice)
docker compose -f deploy/docker-compose.yml restart api

# Derrubar tudo, PRESERVANDO os dados
docker compose -f deploy/docker-compose.yml down

# Derrubar tudo e APAGAR os dados — pedidos e notas incluídos
docker compose -f deploy/docker-compose.yml down -v
```

**Publicar uma versão nova do código:**

```bash
git pull
docker compose -f deploy/docker-compose.yml up -d --build --wait
```

O `--build` não é opcional. Sem ele o compose reaproveita a imagem antiga e o `git pull` não
chega a lugar nenhum — o sintoma é um deploy que "não fez nada", e é o erro mais fácil de
cometer aqui.

## 4. Segurança mínima do host (RNF-9)

Nada disto é opcional num host que não seja o seu laptop.

**Firewall.** Só a porta do nginx precisa estar aberta. Postgres e Qdrant já não publicam porta
nenhuma — são alcançáveis apenas pela rede interna do compose —, e isso é do desenho, não da
configuração do firewall. O firewall é a segunda tranca.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 8080/tcp
sudo ufw enable
```

**SSH por chave, nunca por senha.** Em `/etc/ssh/sshd_config`:

```
PasswordAuthentication no
PermitRootLogin no
```

e `sudo systemctl restart ssh`. Confirme que ainda consegue entrar **numa segunda sessão** antes
de fechar a primeira — é a única forma de não se trancar do lado de fora.

**Containers non-root.** Já vem assim: a API roda como `vendinha` (uid 10001) e o nginx usa a
imagem `nginx-unprivileged`. Para conferir a qualquer momento:

```bash
docker compose -f deploy/docker-compose.yml exec api id     # uid=10001(vendinha)
docker compose -f deploy/docker-compose.yml exec nginx id   # uid=101(nginx)
```

**Quem pode abrir a página, pode usar o chat.** A landing não tem autenticação — é o canal do
cliente. Quem tiver o endereço conversa com o agente e gasta a sua cota de modelo. O
`SESSION_BUDGET_TOKENS` limita uma sessão, não o número de sessões: numa rede não confiável, é o
firewall que decide quem chega.

## 5. Backup e restore do Postgres

O Postgres guarda tudo que não dá para refazer: pedidos, aprovações de nota fiscal, notas
emitidas, e o histórico das conversas no checkpointer. O Qdrant **não** precisa de backup — ele é
derivado do catálogo e o `bootstrap` o reconstrói.

**Backup:**

```bash
docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom \
  > backup-$(date +%F-%H%M).dump
```

Guarde fora deste host. Um backup que só existe na máquina que pode pegar fogo não é backup.
Para automatizar, o `cron` resolve — e teste o restore pelo menos uma vez, porque backup nunca
testado é backup que não existe.

**Restore:**

```bash
docker compose -f deploy/docker-compose.yml up -d --wait postgres
cat backup-2026-08-31-1430.dump | docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists
docker compose -f deploy/docker-compose.yml up -d --wait
```

## 6. Rollback

Não há registro de imagens: as imagens são construídas aqui, a partir do código que estiver no
diretório. Então voltar versão é voltar o código e reconstruir.

```bash
git log --oneline -10          # ache o commit que funcionava
git checkout <sha>
docker compose -f deploy/docker-compose.yml up -d --build --wait
```

O banco **não** volta junto, e isso é o que costuma doer: se a versão nova criou coluna ou
tabela, a versão antiga vai encontrá-las e ignorá-las (o schema é `CREATE TABLE IF NOT EXISTS`,
sem ferramenta de migração neste projeto). O caminho oposto — a versão antiga precisar de algo
que a nova removeu — não tem conserto pelo rollback: aí é restore do backup de antes da subida.
**Tire um backup antes de publicar**, e o rollback passa a ter volta.

## 7. Armadilhas — as coisas que não dão erro compreensível

**A tela de Configurações é somente leitura aqui, e é de propósito.** `PUT /config` só aceita
escrita com `APP_ENV=local`; em qualquer outro valor responde 403 (S-02, D-8 — não há
autenticação, e uma rota aberta que grava credencial de terceiro não vai para um host
compartilhado). **Consequência prática: a chave do modelo TEM que vir do `deploy/.env`.** Não dá
para corrigi-la pela interface depois de subir; o caminho é editar o arquivo e
`restart api`.

**O `OPENAI_API_KEY` é obrigatório mesmo se você só usa Anthropic.** A Anthropic não oferece API
de embedding, e a S-03 decidiu embedar pela OpenAI (D-1). Sem essa chave o `bootstrap` falha na
segunda metade e **o ambiente inteiro não sobe** — a API depende dele ter terminado com sucesso.
A mensagem de erro diz isso em voz alta; procure-a em
`docker compose -f deploy/docker-compose.yml logs bootstrap`.

**`PUBLIC_BASE_URL` termina em `/api`.** Ela monta o link de pagamento que o cliente recebe, o
`notification_url` do gateway e os links de DANFE e XML do painel. O nginx serve as telas em `/`
e a API em `/api/` — sem o prefixo, o cliente clica no link de pagamento e vê a página inicial da
loja, sem nenhum erro em lugar nenhum.

**Mudar `VITE_API_BASE_URL` exige rebuild, não restart.** O Vite substitui essa variável
estaticamente: o valor fica dentro do JavaScript entregue ao navegador. Editar o `.env` e
reiniciar não muda nada.

**A conversa não sobrevive a um F5.** É condição conhecida do produto, não do deploy: as
mensagens vivem no checkpointer, mas o navegador não guarda mais o `session_id` (S-07, DESC-10).
O cartão de espera da nota fiscal avisa para manter a janela aberta.

**A nota fiscal sai com a tarja SEM VALOR FISCAL**, e não existe outro emissor (ADR-004). Se
alguém configurar `NF_EMITTER=homologacao`, a API recusa subir com uma mensagem explicando —
em vez de servir o mock em silêncio, que seria a pior falha possível aqui.

## 8. Observabilidade, e a decisão de LGPD que mora aqui

O Langfuse é **Cloud** ([ADR-010](../docs/adr/ADR-010-langfuse-cloud.md)), não sobe contêiner, e é
opcional: sem `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` a instrumentação não instancia o
cliente e o atendimento segue igual. Indisponibilidade do Langfuse nunca derruba o atendimento.

**A região do projeto (EU ou US) é decisão de LGPD e precisa ser registrada.** O ADR-010 endereça
essa pendência a este runbook, e este é o lugar de anotá-la:

> **Região do projeto Langfuse em uso:** `_______________` (preencher ao criar o projeto)
> `LANGFUSE_BASE_URL` é `https://cloud.langfuse.com` para US e `https://eu.cloud.langfuse.com`
> para EU.

O que torna a nuvem aceitável não é a topologia: é o mascaramento de PII **na origem**, antes do
envio (ADR-007). CPF, e-mail e nome não saem legíveis deste processo em nenhum ambiente, e há
teste de segurança que reprova o release se isso deixar de ser verdade.

## 9. Quando alguma coisa não sobe

```bash
docker compose -f deploy/docker-compose.yml ps        # quem está de pé, quem está unhealthy
docker compose -f deploy/docker-compose.yml logs bootstrap   # a primeira suspeita
docker compose -f deploy/docker-compose.yml logs api
```

| Sintoma | Causa provável |
|---|---|
| `bootstrap` sai com erro e a `api` nunca começa | falta `OPENAI_API_KEY`, ou o Postgres não subiu |
| a API sobe e cai em ciclo | leia o log: se falar em catálogo, o `bootstrap` não terminou |
| a landing abre e o chat não responde | falta `ANTHROPIC_API_KEY` — e a tela de config não a conserta (§7) |
| o painel abre e responde 401 em tudo | `OPERADOR_API_TOKEN` vazio no `.env`, ou token errado na tela |
| `/admin/conversas` mostra a landing | o `try_files` do nginx não está valendo — confira `deploy/nginx.conf` |
| a resposta do chat aparece de uma vez, sem streaming | `proxy_buffering` ligado em algum proxy à frente do nginx |
| `POSTGRES_PASSWORD variable is not set` | o `deploy/.env` não existe, ou está incompleto |
