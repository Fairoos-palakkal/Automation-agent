# 06: T-06: Fail-Fast Initialization and Provider Error Handling

**What to build:** Fail fast with clear error messages and non-zero exit codes when LLM_API_KEY is missing, Playwright fails to launch, or tool arguments are malformed. Add python-dotenv to automatically load .env files. Add exponential backoff retry for HTTP 429, 5xx, and provider timeouts. Clearly label mock runs in report headers.

**Blocked by:** None (can start immediately)

**Status:** resolved

## Acceptance criteria

- [x] Running `qa-cc run` without LLM_API_KEY exits with non-zero status and an explicit configuration error message
- [x] Missing browser binaries fail immediately rather than continuing with empty toolsets
- [x] Transient 429 and 500 LLM errors trigger retry with backoff
- [x] Reports generated from --mock runs display a prominent MOCK RUN badge
