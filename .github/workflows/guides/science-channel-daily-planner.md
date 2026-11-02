# Science Channel — Daily Gemini Planner

Workflow: [science-channel-daily-planner.yml](../science-channel-daily-planner.yml)  
Main implementation: [gemini_planner.py](../../../science-channel/scripts/gemini_planner.py)

## Purpose and flow

This workflow creates one new Science Channel episode package. It runs automatically at **01:15 UTC daily** and can also be started manually from **Actions → Science Channel — Daily Gemini Planner → Run workflow**.

1. Checks out `main` with full history and installs Python 3.11 plus `requests`.
2. Runs `science-channel/scripts/gemini_planner.py` using `GEMINI_API_KEY` and optional `SCIENCE_GEMINI_MODEL`.
3. The planner reserves the accepted topic in `science-channel/history/generated-topics.json` and creates an episode folder containing the episode metadata, scene plan, narration script and image prompts.
4. The workflow requires exactly one new `episode.json` to have appeared during the run.
5. It commits the new episode folder and topic history together, rebases on the latest `main`, and retries the push up to three times.
6. It verifies the episode is present on `main`, then sends its `image-prompts.md` document to Telegram when Telegram credentials are configured.

The workflow timeout is 60 minutes. It shares the `stickman-lab-main-writer` concurrency group with other main-branch writers to avoid simultaneous write races.

## Required configuration

Set these in **Repository → Settings → Secrets and variables → Actions**:

| Name | Type | Required | Use |
|---|---|---:|---|
| `GEMINI_API_KEY` | Secret | Yes | Authenticates Gemini planning |
| `SCIENCE_GEMINI_MODEL` | Variable | No | Overrides the planner model; if unset, the script's own default applies |
| `TELEGRAM_BOT_TOKEN` | Secret | No | Sends the prompt document and failure alert |
| `TELEGRAM_CHAT_ID` | Secret | No | Destination for Telegram messages |

Never put credentials in the workflow YAML, script, episode files or README. Telegram delivery is non-blocking: the episode remains committed if prompt delivery fails or credentials are absent.

## What gets created

- A new folder below `science-channel/daily-episodes/`.
- Episode metadata and scene/narration planning files, including `episode.json`, `scenes.json`, `script.md` and `image-prompts.md`.
- Updated `science-channel/history/generated-topics.json` to prevent the planner from reusing previously generated topics.

After the commit is verified on `main`, Telegram receives `image-prompts.md` and a caption identifying the episode and its `images/incoming/` upload path.

## How to change it

| Desired change | Edit |
|---|---|
| Change the daily run time | Edit the cron expression in `on.schedule`. GitHub cron uses UTC. |
| Disable the schedule but keep manual runs | Remove only the `schedule` block; keep `workflow_dispatch`. |
| Change Python or job timeout | Edit `python-version` or `timeout-minutes` in the workflow. |
| Change Gemini model | Set/update the `SCIENCE_GEMINI_MODEL` Actions variable. |
| Change topic planning, prompts, scene structure or generated files | Edit `science-channel/scripts/gemini_planner.py`. |
| Change the no-repeat history behavior | Review the planner and `science-channel/history/generated-topics.json` together. Do not delete history unless repeats are acceptable. |
| Change Telegram prompt delivery/caption | Edit the `Send episode prompts to Telegram` step in the workflow. |
| Change concurrency or branch publishing | Review the checkout, commit/rebase/push steps and `stickman-lab-main-writer` group as one unit. |

The planner and downstream receiver/renderer share the episode folder schema and scene count. If changing that schema or count, update the receiver, ZIP importer, renderer, validation and documentation together.

## Troubleshooting

- **Gemini authentication/model error:** confirm `GEMINI_API_KEY` is present and valid; check `SCIENCE_GEMINI_MODEL` for a supported model ID.
- **No episode or more than one new episode:** inspect the planner script's output paths and ensure it creates exactly one new `episode.json`.
- **Push/rebase failure:** inspect the commit and rebase log. The workflow retries three times; do not force-push over concurrent main changes.
- **Telegram prompt missing:** check the optional Telegram secrets and the sendDocument step. The episode may still have been committed successfully.
- **No scheduled run:** check the Actions tab, repository Actions settings and the UTC cron expression. Scheduled workflows run on the default branch.

## Rollback

1. Open the successful or problematic run and note the commit SHA that added the episode and updated topic history.
2. If the workflow produced an unwanted episode, revert that commit (or a carefully reviewed follow-up cleanup commit) so both the episode folder and topic-history change are handled consistently.
3. Prefer a normal revert commit on `main`; do not reset or force-push shared history.
4. If reverting a workflow/script change, revert the specific change commit, then run the planner manually once and inspect the new episode package before relying on the next schedule.
5. A Telegram document already delivered cannot be recalled by a Git revert. Delete it in Telegram separately if needed.

Example from a local clone:

```bash
git checkout main
git pull --ff-only
git revert <commit-sha>
git push origin main
```

Review the revert diff before pushing. A revert of a planner output commit removes the committed episode/history update; it does not undo messages already sent to Telegram.
