#!/usr/bin/env python3
"""
Google Maps Scraper - Extrai estabelecimentos sem usar a API oficial
Uso: python3 google_maps_scraper.py "restaurantes" --location "São Paulo, SP" --max-results 20
"""

import argparse
import csv
import json
import logging
import os
import random
import re
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from selenium import webdriver
from selenium.common.exceptions import (
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys  # mantido para compatibilidade futura
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    from webdriver_manager.chrome import ChromeDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Establishment:
    name: str = ""
    address: str = ""
    rating: str = ""
    reviews_count: str = ""
    phone: str = ""
    website: str = ""
    category: str = ""
    hours: str = ""
    maps_url: str = ""


# ---------------------------------------------------------------------------
# Driver helpers
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]


def build_driver(headless: bool = True) -> webdriver.Chrome:
    """Build and return a configured Chrome WebDriver."""
    options = Options()
    ua = random.choice(USER_AGENTS)
    options.add_argument(f"--user-agent={ua}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1400,900")
    options.add_argument("--lang=pt-BR")

    if headless:
        options.add_argument("--headless=new")

    if WEBDRIVER_MANAGER_AVAILABLE:
        logger.info("Usando webdriver-manager para ChromeDriver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    else:
        logger.info("webdriver-manager não disponível; usando Selenium Manager...")
        driver = webdriver.Chrome(options=options)

    # Remove o flag navigator.webdriver
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


# ---------------------------------------------------------------------------
# Scroll helpers
# ---------------------------------------------------------------------------
def random_sleep(min_s: float = 0.8, max_s: float = 2.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


def scroll_results_panel(driver: webdriver.Chrome, panel, times: int = 3) -> None:
    """Scroll inside the results panel to load more entries."""
    for _ in range(times):
        try:
            driver.execute_script("arguments[0].scrollTop += 800;", panel)
            random_sleep(1.0, 2.0)
        except Exception as exc:
            logger.debug("Scroll error (ignorado): %s", exc)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------
DETAIL_SELECTORS = {
    "address": [
        "[data-item-id='address'] .fontBodyMedium",
        "button[data-item-id='address']",
        ".rogA2c .fontBodyMedium",
    ],
    "phone": [
        "[data-item-id^='phone:tel'] .fontBodyMedium",
        "button[data-item-id^='phone'] .fontBodyMedium",
    ],
    "website": [
        "a[data-item-id='authority']",
        "a[href][data-tooltip='Abrir o site']",
        "a[aria-label^='Site:']",
    ],
    "hours": [
        ".t39EBf .fontBodyMedium",
        "[data-hide-tooltip-on-mouse-move] .fontBodyMedium",
        ".MkV9ic span",
    ],
    "category": [
        ".DkEaL",
        ".fontBodyMedium.dmRWX",
        ".mgr77e .fontBodyMedium",
    ],
}


def safe_text(driver: webdriver.Chrome, selectors: List[str]) -> str:
    """Try multiple CSS selectors and return the first match's text."""
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            txt = el.get_attribute("textContent") or el.text
            if txt and txt.strip():
                return txt.strip()
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    return ""


def safe_attr(driver: webdriver.Chrome, selectors: List[str], attr: str) -> str:
    for sel in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            val = el.get_attribute(attr)
            if val and val.strip():
                return val.strip()
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    return ""


def extract_rating(driver: webdriver.Chrome) -> tuple:
    """Return (rating_str, reviews_count_str)."""
    selectors_rating = [
        "div.fontDisplayLarge",
        "span.ceNzKf",
        ".MW4etd",
    ]
    selectors_count = [
        "span.UY7F9",
        "span[aria-label*='avaliações']",
        "span[aria-label*='reviews']",
        ".F7nice span:last-child",
    ]
    rating = safe_text(driver, selectors_rating)
    count = safe_text(driver, selectors_count)
    # Limpa parênteses do count
    count = re.sub(r"[()]", "", count).strip()
    return rating, count


def extract_detail_page(driver: webdriver.Chrome, url: str) -> Establishment:
    """Open the detail page and extract all fields."""
    est = Establishment(maps_url=url)
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1")))
        random_sleep(1.5, 3.0)

        # Nome
        try:
            est.name = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
        except NoSuchElementException:
            pass

        # Rating
        est.rating, est.reviews_count = extract_rating(driver)

        # Campos de texto
        est.address = safe_text(driver, DETAIL_SELECTORS["address"])
        est.phone = safe_text(driver, DETAIL_SELECTORS["phone"])
        est.category = safe_text(driver, DETAIL_SELECTORS["category"])
        est.hours = safe_text(driver, DETAIL_SELECTORS["hours"])

        # Website (atributo href)
        est.website = safe_attr(driver, DETAIL_SELECTORS["website"], "href")
        if est.website:
            # Remove parâmetros de rastreamento do Google
            est.website = re.sub(r"/url\?.*?(?:url=|q=)(https?://[^&]+).*", r"\1", est.website)

    except TimeoutException:
        logger.warning("Timeout ao carregar detalhe: %s", url)
    except Exception as exc:
        logger.warning("Erro ao extrair detalhe (%s): %s", url, exc)

    return est


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------
def scrape_google_maps(
    query: str,
    location: Optional[str] = None,
    max_results: int = 20,
    headless: bool = True,
    scroll_rounds: int = 5,
) -> List[Establishment]:
    search_term = f"{query} {location}" if location else query
    logger.info("Buscando: '%s' (máx. %d resultados)", search_term, max_results)

    driver = build_driver(headless=headless)
    establishments: List[Establishment] = []
    detail_urls: List[str] = []

    try:
        # ------------------------------------------------------------------ #
        # 1. Abre Google Maps com a busca diretamente na URL
        # ------------------------------------------------------------------ #
        encoded = urllib.parse.quote_plus(search_term)
        maps_url = f"https://www.google.com/maps/search/{encoded}/"
        logger.info("Abrindo URL: %s", maps_url)
        driver.get(maps_url)
        random_sleep(3.0, 5.0)

        wait = WebDriverWait(driver, 30)

        # Aceita cookies / aviso de consentimento (se aparecer)
        for consent_sel in [
            "button[aria-label='Aceitar tudo']",
            "button[aria-label='Accept all']",
            "button[jsname='V67aGc']",
            "form:last-child button",
        ]:
            try:
                btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, consent_sel))
                )
                btn.click()
                logger.info("Consentimento aceito via: %s", consent_sel)
                random_sleep(2.0, 3.0)
                break
            except (TimeoutException, ElementNotInteractableException):
                continue

        # Aguarda a página carregar verificando a URL atual
        random_sleep(2.0, 4.0)
        current_url = driver.current_url
        logger.info("URL atual após carregamento: %s", current_url[:100])

        # ------------------------------------------------------------------ #
        # 2. Aguarda painel de resultados
        # ------------------------------------------------------------------ #
        results_panel_selectors = [
            "div[role='feed']",
            "div.m6QErb[aria-label]",
            ".DxyBCb",
            "div.m6QErb",
        ]
        panel = None
        for sel in results_panel_selectors:
            try:
                panel = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                logger.info("Painel de resultados encontrado com selector: %s", sel)
                break
            except TimeoutException:
                continue

        if panel is None:
            logger.warning("Painel de resultados não encontrado.")
            logger.debug("Título da página: %s", driver.title)
            logger.debug("URL atual: %s", driver.current_url)
            # Tenta coletar links diretos sem painel
            logger.info("Tentando coletar links sem painel...")

        # ------------------------------------------------------------------ #
        # 3. Scroll para carregar mais resultados
        # ------------------------------------------------------------------ #
        collected_urls = set()

        for round_n in range(scroll_rounds):
            logger.info("Rodada de scroll %d/%d...", round_n + 1, scroll_rounds)

            # Coleta links dos resultados visíveis
            try:
                result_links = driver.find_elements(
                    By.CSS_SELECTOR,
                    "a.hfpxzc, a[href*='/maps/place/']",
                )
                for link in result_links:
                    href = link.get_attribute("href")
                    if href and "/maps/place/" in href and href not in collected_urls:
                        collected_urls.add(href)
                        if len(collected_urls) >= max_results:
                            break
            except StaleElementReferenceException:
                logger.debug("StaleElementReference durante coleta de links")

            if len(collected_urls) >= max_results:
                break

            # Scroll
            if panel:
                scroll_results_panel(driver, panel, times=2)
            else:
                driver.execute_script("window.scrollBy(0, 800);")
                random_sleep(1.5, 2.5)

        detail_urls = list(collected_urls)[:max_results]
        logger.info("%d URLs de detalhe coletadas.", len(detail_urls))

        # ------------------------------------------------------------------ #
        # 4. Extrai detalhes de cada estabelecimento
        # ------------------------------------------------------------------ #
        for idx, url in enumerate(detail_urls, 1):
            logger.info("[%d/%d] Extraindo: %s", idx, len(detail_urls), url[:80])
            est = extract_detail_page(driver, url)
            establishments.append(est)
            random_sleep(1.5, 3.5)

    except Exception as exc:
        logger.error("Erro fatal no scraper: %s", exc, exc_info=True)
    finally:
        driver.quit()

    return establishments


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def save_csv(data: List[Establishment], path: str) -> None:
    if not data:
        logger.warning("Nenhum dado para salvar em CSV.")
        return
    fieldnames = list(asdict(data[0]).keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for est in data:
            writer.writerow(asdict(est))
    logger.info("CSV salvo: %s", path)


def save_json(data: List[Establishment], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(e) for e in data], f, ensure_ascii=False, indent=2)
    logger.info("JSON salvo: %s", path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scraper de estabelecimentos no Google Maps (sem API oficial)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemplos:\n"
               "  python3 google_maps_scraper.py \"restaurantes\"\n"
               "  python3 google_maps_scraper.py \"farmácias\" --location \"Curitiba, PR\" --max-results 30\n"
               "  python3 google_maps_scraper.py \"hotéis\" --no-headless",
    )
    parser.add_argument("query", help="Termo de busca (ex: 'restaurantes', 'farmácias')")
    parser.add_argument(
        "--location", "-l", default="", help="Localização (ex: 'São Paulo, SP')"
    )
    parser.add_argument(
        "--max-results", "-n", type=int, default=20, help="Número máximo de resultados (padrão: 20)"
    )
    parser.add_argument(
        "--no-headless", action="store_true", help="Abre o navegador em modo visível (para debug)"
    )
    parser.add_argument(
        "--output", "-o", default="resultados", help="Prefixo do arquivo de saída (padrão: resultados)"
    )
    parser.add_argument(
        "--scroll-rounds", type=int, default=5, help="Rodadas de scroll para carregar mais resultados (padrão: 5)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    results = scrape_google_maps(
        query=args.query,
        location=args.location if args.location else None,
        max_results=args.max_results,
        headless=not args.no_headless,
        scroll_rounds=args.scroll_rounds,
    )

    if not results:
        logger.warning("Nenhum resultado extraído.")
        sys.exit(1)

    logger.info("%d estabelecimentos extraídos.", len(results))
    save_csv(results, f"{args.output}.csv")
    save_json(results, f"{args.output}.json")


if __name__ == "__main__":
    main()
