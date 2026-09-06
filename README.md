# YouTube Radar — cloud version

YouTube Radar collects YouTube statistics in GitHub Actions and shows the saved history in a desktop dashboard.

## What is automatic

- GitHub Actions runs the collector approximately every 5 minutes.
- `data/snapshots.json` keeps the 7-day history.
- The desktop app refreshes itself every 30 seconds.
- When GitHub sync is configured, the app pulls the newest cloud history without restarting.
- The **⚙ Конкуренты** window changes `channels.json` without clearing snapshots.
- Adding/removing a channel does not delete the old history in `snapshots.json`.

## 1. Put the project on GitHub

Create a repository and upload all project files, including:

- `main.py`
- `app.py`
- `channels.json`
- `data/snapshots.json`
- `requirements.txt`
- `.github/workflows/radar.yml`

Do not upload any API key into the code.

## 2. Add the YouTube API key

In GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

Name: `YOUTUBE_API_KEY`
Value: your YouTube Data API v3 key.

The workflow reads this secret when it runs.

## 3. Enable/check the workflow

Open **Actions → YouTube Radar Collector** and run it once with **Run workflow**.

After that it is scheduled approximately every 5 minutes. GitHub Actions schedules can be delayed occasionally.

## 4. Install the desktop app

Open PowerShell in the project folder and run:

```powershell
py -m pip install -r requirements.txt
py app.py
```

If `py` is not available, use `python` instead.

## 5. Configure cloud sync for the desktop app

The app needs these Windows environment variables:

- `GITHUB_REPOSITORY` — for example `yourname/youtube-radar`
- `YOUTUBE_RADAR_GITHUB_TOKEN` — a fine-grained GitHub token with **Contents: Read and write** for this repository
- `GITHUB_BRANCH` — normally `main`

Keep the token outside the project files. Never paste it into `app.py`, `channels.json`, or GitHub.

After setting the variables, close and reopen PowerShell, then start `app.py` again.

### Windows example

```powershell
setx GITHUB_REPOSITORY "yourname/youtube-radar"
setx GITHUB_BRANCH "main"
setx YOUTUBE_RADAR_GITHUB_TOKEN "YOUR_TOKEN_HERE"
```

Replace the values with your own. The token command is only an example; do not commit the token anywhere.

## 6. Daily use

1. Start `app.py`.
2. Leave the dashboard open only when you want to watch the data. The collector itself runs in GitHub Actions, so the laptop does **not** need to stay on for collection.
3. The dashboard automatically pulls the latest repository data every 30 seconds.
4. Click **⚙ Конкуренты** to add or remove channels.
5. Add a channel using its Channel ID (`UC...`).
6. The app saves `channels.json` locally and sends it to GitHub.
7. The next scheduled collector run reads the new list.
8. Old snapshots are not cleared. A newly added channel simply starts building its own history from the next collection.

## Important limitation

This version stores history in Git. That is convenient for a prototype, but a 5-minute snapshot system can make `snapshots.json` and the Git history grow quickly. For a larger number of channels, the next upgrade should be a database (for example PostgreSQL/Supabase/Firestore) instead of committing JSON every 5 minutes.

## Security

If an API key was ever placed directly in an old `main.py`, rotate that key and use the GitHub secret instead.

The desktop GitHub token is more sensitive than the YouTube API key because it can modify the repository. Use a fine-grained token limited to this one repository and only the permissions required for repository contents.
