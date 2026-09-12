# M1--M5 paper-alignment traceability

The research paper itself was not included in this workspace. This mapping uses
the supplied audit briefs as the available specification; requirements that
need additional paper detail are marked accordingly.

| Requirement | Location | Evidence | Status |
|---|---|---|---|
| Unprivileged local structured planner | `app/planner/*` | parser/prompt tests | ALIGNED |
| Invalid planner output fails closed | `planner/parsing.py` | `test_parsing.py` | ALIGNED |
| M2 plan provenance and consistency check | `intent/validator.py`, `schemas.py` | `test_security_boundaries.py` | PARTIALLY ALIGNED |
| Developer-defined canonical capability mapping | `capabilities/templates.py`, `resolver.py` | registry and pipeline tests | ALIGNED |
| Unknown planner operation cannot mint authority | `capabilities/resolver.py` | registry tests | ALIGNED |
| M4 deterministic default deny | `permissions/evaluator.py`, `authorization.py` | permission/task tests | ALIGNED |
| M5 HMAC, task/agent/operation binding | `security/*` | crypto, verification, lifecycle tests | ALIGNED |
| Expiry, revocation, replay protection | `security/lifecycle.py` | lifecycle tests | ALIGNED (process-local) |
| Executable M1--M5 flow | `app/pipeline.py` | `test_m1_m5_pipeline.py` | ALIGNED |
| Real path containment / M6 action verification | no M6 implementation | no executable action exists | NOT APPLICABLE / deferred |
| Approval-required broadening | no approval workflow specified in source | no testable policy contract | AMBIGUOUS IN PAPER |

The legacy label `USER_REQUESTED_READ_DOCUMENTS` is an explicit, reviewed
compatibility mapping to `READ`; all other unknown labels fail closed.
