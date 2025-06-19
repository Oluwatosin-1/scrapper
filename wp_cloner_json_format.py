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
import json
import argparse
import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
try:
    from bs4 import BeautifulSoup
    import aiofiles
except ImportError as e:
    print(f"Missing dependency: {e.name}. Install with `pip install requests beautifulsoup4 aiohttp aiofiles certifi`", file=sys.stderr)
    sys.exit(1)

# Configuration
DEFAULT_CONFIG = {
    'base_url': 'https://www.hsc.co.ke/',
    'output_root': 'wp_clone',
    'max_pages': 10000,
    'timeout': 15,
    'max_concurrent': 10,
    'max_retries': 3,
    'asset_types': {'.css', '.js', '.jpg', '.jpeg', '.png', '.gif', '.woff', '.woff2', '.ttf', '.svg', '.php', '.ico'},
    'exclude_patterns': {r'.*wp-config\.php$', r'.*wp-config-sample\.php$', r'.*wp-login\.php$', r'.*\.sql$', r'.*\.zip$'},
    'user_agent': 'Mozilla/5.0 (compatible; WPCloner/1.3)',
    'follow_sitemap': True,
    'fetch_json': True,
    'wp_folders': {'wp-content', 'wp-admin', 'wp-includes'},
    'verify_ssl': True,
    'ca_bundle': certifi.where(),
    'username': '',
    'password': '',
    'generate_xml': True,  # Generate WXR XML for WordPress import
    'xml_output': 'wordpress_export.xml',
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

def load_config(config_file='config.json'):
    """Load configuration from JSON file if exists."""
    config = DEFAULT_CONFIG.copy()
    if Path(config_file).exists():
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
            config.update(file_config)
            logger.info(f"Loaded configuration from {config_file}")
        except Exception as e:
            logger.warning(f"Failed to load config file {config_file}: {e}")
    return config

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

async def login(session, base_url, username, password):
    """Attempt to log in to WordPress via wp-login.php."""
    login_url = urljoin(base_url, 'wp-login.php')
    try:
        async with session.get(login_url, timeout=CONFIG['timeout']) as resp:
            resp.raise_for_status()
            soup = BeautifulSoup(await resp.text(), 'html.parser')
            login_form = soup.find('form', id='loginform')
            if not login_form:
                logger.warning("Could not find login form on wp-login.php")
                return False
            data = {
                'log': username,
                'pwd': password,
                'wp-submit': 'Log In',
                'redirect_to': urljoin(base_url, 'wp-admin/'),
            }
            for inp in login_form.find_all('input', type='hidden'):
                if inp.get('name'):
                    data[inp['name']] = inp.get('value', '')
        async with session.post(login_url, data=data, timeout=CONFIG['timeout'], allow_redirects=True) as resp:
            if 'wp-admin' in resp.url or resp.status == 200:
                logger.info(f"Login successful for {username}")
                return True
            else:
                logger.error(f"Login failed for {username}: Status {resp.status}")
                return False
    except Exception as e:
        logger.error(f"Login error: {e}")
        return False

async def fetch_sitemap_urls(base_url, session):
    """Fetch and parse sitemap.xml for URLs."""
    sitemap = base_url.rstrip('/') + '/sitemap.xml'
    for attempt in range(CONFIG['max_retries']):
        try:
            async with session.get(sitemap, timeout=CONFIG['timeout']) as resp:
                resp.raise_for_status()
                root = ET.fromstring(await resp.text())
                urls = [normalize_url(loc.text.strip()) for loc in root.findall('.//{*}loc') if loc.text]
                logger.info(f"Found {len(urls)} URLs in sitemap.xml")
                return [url for url in urls if url]
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{CONFIG['max_retries']} failed for sitemap {sitemap}: {e}")
            if attempt + 1 < CONFIG['max_retries']:
                await asyncio.sleep(1)
    logger.error(f"Failed to fetch sitemap {sitemap} after {CONFIG['max_retries']} attempts")
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
        for attempt in range(CONFIG['max_retries']):
            try:
                async with session.get(endpoint, timeout=CONFIG['timeout']) as resp:
                    if resp.status == 200 and 'application/json' in resp.headers.get('Content-Type', ''):
                        json_urls.append(endpoint)
                        logger.info(f"Found JSON endpoint: {endpoint}")
                        break
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{CONFIG['max_retries']} failed for {endpoint}: {e}")
                if attempt + 1 < CONFIG['max_retries']:
                    await asyncio.sleep(1)
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
                await asyncio.sleep(1)
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

def extract_page_data(url, html_content, base_url):
    """Extract title, content, and slug from HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    # Extract title
    title_tag = soup.find('title')
    title = title_tag.text.strip() if title_tag else os.path.basename(urlparse(url).path) or 'Untitled'
    # Extract main content (try common selectors)
    content_selectors = ['main', 'article', '#content', '.content', '.entry-content', 'body']
    content = None
    for selector in content_selectors:
        content_elem = soup.select_one(selector)
        if content_elem:
            content = str(content_elem)
            break
    if not content:
        content = str(soup.body) if soup.body else ''
    # Generate slug
    parsed = urlparse(url)
    path = parsed.path.rstrip('/').lstrip('/')
    slug = path if path else 'home'
    if path.endswith('.php'):
        slug = os.path.splitext(path)[0]
    elif not os.path.splitext(path)[1]:
        slug = os.path.basename(path) or 'home'
    return {
        'title': title,
        'content': content,
        'slug': slug,
        'url': url,
    }

def generate_wxr_xml(pages, output_path, base_url):
    """Generate WordPress WXR XML file from pages."""
    root = ET.Element('rss')
    root.set('version', '2.0')
    root.set('xmlns:excerpt', 'http://wordpress.org/export/1.2/excerpt/')
    root.set('xmlns:content', 'http://purl.org/rss/1.0/modules/content/')
    root.set('xmlns:wfw', 'http://wellformedweb.org/CommentAPI/')
    root.set('xmlns:dc', 'http://purl.org/dc/elements/1.1/')
    root.set('xmlns:wp', 'http://wordpress.org/export/1.2/')

    channel = ET.SubElement(root, 'channel')
    ET.SubElement(channel, 'title').text = urlparse(base_url).netloc
    ET.SubElement(channel, 'link').text = base_url
    ET.SubElement(channel, 'description').text = 'Exported WordPress content'
    ET.SubElement(channel, 'pubDate').text = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')
    ET.SubElement(channel, 'language').text = 'en-US'
    ET.SubElement(channel, 'wp:wxr_version').text = '1.2'

    for page in pages:
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = page['title']
        ET.SubElement(item, 'link').text = page['url']
        ET.SubElement(item, 'pubDate').text = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')
        ET.SubElement(item, 'dc:creator').text = 'admin'
        ET.SubElement(item, 'guid', isPermaLink='false').text = page['url']
        ET.SubElement(item, 'description')  # Empty
        content_encoded = ET.SubElement(item, 'content:encoded')
        content_encoded.text = f'<![CDATA[{page["content"]}]]>'
        ET.SubElement(item, 'wp:post_id').text = str(hash(page['url']) % 1000000)
        ET.SubElement(item, 'wp:post_date').text = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        ET.SubElement(item, 'wp:post_date_gmt').text = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        ET.SubElement(item, 'wp:comment_status').text = 'closed'
        ET.SubElement(item, 'wp:ping_status').text = 'closed'
        ET.SubElement(item, 'wp:post_name').text = page['slug']
        ET.SubElement(item, 'wp:status').text = 'publish'
        ET.SubElement(item, 'wp:post_parent').text = '0'
        ET.SubElement(item, 'wp:menu_order').text = '0'
        ET.SubElement(item, 'wp:post_type').text = 'page'
        ET.SubElement(item, 'wp:post_password').text = ''
        ET.SubElement(item, 'wp:is_sticky').text = '0'

    # Pretty-print XML
    rough_string = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)
    logger.info(f"Generated WXR XML file: {output_path}")

async def process_url(url, base_domain, root_dir, session, visited, queue, pages):
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
        # Collect page data for XML
        if CONFIG['generate_xml'] and local_path.suffix == '.html':
            page_data = extract_page_data(norm_url, html_text, CONFIG['base_url'])
            pages.append(page_data)
    else:
        await save_resource(norm_url, local_path, session)

def make_relative(from_path, to_path):
    """Create a relative path from one path to another."""
    rel = os.path.relpath(to_path, os.path.dirname(from_path))
    return rel.replace(os.sep, '/')

async def scrape_wp_site(base_url=None, output_root=None, username=None, password=None):
    """Main WordPress cloning function."""
    global CONFIG
    CONFIG['base_url'] = base_url or CONFIG['base_url']
    CONFIG['output_root'] = output_root or CONFIG['output_root']
    CONFIG['username'] = username or CONFIG['username']
    CONFIG['password'] = password or CONFIG['password']
    base_domain = urlparse(CONFIG['base_url']).netloc.lower()
    root_dir = Path(CONFIG['output_root'])
    pages = []  # Collect pages for XML

    visited = set()
    queue = deque([normalize_url(CONFIG['base_url'])])
    headers = {'User-Agent': CONFIG['user_agent']}

    ssl_context = None if not CONFIG['verify_ssl'] else ssl.create_default_context(cafile=CONFIG['ca_bundle'])

    async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        if CONFIG['username'] and CONFIG['password']:
            if await login(session, CONFIG['base_url'], CONFIG['username'], CONFIG['password']):
                logger.info("Proceeding with authenticated session")
            else:
                logger.warning("Continuing without authenticated session")
        else:
            logger.info("No credentials provided, crawling public content only")

        if CONFIG['follow_sitemap']:
            sitemap_urls = await fetch_sitemap_urls(CONFIG['base_url'], session)
            for url in sitemap_urls:
                if url not in visited and is_valid_url(url, base_domain):
                    queue.append(url)

        if CONFIG['fetch_json']:
            json_urls = await fetch_json_urls(CONFIG['base_url'], session)
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
            abs_url = urljoin(CONFIG['base_url'], path)
            norm_url = normalize_url(abs_url)
            if norm_url and norm_url not in visited and is_valid_url(norm_url, base_domain):
                queue.append(norm_url)

        semaphore = asyncio.Semaphore(CONFIG['max_concurrent'])
        async def bounded_process(url):
            async with semaphore:
                await process_url(url, base_domain, root_dir, session, visited, queue, pages)

        tasks = []
        while queue and len(visited) < CONFIG['max_pages']:
            url = queue.popleft()
            tasks.append(bounded_process(url))
            if len(tasks) >= CONFIG['max_concurrent']:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Generate XML if enabled
        if CONFIG['generate_xml'] and pages:
            xml_path = root_dir / CONFIG['xml_output']
            generate_wxr_xml(pages, xml_path, CONFIG['base_url'])

    logger.info(f"Completed! Crawled {len(visited)} resources.")

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Clone a WordPress site and generate WXR XML.')
    parser.add_argument('base_url', nargs='?', default=DEFAULT_CONFIG['base_url'], help='Base URL of the WordPress site')
    parser.add_argument('output_root', nargs='?', default=DEFAULT_CONFIG['output_root'], help='Output directory for cloned files')
    parser.add_argument('--username', help='WordPress admin username')
    parser.add_argument('--password', help='WordPress admin password')
    parser.add_argument('--config', default='config.json', help='Path to configuration JSON file')
    parser.add_argument('--no-ssl-verify', action='store_true', help='Disable SSL verification (insecure)')
    parser.add_argument('--no-xml', action='store_true', help='Disable XML generation')
    return parser.parse_args()

async def main():
    args = parse_args()
    global CONFIG
    CONFIG = load_config(args.config)
    if args.no_ssl_verify:
        CONFIG['verify_ssl'] = False
    if args.no_xml:
        CONFIG['generate_xml'] = False
    await scrape_wp_site(args.base_url, args.output_root, args.username, args.password)

if __name__ == '__main__':
    asyncio.run(main())