"""Read-only public web observation. Remote content never becomes an executable instruction."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

import httpx


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use um URL público http(s) sem credenciais.")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("Apenas portas Web públicas 80 e 443.")
    for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(item[4][0]).is_global:
            raise PermissionError(
                "Endereços privados, locais e reservados não são permitidos nesta ferramenta."
            )
    return url


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.links = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def read_page(url):
    public_url(url)
    with httpx.Client(
        timeout=12, follow_redirects=False, headers={"User-Agent": "JarvisPT/0.1 (read-only)"}
    ) as client:
        for _ in range(5):
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = public_url(urljoin(url, response.headers["location"]))
                    continue
                response.raise_for_status()
                if not any(
                    t in response.headers.get("content-type", "") for t in ("text/html", "text/plain")
                ):
                    raise ValueError("Este leitor aceita apenas texto e HTML.")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 2_000_000:
                        raise ValueError("Página excede o limite de 2 MB.")
                text = data.decode(response.encoding or "utf-8", errors="replace")
                parser = TextParser()
                parser.feed(text)
                title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
                return {
                    "source": url,
                    "title": unescape(title[1]).strip() if title else url,
                    "text": "\n".join(parser.parts)[:30000],
                    "links": [urljoin(url, v) for v in parser.links[:80]],
                    "trusted": False,
                    "evidence": "HTML recebido por HTTP; sem observação do servidor.",
                }
    raise RuntimeError("Demasiados redirecionamentos.")


def search_web(query):
    result = read_page("https://html.duckduckgo.com/html/?q=" + quote(query))
    return {
        "query": query,
        "source": result["source"],
        "text": result["text"],
        "links": result["links"],
        "trusted": False,
    }


async def inspect_site(url, executable_path=None):
    await asyncio.to_thread(public_url, url)
    from playwright.async_api import async_playwright

    assets = []
    banners = []
    cached = set()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, executable_path=executable_path)
        context = None
        try:
            context = await browser.new_context(service_workers="block", accept_downloads=False)

            async def route(request_route):
                target = request_route.request.url
                parsed = urlparse(target)
                try:
                    if parsed.scheme not in {"http", "https"} or parsed.port not in {None, 80, 443}:
                        raise PermissionError("Recurso fora do âmbito Web público.")
                    if parsed.hostname not in cached:
                        await asyncio.to_thread(public_url, target)
                        cached.add(parsed.hostname)
                    if len(assets) > 500:
                        await request_route.abort()
                    else:
                        await request_route.continue_()
                except Exception:
                    await request_route.abort()

            await context.route("**/*", route)
            page = await context.new_page()
            page.on(
                "response",
                lambda response: assets.append(
                    {
                        "source": "Playwright network listener",
                        "url": response.url,
                        "status": response.status,
                        "content_type": response.headers.get("content-type"),
                        "declared_bytes": response.headers.get("content-length"),
                        "size_kind": "header; may be absent or compressed",
                    }
                ),
            )
            # Listener is registered before navigation, in a new non-persistent profile.
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            for _ in range(4):
                await page.mouse.wheel(0, 600)
                await page.wait_for_timeout(250)
            facts = await page.evaluate(
                "() => ({title:document.title, scripts:[...document.scripts].map(s=>s.src).filter(Boolean), text:document.body.innerText.slice(0,16000)})"
            )
            # Only observable client assets; do not claim server technology from a URL name.
            for script in facts["scripts"][:8]:
                if urlparse(script).netloc != urlparse(url).netloc:
                    continue
                response = await context.request.get(script, timeout=8000, max_redirects=0)
                if response.ok:
                    body = await response.body()
                    if len(body) < 2_000_000:
                        for pattern in (
                            r"Three\.js[^\n]{0,100}",
                            r"GSAP\s+\d+\.\d+\.\d+",
                            r"@license[^\n]{0,120}",
                        ):
                            for match in re.findall(pattern, body.decode(errors="replace"))[:4]:
                                banners.append(
                                    {
                                        "source": script,
                                        "observation": match,
                                        "kind": "literal banner, not proof of active use",
                                    }
                                )
            return {
                "source": url,
                "collector": "Playwright (REA not used)",
                "facts": facts,
                "assets": assets[:500],
                "banners": banners,
                "trusted": False,
                "limits": "Só código e tráfego recebidos pelo browser. Cabeçalhos de tamanho não medem o total transferido; lógica do servidor não observável.",
            }
        finally:
            if context:
                await context.close()
            await browser.close()
