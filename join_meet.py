import asyncio
import os
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


ENV_PATH = Path(".env")
DEBUG_DIR = Path("debug")
USER_DATA_DIR = Path("./chrome-meet-profile")
REJECTION_DEBUG_WAIT_MS = 120000

REJECTION_MESSAGES = [
    "You can't join this video call",
    "No one can join a meeting unless invited or admitted by the host",
    "Someone in this call denied your request to join",
    "Your request to join was denied",
]

JOIN_BUTTON_NAMES = [
    "Ask to join",
    "Join now",
    "Request to join",
    "Join",
]

MEDIA_MODAL_BUTTONS = [
    "Continue without microphone and camera",
    "Continue without mic and camera",
    "Use microphone and camera",
]


def load_dotenv():
    if not ENV_PATH.exists():
        return

    for raw_line in ENV_PATH.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')

        if key and key not in os.environ:
            os.environ[key] = value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return int(value)


def log(message):
    print(f"[meet-agent] {message}")


load_dotenv()

MEET_URL = os.environ.get("GMEET_URL")
DISPLAY_NAME = os.environ.get("GMEET_DISPLAY_NAME", "Orbit Agent")
WAIT_AFTER_JOIN_MS = env_int("GMEET_WAIT_AFTER_JOIN_MS", 120000)
HEADLESS = env_bool("HEADLESS", False)


async def save_debug_artifacts(page, reason):
    DEBUG_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_reason = re.sub(r"[^a-z0-9-]+", "-", reason.lower()).strip("-")
    base_path = DEBUG_DIR / f"{timestamp}-{safe_reason}"
    screenshot_path = base_path.with_suffix(".png")
    html_path = base_path.with_suffix(".html")

    await page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(await page.content())

    log(f"Saved debug screenshot: {screenshot_path}")
    log(f"Saved debug HTML: {html_path}")


async def visible_text(page, text):
    try:
        return await page.get_by_text(text, exact=False).first.is_visible()
    except Exception:
        return False


async def detect_rejection(page):
    for message in REJECTION_MESSAGES:
        if await visible_text(page, message):
            return message
    return None


async def handle_rejection(page, message):
    log(f"Rejected by Google Meet: {message}")
    log(
        "This script does not bypass Google security. The meeting likely blocks "
        "guests, requires host admission, or requires an invited/signed-in account."
    )
    await save_debug_artifacts(page, "meet-rejected")
    log(f"Keeping browser open for {REJECTION_DEBUG_WAIT_MS // 1000} seconds.")
    await page.wait_for_timeout(REJECTION_DEBUG_WAIT_MS)


async def click_first_visible_role_button(page, names, timeout_ms=1500):
    for name in names:
        button = page.get_by_role("button", name=name).first
        try:
            await button.wait_for(state="visible", timeout=timeout_ms)
            await button.click()
            return name
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    return None


async def click_first_visible_selector(page, selectors):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.is_visible():
                await locator.click()
                return selector
        except Exception:
            continue
    return None


async def fill_guest_name(page):
    selectors = [
        'input[aria-label="Your name"]',
        'input[placeholder="Your name"]',
        'input[type="text"]',
    ]

    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.is_visible():
                await locator.fill(DISPLAY_NAME)
                log(f"Name filled: {DISPLAY_NAME}")
                return True
        except Exception:
            continue

    log("Name input not found or not required.")
    return False


async def handle_media_modal(page):
    try:
        modal_visible = await visible_text(
            page, "Do you want people to see and hear you in the meeting?"
        )
        if not modal_visible:
            log("Mic/camera modal not shown.")
            return False

        clicked = await click_first_visible_role_button(page, MEDIA_MODAL_BUTTONS)
        if clicked:
            log(f"Mic/camera modal handled: {clicked}")
            return True

        log("Mic/camera modal shown, but no expected button was clickable.")
        return False
    except Exception as error:
        log(f"Mic/camera modal handling skipped: {error}")
        return False


async def turn_off_prejoin_media(page):
    selectors = [
        '[aria-label*="Turn off microphone"]',
        '[aria-label*="Turn off camera"]',
    ]
    clicked_selector = await click_first_visible_selector(page, selectors)
    if clicked_selector:
        log("Pre-join mic/camera toggle clicked.")
    else:
        log("Pre-join mic/camera toggles not found or already off.")


async def click_join_button(page):
    clicked = await click_first_visible_role_button(page, JOIN_BUTTON_NAMES)
    if clicked:
        log(f"Join button clicked: {clicked}")
        return True

    clicked_selector = await click_first_visible_selector(
        page,
        [
            'button:has-text("Ask to join")',
            'button:has-text("Join now")',
            'button:has-text("Request to join")',
            'button:has-text("Join")',
            'div[role="button"]:has-text("Ask to join")',
            'div[role="button"]:has-text("Join now")',
            'div[role="button"]:has-text("Request to join")',
            'div[role="button"]:has-text("Join")',
        ],
    )
    if clicked_selector:
        log(f"Join button clicked by selector: {clicked_selector}")
        return True

    log("Join button not found.")
    return False


async def wait_after_join(page):
    log(f"Waiting {WAIT_AFTER_JOIN_MS // 1000} seconds after join request.")
    deadline = asyncio.get_running_loop().time() + (WAIT_AFTER_JOIN_MS / 1000)

    while asyncio.get_running_loop().time() < deadline:
        rejection = await detect_rejection(page)
        if rejection:
            await handle_rejection(page, rejection)
            return

        leave_button = page.get_by_role("button", name="Leave call").first
        try:
            if await leave_button.is_visible():
                log("Joined meeting successfully.")
                return
        except Exception:
            pass

        if await visible_text(page, "Asking to be let in"):
            log("Waiting in lobby for host admission.")

        await page.wait_for_timeout(3000)

    log("Finished wait window. Browser will close normally.")


async def join_meet(page):
    log(f"Opening Meet URL: {MEET_URL}")
    await page.goto(MEET_URL, wait_until="domcontentloaded")
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        log("Network idle timed out; continuing with current page state.")

    log("Page loaded.")
    await page.wait_for_timeout(2000)

    await handle_media_modal(page)

    rejection = await detect_rejection(page)
    if rejection:
        await handle_rejection(page, rejection)
        return

    await fill_guest_name(page)
    await turn_off_prejoin_media(page)

    joined = await click_join_button(page)
    if not joined:
        await save_debug_artifacts(page, "join-button-not-found")
        log("Cannot continue because no supported Meet join button was found.")
        log("Keeping browser open for 2 minutes for inspection.")
        await page.wait_for_timeout(REJECTION_DEBUG_WAIT_MS)
        return

    await wait_after_join(page)


async def main():
    if not MEET_URL:
        raise RuntimeError("Missing GMEET_URL in .env or environment.")

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            channel="chrome",
            headless=HEADLESS,
            viewport={"width": 1440, "height": 960},
            permissions=["camera", "microphone"],
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )

        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await join_meet(page)
        finally:
            log("Closing browser context.")
            await context.close()


if __name__ == "__main__":
    asyncio.run(main())
