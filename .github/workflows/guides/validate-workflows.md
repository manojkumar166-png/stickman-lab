# Validate GitHub Actions Workflows

Workflow: [validate-workflows.yml](../validate-workflows.yml)

## Purpose and triggers

This is the repository's static validation gate. It runs when a push to `main` or a pull request changes workflow YAML, the Cloudflare Worker, the Science Channel Python scripts, the legacy `scripts/` package or `main_ai.py`; it can also be started manually from **Actions → Validate GitHub Actions workflows**.

The job performs three checks:
1. **actionlint** validates GitHub Actions YAML, expressions and workflow structure.
2. **Python compileall** checks syntax across `science-channel/scripts/`, `scripts/` and `main_ai.py`.
3. **Node syntax check** runs `node --check cloudflare-worker.js`.

It has read-only `contents: read` permission and a five-minute timeout. It does not deploy code, generate media, commit files or require repository secrets.

## How to read the result

- A green run means actionlint, Python syntax compilation and the Cloudflare Worker JavaScript syntax check all passed for that commit.
- A red run means inspect the actionlint output for the file, line and validation message.
- A green lint run does **not** prove that a workflow's external API credentials work, a provider is available, a render succeeds, Telegram accepts a video, or a Git push will be authorized. Run the actual workflow for end-to-end verification.

## How to change it

| Desired change | Edit |
|---|---|
| Change trigger paths/branches | `on.push` and `on.pull_request` in this YAML. Keep all workflow and production entry-point paths covered. |
| Change lint action/version | The `uses: reviewdog/action-actionlint@v1` step. Review upstream action changes before pinning/updating. |
| Change actionlint flags | `with.actionlint_flags`. Current value is `-color`. |
| Change timeout or runner | Job-level `timeout-minutes` or `runs-on`. |
| Change permissions | Keep `contents: read` unless the validation job genuinely needs more. It currently has no write operations. |
| Change cancellation behavior | Review the `workflow-lint-${{ github.workflow }}-${{ github.ref }}` concurrency group and `cancel-in-progress`. |

Do not add secrets or write permissions to this lint-only job without a concrete requirement.

## Troubleshooting

- **YAML parse or expression error:** follow the reported file/line and correct indentation, quoting, expression syntax or invalid keys.
- **Actionlint action cannot be fetched:** check GitHub Actions availability and the action reference/network error; retry before changing the action version.
- **Lint passes but a workflow fails:** open that workflow's own run. Lint validates configuration syntax, not runtime behavior or secret values.
- **No run after editing code:** confirm the changed path matches one of the watched workflow, Worker or Python entry-point paths in `on.push.paths` / `on.pull_request.paths`.

## Rollback

If a change to this validator breaks checks:
1. Revert the commit that changed `validate-workflows.yml` or the action reference.
2. Push the revert normally and confirm the validation workflow runs again.
3. If a workflow edit itself is invalid, fix or revert that workflow in a separate reviewed commit; disabling validation only hides the problem.

```bash
git checkout main
git pull --ff-only
git revert <change-commit-sha>
git push origin main
```

This workflow is read-only, so it has no generated files or data to restore. Do not reset or force-push shared `main` history.
