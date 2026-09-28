#!/usr/bin/env python3
"""Run Admin visual, parity, and interaction gates in real Chrome."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from oldman.testing import (  # noqa: E402
    BrowserResult,
    BrowserVerificationError,
    ChromePage,
    clear_origin,
    configure_viewport,
    navigate,
    save_screenshot,
)

DEFAULT_ADMIN_URL = "http://127.0.0.1:17999/"
GATE_PROJECT_NAME = "Browser Gate Project"
PERMISSION_GATE_USERNAME = "browser_staff"
PERMISSION_GATE_PASSWORD = "BrowserStaff123"
USER_MANAGEMENT_GATE_USERNAME = "browser_lifecycle"
USER_MANAGEMENT_GATE_PASSWORD = "BrowserUser123"
USER_MANAGEMENT_GATE_UPDATED_PASSWORD = "BrowserUser456"
SUPERUSER_GATE_USERNAME = "browser_superuser_guard"

EVIDENCE_DIR = Path(os.environ.get("OLDMAN_ADMIN_EVIDENCE_DIR", "/tmp/oldman-admin-browser-evidence-standalone")).resolve()
SCREENSHOT_DIR = EVIDENCE_DIR / "screenshots"
STATE_SCREENSHOT_DIR = SCREENSHOT_DIR / "states"
REQUIRED_STATE_CAPTURES = (
    "login",
    "dark-theme",
    "desktop-sidebar-collapsed",
    "mobile-sidebar-open",
    "validation-feedback",
    "success-toast",
    "direct-delete",
)

STATE_CAPTURES: dict[str, tuple[int, int, bool]] = {
    name: (390, 844, True) if name == "mobile-sidebar-open" else (1440, 1000, False)
    for name in REQUIRED_STATE_CAPTURES
}

CAPTURES: dict[str, tuple[int, int, bool, str]] = {
    "desktop-list-top": (1440, 1000, False, str(SCREENSHOT_DIR / "desktop-list-top.png")),
    "desktop-table-footer": (1440, 1000, False, str(SCREENSHOT_DIR / "desktop-table-footer.png")),
    "desktop-form": (1440, 1000, False, str(SCREENSHOT_DIR / "desktop-form.png")),
    "desktop-user-list": (1440, 1000, False, str(SCREENSHOT_DIR / "desktop-user-list.png")),
    "desktop-user-form": (1440, 1000, False, str(SCREENSHOT_DIR / "desktop-user-form.png")),
    "desktop-user-password": (1440, 1000, False, str(SCREENSHOT_DIR / "desktop-user-password.png")),
    "desktop-user-status": (1440, 1000, False, str(SCREENSHOT_DIR / "desktop-user-status.png")),
    "desktop-user-delete": (1440, 1000, False, str(SCREENSHOT_DIR / "desktop-user-delete.png")),
    "mobile-list-top": (390, 844, True, str(SCREENSHOT_DIR / "mobile-list-top.png")),
    "mobile-table-footer": (390, 844, True, str(SCREENSHOT_DIR / "mobile-table-footer.png")),
}

SemanticVisualSpec = tuple[str, str, float, float] | tuple[str, str, float, float, bool]

SEMANTIC_VISUAL_CONTRACT: dict[str, tuple[SemanticVisualSpec, ...]] = {
    "desktop-list-top": (
        ("page title", ".om-page-title", 1, 20),
        # 视觉改版把列表页的新增动作放进了 page head 的动作区，不再挂在卡片头上。
        ("new control", ".om-page-actions .om-button-primary", 32, 28),
        ("table", "[data-om-component='table']", 320, 120),
        ("name sort control", "[data-om-table-sort='name']", 32, 16, True),
        ("first edit control", "[data-om-table-row] [data-om-column='action'] a", 24, 24),
    ),
    "desktop-table-footer": (
        ("table summary", "[data-om-table-summary]", 80, 16),
        ("page size control", "[data-om-table-page-size-control]", 32, 24),
        ("pagination", "[data-om-table-pagination]", 96, 24),
        ("page control", "[data-om-table-page]", 24, 24),
    ),
    "desktop-form": (
        ("edit form", "form[data-om-form]", 320, 160),
        ("cancel control", ".om-form-actions [data-om-history-back]", 32, 28),
        ("save control", ".om-form-actions .om-button-primary", 32, 28),
    ),
    "desktop-user-list": (
        ("user table", "[data-om-component='table']", 320, 120),
        ("user filter", "form[data-om-component='table-filter-form']", 160, 32),
        ("row actions", "[data-om-table-row] [data-om-dropdown-toggle]", 24, 24),
    ),
    "desktop-user-form": (
        ("user form", "form[data-om-form]", 320, 180),
        ("user save control", ".om-form-actions .om-button-primary", 32, 28),
    ),
    "desktop-user-password": (
        ("password modal", "#user-password-modal.is-open", 320, 180),
        ("password cancel", "#user-password-modal [data-om-modal-close]", 24, 24),
        ("password submit", "#user-password-modal [data-om-form-submit]", 32, 28),
    ),
    "desktop-user-status": (
        ("status modal", "#user-status-modal.is-open", 320, 180),
        ("status cancel", "#user-status-modal [data-om-modal-close]", 24, 24),
        ("status submit", "#user-status-modal [data-om-form-submit]", 32, 28),
    ),
    "desktop-user-delete": (
        ("delete modal", "#user-delete-modal.is-open", 320, 180),
        ("delete cancel", "#user-delete-modal [data-om-modal-close]", 24, 24),
        ("delete submit", "#user-delete-modal [data-om-form-submit]", 32, 28),
    ),
    "mobile-list-top": (
        ("mobile sidebar toggle", "[data-om-sidebar-toggle]", 24, 24),
        ("mobile table", "[data-om-component='table']", 240, 120),
        ("mobile edit control", "[data-om-table-row] [data-om-column='action'] a", 24, 24),
    ),
    "mobile-table-footer": (
        ("mobile table summary", "[data-om-table-summary]", 80, 16),
        ("mobile page size", "[data-om-table-page-size-control]", 32, 24),
        ("mobile pagination", "[data-om-table-pagination]", 96, 24),
    ),
}

VISUAL_CONTRACT: dict[str, dict[str, object]] = {
    "pageTitle": {
        "selector": ".om-page-title",
        "properties": ["font-family", "font-size", "font-weight", "line-height", "color"],
    },
    "card": {
        "selector": ".om-card",
        "properties": ["background-color", "border-top-color", "border-top-width", "border-radius", "box-shadow"],
    },
    "cardHeader": {
        "selector": ".om-card-header",
        "properties": ["padding-top", "padding-right", "padding-bottom", "padding-left", "border-bottom-color", "border-bottom-width"],
    },
    "cardTitle": {
        "selector": ".om-card-title",
        "properties": ["font-family", "font-size", "font-weight", "line-height", "color"],
    },
    "primaryButton": {
        "selector": ".om-button-primary",
        "properties": [
            "font-family",
            "font-size",
            "font-weight",
            "line-height",
            "color",
            "background-color",
            "border-radius",
            "padding-top",
            "padding-right",
            "padding-bottom",
            "padding-left",
        ],
    },
    "field": {
        "selector": ".om-field",
        "properties": [
            "font-family",
            "font-size",
            "line-height",
            "color",
            "background-color",
            "border-top-color",
            "border-top-width",
            "border-radius",
            "height",
            "padding-left",
            "padding-right",
        ],
    },
    "table": {
        "selector": ".om-table",
        "properties": ["font-family", "font-size", "line-height", "color", "background-color", "border-collapse"],
    },
    "tableHeader": {
        "selector": ".om-table th[data-om-column]",
        "properties": [
            "font-size",
            "font-weight",
            "line-height",
            "color",
            "background-color",
            "padding-top",
            "padding-right",
            "padding-bottom",
            "padding-left",
        ],
    },
    "tableCell": {
        "selector": ".om-table td[data-om-column]",
        "properties": [
            "font-size",
            "line-height",
            "color",
            "background-color",
            "padding-top",
            "padding-right",
            "padding-bottom",
            "padding-left",
        ],
    },
    "pageButton": {
        "selector": ".om-page-button",
        "properties": ["font-size", "font-weight", "color", "background-color", "border-radius", "height", "min-width"],
    },
    "select": {
        "selector": ".om-select",
        "properties": ["font-size", "color", "background-color", "border-top-color", "border-radius", "height"],
    },
    "sidebar": {
        "selector": ".oldman-sidebar",
        "properties": ["background-color", "border-right-color", "border-right-width", "box-shadow", "width"],
    },
    "topbar": {
        "selector": ".oldman-topbar",
        "properties": ["background-color", "border-bottom-color", "border-bottom-width", "height", "padding-left", "padding-right"],
    },
}

MODAL_FORM_VISUAL_CONTRACT: dict[str, dict[str, object]] = {
    "dialog": {
        "selector": ".om-modal-dialog",
        "properties": ["display", "width", "max-width", "margin-top", "margin-right", "margin-bottom", "margin-left"],
    },
    "surface": {
        "selector": ".om-modal-surface",
        "properties": [
            "display",
            "flex-direction",
            "width",
            "max-height",
            "background-color",
            "border-top-color",
            "border-top-width",
            "border-radius",
            "box-shadow",
        ],
    },
    "header": {
        "selector": ".om-modal-header",
        "properties": [
            "display",
            "align-items",
            "justify-content",
            "padding-top",
            "padding-right",
            "padding-bottom",
            "padding-left",
            "border-bottom-color",
            "border-bottom-width",
        ],
    },
    "body": {
        "selector": ".om-modal-body",
        "properties": [
            "display",
            "padding-top",
            "padding-right",
            "padding-bottom",
            "padding-left",
            "overflow-x",
            "overflow-y",
        ],
    },
    "footer": {
        "selector": ".om-modal-footer",
        "properties": [
            "display",
            "align-items",
            "justify-content",
            "gap",
            "padding-top",
            "padding-right",
            "padding-bottom",
            "padding-left",
            "border-top-color",
            "border-top-width",
        ],
    },
    "title": {
        "selector": ".om-modal-title",
        "properties": ["font-family", "font-size", "font-weight", "line-height", "color"],
    },
    "closeButton": {
        "selector": ".om-close-button[data-om-modal-close]",
        "properties": ["display", "width", "height", "color", "background-color"],
    },
    "cancelButton": {
        "selector": "form[data-om-form] .om-button-light[data-om-modal-close]",
        "properties": ["display", "font-size", "font-weight", "height", "color", "background-color", "border-radius"],
    },
    "submitButton": {
        "selector": "form[data-om-form] [data-om-form-submit]",
        "properties": ["display", "font-size", "font-weight", "height", "color", "background-color", "border-radius"],
    },
}


def main() -> int:
    """Run the complete browser gate and print one machine-readable result."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    admin_url = os.environ.get("OLDMAN_ADMIN_URL", DEFAULT_ADMIN_URL)
    username = os.environ.get("OLDMAN_ADMIN_USERNAME", "oldman_admin")
    password = os.environ.get("OLDMAN_ADMIN_PASSWORD", "oldman_admin_123")
    browser_result = BrowserResult()
    failures: list[str] = []
    interactions: list[str] = []
    semantic_visual_evidence: dict[str, object] = {}
    admin_contract: dict[str, object] = {}
    expected_user_validation_responses: list[dict[str, object]] = []
    expected_authentication_responses: list[dict[str, object]] = []
    admin_modal_form_contract: dict[str, object] = {}
    state_screenshots: dict[str, str] = {}
    structured_console_errors: list[dict[str, object]] = []
    suppressed_browser_errors: list[dict[str, object]] = []
    admin_login_ok = False

    with ChromePage(browser_result) as client:
        _install_structured_error_collector(client, structured_console_errors)
        configure_viewport(client, 1440, 1000, mobile=False)
        _clear_url_origin(client, admin_url)
        admin_login_ok = _login(
            client,
            urljoin(admin_url, "/admin/login"),
            username,
            password,
            failures,
            label="Admin",
            state_screenshots=state_screenshots,
            capture_name="login",
        )
        _record_assertion(
            "Admin registry card hover",
            _verify_admin_registry_card_hover(client, admin_url),
            failures,
            interactions,
        )
        _remove_gate_project_if_present(client, admin_url, failures)

        list_url = urljoin(admin_url, "/admin/admin_demo_project")
        navigate(client, list_url)
        _record_assertion("initial table", client.evaluate(_list_state_script(expected_rows=20), timeout=12.0), failures, interactions)
        _record_assertion(
            "Admin shared Topbar notification removal and BackToTop",
            client.evaluate(_shared_dashboard_shell_script(), timeout=12.0),
            failures,
            interactions,
        )
        navigate(client, list_url)
        _record_assertion(
            "Admin list restored after shared shell probe",
            client.evaluate(_list_state_script(expected_rows=20), timeout=12.0),
            failures,
            interactions,
        )
        _record_assertion("Admin DM Sans font loading", client.evaluate(_font_loading_script(), timeout=8.0), failures, interactions)
        _record_assertion("Admin CSRF rejection", client.evaluate(_csrf_rejection_script(), timeout=8.0), failures, interactions)
        admin_contract = _collect_visual_contract(client)
        _capture_visual(
            client,
            "desktop-list-top",
            semantic_visual_evidence,
            failures,
        )

        _scroll(client, "bottom")
        _capture_visual(
            client,
            "desktop-table-footer",
            semantic_visual_evidence,
            failures,
        )
        _scroll(client, "top")

        _record_assertion(
            "search, sort, page size and pagination", client.evaluate(_table_interactions_script(), timeout=25.0), failures, interactions
        )
        failures.extend(_verify_full_table_history_state(client, admin_url, interactions))
        navigate(client, list_url)
        _record_assertion("theme toggle", client.evaluate(_theme_interaction_script(), timeout=5.0), failures, interactions)
        _capture_temporary_theme_state(client, "dark", state_screenshots, "dark-theme")
        _record_assertion("desktop sidebar collapse", client.evaluate(_desktop_sidebar_script(), timeout=7.0), failures, interactions)
        _capture_temporary_sidebar_state(client, state_screenshots)

        failures.extend(_create_and_delete_project(client, admin_url, interactions, state_screenshots))

        navigate(client, list_url)
        _record_assertion("table restored after CRUD", client.evaluate(_list_state_script(expected_rows=20), timeout=12.0), failures, interactions)
        form_url = client.evaluate("document.querySelector('[data-om-table-row] [data-om-column=\"action\"] a')?.href || null")
        if not form_url:
            failures.append("shared edit form: no row edit URL is available")
        else:
            navigate(client, str(form_url))
            _record_assertion("shared edit form", client.evaluate(_form_state_script()), failures, interactions)
            _capture_visual(
                client,
                "desktop-form",
                semantic_visual_evidence,
                failures,
            )

        failures.extend(
            _verify_admin_user_management(
                client,
                admin_url,
                root_username=username,
                root_password=password,
                interactions=interactions,
                expected_validation_responses=expected_user_validation_responses,
                expected_authentication_responses=expected_authentication_responses,
                modal_form_contract=admin_modal_form_contract,
                semantic_visual_evidence=semantic_visual_evidence,
                state_screenshots=state_screenshots,
            )
        )

        # The user-management lifecycle deliberately expires the Admin session
        # while checking 401 handling. Re-authenticate before mobile assertions.
        _clear_url_origin(client, admin_url)
        _login(client, urljoin(admin_url, "/admin/login"), username, password, failures, label="Admin mobile restore")
        configure_viewport(client, 390, 844, mobile=True)
        navigate(client, list_url)
        _record_assertion("mobile table layout", client.evaluate(_mobile_state_script(), timeout=12.0), failures, interactions)
        _capture_visual(
            client,
            "mobile-list-top",
            semantic_visual_evidence,
            failures,
        )
        _scroll(client, "bottom")
        _capture_visual(
            client,
            "mobile-table-footer",
            semantic_visual_evidence,
            failures,
        )
        _scroll(client, "top")
        _record_mobile_sidebar_interactions(client, failures, interactions, state_screenshots)

        configure_viewport(client, 1440, 1000, mobile=False)
        _clear_url_origin(client, admin_url)
        _login(
            client,
            urljoin(admin_url, "/admin/login"),
            PERMISSION_GATE_USERNAME,
            PERMISSION_GATE_PASSWORD,
            failures,
            label="Admin staff",
        )
        permission_state = client.evaluate(
            """
            (async () => {
              const failures = [];
              const currentUrl = location.href;
              const response = await fetch('/admin/admin_demo_project', {
                headers: { Accept: 'text/html' },
                redirect: 'manual'
              });
              const body = await response.text();
              if (response.status !== 403) failures.push(`permission denial returned ${response.status}, expected 403`);
              if (response.redirected) failures.push(`permission denial redirected to ${response.url}`);
              if (!response.headers.get('content-type')?.includes('text/html') || !body.includes('403')) failures.push('permission denial HTML is missing');
              if (location.href !== currentUrl) failures.push(`permission probe navigated to ${location.href}`);
              return { failures, status: response.status, redirected: response.redirected, responseUrl: response.url };
            })()
            """
        )
        _record_assertion(
            "authenticated non-superuser permission denial returns 403 without redirect",
            permission_state,
            failures,
            interactions,
        )

    missing_state_captures = [
        name for name in REQUIRED_STATE_CAPTURES if name not in state_screenshots or not Path(state_screenshots[name]).is_file()
    ]
    failures.extend(f"required state screenshot is missing: {name}" for name in missing_state_captures)

    _discard_expected_csrf_rejection(
        browser_result,
        admin_url,
        structured_console_errors,
        suppressed_browser_errors,
    )
    _discard_expected_permission_denial(
        browser_result,
        admin_url,
        structured_console_errors,
        suppressed_browser_errors,
    )
    _discard_expected_responses(
        browser_result,
        expected_user_validation_responses,
        structured_console_errors,
        suppressed_browser_errors,
    )
    _discard_expected_responses(
        browser_result,
        expected_authentication_responses,
        structured_console_errors,
        suppressed_browser_errors,
    )
    payload: dict[str, object] = {
        "ok": not failures and browser_result.ok,
        "failures": failures,
        "interactions": interactions,
        "semanticVisualEvidence": semantic_visual_evidence,
        "renderedStyle": admin_contract,
        "adminModalForm": admin_modal_form_contract,
        "consoleErrors": browser_result.console_errors,
        "pageErrors": browser_result.page_errors,
        "badResponses": browser_result.bad_responses,
        "screenshots": {name: values[3] for name, values in CAPTURES.items()},
        "stateScreenshots": state_screenshots,
        "statusMatrix": {
            "login": admin_login_ok,
            "darkTheme": "theme toggle" in interactions,
            "desktopSidebar": "desktop sidebar collapse" in interactions,
            "sharedDashboardShell": "Admin shared Topbar notification removal and BackToTop" in interactions,
            "mobileSidebar": "mobile sidebar ignores Escape and closes through backdrop" in interactions,
            "validation": "Admin user shared Form create/edit native validation, messages, Actions and redirects"
            in interactions,
            "toast": "Admin Modal Form success Action feedback toasts are visible" in interactions,
            "directDelete": "native create, persistence and delete" in interactions,
        },
        "suppressedBrowserErrors": suppressed_browser_errors,
        "artifacts": _evidence_artifacts(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def _install_structured_error_collector(client: Any, records: list[dict[str, object]]) -> None:
    """Retain Log-domain URL/request metadata omitted by the generic collector."""
    original = client._handle_event

    def handle(message: dict[str, Any]) -> None:
        before = len(client.result.console_errors)
        original(message)
        params = message.get("params", {})
        entry = params.get("entry", {}) if message.get("method") == "Log.entryAdded" else {}
        if not isinstance(entry, dict) or entry.get("level") != "error":
            return
        added = client.result.console_errors[before:]
        for offset, text in enumerate(added):
            records.append(
                {
                    "message": text,
                    "consoleIndex": before + offset,
                    "url": str(entry.get("url") or ""),
                    "networkRequestId": str(entry.get("networkRequestId") or ""),
                    "source": str(entry.get("source") or ""),
                }
            )

    client._handle_event = handle


def _discard_expected_csrf_rejection(
    result: BrowserResult,
    admin_url: str,
    structured_errors: list[dict[str, object]],
    audit: list[dict[str, object]],
) -> None:
    """Exclude only the deliberate missing-token probe from generic browser error collection."""
    expected_url = urljoin(admin_url, "/admin/admin_demo_project/new")
    for index, response in enumerate(result.bad_responses):
        if response == {"method": "POST", "status": 403, "url": expected_url}:
            result.bad_responses.pop(index)
            audit.append({"kind": "networkResponse", **response})
            break
    else:
        return

    _discard_exact_console_error(result, structured_errors, status=403, url=expected_url, audit=audit)


def _discard_expected_permission_denial(
    result: BrowserResult,
    admin_url: str,
    structured_errors: list[dict[str, object]],
    audit: list[dict[str, object]],
) -> None:
    """Exclude only the deliberate authenticated permission-denial navigation."""
    expected_url = urljoin(admin_url, "/admin/admin_demo_project")
    for index, response in enumerate(result.bad_responses):
        if response == {"method": "GET", "status": 403, "url": expected_url}:
            result.bad_responses.pop(index)
            audit.append({"kind": "networkResponse", **response})
            break
    else:
        return
    _discard_exact_console_error(result, structured_errors, status=403, url=expected_url, audit=audit)


def _discard_expected_responses(
    result: BrowserResult,
    expected_responses: list[dict[str, object]],
    structured_errors: list[dict[str, object]],
    audit: list[dict[str, object]],
) -> None:
    """Discard only exact method/status/URL responses already asserted by an interaction."""
    for expected in expected_responses:
        method = str(expected.get("method") or "").upper()
        raw_status = expected.get("status")
        if not isinstance(raw_status, int):
            continue
        status = raw_status
        url = str(expected.get("url") or "")
        exact_response = {"method": method, "status": status, "url": url}
        for index, response in enumerate(result.bad_responses):
            if response == exact_response:
                result.bad_responses.pop(index)
                audit.append({"kind": "networkResponse", **response})
                break
        else:
            # Do not suppress a generic console message when the exact network
            # response was not observed by the browser collector.
            continue

        _discard_exact_console_error(result, structured_errors, status=status, url=url, audit=audit)


def _discard_exact_console_error(
    result: BrowserResult,
    structured_errors: list[dict[str, object]],
    *,
    status: int,
    url: str,
    audit: list[dict[str, object]],
) -> None:
    """Suppress a console entry only when CDP tied it to the asserted URL/request."""
    status_token = f"{status} ("
    for record in structured_errors:
        if record.get("consumed") or record.get("url") != url or status_token not in str(record.get("message") or ""):
            continue
        message = str(record.get("message") or "")
        original_index = record.get("consoleIndex")
        if not isinstance(original_index, int):
            return
        removed_before = 0
        for item in structured_errors:
            item_index = item.get("consoleIndex")
            if item.get("consumed") and isinstance(item_index, int) and item_index < original_index:
                removed_before += 1
        current_index = original_index - removed_before
        if current_index < 0 or current_index >= len(result.console_errors) or result.console_errors[current_index] != message:
            return
        result.console_errors.pop(current_index)
        record["consumed"] = True
        audit.append(
            {
                "kind": "consoleError",
                "status": status,
                "url": url,
                "networkRequestId": record.get("networkRequestId"),
                "message": message,
            }
        )
        return


def _clear_url_origin(client: Any, url: str) -> None:
    parsed = urlparse(url)
    clear_origin(client, f"{parsed.scheme}://{parsed.netloc}")


def _login(
    client: Any,
    login_url: str,
    username: str,
    password: str,
    failures: list[str],
    *,
    label: str,
    state_screenshots: dict[str, str] | None = None,
    capture_name: str | None = None,
) -> bool:
    navigate(client, login_url)
    language_state = client.evaluate(_language_switcher_contract_script())
    failures.extend(
        f"{label} language switcher: {failure}"
        for failure in _browser_failure_items(language_state)
    )
    if state_screenshots is not None and capture_name:
        _capture_state(client, capture_name, state_screenshots)
    credentials = json.dumps({"username": username, "password": password})
    client.load_seen = False
    submission = client.evaluate(
        """
        (() => {
          const credentials =
        """
        + credentials
        + """;
          const form = document.querySelector('form');
          const username = document.querySelector('[name="username"]');
          const password = document.querySelector('[name="password"]');
          const csrf = form?.querySelector('input[name="csrfmiddlewaretoken"]');
          if (!form || !username || !password) return { submitted: false, error: "login form is incomplete" };
          if (!csrf?.value) return { submitted: false, error: "login form has no CSRF token" };
          username.value = credentials.username;
          password.value = credentials.password;
          form.submit();
          return { submitted: true };
        })()
        """
    )
    if not isinstance(submission, dict) or not submission.get("submitted"):
        error = submission.get("error") if isinstance(submission, dict) else "login form is incomplete"
        failures.append(f"{label} {error}")
        return False
    client.wait_for_load()
    client.pump(0.25)
    if urlparse(str(client.evaluate("location.href"))).path == urlparse(login_url).path:
        failures.append(f"{label} login did not leave the login page")
        return False
    return True


def _language_switcher_contract_script() -> str:
    """Require every Admin/Dashboard login page to expose the common languages."""
    return r"""
    (() => {
      const failures = [];
      const root = document.querySelector('[data-om-component="language-switcher"]');
      const toggle = root?.querySelector('[data-om-language-current]');
      const menu = root?.querySelector('[data-om-dropdown-menu]');
      const codes = Array.from(root?.querySelectorAll('[data-lang]') || [])
        .map((item) => item.getAttribute('data-lang'));
      if (!root) failures.push('language switcher root is missing');
      if (!toggle) failures.push('language switcher toggle is missing');
      if (!menu) failures.push('language switcher menu is missing');
      if (JSON.stringify(codes) !== JSON.stringify(['en', 'zh-Hans', 'zh-Hant'])) {
        failures.push(`language codes are ${JSON.stringify(codes)}`);
      }
      if (toggle) {
        const style = getComputedStyle(toggle);
        const rect = toggle.getBoundingClientRect();
        if (toggle.hidden || style.display === 'none' || style.visibility === 'hidden' || rect.width < 24 || rect.height < 24) {
          failures.push('language switcher toggle is not visible');
        }
      }
      return { failures, codes };
    })()
    """


def _record_assertion(label: str, state: object, failures: list[str], interactions: list[str]) -> None:
    assertion_failures = _browser_failure_items(state)
    if assertion_failures:
        failures.extend(f"{label}: {failure}" for failure in assertion_failures)
    else:
        interactions.append(label)


def _verify_admin_registry_card_hover(client: Any, admin_url: str) -> dict[str, list[str]]:
    """Verify the target-native registry card uses a real source-theme hover color."""
    navigate(client, urljoin(admin_url, "/admin"))
    initial = client.evaluate(
        """
        (() => {
          const card = document.querySelector('.om-page-section .om-card');
          if (!card) return null;
          const rect = card.getBoundingClientRect();
          return {
            borderColor: getComputedStyle(card).borderTopColor,
            hoverCapable: matchMedia('(hover: hover)').matches,
            visible: rect.width > 0 && rect.height > 0
          };
        })()
        """
    )
    if not isinstance(initial, dict):
        return {"failures": ["registry card is missing"]}
    if not initial.get("visible"):
        return {"failures": ["registry card is not visible"]}
    if not initial.get("hoverCapable"):
        rule_found = client.evaluate(
            """
            (() => {
              const card = document.querySelector('.om-page-section .om-card');
              // 卡片的 hover 现在由组件类 .om-card-animate 提供（规则在 @media (hover: hover) 里），
              // 不再是 hover:border-primary-* 这种工具类。
              const selector = card.classList.contains('om-card-animate') ? '.om-card-animate:hover' : '';
              const contains = (rules) => Array.from(rules || []).some((rule) =>
                rule.selectorText === selector || (rule.cssRules && contains(rule.cssRules))
              );
              return selector && Array.from(document.styleSheets).some((sheet) => {
                try { return contains(sheet.cssRules); } catch { return false; }
              });
            })()
            """
        )
        return {"failures": [] if rule_found else ["registry card hover rule is absent from the real page CSSOM"]}
    document = client.command("DOM.getDocument")
    node = client.command(
        "DOM.querySelector",
        {
            "nodeId": document["root"]["nodeId"],
            "selector": ".om-page-section .om-card",
        },
    )
    client.command("CSS.enable")
    client.command("CSS.forcePseudoState", {"nodeId": node["nodeId"], "forcedPseudoClasses": ["hover"]})
    client.pump(0.4)
    hovered = client.evaluate(
        """
        (() => {
          const card = document.querySelector('.om-page-section .om-card');
          return {
            borderColor: getComputedStyle(card).borderTopColor,
            hoverMatches: card.matches(':hover')
          };
        })()
        """
    )
    client.command("CSS.forcePseudoState", {"nodeId": node["nodeId"], "forcedPseudoClasses": []})
    if not isinstance(hovered, dict) or hovered.get("borderColor") == initial["borderColor"]:
        return {"failures": [f"registry card hover did not apply: {hovered}"]}
    return {"failures": []}


def _freeze_visual_capture(client: Any) -> None:
    """Freeze page-owned motion and exclude transient browser scrollbars."""
    client.evaluate(
        r"""
        document.fonts.ready.then(() => new Promise((resolve) => {
          const style = document.createElement('style');
          style.id = 'oldman-visual-capture-freeze';
          style.textContent = `
            html.oldman-visual-capture-freeze *,
            html.oldman-visual-capture-freeze *::before,
            html.oldman-visual-capture-freeze *::after {
              animation: none !important;
              caret-color: transparent !important;
              transition: none !important;
            }
            html.oldman-visual-capture-freeze {
              scrollbar-width: none !important;
            }
            html.oldman-visual-capture-freeze::-webkit-scrollbar {
              width: 0 !important;
              height: 0 !important;
            }
            html.oldman-visual-capture-freeze .swal2-show {
              opacity: 1 !important;
              transform: none !important;
            }
            html.oldman-visual-capture-freeze .swal2-timer-progress-bar {
              transform: none !important;
              width: 100% !important;
            }
          `;
          document.getElementById(style.id)?.remove();
          document.head.appendChild(style);
          document.documentElement.classList.add('oldman-visual-capture-freeze');
          requestAnimationFrame(() => requestAnimationFrame(resolve));
        }))
        """,
        timeout=5.0,
    )


def _unfreeze_visual_capture(client: Any) -> None:
    client.evaluate(
        "document.documentElement.classList.remove('oldman-visual-capture-freeze'); "
        "document.getElementById('oldman-visual-capture-freeze')?.remove()"
    )


def _capture_state(client: Any, name: str, screenshots: dict[str, str]) -> None:
    """Save one reviewable full PNG with motion forced to its final visual state."""
    _freeze_visual_capture(client)
    path = STATE_SCREENSHOT_DIR / f"{name}.png"
    try:
        save_screenshot(client, str(path), capture_beyond_viewport=False)
        screenshots[name] = str(path)
    finally:
        _unfreeze_visual_capture(client)


def _capture_temporary_theme_state(client: Any, theme: str, screenshots: dict[str, str], name: str) -> None:
    """Capture the asserted theme without leaking it into following scenarios."""
    client.evaluate(
        """
        new Promise((resolve) => {
          document.documentElement.setAttribute('data-theme',
        """
        + json.dumps(theme)
        + "); requestAnimationFrame(() => requestAnimationFrame(resolve)); })"
    )
    _capture_state(client, name, screenshots)
    client.evaluate("document.documentElement.setAttribute('data-theme', 'light')")


def _capture_temporary_sidebar_state(client: Any, screenshots: dict[str, str]) -> None:
    """Capture the compact desktop sidebar and restore the expanded source state."""
    client.evaluate(
        "new Promise(resolve => { document.documentElement.setAttribute('data-sidebar-size', 'sm'); setTimeout(resolve, 400); })",
        timeout=2.0,
    )
    _capture_state(client, "desktop-sidebar-collapsed", screenshots)
    client.evaluate("document.documentElement.setAttribute('data-sidebar-size', 'lg')")


def _shared_dashboard_shell_script() -> str:
    """Exercise the shared Topbar selection/removal and BackToTop composition in Admin."""
    return """
    (async () => {
      const failures = [];
      const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      const visible = (element) => {
        if (!(element instanceof HTMLElement) || element.hidden) return false;
        const style = getComputedStyle(element);
        return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0;
      };

      const title = 'Admin shell gate notification';
      document.dispatchEvent(new CustomEvent('om:notification:add', {
        detail: { title, description: 'Shared DashboardTopbar action contract', href: location.pathname }
      }));
      await wait(150);

      const item = Array.from(document.querySelectorAll('[data-om-activity-notification-list] [data-om-activity-notification-item]')).find((candidate) => {
        return candidate.querySelector('a')?.textContent?.trim() === title;
      });
      if (!(item instanceof HTMLElement)) {
        failures.push('runtime notification was not rendered by the shared Topbar');
      } else {
        const checkbox = item.querySelector('.notification-check input');
        if (!(checkbox instanceof HTMLInputElement)) {
          failures.push('runtime notification selection control is missing');
        } else {
          checkbox.checked = true;
          checkbox.dispatchEvent(new Event('change', { bubbles: true }));
          await wait(50);
          const actions = document.querySelector('[data-om-activity-notification-actions]');
          const remove = document.querySelector('[data-om-modal-target="#removeNotificationModal"]');
          if (!visible(actions)) failures.push('notification selection actions did not become visible');
          if (!(remove instanceof HTMLElement)) {
            failures.push('notification Remove action is missing');
          } else {
            remove.click();
            await wait(150);
            const modal = document.querySelector('#removeNotificationModal');
            if (!visible(modal)) failures.push('notification removal modal did not open');
            const deleteButton = document.querySelector('#delete-notification');
            if (!(deleteButton instanceof HTMLElement)) {
              failures.push('notification delete confirmation is missing');
            } else {
              deleteButton.click();
              for (let attempt = 0; attempt < 20 && visible(modal); attempt += 1) await wait(50);
              if (document.contains(item)) failures.push('selected runtime notification was not removed');
              if (visible(modal)) failures.push('notification removal modal did not close');
              const empty = document.querySelector(
                '[data-om-activity-notification-list] [data-om-activity-notification-empty], '
                + '[data-om-activity-notification-list] .empty-notification-elem'
              );
              if (!visible(empty) || !empty.textContent.includes('No notifications')) {
                failures.push('shared Topbar did not restore the Admin empty notification state');
              }
            }
          }
        }
      }

      const backToTop = document.querySelector('#back-to-top');
      if (!(backToTop instanceof HTMLElement)) {
        failures.push('shared BackToTop control is missing');
      } else {
        window.scrollTo(0, document.documentElement.scrollHeight);
        await wait(150);
        const scrolled = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
        if (scrolled < 100) failures.push(`page did not scroll far enough for BackToTop: ${scrolled}`);
        if (!visible(backToTop) || backToTop.dataset.omState !== 'visible') {
          failures.push('shared BackToTop control did not become visible');
        }
        backToTop.click();
        await wait(150);
        const remaining = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
        if (remaining > 2) failures.push(`shared BackToTop did not restore the page origin: ${remaining}`);
      }
      return { failures };
    })()
    """


def _font_loading_script() -> str:
    """Require the real Admin page to fetch and activate the shared webfont.

    设计的字重是 400/500/600（`--om-font-weight-regular/medium/semibold`）；300 和 700 没有 token、
    也没有人用，框架已经不再发它们的字体文件，所以门禁不该要求 700 加载。
    """
    return r"""
    (async () => {
      const failures = [];
      await document.fonts.ready;
      const normalizeFamily = (value) => String(value || '').replace(/["']/g, '').trim().toLowerCase();
      const faces = Array.from(document.fonts).filter((face) => normalizeFamily(face.family) === 'dm sans');
      for (const weight of ['400', '500', '600']) {
        if (!faces.some((face) => String(face.weight) === weight)) failures.push(`DM Sans ${weight} FontFace is not registered`);
      }
      for (const weight of ['300', '700']) {
        if (faces.some((face) => String(face.weight) === weight)) failures.push(`DM Sans ${weight} is registered but no token uses it`);
      }
      const loaded = faces.filter((face) => face.status === 'loaded').map((face) => String(face.weight));
      if (!loaded.length) failures.push(`no DM Sans FontFace reached status=loaded: ${JSON.stringify(faces.map((face) => [face.weight, face.status]))}`);
      if (!document.fonts.check('400 16px "DM Sans"')) failures.push('Font Loading API rejected DM Sans 400');
      const resources = performance.getEntriesByType('resource').map((entry) => decodeURIComponent(entry.name));
      const fetched = loaded.filter((weight) => resources.some((name) => new RegExp(`dm-sans[^/]*${weight}-normal[^/]*\\.woff2(?:\\?|$)`).test(name)));
      if (loaded.length && !fetched.length) failures.push(`no loaded DM Sans weight was fetched as woff2: ${JSON.stringify(loaded)}`);
      return { failures, faces: faces.map((face) => ({ weight: face.weight, status: face.status })) };
    })()
    """


def _capture_visual(
    client: Any,
    name: str,
    semantic_visual_evidence: dict[str, object],
    failures: list[str],
) -> None:
    _, _, _, path = CAPTURES[name]
    semantic = _collect_semantic_visual_contract(client, name)
    failures.extend(f"semantic visual contract: {name}: {item}" for item in semantic["failures"])
    _freeze_visual_capture(client)
    try:
        png = save_screenshot(client, path, capture_beyond_viewport=False)
    finally:
        _unfreeze_visual_capture(client)
    semantic_visual_evidence[name] = {
        "sourcePngSha256": hashlib.sha256(png).hexdigest(),
        "semantic": semantic,
    }


def _collect_semantic_visual_contract(client: Any, name: str) -> dict[str, Any]:
    """Require every capture's small but behaviorally important controls to remain visible."""
    spec = json.dumps(SEMANTIC_VISUAL_CONTRACT[name])
    result = client.evaluate(
        """
        (() => {
          const spec =
        """
        + spec
        + r""";
          const controls = {};
          const failures = [];
          for (const [label, selector, minWidth, minHeight, requireClickable = false] of spec) {
            const element = document.querySelector(selector);
            if (!element) {
              failures.push(`missing ${label} (${selector})`);
              continue;
            }
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            const hitTarget = document.elementFromPoint(
              Math.min(innerWidth - 1, Math.max(0, rect.left + rect.width / 2)),
              Math.min(innerHeight - 1, Math.max(0, rect.top + rect.height / 2))
            );
            const visible = !element.hidden
              && element.getAttribute('aria-hidden') !== 'true'
              && style.display !== 'none'
              && style.visibility !== 'hidden'
              && Number(style.opacity || '1') > 0
              && rect.right > 0
              && rect.bottom > 0
              && rect.left < innerWidth
              && rect.top < innerHeight
              && rect.width >= minWidth
              && rect.height >= minHeight;
            const clickable = !requireClickable || (
              !element.matches(':disabled')
              && element.getAttribute('aria-disabled') !== 'true'
              && style.pointerEvents !== 'none'
              && Boolean(hitTarget && (hitTarget === element || element.contains(hitTarget)))
              && element.matches('button, a[href], input, select, textarea, [role="button"], [role="link"]')
            );
            controls[label] = {
              selector,
              visible,
              clickable,
              rect: {
                x: Math.round(rect.x * 100) / 100,
                y: Math.round(rect.y * 100) / 100,
                width: Math.round(rect.width * 100) / 100,
                height: Math.round(rect.height * 100) / 100
              },
              display: style.display,
              visibility: style.visibility,
              opacity: style.opacity,
              ariaLabel: element.getAttribute('aria-label') || '',
              text: (element.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 120)
            };
            if (!visible) failures.push(`${label} is not visibly at least ${minWidth}x${minHeight}`);
            if (!clickable) failures.push(`${label} is not a visible, enabled hit-testable control`);
          }
          return { controls, failures };
        })()
        """
    )
    return result if isinstance(result, dict) else {"controls": {}, "failures": ["contract returned no result"]}


def _evidence_artifacts() -> list[dict[str, object]]:
    """Hash every full-resolution screenshot produced by this assertion run."""
    artifacts: list[dict[str, object]] = []
    for path in sorted(SCREENSHOT_DIR.rglob("*.png")):
        artifacts.append(
            {
                "path": path.relative_to(EVIDENCE_DIR).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return artifacts


def _scroll(client: Any, edge: str) -> None:
    target = "document.documentElement.scrollHeight" if edge == "bottom" else "0"
    client.evaluate(
        f"new Promise(resolve => {{ window.scrollTo(0, {target}); requestAnimationFrame(() => setTimeout(resolve, 350)); }})",
        timeout=3.0,
    )


def _collect_visual_contract(client: Any) -> dict[str, object]:
    spec = json.dumps(VISUAL_CONTRACT)
    return client.evaluate(
        """
        (() => {
          const spec =
        """
        + spec
        + """;
          const components = {};
          const missing = [];
          for (const [name, definition] of Object.entries(spec)) {
            const element = document.querySelector(definition.selector);
            if (!element) {
              missing.push(`${name} (${definition.selector})`);
              continue;
            }
            const style = getComputedStyle(element);
            components[name] = Object.fromEntries(
              definition.properties.map((property) => [property, style.getPropertyValue(property)])
            );
          }
          return { components, missing };
        })()
        """
    ) or {"components": {}, "missing": ["visual contract returned no result"]}


def _compare_visual_contracts(left: dict[str, object], right: dict[str, object]) -> list[str]:
    failures: list[str] = []
    expected_keys = {"components", "missing"}
    expected_components = set(VISUAL_CONTRACT)
    for consumer, contract in (("Admin", left), ("Dashboard", right)):
        if set(contract) != expected_keys:
            failures.append(f"{consumer} rendered style contract fields are malformed")
            continue
        missing = contract.get("missing")
        if not isinstance(missing, list) or any(not isinstance(item, str) for item in missing):
            failures.append(f"{consumer} rendered style missing-component evidence is malformed")
        else:
            failures.extend(f"{consumer} missing {item}" for item in missing)
        components = contract.get("components")
        if not isinstance(components, dict) or set(components) != expected_components:
            failures.append(f"{consumer} rendered style component inventory is incomplete")
    if failures:
        return failures
    left_components = left["components"]
    right_components = right["components"]
    if not isinstance(left_components, dict) or not isinstance(right_components, dict):
        return ["rendered style contract is malformed"]
    for component_name in VISUAL_CONTRACT:
        left_values = left_components.get(component_name)
        right_values = right_components.get(component_name)
        if not isinstance(left_values, dict) or not isinstance(right_values, dict):
            failures.append(f"{component_name} style contract is malformed")
            continue
        properties = VISUAL_CONTRACT[component_name]["properties"]
        if not isinstance(properties, list):
            failures.append(f"{component_name} property contract is malformed")
            continue
        for property_name in properties:
            if not isinstance(property_name, str):
                failures.append(f"{component_name} property name is malformed")
                continue
            if set(left_values) != set(properties) or set(right_values) != set(properties):
                failures.append(f"{component_name} style property inventory is incomplete")
                break
            left_value = left_values.get(property_name)
            right_value = right_values.get(property_name)
            if not isinstance(left_value, str) or not left_value or not isinstance(right_value, str) or not right_value:
                failures.append(f"{component_name}.{property_name} style value is malformed")
                continue
            if left_value != right_value:
                failures.append(f"{component_name}.{property_name}: Admin={left_value!r}, Dashboard={right_value!r}")
    return failures


def _collect_modal_form_contract(client: Any, modal_selector: str) -> dict[str, object]:
    """Collect the rendered contract of one genuinely opened shared Modal Form."""
    spec = json.dumps(MODAL_FORM_VISUAL_CONTRACT)
    selector = json.dumps(modal_selector)
    return client.evaluate(
        """
        (() => {
          const spec =
        """
        + spec
        + "; const modalSelector = "
        + selector
        + r""";
          const modal = document.querySelector(modalSelector);
          const failures = [];
          if (!modal || modal.hidden || modal.dataset.omState !== 'open') {
            return { failures: ['Modal Form is not genuinely open'], nodes: {}, structure: {} };
          }
          const backdrop = document.querySelector('[data-om-modal-backdrop="true"]');
          const dialog = modal.querySelector('.om-modal-dialog');
          const dialogStyle = dialog ? getComputedStyle(dialog) : null;
          const rootStyle = getComputedStyle(modal);
          const root = {
            classes: Array.from(modal.classList).sort(),
            hidden: modal.hidden,
            display: rootStyle.display,
            inlineDisplay: modal.style.display,
            ariaHidden: modal.getAttribute('aria-hidden'),
            ariaModal: modal.getAttribute('aria-modal'),
            role: modal.getAttribute('role'),
            state: modal.dataset.omState || '',
            status: modal.dataset.omStatus || '',
            managed: modal.dataset.omModalManaged || '',
            bodyOpen: document.body.classList.contains('om-modal-open'),
          };
          const backdropState = backdrop ? {
            classes: Array.from(backdrop.classList).sort(),
            display: getComputedStyle(backdrop).display,
            backgroundColor: getComputedStyle(backdrop).backgroundColor,
            coversViewport: backdrop.getBoundingClientRect().height >= innerHeight,
            count: document.querySelectorAll('[data-om-modal-backdrop="true"]').length,
          } : null;
          const transition = dialogStyle ? {
            transitionProperty: dialogStyle.transitionProperty,
            transitionDuration: dialogStyle.transitionDuration,
            transitionDelay: dialogStyle.transitionDelay,
            animationName: dialogStyle.animationName,
            animationDuration: dialogStyle.animationDuration,
          } : null;
          if (!root.classes.includes('is-open')) failures.push('Modal Form root has no is-open class');
          if (root.display !== 'block' || root.inlineDisplay !== 'block') failures.push(`Modal Form display is ${root.display}/${root.inlineDisplay}`);
          if (root.ariaHidden !== 'false' || root.ariaModal !== 'true' || root.role !== 'dialog') failures.push('Modal Form ARIA open state is incomplete');
          if (root.status !== 'success' || root.managed !== 'true') failures.push(`Modal Form status/managed is ${root.status}/${root.managed}`);
          if (!root.bodyOpen) failures.push('Modal Form did not lock body with om-modal-open');
          if (!backdropState || backdropState.count !== 1 || !backdropState.classes.includes('om-modal-backdrop')) {
            failures.push('Modal Form backdrop state/class is incomplete');
          }
          const elements = {};
          const nodes = {};
          for (const [name, definition] of Object.entries(spec)) {
            const element = modal.querySelector(definition.selector);
            if (!element) {
              failures.push(`missing ${name} (${definition.selector})`);
              continue;
            }
            elements[name] = element;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            nodes[name] = {
              tag: element.tagName.toLowerCase(),
              classes: Array.from(element.classList).sort(),
              geometry: Object.fromEntries(
                ['x', 'y', 'width', 'height'].map((key) => [key, Math.round(rect[key] * 100) / 100])
              ),
              styles: Object.fromEntries(
                definition.properties.map((property) => [property, style.getPropertyValue(property)])
              )
            };
          }
          const structure = {
            dialogInModal: elements.dialog?.parentElement === modal,
            surfaceInDialog: elements.surface?.parentElement === elements.dialog,
            headerInSurface: elements.header?.parentElement === elements.surface,
            bodyInSurface: elements.body?.parentElement === elements.surface,
            headerBeforeBody: Boolean(
              elements.header && elements.body
              && (elements.header.compareDocumentPosition(elements.body) & Node.DOCUMENT_POSITION_FOLLOWING)
            ),
            footerInBody: Boolean(elements.footer && elements.body?.contains(elements.footer)),
            footerInForm: Boolean(elements.footer?.closest('form[data-om-form]')),
          };
          for (const [name, valid] of Object.entries(structure)) {
            if (!valid) failures.push(`invalid Modal Form structure: ${name}`);
          }
          return { failures, nodes, structure, root, backdrop: backdropState, transition };
        })()
        """
    ) or {"failures": ["Modal Form contract returned no result"], "nodes": {}, "structure": {}}


def _remove_gate_project_if_present(client: Any, base_url: str, failures: list[str]) -> None:
    filtered_url = urljoin(base_url, f"/admin/admin_demo_project?{urlencode({'q': GATE_PROJECT_NAME})}")
    navigate(client, filtered_url)
    state = client.evaluate(_wait_for_filtered_project_script(), timeout=12.0) or {}
    state_failures = _browser_failure_items(state)
    if state_failures:
        failures.extend(f"gate fixture cleanup: {failure}" for failure in state_failures)
        return
    edit_url = state.get("editUrl")
    if not edit_url:
        return
    edit_path = urlparse(str(edit_url)).path
    navigate(client, urljoin(base_url, f"{edit_path.removesuffix('/edit')}/delete"))
    submitted = _submit_and_wait_for_path(client, 'form button[type="submit"]', "/admin/admin_demo_project")
    if not submitted:
        failures.append("gate fixture cleanup: delete submit did not return to the list")


def _create_and_delete_project(
    client: Any,
    base_url: str,
    interactions: list[str],
    state_screenshots: dict[str, str],
) -> list[str]:
    failures: list[str] = []
    navigate(client, urljoin(base_url, "/admin/admin_demo_project/new"))
    prepared = client.evaluate(
        """
        (() => {
          const form = document.querySelector('form[data-om-form]');
          const name = form?.querySelector('[name="name"]');
          const owner = form?.querySelector('[name="owner"]');
          const status = form?.querySelector('[name="status"]');
          const active = form?.querySelector('[name="is_active"]');
          const submit = form?.querySelector('button[type="submit"]');
          if (!form || !name || !owner || !status || !active || !submit) {
            return false;
          }
          name.value = "Browser Gate Project";
          owner.value = "Quality Team";
          status.value = "review";
          active.checked = true;
          return true;
        })()
        """,
    )
    if not prepared:
        return ["create/delete form: create form is incomplete"]
    if not _submit_and_wait_for_path(
        client,
        'form[data-om-form] button[type="submit"]',
        "/admin/admin_demo_project",
    ):
        return ["create/delete form: create submit did not return to the list"]
    client.pump(0.25)
    if str(client.evaluate("location.pathname")) != "/admin/admin_demo_project":
        failures.append(f"create/delete form: create did not redirect to list ({client.evaluate('location.pathname')})")

    filtered_url = urljoin(base_url, f"/admin/admin_demo_project?{urlencode({'q': GATE_PROJECT_NAME})}")
    navigate(client, filtered_url)
    created = client.evaluate(_wait_for_filtered_project_script(), timeout=12.0) or {}
    failures.extend(f"create/delete form: {item}" for item in _browser_failure_items(created))
    edit_url = created.get("editUrl")
    if not edit_url:
        failures.append("create/delete form: created row has no edit URL")
        return failures

    edit_path = urlparse(str(edit_url)).path
    filtered_location = urlparse(filtered_url)
    expected_location = f"{filtered_location.path}?{filtered_location.query}"
    edit_opened = client.evaluate(
        """
        new Promise((resolve) => {
          const expectedPath =
        """
        + json.dumps(edit_path)
        + """;
          const link = document.querySelector('[data-om-table-row] [data-om-column="action"] a');
          if (!link) {
            resolve(false);
            return;
          }
          link.click();
          let attempts = 0;
          const check = () => {
            if (location.pathname === expectedPath && document.querySelector('form[data-om-form]')) {
              resolve(true);
              return;
            }
            if (attempts++ > 240) {
              resolve(false);
              return;
            }
            setTimeout(check, 50);
          };
          check();
        })
        """,
        timeout=15.0,
    )
    if not edit_opened:
        failures.append("create/delete form: row edit link did not open the edit form")
        return failures
    edit_state = (
        client.evaluate(
            """
        (() => {
          const failures = [];
          const value = (name) => document.querySelector(`[name="${name}"]`)?.value || '';
          if (value('name') !== 'Browser Gate Project') failures.push(`unexpected name: ${value('name')}`);
          if (value('owner') !== 'Quality Team') failures.push(`unexpected owner: ${value('owner')}`);
          if (value('status') !== 'review') failures.push(`unexpected status: ${value('status')}`);
          if (!document.querySelector('[name="is_active"]')?.checked) failures.push('is_active was not persisted');
          return { failures };
        })()
        """
        )
        or {}
    )
    failures.extend(f"create/delete form: {item}" for item in _browser_failure_items(edit_state))

    cancel_state = (
        client.evaluate(
            """
        new Promise((resolve) => {
          const expectedLocation =
        """
            + json.dumps(expected_location)
            + """;
          const failures = [];
          const cancel = document.querySelector('.om-form-actions [data-om-history-back]');
          if (!cancel) failures.push('missing edit Cancel control');
          if (!cancel?.hasAttribute('data-om-history-back')) failures.push('edit Cancel is not history-aware');
          if (cancel?.getAttribute('data-om-history-mode') === 'fallback') failures.push('edit Cancel forces fallback navigation');
          const restorationIndex = history.state?.turbo?.restorationIndex;
          if (typeof restorationIndex !== 'number' || restorationIndex <= 0) failures.push('edit page has no restorable Turbo history');
          if (failures.length) {
            resolve({ failures });
            return;
          }
          cancel.click();
          let attempts = 0;
          const check = () => {
            const restoredLocation = location.pathname + location.search;
            const restoredRow = Array.from(document.querySelectorAll('[data-om-table-row]')).find(
              (item) => item.querySelector('[data-om-column="name"]')?.textContent.trim() === 'Browser Gate Project'
            );
            const restoredEditLink = restoredRow?.querySelector('[data-om-column="action"] a');
            if (restoredLocation === expectedLocation && restoredEditLink) {
              resolve({ failures, restoredLocation, restorationIndex });
              return;
            }
            if (attempts++ > 240) {
              failures.push(`Cancel did not restore list state: ${location.pathname}${location.search}`);
              resolve({ failures, restoredLocation, restorationIndex });
              return;
            }
            setTimeout(check, 50);
          };
          check();
        })
        """,
            timeout=15.0,
        )
        or {}
    )
    cancel_failures = _browser_failure_items(cancel_state)
    failures.extend(f"create/delete form: {item}" for item in cancel_failures)
    if not cancel_failures:
        interactions.append("edit Cancel restores filtered list history")

    if not _click_and_wait_for_path(
        client,
        '[data-om-table-row] [data-om-column="action"] a',
        edit_path,
        "form[data-om-form]",
    ):
        failures.append("create/delete form: could not reopen the edit form before delete")
        return failures

    delete_path = f"{edit_path.removesuffix('/edit')}/delete"
    delete_selector = f'a[href="{delete_path}"]'
    if not _click_and_wait_for_path(client, delete_selector, delete_path, 'form button[type="submit"]'):
        failures.append("create/delete form: edit Delete link did not open the confirmation page")
        return failures

    delete_cancel_state = (
        client.evaluate(
            """
        new Promise((resolve) => {
          const expectedPath =
        """
            + json.dumps(edit_path)
            + """;
          const failures = [];
          const cancel = document.querySelector('form [data-om-history-back]');
          if (!cancel) failures.push('missing delete confirmation Cancel control');
          if (!cancel?.hasAttribute('data-om-history-back')) failures.push('delete Cancel is not history-aware');
          if (!cancel?.getAttribute('data-om-history-fallback')) failures.push('delete Cancel has no fallback');
          const restorationIndex = history.state?.turbo?.restorationIndex;
          if (typeof restorationIndex !== 'number' || restorationIndex <= 0) failures.push('delete page has no restorable Turbo history');
          if (failures.length) {
            resolve({ failures });
            return;
          }
          cancel.click();
          let attempts = 0;
          const check = () => {
            if (location.pathname === expectedPath && document.querySelector('form[data-om-form]')) {
              resolve({ failures, restorationIndex });
              return;
            }
            if (attempts++ > 240) {
              failures.push(`delete Cancel did not return to edit page: ${location.pathname}${location.search}`);
              resolve({ failures, restorationIndex });
              return;
            }
            setTimeout(check, 50);
          };
          check();
        })
        """,
            timeout=15.0,
        )
        or {}
    )
    delete_cancel_failures = _browser_failure_items(delete_cancel_state)
    failures.extend(f"create/delete form: {item}" for item in delete_cancel_failures)
    if delete_cancel_failures:
        return failures
    interactions.append("delete Cancel returns to the edit page")

    if not _click_and_wait_for_path(client, delete_selector, delete_path, 'form button[type="submit"]'):
        failures.append("create/delete form: could not reopen delete confirmation after Cancel")
        return failures
    _capture_state(client, "direct-delete", state_screenshots)
    delete_submitted = _submit_and_wait_for_path(client, 'form button[type="submit"]', "/admin/admin_demo_project")
    if not delete_submitted:
        failures.append("create/delete form: delete submit did not return to the list")
        return failures
    navigate(client, filtered_url)
    deleted = client.evaluate(_wait_for_empty_filter_script(), timeout=12.0) or {}
    failures.extend(f"create/delete form: {item}" for item in _browser_failure_items(deleted))
    if not failures:
        interactions.append("native create, persistence and delete")
    return failures


def _verify_full_table_history_state(client: Any, base_url: str, interactions: list[str]) -> list[str]:
    """Verify new/edit/delete Cancel against a sorted, filtered and paginated list."""
    failures: list[str] = []
    list_path = "/admin/admin_demo_project"
    initial_location = f"{list_path}?{urlencode({'q': 'Integration Sample'})}"
    expected_location = f"{list_path}?{urlencode({'q': 'Integration Sample', 'page_size': '10', 'page': '2', 'sort': '-name'})}"
    navigate(client, urljoin(base_url, initial_location))
    list_state = client.evaluate(_prepare_full_history_list_state_script(expected_location), timeout=25.0) or {}
    failures.extend(f"full table history: {item}" for item in _browser_failure_items(list_state))
    edit_path = str(list_state.get("editPath") or "")
    if failures or not edit_path:
        if not edit_path:
            failures.append("full table history: page 2 has no edit URL")
        return failures

    new_path = f"{list_path}/new"
    if not _click_and_wait_for_path(
        client,
        f'a[href="{new_path}"]',
        new_path,
        "form[data-om-form]",
    ):
        return failures + ["full table history: New link did not open the create form"]
    new_cancel = client.evaluate(_history_cancel_script(expected_location, "new"), timeout=15.0) or {}
    failures.extend(f"full table history: {item}" for item in _browser_failure_items(new_cancel))
    restored_state = client.evaluate(_restored_full_history_list_state_script(expected_location), timeout=15.0) or {}
    failures.extend(f"full table history restored state: {item}" for item in _browser_failure_items(restored_state))
    if failures:
        return failures

    if not _click_and_wait_for_path(
        client,
        '[data-om-table-row] [data-om-column="action"] a',
        edit_path,
        "form[data-om-form]",
    ):
        return failures + ["full table history: row edit link did not open the edit form"]

    edit_cancel = client.evaluate(_history_cancel_script(expected_location, "edit"), timeout=15.0) or {}
    failures.extend(f"full table history: {item}" for item in _browser_failure_items(edit_cancel))
    restored_state = client.evaluate(_restored_full_history_list_state_script(expected_location), timeout=15.0) or {}
    failures.extend(f"full table history restored state: {item}" for item in _browser_failure_items(restored_state))
    reloaded_state = client.evaluate(_reload_restored_full_history_list_state_script(expected_location), timeout=15.0) or {}
    failures.extend(f"full table history restored reload: {item}" for item in _browser_failure_items(reloaded_state))
    restored_state = client.evaluate(_restored_full_history_list_state_script(expected_location), timeout=15.0) or {}
    failures.extend(f"full table history reloaded state: {item}" for item in _browser_failure_items(restored_state))
    if failures:
        return failures

    navigate(client, urljoin(base_url, expected_location))
    direct_state = client.evaluate(_restored_full_history_list_state_script(expected_location), timeout=15.0) or {}
    failures.extend(f"full table direct URL state: {item}" for item in _browser_failure_items(direct_state))
    if failures:
        return failures

    if not _click_and_wait_for_path(
        client,
        '[data-om-table-row] [data-om-column="action"] a',
        edit_path,
        "form[data-om-form]",
    ):
        return ["full table history: could not reopen edit form"]
    delete_path = f"{edit_path.removesuffix('/edit')}/delete"
    if not _click_and_wait_for_path(client, f'a[href="{delete_path}"]', delete_path, 'form button[type="submit"]'):
        return ["full table history: edit Delete link did not open confirmation"]

    delete_cancel = client.evaluate(_history_cancel_script(edit_path, "delete"), timeout=15.0) or {}
    failures.extend(f"full table history: {item}" for item in _browser_failure_items(delete_cancel))
    if failures:
        return failures

    edit_cancel = client.evaluate(_history_cancel_script(expected_location, "edit"), timeout=15.0) or {}
    failures.extend(f"full table history: {item}" for item in _browser_failure_items(edit_cancel))
    restored_state = client.evaluate(_restored_full_history_list_state_script(expected_location), timeout=15.0) or {}
    failures.extend(f"full table history restored state: {item}" for item in _browser_failure_items(restored_state))
    if not failures:
        interactions.append("new, edit and delete Cancel restore full table URL and UI state")
        interactions.append("restored table state survives the next remote reload")
    return failures


def _verify_user_create_cancel_history(
    client: Any,
    base_url: str,
    *,
    username: str,
    interactions: list[str],
) -> list[str]:
    """Require New-user Cancel to preserve history and use a direct-entry fallback."""
    failures: list[str] = []
    list_path = "/admin/oldman_user"
    new_path = f"{list_path}/new"
    expected_location = f"{list_path}?{urlencode({'q': username, 'is_active': 'true', 'is_staff': 'true', 'is_superuser': 'true', 'page_size': '20', 'sort': '-username'})}"
    navigate(client, urljoin(base_url, expected_location))
    history_state = (
        client.evaluate(
            _user_new_history_cancel_script(expected_location, username),
            timeout=20.0,
        )
        or {}
    )
    failures.extend(f"Admin user new history Cancel: {item}" for item in _browser_failure_items(history_state))
    if failures:
        return failures

    navigate(client, urljoin(base_url, new_path))
    direct_state = client.evaluate(_prepare_direct_user_new_cancel_script(list_path), timeout=12.0) or {}
    failures.extend(f"Admin user new direct Cancel: {item}" for item in _browser_failure_items(direct_state))
    if direct_state.get("clicked"):
        client.load_seen = False
        # The click is issued after the direct-entry restoration index is reset;
        # HistoryBack must therefore take the declared full-navigation fallback.
        clicked = client.evaluate("document.querySelector('.om-form-actions [data-om-history-back]')?.click(); true")
        if clicked:
            client.wait_for_load()
            client.pump(0.25)
        if str(client.evaluate("location.pathname + location.search")) != list_path:
            failures.append(f"Admin user new direct Cancel did not use fallback {list_path}")
        fallback_state = client.evaluate(_user_table_contract_script(), timeout=12.0) or {}
        failures.extend(f"Admin user new direct fallback list: {item}" for item in _browser_failure_items(fallback_state))

    if not failures:
        interactions.append("Admin user new Cancel restores full query and rendered UI state")
        interactions.append("Admin user new Cancel direct entry uses the declared list fallback")
    return failures


def _verify_admin_user_management(
    client: Any,
    base_url: str,
    *,
    root_username: str,
    root_password: str,
    interactions: list[str],
    expected_validation_responses: list[dict[str, object]],
    expected_authentication_responses: list[dict[str, object]],
    modal_form_contract: dict[str, object],
    semantic_visual_evidence: dict[str, object],
    state_screenshots: dict[str, str],
) -> list[str]:
    """Exercise the migrated user manager and its source safety boundaries in Chrome."""
    failures: list[str] = []
    user_list_path = "/admin/oldman_user"
    user_list_url = urljoin(base_url, user_list_path)

    navigate(client, user_list_url)
    list_contract = client.evaluate(_user_table_contract_script(), timeout=12.0) or {}
    _record_assertion("Admin user filters, statuses and row actions", list_contract, failures, interactions)
    _capture_visual(client, "desktop-user-list", semantic_visual_evidence, failures)

    failures.extend(
        _verify_user_create_cancel_history(
            client,
            base_url,
            username=root_username,
            interactions=interactions,
        )
    )

    new_path = f"{user_list_path}/new"
    navigate(client, urljoin(base_url, new_path))
    _capture_visual(client, "desktop-user-form", semantic_visual_evidence, failures)
    client.load_seen = False
    create_validation = client.evaluate(_user_create_form_lifecycle_script(root_username), timeout=30.0) or {}
    _record_assertion(
        "Admin user shared Form native validation, JSON business errors and create Actions",
        create_validation,
        failures,
        interactions,
    )
    client.pump(1.6)
    edit_path = str(create_validation.get("editPath") or "")
    if not edit_path.endswith("/edit"):
        failures.append(f"Admin user create: response edit path is {edit_path!r}")
    if edit_path and str(client.evaluate("location.pathname")) != edit_path:
        failures.append(f"Admin user create: delayed redirect did not open {edit_path}")

    lifecycle_state = _load_filtered_user(client, base_url, USER_MANAGEMENT_GATE_USERNAME)
    failures.extend(f"Admin user create: {item}" for item in _browser_failure_items(lifecycle_state))
    listed_edit_path = str(lifecycle_state.get("editPath") or "")
    if edit_path and listed_edit_path != edit_path:
        failures.append(f"Admin user create: list edit path {listed_edit_path!r} differs from response {edit_path!r}")
    edit_path = listed_edit_path or edit_path
    if edit_path and not _click_and_wait_for_path(
        client,
        '[data-om-table-row] [data-om-column="username"] a',
        edit_path,
        "form[data-om-form]",
    ):
        failures.append("Admin user edit: username link did not open the edit form")
    elif edit_path:
        client.load_seen = False
        edited = client.evaluate(_user_edit_form_lifecycle_script(root_username), timeout=25.0) or {}
        _record_assertion(
            "Admin user edit shared Form native validation, JSON business error and success Actions",
            edited,
            failures,
            interactions,
        )
        response_edit_path = str(edited.get("editPath") or "")
        if response_edit_path != edit_path:
            failures.append(f"Admin user edit: response path {response_edit_path!r} differs from {edit_path!r}")
        client.pump(1.6)
        if str(client.evaluate("location.pathname")) != edit_path:
            failures.append(f"Admin user edit: delayed redirect did not remain on {edit_path}")

    if edit_path:
        edit_state = (
            client.evaluate(
                """
            (() => {
              const failures = [];
              if (document.querySelector('[name="display_name"]')?.value !== 'Browser Lifecycle Updated') {
                failures.push('display name was not persisted');
              }
              return { failures };
            })()
            """
            )
            or {}
        )
        failures.extend(f"Admin user edit: {item}" for item in _browser_failure_items(edit_state))

    lifecycle_state = _load_filtered_user(client, base_url, USER_MANAGEMENT_GATE_USERNAME)
    failures.extend(f"Admin user password: {item}" for item in _browser_failure_items(lifecycle_state))
    password_path = str(lifecycle_state.get("passwordPath") or "")
    password_modal_state = (
        _exercise_user_modal_form(
            client,
            suffix="/password-modal",
            expected_get_path=password_path,
            expected_target="#user-password-modal",
        )
        if password_path
        else {"failures": ["row action has no password modal URL"]}
    )
    failures.extend(f"Admin user password Modal Form: {item}" for item in _browser_failure_items(password_modal_state))
    if password_modal_state.get("ready"):
        modal_form_contract.clear()
        modal_form_contract.update(_collect_modal_form_contract(client, "#user-password-modal"))
        _capture_visual(client, "desktop-user-password", semantic_visual_evidence, failures)
        password_validation = client.evaluate(_user_password_validation_script("#user-password-modal"), timeout=15.0) or {}
        _capture_state(client, "validation-feedback", state_screenshots)
        _record_assertion(
            "Admin user password Modal Form JSON field validation",
            password_validation,
            failures,
            interactions,
        )
        if not _browser_failure_items(password_validation):
            password_submit = _submit_user_modal_form_and_wait_for_refresh(
                client,
                modal_target="#user-password-modal",
                username=USER_MANAGEMENT_GATE_USERNAME,
                values={
                    "password": USER_MANAGEMENT_GATE_UPDATED_PASSWORD,
                    "confirm_password": USER_MANAGEMENT_GATE_UPDATED_PASSWORD,
                },
            )
            failures.extend(f"Admin user password Modal Form: {item}" for item in _browser_failure_items(password_submit))
            _capture_state(client, "success-toast", state_screenshots)

    _clear_url_origin(client, base_url)
    before_login_failures = len(failures)
    _login(
        client,
        urljoin(base_url, "/admin/login"),
        USER_MANAGEMENT_GATE_USERNAME,
        USER_MANAGEMENT_GATE_UPDATED_PASSWORD,
        failures,
        label="Admin lifecycle user",
    )
    if len(failures) == before_login_failures:
        # A staff account without roles opens the Admin but not user management (auth.users.*, since
        # framework 6d9fc57c); the index is where the new password has to get it.
        navigate(client, urljoin(base_url, "/admin"))
        access_state = (
            client.evaluate(
                """
            (() => ({ failures: !location.pathname.startsWith('/admin/login') && document.querySelector('.om-page-section') ? [] : [`Admin index is inaccessible at ${location.pathname}`] }))()
            """
            )
            or {}
        )
        failures.extend(f"Admin lifecycle user: {item}" for item in _browser_failure_items(access_state))

    _clear_url_origin(client, base_url)
    _login(client, urljoin(base_url, "/admin/login"), root_username, root_password, failures, label="Admin root restore")

    root_state = _load_filtered_user(client, base_url, root_username)
    failures.extend(f"Admin self-protection: {item}" for item in _browser_failure_items(root_state))
    root_edit_path = str(root_state.get("editPath") or "")
    if root_edit_path:
        navigate(client, urljoin(base_url, root_edit_path))
        self_protection = client.evaluate(_current_user_edit_protection_script(), timeout=8.0) or {}
        _record_validation_probe("Admin current-user demotion protection", self_protection, failures, expected_validation_responses)

    superuser_state = _load_filtered_user(client, base_url, SUPERUSER_GATE_USERNAME)
    failures.extend(f"Admin superuser protection: {item}" for item in _browser_failure_items(superuser_state))
    superuser_delete_path = str(superuser_state.get("deletePath") or "")
    if superuser_delete_path:
        superuser_delete_modal = _exercise_user_modal_form(
            client,
            suffix="/delete-modal",
            expected_get_path=superuser_delete_path,
            expected_target="#user-delete-modal",
        )
        failures.extend(f"Admin superuser delete Modal Form: {item}" for item in _browser_failure_items(superuser_delete_modal))
        if superuser_delete_modal.get("ready"):
            delete_protection = client.evaluate(_user_delete_protection_script("#user-delete-modal"), timeout=15.0) or {}
            _record_assertion(
                "Admin superuser delete Modal Form business protection",
                delete_protection,
                failures,
                interactions,
            )

    lifecycle_state = _load_filtered_user(client, base_url, USER_MANAGEMENT_GATE_USERNAME)
    status_path = str(lifecycle_state.get("statusPath") or "")
    status_modal_state = (
        _exercise_user_modal_form(
            client,
            suffix="/status-modal",
            expected_get_path=status_path,
            expected_target="#user-status-modal",
        )
        if status_path
        else {"failures": ["row action has no status modal URL"]}
    )
    failures.extend(f"Admin user status Modal Form: {item}" for item in _browser_failure_items(status_modal_state))
    if status_modal_state.get("ready"):
        _capture_visual(client, "desktop-user-status", semantic_visual_evidence, failures)
        disabled_state = _submit_user_modal_form_and_wait_for_refresh(
            client,
            modal_target="#user-status-modal",
            username=USER_MANAGEMENT_GATE_USERNAME,
            values={},
            expected_status="Disabled",
        )
        failures.extend(f"Admin user status Modal Form: {item}" for item in _browser_failure_items(disabled_state))
        if disabled_state.get("status") != "Disabled":
            failures.append(f"Admin user status: expected Disabled, got {disabled_state.get('status')!r}")
        enable_modal_state = _exercise_user_modal_form(
            client,
            suffix="/status-modal",
            expected_get_path=status_path,
            expected_target="#user-status-modal",
        )
        failures.extend(f"Admin user status enable Modal Form: {item}" for item in _browser_failure_items(enable_modal_state))
        if enable_modal_state.get("ready"):
            enabled_state = _submit_user_modal_form_and_wait_for_refresh(
                client,
                modal_target="#user-status-modal",
                username=USER_MANAGEMENT_GATE_USERNAME,
                values={},
                expected_status="Active",
            )
            failures.extend(f"Admin user status enable Modal Form: {item}" for item in _browser_failure_items(enabled_state))
            if enabled_state.get("status") != "Active":
                failures.append(f"Admin user status: expected Active, got {enabled_state.get('status')!r}")

    lifecycle_state = _load_filtered_user(client, base_url, USER_MANAGEMENT_GATE_USERNAME)
    delete_path = str(lifecycle_state.get("deletePath") or "")
    delete_modal_state = (
        _exercise_user_modal_form(
            client,
            suffix="/delete-modal",
            expected_get_path=delete_path,
            expected_target="#user-delete-modal",
        )
        if delete_path
        else {"failures": ["row action has no delete modal URL"]}
    )
    failures.extend(f"Admin user delete Modal Form: {item}" for item in _browser_failure_items(delete_modal_state))
    if delete_modal_state.get("ready"):
        _capture_visual(client, "desktop-user-delete", semantic_visual_evidence, failures)
        delete_submit = _submit_user_modal_form_and_wait_for_refresh(
            client,
            modal_target="#user-delete-modal",
            username=USER_MANAGEMENT_GATE_USERNAME,
            values={},
            expect_missing=True,
        )
        failures.extend(f"Admin user delete Modal Form: {item}" for item in _browser_failure_items(delete_submit))
        deleted_state = _load_filtered_user(client, base_url, USER_MANAGEMENT_GATE_USERNAME, expect_missing=True)
        failures.extend(f"Admin user delete: {item}" for item in _browser_failure_items(deleted_state))

    session_expiry = _verify_admin_modal_form_session_expiry(
        client,
        base_url,
        username=root_username,
        password=root_password,
    )
    failures.extend(f"Admin Modal Form session expiry: {item}" for item in _browser_failure_items(session_expiry))
    response_urls = session_expiry.get("responseUrls", [])
    if isinstance(response_urls, list):
        expected_authentication_responses.extend(item for item in response_urls if isinstance(item, dict))

    if not failures:
        interactions.append("Admin user create, edit, password, login, status and delete lifecycle")
        interactions.append("Admin user uniqueness, password, self-demotion and superuser-delete protections")
        interactions.append("Admin user shared Modal and Form open, Escape/Cancel, JSON errors, close and table reload")
        interactions.append("Admin user shared Form create/edit native validation, messages, Actions and redirects")
        interactions.append("Admin user new Cancel restores full query/UI history and direct-entry fallback")
        interactions.append("Admin user delete shared Modal and Form Cancel, protection and success lifecycle")
        interactions.append("Admin password Modal Form native constraints and server field messages are visible")
        interactions.append("Admin Modal Form success Action feedback toasts are visible")
        interactions.append("Admin password/status Modal Form session expiry uses the Admin 401 redirect contract")
    return failures


def _verify_admin_modal_form_session_expiry(
    client: Any,
    base_url: str,
    *,
    username: str,
    password: str,
) -> dict[str, object]:
    """Require password/status Modal Form expiry to use the Admin 401 redirect contract."""
    failures: list[str] = []
    response_urls: list[dict[str, object]] = []
    login_path = "/admin/login"

    password_state = _load_filtered_user(client, base_url, username)
    failures.extend(f"password GET setup: {item}" for item in _browser_failure_items(password_state))
    password_path = str(password_state.get("passwordPath") or "")
    password_next_path = str(client.evaluate("location.pathname + location.search + location.hash"))
    if not password_path:
        failures.append("password GET setup has no Modal Form URL")
    elif _expire_admin_browser_session(client):
        _install_authentication_xhr_probe(client, password_path)
        client.load_seen = False
        clicked = client.evaluate(
            """
            (() => {
              const expectedPath =
            """
            + json.dumps(password_path)
            + """;
              const action = Array.from(document.querySelectorAll('[data-om-modal-url]')).find((item) => {
                const url = item.getAttribute('data-om-modal-url');
                return url && new URL(url, location.href).pathname === expectedPath;
              });
              action?.click();
              return Boolean(action);
            })()
            """
        )
        if not clicked:
            failures.append("password GET expiry could not click the Modal Form action")
        else:
            client.wait_for_load()
            client.pump(0.25)
            authentication_failures = _authentication_redirect_failures(
                client,
                expected_method="GET",
                expected_path=password_path,
                expected_next_path=password_next_path,
                login_path=login_path,
            )
            failures.extend(f"password GET expiry: {item}" for item in authentication_failures)
            if not authentication_failures:
                response_urls.append({"method": "GET", "status": 401, "url": urljoin(base_url, password_path)})
    else:
        failures.append("password GET expiry could not invalidate the Admin session")

    _login(client, urljoin(base_url, login_path), username, password, failures, label="Admin expiry probe restore")
    status_state = _load_filtered_user(client, base_url, username)
    failures.extend(f"status POST setup: {item}" for item in _browser_failure_items(status_state))
    status_path = str(status_state.get("statusPath") or "")
    status_submit_path = _modal_submit_path(status_path) if status_path else ""
    status_modal_state = (
        _exercise_user_modal_form(
            client,
            suffix="/status-modal",
            expected_get_path=status_path,
            expected_target="#user-status-modal",
        )
        if status_path
        else {"failures": ["status POST setup has no Modal Form URL"]}
    )
    failures.extend(f"status POST setup: {item}" for item in _browser_failure_items(status_modal_state))
    if status_modal_state.get("ready"):
        status_next_path = str(client.evaluate("location.pathname + location.search + location.hash"))
        if not _expire_admin_browser_session(client):
            failures.append("status POST expiry could not invalidate the Admin session")
        else:
            _install_authentication_xhr_probe(client, status_submit_path)
            client.load_seen = False
            clicked = client.evaluate(
                """
                (() => {
                  const submit = document.querySelector('#user-status-modal form[data-om-form] button[type="submit"]');
                  submit?.click();
                  return Boolean(submit);
                })()
                """
            )
            if not clicked:
                failures.append("status POST expiry could not submit the open Modal Form")
            else:
                client.wait_for_load()
                client.pump(0.25)
                authentication_failures = _authentication_redirect_failures(
                    client,
                    expected_method="POST",
                    expected_path=status_submit_path,
                    expected_next_path=status_next_path,
                    login_path=login_path,
                )
                failures.extend(f"status POST expiry: {item}" for item in authentication_failures)
                if not authentication_failures:
                    response_urls.append({"method": "POST", "status": 401, "url": urljoin(base_url, status_submit_path)})

    return {"failures": failures, "responseUrls": response_urls}


def _expire_admin_browser_session(client: Any) -> bool:
    """Invalidate the server session without navigating away from the current Admin DOM."""
    state = client.evaluate(
        r"""
        (async () => {
          const before = location.href;
          const response = await fetch('/admin/sign-out', {
            credentials: 'same-origin',
            redirect: 'manual'
          });
          return {
            stayedOnPage: location.href === before,
            responseType: response.type,
            status: response.status
          };
        })()
        """,
        timeout=8.0,
    )
    return bool(isinstance(state, dict) and state.get("stayedOnPage"))


def _install_authentication_xhr_probe(client: Any, expected_path: str) -> None:
    """Persist the next matching XHR result across the authentication redirect navigation."""
    client.evaluate(
        """
        (() => {
          const expectedPath =
        """
        + json.dumps(expected_path)
        + r""";
          sessionStorage.removeItem('oldman-admin-auth-probe');
          const originalOpen = XMLHttpRequest.prototype.open;
          XMLHttpRequest.prototype.open = function(...args) {
            const method = String(args[0] || 'GET').toUpperCase();
            const requestUrl = new URL(String(args[1] || ''), location.href);
            if (requestUrl.pathname === expectedPath) {
              this.addEventListener('loadend', () => {
                sessionStorage.setItem('oldman-admin-auth-probe', JSON.stringify({
                  method,
                  status: this.status,
                  url: this.responseURL || requestUrl.href
                }));
              }, { once: true });
            }
            return originalOpen.apply(this, args);
          };
        })()
        """
    )


def _authentication_redirect_failures(
    client: Any,
    *,
    expected_method: str,
    expected_path: str,
    expected_next_path: str,
    login_path: str,
) -> list[str]:
    """Assert the 401 payload was consumed into the exact Admin login redirect."""
    failures: list[str] = []
    current_url = str(client.evaluate("location.href"))
    parsed = urlparse(current_url)
    if parsed.path != login_path:
        failures.append(f"redirected to {parsed.path}, expected {login_path}")
    next_values = parse_qs(parsed.query).get("next", [])
    if next_values != [expected_next_path]:
        failures.append(f"login next is {next_values!r}, expected {[expected_next_path]!r}")

    raw_probe = client.evaluate("sessionStorage.getItem('oldman-admin-auth-probe')")
    try:
        probe = json.loads(str(raw_probe)) if raw_probe else {}
    except json.JSONDecodeError:
        probe = {}
    if probe.get("method") != expected_method:
        failures.append(f"authentication response method is {probe.get('method')!r}")
    if probe.get("status") != 401:
        failures.append(f"authentication response status is {probe.get('status')!r}")
    if urlparse(str(probe.get("url") or "")).path != expected_path:
        failures.append(f"authentication response URL is {probe.get('url')!r}")
    return failures


def _record_validation_probe(
    label: str,
    state: object,
    failures: list[str],
    expected_validation_responses: list[dict[str, object]],
) -> None:
    assertion_failures = _browser_failure_items(state)
    if assertion_failures:
        failures.extend(f"{label}: {item}" for item in assertion_failures)
        return
    if not isinstance(state, Mapping):
        return
    result = state
    expected_responses = result.get("expectedResponses")
    if expected_responses is not None:
        if not isinstance(expected_responses, list) or not expected_responses:
            failures.append(f"{label}: browser assertion returned no validation response evidence")
            return
        malformed = [
            item
            for item in expected_responses
            if not isinstance(item, dict)
            or str(item.get("method") or "").upper() != "POST"
            or item.get("status") != 422
            or not _is_absolute_http_url(item.get("url"))
        ]
        if malformed:
            failures.append(f"{label}: browser assertion returned malformed validation response evidence")
            return
        expected_validation_responses.extend(expected_responses)
        return
    response_urls = result.get("responseUrls")
    if not isinstance(response_urls, list) or not response_urls or any(
        not _is_absolute_http_url(item) for item in response_urls
    ):
        failures.append(f"{label}: browser assertion returned no validation response evidence")
        return
    expected_validation_responses.extend({"method": "POST", "status": 422, "url": item} for item in response_urls)


def _is_absolute_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _browser_failure_items(state: object) -> list[str]:
    """Return a typed failure list from a browser assertion payload."""
    if not isinstance(state, Mapping):
        return ["browser assertion returned no object"]
    if "failures" not in state:
        return ["browser assertion omitted failures"]
    value = state["failures"]
    if not isinstance(value, list):
        return ["browser assertion returned malformed failures"]
    return [str(item) for item in value]


def _load_filtered_user(client: Any, base_url: str, username: str, *, expect_missing: bool = False) -> dict[str, object]:
    filtered_url = urljoin(base_url, f"/admin/oldman_user?{urlencode({'q': username})}")
    navigate(client, filtered_url)
    return client.evaluate(_filtered_user_state_script(username, expect_missing=expect_missing), timeout=12.0) or {}


def _click_dropdown_action_and_wait(
    client: Any,
    suffix: str,
    expected_path: str,
    required_selector: str,
) -> bool:
    config = json.dumps({"suffix": suffix, "expectedPath": expected_path, "requiredSelector": required_selector})
    return bool(
        client.evaluate(
            """
            new Promise((resolve) => {
              const config =
            """
            + config
            + """;
              const dropdown = document.querySelector('[data-om-table-row] .om-dropdown');
              const toggle = dropdown?.querySelector('[data-om-dropdown-toggle]');
              const menu = dropdown?.querySelector('.om-dropdown-menu');
              const action = Array.from(dropdown?.querySelectorAll('a') || []).find((item) => item.getAttribute('href')?.endsWith(config.suffix));
              if (!toggle || !menu || !action) {
                resolve(false);
                return;
              }
              toggle.click();
              setTimeout(() => {
                if (toggle.getAttribute('aria-expanded') !== 'true' || !menu.classList.contains('show')) {
                  resolve(false);
                  return;
                }
                action.click();
                let attempts = 0;
                const check = () => {
                  if (location.pathname === config.expectedPath && document.querySelector(config.requiredSelector)) {
                    resolve(true);
                    return;
                  }
                  if (attempts++ > 240) {
                    resolve(false);
                    return;
                  }
                  setTimeout(check, 50);
                };
                check();
              }, 100);
            })
            """,
            timeout=15.0,
        )
    )


def _exercise_user_modal_form(
    client: Any,
    *,
    suffix: str,
    expected_get_path: str,
    expected_target: str,
) -> dict[str, object]:
    """Load the exact modal GET, verify its distinct POST action, and exercise closure."""
    expected_submit_path = _modal_submit_path(expected_get_path)
    config = json.dumps(
        {
            "suffix": suffix,
            "expectedGetPath": expected_get_path,
            "expectedSubmitPath": expected_submit_path,
            "expectedTarget": expected_target,
        }
    )
    return (
        client.evaluate(
            """
            new Promise((resolve) => {
              const config =
            """
            + config
            + r""";
              const failures = [];
              const startLocation = location.href;
              let modal = null;
              let form = null;
              let stableOpenFingerprint = '';
              let stableOpenCount = 0;
              const openFingerprints = [];
              const closeDurations = [];

              const waitFor = (predicate, timeoutMessage, callback) => {
                let attempts = 0;
                const check = () => {
                  if (predicate()) {
                    callback();
                    return;
                  }
                  if (attempts++ > 240) {
                    failures.push(timeoutMessage);
                    resolve({ failures, ready: false });
                    return;
                  }
                  setTimeout(check, 50);
                };
                check();
              };
              const findAction = () => {
                const row = document.querySelector('[data-om-table-row]');
                return Array.from(row?.querySelectorAll('[data-om-column="action"] [data-om-modal-url]') || []).find((item) => {
                  const url = item.getAttribute('data-om-modal-url');
                  return url && new URL(url, location.href).pathname === config.expectedGetPath;
                }) || null;
              };
              const open = (callback) => {
                stableOpenFingerprint = '';
                stableOpenCount = 0;
                const action = findAction();
                const dropdown = action?.closest('.om-dropdown');
                const toggle = dropdown?.querySelector('[data-om-dropdown-toggle]');
                const menu = dropdown?.querySelector('.om-dropdown-menu, [data-om-dropdown-menu]');
                if (!action || !dropdown || !toggle || !menu) {
                  failures.push(`could not find dropdown action ${config.suffix}`);
                  resolve({ failures, ready: false });
                  return;
                }
                if (toggle.getAttribute('aria-expanded') !== 'true') toggle.click();
                setTimeout(() => {
                  if (toggle.getAttribute('aria-expanded') !== 'true' || menu.hidden) {
                    failures.push(`dropdown did not expose ${config.suffix}`);
                  }
                  action.click();
                  waitFor(
                    () => {
                      modal = document.querySelector(config.expectedTarget);
                      form = modal?.querySelector('form[data-om-form]') || null;
                      const backdrop = document.querySelector('[data-om-modal-backdrop="true"]');
                      if (!modal || modal.hidden || modal.dataset.omState !== 'open' || !form) return false;
                      if (new URL(form.action, location.href).pathname !== config.expectedSubmitPath) return false;
                      if (modal.dataset.omStatus !== 'success' || !modal.classList.contains('is-open')) return false;
                      if (getComputedStyle(modal).display !== 'block' || modal.style.display !== 'block') return false;
                      if (!backdrop || !document.body.classList.contains('om-modal-open')) return false;
                      const rect = modal.querySelector('.om-modal-dialog')?.getBoundingClientRect();
                      const normalizedForm = form.cloneNode(true);
                      for (const csrf of normalizedForm.querySelectorAll('[name="csrfmiddlewaretoken"]')) csrf.setAttribute('value', '<csrf>');
                      const fingerprint = JSON.stringify({
                        action: form.action,
                        status: modal.dataset.omStatus,
                        html: normalizedForm.outerHTML,
                        rect: rect ? [rect.x, rect.y, rect.width, rect.height].map((value) => Math.round(value * 100) / 100) : []
                      });
                      if (fingerprint === stableOpenFingerprint) stableOpenCount += 1;
                      else {
                        stableOpenFingerprint = fingerprint;
                        stableOpenCount = 1;
                      }
                      if (stableOpenCount >= 2) openFingerprints.push(fingerprint);
                      return stableOpenCount >= 2;
                    },
                    `${config.suffix} Modal Form did not reach two stable exact-action frames`,
                    callback
                  );
                }, 100);
              };
              const waitForClose = (label, expectedReason, startedAt, callback) => {
                if (modal?.hidden || modal?.dataset.omState !== 'closing' || modal?.classList.contains('is-open')) {
                  failures.push(`${label} did not enter visible closing transition state`);
                }
                waitFor(
                  () => Boolean(modal?.hidden && modal?.dataset.omState === 'closed'),
                  `${label} did not close Modal Form`,
                  () => {
                    if (location.href !== startLocation) failures.push(`${label} navigated to ${location.href}`);
                    if (modal?.dataset.omLastCloseReason !== expectedReason) {
                      failures.push(`${label} close reason is ${modal?.dataset.omLastCloseReason || 'missing'}`);
                    }
                    const duration = performance.now() - startedAt;
                    closeDurations.push(Math.round(duration * 100) / 100);
                    if (duration < 140) failures.push(`${label} close transition lasted only ${duration.toFixed(1)}ms`);
                    callback();
                  }
                );
              };

              const initialAction = findAction();
              const initialModal = document.querySelector(config.expectedTarget);
              if (!initialAction) failures.push(`missing ${config.suffix} data-om-modal-url action`);
              if (initialAction?.tagName !== 'BUTTON') failures.push(`${config.suffix} row action is not a button`);
              if (initialAction?.getAttribute('data-om-modal-target') !== config.expectedTarget) {
                failures.push(`${config.suffix} target is ${initialAction?.getAttribute('data-om-modal-target') || 'missing'}`);
              }
              if (!initialModal) failures.push(`missing modal ${config.expectedTarget}`);
              if (initialModal?.getAttribute('data-om-component') !== 'modal') {
                failures.push(`${config.expectedTarget} does not use shared modal`);
              }
              if (failures.length) {
                resolve({ failures, ready: false });
                return;
              }

              const recordCloseReason = () => {
                modal?.addEventListener('om:modal:close', (event) => {
                  modal.dataset.omLastCloseReason = event.detail?.reason || '';
                }, { once: true });
              };
              open(() => {
                if (location.href !== startLocation) failures.push(`opening ${config.suffix} navigated to ${location.href}`);
                if (form?.dataset.omComponent !== 'form' || form?.dataset.omComponentState !== 'mounted') {
                  failures.push(`${config.suffix} content is not a mounted ordinary Form`);
                }
                if (form?.dataset.omFormMode !== 'json') failures.push(`${config.suffix} Form is not in JSON mode`);
                recordCloseReason();
                const backdrop = document.querySelector('[data-om-modal-backdrop="true"]');
                const backdropStartedAt = performance.now();
                backdrop?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                waitForClose('Backdrop', 'backdrop', backdropStartedAt, () => {
                  open(() => {
                    recordCloseReason();
                    const escapeStartedAt = performance.now();
                    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
                    waitForClose('Escape', 'escape', escapeStartedAt, () => {
                      open(() => {
                        const cancel = form?.querySelector('button[data-om-modal-close], input[data-om-modal-close]');
                        if (!cancel) {
                          failures.push(`${config.suffix} form has no modal Cancel button`);
                          resolve({ failures, ready: false });
                          return;
                        }
                        recordCloseReason();
                        const cancelStartedAt = performance.now();
                        cancel.click();
                        waitForClose('Cancel', 'dismiss', cancelStartedAt, () => {
                          open(() => {
                            if (location.href !== startLocation) failures.push(`reopening ${config.suffix} navigated to ${location.href}`);
                            if (new Set(openFingerprints).size !== 1) failures.push('Modal Form consecutive stable opens produced different geometry/content');
                            resolve({
                              failures,
                              ready: Boolean(modal && form && !modal.hidden),
                              formAction: form?.action || '',
                              modalTarget: config.expectedTarget,
                              openFingerprints,
                              closeDurations
                            });
                          });
                        });
                      });
                    });
                  });
                });
              });
            })
            """,
            timeout=45.0,
        )
        or {}
    )


def _modal_submit_path(modal_get_path: str) -> str:
    """Map one source-compatible ``*-modal`` GET path to its form POST path."""
    if not modal_get_path.endswith("-modal"):
        raise ValueError(f"Modal Form GET path must end with -modal: {modal_get_path}")
    return modal_get_path.removesuffix("-modal")


def _submit_user_modal_form_and_wait_for_refresh(
    client: Any,
    *,
    modal_target: str,
    username: str,
    values: dict[str, str],
    expected_status: str | None = None,
    expect_missing: bool = False,
) -> dict[str, object]:
    """Submit an open Modal Form and require its standard close/reload protocol."""
    config = json.dumps(
        {
            "modalTarget": modal_target,
            "username": username,
            "values": values,
            "expectedStatus": expected_status,
            "expectMissing": expect_missing,
        }
    )
    return (
        client.evaluate(
            """
            new Promise((resolve) => {
              const config =
            """
            + config
            + r""";
              const failures = [];
              const modal = document.querySelector(config.modalTarget);
              const form = modal?.querySelector('form[data-om-form]');
              const submit = form?.querySelector('button[type="submit"], input[type="submit"]');
              const table = document.querySelector('[data-om-component="table"]');
              const startPath = location.pathname;
              if (!modal || modal.hidden || modal.dataset.omState !== 'open') failures.push('Modal Form is not open before submit');
              if (!form || !submit) failures.push('Modal Form submit form is incomplete');
              if (!table) failures.push('user table is missing before Modal Form submit');
              for (const [name, value] of Object.entries(config.values)) {
                const field = form?.querySelector(`[name="${name}"]`);
                if (!field) {
                  failures.push(`missing Modal Form field ${name}`);
                  continue;
                }
                field.value = value;
                field.dispatchEvent(new Event('input', { bubbles: true }));
                field.dispatchEvent(new Event('change', { bubbles: true }));
              }
              if (failures.length) {
                resolve({ failures });
                return;
              }

              let refreshCount = 0;
              let closeReason = '';
              let responseStatus = null;
              let responseUrl = '';
              let responsePayload = null;
              let feedbackText = '';
              let feedbackShown = false;
              let feedbackCloseVisible = false;
              const actionPath = new URL(form.action, location.href).pathname;
              table.addEventListener('om:table:refresh', () => {
                refreshCount += 1;
              });
              modal.addEventListener('om:modal:close', (event) => { closeReason = event.detail?.reason || ''; }, { once: true });

              const originalOpen = XMLHttpRequest.prototype.open;
              XMLHttpRequest.prototype.open = function(...args) {
                const requestUrl = new URL(String(args[1] || ''), location.href);
                if (requestUrl.pathname === actionPath) {
                  this.addEventListener('loadend', () => {
                    responseStatus = this.status;
                    responseUrl = this.responseURL || requestUrl.href;
                    try { responsePayload = JSON.parse(this.responseText || 'null'); } catch {}
                  }, { once: true });
                }
                return originalOpen.apply(this, args);
              };
              const restoreXhr = () => {
                XMLHttpRequest.prototype.open = originalOpen;
              };

              submit.click();
              let attempts = 0;
              const check = () => {
                const visibleFeedback = document.querySelector('.toastify.om-toast.on');
                if (visibleFeedback) {
                  feedbackText = visibleFeedback.textContent || '';
                  feedbackShown ||= visibleFeedback.getBoundingClientRect().height > 0;
                  const close = visibleFeedback.querySelector('.toast-close');
                  feedbackCloseVisible ||= Boolean(close && getComputedStyle(close).display !== 'none');
                }
                if (refreshCount > 0 && modal.hidden && modal.dataset.omState === 'closed') {
                  restoreXhr();
                  if (responseStatus === null || responseStatus < 200 || responseStatus >= 300) {
                    failures.push(`Modal Form success returned ${responseStatus ?? 'no response'}`);
                  }
                  const actionNames = Array.isArray(responsePayload?.actions)
                    ? responsePayload.actions.map((action) => action.action)
                    : [];
                  if (actionNames.join(',') !== 'feedback,dashboard_activity,close_modal,reload_table') {
                    failures.push(`Modal Form actions are ${actionNames.join(',') || 'missing'}`);
                  }
                  const reloadAction = responsePayload?.actions?.find?.((action) => action.action === 'reload_table');
                  if (reloadAction?.target !== '#admin-oldman_user-table') {
                    failures.push(`Modal Form reload target is ${reloadAction?.target || 'missing'}`);
                  }
                  if (closeReason !== 'response-action') failures.push(`Modal Form close reason is ${closeReason || 'missing'}`);
                  if (location.pathname !== startPath) failures.push(`Modal Form success navigated to ${location.pathname}`);
                  const rows = Array.from(document.querySelectorAll('[data-om-table-row]'));
                  const row = rows.find((item) => item.querySelector('[data-om-column="username"]')?.textContent.trim() === config.username);
                  const status = row?.querySelector('[data-om-column="is_active"]')?.textContent.trim() || '';
                  if (config.expectMissing && row) failures.push(`table refresh still contains ${config.username}`);
                  if (!config.expectMissing && !row) failures.push(`table refresh lost ${config.username}`);
                  if (config.expectedStatus && status !== config.expectedStatus) {
                    failures.push(`table refresh status is ${status || 'missing'}, expected ${config.expectedStatus}`);
                  }
                  const feedbackTitle = responsePayload?.actions?.[0]?.title || '';
                  if (!feedbackTitle || !feedbackText.includes(feedbackTitle)) {
                    failures.push(`success Feedback did not render its Action title ${feedbackTitle || 'missing'}`);
                  }
                  if (!feedbackShown) failures.push('success Feedback toast was never visibly shown');
                  if (!feedbackCloseVisible) failures.push('success Feedback toast close button was never visible');
                  if (!config.expectMissing) {
                    const passwordAction = row?.querySelector('[data-om-modal-target="#user-password-modal"][data-om-modal-url$="/password-modal"]');
                    const statusAction = row?.querySelector('[data-om-modal-target="#user-status-modal"][data-om-modal-url$="/status-modal"]');
                    const deleteAction = row?.querySelector('[data-om-modal-target="#user-delete-modal"][data-om-modal-url$="/delete-modal"]');
                    if (!passwordAction || !statusAction || !deleteAction) failures.push('refreshed row lost shared Modal Form actions');
                  }
                  resolve({
                    failures,
                    closeReason,
                    refreshCount,
                    responseStatus,
                    responseUrl,
                    responsePayload,
                    status
                  });
                  return;
                }
                if (attempts++ > 300) {
                  restoreXhr();
                  failures.push(
                    `Modal Form success contract timed out (refresh=${refreshCount}, closed=${modal.hidden}, status=${responseStatus})`
                  );
                  resolve({ failures, closeReason, refreshCount, responseStatus, responseUrl, responsePayload });
                  return;
                }
                setTimeout(check, 50);
              };
              check();
            })
            """,
            timeout=20.0,
        )
        or {}
    )


def _submit_and_wait_for_path(client: Any, selector: str, expected_path: str) -> bool:
    """Submit a real form and accept either a full-page or Turbo navigation."""
    encoded_selector = json.dumps(selector)
    scheduled = client.evaluate(
        """
        (() => {
          const selector =
        """
        + encoded_selector
        + """;
          const button = document.querySelector(selector);
          const csrf = button?.closest('form')?.querySelector('input[name="csrfmiddlewaretoken"]');
          if (!button || !csrf?.value) return false;
          setTimeout(() => button.click(), 0);
          return true;
        })()
        """,
    )
    if not scheduled:
        return False
    for _attempt in range(300):
        client.pump(0.05)
        try:
            state = client.evaluate(
                """
                (() => {
                  const frame = document.querySelector('#oldman-main');
                  const frameSettled = !frame || (
                    frame.getAttribute('data-om-frame-state') === 'mounted'
                    && !frame.hasAttribute('busy')
                    && frame.getAttribute('data-om-preloader-status') !== 'loading'
                  );
                  return {
                    path: location.pathname,
                    ready: document.readyState !== 'loading' && frameSettled,
                  };
                })()
                """,
                timeout=1.0,
            )
        except BrowserVerificationError:
            # A full-page redirect may destroy the old execution context between
            # scheduling the click and evaluating the newly loaded document.
            continue
        if isinstance(state, dict) and state.get("path") == expected_path and state.get("ready") is True:
            return True
    return False


def _click_and_wait_for_path(client: Any, selector: str, expected_path: str, required_selector: str) -> bool:
    """Click a real page control and wait for Turbo navigation to finish."""
    config = json.dumps(
        {
            "selector": selector,
            "expectedPath": expected_path,
            "requiredSelector": required_selector,
        }
    )
    return bool(
        client.evaluate(
            """
            new Promise((resolve) => {
              const config =
            """
            + config
            + """;
              const control = document.querySelector(config.selector);
              if (!control) {
                resolve(false);
                return;
              }
              // The main frame reports mounted before Turbo's promoted page visit has finished;
              // that visit ends at turbo:load, and going back before it starts loses the restore.
              let loaded = false;
              document.addEventListener('turbo:load', () => { loaded = true; }, { once: true });
              control.click();
              let attempts = 0;
              const check = () => {
                const frame = document.querySelector('#oldman-main');
                const frameSettled = !frame || (
                  frame.getAttribute('data-om-frame-state') === 'mounted'
                  && !frame.hasAttribute('busy')
                  && frame.getAttribute('data-om-preloader-status') !== 'loading'
                );
                if (
                  location.pathname === config.expectedPath
                  && document.querySelector(config.requiredSelector)
                  && frameSettled
                  && loaded
                ) {
                  resolve(true);
                  return;
                }
                if (attempts++ > 240) {
                  resolve(false);
                  return;
                }
                setTimeout(check, 50);
              };
              check();
            })
            """,
            timeout=15.0,
        )
    )


def _record_mobile_sidebar_interactions(
    client: Any,
    failures: list[str],
    interactions: list[str],
    state_screenshots: dict[str, str],
) -> None:
    opened = client.evaluate(_mobile_sidebar_open_script(), timeout=5.0) or {}
    opened_failures = _browser_failure_items(opened)
    _capture_state(client, "mobile-sidebar-open", state_screenshots)
    client.command(
        "Input.dispatchKeyEvent",
        {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27},
    )
    client.command(
        "Input.dispatchKeyEvent",
        {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27},
    )
    preserved = client.evaluate(_mobile_sidebar_preserved_script(), timeout=5.0) or {}
    preserved_failures = _browser_failure_items(preserved)
    backdrop = client.evaluate(_mobile_sidebar_backdrop_script(), timeout=5.0) or {}
    backdrop_failures = _browser_failure_items(backdrop)
    all_failures = opened_failures + preserved_failures + backdrop_failures
    if all_failures:
        failures.extend(f"mobile sidebar: {failure}" for failure in all_failures)
    else:
        interactions.append("mobile sidebar ignores Escape and closes through backdrop")


def _prepare_full_history_list_state_script(expected_location: str) -> str:
    config = json.dumps({"expectedLocation": expected_location})
    return (
        r"""
    (async () => {
      const config =
    """
        + config
        + r""";
      const failures = [];
      const waitFor = (predicate, label) => new Promise((resolve, reject) => {
        let attempts = 0;
        const check = () => {
          if (predicate()) return resolve(true);
          if (attempts++ > 240) return reject(new Error(`timed out waiting for ${label}`));
          setTimeout(check, 50);
        };
        check();
      });
      const summary = () => document.querySelector('[data-om-table-summary]')?.textContent.replace(/\s+/g, ' ').trim() || '';
      const rows = () => Array.from(document.querySelectorAll('[data-om-table-row]'));
      try {
        await waitFor(() => summary() === 'Showing 1 to 20 of 22 entries' && rows().length === 20, 'filtered first page');
        const pageSize = document.querySelector('[data-om-table-page-size-control]');
        if (!pageSize) throw new Error('page-size control is missing');
        pageSize.value = '10';
        pageSize.dispatchEvent(new Event('change', { bubbles: true }));
        await waitFor(() => summary() === 'Showing 1 to 10 of 22 entries' && rows().length === 10, '10-row filtered page');

        const sort = document.querySelector('[data-om-table-sort="name"]');
        if (!sort) throw new Error('name sort control is missing');
        sort.click();
        await waitFor(() => sort.getAttribute('aria-sort') === 'ascending', 'ascending name sort');
        sort.click();
        await waitFor(() => sort.getAttribute('aria-sort') === 'descending', 'descending name sort');

        const pageTwo = document.querySelector('[data-om-table-page="2"]');
        if (!pageTwo) throw new Error('page 2 control is missing');
        pageTwo.click();
        await waitFor(
          () => summary() === 'Showing 11 to 20 of 22 entries'
            && rows().length === 10
            && document.querySelector('[data-om-table-page="2"]')?.getAttribute('aria-current') === 'page',
          'sorted second page'
        );
      } catch (error) {
        failures.push(error instanceof Error ? error.message : String(error));
      }
      const locationValue = location.pathname + location.search;
      if (locationValue !== config.expectedLocation) failures.push(`list URL changed unexpectedly: ${locationValue}`);
      const edit = rows()[0]?.querySelector('[data-om-column="action"] a');
      if (!edit) failures.push('page 2 has no edit URL');
      return { failures, editPath: edit ? new URL(edit.href).pathname : '' };
    })()
    """
    )


def _restored_full_history_list_state_script(expected_location: str) -> str:
    config = json.dumps({"expectedLocation": expected_location})
    return (
        r"""
    new Promise((resolve) => {
      const config =
    """
        + config
        + r""";
      let attempts = 0;
      const check = () => {
        const summary = document.querySelector('[data-om-table-summary]')?.textContent.replace(/\s+/g, ' ').trim() || '';
        if (summary === 'Showing 11 to 20 of 22 entries' || attempts++ > 240) {
          const failures = [];
          const locationValue = location.pathname + location.search;
          const rows = document.querySelectorAll('[data-om-table-row]').length;
          const pageSize = document.querySelector('[data-om-table-page-size-control]')?.value || '';
          const page = document.querySelector('[data-om-table-page="2"]')?.getAttribute('aria-current') || '';
          const sort = document.querySelector('[data-om-table-sort="name"]')?.getAttribute('aria-sort') || '';
          const query = document.querySelector('[data-om-table-filter]')?.value || '';
          if (locationValue !== config.expectedLocation) failures.push(`restored URL is ${locationValue}`);
          if (summary !== 'Showing 11 to 20 of 22 entries') failures.push(`restored summary is ${summary}`);
          if (rows !== 10) failures.push(`restored row count is ${rows}`);
          if (pageSize !== '10') failures.push(`restored page size is ${pageSize}`);
          if (page !== 'page') failures.push(`restored page 2 aria-current is ${page}`);
          if (sort !== 'descending') failures.push(`restored name sort is ${sort}`);
          if (query !== 'Integration Sample') failures.push(`restored query is ${query}`);
          const edit = document.querySelector('[data-om-table-row] [data-om-column="action"] a');
          if (!edit) failures.push('restored page has no edit URL');
          resolve({ failures, editPath: edit ? new URL(edit.href).pathname : '' });
          return;
        }
        setTimeout(check, 50);
      };
      check();
    })
    """
    )


def _reload_restored_full_history_list_state_script(expected_location: str) -> str:
    """Reload a Turbo-restored Table and require its internal request state to survive."""
    config = json.dumps({"expectedLocation": expected_location})
    return (
        r"""
    new Promise((resolve) => {
      const config =
    """
        + config
        + r""";
      const table = document.querySelector('[data-om-component="table"]');
      if (!table) {
        resolve({ failures: ['restored table is missing before reload'] });
        return;
      }
      const failures = [];
      let settled = false;
      const finish = (result) => {
        if (settled) return;
        settled = true;
        resolve(result);
      };
      const timeout = setTimeout(() => finish({ failures: ['restored table reload timed out'] }), 10000);
      table.addEventListener('om:table:error', () => {
        clearTimeout(timeout);
        finish({ failures: ['restored table reload emitted an error'] });
      }, { once: true });
      table.addEventListener('om:table:refresh', (event) => {
        clearTimeout(timeout);
        const request = new URL(event.detail?.url || '', location.href);
        const expected = new URL(config.expectedLocation, location.href);
        for (const name of ['q', 'page_size', 'page', 'sort']) {
          if (request.searchParams.get(name) !== expected.searchParams.get(name)) {
            failures.push(`reload ${name} is ${request.searchParams.get(name) || ''}`);
          }
        }
        setTimeout(() => {
          const locationValue = location.pathname + location.search;
          if (locationValue !== config.expectedLocation) failures.push(`reload URL is ${locationValue}`);
          finish({ failures, request: request.pathname + request.search });
        }, 50);
      }, { once: true });
      setTimeout(() => table.dispatchEvent(new CustomEvent('om:table:reload')), 250);
    })
    """
    )


def _history_cancel_script(expected_location: str, label: str) -> str:
    config = json.dumps({"expectedLocation": expected_location, "label": label})
    return (
        r"""
    new Promise((resolve) => {
      const config =
    """
        + config
        + r""";
      const failures = [];
      const cancel = document.querySelector('[data-om-history-back]');
      if (!cancel) failures.push(`${config.label} Cancel is missing`);
      if (!cancel?.getAttribute('data-om-history-fallback')) failures.push(`${config.label} Cancel fallback is missing`);
      const restorationIndex = history.state?.turbo?.restorationIndex;
      if (typeof restorationIndex !== 'number' || restorationIndex <= 0) {
        failures.push(`${config.label} page has no restorable Turbo history`);
      }
      if (failures.length) {
        resolve({ failures });
        return;
      }
      cancel.click();
      let attempts = 0;
      const check = () => {
        const locationValue = location.pathname + location.search;
        const restoredIndex = history.state?.turbo?.restorationIndex;
        const frame = document.querySelector('#oldman-main');
        const restorationSettled = !document.documentElement.hasAttribute('data-turbo-preview')
          && (!frame || (
            frame.getAttribute('data-om-frame-state') === 'mounted'
            && !frame.hasAttribute('busy')
            && frame.getAttribute('data-om-preloader-status') !== 'loading'
          ));
        if (
          locationValue === config.expectedLocation
          && typeof restoredIndex === 'number'
          && restoredIndex < restorationIndex
          && restorationSettled
        ) {
          resolve({ failures, restorationIndex });
          return;
        }
        if (attempts++ > 240) {
          failures.push(`${config.label} Cancel restored ${locationValue}`);
          resolve({ failures, restorationIndex });
          return;
        }
        setTimeout(check, 50);
      };
      check();
    })
    """
    )


def _user_table_contract_script() -> str:
    return r"""
    new Promise((resolve) => {
      let attempts = 0;
      const check = () => {
        const table = document.querySelector('[data-om-component="table"]');
        const partial = table?.querySelector('[data-om-table-partial]:not([data-om-initial-table-partial])');
        if (partial || attempts++ > 180) {
          const failures = [];
          const requiredFilters = ['q', 'is_active', 'is_staff', 'is_superuser', 'last_login_from', 'last_login_to'];
          const requiredColumns = ['username', 'is_active', 'is_staff', 'is_superuser', 'last_login_at', 'action'];
          const expectedHeaders = {
            username: 'Username',
            is_active: 'Status',
            is_staff: 'Staff',
            is_superuser: 'Superuser',
            last_login_at: 'Last Login',
            action: 'Action'
          };
          for (const name of requiredFilters) {
            if (!document.querySelector(`[data-om-component="table-filter-form"] [name="${name}"]`)) failures.push(`missing user filter ${name}`);
          }
          for (const name of requiredColumns) {
            if (!document.querySelector(`[data-om-column="${name}"]`)) failures.push(`missing user column ${name}`);
            const header = document.querySelector(`th[data-om-column="${name}"]`)?.textContent.replace(/\s+/g, ' ').trim() || '';
            if (header !== expectedHeaders[name]) failures.push(`user header ${name} is ${header}`);
          }
          if (table?.getAttribute('data-om-table-page-size') !== '10') failures.push('user table page size is not 10');
          if (!document.querySelector('[data-om-table-select-all]')) failures.push('user table selection contract is missing');
          const action = document.querySelector('[data-om-table-row] [data-om-column="action"]');
          const statusBadge = document.querySelector('[data-om-table-row] [data-om-column="is_active"] .om-badge');
          if (!statusBadge || getComputedStyle(statusBadge).backgroundColor === 'rgba(0, 0, 0, 0)') {
            failures.push('user status badge styling is missing');
          }
          const passwordAction = action?.querySelector('button[data-om-modal-target="#user-password-modal"][data-om-modal-url$="/password-modal"]');
          const statusAction = action?.querySelector('button[data-om-modal-target="#user-status-modal"][data-om-modal-url$="/status-modal"]');
          const deleteAction = action?.querySelector('button[data-om-modal-target="#user-delete-modal"][data-om-modal-url$="/delete-modal"]');
          if (!passwordAction) failures.push('missing password shared Modal Form row action');
          if (!statusAction) failures.push('missing status shared Modal Form row action');
          if (!deleteAction) failures.push('missing delete shared Modal Form row action');
          for (const target of ['#user-password-modal', '#user-status-modal', '#user-delete-modal']) {
            const modal = document.querySelector(target);
            if (!modal) failures.push(`missing ${target} shell`);
            else if (modal.getAttribute('data-om-component') !== 'modal') failures.push(`${target} is not a shared Modal Form`);
            else if (!modal.hidden || modal.getAttribute('aria-hidden') !== 'true') failures.push(`${target} is open before interaction`);
          }
          if (!action?.querySelector('[data-om-dropdown-toggle]')) failures.push('shared Dropdown row action is missing');
          for (const icon of Array.from(action?.querySelectorAll('i[class*="ri-"]') || [])) {
            const iconStyle = getComputedStyle(icon, '::before');
            const mask = iconStyle.webkitMaskImage || iconStyle.maskImage || '';
            if (!mask.includes('data:image/svg+xml')) failures.push('row action icon is missing: ' + icon.className);
          }
          resolve({ failures });
          return;
        }
        setTimeout(check, 50);
      };
      check();
    })
    """


def _filtered_user_state_script(username: str, *, expect_missing: bool) -> str:
    config = json.dumps({"username": username, "expectMissing": expect_missing})
    return (
        r"""
        new Promise((resolve) => {
          const config =
        """
        + config
        + r""";
          let attempts = 0;
          const check = () => {
            const table = document.querySelector('[data-om-component="table"]');
            const partial = table?.querySelector('[data-om-table-partial]:not([data-om-initial-table-partial])');
            if (partial || attempts++ > 180) {
              const failures = [];
              const rows = Array.from(document.querySelectorAll('[data-om-table-row]'));
              const row = rows.find((item) => item.querySelector('[data-om-column="username"]')?.textContent.trim() === config.username);
              if (config.expectMissing) {
                if (row || rows.length) failures.push(`expected no ${config.username} row, got ${rows.length}`);
                resolve({ failures });
                return;
              }
              if (rows.length !== 1) failures.push(`filtered ${config.username} returned ${rows.length} rows`);
              if (!row) failures.push(`filtered row is not ${config.username}`);
              const edit = row?.querySelector('[data-om-column="username"] a');
              const actions = Array.from(row?.querySelectorAll('[data-om-column="action"] a, [data-om-column="action"] button') || []);
              const modalActionFor = (suffix) => actions.find((item) => item.getAttribute('data-om-modal-url')?.endsWith(suffix));
              const modalPathFor = (suffix) => {
                const action = modalActionFor(suffix);
                const url = action?.getAttribute('data-om-modal-url');
                return url ? new URL(url, location.href).pathname : '';
              };
              const deleteAction = modalActionFor('/delete-modal');
              const editPath = edit ? new URL(edit.href).pathname : '';
              const passwordAction = modalActionFor('/password-modal');
              const statusAction = modalActionFor('/status-modal');
              const passwordPath = modalPathFor('/password-modal');
              const statusPath = modalPathFor('/status-modal');
              const deletePath = modalPathFor('/delete-modal');
              if (!editPath) failures.push('user row has no edit link');
              if (!passwordPath) failures.push('user row has no password action');
              if (!statusPath) failures.push('user row has no status action');
              if (!deletePath) failures.push('user row has no delete action');
              if (passwordAction?.tagName !== 'BUTTON' || passwordAction?.getAttribute('data-om-modal-target') !== '#user-password-modal') {
                failures.push('user password action does not target shared Modal Form');
              }
              if (statusAction?.tagName !== 'BUTTON' || statusAction?.getAttribute('data-om-modal-target') !== '#user-status-modal') {
                failures.push('user status action does not target shared Modal Form');
              }
              if (deleteAction?.tagName !== 'BUTTON' || deleteAction?.getAttribute('data-om-modal-target') !== '#user-delete-modal') {
                failures.push('user delete action does not target shared Modal Form');
              }
              resolve({
                failures,
                editPath,
                passwordPath,
                statusPath,
                deletePath,
                passwordTarget: passwordAction?.getAttribute('data-om-modal-target') || '',
                statusTarget: statusAction?.getAttribute('data-om-modal-target') || '',
                status: row?.querySelector('[data-om-column="is_active"]')?.textContent.trim() || ''
              });
              return;
            }
            setTimeout(check, 50);
          };
          check();
        })
        """
    )


def _user_new_history_cancel_script(expected_location: str, username: str) -> str:
    config = json.dumps({"expectedLocation": expected_location, "username": username})
    return (
        r"""
        new Promise((resolve) => {
          const config =
        """
        + config
        + r""";
          const failures = [];
          let attempts = 0;
          // 临时诊断：记录每一次表格刷新的请求 URL 和当时的页面 URL。
          const waitForList = (canonicalLocation = '', phase = 'initial') => {
            const table = document.querySelector('[data-om-component="table"]');
            const q = document.querySelector('[data-om-component="table-filter-form"] [name="q"]');
            const active = document.querySelector('[data-om-component="table-filter-form"] [name="is_active"]');
            const staff = document.querySelector('[data-om-component="table-filter-form"] [name="is_staff"]');
            const superuser = document.querySelector('[data-om-component="table-filter-form"] [name="is_superuser"]');
            const pageSize = table?.querySelector('[data-om-table-page-size-control]');
            const sort = table?.querySelector('[data-om-table-sort="username"]');
            const row = Array.from(document.querySelectorAll('[data-om-table-row]')).find(
              (item) => item.querySelector('[data-om-column="username"]')?.textContent.trim() === config.username
            );
            // Turbo restores the already-rendered table from its page snapshot.
            // That restored DOM can be complete even though no new refresh sets
            // the transient table status back to "success".
            const initialLoadSettled = phase !== 'initial' || table?.dataset.omStatus === 'success';
            if (row && initialLoadSettled) {
              const expectedUrl = new URL(config.expectedLocation, location.origin);
              const actualUrl = new URL(location.href);
              const expectedEntries = Array.from(expectedUrl.searchParams.entries());
              const actualEntries = Array.from(actualUrl.searchParams.entries());
              const hasExpectedQuery = expectedEntries.every(
                ([key, value]) => actualUrl.searchParams.getAll(key).includes(value)
              );
              const hasUnexpectedQuery = actualEntries.some(
                ([key, value]) => !expectedEntries.some(([expectedKey, expectedValue]) => expectedKey === key && expectedValue === value)
              );
              if (actualUrl.pathname !== expectedUrl.pathname || !hasExpectedQuery || hasUnexpectedQuery) {
                failures.push(`list URL is ${location.pathname}${location.search}`);
              }
              if (canonicalLocation && location.pathname + location.search !== canonicalLocation) {
                // 失败时把现场带上：光说"URL 不对"没法判断是谁改写了这条历史条目。
                const tableRoot = document.querySelector('[data-om-component="table"]');
                const filterAttrs = tableRoot
                  ? Array.from(tableRoot.attributes)
                      .filter((attribute) => attribute.name.startsWith('data-om-filter-') || attribute.name.startsWith('data-om-table-initial') || attribute.name === 'data-om-table-page-size')
                      .map((attribute) => `${attribute.name}=${attribute.value}`)
                  : ['table root missing'];
                failures.push(
                  `restored canonical URL is ${location.pathname}${location.search}`
                  + ` (expected ${canonicalLocation}; root ${filterAttrs.join(' ')};`
                  + ` restorationIndex=${history.state?.turbo?.restorationIndex};`
                  + ` tableStatus=${tableRoot?.dataset.omStatus})`
                );
              }
              if (q?.value !== config.username) failures.push(`restored q is ${q?.value || 'missing'}`);
              if (active?.value !== 'true') failures.push(`restored is_active is ${active?.value || 'missing'}`);
              if (staff?.value !== 'true') failures.push(`restored is_staff is ${staff?.value || 'missing'}`);
              if (superuser?.value !== 'true') failures.push(`restored is_superuser is ${superuser?.value || 'missing'}`);
              if (pageSize?.value !== '20') failures.push(`restored page_size is ${pageSize?.value || 'missing'}`);
              if (sort?.getAttribute('aria-sort') !== 'descending') failures.push('restored username sort is not descending');
              return { ready: true, failures };
            }
            if (attempts++ > 240) {
              return {
                ready: false,
                failures: [
                  ...failures,
                  `user list did not reach expected filtered state (${phase}: status=${table?.dataset.omStatus || 'missing'}, rows=${document.querySelectorAll('[data-om-table-row]').length}, row=${Boolean(row)}, location=${location.pathname}${location.search})`
                ]
              };
            }
            return null;
          };
          const start = () => {
            const state = waitForList();
            if (!state) {
              setTimeout(start, 50);
              return;
            }
            if (!state.ready || state.failures.length) {
              resolve(state);
              return;
            }
            const canonicalLocation = location.pathname + location.search;
            const newLink = document.querySelector(`a[href="/admin/oldman_user/new"]`);
            if (!newLink) {
              resolve({ failures: ['New User link is missing'] });
              return;
            }
            // Turbo pushes the /new URL and renders the form before it promotes the frame navigation
            // to a page visit; going back before that visit starts lets it cancel the restore, and the
            // list URL keeps the form. The navigation is over at its turbo:load.
            let newPageLoaded = false;
            document.addEventListener('turbo:load', () => { newPageLoaded = true; }, { once: true });
            newLink.click();
            attempts = 0;
            const waitForNew = () => {
              const form = document.querySelector('form[data-om-component="form"][data-om-form]');
              if (location.pathname === '/admin/oldman_user/new' && form && newPageLoaded) {
                const cancel = form.querySelector('.om-form-actions [data-om-history-back]');
                const restorationIndex = history.state?.turbo?.restorationIndex;
                if (!cancel) failures.push('new-user form has no shared HistoryBack Cancel');
                if (cancel?.getAttribute('data-om-history-fallback') !== '/admin/oldman_user') {
                  failures.push(`new-user Cancel fallback is ${cancel?.getAttribute('data-om-history-fallback') || 'missing'}`);
                }
                if (typeof restorationIndex !== 'number' || restorationIndex <= 0) {
                  failures.push('new-user page has no restorable Turbo history');
                }
                if (failures.length) {
                  resolve({ failures });
                  return;
                }
                cancel.click();
                attempts = 0;
                const waitForRestore = () => {
                  const restored = waitForList(canonicalLocation, 'restored');
                  if (restored?.ready || restored?.failures.length) {
                    resolve({ failures: restored.failures, restorationIndex });
                    return;
                  }
                  setTimeout(waitForRestore, 50);
                };
                waitForRestore();
                return;
              }
              if (attempts++ > 240) {
                resolve({ failures: ['New User link did not open the shared user form'] });
                return;
              }
              setTimeout(waitForNew, 50);
            };
            waitForNew();
          };
          start();
        })
        """
    )


def _prepare_direct_user_new_cancel_script(list_path: str) -> str:
    expected_fallback = json.dumps(list_path)
    return (
        r"""
        new Promise((resolve) => {
          const expectedFallback =
        """
        + expected_fallback
        + r""";
          let attempts = 0;
          const check = () => {
            const form = document.querySelector('form[data-om-component="form"][data-om-form]');
            const validator = form?.querySelector('[data-om-component="form-validator"]');
            const cancel = form?.querySelector('.om-form-actions [data-om-history-back]');
            if (form?.dataset.omComponentState === 'mounted' && validator?.dataset.omComponentState === 'mounted') {
              const failures = [];
              if (!cancel) failures.push('direct new-user page has no HistoryBack Cancel');
              if (cancel?.getAttribute('data-om-history-fallback') !== expectedFallback) {
                failures.push(`direct new-user fallback is ${cancel?.getAttribute('data-om-history-fallback') || 'missing'}`);
              }
              const currentState = history.state || {};
              history.replaceState({ ...currentState, turbo: { ...(currentState.turbo || {}), restorationIndex: 0 } }, '', location.href);
              if (history.state?.turbo?.restorationIndex !== 0) failures.push('direct-entry Turbo history was not reset');
              resolve({ failures, clicked: failures.length === 0 });
              return;
            }
            if (attempts++ > 240) {
              resolve({ failures: ['direct new-user shared Form/FormValidator did not mount'], clicked: false });
              return;
            }
            setTimeout(check, 50);
          };
          check();
        })
        """
    )


def _user_create_form_lifecycle_script(root_username: str) -> str:
    config = json.dumps(
        {
            "rootUsername": root_username,
            "username": USER_MANAGEMENT_GATE_USERNAME,
            "password": USER_MANAGEMENT_GATE_PASSWORD,
        }
    )
    return (
        r"""
        (async () => {
          const config =
        """
        + config
        + r""";
          const failures = [];
          const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const waitFor = async (predicate, attempts = 240) => {
            for (let index = 0; index < attempts; index += 1) {
              if (predicate()) return true;
              await sleep(50);
            }
            return false;
          };
          const form = document.querySelector('form[data-om-component="form"][data-om-form]');
          const validator = form?.querySelector('[data-om-component="form-validator"]');
          const feedback = document.querySelector('#admin-oldman_user-form-feedback[data-om-component="feedback"]');
          const submit = form?.querySelector('button[type="submit"], input[type="submit"]');
          const cancel = form?.querySelector('.om-form-actions [data-om-history-back]');
          if (!form || !validator || !feedback || !submit) {
            return { failures: ['create GET did not render shared Form, FormValidator and Feedback'], expectedResponses: [] };
          }
          if (form.dataset.omComponentState !== 'mounted') failures.push('create shared Form is not mounted');
          if (validator.dataset.omComponentState !== 'mounted') failures.push('create shared FormValidator is not mounted');
          if (feedback.dataset.omComponentState !== 'mounted') failures.push('create shared Feedback is not mounted');
          if (!form.hasAttribute('data-om-form-validate')) failures.push('create shared Form has no native-validation contract');
          if (new URL(form.action, location.href).pathname !== '/admin/oldman_user/new') failures.push(`create action is ${form.action}`);
          if (!cancel?.hasAttribute('data-om-history-back')) failures.push('create Cancel is not shared HistoryBack');

          const actionPath = new URL(form.action, location.href).pathname;
          const responses = [];
          const originalOpen = XMLHttpRequest.prototype.open;
          XMLHttpRequest.prototype.open = function(...args) {
            const method = String(args[0] || 'GET').toUpperCase();
            const requestUrl = new URL(String(args[1] || ''), location.href);
            if (requestUrl.pathname === actionPath) {
              this.addEventListener('loadend', () => {
                let payload = null;
                try { payload = JSON.parse(this.responseText || 'null'); } catch {}
                responses.push({ method, status: this.status, url: this.responseURL || requestUrl.href, payload });
              }, { once: true });
            }
            return originalOpen.apply(this, args);
          };
          const restore = () => {
            XMLHttpRequest.prototype.open = originalOpen;
          };
          const fill = (name, value) => {
            const field = form.querySelector(`[name="${name}"]`);
            if (!field) {
              failures.push(`missing create field ${name}`);
              return null;
            }
            if (field.type === 'checkbox') field.checked = Boolean(value);
            else field.value = String(value);
            field.dispatchEvent(new Event('input', { bubbles: true }));
            field.dispatchEvent(new Event('change', { bubbles: true }));
            return field;
          };

          const beforeNative = responses.length;
          submit.click();
          await sleep(200);
          const usernameField = form.querySelector('[name="username"]');
          if (responses.length !== beforeNative) failures.push(`create native invalid sent ${responses.length - beforeNative} request(s)`);
          if (!form.classList.contains('was-validated')) failures.push('create native invalid did not mark the Form');
          if (usernameField?.checkValidity() !== false) failures.push('create native invalid did not reject empty username');

          fill('username', 'browser_mismatch_candidate');
          fill('email', 'browser-mismatch@example.test');
          fill('display_name', 'Browser Mismatch');
          fill('password', config.password);
          fill('confirm_password', `${config.password}x`);
          fill('is_active', true);
          fill('is_staff', true);
          fill('is_superuser', false);
          submit.click();
          const mismatchReady = await waitFor(() => {
            const error = form.querySelector('[data-om-error-for="confirm_password"]');
            const message = form.querySelector('[data-om-form-message]');
            return responses.length >= 1
              && form.querySelector('[name="confirm_password"]')?.getAttribute('aria-invalid') === 'true'
              && Boolean(error?.textContent.includes('Passwords do not match'))
              && Boolean(message?.textContent)
              && !message.hidden;
          });
          const mismatch = responses[0];
          if (!mismatchReady) failures.push('create JSON error did not render confirmation error and form message');
          if (mismatch?.method !== 'POST' || mismatch?.status !== 200) failures.push(`create mismatch response is ${mismatch?.method} ${mismatch?.status}`);
          if (mismatch?.payload?.error_code !== 1100 || mismatch?.payload?.actions?.length !== 0) {
            failures.push('create mismatch response did not use the JSON business-error contract');
          }
          if (mismatch?.payload?.errors?.confirm_password?.includes?.('Passwords do not match') !== true) {
            failures.push('create mismatch JSON payload is missing confirm_password');
          }
          if (location.pathname !== actionPath) failures.push(`create JSON error navigated to ${location.pathname}`);

          fill('username', config.rootUsername);
          fill('confirm_password', config.password);
          submit.click();
          const duplicateReady = await waitFor(() => {
            const error = form.querySelector('[data-om-error-for="username"]');
            const message = form.querySelector('[data-om-form-message]');
            return responses.length >= 2
              && usernameField?.getAttribute('aria-invalid') === 'true'
              && Boolean(error?.textContent.includes('Username already exists'))
              && Boolean(message?.textContent)
              && !message.hidden;
          });
          const duplicate = responses[1];
          if (!duplicateReady) failures.push('create duplicate JSON error did not render username error and form message');
          if (duplicate?.method !== 'POST' || duplicate?.status !== 200) failures.push(`create duplicate response is ${duplicate?.method} ${duplicate?.status}`);
          if (duplicate?.payload?.errors?.username?.includes?.('Username already exists') !== true) {
            failures.push('create duplicate JSON payload is missing username');
          }

          fill('username', config.username);
          fill('email', 'browser-lifecycle@example.test');
          fill('display_name', 'Browser Lifecycle');
          submit.click();
          let successFeedbackText = '';
          const successReady = await waitFor(() => {
            const toast = document.querySelector('.toastify.om-toast.on');
            successFeedbackText = toast?.textContent || '';
            return responses.length >= 3 && Boolean(toast);
          });
          const success = responses[2];
          const actionNames = success?.payload?.actions?.map?.((action) => action.action) || [];
          const feedbackTitle = success?.payload?.actions?.[0]?.title || '';
          const redirect = success?.payload?.actions?.find?.((action) => action.action === 'redirect');
          const editPath = redirect?.url ? new URL(redirect.url, location.href).pathname : '';
          if (!successReady) failures.push('create success Feedback Action did not complete before redirect');
          if (success?.method !== 'POST' || success?.status < 200 || success?.status >= 300) {
            failures.push(`create success response is ${success?.method} ${success?.status}`);
          }
          if (actionNames.join(',') !== 'feedback,dashboard_activity,redirect') failures.push(`create success actions are ${actionNames.join(',') || 'missing'}`);
          if (!feedbackTitle || !successFeedbackText.includes(feedbackTitle)) failures.push('create success Feedback did not render its Action title');
          if (redirect?.delay_ms !== 1200) failures.push('create redirect delay is not 1200ms');
          if (!/^\/admin\/oldman_user\/[^/]+\/edit$/.test(editPath)) failures.push(`create redirect path is ${editPath || 'missing'}`);
          if (Object.keys(success?.payload?.data || {}).length !== 0) failures.push('create success data contains UI controls');
          restore();
          return {
            failures,
            editPath,
            expectedResponses: []
          };
        })()
        """
    )


def _user_edit_form_lifecycle_script(root_username: str) -> str:
    config = json.dumps({"rootUsername": root_username, "username": USER_MANAGEMENT_GATE_USERNAME})
    return (
        r"""
        (async () => {
          const config =
        """
        + config
        + r""";
          const failures = [];
          const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const waitFor = async (predicate, attempts = 240) => {
            for (let index = 0; index < attempts; index += 1) {
              if (predicate()) return true;
              await sleep(50);
            }
            return false;
          };
          const form = document.querySelector('form[data-om-component="form"][data-om-form]');
          const validator = form?.querySelector('[data-om-component="form-validator"]');
          const feedback = document.querySelector('#admin-oldman_user-form-feedback[data-om-component="feedback"]');
          const submit = form?.querySelector('button[type="submit"], input[type="submit"]');
          if (!form || !validator || !feedback || !submit) {
            return { failures: ['edit GET did not render shared Form, FormValidator and Feedback'], expectedResponses: [] };
          }
          const editPath = new URL(form.action, location.href).pathname;
          if (!/^\/admin\/oldman_user\/[^/]+\/edit$/.test(editPath)) failures.push(`edit action is ${editPath}`);
          if (location.pathname !== editPath) failures.push(`edit GET path is ${location.pathname}`);
          if (form.dataset.omComponentState !== 'mounted') failures.push('edit shared Form is not mounted');
          if (validator.dataset.omComponentState !== 'mounted') failures.push('edit shared FormValidator is not mounted');
          if (feedback.dataset.omComponentState !== 'mounted') failures.push('edit shared Feedback is not mounted');
          if (!form.hasAttribute('data-om-form-validate')) failures.push('edit shared Form has no native-validation contract');

          const responses = [];
          const originalOpen = XMLHttpRequest.prototype.open;
          XMLHttpRequest.prototype.open = function(...args) {
            const method = String(args[0] || 'GET').toUpperCase();
            const requestUrl = new URL(String(args[1] || ''), location.href);
            if (requestUrl.pathname === editPath) {
              this.addEventListener('loadend', () => {
                let payload = null;
                try { payload = JSON.parse(this.responseText || 'null'); } catch {}
                responses.push({ method, status: this.status, url: this.responseURL || requestUrl.href, payload });
              }, { once: true });
            }
            return originalOpen.apply(this, args);
          };
          const restore = () => {
            XMLHttpRequest.prototype.open = originalOpen;
          };
          const field = (name) => form.querySelector(`[name="${name}"]`);
          const setValue = (name, value) => {
            const control = field(name);
            if (!control) {
              failures.push(`missing edit field ${name}`);
              return;
            }
            if (control.type === 'checkbox') control.checked = Boolean(value);
            else control.value = String(value);
            control.dispatchEvent(new Event('input', { bubbles: true }));
            control.dispatchEvent(new Event('change', { bubbles: true }));
          };

          setValue('username', '');
          submit.click();
          await sleep(200);
          if (responses.length !== 0) failures.push(`edit native invalid sent ${responses.length} request(s)`);
          if (!form.classList.contains('was-validated')) failures.push('edit native invalid did not mark the Form');
          if (field('username')?.checkValidity() !== false) failures.push('edit native invalid did not reject empty username');

          setValue('username', config.rootUsername);
          submit.click();
          const duplicateReady = await waitFor(() => {
            const error = form.querySelector('[data-om-error-for="username"]');
            const message = form.querySelector('[data-om-form-message]');
            return responses.length >= 1
              && field('username')?.getAttribute('aria-invalid') === 'true'
              && Boolean(error?.textContent.includes('Username already exists'))
              && Boolean(message?.textContent)
              && !message.hidden;
          });
          const duplicate = responses[0];
          if (!duplicateReady) failures.push('edit duplicate JSON error did not render username error and form message');
          if (duplicate?.method !== 'POST' || duplicate?.status !== 200) failures.push(`edit duplicate response is ${duplicate?.method} ${duplicate?.status}`);
          if (duplicate?.payload?.errors?.username?.includes?.('Username already exists') !== true) {
            failures.push('edit duplicate JSON payload is missing username');
          }
          if (location.pathname !== editPath) failures.push(`edit JSON error navigated to ${location.pathname}`);

          setValue('username', config.username);
          setValue('display_name', 'Browser Lifecycle Updated');
          setValue('is_active', true);
          setValue('is_staff', true);
          setValue('is_superuser', false);
          submit.click();
          let successFeedbackText = '';
          const successReady = await waitFor(() => {
            const toast = document.querySelector('.toastify.om-toast.on');
            successFeedbackText = toast?.textContent || '';
            return responses.length >= 2 && Boolean(toast);
          });
          const success = responses[1];
          const actionNames = success?.payload?.actions?.map?.((action) => action.action) || [];
          const feedbackTitle = success?.payload?.actions?.[0]?.title || '';
          const redirect = success?.payload?.actions?.find?.((action) => action.action === 'redirect');
          const responsePath = redirect?.url ? new URL(redirect.url, location.href).pathname : '';
          if (!successReady) failures.push('edit success Feedback Action did not complete before redirect');
          if (success?.method !== 'POST' || success?.status < 200 || success?.status >= 300) {
            failures.push(`edit success response is ${success?.method} ${success?.status}`);
          }
          if (actionNames.join(',') !== 'feedback,dashboard_activity,redirect') failures.push(`edit success actions are ${actionNames.join(',') || 'missing'}`);
          if (!feedbackTitle || !successFeedbackText.includes(feedbackTitle)) failures.push('edit success Feedback did not render its Action title');
          if (redirect?.delay_ms !== 1200) failures.push('edit redirect delay is not 1200ms');
          if (responsePath !== editPath) failures.push(`edit success redirect is ${responsePath || 'missing'}, expected ${editPath}`);
          if (Object.keys(success?.payload?.data || {}).length !== 0) failures.push('edit success data contains UI controls');
          restore();
          return {
            failures,
            editPath,
            expectedResponses: []
          };
        })()
        """
    )


def _user_password_validation_script(modal_target: str) -> str:
    config = json.dumps({"modalTarget": modal_target})
    return (
        r"""
        new Promise((resolve) => {
          const config =
        """
        + config
        + r""";
          const failures = [];
          const modal = document.querySelector(config.modalTarget);
          const form = modal?.querySelector('form[data-om-form]');
          const password = form?.querySelector('[name="password"]');
          const confirmation = form?.querySelector('[name="confirm_password"]');
          const submit = form?.querySelector('button[type="submit"], input[type="submit"]');
          const validator = form?.querySelector('[data-om-component="form-validator"]');
          if (!modal || modal.hidden || !form || !validator || !password || !confirmation || !submit) {
            resolve({ failures: ['open password Modal Form is incomplete'], responseUrls: [] });
            return;
          }

          const startPath = location.pathname;
          const actionPath = new URL(form.action, location.href).pathname;
          let responseStatus = null;
          let responseUrl = form.action;
          let responsePayload = null;
          let requestCount = 0;
          const originalOpen = XMLHttpRequest.prototype.open;
          XMLHttpRequest.prototype.open = function(...args) {
            const requestUrl = new URL(String(args[1] || ''), location.href);
            if (requestUrl.pathname === actionPath) {
              requestCount += 1;
              this.addEventListener('loadend', () => {
                responseStatus = this.status;
                responseUrl = this.responseURL || requestUrl.href;
                try { responsePayload = JSON.parse(this.responseText || 'null'); } catch {}
              }, { once: true });
            }
            return originalOpen.apply(this, args);
          };
          const restoreXhr = () => { XMLHttpRequest.prototype.open = originalOpen; };

          password.value = 'abcdefgh';
          confirmation.value = 'abcdefgh';
          password.dispatchEvent(new Event('input', { bubbles: true }));
          confirmation.dispatchEvent(new Event('input', { bubbles: true }));
          submit.click();

          setTimeout(() => {
            if (requestCount !== 0) failures.push(`native password validation sent ${requestCount} request(s)`);
            if (!form.classList.contains('was-validated')) failures.push('native password validation did not mark the form');
            if (password.checkValidity()) failures.push('native password pattern accepted a password without a number');
            if (form.dataset.omComponent !== 'form' || form.dataset.omComponentState !== 'mounted') failures.push('shared Form is not mounted');
            if (validator.dataset.omComponentState !== 'mounted') failures.push('shared FormValidator is not mounted');

            password.value = 'abcdefgh1';
            confirmation.value = 'abcdefgh2';
            password.dispatchEvent(new Event('input', { bubbles: true }));
            confirmation.dispatchEvent(new Event('input', { bubbles: true }));
            submit.click();

            let attempts = 0;
            const check = () => {
              const fieldError = modal.querySelector('[data-om-error-for="confirm_password"]');
              const hasFieldError = confirmation.getAttribute('aria-invalid') === 'true'
                && Boolean(fieldError?.textContent.includes('Passwords do not match'))
                && !fieldError.hidden;
              const message = form.querySelector('[data-om-form-message]');
              const hasMessage = Boolean(message?.textContent) && !message.hidden && message.dataset.omTone === 'error';
              if (responseStatus !== null && hasFieldError && hasMessage) {
                restoreXhr();
                if (responseStatus !== 200) failures.push(`password Modal Form validation returned ${responseStatus}`);
                if (requestCount !== 1) failures.push(`password server validation sent ${requestCount} requests`);
                if (modal.hidden || modal.dataset.omState !== 'open') failures.push('business error closed password Modal Form');
                if (form.dataset.omStatus !== 'error') failures.push(`password Form status is ${form.dataset.omStatus || 'missing'}`);
                if (location.pathname !== startPath) failures.push(`business error navigated to ${location.pathname}`);
                if (responsePayload?.error_code !== 1100 || responsePayload?.actions?.length !== 0) {
                  failures.push('password response did not use the JSON business-error contract');
                }
                if (!responsePayload?.errors?.confirm_password?.includes?.('Passwords do not match')) {
                  failures.push('password response is missing confirm_password');
                }
                resolve({ failures, responseStatus, responseUrls: [], responsePayload });
                return;
              }
              if (attempts++ > 240) {
                restoreXhr();
                failures.push(
                  `password Modal Form did not render its JSON field error (status=${responseStatus}, invalid=${confirmation.getAttribute('aria-invalid')})`
                );
                if (!hasMessage) failures.push('password Modal Form did not show its message');
                resolve({ failures, responseStatus, responseUrls: [], responsePayload });
                return;
              }
              setTimeout(check, 50);
            };
            check();
          }, 150);
        })
        """
    )


def _current_user_edit_protection_script() -> str:
    return r"""
    (async () => {
      const failures = [];
      const form = document.querySelector('form[data-om-form]');
      const csrf = form?.querySelector('[name="csrfmiddlewaretoken"]')?.value;
      if (!form || !csrf) return { failures: ['current-user form or CSRF token is missing'], responseUrls: [] };
      const value = (name) => form.querySelector(`[name="${name}"]`)?.value || '';
      const body = new URLSearchParams({
        csrfmiddlewaretoken: csrf,
        username: value('username'),
        email: value('email'),
        display_name: value('display_name')
      });
      const response = await fetch(form.action, { method: 'POST', headers: { Accept: 'text/html' }, body });
      const text = await response.text();
      if (response.status !== 422) failures.push(`current-user demotion returned ${response.status}`);
      for (const message of [
        'cannot disable current user',
        'cannot remove current user staff access',
        'cannot remove current user superuser access'
      ]) {
        if (!text.includes(message)) failures.push(`missing protection message: ${message}`);
      }
      return { failures, responseUrls: [response.url] };
    })()
    """


def _user_delete_protection_script(modal_target: str) -> str:
    config = json.dumps({"modalTarget": modal_target})
    return (
        r"""
        new Promise((resolve) => {
          const config =
        """
        + config
        + r""";
          const failures = [];
          const modal = document.querySelector(config.modalTarget);
          const form = modal?.querySelector('form[data-om-form]');
          const submit = form?.querySelector('button[type="submit"], input[type="submit"]');
          if (!modal || modal.hidden || !form || !submit) {
            resolve({ failures: ['superuser delete Modal Form is incomplete'], expectedResponses: [] });
            return;
          }
          const startLocation = location.href;
          const actionPath = new URL(form.action, location.href).pathname;
          let response = null;
          const originalOpen = XMLHttpRequest.prototype.open;
          XMLHttpRequest.prototype.open = function(...args) {
            const method = String(args[0] || 'GET').toUpperCase();
            const requestUrl = new URL(String(args[1] || ''), location.href);
            if (requestUrl.pathname === actionPath) {
              this.addEventListener('loadend', () => {
                let payload = null;
                try { payload = JSON.parse(this.responseText || 'null'); } catch {}
                response = { method, status: this.status, url: this.responseURL || requestUrl.href, payload };
              }, { once: true });
            }
            return originalOpen.apply(this, args);
          };
          const restore = () => { XMLHttpRequest.prototype.open = originalOpen; };
          submit.click();
          let attempts = 0;
          const check = () => {
            const message = form.querySelector('[data-om-form-message]');
            const ready = response
              && message?.textContent.includes('cannot delete superuser')
              && !message.hidden;
            if (ready) {
              restore();
              if (response.method !== 'POST' || response.status !== 200) {
                failures.push(`superuser delete response is ${response.method} ${response.status}`);
              }
              if (response.payload?.error_code !== 1100 || Object.keys(response.payload?.errors || {}).length !== 0) {
                failures.push('superuser delete response did not use a message-only business error');
              }
              if (!response.payload?.message?.includes?.('cannot delete superuser')) failures.push('superuser delete response message is missing');
              if (modal.hidden || modal.dataset.omState !== 'open') failures.push('superuser delete business error closed Modal Form');
              if (form.dataset.omStatus !== 'error') failures.push(`superuser delete Form status is ${form.dataset.omStatus || 'missing'}`);
              if (location.href !== startLocation) failures.push(`superuser delete business error navigated to ${location.href}`);
              modal.querySelector('[data-om-modal-close]')?.click();
              resolve({
                failures,
                expectedResponses: []
              });
              return;
            }
            if (attempts++ > 240) {
              restore();
              failures.push(`superuser delete business message timed out (status=${response?.status ?? 'missing'})`);
              resolve({
                failures,
                expectedResponses: []
              });
              return;
            }
            setTimeout(check, 50);
          };
          check();
        })
        """
    )


def _list_state_script(*, expected_rows: int) -> str:
    return f"""
    new Promise((resolve) => {{
      let attempts = 0;
      const check = () => {{
        const rows = document.querySelectorAll('[data-om-table-row]');
        const summary = document.querySelector('[data-om-table-summary]')?.textContent.replace(/\\s+/g, ' ').trim() || '';
        if ((rows.length === {expected_rows} && summary === 'Showing 1 to 20 of 25 entries') || attempts++ > 160) {{
          const failures = [];
          const icons = Array.from(document.querySelectorAll('#navbar-nav .oldman-menu-icon'));
          if (document.documentElement.dataset.omReady !== 'true') failures.push('Admin runtime is not ready');
          if (rows.length !== {expected_rows}) failures.push(`expected {expected_rows} rows, got ${{rows.length}}`);
          if (summary !== 'Showing 1 to 20 of 25 entries') failures.push(`unexpected summary: ${{summary}}`);
          if (!document.querySelector('[data-om-component="table"]')) failures.push('shared Table component is missing');
          if (!document.querySelector('.om-page-header .om-page-title')) failures.push('shared page header is missing');
          if (!document.querySelector('.om-card-header .om-card-title')) failures.push('shared card header is missing');
          if (!document.querySelector('[data-om-table-page-size-control] option[value="10"]')) failures.push('page-size options are missing');
          if (!document.querySelector('[data-om-table-pagination] .om-page-button')) failures.push('shared pagination is missing');
          if (!document.querySelector('#navbar-nav .oldman-menu-link.active')) failures.push('active navigation state is missing');
          if (!icons.length) failures.push('App menu icons are missing');
          for (const icon of icons) {{
            const iconStyle = getComputedStyle(icon, '::before');
            if (!(iconStyle.webkitMaskImage || iconStyle.maskImage || '').includes('data:image/svg+xml')) {{
              failures.push(`App menu icon mask is missing: ${{icon.className}}`);
            }}
          }}
          if (document.documentElement.scrollWidth > document.documentElement.clientWidth) failures.push('desktop document overflows horizontally');
          resolve({{ failures }});
          return;
        }}
        setTimeout(check, 50);
      }};
      check();
    }})
    """


def _table_interactions_script() -> str:
    return r"""
    (async () => {
      const failures = [];
      const waitFor = async (predicate, label) => {
        for (let attempt = 0; attempt < 180; attempt += 1) {
          if (predicate()) return true;
          await new Promise((resolve) => setTimeout(resolve, 50));
        }
        failures.push(`timed out waiting for ${label}`);
        return false;
      };
      const summary = () => document.querySelector('[data-om-table-summary]')?.textContent.replace(/\s+/g, ' ').trim() || '';
      const rows = () => Array.from(document.querySelectorAll('[data-om-table-row]'));
      const firstName = () => rows()[0]?.querySelector('[data-om-column="name"]')?.textContent.trim() || '';
      const filter = document.querySelector('[data-om-table-filter]');
      if (!filter) return { failures: ['search control is missing'] };

      filter.value = 'Integration Sample 22';
      filter.dispatchEvent(new Event('input', { bubbles: true }));
      await waitFor(() => summary() === 'Showing 1 to 1 of 1 entries' && rows().length === 1, 'search result');
      if (firstName() !== 'Integration Sample 22') failures.push(`search returned ${firstName() || 'no row'}`);

      filter.value = '';
      filter.dispatchEvent(new Event('input', { bubbles: true }));
      await waitFor(() => summary() === 'Showing 1 to 20 of 25 entries' && rows().length === 20, 'cleared search');

      document.querySelector('[data-om-table-sort="name"]')?.click();
      await waitFor(
        () => document.querySelector('[data-om-table-sort="name"]')?.getAttribute('aria-sort') === 'ascending' && firstName() === 'Admin Experience',
        'ascending name sort'
      );
      document.querySelector('[data-om-table-sort="name"]')?.click();
      await waitFor(
        () => document.querySelector('[data-om-table-sort="name"]')?.getAttribute('aria-sort') === 'descending' && firstName() === 'Integration Sample 22',
        'descending name sort'
      );

      const pageSize = document.querySelector('[data-om-table-page-size-control]');
      if (!pageSize) {
        failures.push('page-size control is missing');
      } else {
        pageSize.value = '10';
        pageSize.dispatchEvent(new Event('change', { bubbles: true }));
        await waitFor(() => summary() === 'Showing 1 to 10 of 25 entries' && rows().length === 10, '10-row page size');
      }

      document.querySelector('[data-om-table-page="2"]')?.click();
      await waitFor(() => summary() === 'Showing 11 to 20 of 25 entries' && rows().length === 10, 'second page');
      if (document.querySelector('[data-om-table-page="2"]')?.getAttribute('aria-current') !== 'page') {
        failures.push('page 2 does not expose aria-current=page');
      }
      return { failures, summary: summary(), firstName: firstName() };
    })()
    """


def _theme_interaction_script() -> str:
    return r"""
    (async () => {
      const failures = [];
      const html = document.documentElement;
      const toggle = document.querySelector('.light-dark-mode');
      const card = document.querySelector('.om-card');
      if (!toggle || !card) return { failures: ['theme toggle or card is missing'] };
      html.setAttribute('data-theme', 'light');
      const lightBody = getComputedStyle(document.body).backgroundColor;
      const lightCard = getComputedStyle(card).backgroundColor;
      toggle.click();
      await new Promise((resolve) => setTimeout(resolve, 100));
      const darkBody = getComputedStyle(document.body).backgroundColor;
      const darkCard = getComputedStyle(card).backgroundColor;
      if (html.getAttribute('data-theme') !== 'dark') failures.push('toggle did not enter dark theme');
      if (lightBody === darkBody) failures.push('body color did not change in dark theme');
      if (lightCard === darkCard) failures.push('card color did not change in dark theme');
      toggle.click();
      await new Promise((resolve) => setTimeout(resolve, 100));
      if (html.getAttribute('data-theme') !== 'light') failures.push('toggle did not restore light theme');
      return { failures, lightBody, darkBody, lightCard, darkCard };
    })()
    """


def _desktop_sidebar_script() -> str:
    return r"""
    (async () => {
      const failures = [];
      const html = document.documentElement;
      const sidebar = document.querySelector('.oldman-sidebar');
      const content = document.querySelector('.oldman-page-content');
      const toggle = document.querySelector('[data-om-sidebar-toggle]');
      if (!sidebar || !content || !toggle) return { failures: ['desktop shell controls are missing'] };
      html.setAttribute('data-sidebar-size', 'lg');
      const expandedWidth = sidebar.getBoundingClientRect().width;
      const expandedMargin = parseFloat(getComputedStyle(content).marginLeft);
      toggle.click();
      await new Promise((resolve) => setTimeout(resolve, 400));
      const collapsedWidth = sidebar.getBoundingClientRect().width;
      const collapsedMargin = parseFloat(getComputedStyle(content).marginLeft);
      if (html.getAttribute('data-sidebar-size') !== 'sm') failures.push('toggle did not set compact sidebar state');
      if (collapsedWidth >= expandedWidth - 80) failures.push(`sidebar width did not collapse: ${expandedWidth} to ${collapsedWidth}`);
      if (collapsedMargin >= expandedMargin - 80) failures.push(`content margin did not follow sidebar: ${expandedMargin} to ${collapsedMargin}`);
      toggle.click();
      await new Promise((resolve) => setTimeout(resolve, 400));
      if (html.getAttribute('data-sidebar-size') !== 'lg') failures.push('toggle did not restore expanded sidebar');
      return { failures, expandedWidth, collapsedWidth, expandedMargin, collapsedMargin };
    })()
    """


def _form_state_script() -> str:
    return r"""
    (() => {
      const failures = [];
      if (!document.querySelector('.om-page-header .om-page-title')) failures.push('edit page does not use shared page header');
      if (!document.querySelector('.om-form-grid')) failures.push('edit page does not use shared ModelForm renderer');
      const form = document.querySelector('form[data-om-component="form"][data-om-form]');
      if (!form || form.dataset.omFormMode !== 'json') failures.push('edit form JSON protocol is missing');
      if (!document.querySelector('form[data-om-form] input[name="csrfmiddlewaretoken"]')) failures.push('edit form CSRF token is missing');
      if (document.querySelector('[name="created_at"]')) failures.push('readonly created_at leaked into editable form');
      if (!document.querySelector('.om-form-actions .om-button-primary')) failures.push('shared form actions are missing');
      return { failures };
    })()
    """


def _csrf_rejection_script() -> str:
    return r"""
    (async () => {
      const response = await fetch('/admin/admin_demo_project/new', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'name=Must+Not+Be+Created&owner=Gate&status=active'
      });
      const failures = [];
      if (response.status !== 403) failures.push(`POST without CSRF returned ${response.status}, expected 403`);
      return { failures, status: response.status };
    })()
    """


def _mobile_state_script() -> str:
    return r"""
    new Promise((resolve) => {
      let attempts = 0;
      const check = () => {
        const rows = document.querySelectorAll('[data-om-table-row]');
        const summary = document.querySelector('[data-om-table-summary]')?.textContent.replace(/\s+/g, ' ').trim() || '';
        if ((rows.length === 20 && summary === 'Showing 1 to 20 of 25 entries') || attempts++ > 160) {
          const failures = [];
          const tableScroll = document.querySelector('.om-table-scroll');
          const sidebar = document.querySelector('.oldman-sidebar');
          const dataColumns = ['id', 'name', 'owner', 'status', 'is_active', 'created_at', 'action'].filter((name) =>
            document.querySelector(`td[data-om-column="${name}"]`)
          );
          if (rows.length !== 20) failures.push(`expected 20 mobile rows, got ${rows.length}`);
          if (summary !== 'Showing 1 to 20 of 25 entries') failures.push(`unexpected mobile summary: ${summary}`);
          if (document.documentElement.scrollWidth > document.documentElement.clientWidth) failures.push('mobile document overflows horizontally');
          if (!tableScroll || tableScroll.scrollWidth <= tableScroll.clientWidth) failures.push('mobile table has no horizontal-scroll fallback');
          if (dataColumns.length !== 7) failures.push(`mobile table lost data columns: ${dataColumns.join(', ')}`);
          if (!sidebar || sidebar.getBoundingClientRect().right > 1) failures.push('mobile sidebar is not initially closed');
          resolve({ failures });
          return;
        }
        setTimeout(check, 50);
      };
      check();
    })
    """


def _mobile_sidebar_open_script() -> str:
    return r"""
    (async () => {
      const failures = [];
      const sidebar = document.querySelector('.oldman-sidebar');
      const toggle = document.querySelector('[data-om-sidebar-toggle]');
      const backdrop = document.querySelector('[data-om-sidebar-backdrop]');
      if (!sidebar || !toggle || !backdrop) return { failures: ['mobile shell controls are missing'] };
      toggle.click();
      await new Promise((resolve) => setTimeout(resolve, 400));
      if (document.documentElement.dataset.omSidebarOpen !== 'true') failures.push('open state is missing');
      if (!document.body.classList.contains('vertical-sidebar-enable')) failures.push('body open state is missing');
      if (sidebar.getBoundingClientRect().right < innerWidth * 0.5) failures.push('sidebar did not enter the viewport');
      if (backdrop.hidden || backdrop.classList.contains('hidden')) failures.push('backdrop did not become visible');
      return { failures };
    })()
    """


def _mobile_sidebar_preserved_script() -> str:
    return r"""
    (async () => {
      await new Promise((resolve) => setTimeout(resolve, 400));
      const failures = [];
      const sidebar = document.querySelector('.oldman-sidebar');
      const backdrop = document.querySelector('[data-om-sidebar-backdrop]');
      if (document.documentElement.dataset.omSidebarOpen !== 'true') failures.push('Escape unexpectedly cleared open state');
      if (!document.body.classList.contains('vertical-sidebar-enable')) failures.push('Escape unexpectedly cleared body state');
      if (sidebar && sidebar.getBoundingClientRect().right < innerWidth * 0.5) failures.push('Escape unexpectedly moved sidebar out of viewport');
      if (backdrop && (backdrop.hidden || backdrop.classList.contains('hidden'))) failures.push('Escape unexpectedly hid backdrop');
      return { failures };
    })()
    """


def _mobile_sidebar_backdrop_script() -> str:
    return r"""
    (async () => {
      const failures = [];
      const backdrop = document.querySelector('[data-om-sidebar-backdrop]');
      if (!backdrop) return { failures: ['mobile backdrop is missing'] };
      backdrop.click();
      await new Promise((resolve) => setTimeout(resolve, 350));
      if (document.documentElement.dataset.omSidebarOpen === 'true') failures.push('backdrop did not clear open state');
      if (!backdrop.hidden || !backdrop.classList.contains('hidden')) failures.push('backdrop did not hide itself');
      return { failures };
    })()
    """


def _wait_for_filtered_project_script() -> str:
    return r"""
    new Promise((resolve) => {
      let attempts = 0;
      const check = () => {
        const summary = document.querySelector('[data-om-table-summary]')?.textContent.replace(/\s+/g, ' ').trim() || '';
        if (summary || attempts++ > 160) {
          const failures = [];
          const rows = Array.from(document.querySelectorAll('[data-om-table-row]'));
          const row = rows.find((item) => item.querySelector('[data-om-column="name"]')?.textContent.trim() === 'Browser Gate Project');
          if (rows.length > 1) failures.push(`filtered gate fixture returned ${rows.length} rows`);
          if (rows.length === 1 && !row) failures.push('filtered row is not the gate fixture');
          resolve({ failures, editUrl: row?.querySelector('[data-om-column="action"] a')?.href || null });
          return;
        }
        setTimeout(check, 50);
      };
      check();
    })
    """


def _wait_for_empty_filter_script() -> str:
    return r"""
    new Promise((resolve) => {
      let attempts = 0;
      const check = () => {
        const summary = document.querySelector('[data-om-table-summary]')?.textContent.replace(/\s+/g, ' ').trim() || '';
        if (summary === 'Showing 0 to 0 of 0 entries' || attempts++ > 160) {
          const failures = [];
          const rows = document.querySelectorAll('[data-om-table-row]').length;
          if (rows !== 0) failures.push(`deleted gate fixture still has ${rows} rows`);
          if (summary !== 'Showing 0 to 0 of 0 entries') failures.push(`unexpected empty summary: ${summary}`);
          resolve({ failures });
          return;
        }
        setTimeout(check, 50);
      };
      check();
    })
    """


if __name__ == "__main__":
    raise SystemExit(main())
