# YaarWin Demo Tracker - Render Docker version

This version uses the official Playwright Python Docker image, so Chromium is already included.

Render:
- Runtime: Docker
- Dockerfile: `./Dockerfile`
- Docker Context: `.`
- No Playwright browser install command is needed.

Telegram commands:
`/setlogin DEMO_NUMBER DEMO_PASSWORD`
`/run`
`/stop`
`/status`
`/screenshot`

IMPORTANT:
Telegram error 409 means the same BOT_TOKEN is being polled by another running bot instance. Stop the old Render service/deployment or any local bot using this token. Only one polling instance can run at a time.

This is a non-betting demo tracker: it logs in, opens WinGo 1M, reads visible results and sends mobile screenshots.
