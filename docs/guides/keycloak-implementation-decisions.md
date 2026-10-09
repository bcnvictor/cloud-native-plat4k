# Décisions de mise en œuvre Keycloak portable

Exécution native du plan approuvé le 9 octobre 2026. Les décisions ci-dessous
conservent leur justification et leur coût si elles doivent être révisées.
La revue indépendante a relevé cinq points importants, traités ensemble avec
des tests de régression. Aucun point mineur reporté. Les validations live
restent ouvertes comme indiqué dans le guide de validation.

- Ruling: Native worktree creation is unavailable because the desktop task is rooted at the multi-repository parent; use Git fallback in the sibling .worktrees directory outside the repository — preserves the original checkout — cost if wrong: worktree is managed by Git instead of the desktop attachment.

- Task 3: Ruling: Add optional auth_provisioned to KeycloakStatusResponse — realm existence alone cannot prove successful client/Vault provisioning, and the CLI needs a reliable failure signal — cost if wrong: an additional optional response field.

- Task 3: Ruling: Sanitize the shared Vault read failure log as well as Keycloak errors — the new provisioner-secret read otherwise exposes reflected credentials at DEBUG level, reproduced by a failing test — cost if wrong: less upstream diagnostic detail in that log, exception still available to callers.

- Task 5: Ruling: ESO→Vault connectivity is checked in the existing external-secrets namespace, not by an ineffective policy in Keycloak's namespace — ESO runs outside this chart — cost if wrong: an existing ESO egress restriction must be fixed before installation can pass preflight.

- Task 7: Ruling: Generate ArgoCD Applications only after an immutable chart commit is published, instead of checking in unusable placeholder SHAs — matches the spec publication/access gate — cost if wrong: one operator generation step before GitOps integration.

- Task 7: Ruling: Add a daily isolated token-renewal CronJob using the already locked NGINX image and curl stdin configuration — a periodic ESO identity must not expire silently after 30 days — cost if wrong: an additional small Job and monitoring of renewal failures.

- Task 8: Ruling: Keep console accounts without an automatically copied email and exercise/document Keycloak's required profile step — real 26.8.0 requests email after temporary-password change; copying the CNP email can collide with an existing app user — cost if wrong: a first-login profile form remains for the team administrator.

- Task 8: Ruling: Leave private k3s live validation to the user, as explicitly requested — runbook retains the same commands for execution from the VM — cost if wrong: no live private-cluster evidence in this branch.

- Task 8: Ruling: Disable auth-vhost access logging of query strings by disabling its access log — authentication queries contain short-lived codes — cost if wrong: less HTTP request detail, infrastructure/error logs remain.

- Task 8: Ruling: Build the small gateway test Compose from its isolated fixture rather than duplicating a static gateway-compose.yaml — certificates, paths and ports belong to the test run — cost if wrong: this harness is invoked through pytest instead of standalone Compose.

- Task 8: Ruling: Keep AKS live deployment/app validation explicitly open because CNP gateway SSH/tailnet connectivity is unavailable from this machine — complete dry-run and isolated real-service checks without changing production CNP — cost if wrong: chart storage/network and template/onboarded apps still need live validation.

- Final: Ruling: Make install_route a context manager covering public verification and CNP activation, with an ownership-checked gateway transaction — the earlier one-shot interface cannot restore a valid but unreachable route after installation — cost if wrong: a crashed operator leaves a lock requiring the documented manual rollback.

- Final: Ruling: Use the common backend read path secret/data/cnp/keycloak/+/provisioner — concurrent instance bootstraps append the same policy rule, preserving both grants and original rules; app/ESO identities keep their own scopes — cost if wrong: the trusted backend can read all provisioner secrets in this namespace, and manual policy edits must be coordinated with bootstrap.

- Final: Ruling: Support standard If-None-Match:* for create-only registry writes — stale initial installers cannot overwrite an instance already activated by a concurrent winner — cost if wrong: one optional API precondition and a 412 response for callers using it.

- Final: Ruling: Treat actual AKS storage/network/app validation, which the reviewer declined to judge, as still open — only API dry-run and isolated services are proven while VM access is unavailable — cost if wrong: a live infrastructure issue could remain undetected until that validation.

- Final: Ruling: Treat actual private k3s validation, which the reviewer declined to judge, as user-owned and still open — the user explicitly performs it from their SSH VM — cost if wrong: this branch supplies no live private-cluster result.

- Final: Ruling: Keep actual GitOps publication and ArgoCD repository access, which the reviewer declined to judge, as a separate deployment gate — generated Applications require a published immutable chart SHA and verified repository credentials — cost if wrong: GitOps installation cannot start until that access is verified.

- Final: Ruling: Keep automatic identity restoration, which the reviewer declined to judge, outside fresh-install recovery — retained credentials allow a fresh Keycloak bootstrap, not restoration of users, sessions or application realms; the runbook states this — cost if wrong: identity recovery needs a database backup and explicit realm restoration.

- Final: Ruling: Keep expired ESO token replacement, which the reviewer declined to judge, a controlled manual rotation after an outage longer than 30 days — the daily renewer covers normal operation, while automatic credential rotation is outside the approved scope — cost if wrong: fresh deployment after such an outage needs operator token replacement before retrying.

- Final: Ruling: Keep HA, cross-cloud failover, cloud/cluster creation and the Keycloak Operator, which the reviewer declined to judge, outside this implementation — the user uses multi-cloud for deployment choice and one app cluster, not resilience; targets assume an existing cluster — cost if wrong: those capabilities require separate infrastructure work.

- Final: Ruling: Keep arbitrary onboarded OIDC code, external IdP and SMTP behavior, which the reviewer declined to judge, outside the installer — templates and compatible imported apps receive the same OIDC environment contract; unknown app code and identity providers need their own integration — cost if wrong: those apps or providers need additional configuration or implementation.

## Corrections vérifiées

- Final: fixed failed update permanently replacing the working route — test_failed_public_proof_rolls_back_staged_route and test_failed_activation_restores_last_working_route RED→GREEN, suite 490 passed/2 unrelated skipped; real integration 6/6.

- Final: fixed cluster reassociation blocked during recovery — test_recovery_reassociates_only_after_public_proof (old cluster and NULL tombstone) RED→GREEN, suite 490 passed/2 unrelated skipped; real integration 6/6.

- Final: fixed fresh Keycloak database unable to reuse retained client secret — test_missing_provisioner_is_seeded_from_retained_secret RED→GREEN and test_real_recovery_reuses_retained_credentials green on real Keycloak/PostgreSQL/Vault, suite 490 passed/2 unrelated skipped; real integration 6/6.

- Final: fixed concurrent backend Vault policy updates losing an instance grant — test_parallel_backend_policy_updates_keep_both_instances RED→GREEN, suite 490 passed/2 unrelated skipped; real integration 6/6.

- Final: fixed stale first installer disabling a concurrently activated instance — test_stale_first_install_cannot_disable_concurrent_winner and test_create_only_registration_preserves_existing_active_row RED→GREEN, suite 490 passed/2 unrelated skipped; real integration 6/6.

- Final: Verification: Ruff backend/shared/infra scopes passed; bash syntax and git diff --check passed. Full non-integration suite 490 passed, 2 skipped, 6 deselected in 134.26s; isolated real integration 6 passed in 20.81s. Frontend and dependency locks are unchanged since Task 8's successful checks.
