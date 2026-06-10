#!/usr/bin/env python3
"""
scrape_substack.py
==================
Archive an entire Substack publication to local Markdown files.

It walks the publication's archive API to enumerate every post, fetches each
post's full HTML, converts it to Markdown, and writes one file per post with
YAML front-matter. Automatically downloads inline images and localizes links.
Saves likes, comments, and restacks to a CSV file.

Works with custom-domain Substacks (e.g. https://killercharts.blog).
"""

import argparse
import base64
import csv
import hashlib
import os
import re
import sys
import time
from typing import Any, Dict, Generator, List, Optional
from urllib.parse import urlparse

# If running as a PyInstaller executable, configure SSL CA bundle paths to use certifi
if getattr(sys, 'frozen', False):
    try:
        import certifi
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
        os.environ['SSL_CERT_FILE'] = certifi.where()
    except Exception as e:
        pass

try:
    import requests
    from bs4 import BeautifulSoup
    from markdownify import markdownify as html_to_md
    from fpdf import FPDF
except ImportError:
    sys.exit("Missing deps. Run:  pip install requests beautifulsoup4 markdownify fpdf2")


# --------------------------------------------------------------------------- #
# Constants & Mappings
# --------------------------------------------------------------------------- #
EXT_BY_CT: Dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def slugify(value: str, fallback: str = "post") -> str:
    """Convert a string into a clean URL slug."""
    value = re.sub(r"[^\w\s-]", "", (value or "")).strip().lower()
    value = re.sub(r"[\s_-]+", "-", value)
    return value[:80] or fallback


def make_session(cookie: str) -> requests.Session:
    """Create a configured requests Session with optional cookie authentication."""
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
    )
    if cookie:
        s.headers["Cookie"] = cookie
    return s


def get_json(session: requests.Session, url: str, delay: float, retries: int = 4) -> Optional[Any]:
    """GET a URL and return parsed JSON, with exponential backoff on errors."""
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    print(f"  ! Non-JSON response from {url}", file=sys.stderr)
                    return None
            if r.status_code == 404:
                return None
            if r.status_code in (401, 403):
                print(f"  ! Auth / Permission error (HTTP {r.status_code}) on {url}", file=sys.stderr)
                return None
            print(f"  ! HTTP {r.status_code} on {url}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  ! Request error ({e}) on {url}", file=sys.stderr)
        time.sleep(delay * (attempt + 2))  # Exponential backoff
    return None


def get_default_out_dir(url: str) -> str:
    """Generate a clean directory name from a Substack URL."""
    parsed = urlparse(url)
    netloc = parsed.netloc or parsed.path
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if netloc.endswith(".substack.com"):
        name = netloc[:-13]
    else:
        parts = netloc.split(".")
        name = parts[-2] if len(parts) > 1 else parts[0]
    return f"./{slugify(name)}_md"


# --------------------------------------------------------------------------- #
# Substack API Walking
# --------------------------------------------------------------------------- #
def fetch_archive(session: requests.Session, base: str, limit: int, delay: float) -> Generator[Dict[str, Any], None, None]:
    """Yield post-metadata dicts from the archive API, paginating to the end."""
    offset = 0
    while True:
        url = f"{base}/api/v1/archive?sort=new&search=&offset={offset}&limit={limit}"
        batch = get_json(session, url, delay)
        if not batch:
            break
        for item in batch:
            yield item
        offset += len(batch)
        time.sleep(delay)


def fetch_post(session: requests.Session, base: str, slug: str, delay: float) -> Optional[Dict[str, Any]]:
    """Fetch detail payload for a specific post."""
    return get_json(session, f"{base}/api/v1/posts/{slug}", delay)


# --------------------------------------------------------------------------- #
# Image Handling & Localization
# --------------------------------------------------------------------------- #
def _download_one(session: requests.Session, url: str, img_dir: str, delay: float) -> Optional[str]:
    """Download a single image URL (supports base64 and standard URLs) and return its local filename."""
    os.makedirs(img_dir, exist_ok=True)
    h = hashlib.sha1(url.encode()).hexdigest()[:16]

    # Handle Base64 inline data URLs directly without making network requests
    if url.startswith("data:image/"):
        try:
            header, encoded = url.split(",", 1)
            ext = "." + header.split(";")[0].split("/")[1]
            # Strip off metadata if any (e.g. ;base64)
            if "+" in ext:
                ext = ext.split("+")[0]
            data = base64.b64decode(encoded)
            name = f"{h}{ext}"
            with open(os.path.join(img_dir, name), "wb") as f:
                f.write(data)
            return name
        except Exception as e:
            print(f"  ! Failed to decode inline base64 image: {e}", file=sys.stderr)
            return None

    # check cache on disk
    for existing in os.listdir(img_dir):
        if existing.startswith(h):
            return existing

    # Standard URL download
    try:
        r = session.get(url, timeout=60)
        if r.status_code != 200:
            return None
        content_type = r.headers.get("Content-Type", "").split(";")[0].strip()
        ext = EXT_BY_CT.get(content_type)
        if not ext:
            path_ext = os.path.splitext(urlparse(url).path)[1]
            ext = path_ext if path_ext else ".img"
        name = f"{h}{ext}"
        with open(os.path.join(img_dir, name), "wb") as f:
            f.write(r.content)
        time.sleep(delay)
        return name
    except requests.RequestException as e:
        print(f"  ! Image download failed for {url}: {e}", file=sys.stderr)
        return None


def localize_html_images(session: requests.Session, body_html: str, img_dir: str, delay: float, cache: Dict[str, str]) -> str:
    """Parse HTML body, download images, clean picture tags, and localize all src & anchor hrefs."""
    if not body_html:
        return ""

    soup = BeautifulSoup(body_html, "html.parser")

    # Simplify picture tags: extract nested img tag and discard source wrappers
    for picture in soup.find_all("picture"):
        img = picture.find("img")
        if img:
            picture.replace_with(img)

    # Process all image tags
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        if src.startswith("images/"):
            continue

        if src not in cache:
            cache[src] = _download_one(session, src, img_dir, delay) or ""
        local = cache[src]

        if local:
            local_path = f"images/{local}"
            img["src"] = local_path
            # Delete srcset so markdown converters or viewers don't fetch original sources
            if img.get("srcset"):
                del img["srcset"]

            # If wrapped in an anchor link pointing to the same CDN image, localize the link as well
            current = img
            for _ in range(4):
                parent = current.parent
                if not parent:
                    break
                if parent.name == "a":
                    href = parent.get("href")
                    if href:
                        is_image_link = "substackcdn.com" in href or any(
                            ext in href.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"]
                        )
                        if is_image_link:
                            parent["href"] = local_path
                    break
                current = parent

    return str(soup)


# --------------------------------------------------------------------------- #
# Rendering Post to Markdown
# --------------------------------------------------------------------------- #
def yaml_escape(s: str) -> str:
    """Escape titles/descriptions cleanly for YAML front-matter."""
    cleaned = str(s or "").replace("\n", " ").replace("\r", "").strip()
    return '"' + cleaned.replace("\\", "\\\\").replace('"', '\\"') + '"'


def post_to_markdown(meta: Dict[str, Any], detail: Dict[str, Any]) -> str:
    """Convert post payload details to Markdown with front-matter."""
    title = detail.get("title") or meta.get("title") or "untitled"
    subtitle = detail.get("subtitle") or meta.get("subtitle") or ""
    date = (detail.get("post_date") or meta.get("post_date") or "")[:10]
    url = detail.get("canonical_url") or meta.get("canonical_url") or ""
    audience = detail.get("audience") or meta.get("audience") or "everyone"
    body_html = detail.get("body_html") or ""

    body_md = html_to_md(body_html, heading_style="ATX", strip=["script", "style"])
    body_md = re.sub(r"\n{3,}", "\n\n", body_md).strip()

    paywalled = audience not in ("everyone", None, "")
    looks_truncated = paywalled and len(body_md) < 400

    fm = [
        "---",
        f"title: {yaml_escape(title)}",
        f"subtitle: {yaml_escape(subtitle)}",
        f"date: {date}",
        f"url: {yaml_escape(url)}",
        f"audience: {yaml_escape(audience)}",
    ]
    if looks_truncated:
        fm.append("note: \"PREVIEW ONLY - paywalled; re-run with --cookie to fetch full text\"")
    fm.append("---")

    parts = ["\n".join(fm), f"# {title}"]
    if subtitle:
        parts.append(f"*{subtitle}*")
    parts.append(body_md or "_(no body content returned)_")
    return "\n\n".join(parts) + "\n"


# --------------------------------------------------------------------------- #
# Alternative Formats rendering (PDF, HTML, JSON)
# --------------------------------------------------------------------------- #
def clean_unicode_text(text: str) -> str:
    """Replace common smart quotes and dashes with ASCII equivalents to avoid FPDF Helvetica mapping errors."""
    replacements = {
        '\u201c': '"',  # left double quote
        '\u201d': '"',  # right double quote
        '\u2018': "'",  # left single quote
        '\u2019': "'",  # right single quote
        '\u2013': '-',  # en dash
        '\u2014': '--', # em dash
        '\u2022': '*',  # bullet
        '\u2026': '...',# ellipsis
        '\u00a0': ' ',  # non-breaking space
        '\u202f': ' ',  # narrow no-break space
        '\u200b': '',   # zero-width space
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)
    return text.encode('latin-1', 'replace').decode('latin-1')


def generate_pdf(meta: Dict[str, Any], detail: Dict[str, Any], out_dir: str, fname: str) -> bool:
    """Generate a PDF representation of the post using FPDF2."""
    title = detail.get("title") or meta.get("title") or "untitled"
    subtitle = detail.get("subtitle") or meta.get("subtitle") or ""
    date = (detail.get("post_date") or meta.get("post_date") or "")[:10]
    
    body_html = detail.get("body_html", "")
    pdf_soup = BeautifulSoup(body_html, "html.parser")
    
    # Resolve images to absolute local paths
    for img in pdf_soup.find_all("img"):
        src = img.get("src")
        if src and src.startswith("images/"):
            img["src"] = os.path.abspath(os.path.join(out_dir, src))
            if img.get("srcset"):
                del img["srcset"]
                
    # Clean unsupported tags for fpdf2
    for tag in pdf_soup.find_all(["script", "style", "button", "iframe", "video", "svg"]):
        tag.decompose()
        
    html_content = clean_unicode_text(str(pdf_soup))
    clean_title = clean_unicode_text(title)
    clean_subtitle = clean_unicode_text(subtitle)
    
    class SubstackPDF(FPDF):
        def header(self):
            self.set_font('helvetica', 'B', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, 'Archived via StackFlow', border=0, align='R')
            self.ln(10)
            
        def footer(self):
            self.set_y(-15)
            self.set_font('helvetica', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, f'Page {self.page_no()}', border=0, align='C')

    pdf = SubstackPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("helvetica", "B", 18)
    pdf.set_text_color(0, 0, 0)
    pdf.write(10, clean_title)
    pdf.ln(12)
    
    # Subtitle
    if clean_subtitle:
        pdf.set_font("helvetica", "I", 12)
        pdf.set_text_color(100, 100, 100)
        pdf.write(8, clean_subtitle)
        pdf.ln(10)
        
    # Meta line
    pdf.set_font("helvetica", "B", 9)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 6, f"Published: {date}", border="B")
    pdf.ln(8)
    
    # Content
    pdf.set_font("helvetica", size=10)
    pdf.set_text_color(50, 50, 50)
    
    try:
        pdf.write_html(html_content)
        pdf.output(os.path.join(out_dir, fname))
        return True
    except Exception as e:
        print(f"  ! PDF generation failed for {title}: {e}", file=sys.stderr)
        return False


def generate_html(meta: Dict[str, Any], detail: Dict[str, Any], out_dir: str, fname: str) -> bool:
    """Save the post as a beautifully styled offline HTML document."""
    title = detail.get("title") or meta.get("title") or "untitled"
    subtitle = detail.get("subtitle") or meta.get("subtitle") or ""
    date = (detail.get("post_date") or meta.get("post_date") or "")[:10]
    url = detail.get("canonical_url") or meta.get("canonical_url") or ""
    audience = detail.get("audience") or meta.get("audience") or "everyone"
    body_html = detail.get("body_html") or ""
    
    subtitle_html = f'<div class="subtitle">{subtitle}</div>' if subtitle else ""
    
    html_template = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      max-width: 700px;
      margin: 40px auto;
      padding: 0 20px;
      color: #333;
    }}
    h1 {{
      font-size: 2.2em;
      margin-bottom: 5px;
    }}
    .subtitle {{
      font-size: 1.2em;
      color: #666;
      font-style: italic;
      margin-bottom: 20px;
    }}
    .meta {{
      font-size: 0.9em;
      color: #888;
      border-bottom: 1px solid #eee;
      padding-bottom: 20px;
      margin-bottom: 30px;
    }}
    img {{
      max-width: 100%;
      height: auto;
      display: block;
      margin: 20px auto;
      border-radius: 4px;
    }}
    a {{
      color: #ff6719;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  {subtitle_html}
  <div class="meta">
    <span>Published: {date}</span> | <span>Audience: {audience}</span> | <a href="{url}" target="_blank">Original Link</a>
  </div>
  <div class="content">
    {body_html}
  </div>
</body>
</html>"""
    try:
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
            f.write(html_template)
        return True
    except Exception as e:
        print(f"  ! HTML generation failed: {e}", file=sys.stderr)
        return False


def generate_json(meta: Dict[str, Any], detail: Dict[str, Any], out_dir: str, fname: str) -> bool:
    """Save raw post metadata and content details as a structured JSON file."""
    import json
    post_data = {
        "title": detail.get("title") or meta.get("title") or "",
        "subtitle": detail.get("subtitle") or meta.get("subtitle") or "",
        "date": (detail.get("post_date") or meta.get("post_date") or "")[:10],
        "slug": meta.get("slug") or "",
        "audience": detail.get("audience") or meta.get("audience") or "everyone",
        "url": detail.get("canonical_url") or meta.get("canonical_url") or "",
        "likes": detail.get("reaction_count") or meta.get("reaction_count") or 0,
        "reshares": detail.get("restacks") or meta.get("restacks") or 0,
        "comments": detail.get("comment_count") or meta.get("comment_count") or 0,
        "body_html": detail.get("body_html") or "",
    }
    try:
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
            json.dump(post_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"  ! JSON generation failed: {e}", file=sys.stderr)
        return False


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Archive a Substack to Markdown, PDF, HTML, or JSON.")
    ap.add_argument("--url", default="https://plotset2.substack.com/",
                    help="Publication base URL (default: https://plotset2.substack.com/)")
    ap.add_argument("--out", default=None, help="Output directory (default: based on URL)")
    ap.add_argument("--limit", type=int, default=50, help="Archive page size")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="Seconds to pause between requests (be polite)")
    ap.add_argument("--cookie", default="",
                    help="Your logged-in Cookie header, to fetch paywalled posts you can access")
    ap.add_argument("--download-images", action="store_true",
                    help="Download inline images locally and rewrite links")
    ap.add_argument("--max-posts", type=int, default=None,
                    help="Maximum number of posts to download (useful for testing)")
    ap.add_argument("--formats", default="pdf",
                    help="Comma-separated list of formats to save: pdf, md, html, json (default: pdf)")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    if not args.out:
        args.out = get_default_out_dir(base)
    os.makedirs(args.out, exist_ok=True)
    img_dir = os.path.join(args.out, "images")
    session = make_session(args.cookie)
    img_cache: Dict[str, str] = {}

    formats = [f.strip().lower() for f in args.formats.split(",")]
    print(f"Enumerating archive at {base} ...")
    posts = []
    for post in fetch_archive(session, base, args.limit, args.delay):
        posts.append(post)
        if args.max_posts and len(posts) >= args.max_posts:
            break

    if not posts:
        sys.exit(
            "No posts returned. The API may be unreachable from your network, "
            "or try the *.substack.com domain instead, e.g. "
            "--url https://plotset2.substack.com"
        )
    print(f"Found {len(posts)} posts. Downloading (formats: {', '.join(formats)})...\n")

    csv_path = os.path.join(args.out, "posts.csv")
    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["Date", "Title", "Slug", "Audience", "Likes", "Reshares", "Comments", "URL", "File"])

    index_rows: List[tuple] = []
    for i, meta in enumerate(sorted(posts, key=lambda p: p.get("post_date", ""), reverse=True), 1):
        if args.max_posts and i > args.max_posts:
            print(f"Reached max-posts limit of {args.max_posts}. Stopping.")
            break
        slug = meta.get("slug")
        if not slug:
            continue
        detail = fetch_post(session, base, slug, args.delay) or meta

        detail_copy = detail.copy()
        if args.download_images:
            detail_copy["body_html"] = localize_html_images(
                session, detail.get("body_html", ""), img_dir, args.delay, img_cache
            )

        date = (detail.get("post_date") or meta.get("post_date") or "")[:10]
        base_name = f"{date}_{slugify(slug)}".lstrip("_")
        
        # Select primary representative filename for posts.csv and index.md
        primary_fname = ""
        if "pdf" in formats:
            primary_fname = f"{base_name}.pdf"
        elif "md" in formats:
            primary_fname = f"{base_name}.md"
        elif "html" in formats:
            primary_fname = f"{base_name}.html"
        elif "json" in formats:
            primary_fname = f"{base_name}.json"
        else:
            primary_fname = f"{base_name}.pdf"

        # Generate files based on formats
        if "pdf" in formats:
            generate_pdf(meta, detail_copy, args.out, f"{base_name}.pdf")
            
        if "md" in formats:
            md = post_to_markdown(meta, detail_copy)
            with open(os.path.join(args.out, f"{base_name}.md"), "w", encoding="utf-8") as f:
                f.write(md)
                
        if "html" in formats:
            generate_html(meta, detail_copy, args.out, f"{base_name}.html")
            
        if "json" in formats:
            generate_json(meta, detail_copy, args.out, f"{base_name}.json")

        title = detail.get("title") or meta.get("title") or slug
        likes = detail.get("reaction_count") or meta.get("reaction_count") or 0
        reshares = detail.get("restacks") or meta.get("restacks") or 0
        comments = detail.get("comment_count") or meta.get("comment_count") or 0

        csv_writer.writerow([
            date,
            title,
            slug,
            detail.get("audience") or meta.get("audience") or "everyone",
            likes,
            reshares,
            comments,
            detail.get("canonical_url") or meta.get("canonical_url") or "",
            primary_fname
        ])

        index_rows.append((date, title, primary_fname, likes, reshares, comments))
        print(f"[{i}/{len(posts)}] {date}  {title[:60]}")
        time.sleep(args.delay)

    csv_file.close()

    # write an index
    with open(os.path.join(args.out, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Archive index\n\n")
        f.write(f"Download the complete metadata and engagement stats as a [CSV file](./posts.csv).\n\n")
        f.write("| Date | Title | Likes | Reshares | Comments | File |\n|---|---|---|---|---|---|\n")
        for date, title, fname, likes, reshares, comments in index_rows:
            safe = title.replace("|", "\\|")
            f.write(f"| {date} | {safe} | {likes} | {reshares} | {comments} | [{fname}](./{fname}) |\n")

    print(f"\nDone. {len(index_rows)} files written to {args.out}")
    if args.download_images:
        n = len([x for x in img_cache.values() if x])
        print(f"Images downloaded: {n} -> {img_dir}")


if __name__ == "__main__":
    main()
