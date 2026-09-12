# M1--M5 repair audit

## Root cause repaired

M1 could emit planner labels and templates that M3 did not register. In
particular, `USER_REQUESTED_READ_DOCUMENTS` was passed verbatim to an M3
operation lookup, causing `CAPABILITY_NOT_FOUND`. M3 now uses a finite,
developer-owned canonical mapping. The legacy label resolves only to `READ`,
then to `file.read`; unrecognized labels remain denied.

## Runtime flow

`M1 Planner -> M2 ValidatedIntentResult -> M3 resolution inside M4 -> M4
AuthorizationResult -> M5 mint -> verify -> lifecycle consume -> result`.

`app.pipeline.M1M5Pipeline` is intentionally non-executing. M6 must perform
any actual desktop action only after presenting its action context to M5.

## Security results

Existing tests verify M2/M4 provenance, HMAC integrity, task/step/agent/
operation/resource substitution rejection, expiry, revocation, and one-time
replay rejection. New pipeline coverage contains 12 supported human-language
cases, 18 ambiguous/adversarial cases, and the Documents regression.

## Known limitations

No research-paper file was supplied. The lifecycle store is process-local.
There is no desktop executor, real filesystem path resolution, or approval UI;
therefore M6 action-time canonical-path containment and human approval cannot
be claimed as implemented. Ollama-specific integration remains skippable when
the local service is unavailable.
