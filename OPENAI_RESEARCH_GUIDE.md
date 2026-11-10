# OpenAI research pilot

## One required repository secret

Open repository **Settings → Secrets and variables → Actions → New repository
secret**. Name it **OPENAI_API_KEY**; paste the OpenAI API key as its value.
Do not put it in a repository file, issue, chat, workflow input or Actions variable.
A project service-account API key is appropriate for this scheduled workload;
do not use an organization Admin API key. The project needs API billing/credits
and access to the configured model and Responses API. Authentication is sent
only to the fixed HTTPS OpenAI endpoint; redirects are disabled.

The daily workflow already passes the secret and `--ai-research`. Without
the key, the compact email visibly says `DISABLED_NO_KEY`, and no API calls
are made. Existing deterministic screening continues. No server is required.

## What runs

The initial approved company budget is **three per UTC calendar day**, with
**at most two API requests per company**, six requests total. Each request
has an output/reasoning ceiling of 5,000 tokens. The research request permits
at most six web-tool calls; the extraction request has no tools. There are
no automatic retries. An explicit `--resume-incomplete` pilot probe can use
one remaining request for a company whose first response exhausted output
tokens, without exceeding two requests per company or six per day. Its repair
request combines web research and structured output; at most 36 web-tool calls
are possible across three companies if all three need this explicit repair.
The default model is pinned to
`gpt-5.4-mini-2026-03-17`; changing it requires code review, not an arbitrary
environment endpoint. Model access and live compatibility still need a first
real API run after the key is configured.

This is a usage cap, **not a hard dollar cap**. Inputs, outputs and web tools
are billed. Record actual token usage in `ai_research_state.json`, review
OpenAI project usage, and configure billing alerts appropriate to the account.
Provider/project budget settings should not be assumed to stop spending.

Request and company reservations are written **before** network calls. Failed
and timed-out calls consume their reservation. Same-day reruns reuse these
reservations and do not reattempt the same company. The workflow commits state
and separately caches same-day state even when later steps fail. Concurrency
serializes daily runs. A complete runner/storage failure before state can be
saved externally, deletion of state/cache, a different checkout or a separate
manual process can defeat cross-run accounting. This is not a provider-side
spending guarantee. Do not run parallel paid probes with independent state.

## Research and admission are separate

1. Prioritize changed watched disclosures, then growth observations, core
   selections and remaining reviewable candidates. The rest rotate by day.
   Known hard financial/risk exclusions are not paid-research candidates.
2. Search/read primary issuer, SEC and exchange sources through Responses
   web search, using a bounded public-company snapshot. No account email,
   private portfolio, API key, SMTP secret or trading credential enters prompts.
3. Extract a strict JSON brief. Code checks issuer, source URL provenance,
   dates, counterevidence, review horizon and scenario arithmetic. At least
   two distinct primary-source URLs must occur in the research tool output.
   Unknown data must remain unknown. Schema/citation validation is not an
   independent audit of truth, source classification or financial interpretation.
4. Save recent findings and reuse them for under three days. Changed source
   identities, statement values/periods, policy, hold or watch questions
   invalidate the cache. Checkpoints must still be future dates. Cached
   assumptions are shown with their original review timestamp; current market
   cap is used to recalculate scenario returns. No current verified quote/cap
   means no displayed numerical return valuation.
5. Show **at most ten distinct companies total** across core selections and
   AI briefs. Documented core cases come first. AI `PROMISING` cases with
   qualifying arithmetic rank before other research leads, then fewer stated
   unresolved issues; this is a triage ordering, not a calibrated quality score.
   `AVOID`, insufficient, invalid, stale and refused outputs are not promoted.
   There is no quota to fill ten positions.

Every AI card is labelled **AI research lead; not qualified**, with its thesis,
decline explanation, resilience, competition/technology assessment, catalyst,
risks, unresolved questions, core outcome, checkpoint, invalidation, opportunity
cost, conditional valuation and source links. A company watched outside the
current price candidates is explicitly identified. AI does not clear holds,
populate `recovery_cases.json`, create paper selections, or execute trades.
The existing documented-case validator remains authoritative. First assess
the pilot's factual accuracy before considering any admission integration.

Return arithmetic uses equity cash after financing costs × assumed multiple,
then dilution; net debt is not subtracted again. +50% is required within
365 days, +100% on days 366–730; base upside must be at least 20%. These are
conditional assumptions, not forecasts. Company-specific five-year resilience,
technology durability and listing compliance cannot be proved by an old high.

## Email and artifacts

The headline reports the number of companies actually displayed, documented
cases and AI leads. Access/validation failures are visible; failed research
never silently becomes an investment case. The large price-alert and filing
backlogs stay in artifacts rather than making the user read dozens of names.
The compact format is used even if the key is missing. Omit `--ai-research`
to restore the original email format and avoid all OpenAI usage.

- `ai_research.json`: current shortlist, calculation inputs/results and failures.
- `ai_research.md`: rendered brief content and pilot status.
- `ai_research_state.json`: dated request reservations, research cache, source
  provenance and API token usage. Public company research only; these are
  committed to this public repository and preserved in Actions artifacts.
- Existing `research_report`, `filing_review`, `disclosure_watch` and shadow
  artifacts remain available, with admissions and holds unchanged.

The separate research-only workflow remains free of OpenAI calls unless it is
explicitly extended. The CLI flag is opt-in; normal imports/tests do not spend.

The **OpenAI research pilot (no email or paper)** workflow validates the key and
API against saved scan data up to three days old, sharing the daily job's
concurrency lock, request reservations and cache. It runs once when its workflow
file is pushed and supports manual dispatch. It sends no email, refreshes no
quotes and changes no selections or paper observations. Its artifact includes
`ai_email_preview.html`; failed or partial API validation makes this probe red
while preserving research and budget state. A probe consumes the same daily
allowance; it does not grant an extra three companies.

## References

- [OpenAI API keys and service accounts](https://developers.openai.com/api/docs/guides/api-keys)
- [Web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Pinned model capabilities](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
