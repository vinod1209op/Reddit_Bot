"""
Purpose: Selenium reply helper utilities (old Reddit only).
Constraints: UI interactions only; posting decisions happen elsewhere.
"""

# Imports
import logging
import time
from typing import Optional, Sequence

# Constants
logger = logging.getLogger(__name__)

# Helpers
def _safe_import_by():
    try:
        from selenium.webdriver.common.by import By  # type: ignore
        return By
    except Exception:
        return None


def _candidate_selectors() -> Sequence[str]:
    return (
        "textarea[name='text']",
        "textarea#comment",
        "textarea",
        "div[data-testid='commenttextarea']",
        "div[role='textbox'][data-testid='commenttextarea']",
        "div[contenteditable='true'][data-testid='commenttextarea']",
        "div[contenteditable='true'][aria-label*='comment']",
        "div[contenteditable='true'][role='textbox']",
    )


def dump_comment_debug(driver) -> None:
    """Log a compact snapshot of likely comment elements."""
    By = _safe_import_by()
    if not By:
        return
    snapshot = []
    for sel in _candidate_selectors():
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            snapshot.append((sel, len(elems)))
        except Exception as e:
            snapshot.append((sel, f"error: {e}"))
    logger.info("Comment debug snapshot: " + "; ".join([f"{s}:{c}" for s, c in snapshot]))


def focus_comment_box(driver) -> None:
    """Scroll and focus the old Reddit comment textarea if present."""
    By = _safe_import_by()
    if not By:
        return
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(0.5)
    except Exception:
        pass

    for selector in _candidate_selectors():
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elems:
                if el.is_displayed() and el.is_enabled():
                    if _try_click(driver, el):
                        time.sleep(0.3)
                        dump_comment_debug(driver)
                        return
        except Exception:
            continue


def find_comment_area(driver) -> Optional[object]:
    """Locate a writable comment area (old Reddit)."""
    By = _safe_import_by()
    if not By:
        return None
    for selector in _candidate_selectors():
        try:
            elem = driver.find_element(By.CSS_SELECTOR, selector)
            if elem.is_displayed():
                return elem
        except Exception:
            continue
    return None


def js_find_comment_box(driver) -> Optional[object]:
    """Find a comment box via JS querySelector."""
    try:
        return driver.execute_script(
            """
const selectors = arguments[0];
for (const sel of selectors) {
  const el = document.querySelector(sel);
  if (el) return el;
}
return null;
            """,
            list(_candidate_selectors()),
        )
    except Exception:
        return None


def js_set_comment_text(driver, text: str) -> bool:
    """Set comment text using JavaScript."""
    element = js_find_comment_box(driver)
    if not element:
        return False
    try:
        driver.execute_script(
            """
const el = arguments[0];
const text = arguments[1];
if (el.value !== undefined) {
  el.value = text;
  el.dispatchEvent(new Event('input', {bubbles: true}));
  return true;
}
el.textContent = text;
el.dispatchEvent(new Event('input', {bubbles: true}));
return true;
            """,
            element,
            text,
        )
        return True
    except Exception:
        return False


def js_force_set_comment_text(driver, text: str) -> bool:
    """Force-set comment text using JS and focus events."""
    element = js_find_comment_box(driver)
    if not element:
        return False
    try:
        driver.execute_script(
            """
const el = arguments[0];
const text = arguments[1];
el.focus();
if (el.value !== undefined) {
  el.value = text;
} else {
  el.textContent = text;
}
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            element,
            text,
        )
        return True
    except Exception:
        return False


def js_fill_composer_strict(driver, text: str) -> bool:
    """Compatibility stub for modern UI helper (unused on old Reddit)."""
    return js_force_set_comment_text(driver, text)


def js_paste_comment_text(driver, text: str) -> bool:
    """Compatibility stub for modern UI helper (unused on old Reddit)."""
    return js_set_comment_text(driver, text)


def get_composer_text(driver) -> str:
    """Read current text from the comment box."""
    element = js_find_comment_box(driver)
    if not element:
        return ""
    try:
        return driver.execute_script(
            """
const el = arguments[0];
if (!el) return '';
if (el.value !== undefined) return el.value || '';
return el.innerText || el.textContent || '';
            """,
            element,
        ) or ""
    except Exception:
        return ""


def js_read_comment_text(driver) -> str:
    """Alias for get_composer_text for compatibility."""
    return get_composer_text(driver)


def get_composer_element(driver):
    """Expose a single element handle for fill routines."""
    return find_comment_area(driver) or js_find_comment_box(driver)


def _normalize_text_for_compare(text: str) -> str:
    return " ".join((text or "").split())


def fill_modern_reddit_comment(driver, text: str) -> bool:
    """Fill the old Reddit textarea (kept name for compatibility)."""
    if not text:
        return False
    return js_set_comment_text(driver, text) or js_force_set_comment_text(driver, text)


def keystroke_fill_simple(driver, element, text: str) -> bool:
    """Type using Selenium send_keys."""
    if not element:
        return False
    try:
        element.clear()
        element.send_keys(text)
        return True
    except Exception:
        return False


def js_open_comment_composer(driver) -> None:
    """Scroll toward the comment box on old Reddit."""
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
    except Exception:
        pass


def js_submit_comment(driver) -> bool:
    """Attempt to submit the comment form."""
    try:
        return driver.execute_script(
            """
const textarea = document.querySelector("textarea[name='text'], textarea#comment, textarea");
if (!textarea) return false;
const form = textarea.closest('form');
if (!form) return false;
const btn = form.querySelector("button[type='submit'], input[type='submit']");
if (btn) { btn.click(); return true; }
form.submit();
return true;
            """
        )
    except Exception:
        return False


def submit_via_buttons(driver) -> bool:
    """Fallback submit using Selenium element search."""
    By = _safe_import_by()
    if not By:
        return False
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                if _try_click(driver, btn):
                    return True
    except Exception:
        pass
    return False


def fill_comment_box(driver, element, text: str) -> bool:
    """Fill comment box by JS or keystrokes."""
    return keystroke_fill_simple(driver, element, text)


def fill_comment_box_via_keystrokes(driver, element, text: str) -> bool:
    """Compatibility wrapper for keystroke filling."""
    return keystroke_fill_simple(driver, element, text)


def _try_click(driver, el) -> bool:
    try:
        el.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
            return True
        except Exception:
            return False
