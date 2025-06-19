# Web Scraper & WordPress Cloner

This project provides two Python scripts for website cloning:

- [`scraped.py`](scraped.py): A general-purpose website scraper that downloads HTML pages and static assets, rewriting links for local use.
- [`wp_cloner.py`](wp_cloner.py): A WordPress-focused cloner that preserves WordPress directory structure and attempts to fetch WordPress-specific resources.

---

## Features

- Recursively downloads all internal HTML pages and static assets (CSS, JS, images, fonts, etc.).
- Rewrites asset links for local usage.
- Handles `sitemap.xml` for improved coverage.
- Skips external domains and duplicate pages.
- [`wp_cloner.py`](wp_cloner.py) preserves WordPress folder structure and fetches WordPress REST API endpoints.

---
## Activate Virtual Environment

**For Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**For Windows (Command Prompt):**
```cmd
python -m venv venv 
venv\Scripts\activate
```

**For Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

## Requirements

- Python 3.6+
- [aiohttp](https://pypi.org/project/aiohttp/)
- [aiofiles](https://pypi.org/project/aiofiles/)
- [beautifulsoup4](https://pypi.org/project/beautifulsoup4/)

Install all dependencies with:

```sh
pip install --upgrade pip 
pip install requests beautifulsoup4 aiohttp aiofiles certifi
pip install --upgrade requests beautifulsoup4 aiohttp aiofiles certifi
export SSL_CERT_FILE=$(python -m certifi)  # macOS/Linux
```

---

## Usage

### 1. General Website Scraper

Clone a website to your local machine:

```sh
python3 scraped.py [BASE_URL] [OUTPUT_DIR]
```

- `BASE_URL` (optional): The root URL to start scraping (default: `https://www.hsc.co.ke/`)
- `OUTPUT_DIR` (optional): Directory to save the cloned site (default: `site_clone`)

Example:

```sh
python3 scraped.py https://example.com/ my_clone
```

This will create a `my_clone` directory with subfolders for HTML, CSS, JS, images, etc.

---

### 2. WordPress Cloner

Clone a WordPress site, preserving its structure:

```sh
python3 wp_cloner.py [BASE_URL] [OUTPUT_DIR]
```

- `BASE_URL` (optional): The root URL to start scraping (default: `https://www.hsc.co.ke/`)
- `OUTPUT_DIR` (optional): Directory to save the cloned site (default: `wp_clone`)

Example:

```sh
python3 wp_cloner.py https://mywordpresssite.com/ my_wp_clone 
```

This will create a `my_wp_clone` directory with WordPress core folders and files.

---

## Logging

- [`scraped.py`](scraped.py) logs to `site_clone.log`.
- [`wp_cloner.py`](wp_cloner.py) logs to `wp_clone.log`.

---

## Notes

- Only static content is supported. Dynamic content loaded via JavaScript will not be scraped.
- For large sites, scraping may take a while and use significant disk space.
- Make sure you have permission