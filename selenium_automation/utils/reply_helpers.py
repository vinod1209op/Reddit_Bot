"""
Reply helper utilities for Selenium-based comment posting.
Handles focus/open, DOM traversal (including shadow roots), filling, and submitting.
"""
import time
import logging
from typing import Optional


logger = logging.getLogger(__name__)


def _safe_import_by():
    try:
        from selenium.webdriver.common.by import By  # type: ignore
        return By
    except Exception:
        return None


def dump_comment_debug(driver) -> None:
    """Log a compact snapshot of likely comment elements."""
    By = _safe_import_by()
    if not By:
        return
    selectors = [
        "shreddit-comment-composer",
        "button[data-click-id='comment']",
        "button[aria-label*='comment']",
        "button[aria-label*='reply']",
        "textarea",
        "div[contenteditable='true']",
        "div[role='textbox']",
        "div[data-testid='comment-field']",
        "div[data-test-id='comment-field']",
        "form",
    ]
    snapshot = []
    for sel in selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            snapshot.append((sel, len(elems)))
        except Exception as e:
            snapshot.append((sel, f"error: {e}"))
    logger.info("Comment debug snapshot: " + "; ".join([f"{s}:{c}" for s, c in snapshot]))


def focus_comment_box(driver) -> None:
    """Try to bring the comment composer into focus."""
    By = _safe_import_by()
    if not By:
        return

    try:
        driver.execute_script("window.scrollBy(0, window.innerHeight * 0.4);")
        time.sleep(0.5)
    except Exception:
        pass

    triggers = [
        "button[aria-label*='comment']",
        "button[aria-label*='reply']",
        "div[data-testid='comment-field']",
        "div[data-test-id='comment-field']",
        "div[placeholder*='thoughts']",
        "textarea[placeholder*='thoughts']",
        "textarea[placeholder*='comment']",
        "shreddit-comment-composer",
        "button[data-click-id='comment']",
        "button:contains('Add a comment')",
    ]
    for selector in triggers:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elems:
                if el.is_displayed() and el.is_enabled():
                    clicked = False
                    if ":contains" in selector:
                        if "add a comment" in el.text.lower():
                            clicked = _try_click(driver, el)
                    else:
                        clicked = _try_click(driver, el)
                    if clicked:
                        time.sleep(0.5)
                        dump_comment_debug(driver)
                        return
        except Exception:
            continue

    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.9);")
        time.sleep(0.5)
        elems = driver.find_elements(By.CSS_SELECTOR, "textarea, div[contenteditable='true'], div[role='textbox']")
        for el in elems:
            if el.is_displayed() and _try_click(driver, el):
                time.sleep(0.5)
                dump_comment_debug(driver)
                return
    except Exception:
        pass


def find_comment_area(driver) -> Optional[object]:
    """Locate a writable comment area via standard selectors or shadow DOM."""
    By = _safe_import_by()
    if not By:
        return None

    selectors = [
        "div[contenteditable='true']",
        "div[role='textbox']",
        "textarea",
        "textarea[placeholder*='thoughts']",
        "textarea[placeholder*='comment']",
        "div[placeholder*='thoughts']",
        "div[data-testid='comment-field'] div[contenteditable='true']",
        "div[data-test-id='comment-field'] div[contenteditable='true']",
        "shreddit-comment-composer div[contenteditable='true']",
        "shreddit-comment-composer textarea",
    ]
    for selector in selectors:
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in candidates:
                if el.is_displayed() and el.is_enabled():
                    return el
        except Exception:
            continue

    try:
        shadow_el = driver.execute_script(
            """
const composer = document.querySelector('shreddit-comment-composer');
if (composer && composer.shadowRoot){
  const el = composer.shadowRoot.querySelector('textarea,div[contenteditable="true"],div[role="textbox"]');
  return el;
}
return null;
            """
        )
        if shadow_el:
            return shadow_el
    except Exception:
        pass

    try:
        fallbacks = driver.find_elements(By.CSS_SELECTOR, "textarea, div[contenteditable='true'], div[role='textbox']")
        if fallbacks:
            return fallbacks[0]
    except Exception:
        pass

    return None


def js_find_comment_box(driver) -> Optional[object]:
    """Use JS (including shadow DOM) to locate a visible textarea/textbox."""
    try:
        el = driver.execute_script(
            """
const prioritySelectors = [
  'div[contenteditable="true"][data-lexical-editor="true"]',
  'div[role="textbox"][data-lexical-editor="true"]',
];
const selectors = [
  'textarea#innerTextArea',
  'textarea[placeholder*="Share your thoughts"]',
  'textarea[placeholder*="comment"]',
  'textarea',
  'div[role="textbox"][data-lexical-editor="true"]',
  'div[contenteditable="true"][data-lexical-editor="true"]',
  'div[role="textbox"]',
  'div[contenteditable="true"]'
];

function isVisible(node) {
  if (!node) return false;
  const rect = node.getBoundingClientRect();
  const style = window.getComputedStyle(node);
  return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
}

function findDeep(root) {
  if (!root) return null;
  for (const sel of prioritySelectors) {
    const found = root.querySelector(sel);
    if (found && isVisible(found)) return found;
  }
  for (const sel of selectors) {
    const found = root.querySelector(sel);
    if (found && isVisible(found)) return found;
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.shadowRoot) {
      const shadowFound = findDeep(node.shadowRoot);
      if (shadowFound) return shadowFound;
    }
  }
  return null;
}

const loader = document.querySelector('shreddit-async-loader[bundlename="comment_composer"]');
if (loader) {
  const shadow = loader.shadowRoot || loader;
  const found = findDeep(shadow);
  if (found) return found;
}

const composers = [
  document.querySelector('shreddit-comment-composer'),
  document.querySelector('shreddit-composer'),
];
for (const comp of composers) {
  if (comp && comp.shadowRoot) {
    const found = findDeep(comp.shadowRoot);
    if (found) return found;
  }
}

return findDeep(document);
            """
        )
        return el
    except Exception:
        return None


def js_set_comment_text(driver, text: str) -> bool:
    """Attempt to set comment text via JS inside the composer."""
    try:
        return driver.execute_script(
            """
const txt = arguments[0];
function isVisible(node) {
  if (!node) return false;
  const rect = node.getBoundingClientRect();
  const style = window.getComputedStyle(node);
  return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
}
function setValue(node) {
  if (!node) return false;
  try { node.focus(); } catch(e){}
  if (node.tagName && node.tagName.toLowerCase() === 'textarea') {
    node.value = txt;
  } else {
    node.innerHTML = `<p>${txt}</p>`;
  }
  node.dispatchEvent(new Event('keydown', {bubbles: true}));
  node.dispatchEvent(new Event('input', {bubbles: true}));
  node.dispatchEvent(new Event('keyup', {bubbles: true}));
  node.dispatchEvent(new Event('change', {bubbles: true}));
  return true;
}
function findDeep(root){
  if (!root) return null;
  const prioritySelectors = [
    'div[contenteditable="true"][data-lexical-editor="true"]',
    'div[role="textbox"][data-lexical-editor="true"]',
  ];
  for (const sel of prioritySelectors) {
    const found = root.querySelector(sel);
    if (found && isVisible(found)) return found;
  }
  const selectors = [
    'shreddit-comment-composer div[contenteditable="true"][data-lexical-editor="true"]',
    'shreddit-comment-composer div[contenteditable="true"]',
    'shreddit-comment-composer textarea',
    'shreddit-composer div[contenteditable="true"][data-lexical-editor="true"]',
    'shreddit-composer div[contenteditable="true"]',
    'shreddit-composer textarea',
    'textarea#innerTextArea',
    'textarea[placeholder*="Share your thoughts"]',
    'textarea[placeholder*="comment"]',
    'textarea',
    'div[role="textbox"][data-lexical-editor="true"]',
    'div[contenteditable="true"][data-lexical-editor="true"]',
    'div[role="textbox"]',
    'div[contenteditable="true"]'
  ];
  for (const sel of selectors) {
    const found = root.querySelector(sel);
    if (found && isVisible(found)) return found;
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.shadowRoot) {
      const inner = findDeep(node.shadowRoot);
      if (inner) return inner;
    }
  }
  return null;
}

const loader = document.querySelector('shreddit-async-loader[bundlename="comment_composer"]');
const target = (loader && findDeep(loader.shadowRoot || loader)) || findDeep(document);
if (!target) {
  const comps = [
    document.querySelector('shreddit-comment-composer'),
    document.querySelector('shreddit-composer'),
  ];
  for (const comp of comps) {
    if (comp && comp.shadowRoot) {
      const inner = findDeep(comp.shadowRoot);
      if (inner) {
        return setValue(inner);
      }
    }
  }
}
if (target) {
  return setValue(target);
}
return false;
            """,
            text,
        )
    except Exception as e:
        logger.debug(f"JS set text failed: {e}")
    return False


def js_force_set_comment_text(driver, text: str) -> bool:
    """
    Force-set text inside the rich editor using selection APIs; last-resort for sticky editors.
    """
    try:
        return driver.execute_script(
            """
const txt = arguments[0];
const comps = [
  document.querySelector('shreddit-comment-composer'),
  document.querySelector('shreddit-composer')
];
for (const composer of comps) {
  if (!composer) continue;
  const root = composer.shadowRoot || composer;
  const target = root.querySelector('[data-lexical-editor="true"], div[contenteditable="true"], textarea, div[role="textbox"]');
  if (!target) continue;
  try { target.focus(); } catch(e){}
  if (target.tagName && target.tagName.toLowerCase() === 'textarea') {
    target.value = txt;
  } else {
    target.innerHTML = `<p>${txt}</p>`;
  }
  const sel = root.getSelection ? root.getSelection() : window.getSelection();
  if (sel) {
    try {
      const range = document.createRange();
      range.selectNodeContents(target);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    } catch(e){}
  }
  ['keydown','input','keyup','change'].forEach(evt => target.dispatchEvent(new Event(evt, {bubbles:true})));
  return true;
}
return false;
            """,
            text,
        )
    except Exception as e:
        logger.debug(f"Force set text failed: {e}")
        return False


def js_fill_shreddit_composer(driver, text: str) -> bool:
    """
    Directly target the shreddit composer shadow root and set innerHTML on the lexical editor.
    This is a stronger path for the new Reddit rich text composer.
    """
    try:
        return driver.execute_script(
            """
const txt = arguments[0];
const comps = [
  document.querySelector('shreddit-composer'),
  document.querySelector('shreddit-comment-composer')
];
for (const comp of comps) {
  if (!comp || !comp.shadowRoot) continue;
  const editor = comp.shadowRoot.querySelector('[data-lexical-editor="true"], div[contenteditable="true"], textarea, div[role="textbox"]');
  if (!editor) continue;
  try { editor.focus(); } catch(e){}
  if (editor.tagName && editor.tagName.toLowerCase() === 'textarea') {
    editor.value = txt;
  } else {
    editor.innerHTML = `<p>${txt}</p><p><br></p>`;
  }
  try {
    const sel = (editor.getRootNode && editor.getRootNode().getSelection) ? editor.getRootNode().getSelection() : window.getSelection();
    if (sel) {
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    }
  } catch(e){}
  // Fire richer events to mimic a paste/typing
  const events = [
    new InputEvent('beforeinput', {data: txt, inputType:'insertFromPaste', bubbles:true, composed:true}),
    new InputEvent('input', {data: txt, inputType:'insertFromPaste', bubbles:true, composed:true}),
    new Event('change', {bubbles:true, composed:true}),
  ];
  events.forEach(evt => editor.dispatchEvent(evt));
  return true;
}
return false;
            """,
            text,
        )
    except Exception as e:
        logger.debug(f"Fill shreddit composer failed: {e}")
        return False


def js_fill_composer_strict(driver, text: str) -> bool:
    """
    Stricter fill for shreddit composer: clicks, sets textContent, and fires input events.
    """
    try:
        return driver.execute_script(
            """
const txt = arguments[0];
const comps = [
  document.querySelector('shreddit-composer'),
  document.querySelector('shreddit-comment-composer')
];
for (const comp of comps) {
  if (!comp || !comp.shadowRoot) continue;
  const editor = comp.shadowRoot.querySelector('div[role="textbox"][data-lexical-editor="true"], div[contenteditable="true"][data-lexical-editor="true"]');
  if (!editor) continue;
  try { editor.click(); editor.focus(); } catch(e){}
  editor.textContent = txt;
  const evt = new InputEvent('input', {data: txt, inputType:'insertText', bubbles:true, composed:true});
  editor.dispatchEvent(evt);
  editor.dispatchEvent(new Event('change', {bubbles:true, composed:true}));
  return true;
}
return false;
            """,
            text,
        )
    except Exception as e:
        logger.debug(f"Strict fill failed: {e}")
        return False


def js_paste_comment_text(driver, text: str) -> bool:
    """
    Attempt to paste text using execCommand after focusing the composer.
    Some Reddit editors ignore simple value/innerHTML writes; this mimics a paste.
    """
    try:
        return driver.execute_script(
            """
const txt = arguments[0];
const comps = [
  document.querySelector('shreddit-comment-composer'),
  document.querySelector('shreddit-composer')
];
let target = null;
for (const comp of comps) {
  if (!comp) continue;
  const root = comp.shadowRoot || comp;
  target = root.querySelector('[data-lexical-editor="true"], div[contenteditable="true"], textarea, div[role="textbox"]');
  if (target) break;
}
if (!target) return false;
try { target.focus(); } catch(e){}
const sel = (target.getRootNode && target.getRootNode().getSelection) ? target.getRootNode().getSelection() : window.getSelection();
if (sel) {
  try {
    const range = document.createRange();
    range.selectNodeContents(target);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
  } catch(e){}
}
try {
  document.execCommand('insertText', false, txt);
} catch(e) {
  try { target.innerHTML = `<p>${txt}</p>`; } catch(e2){}
}
['keydown','input','keyup','change'].forEach(evt => target.dispatchEvent(new Event(evt, {bubbles:true})));
return true;
            """,
            text,
        )
    except Exception as e:
        logger.debug(f"Paste set text failed: {e}")
        return False


def get_composer_text(driver) -> str:
    """Read current text from the composer (shadow DOM aware)."""
    try:
        return driver.execute_script(
            """
const comps = [
  document.querySelector('shreddit-composer'),
  document.querySelector('shreddit-comment-composer')
];
for (const comp of comps) {
  if (!comp || !comp.shadowRoot) continue;
  const editor = comp.shadowRoot.querySelector('div[role="textbox"][data-lexical-editor="true"], div[contenteditable="true"][data-lexical-editor="true"], textarea');
  if (editor) {
    if (editor.value !== undefined) return editor.value;
    return editor.innerText || editor.textContent || '';
  }
}
return '';
            """
        ) or ""
    except Exception as e:
        logger.debug(f"Read composer text failed: {e}")
        return ""


def get_composer_element(driver):
    """Return the composer editor element (shadow DOM) if present."""
    try:
        return driver.execute_script(
            """
const comps = [
  document.querySelector('shreddit-composer'),
  document.querySelector('shreddit-comment-composer')
];
for (const comp of comps) {
  if (!comp || !comp.shadowRoot) continue;
  const editor = comp.shadowRoot.querySelector('div[role="textbox"][data-lexical-editor="true"], div[contenteditable="true"][data-lexical-editor="true"], textarea');
  if (editor) return editor;
}
return null;
            """
        )
    except Exception as e:
        logger.debug(f"Get composer element failed: {e}")
        return None


def keystroke_fill_simple(driver, element, text: str) -> bool:
    """
    Minimal ActionChains-only fill to mimic human typing.
    Avoids JS writes; returns True if no exception is raised.
    """
    try:
        from selenium.webdriver import ActionChains  # type: ignore
    except Exception:
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", element)
    except Exception:
        pass

    try:
        element.click()
    except Exception:
        _try_click(driver, element)

    try:
        actions = ActionChains(driver)
        actions.move_to_element(element).click().pause(0.2).send_keys(text).perform()
        return True
    except Exception as e:
        logger.debug(f"Simple keystroke fill failed: {e}")
        return False


def js_open_comment_composer(driver) -> None:
    """Try to click the comment composer trigger via JS (handles shadow DOM)."""
    try:
        driver.execute_script(
            """
function clickDeep(root){
  if (!root) return false;
  const selectors = [
    '[data-testid="trigger-button"]',
    'button[data-click-id="comment"]',
    'button[aria-label*="comment"]',
    'button[aria-label*="reply"]',
    'textarea[placeholder*="Share your thoughts"]',
    'div[role="textbox"]'
  ];
  for (const sel of selectors){
    const el = root.querySelector(sel);
    if (el){
      el.click();
      return true;
    }
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  while (walker.nextNode()){
    const node = walker.currentNode;
    if (node.shadowRoot && clickDeep(node.shadowRoot)) return true;
  }
  return false;
}

const loader = document.querySelector('shreddit-async-loader[bundlename="comment_composer"]');
if (loader && clickDeep(loader.shadowRoot || loader)) return true;
return clickDeep(document);
            """
        )
    except Exception:
        pass


def js_submit_comment(driver) -> bool:
    """Attempt to click the comment submit via JS."""
    try:
        return driver.execute_script(
            """
function clickDeep(root){
  if (!root) return false;
  const selectors = [
    'button[slot="submit-button"]',
    'button[type="submit"]',
    'button[data-testid="comment-submit-button"]',
    'button[aria-label*="comment"]'
  ];
  for (const sel of selectors) {
    const el = root.querySelector(sel);
    if (el) {
      el.click();
      return true;
    }
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.shadowRoot && clickDeep(node.shadowRoot)) return true;
  }
  return false;
}

const loader = document.querySelector('shreddit-async-loader[bundlename="comment_composer"]');
if (loader && clickDeep(loader.shadowRoot || loader)) return true;
return clickDeep(document);
            """
        )
    except Exception as e:
        logger.debug(f"JS submit failed: {e}")
        return False


def submit_via_buttons(driver) -> bool:
    """Fallback: click submit buttons via Selenium."""
    By = _safe_import_by()
    if not By:
        return False
    clicked = False
    submit_selectors = [
        "button[data-testid='comment-submit-button']",
        "button[type='submit']",
        "button[aria-label*='comment']",
        "button[slot='submit-button']",
    ]
    for selector in submit_selectors:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, selector)
            for btn in btns:
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    clicked = True
                    break
            if clicked:
                break
        except Exception:
            continue
    return clicked


def fill_comment_box(driver, element, text: str) -> bool:
    """Fill a comment box, trying JS and send_keys."""
    try:
        driver.execute_script(
            """
const el = arguments[0];
const txt = arguments[1];
try { el.focus(); } catch(e){}
if (el.tagName && el.tagName.toLowerCase() === 'textarea') {
  el.value = txt;
} else {
  if (el.getAttribute && el.getAttribute('data-lexical-editor') === 'true') {
    el.innerHTML = `<p>${txt}</p>`;
  } else {
    el.textContent = txt;
  }
}
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
return true;
            """,
            element,
            text,
        )
        try:
            element.clear()
        except Exception:
            pass
        try:
            element.send_keys(text)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.debug(f"JS fill failed: {e}")
        try:
            element.clear()
            element.send_keys(text)
            return True
        except Exception as e2:
            logger.debug(f"send_keys failed: {e2}")
            return False


def fill_comment_box_via_keystrokes(driver, element, text: str) -> bool:
    """Fill the comment box using real keystrokes to satisfy Reddit's rich editor."""
    try:
        from selenium.webdriver import ActionChains  # type: ignore
    except Exception:
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'});", element)
        try:
            element.click()
        except Exception:
            _try_click(driver, element)
        actions = ActionChains(driver)
        actions.move_to_element(element).click().pause(0.2).send_keys(text).perform()
        element = js_find_comment_box(driver) or element
        # Verify content and fallback to JS set if empty
        content = driver.execute_script(
            """
const el = arguments[0];
if (!el) return '';
if (el.value !== undefined) return el.value;
return el.innerText || el.textContent || '';
            """,
            element,
        )
        if not content or str(content).strip() == "":
            # Try another keystroke pass
            actions = ActionChains(driver)
            actions.move_to_element(element).click().pause(0.2).send_keys(text).perform()
            content = driver.execute_script(
                """
const el = arguments[0];
if (!el) return '';
if (el.value !== undefined) return el.value;
return el.innerText || el.textContent || '';
                """,
                element,
            )
        if not content or str(content).strip() == "":
            # Last resorts: JS set text, then force set
            if not js_set_comment_text(driver, text):
                if not js_force_set_comment_text(driver, text):
                    return False
        # Final verification with small delay to catch rich-editor resets
        driver.implicitly_wait(0)
        driver.execute_script("setTimeout(() => {}, 150);")  # slight pause
        final_content = driver.execute_script(
            """
const el = arguments[0];
if (!el) return '';
if (el.value !== undefined) return el.value;
return el.innerText || el.textContent || '';
            """,
            element,
        )
        return bool(str(final_content).strip())
    except Exception as e:
        logger.debug(f"Keystroke fill failed: {e}")
        return False


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
