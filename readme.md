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
- Check Output:
HTML files and assets are in wp_clone/ with WordPress structure.
JSON files are in wp_clone/json/ (e.g., home.json, about.json).
REST API data (if fetched) is in wp_clone/json/ with hashed filenames.
Import into WordPress:
Use WP All Import or the custom importer plugin.
Upload assets to your WordPress site.
Update asset URLs in the content.
Edit in Elementor:
Open imported pages in Elementor to refine layouts.
Rebuild complex sections if the HTML doesn’t render perfectly.
Test with a Local WordPress:
Set up a local WordPress site to test imports before deploying to production.
Use REST API Data:
If /wp-json/wp/v2/pages is accessible, prioritize importing those JSON files for cleaner Elementor integration.
Backup Plugins:
If you gain access to wp-admin, use a plugin like Duplicator to export a full site, including the database.

Use WP All Import:
Install the WP All Import plugin on your WordPress site.
Go to All Import > New Import.
Upload pages.json and map fields:
title → Page Title
content → Page Content
slug → Page Slug
status → Status (Publish)
Run the import to create pages.
Manually upload assets from wp_clone/wp-content/uploads/ to the media library via Media > Add New.
Edit with Elementor:
In WordPress admin, go to Pages > All Pages.
Find the imported pages (e.g., “Home”, “About”).
Click “Edit with Elementor” for each page.
The HTML content will appear in a Text Editor widget or as raw content.
Drag and drop Elementor widgets to rebuild layouts (e.g., replace <img> tags with Image widgets, text with Text Editor widgets).
Save changes.
Handle Assets:
After importing assets to the media library, update image references in Elementor by selecting the uploaded media files.
CSS/JS files in wp-content/themes/ can be added to your theme or enqueued manually.
