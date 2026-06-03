# Screenshot QA: render and inspect before hand-off

Read this before delivering an infographic. It covers the headless-render loop
that catches the layout bugs reading the markup hides, the snippet to produce a
full-page screenshot, and the checklist of what to look at in the image.

## Why render at all

Markup looks correct in source and still ships broken: text overflows its node,
dim text fails contrast on the dark canvas, a flex row wraps badly at a width
you did not test, or reveal-on-scroll blocks never become visible. None of these
are visible by reading the HTML. Rendering and looking at the pixels is the only
reliable check.

## The snippet

Use the Playwright Chromium that ships with most repos, or any headless
Chromium. Scroll to the bottom first so any IntersectionObserver reveal fires,
then capture full-page.

```python
from playwright.sync_api import sync_playwright
import pathlib

url = pathlib.Path("docs/how-it-works.html").resolve().as_uri()
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1100, "height": 900}, device_scale_factor=2)
    pg.goto(url)
    pg.wait_for_timeout(1200)
    pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")  # fire reveals
    pg.wait_for_timeout(800)
    pg.evaluate("window.scrollTo(0, 0)")
    pg.wait_for_timeout(300)
    pg.screenshot(path="/tmp/infographic.png", full_page=True)
    b.close()
```

Then open or read `/tmp/infographic.png` and actually look at it. For a narrow
check, run it again with `viewport={"width": 800, "height": 900}` and compare.

## What to look for

- Reveal blocks all fired. If a section is blank in the screenshot, the
  scroll-to-bottom step was skipped or the reveal threshold never tripped. Any
  block still at opacity 0 in a full-page capture is a bug, not a style.
- No overflow or clipping. Long node titles and command chips are the usual
  culprits. Commands should wrap or scroll inside their chip, not spill.
- Contrast holds. Dim and faint text on the dark canvas is the first thing to
  fail. If a label is hard to read in the screenshot, it is unreadable on a
  laptop in daylight.
- Connectors land. Arrows and wires between nodes should point at the right
  thing after any responsive wrap. A rotated arrow that now points sideways is a
  common narrow-width break.
- Narrow viewport collapses cleanly. Around 800px the multi-column grids should
  stack and the horizontal pipeline should become vertical. Check that nothing
  becomes a one-pixel sliver.
- Print preview is legible. If PDF export matters, confirm the `@media print`
  block flattens the dark theme and avoids breaking cards across pages.

## A note on reveal animations

If the body uses reveal-on-scroll (sections fading up as they enter the
viewport), a screenshot taken before scrolling will capture them invisible. The
scroll-to-bottom step in the snippet exists for exactly this reason. When in
doubt, also disable the reveal for the capture by adding a `.rv{opacity:1}`
override in the page, or screenshot after the full scroll.
