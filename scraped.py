#!/usr/bin/env python3
 
import os
import sys
from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse, urldefrag, unquote

try:
    import requests
    from bs4 import BeautifulSoup
    import xml.etree.ElementTree as ET
except ImportError as e:
    print(f"Missing dependency: {e.name}. Install with `pip install requests beautifulsoup4`", file=sys.stderr)
    sys.exit(1)

# Configuration
default_base = "https://vinted.se"  # override via command-line
output_root = "site_clone"

# HTTP headers
headers = {"User-Agent": "Mozilla/5.0 (compatible; SiteCrawler/1.1)"}

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def normalize_url(url):
    """Strip fragments, drop trailing slash duplicates."""
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    # unify path: remove trailing slash (unless root)
    path = parsed.path or '/'
    if path != '/' and path.endswith('/'):
        path = path[:-1]
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, '', '', ''))


def get_sitemap_urls(base_url):
    """Fetch and parse sitemap.xml for <loc> URLs."""
    sitemap = base_url.rstrip('/') + '/sitemap.xml'
    try:
        r = requests.get(sitemap, headers=headers, timeout=10)
        r.raise_for_status()
        # parse XML
        root = ET.fromstring(r.content)
        urls = []
        for loc in root.findall('.//{*}loc'):
            url = loc.text.strip()
            if url:
                norm = normalize_url(url)
                if norm:
                    urls.append(norm)
        print(f"🔍 Found {len(urls)} URLs in sitemap.xml")
        return urls
    except Exception:
        return []


def save_asset(url, dest_folder):
    """Download asset to dest_folder; return filename or None."""
    parsed = urlparse(url)
    name = os.path.basename(parsed.path) or 'index'
    local_path = os.path.join(dest_folder, name)
    if os.path.exists(local_path):
        return name
    try:
        resp = requests.get(url, headers=headers, timeout=10, stream=True)
        resp.raise_for_status()
    except Exception as e:
        print(f"⚠️  Skipping asset {url}: {e}")
        return None
    ensure_dir(dest_folder)
    with open(local_path, 'wb') as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    print(f"📥 Asset: {url} → {local_path}")
    return name


def url_to_filepath(url, base_domain, root_html):
    """Map a URL to a local file path under root_html/html."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if path in ('', '/'):
        return os.path.join(root_html, 'index.html')
    # remove leading '/'
    path = path.lstrip('/')
    # if no extension, treat as folder
    if os.path.splitext(path)[1] == '':
        folder = os.path.join(root_html, path)
        ensure_dir(folder)
        return os.path.join(folder, 'index.html')
    # file path
    folder = os.path.join(root_html, os.path.dirname(path))
    ensure_dir(folder)
    return os.path.join(folder, os.path.basename(path))


def make_relative(from_path, to_path):
    rel = os.path.relpath(to_path, os.path.dirname(from_path))
    return rel.replace(os.sep, '/')


def scrape_site(base_url=default_base, output_root=output_root):
    parsed_root = urlparse(base_url)
    domain = parsed_root.netloc.lower()
    root_html = os.path.join(output_root, 'html')
    css_dir = os.path.join(output_root, 'css')
    js_dir = os.path.join(output_root, 'js')

    # Seed URLs: sitemap first, then homepage
    seeds = get_sitemap_urls(base_url)
    if base_url not in seeds:
        seeds.insert(0, normalize_url(base_url))

    visited = set()
    queue = deque(seeds)

    while queue:
        url = queue.popleft()
        norm = normalize_url(url)
        if not norm or norm in visited:
            continue
        if urlparse(norm).netloc.lower() != domain:
            continue
        visited.add(norm)
        print(f"➡️  Fetching: {norm}")

        # Fetch page
        try:
            resp = requests.get(norm, headers=headers, timeout=10)
            resp.raise_for_status()
            html_text = resp.text
        except Exception as e:
            print(f"❌  Failed to fetch {norm}: {e}")
            continue

        soup = BeautifulSoup(html_text, 'html.parser')
        local_page = url_to_filepath(norm, domain, root_html)

        # Download & rewrite CSS
        for link in soup.select('link[rel=stylesheet]'):
            href = link.get('href')
            if not href:
                continue
            abs_href = urljoin(norm, href)
            fname = save_asset(abs_href, css_dir)
            if fname:
                rel = make_relative(local_page, os.path.join(css_dir, fname))
                link['href'] = rel

        # Download & rewrite JS
        for script in soup.select('script[src]'):
            src = script['src']
            abs_src = urljoin(norm, src)
            fname = save_asset(abs_src, js_dir)
            if fname:
                rel = make_relative(local_page, os.path.join(js_dir, fname))
                script['src'] = rel

        # Enqueue internal HTML links
        for a in soup.select('a[href]'):
            href = a['href']
            abs_link = urljoin(norm, href)
            child = normalize_url(abs_link)
            # only enqueue .html or directory-like URLs
            if child and urlparse(child).netloc.lower() == domain:
                queue.append(child)

        # Save modified HTML
        ensure_dir(os.path.dirname(local_page))
        with open(local_page, 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        print(f"💾 Saved page to: {local_page}")

    print(f"🎉 Done! Crawled {len(visited)} pages.")

if __name__ == '__main__':
    base = sys.argv[1] if len(sys.argv) > 1 else default_base
    out = sys.argv[2] if len(sys.argv) > 2 else output_root
    scrape_site(base, out)