# Web Scrapper

This project is a simple web scraper and HTML extractor for cloning static websites. It consists of two main scripts:

- [`scraped.py`](scraped.py): Crawls a website, downloads HTML pages, CSS, and JS assets, and rewrites links for local use.
- [`extract.py`](extract.py): Cleans and rewrites an existing HTML file's asset links for local usage.

## Requirements

- Python 3.6+
- [requests](https://pypi.org/project/requests/)
- [beautifulsoup4](https://pypi.org/project/beautifulsoup4/)

Install dependencies with:

```sh
pip install requests beautifulsoup4
```

## Usage

### 1. Scrape a Website

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

This will create a `my_clone` directory with `html/`, `css/`, and `js/` subfolders.

### 2. Clean and Rewrite HTML

After scraping, you can clean and rewrite asset links in an HTML file:

```sh
python3 extract.py [INPUT_HTML] [OUTPUT_HTML]
```

- `INPUT_HTML` (optional): Path to the HTML file to process (default: tries to auto-detect)
- `OUTPUT_HTML` (optional): Path to save the cleaned HTML (default: `index.html`)

Example:

```sh
python3 extract.py my_clone/html/index.html cleaned_index.html
```

## Features

- Recursively downloads all internal HTML pages, CSS, and JS assets.
- Rewrites asset links for local usage.
- Handles sitemap.xml if available for better coverage.
- Skips external domains and duplicate pages.

## Notes

- Only static content is supported. Dynamic content loaded via JavaScript will not be scraped.
- For large sites, scraping may take a while and use significant disk space.

## License

MIT License

---