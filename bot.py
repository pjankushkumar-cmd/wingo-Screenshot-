import asyncio
import logging
import os
import re

from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# =========================================================
# CONFIG
# =========================================================

SITE_URL = os.getenv(
    "SITE_URL",
    "https://yaarwin.app/#/login"
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")

# Optional Render environment login
DEMO_PHONE = os.getenv("DEMO_PHONE", "")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")

HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"

POLL_SECONDS = float(
    os.getenv("POLL_SECONDS", "1.5")
)

WIN_SCREENSHOT_DELAY = int(
    os.getenv("WIN_SCREENSHOT_DELAY", "10")
)

# Runtime login credentials.
# Telegram /setlogin can update these.
login_phone = DEMO_PHONE
login_password = DEMO_PASSWORD

# =========================================================
# GLOBALS
# =========================================================

browser = None
page = None
playwright_instance = None

tracker_task = None

last_result = None
last_win_signature = None


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("YaarWinDemoTracker")


# =========================================================
# ADMIN CHECK
# =========================================================

def get_admin_id():
    try:
        return int(ADMIN_CHAT_ID)
    except Exception:
        return None


def is_admin(update: Update):
    admin = get_admin_id()

    if not admin:
        return False

    if not update.effective_chat:
        return False

    return update.effective_chat.id == admin


# =========================================================
# TELEGRAM MESSAGE
# =========================================================

async def send_admin_text(text):
    admin = get_admin_id()

    if not admin:
        logger.warning("ADMIN_CHAT_ID is not configured.")
        return

    try:
        application = Application.builder().token(
            BOT_TOKEN
        ).build()

        async with application:
            await application.bot.send_message(
                chat_id=admin,
                text=text
            )

    except Exception as e:
        logger.error(
            "Telegram text error: %s",
            e
        )


# =========================================================
# LOGIN
# =========================================================

async def login():

    global browser
    global page
    global playwright_instance
    global login_phone
    global login_password

    if not login_phone or not login_password:
        raise RuntimeError(
            "Demo login is not configured. "
            "Use /setlogin NUMBER PASSWORD first."
        )

    logger.info("Starting browser...")

    playwright_instance = await async_playwright().start()

    browser = await playwright_instance.chromium.launch(
        headless=HEADLESS,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu"
        ]
    )

    context = await browser.new_context(
        viewport={
            "width": 430,
            "height": 900
        }
    )

    page = await context.new_page()

    logger.info(
        "Opening site: %s",
        SITE_URL
    )

    await page.goto(
        SITE_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    await page.wait_for_timeout(3000)

    # -----------------------------------------------------
    # PHONE FIELD
    # -----------------------------------------------------

    phone_selectors = [

        'input[type="tel"]',

        'input[placeholder*="phone" i]',

        'input[placeholder*="mobile" i]',

        'input[placeholder*="number" i]',

        'input[name*="phone" i]',

        'input[name*="mobile" i]',

        'input[name*="username" i]',

    ]

    phone = None

    for selector in phone_selectors:

        try:

            locator = page.locator(
                selector
            ).first

            if await locator.count():

                phone = locator
                break

        except Exception:
            continue

    # -----------------------------------------------------
    # PASSWORD FIELD
    # -----------------------------------------------------

    password_selectors = [

        'input[type="password"]',

        'input[placeholder*="password" i]',

        'input[name*="password" i]',

    ]

    password = None

    for selector in password_selectors:

        try:

            locator = page.locator(
                selector
            ).first

            if await locator.count():

                password = locator
                break

        except Exception:
            continue

    if not phone or not password:

        await page.screenshot(
            path="login_debug.png",
            full_page=True
        )

        raise RuntimeError(
            "Login fields were not found. "
            "login_debug.png was created."
        )

    # -----------------------------------------------------
    # FILL LOGIN
    # -----------------------------------------------------

    await phone.fill(
        login_phone
    )

    await password.fill(
        login_password
    )

    logger.info(
        "Demo credentials entered."
    )

    # -----------------------------------------------------
    # LOGIN BUTTON
    # -----------------------------------------------------

    login_buttons = [

        page.get_by_role(
            "button",
            name=re.compile(
                r"login|log in|sign in",
                re.I
            )
        ),

        page.locator(
            'button[type="submit"]'
        ),

        page.locator(
            'input[type="submit"]'
        ),

    ]

    clicked = False

    for locator in login_buttons:

        try:

            if await locator.count():

                await locator.first.click()

                clicked = True

                break

        except Exception:
            continue

    if not clicked:

        raise RuntimeError(
            "Login button was not found."
        )

    await page.wait_for_timeout(
        5000
    )

    logger.info(
        "Login completed."
    )


# =========================================================
# FIND WINGO
# =========================================================

async def find_wingo():

    patterns = [

        re.compile(
            r"win\s*go",
            re.I
        ),

        re.compile(
            r"wingo",
            re.I
        ),

    ]

    # Try buttons and links
    for pattern in patterns:

        for role in [
            "button",
            "link"
        ]:

            try:

                locator = page.get_by_role(
                    role,
                    name=pattern
                ).first

                if await locator.count():

                    await locator.click()

                    await page.wait_for_timeout(
                        2500
                    )

                    logger.info(
                        "WinGo section opened."
                    )

                    return True

            except Exception:
                continue

    # Text fallback
    try:

        locator = page.get_by_text(
            re.compile(
                r"win\s*go",
                re.I
            )
        ).first

        if await locator.count():

            await locator.click()

            await page.wait_for_timeout(
                2500
            )

            return True

    except Exception:
        pass

    logger.warning(
        "WinGo section was not found."
    )

    return False


# =========================================================
# SELECT 1 MINUTE
# =========================================================

async def select_one_minute():

    patterns = [

        re.compile(
            r"1\s*minute",
            re.I
        ),

        re.compile(
            r"1\s*min",
            re.I
        ),

    ]

    for pattern in patterns:

        for role in [
            "button",
            "link"
        ]:

            try:

                locator = page.get_by_role(
                    role,
                    name=pattern
                ).first

                if await locator.count():

                    await locator.click()

                    await page.wait_for_timeout(
                        1000
                    )

                    logger.info(
                        "1-minute mode selected."
                    )

                    return True

            except Exception:
                continue

    logger.warning(
        "1-minute selector was not found."
    )

    return False


# =========================================================
# PAGE TEXT
# =========================================================

async def get_page_text():

    try:

        return await page.locator(
            "body"
        ).inner_text(
            timeout=10000
        )

    except Exception:

        return ""


# =========================================================
# RESULT DETECTOR
# =========================================================

def extract_result(text):

    # Example:
    # Result: 7
    # Winning Number: 3

    patterns = [

        r"(?:result|winning\s*number|winning|number)"
        r"\s*[:\-]?\s*([0-9])\b",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            return match.group(1)

    # Search line by line
    for line in text.splitlines():

        if re.search(
            r"result|winning|period",
            line,
            re.I
        ):

            numbers = re.findall(
                r"\b([0-9])\b",
                line
            )

            if numbers:

                return numbers[-1]

    return None


# =========================================================
# WINNING POPUP DETECTOR
# =========================================================

def winning_popup_visible(text):

    keywords = [

        r"\bwin\b",

        r"\bwinning\b",

        r"\bcongratulations\b",

        r"you\s+win",

        r"\bwinner\b",

    ]

    for keyword in keywords:

        if re.search(
            keyword,
            text,
            re.I
        ):

            return True

    return False


# =========================================================
# SCREENSHOT
# =========================================================

async def send_winning_screenshot():

    admin = get_admin_id()

    if not admin:
        return

    screenshot_path = (
        "winning_popup.png"
    )

    try:

        await page.screenshot(
            path=screenshot_path,
            full_page=False
        )

        application = (
            Application
            .builder()
            .token(BOT_TOKEN)
            .build()
        )

        async with application:

            with open(
                screenshot_path,
                "rb"
            ) as photo:

                await application.bot.send_photo(
                    chat_id=admin,
                    photo=photo,
                    caption=(
                        "Winning popup screenshot "
                        "(demo tracker)"
                    )
                )

        logger.info(
            "Winning screenshot sent."
        )

    except Exception as e:

        logger.error(
            "Screenshot error: %s",
            e
        )


# =========================================================
# TRACKER
# =========================================================

async def tracker_loop():

    global last_result
    global last_win_signature

    try:

        if not page:

            await login()

        # Open WinGo
        await find_wingo()

        # Select 1-minute
        await select_one_minute()

        logger.info(
            "Tracking started."
        )

        while True:

            try:

                text = await get_page_text()

                # -----------------------------------------
                # RESULT
                # -----------------------------------------

                result = extract_result(
                    text
                )

                if (
                    result is not None
                    and result != last_result
                ):

                    last_result = result

                    logger.info(
                        "Detected result: %s",
                        result
                    )

                    await send_admin_text(
                        "WinGo 1-minute result detected: "
                        f"{result}"
                    )

                # -----------------------------------------
                # WINNING POPUP
                # -----------------------------------------

                if winning_popup_visible(
                    text
                ):

                    signature = re.sub(
                        r"\s+",
                        " ",
                        text
                    )[-500:]

                    if (
                        signature
                        != last_win_signature
                    ):

                        last_win_signature = (
                            signature
                        )

                        logger.info(
                            "Winning popup detected. "
                            "Waiting %s seconds.",
                            WIN_SCREENSHOT_DELAY
                        )

                        await asyncio.sleep(
                            WIN_SCREENSHOT_DELAY
                        )

                        await send_winning_screenshot()

                await asyncio.sleep(
                    POLL_SECONDS
                )

            except asyncio.CancelledError:

                raise

            except Exception as e:

                logger.exception(
                    "Tracker loop error: %s",
                    e
                )

                await asyncio.sleep(
                    3
                )

    except asyncio.CancelledError:

        logger.info(
            "Tracker task stopped."
        )

    except Exception as e:

        logger.exception(
            "Tracker failed: %s",
            e
        )


# =========================================================
# START TRACKER
# =========================================================

async def start_tracker():

    global tracker_task

    if (
        tracker_task
        and not tracker_task.done()
    ):

        return False

    tracker_task = asyncio.create_task(
        tracker_loop()
    )

    return True


# =========================================================
# /START
# =========================================================

async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    await update.message.reply_text(
        "YaarWin Demo Tracker\n\n"
        "/setlogin NUMBER PASSWORD\n"
        "/run\n"
        "/stop\n"
        "/status\n"
        "/screenshot\n\n"
        "Tracker only reads the demo page "
        "and sends result/screenshot updates."
    )


# =========================================================
# /SETLOGIN
# =========================================================

async def cmd_setlogin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global login_phone
    global login_password

    if not is_admin(update):
        return

    if len(context.args) != 2:

        await update.message.reply_text(
            "Format:\n"
            "/setlogin DEMO_NUMBER DEMO_PASSWORD"
        )

        return

    login_phone = context.args[0]

    login_password = context.args[1]

    await update.message.reply_text(
        "Demo login saved for this running bot.\n\n"
        "Now use /run"
    )


# =========================================================
# /RUN
# =========================================================

async def cmd_run(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    started = await start_tracker()

    if started:

        await update.message.reply_text(
            "Demo tracker started.\n\n"
            "Login → WinGo 1 Minute → "
            "result tracking → "
            "winning screenshot."
        )

    else:

        await update.message.reply_text(
            "Tracker is already running."
        )


# =========================================================
# /STOP
# =========================================================

async def cmd_stop(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    global tracker_task

    if not is_admin(update):
        return

    if tracker_task:

        tracker_task.cancel()

        tracker_task = None

        await update.message.reply_text(
            "Tracker stopped."
        )

    else:

        await update.message.reply_text(
            "Tracker is not running."
        )


# =========================================================
# /STATUS
# =========================================================

async def cmd_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    running = bool(
        tracker_task
        and not tracker_task.done()
    )

    await update.message.reply_text(
        "Tracker Status\n\n"
        f"Running: {running}\n"
        f"Last result: {last_result}\n"
        f"Screenshot delay: "
        f"{WIN_SCREENSHOT_DELAY}s\n"
        f"Poll interval: "
        f"{POLL_SECONDS}s"
    )


# =========================================================
# /SCREENSHOT
# =========================================================

async def cmd_screenshot(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if not page:

        await update.message.reply_text(
            "Browser is not running.\n"
            "Use /run first."
        )

        return

    path = "manual_screenshot.png"

    try:

        await page.screenshot(
            path=path,
            full_page=False
        )

        with open(
            path,
            "rb"
        ) as photo:

            await update.message.reply_photo(
                photo=photo,
                caption=(
                    "Current demo tracker screen"
                )
            )

    except Exception as e:

        await update.message.reply_text(
            f"Screenshot error: {e}"
        )


# =========================================================
# TELEGRAM POST INIT
# =========================================================

async def post_init(
    application: Application
):

    # Don't auto-start if no login credentials exist.
    # Set them with /setlogin and then use /run.
    if login_phone and login_password:

        logger.info(
            "Login credentials found. "
            "Use /run to start tracker."
        )


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:

        raise SystemExit(
            "BOT_TOKEN is missing."
        )

    if not ADMIN_CHAT_ID:

        raise SystemExit(
            "ADMIN_CHAT_ID is missing."
        )

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            cmd_start
        )
    )

    application.add_handler(
        CommandHandler(
            "setlogin",
            cmd_setlogin
        )
    )

    application.add_handler(
        CommandHandler(
            "run",
            cmd_run
        )
    )

    application.add_handler(
        CommandHandler(
            "stop",
            cmd_stop
        )
    )

    application.add_handler(
        CommandHandler(
            "status",
            cmd_status
        )
    )

    application.add_handler(
        CommandHandler(
            "screenshot",
            cmd_screenshot
        )
    )

    logger.info(
        "Telegram bot starting..."
    )

    application.run_polling(
        close_loop=False
    )


# =========================================================
# ENTRY
# =========================================================

if __name__ == "__main__":
    main()
