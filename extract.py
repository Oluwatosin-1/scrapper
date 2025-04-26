#!/usr/bin/env python3
import os
import sys
from bs4 import BeautifulSoup

def die(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)

def find_input():
    candidates = [
        "html/index.html",
        "vinted_clone/html/index.html",
        "index.html"
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    die(f"Couldn't find input HTML. Checked: {', '.join(candidates)}")

def main():
    # Parse args
    # Usage: python3 extract.py [input_html] [output_html]
    input_path  = sys.argv[1] if len(sys.argv) > 1 else find_input()
    output_path = sys.argv[2] if len(sys.argv) > 2 else "index.html"

    if not os.path.isfile(input_path):
        die(f"Input file not found: {input_path}")

    # Load & parse
    with open(input_path, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Rewrite CSS hrefs
    for link in soup.find_all("link", href=True):
        href = link["href"]
        if href.startswith("../css/"):
            link["href"] = href.replace("../css/", "css/")
        elif href.startswith("css/") is False and "vendor.css" in href:
            # catch other css if needed
            link["href"] = os.path.basename(href)

    # Rewrite JS srcs
    for script in soup.find_all("script", src=True):
        src = script["src"]
        if src.startswith("../js/"):
            script["src"] = src.replace("../js/", "js/")
        elif src.startswith("js/") is False and "app" in src:
            # catch other js if needed
            script["src"] = os.path.basename(src)

    # Ensure output dir exists
    out_dir = os.path.dirname(output_path) or "."
    os.makedirs(out_dir, exist_ok=True)

    # Write prettified HTML
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(soup.prettify())

    print(f"✔️  Clean HTML written to {output_path}")

if __name__ == "__main__":
    main()
