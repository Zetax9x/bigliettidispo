#!/usr/bin/env python3
"""Monitora disponibilità biglietti su TicketOne e notifica via Telegram."""
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional
import requests

EVENT_URL = (
    "https://sport.ticketone.it/seatmap/52806/90600526/"
    "ascoli-vs-union-brescia-play-off-serie-c-2025-2026"
)
STATE_FILE = Path("state.json")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
SEND_STATUS = os.environ.get("SEND_STATUS", "").lower() in ("1", "true", "yes")


def send_telegram(message: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        print(f"[TELEGRAM non configurato] {message}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=15,
    )
    resp.raise_for_status()
    print("Notifica Telegram inviata.")


def _parse_sector_item(item: dict) -> tuple[Optional[str], Optional[bool]]:
    """Estrae nome e disponibilità da un oggetto settore JSON."""
    if not isinstance(item, dict):
        return None, None

    name = (
        item.get("name")
        or item.get("nome")
        or item.get("label")
        or item.get("sectorName")
        or item.get("zoneName")
        or item.get("categoryName")
        or item.get("title")
        or str(item.get("id", ""))
    )
    if not name:
        return None, None

    avail_keys = ["available", "isAvailable", "disponibile", "enabled", "active"]
    sold_keys = ["soldOut", "sold_out", "isSoldOut", "esaurito", "unavailable", "disabled"]

    is_avail = any(item.get(k) for k in avail_keys)
    is_sold = any(item.get(k) for k in sold_keys)

    if not is_avail and not is_sold:
        status = str(item.get("status", item.get("stato", ""))).lower()
        is_avail = status in ("available", "on_sale", "onsale", "disponibile", "1", "active")
        is_sold = status in ("sold_out", "soldout", "esaurito", "unavailable", "0", "inactive")

    if not is_avail and not is_sold:
        qty = item.get("quantity", item.get("availableQuantity", item.get("qty")))
        if qty is not None:
            is_avail = int(qty) > 0
            is_sold = int(qty) == 0

    available = is_avail and not is_sold
    return str(name), available


def _sectors_from_json(data) -> dict[str, bool]:
    """Tenta di estrarre settori da una struttura JSON qualsiasi."""
    sectors: dict[str, bool] = {}

    candidates = None
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        for key in (
            "sectors", "zone", "zones", "settori", "categories",
            "areas", "items", "data", "result", "content", "list",
        ):
            if key in data and isinstance(data[key], list):
                candidates = data[key]
                break

    if candidates:
        for item in candidates:
            name, avail = _parse_sector_item(item)
            if name:
                sectors[name] = avail if avail is not None else False

    return sectors


def get_availability() -> Optional[dict[str, bool]]:
    """
    Usa Playwright per caricare la pagina TicketOne, intercetta le chiamate API
    e restituisce {nome_settore: disponibile}. None in caso di errore grave.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    captured: list[dict] = []
    dom_sectors: dict[str, bool] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="it-IT",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
            },
        )
        page = context.new_page()

        def on_response(response):
            url = response.url
            status = response.status
            if status != 200:
                return
            keywords = ("api", "catalog", "event", "sector", "zone", "availab", "seatmap", "ticket")
            if not any(k in url.lower() for k in keywords):
                return
            try:
                data = response.json()
                captured.append({"url": url, "data": data})
                if DEBUG:
                    print(f"  [API] {url}")
            except Exception:
                pass

        page.on("response", on_response)

        try:
            page.goto(EVENT_URL, wait_until="networkidle", timeout=40000)
            page.wait_for_timeout(3000)
        except PWTimeout:
            print("Timeout caricamento pagina, estraggo comunque dati disponibili.")

        # --- Parsing DOM come fallback ---
        try:
            selectors = [
                "[data-sector-name]", "[data-name]", "[data-sector]",
                ".sector", ".zone", ".area",
                "[class*='sector']", "[class*='zone']", "[class*='area']",
                "[data-available]", "[data-status]",
            ]
            for sel in selectors:
                elements = page.query_selector_all(sel)
                if not elements:
                    continue
                for el in elements:
                    name = (
                        el.get_attribute("data-sector-name")
                        or el.get_attribute("data-name")
                        or el.get_attribute("data-sector")
                        or el.get_attribute("title")
                        or ""
                    )
                    if not name:
                        txt = (el.inner_text() or "").strip()
                        name = txt[:60] if txt else ""
                    if not name or len(name) < 2:
                        continue
                    classes = el.get_attribute("class") or ""
                    avail_attr = (el.get_attribute("data-available") or "").lower()
                    status_attr = (el.get_attribute("data-status") or "").lower()
                    sold_out = (
                        "sold-out" in classes
                        or "soldout" in classes
                        or "esaurito" in classes
                        or "unavailable" in classes
                        or avail_attr in ("false", "0", "no")
                        or status_attr in ("soldout", "sold_out", "unavailable", "esaurito")
                    )
                    dom_sectors[name] = not sold_out
                if dom_sectors:
                    if DEBUG:
                        print(f"  [DOM] {len(dom_sectors)} settori con selettore '{sel}'")
                    break
        except Exception as exc:
            print(f"Errore parsing DOM: {exc}")

        # --- Cerca JSON inline negli script ---
        try:
            html = page.content()
            if DEBUG:
                Path("debug_page.html").write_text(html, encoding="utf-8")
                print("  [DEBUG] HTML salvato in debug_page.html")

            patterns = [
                r'"(?:sectors|zone|zones|settori|categories|areas)"\s*:\s*(\[.{5,10000}?\])',
                r'window\.__(?:INITIAL_STATE|STATE|DATA)__\s*=\s*(\{.{5,50000}?\});',
            ]
            for pat in patterns:
                for match in re.finditer(pat, html, re.DOTALL):
                    try:
                        data = json.loads(match.group(1))
                        captured.append({"url": "inline-script", "data": data})
                        if DEBUG:
                            print(f"  [INLINE] JSON trovato, {len(str(data))} char")
                    except Exception:
                        pass
        except Exception as exc:
            print(f"Errore lettura HTML: {exc}")

        browser.close()

    # --- Priorità: dati API intercettati > DOM ---
    sectors: dict[str, bool] = {}
    for item in captured:
        data = item["data"]
        parsed = _sectors_from_json(data)
        if parsed:
            if DEBUG:
                print(f"  [PARSED] {item['url']}: {parsed}")
            sectors.update(parsed)

    if sectors:
        return sectors

    if dom_sectors:
        return dom_sectors

    print("ATTENZIONE: nessun settore trovato. La struttura della pagina potrebbe essere cambiata.")
    print(f"  API intercettate: {len(captured)}")
    print(f"  DOM settori: {len(dom_sectors)}")
    if captured and DEBUG:
        for c in captured[:3]:
            print(f"  Sample: {c['url']} -> {str(c['data'])[:200]}")
    return None


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sectors": {}, "consecutive_failures": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def format_status_report(sectors: dict[str, bool]) -> str:
    """Formatta un riepilogo completo di tutti i settori."""
    available = sorted(n for n, a in sectors.items() if a)
    sold_out = sorted(n for n, a in sectors.items() if not a)

    lines = [
        "📊 <b>Stato settori — Ascoli vs Union Brescia</b>",
        "Play-off Serie C 2025/2026\n",
    ]

    if available:
        lines.append("✅ <b>Disponibili:</b>")
        lines.extend(f"  • {n}" for n in available)
    else:
        lines.append("✅ <b>Disponibili:</b> nessuno")

    lines.append("")

    if sold_out:
        lines.append("❌ <b>Esauriti:</b>")
        lines.extend(f"  • {n}" for n in sold_out)
    else:
        lines.append("❌ <b>Esauriti:</b> nessuno")

    lines.append(f'\n<a href="{EVENT_URL}">🔗 Pagina acquisto TicketOne</a>')
    return "\n".join(lines)


def main() -> None:
    print("=== Monitor biglietti TicketOne ===")
    print(f"URL: {EVENT_URL}")

    sectors = get_availability()

    state = load_state()

    if sectors is None:
        failures = state.get("consecutive_failures", 0) + 1
        state["consecutive_failures"] = failures
        save_state(state)
        print(f"Errore #{failures}: impossibile leggere disponibilità.")
        if failures == 5:
            send_telegram(
                "⚠️ <b>Monitor biglietti: errore</b>\n\n"
                "Non riesco a leggere la pagina TicketOne da 5 controlli consecutivi.\n"
                "Controlla manualmente o verifica i log di GitHub Actions."
            )
        return

    state["consecutive_failures"] = 0
    prev = state.get("sectors", {})
    is_first_run = not prev

    print(f"Settori rilevati ({len(sectors)}): {sectors}")

    newly_available = [
        name for name, avail in sectors.items()
        if avail and not prev.get(name, False)
    ]

    went_sold_out = [
        name for name, avail in sectors.items()
        if not avail and prev.get(name, False)
    ]

    # --- Notifica cambiamenti ---
    if newly_available:
        elenco = "\n".join(f"  • {s}" for s in newly_available)
        msg = (
            "🎟 <b>BIGLIETTI DISPONIBILI!</b>\n\n"
            "⚽ <b>Ascoli vs Union Brescia</b>\n"
            "Play-off Serie C 2025/2026\n\n"
            f"Settori tornati disponibili:\n{elenco}\n\n"
            + format_status_report(sectors)
        )
        send_telegram(msg)
    elif went_sold_out:
        elenco = "\n".join(f"  • {s}" for s in went_sold_out)
        msg = (
            "🔴 <b>Settori appena esauriti:</b>\n"
            f"{elenco}\n\n"
            + format_status_report(sectors)
        )
        send_telegram(msg)
    else:
        print("Nessun cambiamento di disponibilità.")

    # --- Riepilogo completo: al primo avvio o su richiesta esplicita ---
    if (is_first_run or SEND_STATUS) and not newly_available and not went_sold_out:
        send_telegram(format_status_report(sectors))

    state["sectors"] = sectors
    save_state(state)
    print("Stato aggiornato.")


if __name__ == "__main__":
    main()
