# Telegram ZIP Import

Workflow: [telegram-zip-import.yml](../telegram-zip-import.yml)  
Importer implementation: [import_telegram_zip.py](../../../science-channel/scripts/import_telegram_zip.py)

## Purpose and flow

This is a **manual** workflow for importing a ZIP that has already been staged in the repository. It does not download a ZIP directly from Telegram.

1. Commit the ZIP into the repository's staging location (currently `science-channel/telegram-uploads/`).
2. Open **Actions → Telegram ZIP Import → Run workflow**.
3. Supply the exact `episode_path` and `zip_path` repository paths.
4. The workflow checks out `main` using `GH_PAT`, installs Python 3.11 and runs the importer.
5. The importer validates the archive and extracts the accepted images into the episode's `images/incoming/`, creating `READY.txt`.
6. The workflow commits the incoming images and READY marker, removes the staged ZIP from Git, then rebases/pushes to `main` with up to five attempts.
7. The new incoming-image/READY-marker commit can trigger the render workflow.

Timeout: 10 minutes. Concurrency group: `stickman-lab-main-writer`.

## Inputs

| Input | Required | Example |
|---|---:|---|
| `episode_path` | Yes | `science-channel/daily-episodes/2026-11-01/episode-001` |
| `zip_path` | Yes | `science-channel/telegram-uploads/dream.zip` |

Paths must point to repository content on `main`. The episode must already exist and contain its metadata. The ZIP must be staged at the location accepted by the importer; inspect `import_telegram_zip.py` before changing that location.

## Required configuration and permissions

| Name | Type | Purpose |
|---|---|---|
| `GH_PAT` | GitHub Secret | Checkout token with repository contents write access so the workflow can push the import/ZIP-removal commit |
| `TELEGRAM_BOT_TOKEN` | GitHub Secret | Optional failure alert |
| `TELEGRAM_CHAT_ID` | GitHub Secret | Optional failure alert destination |

The workflow declares `contents: read` for the built-in Actions token and uses `GH_PAT` as the checkout token. Ensure the PAT has the repository access required to push to `main`, and that branch protection permits the intended automation. Never expose the PAT in logs or commit it.

## Validation and side effects

The importer is responsible for archive validation, safe extraction and checking the target episode. Its current contract is a 48-image episode pipeline. The workflow then:
- adds extracted files under `images/incoming/`;
- adds `READY.txt`;
- removes the staged ZIP from the repository with `git rm`;
- commits and pushes the changes to `main`.

The staged ZIP is intentionally deleted after a successful import commit. Keep a local backup if you need to retain the original archive. The renderer will process the incoming images after the push.

## How to change it

| Desired change | Edit |
|---|---|
| Change workflow inputs or their help text | `workflow_dispatch.inputs` in the YAML and this guide. |
| Change ZIP staging path, archive limits, allowed formats or safety checks | `science-channel/scripts/import_telegram_zip.py`. Update examples and operational instructions too. |
| Change destination episode layout or READY behavior | Importer script plus planner/receiver/renderer contract. |
| Change token or push authorization | Actions secret `GH_PAT`; review repository/PAT permissions and branch rules. |
| Change push retry count or timeout | YAML commit/push block and `timeout-minutes`. |
| Change failure alerts | Telegram secrets and the final alert step. |

Keep the workflow's checkout and push target on `main`. Do not remove the archive path validation or traversal/symlink protections when editing the importer.

## Troubleshooting

- **Workflow rejects the inputs:** use complete repository-relative paths; confirm both paths exist on `main`.
- **ZIP validation fails:** inspect the importer log for its specific reason (wrong archive, count, format, size, duplicate names, unsafe path or existing incoming files).
- **Permission denied on push:** verify `GH_PAT` is present, has contents write access and is allowed by branch protection.
- **Commit succeeds but renderer does not run:** verify the imported commit contains files under the renderer's watched incoming path or a `READY.txt` addition.
- **ZIP missing after import:** this is expected; the workflow removes the staged archive after extraction and commits that deletion.
- **Telegram alert missing:** alert delivery is best-effort and requires both Telegram secrets.

## Rollback

1. Find the import commit SHA in the Actions log or main-branch history.
2. If the imported images are wrong, revert that commit after reviewing its diff. The revert normally removes the extracted images/READY marker and restores the staged ZIP deletion, so the archive can be staged/imported again.
3. If you only need to replace a few images, a targeted corrective commit may be safer than reverting the full import.
4. Check the renderer's run separately. If it already rendered and sent a video, a Git revert does not recall that Telegram video or remove its Actions artifact.
5. Do not reset/force-push `main`.

```bash
git checkout main
git pull --ff-only
git revert <import-commit-sha>
git push origin main
```

Review the revert diff to confirm it restores the staged ZIP and removes only the intended imported files.
