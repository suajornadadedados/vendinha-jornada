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
from pydantic import AliasChoices, Field
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

    # `provedor:modelo`. The code never branches on the provider — see ADR-012.
    llm_model: str = "anthropic:claude-haiku-4-5"

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
    evals_judge_model: str | None = None

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
    session_budget_tokens: int = 250_000

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached: reading the file on every request would be an I/O per request."""
    return Settings()
