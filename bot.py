import asyncio
import json
import logging
import os
import re
from pathlib import Path

import aiohttp
from playwright.async_api import async_playwright

SITE_LOGIN = "https://yaarwin.app/#/login"
WINGO_URL = "https://yaarwin.app/#/saasLottery/WinGo?gameCode=WinGo_1M&lottery=WinGo"

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
DEMO_PHONE = os.getenv("DEMO_PHONE", "")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")

HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "1.5"))
SCREENSHOT_DELAY = int(os.getenv("WIN_SCREENSHOT_DELAY", "10"))

login_phone = DEMO_PHONE
login_password = DEMO_PASSWORD

browser = None
context = None
page = None
pw = None
tracker_task = None

last_result = None
last_period = None
last_popup_signature = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("demo-tracker")


def admin_ok(chat_id):
    try:
        return int(chat_id) == int(ADMIN_CHAT_ID)
    except Exception:
        return False


async def tg_call(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    timeout = aiohttp.ClientTimeout(total=40)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, data=data or {}) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Telegram API {resp.status}: {text}")
            return json.loads(text)


async def tg_send(chat_id, text):
    await tg_call("sendMessage", {
        "chat_id": str(chat_id),
        "text": text
    })


async def tg_photo(chat_id, path, caption):
    with open(path, "rb") as f:
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))
        form.add_field("caption", caption)
        form.add_field(
            "photo",
            f,
            filename=Path(path).name,
            content_type="image/png"
        )

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=form) as resp:
                if resp.status >= 400:
                    raise RuntimeError(await resp.text())


async def close_browser():
    global browser, context, page, pw

    try:
        if context:
            await context.close()
    except Exception:
        pass

    try:
        if browser:
            await browser.close()
    except Exception:
        pass

    try:
        if pw:
            await pw.stop()
    except Exception:
        pass

    browser = None
    context = None
    page = None
    pw = None


async def find_first(selectors):
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count():
                return loc
        except Exception:
            pass
    return None


async def login():
    global browser, context, page, pw
    global login_phone, login_password

    if not login_phone or not login_password:
        raise RuntimeError(
            "Demo login missing. Use /setlogin NUMBER PASSWORD first."
        )

    await close_browser()

    pw = await async_playwright().start()

    browser = await pw.chromium.launch(
        headless=HEADLESS,
        channel="chromium",
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]
    )

    # Mobile layout, as requested.
    context = await browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True
    )

    page = await context.new_page()

    log.info("Opening login page")
    await page.goto(
        SITE_LOGIN,
        wait_until="domcontentloaded",
        timeout=60000
    )
    await page.wait_for_timeout(2500)

    phone = await find_first([
        'input[type="tel"]',
        'input[placeholder*="phone" i]',
        'input[placeholder*="mobile" i]',
        'input[placeholder*="number" i]',
        'input[name*="phone" i]',
        'input[name*="mobile" i]',
        'input[name*="username" i]',
    ])

    password = await find_first([
        'input[type="password"]',
        'input[placeholder*="password" i]',
        'input[name*="password" i]',
    ])

    if not phone or not password:
        await page.screenshot(
            path="login_debug.png",
            full_page=True
        )
        raise RuntimeError(
            "Login fields were not detected. login_debug.png was saved."
        )

    await phone.fill(login_phone)
    await password.fill(login_password)

    button = await find_first([
        'button[type="submit"]',
        'input[type="submit"]',
    ])

    if not button:
        try:
            button = page.get_by_role(
                "button",
                name=re.compile(r"login|log in|sign in", re.I)
            ).first
            if not await button.count():
                button = None
        except Exception:
            button = None

    if not button:
        await page.screenshot(
            path="login_button_debug.png",
            full_page=True
        )
        raise RuntimeError(
            "Login button was not detected. login_button_debug.png was saved."
        )

    await button.click()
    await page.wait_for_timeout(5000)

    log.info("Login submitted.")


async def open_wingo():
    if not page:
        raise RuntimeError("Browser is not running.")

    await page.goto(
        WINGO_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    await page.wait_for_timeout(3000)

    log.info("Opened WinGo 1 Minute page.")


async def get_body_text():
    try:
        return await page.locator("body").inner_text(timeout=10000)
    except Exception:
        return ""


def extract_period(text):
    patterns = [
        r"(?:period|issue|round|draw)\s*[:#-]?\s*([0-9]{5,})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1)

    return None


def extract_result(text):
    # Only read visible text. No betting action is performed.
    patterns = [
        r"(?:winning\s*number|result|result\s*number)\s*[:#-]?\s*([0-9])\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1)

    for line in text.splitlines():
        if re.search(r"winning|result", line, re.I):
            nums = re.findall(r"\b([0-9])\b", line)
            if nums:
                return nums[-1]

    return None


def winning_popup(text):
    return bool(re.search(
        r"winning|you\s+win|congratulations|winner",
        text,
        re.I
    ))


async def send_current_screen(caption):
    path = "current_mobile.png"

    await page.screenshot(
        path=path,
        full_page=False
    )

    await tg_photo(
        ADMIN_CHAT_ID,
        path,
        caption
    )


async def tracker():
    global last_result, last_period, last_popup_signature

    try:
        await login()
        await open_wingo()

        await tg_send(
            ADMIN_CHAT_ID,
            "Demo login successful.\n"
            "WinGo 1 Minute opened.\n"
            "Result tracking started."
        )

        while True:
            text = await get_body_text()

            period = extract_period(text)
            result = extract_result(text)

            if period and period != last_period:
                last_period = period
                log.info("Period: %s", period)

            if result is not None and result != last_result:
                last_result = result

                msg = f"WinGo 1M result detected: {result}"
                if period:
                    msg += f"\nPeriod: {period}"

                await tg_send(
                    ADMIN_CHAT_ID,
                    msg
                )

            if winning_popup(text):
                signature = re.sub(
                    r"\s+",
                    " ",
                    text
                )[-700:]

                if signature != last_popup_signature:
                    last_popup_signature = signature

                    await asyncio.sleep(
                        SCREENSHOT_DELAY
                    )

                    await send_current_screen(
                        "Winning/result popup screenshot "
                        "(demo tracker, mobile layout)"
                    )

            await asyncio.sleep(POLL_SECONDS)

    except asyncio.CancelledError:
        log.info("Tracker stopped.")
    except Exception as exc:
        log.exception("Tracker failed")
        try:
            await tg_send(
                ADMIN_CHAT_ID,
                f"Tracker error:\n{type(exc).__name__}: {exc}"
            )
        except Exception:
            pass
    finally:
        await close_browser()


async def start_tracker():
    global tracker_task

    if tracker_task and not tracker_task.done():
        return False

    tracker_task = asyncio.create_task(tracker())
    return True


async def stop_tracker():
    global tracker_task

    if tracker_task and not tracker_task.done():
        tracker_task.cancel()

        try:
            await tracker_task
        except asyncio.CancelledError:
            pass

    tracker_task = None
    await close_browser()


async def handle_command(chat_id, text):
    global login_phone, login_password

    if not admin_ok(chat_id):
        return

    parts = text.strip().split()

    if not parts:
        return

    command = parts[0].split("@")[0].lower()

    if command == "/start":
        await tg_send(
            chat_id,
            "YaarWin Demo Tracker\n\n"
            "/setlogin NUMBER PASSWORD\n"
            "/run\n"
            "/stop\n"
            "/status\n"
            "/screenshot\n\n"
            "This version only logs in, opens WinGo 1M, "
            "reads visible results and sends screenshots."
        )

    elif command == "/setlogin":
        if len(parts) != 3:
            await tg_send(
                chat_id,
                "Use:\n/setlogin DEMO_NUMBER DEMO_PASSWORD"
            )
            return

        login_phone = parts[1]
        login_password = parts[2]

        await tg_send(
            chat_id,
            "Demo login saved in memory.\n"
            "Now use /run"
        )

    elif command == "/run":
        started = await start_tracker()

        if started:
            await tg_send(
                chat_id,
                "Tracker started."
            )
        else:
            await tg_send(
                chat_id,
                "Tracker is already running."
            )

    elif command == "/stop":
        await stop_tracker()
        await tg_send(
            chat_id,
            "Tracker stopped."
        )

    elif command == "/status":
        running = bool(
            tracker_task
            and not tracker_task.done()
        )

        await tg_send(
            chat_id,
            f"Running: {running}\n"
            f"Last period: {last_period}\n"
            f"Last result: {last_result}"
        )

    elif command == "/screenshot":
        if not page:
            await tg_send(
                chat_id,
                "Browser is not running. Use /run first."
            )
            return

        try:
            await send_current_screen(
                "Current WinGo mobile screen"
            )
        except Exception as exc:
            await tg_send(
                chat_id,
                f"Screenshot error: {exc}"
            )


async def telegram_polling():
    offset = None

    await tg_send(
        ADMIN_CHAT_ID,
        "Demo tracker bot is online."
    )

    while True:
        try:
            params = {
                "timeout": 25,
                "allowed_updates": json.dumps(["message"])
            }

            if offset is not None:
                params["offset"] = offset

            result = await tg_call(
                "getUpdates",
                params
            )

            for update in result.get("result", []):
                offset = update["update_id"] + 1

                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")

                text = message.get("text", "")

                if chat_id and text:
                    await handle_command(
                        chat_id,
                        text
                    )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            log.exception(
                "Telegram polling error: %s",
                exc
            )
            await asyncio.sleep(3)


async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing.")

    if not ADMIN_CHAT_ID:
        raise SystemExit("ADMIN_CHAT_ID is missing.")

    await telegram_polling()


if __name__ == "__main__":
    asyncio.run(main())
