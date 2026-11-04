# Upload videos here

1. Open this folder in GitHub.
2. Select **Add file → Upload files**.
3. Select **one video** with an `.mp4`, `.mov`, `.m4v`, `.webm`, `.mkv` or `.avi` extension.
4. Commit the upload directly to the **main** branch.
5. The **💡 AI Chat Videos** GitHub Actions workflow starts automatically. It renders the vertical edit, uploads the edited MP4 as a GitHub Actions artifact (kept for 7 days), and attempts to send it to the configured Telegram chat.
6. After the edited artifact has been saved successfully, the workflow commits a deletion of the uploaded source from the latest `main` branch.

**Upload one video per commit.** If a commit adds or modifies multiple supported videos, the workflow stops and asks for a single-video commit.

## Important public-repository warning

This repository is public. Anyone can view a video after its upload commit is published. The automatic cleanup removes the source from the current branch, but **does not erase it from Git commit history**. The original upload may remain accessible through the earlier commit. Do not upload confidential, private, or personal recordings here. Use Telegram for private source uploads, or make the repository private before using GitHub uploads.

GitHub's browser uploader has a per-file size limit; GitHub also rejects regular Git files larger than 100 MB. The workflow does not use Git LFS.
