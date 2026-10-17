# Homework code isolation

Submitted source is stored as escaped JSON, never executed by Django. Code review
does not run submissions automatically. Source and console output are rendered as
text; legacy text answers also use escaped plain text.

## Browser execution

- Web projects run inside two `sandbox="allow-scripts"` frames. Neither has
  same-origin, forms, popup, download, or top-navigation permission. The trusted
  outer frame blocks navigation of the inner student frame using `frame-src 'none'`.
- Web preview cannot fetch network resources, including images, stylesheets and
  scripts. Embedded `data:` images and inline CSS/JavaScript remain supported.
- Python runs in a Worker belonging to an opaque sandbox frame. Its network policy
  allows only the selected, pinned Pyodide distribution directory. Application
  APIs, arbitrary package/CDN URLs and browser session storage are inaccessible.
- A private MessageChannel carries Python output and lifecycle events. Calls to
  `js.postMessage()` cannot forge completion or reset the execution timeout.
- The host validates message source, type and length. Python has a 120-second
  loading deadline, a 15-second execution deadline and bounded console output.
  Removing the sandbox stops its worker. Browser capability access is denied via
  sandbox and Permissions Policy attributes.

These are browser isolation boundaries, not a guarantee against browser-engine
vulnerabilities or tab resource exhaustion. In particular, DOM JavaScript can
still consume CPU/memory in the viewer's browser. Do not move student execution
into Django or add `allow-same-origin` to either execution frame.

## Submission and media

The server validates the project schema, interpreter version, input size and total
size. Submit/edit endpoints check ownership, enrollment and CSRF. Editing cannot
bypass file-only/handwritten requirements. Django's existing `serve_media` sends
active uploaded file types as downloads with `nosniff`; any web server/CDN serving
`/media/` directly must preserve that behavior.

## Regression checks

`node --test accounts/tests_homework_python.cjs` covers editor/protocol setup.
`node accounts/tests_homework_python.browser.cjs` requires Playwright and Chrome;
set `PLAYWRIGHT_MODULE` to an alternate installed Playwright directory if needed.
It checks real Python execution and local attack probes under the LMS CSP.
`python -m unittest accounts.tests_web_homework_security` checks inert storage and
validation; the browser suite also runs these pure-Python tests with Pyodide.
Django endpoint tests are in `accounts/tests_web_homework.py`.
