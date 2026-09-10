# YaarWin Demo Tracker - fixed Render version

Files:
- bot.py
- requirements.txt
- render.yaml

Build command:
pip install -r requirements.txt && playwright install chromium

Start command:
python bot.py

Telegram:
 /start
 /setlogin DEMO_NUMBER DEMO_PASSWORD
 /run
 /stop
 /status
 /screenshot

The browser uses a mobile viewport.

This tracker logs into the demo site, opens the supplied WinGo 1 Minute URL, reads visible result text, and sends a mobile screenshot after a detected winning/result popup. It does NOT place bets or change stakes.
