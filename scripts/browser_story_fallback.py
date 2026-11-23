#!/usr/bin/env python3
"""Best-effort anonymous browser fallback for public AI chat pages.

This module intentionally uses a fresh, empty browser context for every site.
It never loads saved cookies, storage state, credentials, or a user profile.
Sites that require sign-in, CAPTCHA, or human verification are skipped.
"""
import re
import time
from urllib.parse import urlparse


SITES = (
    {
        "name": "ChatGPT",
        "url": "https://chatgpt.com/",
        "inputs": (
            "#prompt-textarea",
            "[data-testid='prompt-textarea']",
            "textarea",
            "[contenteditable='true'][role='textbox']",
            "[contenteditable='true']",
            "[role='textbox']",
        ),
        "responses": (
            "[data-message-author-role='assistant']",
            "[data-testid*='conversation-turn'][data-testid*='assistant']",
        ),
    },
    {
        "name": "Gemini",
        "url": "https://gemini.google.com/app",
        "inputs": (
            "rich-textarea [contenteditable='true']",
            "rich-textarea textarea",
            "textarea",
            "[contenteditable='true'][role='textbox']",
            "[contenteditable='true']",
            "[role='textbox']",
        ),
        "responses": (
            "model-response",
            ".model-response-text",
            "[data-message-author-role='assistant']",
        ),
    },
    {
        "name": "Microsoft Copilot",
        "url": "https://copilot.microsoft.com/",
        "inputs": (
            "textarea#userInput",
            "textarea",
            "[contenteditable='true'][role='textbox']",
            "[contenteditable='true']",
            "[role='textbox']",
        ),
        "responses": (
            "cib-message-group[author='bot']",
            "[data-testid*='bot-response']",
            ".response-message-group",
        ),
    },
    {
        "name": "Meta AI",
        "url": "https://www.meta.ai/",
        "inputs": (
            "textarea",
            "[contenteditable='true'][role='textbox']",
            "[contenteditable='true']",
            "[role='textbox']",
        ),
        "responses": (
            "[data-testid*='message']",
            "[role='article']",
            "main",
        ),
    },
)

LOGIN_TEXT = (
    "sign in to continue",
    "log in to continue",
    "sign in to use",
    "you must sign in",
    "please sign in",
    "create an account to continue",
)
CHALLENGE_TEXT = (
    "verify you are human",
    "complete the security check",
    "unusual traffic",
    "are you a robot",
    "captcha",
)


def _page_block_reason(page):
    """Return why a public page must be skipped, without attempting a bypass."""
    url = (page.url or "").lower()
    path = urlparse(url).path.lower()
    if any(part in path for part in ("/login", "/signin", "/sign-in", "/auth/")):
        return "redirected to a sign-in/authentication page"
    try:
        body = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        body = ""
    if any(phrase in body for phrase in CHALLENGE_TEXT):
        return "requires CAPTCHA or human verification"
    if any(phrase in body for phrase in LOGIN_TEXT):
        return "requires sign-in"
    if "accounts.google.com" in url or "login.live.com" in url:
        return "redirected to an account login"
    return ""


def _visible_input(page, selectors):
    for selector in selectors:
        try:
            matches = page.locator(selector)
            for index in range(min(matches.count(), 8)):
                item = matches.nth(index)
                if item.is_visible() and item.is_editable():
                    return item
        except Exception:
            continue
    return None


def _submit_prompt(page, textbox, prompt):
    textbox.fill(prompt)
    try:
        textbox.press("Enter", timeout=5000)
        return
    except Exception:
        pass
    for selector in (
        "button[aria-label*='send' i]",
        "button[data-testid*='send']",
        "button[title*='send' i]",
        "button[type='submit']",
    ):
        try:
            button = page.locator(selector).last
            if button.is_visible() and button.is_enabled():
                button.click(timeout=5000)
                return
        except Exception:
            continue
    raise RuntimeError("Could not submit the prompt using the page's visible chat controls.")


def _assistant_text(page, selectors, prompt):
    for selector in selectors:
        try:
            items = page.locator(selector)
            count = items.count()
            for index in range(count - 1, max(-1, count - 5), -1):
                text = items.nth(index).inner_text(timeout=3000).strip()
                if len(text) >= 200 and (text.lstrip().startswith("{") or '"scenes"' in text):
                    return text
        except Exception:
            continue

    # Last-resort extraction from the visible page, limited to text after the
    # submitted prompt. The normal assistant-message selectors are preferred.
    try:
        visible = page.locator("main").inner_text(timeout=5000)
    except Exception:
        visible = page.locator("body").inner_text(timeout=5000)
    position = visible.rfind(prompt[:160])
    if position >= 0:
        visible = visible[position + min(len(prompt), 160):]
    visible = visible.strip()
    if len(visible) >= 200 and ('"scenes"' in visible or visible.lstrip().startswith("{")):
        return visible
    return ""


def _try_site(browser, site, prompt, timeout_seconds):
    context = browser.new_context(
        locale="en-US",
        viewport={"width": 1440, "height": 1000},
    )
    page = context.new_page()
    page.set_default_timeout(12000)
    try:
        print(f"Anonymous browser fallback: opening {site['name']} ({site['url']}).", flush=True)
        page.goto(site["url"], wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)

        blocked = _page_block_reason(page)
        if blocked:
            raise RuntimeError(blocked)

        textbox = _visible_input(page, site["inputs"])
        if textbox is None:
            raise RuntimeError("no usable public chat input was found")

        _submit_prompt(page, textbox, prompt)
        print(f"{site['name']}: prompt submitted; waiting for a complete response.", flush=True)

        deadline = time.monotonic() + timeout_seconds
        previous = ""
        stable_polls = 0
        best = ""
        while time.monotonic() < deadline:
            page.wait_for_timeout(4000)
            blocked = _page_block_reason(page)
            if blocked:
                raise RuntimeError(blocked)
            current = _assistant_text(page, site["responses"], prompt)
            if len(current) > len(best):
                best = current
            if current and current == previous and len(current) >= 200:
                stable_polls += 1
            elif current:
                stable_polls = 0
            previous = current
            if stable_polls >= 3:
                return current
        if best and len(best) >= 200:
            return best
        raise TimeoutError(f"no usable assistant response arrived within {timeout_seconds} seconds")
    finally:
        context.close()


def generate_story_anonymously(prompt, timeout_seconds=150, validator=None):
    """Try public AI chat pages in order; optionally validate before accepting output."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(
            "Playwright is unavailable; anonymous browser fallback cannot start."
        ) from exc

    failures = []
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            raise RuntimeError(
                "Chromium is not installed for Playwright; anonymous browser fallback cannot start."
            ) from exc
        try:
            for site in SITES:
                try:
                    response = _try_site(browser, site, prompt, timeout_seconds)
                    if response:
                        accepted = response
                        if validator is not None:
                            try:
                                accepted = validator(response)
                            except Exception as exc:
                                raise ValueError(
                                    f"response from {site['name']} failed story validation: "
                                    f"{type(exc).__name__}: {str(exc)[:220]}"
                                ) from exc
                        print(
                            f"Anonymous browser fallback succeeded with {site['name']}.",
                            flush=True,
                        )
                        return accepted
                except Exception as exc:
                    reason = f"{site['name']}: {type(exc).__name__}: {str(exc)[:250]}"
                    failures.append(reason)
                    print(f"Anonymous browser fallback skipped {reason}", flush=True)
        finally:
            browser.close()

    raise RuntimeError(
        "All anonymous browser AI websites failed or required sign-in/verification. "
        + " | ".join(failures)
    )
