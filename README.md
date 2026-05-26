# Google Meet Playwright Agent

Minimal Python agent that uses Playwright to join a Google Meet as a guest.

## What it does

- Opens a fresh Chrome browser
- Navigates to a Meet URL
- Fills your guest display name
- Turns off mic and camera on the pre-join screen
- Clicks the Meet join button

## Setup

1. Create a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   python -m playwright install chromium
   ```

3. Edit `.env`:

   ```bash
   GMEET_URL=https://meet.google.com/your-meeting-code
   GMEET_DISPLAY_NAME=Orbit
   GMEET_WAIT_AFTER_JOIN_MS=120000
   HEADLESS=false
   ```

4. Use a guest-join Meet link that shows a name field and `Ask to join` or `Join now`.

## Run

```bash
source .venv/bin/activate
python join_meet.py
```

## Notes

- This relies on Google Meet's current DOM and button labels. UI changes will require selector updates.
- `channel="chrome"` expects Google Chrome to be installed locally.
- Some meetings require host approval. In those cases the script waits for `GMEET_WAIT_AFTER_JOIN_MS` so the host can admit the guest.
- Some organizations require a signed-in Google account. This script is for guest-access meetings like the one you showed.
