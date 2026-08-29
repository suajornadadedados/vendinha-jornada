"""Configuration, read once, typed at the edge.

Pydantic on every boundary is a project rule (CLAUDE.md), and the environment is a
boundary like any other: a missing `DATABASE_URL` should fail at import with a name
and a reason, not at the first request with a `NoneType` somewhere in psycopg.

The `.env` is resolved from the repository root, not from the working directory —
the API is started from `backend/`, the tests run from the root, and `make` from
either. A config that depends on where you stood when you typed the command is a
config that works on one machine.
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"

# Two readers of the same file, and both are needed. `Settings` below reads it for
# our own configuration; `load_dotenv` puts it in the process environment because
# provider SDKs read `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` from there and know
# nothing about our settings object. `override=False` so a variable already set in
# the shell — which is how CI and the containers pass secrets — always wins.
load_dotenv(ENV_FILE, override=False)


class Settings(BaseSettings):
    """Everything S-02 reads from the environment. See `.env.example` for the prose."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        # `model_` is a Pydantic-reserved prefix and `LLM_MODEL` would collide with
        # it in a confusing way. Naming the field `llm_model` and pointing it at the
        # env var explicitly keeps both names readable.
        populate_by_name=True,
    )

    # `local` is the only environment where the configuration endpoints accept a
    # write. There is no authentication in this project yet, and an unauthenticated
    # route that stores a provider credential is not something to ship to a public
    # host and remember to fix later. See D-8 in the S-02 spec.
    app_env: str = "local"

    # Lido por `install_log_redaction`, que é o único ponto do processo que mexe
    # no logger raiz. Estava no `.env.example` marcado (S-02) e nenhum código o
    # lia — ressalva R-5 da verificação da S-02.
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # A URL por onde o mundo de fora alcança este backend. Ela vai no
    # `notification_url` da preferência do Mercado Pago e no link do adapter mock,
    # então em local costuma ser um túnel. Estava no `.env.example` desde a S-02 e
    # ninguém a lia — mesma classe da ressalva R-5 da verificação da S-02.
    public_base_url: str = "http://localhost:8000"

    database_url: str = "postgresql://vendinha:vendinha@127.0.0.1:5432/vendinha"

    # De onde o navegador pode chamar esta API (S-07). Lista separada por vírgula.
    #
    # Até a S-07 não havia middleware nenhum no app, e não fazia falta: o único
    # cliente era `curl` e o runner de evals. Um navegador é outra coisa — sem
    # `Access-Control-Allow-Origin` o painel recebe erro de rede numa API que está
    # perfeitamente de pé, que é a falha mais confusa de diagnosticar do conjunto.
    #
    # Origem explícita e nunca `*`: com credencial no header (`X-Operador-Token`),
    # curinga é o que transforma qualquer página aberta pelo operador num cliente
    # do painel dele.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def origens_permitidas(self) -> list[str]:
        return [origem.strip() for origem in self.cors_origins.split(",") if origem.strip()]

    # `provedor:modelo`. The code never branches on the provider — see ADR-012.
    #
    # **Pinned to a dated snapshot, and that is the R7 line itself.** The plain
    # `claude-haiku-4-5` is an alias: the model behind it can change without a line
    # of this repository changing. A ruler that moves on its own does not detect
    # regression — it produces red at random, and random red is training to ignore
    # the CI. S-05's DESC-8 is what that costs: three eval suites red, and an A/B on
    # a clean `main` showing `golden-013` failing with no line of that branch in it.
    #
    # The offered-model list is fetched from the provider (`providers.py`), not
    # hardcoded, so pinning here does not narrow what an operator may choose — it
    # fixes what the suite measures against by default.
    llm_model: str = "anthropic:claude-haiku-4-5-20251001"

    # How much the model is allowed to wander. **Product configuration, and the
    # eval inherits it** — never the other way around: *"an eval that runs with a
    # different configuration measures a different system"* (`_monta_o_grafo`).
    #
    # **Nothing in this project fixed it until S-06, and it cost a moving ruler.**
    # Pinning `llm_model` to a dated snapshot was necessary and not sufficient: two
    # runs of the S-03 suite with byte-identical code disagreed — `golden-005` went
    # from 5 failing criteria to 2 (`docs/harness/medicao-de-evals.md` §2). The
    # variance is the agent's, because `init_chat_model` was using the provider
    # default. A gate where a case flips between runs produces intermittent red,
    # and intermittent red is training to ignore the CI.
    #
    # ADR-006 closes the easy way out: running *n* times and requiring *k* passes
    # is the threshold rubric coming in through the back door. So ADR-014 decided
    # the variance is attacked in the configuration, and this is where.
    #
    # `None` means *the provider's default*, and it stays representable because a
    # reasoning model refuses `temperature` outright while `resolve_model` is
    # provider-agnostic by design (ADR-012). Absent is not the same as zero, and a
    # config that could not say so would force a branch on the vendor.
    llm_temperature: float | None = 0.0

    # Qdrant: where the catalogue is ranked. No fact lives there — the index
    # returns ids by similarity and Postgres asserts the rest (S-03, `catalogo.py`).
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "catalogo"

    # What turns into a vector, in the same `provedor:modelo` shape as the chat
    # model. Anthropic offers no embedding endpoint, so this requires an
    # OPENAI_API_KEY even on an instance that only talks through Anthropic — that
    # is S-03 D-1, and the cost is written there and in `.env.example` rather than
    # discovered here.
    embedding_model: str = "openai:text-embedding-3-small"

    # The model that judges the eval cases, `provedor:modelo`. Unset means the
    # judge is the agent's own model, and the runner says so out loud: a model
    # grading its own output is a known bias, and a ruler must not hide it from
    # whoever reads the report (S-03, ADR-006).
    #
    # **Defaults to another provider now, and S-04's DESC-7 is why.** Measured
    # both ways: with the self-judge the suite oscillated at 5 of 7 and *the failing
    # cases changed between runs*; with `openai:gpt-4.1` it was stable. That DESC
    # said the default was S-06's call to make, and this is it. Instability is not
    # merely noise — it is paying for the same run three times.
    #
    # This asks for no credential the project did not already require: embedding is
    # OpenAI's even on an Anthropic-only instance (S-03 D-1, `embedding_model`).
    evals_judge_model: str | None = "openai:gpt-4.1"

    # `LANGFUSE_HOST` is the v3 name and `LANGFUSE_BASE_URL` is the current one.
    # Both are accepted so an existing `.env` keeps working; see D-1 in the spec.
    langfuse_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
    )
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    # Token, not currency — D-2 in the S-02 spec. A price table per model would be
    # several tables now that the provider is configurable, all rotting quietly.
    #
    # **Measured, not guessed.** 60_000 came from the S-02, when the agent had three
    # tools and answered one question about one product. The B2B composition flow
    # is longer by design — search, detail, price, validate, and all of it again
    # when the code refuses — and the S-11 measured what that actually costs by
    # reporting the spend of every eval case (`evals/runner.py`):
    #
    #     adversarial-007  12k    two turns, no composition
    #     golden-007       33k    one composition, one recompose after a refusal
    #     golden-014       57k    one composition, one recompose after a refusal
    #     golden-001       64k    one composition, six products detailed
    #
    # So legitimate work runs to ~65k and the old ceiling cut the top of the normal
    # range: `golden-014` said "now I'll validate the composition" and then could
    # not, because the guard had already taken the tools away. 150_000 leaves room
    # for the real B2B conversation — several compositions in one order, RF-2.3 —
    # while staying a hard bound on the loop `adversarial-006` builds.
    #
    # It is also the right side of the economics after the ADR-013: the ticket went
    # from tens of reais to thousands, and a ceiling that saves a fraction of a cent
    # by dropping an order is not a saving.
    #
    # **Raised again in S-04, and measured the same way.** 150_000 was chosen for a
    # flow that ENDED at the composition. The checkout adds turns after it — company
    # data, a refusal and a correction, the order, the link.
    #
    # The numbers below are the ones in `docs/specs/relatorios/S-04-evals-checkout.md`,
    # the report the PR carries, and they are the ONLY record of this measurement in
    # the repository. An earlier draft of this comment quoted an intermediate run and
    # the spec quoted a third set; the independent verification found all three
    # disagreeing (M-4). A ceiling justified by a number nobody can reproduce is a
    # ceiling chosen by feel.
    #
    #     golden-010        19k    reads an existing order, one turn
    #     adversarial-001   55k    composition, then an injected instruction
    #     golden-009        56k    composition, then a customer who pauses
    #     adversarial-005   92k    composition, then commercial pressure
    #     golden-015       105k    two compositions in one order
    #     golden-003       115k    composition, confirmation, company data, order, link
    #     golden-008       152k    the same, plus a refused CNPJ and a correction
    #
    # **These vary between runs, and by a lot** — the same case measured 144k and 152k
    # on two consecutive executions, and `golden-015` moved 131k → 105k. The spread is
    # the model choosing to re-check something, or not. A ceiling picked from one run's
    # maximum is a ceiling picked from one sample, so the headroom below is deliberate
    # rather than tight.
    #
    # The soft line takes the tools away at 80% of the cap (`budget.ANSWER_RESERVE`),
    # which at 150_000 is 120k — below the top of the NORMAL range. The symptom is
    # nasty precisely because it is not an error: the agent collects the data, says it
    # is closing, and then cannot call `criar_pedido`, because the guard had already
    # unbound it. It reads as a model that gave up.
    #
    # 250_000 puts the soft line at 200k — a third above the measured maximum of 152k,
    # which is the room the run-to-run spread demands — and stays a hard bound on the
    # loop `adversarial-006` builds. `tests/unit/test_budget_guard.py` pins this number to
    # `graph.DEFAULT_BUDGET_TOKENS`, so the two cannot drift apart again (M-2).
    #
    # **Raised a third time, and this time by a HUMAN conversation rather than an
    # eval.** Session `5ac8c0a9`, read off the `turno` table: 12 turns, 266_991
    # tokens, and the soft line at 200k crossed on turn 8 — the turn that handed over
    # the company data. Turns 9 through 12 ran with no tools at all, which is why no
    # order, no approval queue and no invoice exist for it.
    #
    #     turno 5   44_504    recompose after a refusal, several tool rounds
    #     turno 8   37_151    company data — crosses the soft line at 206_452
    #     turno 9   30_888    already toolless: the answer is improvised
    #
    # The eval maximum was 152k because an eval case is scripted and a person is not:
    # they greet, they ask what you have, they change their mind about quantities.
    # 500_000 puts the soft line at 400k, which is above this measurement by the same
    # margin the previous raise used.
    #
    # **And the instrument is still wrong, which is why this is a stopgap and not a
    # fix.** `budget.tokens_spent` sums `total_tokens` of every `AIMessage`, and every
    # call carries the whole history — so the counter grows quadratically with the
    # number of turns and measures conversation LENGTH, not money. Any fixed number
    # loses to a customer who chats. The counter only becomes a cost ceiling again
    # once prompt caching exists and it can charge what was actually billed instead
    # of what was re-sent for free (S-12).
    session_budget_tokens: int = 500_000

    # Ceiling for one external call: a tool when they arrive in S-03, and today
    # the wait for the model's first token.
    tool_timeout_seconds: float = 20.0

    # Fernet key that encrypts the stored provider credential (ADR-012). Absent
    # means writes are refused — never that the secret is stored in the clear.
    config_encryption_key: str | None = None

    # Payment, S-04. Sandbox always — a production credential does not enter this
    # project. Absent token means the mock adapter, and there is deliberately no
    # `PAYMENT_GATEWAY` switch: it would allow `mercadopago` with no token, which
    # boots fine and breaks on the first order. See D-4 and `pagamento.gateway_de`.
    mercadopago_access_token: str | None = None
    # Emissor de NF-e, S-05. `mock` (default) gera DANFE e XML fiéis ao leiaute 55
    # com tarja "SEM VALOR FISCAL"; `homologacao` é o adapter da S-09 e é recusado
    # aqui com uma frase que diz isso, em vez de cair no mock em silêncio.
    #
    # Ao contrário do pagamento, a escolha é EXPLÍCITA (ver `nota.emissor_de`). As
    # três variáveis estavam no `.env.example` desde a S-02 e nenhum código as lia —
    # mesma classe da ressalva R-5 da verificação da S-02 e da DESC-3 da S-04.
    nf_emitter: str = "mock"
    nf_emitter_api_key: str | None = None
    nf_emitter_base_url: str | None = None

    # A porta da fila do operador (S-05, REQ-2). Ela lista dados completos da nota —
    # CNPJ, contato, endereço de entrega — e autoriza uma emissão irreversível, então
    # não pode ficar aberta.
    #
    # **Sem token configurado, nada confere**, exatamente como o segredo do webhook:
    # a alternativa — "sem token, aceita tudo" — transformaria esquecer uma variável
    # de ambiente num endpoint aberto que emite documento fiscal. Quem roda o
    # quickstart e quer aprovar uma nota define esta linha; é a única coisa a mais
    # que o fluxo completo pede (RNF-1).
    #
    # O `operador` do corpo da requisição é gravado como veio. Este projeto não tem
    # autenticação (é a mesma razão de `PUT /config` só aceitar escrita em
    # `APP_ENV=local`), então o campo é uma **declaração**, não uma identidade
    # provada — e está dito assim na rota, em vez de fingir o contrário.
    operador_api_token: str | None = None
    # Origin verification of the payment webhook (RF-2.5, R8). Absent means no
    # signature verifies — the safe side. "No secret, accept anything" would turn
    # a forgotten environment variable into an open endpoint that moves money.
    mercadopago_webhook_secret: str | None = None

    @field_validator("evals_judge_model", mode="after")
    @classmethod
    def _vazio_e_ausente(cls, valor: str | None) -> str | None:
        """`EVALS_JUDGE_MODEL=` significa ausente, e o runner precisa vê-lo assim.

        `.env.example` sempre disse que **vazio** quer dizer *"o juiz é o próprio
        `LLM_MODEL`"*, e o runner avisa em voz alta quando isso acontece — porque um
        modelo avaliando a própria saída é viés conhecido e uma régua não pode
        escondê-lo de quem lê o relatório.

        Só que a linha em branco chega como `""`, não como `None`: ela cai no
        auto-juiz (`"" or modelo_do_agente`) e **não** dispara o aviso, que testa
        `is None`. Era latente enquanto o default era `None` — o caminho comum
        avisava. Deixou de ser no momento em que o default passou a nomear um juiz:
        agora quem copia o `.env.example` e apaga o valor recebe exatamente o viés
        contra o qual o aviso existe, em silêncio.
        """
        return valor or None

    @field_validator("llm_temperature", mode="before")
    @classmethod
    def _temperatura_vazia_e_o_default_do_provedor(cls, valor: object) -> object:
        """`LLM_TEMPERATURE=` significa *não mande o parâmetro*, e não zero.

        Mesma classe da linha acima, e descoberta do mesmo jeito: tentando usar. O
        campo é `float | None`, mas a linha em branco chega como `""` — que o
        Pydantic não converte em `None`, então o default `0.0` vencia. Uma
        instância que apagasse o valor para pedir o comportamento do provedor
        receberia `temperature=0` em silêncio, e é o oposto do que ela pediu.

        O custo disso já foi pago uma vez nesta spec: a primeira tentativa de medir
        o efeito da temperatura rodou **duas vezes a mesma configuração** e produziu
        um A/B que não comparava nada. O relatório saiu plausível, que é o que torna
        esse modo de falha caro (`docs/specs/relatorios/S-06-variancia-temperature.md`).
        """
        return None if valor == "" else valor


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached: reading the file on every request would be an I/O per request."""
    return Settings()
