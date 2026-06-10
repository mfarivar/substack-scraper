#!/usr/bin/env python3
"""
scrape_substack.py
==================
Archive an entire Substack publication to local Markdown files.

It walks the publication's archive API to enumerate every post, fetches each
post's full HTML, converts it to Markdown, and writes one file per post with
YAML front-matter. Optionally downloads inline images so the archive is
self-contained.

Works with custom-domain Substacks (e.g. https://killercharts.blog).

------------------------------------------------------------------------------
QUICK START
------------------------------------------------------------------------------
    pip install requests markdownify
    python scrape_substack.py --url https://killercharts.blog --out ./killercharts_md

    # also pull every image down into ./killercharts_md/images and rewrite links:
    python scrape_substack.py --url https://killercharts.blog --download-images

------------------------------------------------------------------------------
PAYWALLED POSTS
------------------------------------------------------------------------------
Free posts are archived in full. Subscriber-only posts return only the public
preview UNLESS you supply your own logged-in session cookie. If you are a paid
subscriber and want the full text of paid posts that *you* can already read:

  1. Log into the publication in your browser.
  2. Open dev-tools -> Network -> click any request to the site.
  3. Copy the entire "cookie:" request header value.
  4. Pass it with --cookie "....":

    python scrape_substack.py --url https://killercharts.blog \
        --cookie "substack.sid=...; other=..."

Only archive content you are entitled to access, and keep copies for personal
use in line with the publication's terms.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

try:
    import requests
    from markdownify import markdownify as html_to_md
except ImportError:
    sys.exit("Missing deps. Run:  pip install requests markdownify")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def slugify(value, fallback="post"):
    value = re.sub(r"[^\w\s-]", "", (value or "")).strip().lower()
    value = re.sub(r"[\s_-]+", "-", value)
    return value[:80] or fallback


def make_session(cookie):
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


def get_json(session, url, delay, retries=4):
    """GET a URL and return parsed JSON, with simple backoff on errors/429/5xx."""
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    print(f"  ! non-JSON response from {url}", file=sys.stderr)
                    return None
            if r.status_code == 404:
                return None
            print(f"  ! HTTP {r.status_code} on {url}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  ! request error ({e}) on {url}", file=sys.stderr)
        time.sleep(delay * (attempt + 2))  # back off
    return None


# --------------------------------------------------------------------------- #
# substack API walking
# --------------------------------------------------------------------------- #
def fetch_archive(session, base, limit, delay):
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


def fetch_post(session, base, slug, delay):
    return get_json(session, f"{base}/api/v1/posts/{slug}", delay)


# --------------------------------------------------------------------------- #
# image handling
# --------------------------------------------------------------------------- #
IMG_MD_RE = re.compile(r"(!\[[^\]]*\]\()(https?://[^)\s]+?)(\s+\"[^\"]*\")?(\))")
EXT_BY_CT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
}


def localize_images(session, markdown, img_dir, delay, cache):
    """Download every image referenced in the markdown and rewrite links to
    point at ./images/<hash>.<ext> (relative to each post file)."""

    def repl(m):
        url = m.group(2)
        if url not in cache:
            cache[url] = _download_one(session, url, img_dir, delay)
        local = cache[url]
        if not local:
            return m.group(0)  # leave original URL on failure
        return f"{m.group(1)}images/{local}{m.group(3) or ''}{m.group(4)}"

    return IMG_MD_RE.sub(repl, markdown)


def _download_one(session, url, img_dir, delay):
    os.makedirs(img_dir, exist_ok=True)
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    # reuse if already on disk
    for existing in os.listdir(img_dir):
        if existing.startswith(h):
            return existing
    try:
        r = session.get(url, timeout=60)
        if r.status_code != 200:
            return None
        ext = EXT_BY_CT.get(r.headers.get("Content-Type", "").split(";")[0].strip())
        if not ext:
            path_ext = os.path.splitext(urlparse(url).path)[1]
            ext = path_ext if path_ext else ".img"
        name = f"{h}{ext}"
        with open(os.path.join(img_dir, name), "wb") as f:
            f.write(r.content)
        time.sleep(delay)
        return name
    except requests.RequestException:
        return None


# --------------------------------------------------------------------------- #
# rendering a post to markdown
# --------------------------------------------------------------------------- #
def yaml_escape(s):
    return '"' + str(s or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def post_to_markdown(meta, detail):
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
# helpers for URL parsing
# --------------------------------------------------------------------------- #
def get_default_out_dir(url):
    parsed = urlparse(url)
    netloc = parsed.netloc or parsed.path
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if netloc.endswith(".substack.com"):
        name = netloc[:-13]
    else:
        parts = netloc.split(".")
        if len(parts) > 1:
            name = parts[-2]
        else:
            name = parts[0]
    return f"./{slugify(name)}_md"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Archive a Substack to Markdown files.")
    ap.add_argument("--url", default="https://killercharts.blog",
                    help="Publication base URL (default: https://killercharts.blog)")
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
    args = ap.parse_args()

    base = args.url.rstrip("/")
    if not args.out:
        args.out = get_default_out_dir(base)
    os.makedirs(args.out, exist_ok=True)
    img_dir = os.path.join(args.out, "images")
    session = make_session(args.cookie)
    img_cache = {}

    print(f"Enumerating archive at {base} ...")
    posts = list(fetch_archive(session, base, args.limit, args.delay))
    if not posts:
        sys.exit(
            "No posts returned. The API may be unreachable from your network, "
            "or try the *.substack.com domain instead, e.g. "
            "--url https://killercharts.substack.com"
        )
    print(f"Found {len(posts)} posts. Downloading...\n")

    csv_path = os.path.join(args.out, "posts.csv")
    csv_file = open(csv_path, "w", newline="", encoding="utf-8")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["Date", "Title", "Slug", "Audience", "Likes", "Reshares", "Comments", "URL", "File"])

    index_rows = []
    for i, meta in enumerate(sorted(posts, key=lambda p: p.get("post_date", ""), reverse=True), 1):
        if args.max_posts and i > args.max_posts:
            print(f"Reached max-posts limit of {args.max_posts}. Stopping.")
            break
        slug = meta.get("slug")
        if not slug:
            continue
        detail = fetch_post(session, base, slug, args.delay) or meta
        md = post_to_markdown(meta, detail)

        if args.download_images:
            md = localize_images(session, md, img_dir, args.delay, img_cache)

        date = (detail.get("post_date") or meta.get("post_date") or "")[:10]
        fname = f"{date}_{slugify(slug)}.md".lstrip("_")
        with open(os.path.join(args.out, fname), "w", encoding="utf-8") as f:
            f.write(md)

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
            fname
        ])

        index_rows.append((date, title, fname, likes, reshares, comments))
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
