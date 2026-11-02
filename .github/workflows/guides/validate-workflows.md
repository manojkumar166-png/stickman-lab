# Validate GitHub Actions Workflows

Workflow: [validate-workflows.yml](../validate-workflows.yml)

## Purpose and triggers

This is the repository's workflow syntax check. It runs when:
- a push to `main` changes something under `.github/workflows/**`;
- a pull request changes something under `.github/workflows/**`; or
- it is started manually from **Actions → Validate GitHub Actions workflows**.

The job checks out the repository and runs actionlint through `reviewdog/action-actionlint@v1`. It has read-only `contents: read` permission and a five-minute timeout. It does not deploy code, generate media, commit files or require repository secrets.

## How to read the result

- A green run means actionlint accepted the workflow YAML and expressions it checked.
- A red run means inspect the actionlint output for the file, line and validation message.
- A green lint run does **not** prove that a workflow's external API credentials work, a provider is available, a render succeeds, Telegram accepts a video, or a Git push will be authorized. Run the actual workflow for end-to-end verification.

## How to change it

| Desired change | Edit |
|---|---|
| Change trigger paths/branches | `on.push` and `on.pull_request` in this YAML. Keep PR validation enabled if workflow edits are reviewed through PRs. |
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
- **No run after editing a workflow:** confirm the change is on `main` or a PR and the changed path is under `.github/workflows/`.

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
