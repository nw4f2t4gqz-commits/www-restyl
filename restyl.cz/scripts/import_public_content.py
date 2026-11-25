#!/usr/bin/env python3
"""Fetch and sanitize Restyl's public, server-rendered pages for Drupal import."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
PAGES_FILE = CONTENT / "pages.json"
SITEMAP_URL = "https://www.restyl.cz/sitemap.xml"
ALLOWED_HOSTS = {"www.restyl.cz", "restyl.cz", "media.smtx.cz"}
MAX_HTML_BYTES = 5_000_000
MAX_IMAGE_BYTES = 20_000_000
IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
DROP_CONTENT_TAGS = {"script", "style", "noscript", "iframe", "object", "embed", "svg", "canvas", "template"}
ALLOWED_TAGS = {
    "a", "b", "blockquote", "br", "caption", "div", "em", "figcaption", "figure",
    "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "span",
    "strong", "table", "tbody", "td", "th", "tfoot", "thead", "tr", "u", "ul",
}
ALLOWED_CLASSES = {
    "vc_row", "vc_row-fluid", "vc_row-full-width", "wpb_row", "wpb_column",
    "vc_column_container", "vc_column-inner", "wpb_wrapper", "wpb_content_element",
    "wpb_single_image", "vc_single_image-wrapper", "vc_single_image-img",
    "icon-center", "icon-header", "icon-title", "text-uppercase", "btn", "button",
    "background-image-left", "clients", "rev_slider_wrapper", "rev_slider",
    "fullwidthabanner", "fullwidthbanner-container", "rev-slidebg",
    "rs-background-video-layer", "tp-caption", "rev-btn", "row", "owl-carousel",
    "owl-stage-outer", "owl-stage", "owl-item", "restyl-form-link", "jumbotron",
} | {f"{prefix}-{number}" for prefix in ("vc_col-md", "col-md") for number in range(1, 13)}


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise urllib.error.HTTPError(newurl, code, "Redirect outside allowed public source hosts", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SafeRedirectHandler)


def fetch(url: str, limit: int) -> tuple[bytes, str, str]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise ValueError(f"Refusing non-public or unapproved URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "Restyl-public-content-import/1.0"})
    with OPENER.open(request, timeout=25) as response:
        final = urllib.parse.urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname not in ALLOWED_HOSTS:
            raise ValueError(f"Refusing redirect to unapproved host: {response.geturl()}")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"Response exceeds {limit} byte safety limit: {url}")
        return data, response.headers.get_content_type(), response.geturl()


class Node:
    def __init__(self, tag: str, attrs: list[tuple[str, str | None]] | None = None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children: list[Node | str] = []


class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag.lower(), attrs)
        self.stack[-1].children.append(node)
        if tag.lower() not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag.lower(), attrs))

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def descendants(node: Node, tag: str):
    for child in node.children:
        if isinstance(child, Node):
            if child.tag == tag:
                yield child
            yield from descendants(child, tag)


def text_content(node: Node) -> str:
    pieces: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            pieces.append(child)
        else:
            pieces.append(text_content(child))
    return re.sub(r"\s+", " ", " ".join(pieces)).strip()


def class_has(node: Node, classname: str) -> bool:
    return classname in (node.attrs.get("class") or "").split()


def find_main(parser: TreeParser) -> Node:
    return next(descendants(parser.root, "main"), parser.root)


def find_content(main: Node) -> Node:
    return next((node for node in descendants(main, "div") if class_has(node, "content-container")), main)


def canonical_source_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.hostname not in {"www.restyl.cz", "restyl.cz"} or parsed.scheme != "https":
        raise ValueError(f"Unexpected page URL: {url}")
    path = parsed.path or "/"
    if not path.endswith("/"):
        path += "/"
    return urllib.parse.urlunsplit(("https", "www.restyl.cz", path, "", ""))


def internal_url(url: str, page_url: str) -> str:
    resolved = urllib.parse.urljoin(page_url, url)
    parsed = urllib.parse.urlsplit(resolved)
    if parsed.scheme in {"mailto", "tel"} and not any(char in url for char in "\r\n"):
        return urllib.parse.urlunsplit((parsed.scheme, "", parsed.path, parsed.query, parsed.fragment))
    if parsed.hostname in {"www.restyl.cz", "restyl.cz"}:
        path = parsed.path or "/"
        if not path.startswith("/"):
            path = "/" + path
        return urllib.parse.urlunsplit(("", "", path, parsed.query, parsed.fragment))
    if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password:
        return urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    if not parsed.scheme and not parsed.netloc:
        return urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, parsed.fragment))
    return ""


def asset_name(url: str, data: bytes, content_type: str) -> str:
    extension = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        extension = ".pdf" if content_type == "application/pdf" else mimetypes.guess_extension(content_type) or ""
    if extension not in MEDIA_EXTENSIONS:
        raise ValueError(f"Unsupported media type: {content_type}")
    key = hashlib.sha256(data).hexdigest()[:20]
    return f"{key}{extension}"


class PageSanitizer:
    def __init__(self, page_url: str, assets_dir: Path, assets: dict[str, dict], warnings: list[str]):
        self.page_url = page_url
        self.assets_dir = assets_dir
        self.assets = assets
        self.warnings = warnings

    def download_asset(self, raw_url: str, expected_kind: str) -> str | None:
        resolved = urllib.parse.urljoin(self.page_url, raw_url.strip())
        parsed = urllib.parse.urlsplit(resolved)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            self.warnings.append(f"Skipped media outside allowed source hosts: {resolved}")
            return None
        try:
            data, content_type, final_url = fetch(resolved, MAX_IMAGE_BYTES)
            is_image = content_type.startswith("image/") and content_type != "image/svg+xml"
            is_pdf = content_type == "application/pdf"
            accepted = is_image if expected_kind == "image" else is_pdf if expected_kind == "pdf" else is_image or is_pdf
            if not accepted:
                self.warnings.append(f"Skipped unsupported media type {content_type}: {resolved}")
                return None
            name = asset_name(final_url, data, content_type)
            self.assets_dir.mkdir(parents=True, exist_ok=True)
            target = self.assets_dir / name
            if not target.exists():
                with target.open("xb") as file:
                    file.write(data)
            elif hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(data).digest():
                raise ValueError(f"Asset name collision for {name}")
            self.assets.setdefault(name, {
                "file": f"assets/{name}",
                "sha256": hashlib.sha256(data).hexdigest(),
                "source_host": urllib.parse.urlsplit(final_url).hostname,
                "source_url": final_url,
            })
            return f"restyl-asset:{name}"
        except (OSError, ValueError, urllib.error.URLError) as error:
            self.warnings.append(f"Could not localize media {resolved}: {error}")
            return None

    def safe_href(self, raw_url: str) -> str:
        if not raw_url:
            return ""
        resolved = urllib.parse.urljoin(self.page_url, raw_url)
        media_path = Path(urllib.parse.urlsplit(resolved).path)
        media_host = urllib.parse.urlsplit(resolved).hostname
        if media_path.suffix.lower() in MEDIA_EXTENSIONS or media_host == "media.smtx.cz":
            expected_kind = "pdf" if media_path.suffix.lower() == ".pdf" else "image" if media_path.suffix.lower() in IMAGE_EXTENSIONS else "media"
            localized = self.download_asset(raw_url, expected_kind)
            if localized:
                return localized
        return internal_url(raw_url, self.page_url)

    def render(self, node: Node, form_url: str) -> str:
        output: list[str] = []
        for child in node.children:
            if isinstance(child, str):
                output.append(html.escape(child, quote=False))
                continue
            tag = child.tag
            if tag in DROP_CONTENT_TAGS:
                continue
            counter = child.attrs.get("data-to") or ""
            if tag == "span" and class_has(child, "counter-number") and counter.isascii() and counter.isdigit() and len(counter) <= 12:
                output.append(f"<span>{counter}</span>")
                continue
            if (
                tag == "div"
                and urllib.parse.urlsplit(self.page_url).path == "/"
                and class_has(child, "tp-caption")
                and class_has(child, "rev-btn")
                and text_content(child) == "KONTAKT"
            ):
                output.append('<a class="tp-caption rev-btn" href="/kontakt/">KONTAKT</a>')
                continue
            if tag == "form":
                is_search = (
                    (child.attrs.get("role") or "").lower() == "search"
                    or (child.attrs.get("id") or "").lower() == "searchform"
                    or class_has(child, "searchform")
                )
                if class_has(child, "wpcf7-form") and not is_search:
                    label = "ENERGY" if form_url.endswith("energy") else "ELEKTRO"
                    output.append(f'<p class="restyl-form-link">Formulář: <a href="{form_url}">Pokračovat na formulář {label}</a></p>')
                else:
                    kind = "search" if is_search else "unrecognized"
                    self.warnings.append(f"Skipped {kind} form on {self.page_url}")
                continue
            if tag == "img":
                raw_src = child.attrs.get("src") or child.attrs.get("data-src") or ""
                if not raw_src and child.attrs.get("srcset"):
                    raw_src = child.attrs["srcset"].split(",")[0].strip().split(" ")[0]
                src = self.download_asset(raw_src, "image") if raw_src else None
                if not src:
                    continue
                attrs = [("src", src)]
                classes = [item for item in (child.attrs.get("class") or "").split() if item in ALLOWED_CLASSES]
                if classes:
                    attrs.append(("class", " ".join(dict.fromkeys(classes))))
                for name in ("alt", "title"):
                    if child.attrs.get(name) is not None:
                        attrs.append((name, child.attrs[name]))
                for name in ("width", "height"):
                    value = child.attrs.get(name, "")
                    if value.isdigit() and int(value) <= 10000:
                        attrs.append((name, value))
                output.append("<img" + "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in attrs) + ">")
                continue
            if tag == "aside" and class_has(child, "col-md-3"):
                tag = "div"
            if tag not in ALLOWED_TAGS:
                output.append(self.render(child, form_url))
                continue
            attrs: list[tuple[str, str]] = []
            classes = [
                item for item in (child.attrs.get("class") or "").split()
                if item in ALLOWED_CLASSES and (item != "jumbotron" or tag == "div")
            ]
            if classes:
                attrs.append(("class", " ".join(dict.fromkeys(classes))))
            if tag == "a":
                href = self.safe_href(child.attrs.get("href", ""))
                if href:
                    attrs.append(("href", href))
                if child.attrs.get("title"):
                    attrs.append(("title", child.attrs["title"]))
            elif tag in {"td", "th"}:
                for name in ("colspan", "rowspan"):
                    value = child.attrs.get(name, "")
                    if value.isdigit() and 1 <= int(value) <= 100:
                        attrs.append((name, value))
            rendered_attrs = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in attrs)
            if tag in VOID_TAGS:
                output.append(f"<{tag}{rendered_attrs}>")
            else:
                output.append(f"<{tag}{rendered_attrs}>")
                output.append(self.render(child, form_url))
                output.append(f"</{tag}>")
        return "".join(output)


def parse_page(url: str, lastmod: str, assets: dict, assets_dir: Path) -> tuple[dict, list[str], set[str]]:
    data, content_type, final_url = fetch(url, MAX_HTML_BYTES)
    if content_type not in {"text/html", "application/xhtml+xml"}:
        raise ValueError(f"Expected HTML at {url}, got {content_type}")
    text = data.decode("utf-8", "replace")
    parser = TreeParser()
    parser.feed(text)
    main = find_main(parser)
    content = find_content(main)
    title = next((text_content(node) for node in descendants(main, "h1") if class_has(node, "page-title")), "")
    if not title:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
        title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else urllib.parse.urlsplit(url).path.strip("/") or "Restyl"
        title = re.sub(r"\s*[-|]\s*Restyl\.cz\s*$", "", title, flags=re.I)
    desc_match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', text, flags=re.I | re.S)
    description = html.unescape(desc_match.group(1)).strip() if desc_match else ""
    path = urllib.parse.urlsplit(final_url).path or "/"
    form_url = "/formular/energy" if path.lower().startswith("/energy/") else "/formular/elektro"
    warnings: list[str] = []
    page_sanitizer = PageSanitizer(url, assets_dir, assets, warnings)
    body = page_sanitizer.render(content, form_url)
    portfolio_links = set()
    for link in descendants(content, "a"):
        href = internal_url(link.attrs.get("href", ""), url)
        if href.startswith("/portfolio/"):
            portfolio_links.add(urllib.parse.urlsplit(href).path)
    page = {
        "title": title,
        "path": path if path.endswith("/") else path + "/",
        "body": body.strip(),
        "format": "restyl_html",
        "source_url": url,
        "source_lastmod": lastmod,
        "description": description,
    }
    return page, warnings, portfolio_links


def load_sitemap() -> list[tuple[str, str]]:
    data, _, _ = fetch(SITEMAP_URL, MAX_HTML_BYTES)
    root = ET.fromstring(data)
    entries = []
    for url_node in root.findall(".//{*}url"):
        loc = url_node.findtext("{*}loc")
        if loc:
            entries.append((canonical_source_url(loc.strip()), (url_node.findtext("{*}lastmod") or "").strip()))
    if not entries:
        raise ValueError("Public sitemap contained no URLs")
    return entries


def collect(force: bool):
    if PAGES_FILE.exists() and not force:
        raise SystemExit(f"{PAGES_FILE.relative_to(ROOT)} already exists; use --force to refresh the public snapshot.")
    sitemap_pages = load_sitemap()
    sitemap_paths = {urllib.parse.urlsplit(url).path or "/" for url, _ in sitemap_pages}
    assets: dict[str, dict] = {}
    pages_by_path: dict[str, dict] = {}
    warnings: list[str] = []
    pending = list(sitemap_pages)
    discovered: set[str] = set()
    while pending:
        url, lastmod = pending.pop(0)
        path = urllib.parse.urlsplit(url).path or "/"
        if path in discovered:
            continue
        discovered.add(path)
        page, page_warnings, portfolio_links = parse_page(url, lastmod, assets, CONTENT / "assets")
        page["discovery"] = "sitemap" if path in sitemap_paths else "portfolio_reference"
        pages_by_path[page["path"]] = page
        warnings.extend(page_warnings)
        for link_path in sorted(portfolio_links):
            if link_path not in discovered:
                pending.append((canonical_source_url("https://www.restyl.cz" + link_path), ""))
    manifest = {
        "schema_version": 1,
        "source": "https://www.restyl.cz/",
        "sitemap_page_count": len(sitemap_paths),
        "linked_page_count": len(pages_by_path) - len(sitemap_paths),
        "pages": sorted(pages_by_path.values(), key=lambda page: page["path"]),
        "assets": assets,
        "warnings": sorted(set(warnings)),
    }
    CONTENT.mkdir(parents=True, exist_ok=True)
    temp = PAGES_FILE.with_suffix(".json.new")
    with temp.open("w", encoding="utf-8") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(temp, PAGES_FILE)
    print(
        f"Saved {len(manifest['pages'])} pages "
        f"({manifest['sitemap_page_count']} sitemap, {manifest['linked_page_count']} linked) "
        f"and {len(assets)} local media files to {PAGES_FILE.relative_to(ROOT)}"
    )
    if warnings:
        print(f"Warnings: {len(set(warnings))}; see manifest.warnings.", file=sys.stderr)


def validate():
    manifest = json.loads(PAGES_FILE.read_text(encoding="utf-8"))
    assert manifest.get("schema_version") == 1
    aliases = [page["path"] for page in manifest["pages"]]
    if len(aliases) != len(set(aliases)):
        raise ValueError("Duplicate Drupal paths in manifest")
    if sum(page.get("discovery") == "sitemap" for page in manifest["pages"]) != manifest.get("sitemap_page_count"):
        raise ValueError("Sitemap page count does not match the page manifest")
    if sum(page.get("discovery") == "portfolio_reference" for page in manifest["pages"]) != manifest.get("linked_page_count"):
        raise ValueError("Linked page count does not match the page manifest")
    for page in manifest["pages"]:
        if not page["title"] or not page["path"].startswith("/") or ".." in page["path"].split("/"):
            raise ValueError(f"Invalid page metadata: {page.get('path')}")
        if re.search(r"<\s*(script|style|iframe|form|input|button)\b|\son[a-z]+\s*=|javascript:", page["body"], re.I):
            raise ValueError(f"Unsafe markup in {page['path']}")
        for name, metadata in manifest["assets"].items():
            path = ROOT / "content" / metadata["file"]
            if Path(name).name != name or not path.is_file():
                raise ValueError(f"Missing/invalid media file: {name}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != metadata["sha256"]:
                raise ValueError(f"Media checksum mismatch: {name}")
    print(f"Validated {len(aliases)} pages and {len(manifest['assets'])} local media files.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Fetch and sanitize the public pages and media.")
    parser.add_argument("--force", action="store_true", help="Explicitly replace content/pages.json when fetching.")
    parser.add_argument("--check", action="store_true", help="Validate the local snapshot without network access.")
    args = parser.parse_args()
    if args.check:
        validate()
    elif args.fetch:
        collect(args.force)
        validate()
    else:
        parser.error("Choose --fetch or --check.")


if __name__ == "__main__":
    main()
