# Configuração do GitHub — proteção da main, checks e CODEOWNERS

> Referenciado por `README.md` e pelo REQ-4 da `docs/specs/S-00-fundacao.md`.
> É a parte do harness que **o GitHub executa por você** — inclusive quando você não quer.

O enunciado do desafio pede "validações automáticas que **bloqueiam**". Bloquear é a palavra:
um check que roda e não impede o merge é relatório, não portão. Esta é a fronteira entre
*"eu prometi"* e *"o sistema exige"*.

---

## 1. Criar o repositório

```bash
git init -b main
git add -A
git commit -m "chore(harness): scaffold repo with harness, docs and gates"
gh repo create vendinha-jornada --public --source=. --push
```

Público desde o commit 1. O desafio cobra processo visível; esperar o repositório "ficar
bonito" apaga justamente a parte que tem valor.

## 2. Conferir o CODEOWNERS

`.github/CODEOWNERS` aponta para `@caio-moliveira` (preenchido na S-00). Se você forkar ou
reusar este repositório, **troque antes do primeiro push**: handle inexistente faz o GitHub
ignorar a regra inteira sem avisar no PR — o portão fica decorativo e você não percebe.

```bash
sed -i "s/@caio-moliveira/@seu-handle/g" .github/CODEOWNERS
gh api "repos/{owner}/{repo}/collaborators/seu-handle/permission" --jq .permission  # write ou admin
```

O dono precisa de permissão de **write** no repositório; num repo de organização, um handle
sem acesso é ignorado do mesmo jeito que um inexistente.

O que ele protege e por quê: `evals/`, `docs/adr/`, `docs/PRD.md`, `docs/testes.md` e
`.claude/`. Sem isso, um PR com eval vermelho ficaria verde **editando o caso que reprovou**
(ADR-006). O gate só é real se os arquivos que o definem forem protegidos.

## 3. Proteger a `main` (ruleset)

`Settings → Rules → Rulesets → New branch ruleset`, alvo `main`:

| Regra | Valor |
|---|---|
| Restrict deletions | ✅ |
| Block force pushes | ✅ |
| Require a pull request before merging | ✅ |
| Required approvals | **0** |
| Require status checks to pass | ✅ (lista abaixo) |
| Require branches to be up to date | ✅ |
| Allowed merge methods | **Squash** apenas |
| Automatically delete head branches | ✅ (em `Settings → General`) |

**Zero aprovações, e isso é honesto.** Em repositório de um mantenedor só, exigir aprovação
humana produz teatro: você aprova o próprio PR. A revisão real é o `/verificar-spec` rodando
em **sessão nova**, com o relatório anexado ao PR e cobrado no checklist do template
(ADR-005).

**Squash apenas:** a `main` conta a história em nível de **spec**; a branch, em nível de
**task**.

## 4. Checks obrigatórios

Os nomes precisam bater exatamente com os `jobs:` de `.github/workflows/ci.yml`.

| Check | O que ele barra | Marcar como obrigatório |
|---|---|---|
| `commitlint` | histórico ilegível — escopo é obrigatório (`s-04`, `harness`) | agora |
| `lint` | estilo, erro estático e **workflow inválido** (actionlint), na raiz inteira | agora |
| `test` | regressão funcional: `unit` (a conta está certa) e `security` (a ação errada é alcançável?) | agora |
| `secrets` | credencial no diff | agora |
| `skills-drift` | skill vendorizada editada à mão, fora do lockfile (ADR-009) | agora |
| `detect` | calcula quais jobs condicionais ligam; se ele falhar, os dependentes somem | agora |
| `typecheck` | tipo quebrado no backend | **já obrigatório** (`backend/` existe desde a S-00) |
| `evals` | **regressão de qualidade do agente** | **depois da S-06** |

`evals` é o único que ainda aparece como **skipped**, e **check pulado não pode ser marcado
como obrigatório enquanto pular** — ele entra junto com o runner, na S-06.

### Como um job condicional decide se liga

O gatilho é calculado pelo job `detect`, que faz checkout e exporta o resultado como output;
os jobs condicionais leem `needs.detect.outputs.*`.

**Não use `if: hashFiles(...)` no nível do job.** Foi como este repositório nasceu, e o
resultado foi seis dias de CI que nunca executou: `hashFiles` só é permitida em contexto de
step, e uma expressão inválida **não reprova o job — quebra o parse do arquivo inteiro**. O
workflow vira `startup_failure`, sem job, sem log, e nenhum check reporta. A falha é
especialmente traiçoeira porque a ausência de check não se parece com um erro: a página do PR
fica limpa. Semanticamente também não funcionaria: no `if` de um job o workspace ainda não foi
clonado, então `hashFiles` responderia vazio sempre.

O portão contra a volta disso é o `actionlint`, que roda dentro do job `lint` e no `pre-push`.
Validar o YAML não basta — YAML válido não é schema de workflow válido.

> **Por que não deixar vermelho e pronto:** check vermelho permanente treina a ignorar CI
> vermelho. No dia em que um ficar vermelho de verdade, você ignora também — e aí os outros
> perderam o valor junto.

O job `test` **não sobe contêiner**. É consequência de não existir camada de integração
(`docs/testes.md` §1): `unit` e `security` são rápidos por construção, e o que precisa de
infraestrutura de verdade é verificado à mão no `/verificar-spec`.

## 5. Secrets e variáveis

`Settings → Secrets and variables → Actions`:

| Secret | Para quê | Necessário a partir de |
|---|---|---|
| `ANTHROPIC_API_KEY` | runner de evals | S-06 |
| `LANGFUSE_HOST` · `LANGFUSE_PUBLIC_KEY` · `LANGFUSE_SECRET_KEY` | observabilidade em Langfuse Cloud (ADR-010) | S-02 |

Nenhum deles entra no repositório. `.env` está no `.gitignore` e a leitura pelo agente está
negada em `.claude/settings.json` — são garantias diferentes: o `.gitignore` impede o *commit*,
a regra de permissão impede a *leitura*. Segredo lido entra no contexto, e contexto sai da
máquina.

## 6. Hooks locais

O CI é o portão remoto; o pre-commit é o local — barra antes de virar PR.

```bash
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg   # commitlint
pre-commit install --hook-type pre-push     # pytest (unit + security)
```

`pytest` fica no `pre-push`, não no `pre-commit`: hook lento treina a usar `--no-verify`, e aí
você desativou o portão local inteiro para ganhar dois segundos.

## 7. Conferir que o portão fecha

Portão que nunca barrou nada é decoração. Vale gastar cinco minutos provando:

```bash
git checkout main
echo "teste" >> README.md
git commit -am "test: push direto na main"
git push                      # deve ser RECUSADO pelo ruleset
git reset --hard origin/main
```

E, no primeiro PR, confirme na aba *Checks* que os jobs aparecem e que o botão de merge fica
bloqueado enquanto algum estiver vermelho.
