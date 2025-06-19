#!/usr/bin/env python3
import os
import sys
import asyncio
import aiohttp
from urllib.parse import urljoin, urlparse, urlunparse, urldefrag, unquote
from collections import deque
import logging
from pathlib import Path
import re
try:
    from bs4 import BeautifulSoup
    import xml.etree.ElementTree as ET
    import aiofiles
except ImportError as e:
    print(f"Missing dependency: {e.name}. Install with `pip install requests beautifulsoup4 aiohttp aiofiles`", file=sys.stderr)
    sys.exit(1)

# Configuration
CONFIG = {
    'base_url': 'https://www.example.com',  # Override via CLI
    'output_root': 'site_clone',
    'max_pages': 10000,  # Maximum pages to crawl to prevent infinite loops
    'timeout': 15,  # HTTP request timeout (seconds)
    'max_concurrent': 10,  # Concurrent downloads
    'asset_types': {'.css', '.js', '.jpg', '.jpeg', '.png', '.gif', '.woff', '.woff2', '.ttf', '.svg'},
    'exclude_patterns': {r'.*\.pdf$', r'.*\.zip$', r'.*\.exe$'},
    'user_agent': 'Mozilla/5.0 (compatible; SiteCloner/2.0)',
    'follow_sitemap': True,
    'fetch_json': True,  # Try to fetch JSON API endpoints
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('site_clone.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def normalize_url(url):
    """Normalize URL by removing fragments and standardizing format."""
    if not url:
        return None
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    path = parsed.path or '/'
    if path != '/' and path.endswith('/'):
        path = path[:-1]
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, '', '', ''))

def is_valid_url(url, base_domain):
    """Check if URL is valid and belongs to the same domain."""
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.netloc.lower() == base_domain

async def fetch_sitemap_urls(base_url, session):
    """Fetch and parse sitemap.xml for URLs."""
    sitemap = base_url.rstrip('/') + '/sitemap.xml'
    try:
        async with session.get(sitemap, timeout=CONFIG['timeout']) as resp:
            resp.raise_for_status()
            root = ET.fromstring(await resp.text())
            urls = [normalize_url(loc.text.strip()) for loc in root.findall('.//{*}loc') if loc.text]
            logger.info(f"Found {len(urls)} URLs in sitemap.xml")
            return [url for url in urls if url]
    except Exception as e:
        logger.warning(f"Failed to fetch sitemap {sitemap}: {e}")
        return []

async def fetch_json_urls(url, session):
    """Fetch potential JSON API endpoints."""
    parsed = urlparse(url)
    possible_endpoints = [
        f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2/posts" if 'wordpress' in url.lower() else None,
        f"{parsed.scheme}://{parsed.netloc}/api/",
        f"{parsed.scheme}://{parsed.netloc}/data/",
    ]
    endpoints = [ep for ep in possible_endpoints if ep]
    json_urls = []
    for endpoint in endpoints:
        try:
            async with session.get(endpoint, timeout=CONFIG['timeout']) as resp:
                if resp.status == 200 and 'application/json' in resp.headers.get('Content-Type', ''):
                    json_urls.append(endpoint)
                    logger.info(f"Found JSON endpoint: {endpoint}")
        except Exception:
            continue
    return json_urls

async def save_asset(url, dest_folder, session):
    """Download and save an asset asynchronously."""
    parsed = urlparse(url)
    name = os.path.basename(parsed.path) or f"asset_{hash(url)}"
    local_path = Path(dest_folder) / name
    if local_path.exists():
        return name
    try:
        async with session.get(url, timeout=CONFIG['timeout']) as resp:
            resp.raise_for_status()
            Path(dest_folder).mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(local_path, 'wb') as f:
                async for chunk in resp.content.iter_chunked(8192):
                    await f.write(chunk)
        logger.info(f"Saved asset: {url} → {local_path}")
        return name
    except Exception as e:
        logger.warning(f"Failed to download asset {url}: {e}")
        return None

def url_to_filepath(url, base_domain, root_html):
    """Map a URL to a local file path."""
    parsed = urlparse(url)
    path = unquote(parsed.path).lstrip('/')
    if not path or path == '/':
        return Path(root_html) / 'index.html'
    if not os.path.splitext(path)[1]:
        folder = Path(root_html) / path
        folder.mkdir(parents=True, exist_ok=True)
        return folder / 'index.html'
    folder = Path(root_html) / os.path.dirname(path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / os.path.basename(path)

def make_relative(from_path, to_path):
    """Create a relative path from one path to another."""
    rel = os.path.relpath(to_path, os.path.dirname(from_path))
    return rel.replace(os.sep, '/')

async def process_page(url, base_domain, root_html, asset_dirs, session, visited, queue):
    """Process a single page and its assets."""
    norm_url = normalize_url(url)
    if not norm_url or norm_url in visited or not is_valid_url(norm_url, base_domain):
        return
    if len(visited) >= CONFIG['max_pages']:
        logger.info(f"Reached max pages limit ({CONFIG['max_pages']})")
        return
    visited.add(norm_url)
    logger.info(f"Fetching: {norm_url}")

    try:
        async with session.get(norm_url, timeout=CONFIG['timeout']) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type:
                return
            html_text = await resp.text()
    except Exception as e:
        logger.error(f"Failed to fetch {norm_url}: {e}")
        return

    soup = BeautifulSoup(html_text, 'html.parser')
    local_page = url_to_filepath(norm_url, base_domain, root_html)

    # Process assets
    tasks = []
    for tag, attr, dir_key in [
        ('link', 'href', 'css'),  # CSS files
        ('script', 'src', 'js'),  # JS files
        ('img', 'src', 'images'),  # Images
        ('source', 'src', 'media'),  # Media files
        ('link', 'href', 'fonts'),  # Fonts
    ]:
        for element in soup.find_all(tag, **{attr: True}):
            href = element[attr]
            abs_href = urljoin(norm_url, href)
            if any(abs_href.endswith(ext) for ext in CONFIG['asset_types']) and not any(re.match(pat, abs_href) for pat in CONFIG['exclude_patterns']):
                if is_valid_url(abs_href, base_domain):
                    tasks.append(save_asset(abs_href, asset_dirs[dir_key], session))
                    element[attr] = make_relative(local_page, Path(asset_dirs[dir_key]) / os.path.basename(urlparse(abs_href).path))

    # Run asset downloads concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result, task in zip(results, tasks):
        if isinstance(result, Exception):
            logger.warning(f"Asset download failed: {result}")

    # Enqueue internal links
    for a in soup.find_all('a', href=True):
        abs_link = urljoin(norm_url, a['href'])
        child = normalize_url(abs_link)
        if child and is_valid_url(child, base_domain) and child not in visited:
            queue.append(child)

    # Save modified HTML
    local_page.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(local_page, 'w', encoding='utf-8') as f:
        await f.write(soup.prettify())
    logger.info(f"Saved page: {local_page}")

async def scrape_site(base_url=None, output_root=None):
    """Main crawling function."""
    base_url = base_url or CONFIG['base_url']
    output_root = output_root or CONFIG['output_root']
    base_domain = urlparse(base_url).netloc.lower()

    # Setup directories
    root_html = Path(output_root) / 'html'
    asset_dirs = {
        'css': Path(output_root) / 'css',
        'js': Path(output_root) / 'js',
        'images': Path(output_root) / 'images',
        'media': Path(output_root) / 'media',
        'fonts': Path(output_root) / 'fonts',
    }
    for dir_path in asset_dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)

    # Initialize
    visited = set()
    queue = deque([normalize_url(base_url)])
    headers = {'User-Agent': CONFIG['user_agent']}

    async with aiohttp.ClientSession(headers=headers) as session:
        # Seed with sitemap
        if CONFIG['follow_sitemap']:
            sitemap_urls = await fetch_sitemap_urls(base_url, session)
            for url in sitemap_urls:
                if url not in visited and is_valid_url(url, base_domain):
                    queue.append(url)

        # Fetch JSON endpoints for dynamic sites
        if CONFIG['fetch_json']:
            json_urls = await fetch_json_urls(base_url, session)
            for url in json_urls:
                if url not in visited and is_valid_url(url, base_domain):
                    queue.append(url)

        # Process pages
        semaphore = asyncio.Semaphore(CONFIG['max_concurrent'])
        async def bounded_process(url):
            async with semaphore:
                await process_page(url, base_domain, root_html, asset_dirs, session, visited, queue)

        tasks = []
        while queue and len(visited) < CONFIG['max_pages']:
            url = queue.popleft()
            tasks.append(bounded_process(url))
            if len(tasks) >= CONFIG['max_concurrent']:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"Completed! Crawled {len(visited)} pages.")

async def main():
    base = sys.argv[1] if len(sys.argv) > 1 else CONFIG['base_url']
    out = sys.argv[2] if len(sys.argv) > 2 else CONFIG['output_root']
    await scrape_site(base, out)

if __name__ == '__main__':
    asyncio.run(main())