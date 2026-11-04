# Telegram Failed Workflow Alerts

Workflow: [telegram-failure-alerts.yml](../telegram-failure-alerts.yml)

## Purpose

This is a notification-only workflow. It watches the completion events of selected GitHub Actions workflows and sends a Telegram message when one finishes with the conclusion `failure`. It does not rerun jobs, change repository files, roll back commits, or repair the failed workflow.

## Trigger and monitored workflows

The workflow uses the `workflow_run` event with `types: [completed]`. It currently monitors:

- 💡 AI Chat Videos
- AI Story & Science Video Creator
- AI Video Experiment
- Free Science Visuals — Render Ready Episode
- Science Channel — Daily Gemini Planner
- Telegram Image Receiver
- Telegram ZIP Import
- Validate GitHub Actions workflows

The notification job has an `if` condition that allows it to run only when the completed workflow's conclusion is `failure`. Successful, cancelled and skipped runs do not send an alert.

## What the alert contains

The Telegram message includes:

- Workflow display name
- Run number
- Branch name
- Repository name
- Conclusion
- Direct GitHub Actions run URL

The message is sent with Telegram's `sendMessage` Bot API. The payload is JSON-encoded with `jq`, and the HTTP request retries transient failures.

## Required repository secrets

Configure both under **Repository → Settings → Secrets and variables → Actions**:

| Secret | Required | Purpose |
|---|---:|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Authenticates the Telegram Bot API request |
| `TELEGRAM_CHAT_ID` | Yes | Destination chat for failure notifications |

The bot must be able to send messages to the configured chat. Keep the token private and never place it in workflow inputs, source files or logs.

## Permissions and runtime

- Runner: `ubuntu-latest`
- Job timeout: 2 minutes
- Workflow permissions: `actions: read`, `contents: read`
- Trigger context: `github.event.workflow_run`
- The job runs only for failed monitored runs.

These read-only permissions are intentional: this workflow only reads run metadata and sends an external notification. It does not need repository write access.

## Troubleshooting

**No alert arrived**
1. Confirm the failed workflow is listed under `on.workflow_run.workflows` using its exact Actions display name.
2. Confirm the completed run conclusion is `failure` rather than `cancelled` or `timed_out` reported differently by GitHub.
3. Check that both Telegram secrets exist and are not empty.
4. Open the alert workflow's own Actions run. Inspect the Telegram API response for chat permissions, an invalid token, or an invalid chat ID.

**The alert workflow itself failed**
- Open its run URL from the Actions tab.
- Check the `Send failure alert to Telegram` step.
- Verify the bot can message the destination chat and that GitHub has access to the configured secrets.

**A newly added workflow is not monitored**
- Add its exact `name:` value from the target YAML to the `workflows:` list.
- Commit the change and verify that a test failure in the target workflow produces a notification.

## Safe customization

| Desired change | Edit |
|---|---|
| Add/remove monitored workflows | `on.workflow_run.workflows` |
| Change failure-only behavior | `jobs.notify.if` |
| Change message fields or format | `env` values and the `MESSAGE` construction in the shell step |
| Change Telegram retry behavior | `curl --retry` options |
| Change execution limit | `jobs.notify.timeout-minutes` |
| Change access | Keep `actions: read` and `contents: read` unless a documented requirement changes |

Do not add a workflow to the monitored list if it is intended to be excluded from Telegram notifications. Avoid adding write permissions: the alert workflow should remain a small, isolated notification service.
