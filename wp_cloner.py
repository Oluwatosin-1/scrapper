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
import certifi
import ssl
try:
    from bs4 import BeautifulSoup
    import xml.etree.ElementTree as ET
    import aiofiles
except ImportError as e:
    print(f"Missing dependency: {e.name}. Install with `pip install requests beautifulsoup4 aiohttp aiofiles certifi`", file=sys.stderr)
    sys.exit(1)

# Configuration
CONFIG = {
    'base_url': 'https://www.hsc.co.ke',  # Override via CLI
    'output_root': 'wp_clone_output',  # Override via CLI
    'max_pages': 10000,  # Maximum pages to prevent infinite loops
    'timeout': 15,  # HTTP request timeout (seconds)
    'max_concurrent': 10,  # Concurrent downloads
    'max_retries': 3,  # Retry attempts for failed requests
    'asset_types': {'.css', '.js', '.jpg', '.jpeg', '.png', '.gif', '.woff', '.woff2', '.ttf', '.svg', '.php', '.ico'},
    'exclude_patterns': {r'.*wp-config\.php$', r'.*wp-login\.php$', r'.*\.sql$', r'.*\.zip$'},
    'user_agent': 'Mozilla/5.0 (compatible; WPCloner/1.1)',
    'follow_sitemap': True,
    'fetch_json': True,  # Fetch WordPress REST API
    'wp_folders': {'wp-content', 'wp-admin', 'wp-includes'},
    'verify_ssl': True,  # Set to False to disable SSL verification (insecure)
    'ca_bundle': certifi.where(),  # Path to CA bundle
}

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wp_clone.log'),
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
    """Fetch WordPress REST API endpoints."""
    parsed = urlparse(url)
    possible_endpoints = [
        f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2/posts",
        f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2/pages",
        f"{parsed.scheme}://{parsed.netloc}/wp-json/wp/v2/media",
        f"{parsed.scheme}://{parsed.netloc}/wp-json/",
    ]
    json_urls = []
    for endpoint in possible_endpoints:
        try:
            async with session.get(endpoint, timeout=CONFIG['timeout']) as resp:
                if resp.status == 200 and 'application/json' in resp.headers.get('Content-Type', ''):
                    json_urls.append(endpoint)
                    logger.info(f"Found JSON endpoint: {endpoint}")
        except Exception:
            continue
    return json_urls

async def save_resource(url, dest_path, session):
    """Download and save a resource asynchronously with retries."""
    if dest_path.exists():
        return dest_path.name
    for attempt in range(CONFIG['max_retries']):
        try:
            async with session.get(url, timeout=CONFIG['timeout']) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get('Content-Type', '').lower()
                if 'text/html' in content_type:
                    content = await resp.text()
                    soup = BeautifulSoup(content, 'html.parser')
                    content = soup.prettify()
                else:
                    content = await resp.read()
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(dest_path, 'wb' if isinstance(content, bytes) else 'w', encoding=None if isinstance(content, bytes) else 'utf-8') as f:
                    await f.write(content)
                logger.info(f"Saved resource: {url} → {dest_path}")
                return dest_path.name
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{CONFIG['max_retries']} failed for {url}: {e}")
            if attempt + 1 < CONFIG['max_retries']:
                await asyncio.sleep(1)  # Backoff before retry
    logger.error(f"Failed to download {url} after {CONFIG['max_retries']} attempts")
    return None

def url_to_filepath(url, base_domain, root_dir):
    """Map a URL to a local file path, preserving WordPress structure."""
    parsed = urlparse(url)
    path = unquote(parsed.path).lstrip('/')
    if not path:
        return Path(root_dir) / 'index.php'
    if any(path.startswith(folder) for folder in CONFIG['wp_folders']):
        return Path(root_dir) / path
    if path.endswith('.php') and '/' not in path:
        return Path(root_dir) / path
    if not os.path.splitext(path)[1]:
        return Path(root_dir) / path / 'index.html'
    return Path(root_dir) / path

async def process_url(url, base_domain, root_dir, session, visited, queue):
    """Process a single URL and its resources."""
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
            if 'text/html' not in content_type and not norm_url.endswith(('.php', '.css', '.js')):
                return
            html_text = await resp.text() if 'text/html' in content_type else None
    except Exception as e:
        logger.error(f"Failed to fetch {norm_url}: {e}")
        return

    local_path = url_to_filepath(norm_url, base_domain, root_dir)
    if html_text:
        soup = BeautifulSoup(html_text, 'html.parser')
        tasks = []
        for tag, attr in [
            ('link', 'href'),
            ('script', 'src'),
            ('img', 'src'),
            ('source', 'src'),
        ]:
            for element in soup.find_all(tag, **{attr: True}):
                href = element[attr]
                abs_href = urljoin(norm_url, href)
                if any(abs_href.endswith(ext) for ext in CONFIG['asset_types']) and not any(re.match(pat, abs_href) for pat in CONFIG['exclude_patterns']):
                    if is_valid_url(abs_href, base_domain):
                        asset_path = url_to_filepath(abs_href, base_domain, root_dir)
                        tasks.append(save_resource(abs_href, asset_path, session))
                        element[attr] = make_relative(local_path, asset_path)
        await asyncio.gather(*tasks, return_exceptions=True)
        for a in soup.find_all('a', href=True):
            abs_link = urljoin(norm_url, a['href'])
            child = normalize_url(abs_link)
            if child and is_valid_url(child, base_domain) and child not in visited:
                queue.append(child)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(local_path, 'w', encoding='utf-8') as f:
            await f.write(soup.prettify())
        logger.info(f"Saved page: {local_path}")
    else:
        await save_resource(norm_url, local_path, session)

def make_relative(from_path, to_path):
    """Create a relative path from one path to another."""
    rel = os.path.relpath(to_path, os.path.dirname(from_path))
    return rel.replace(os.sep, '/')

async def scrape_wp_site(base_url=None, output_root=None):
    """Main WordPress cloning function."""
    base_url = base_url or CONFIG['base_url']
    output_root = output_root or CONFIG['output_root']
    base_domain = urlparse(base_url).netloc.lower()
    root_dir = Path(output_root)

    visited = set()
    queue = deque([normalize_url(base_url)])
    headers = {'User-Agent': CONFIG['user_agent']}

    # Configure SSL context
    ssl_context = None if not CONFIG['verify_ssl'] else ssl.create_default_context(cafile=CONFIG['ca_bundle'])

    async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        if CONFIG['follow_sitemap']:
            sitemap_urls = await fetch_sitemap_urls(base_url, session)
            for url in sitemap_urls:
                if url not in visited and is_valid_url(url, base_domain):
                    queue.append(url)
        if CONFIG['fetch_json']:
            json_urls = await fetch_json_urls(base_url, session)
            for url in json_urls:
                if url not in visited and is_valid_url(url, base_domain):
                    queue.append(url)
        wp_core_paths = [
            'wp-content/themes/',
            'wp-content/plugins/',
            'wp-admin/',
            'wp-includes/',
            'index.php',
            'wp-blog-header.php',
        ]
        for path in wp_core_paths:
            abs_url = urljoin(base_url, path)
            norm_url = normalize_url(abs_url)
            if norm_url and norm_url not in visited and is_valid_url(norm_url, base_domain):
                queue.append(norm_url)

        semaphore = asyncio.Semaphore(CONFIG['max_concurrent'])
        async def bounded_process(url):
            async with semaphore:
                await process_url(url, base_domain, root_dir, session, visited, queue)

        tasks = []
        while queue and len(visited) < CONFIG['max_pages']:
            url = queue.popleft()
            tasks.append(bounded_process(url))
            if len(tasks) >= CONFIG['max_concurrent']:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"Completed! Crawled {len(visited)} resources.")

async def main():
    base = sys.argv[1] if len(sys.argv) > 1 else CONFIG['base_url']
    out = sys.argv[2] if len(sys.argv) > 2 else CONFIG['output_root']
    await scrape_wp_site(base, out)

if __name__ == '__main__':
    asyncio.run(main())