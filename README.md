# Substack Scraper & Archiver

A clean, robust, and general-purpose Python utility to archive any Substack publication (using standard subdomains like `*.substack.com` or custom domains) into a local folder of self-contained Markdown files, downloaded images, and a comprehensive engagement CSV database.

---

## Features

- 📂 **Auto-Directory Setup**: Automatically extracts the publication name from the URL to create a clean, dedicated output directory (e.g., `plotset2_md/`).
- 📝 **Markdown Conversion**: Uses `markdownify` to convert the raw HTML body of each article into clean Markdown format with standard header formatting.
- 🖼️ **Local Image Hosting**: Parses and downloads all inline post images locally, rewriting image URLs in the Markdown files to point to relative local paths (`images/<hash>.<ext>`) for a completely self-contained offline archive.
- 📊 **Engagement Metadata CSV**: Automatically extracts and logs publication statistics—**Likes** (`reaction_count`), **Reshares** (`restacks`), and **Comments** (`comment_count`)—into a `posts.csv` file for easy sorting and data analysis.
- 🔗 **Linked Markdown Index**: Generates an `index.md` listing every scraped post by date with direct links to the local files and showing their engagement metrics.
- 🍪 **Paywall Preview Mode**: Free posts are archived in full. Paywalled posts are saved as public previews with a YAML header notification (unless a session cookie is supplied via `--cookie`).
- 🛡️ **Robust Pagination & Backoff**: Bypasses common pagination issues by dynamically paging through offsets until the feed is fully exhausted, combined with exponential backoff for network safety.

---

## Quick Start

### 1. Install Dependencies
Ensure you have Python 3.x installed, then install the required dependencies:
```bash
pip install requests markdownify
```

### 2. Basic Scrape
Scrape the entire public archive of a Substack. For example, to scrape the `plotset2` demo Substack:
```bash
python3 scrape_substack.py --url https://plotset2.substack.com/ --download-images
```
This command will:
1. Automatically detect the subdomain name and create an output directory named `./plotset2_md/`.
2. Page through and download all 14 articles.
3. Download all 10 inline images to `./plotset2_md/images/` and update references in the articles.
4. Export the metadata and engagement metrics of all articles to `./plotset2_md/posts.csv`.
5. Generate an archive catalog at `./plotset2_md/index.md`.

---

## CLI Options

| Option | Default | Description |
| :--- | :--- | :--- |
| `--url` | `https://killercharts.blog` | Base URL of the Substack publication. Supports custom domains and `*.substack.com`. |
| `--out` | *Auto-generated* | Directory to save files (e.g., `./plotset2_md`). Defaults to URL subdomain name. |
| `--limit` | `50` | Number of posts to fetch per API request (Substack pagination batch size). |
| `--delay` | `1.0` | Number of seconds to wait between HTTP requests (keep it polite). |
| `--cookie` | `""` | Logged-in session cookie string (to fetch full text for paid posts you own). |
| `--download-images`| *Disabled* | Flag to download inline images locally and rewrite Markdown image links. |
| `--max-posts` | *None* | Limit the total number of articles to download (useful for quick testing). |

---

## Technical Details

Substack publications serve content dynamically using their platform API. This script bypasses heavy page-scrapers by querying the structured endpoints directly:
1. **Archive Fetch**: It fetches metadata from `/api/v1/archive?sort=new&search=&offset=<offset>&limit=<limit>`.
2. **Post Details**: For each post, it grabs the full HTML representation via `/api/v1/posts/<slug>`.
3. **Pagination Handling**: Because Substack does not guarantee that every non-final page returns exactly `limit` items (e.g., if pinned posts are separated), this scraper steps through offsets dynamically based on the length of the returned batch and continues until the API returns an empty list, ensuring no older posts are skipped.

---

## Paywalled Posts
If you are a paid subscriber and want to download the full content of articles behind a paywall that you have access to:
1. Log into the publication on your web browser.
2. Open DevTools (F12) -> **Network** tab.
3. Click any request to the site and copy the value of the `cookie:` request header.
4. Pass that string to the script:
   ```bash
   python3 scrape_substack.py --url https://plotset2.substack.com/ --download-images --cookie "substack.sid=...; other=..."
   ```

---

## License
MIT License. Created for personal archiving and data analysis.
