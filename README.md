# 🧡 StackFlow

[![macOS Support](https://img.shields.io/badge/platform-macOS-blueviolet.svg?style=flat-sq)](https://apple.com)
[![Python Version](https://img.shields.io/badge/python-3.13%2B-blue.svg?style=flat-sq)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-sq)](https://opensource.org/licenses/MIT)
[![Aesthetic: Glassmorphism](https://img.shields.io/badge/design-Glassmorphism-ff6719.svg?style=flat-sq)](https://en.wikipedia.org/wiki/Glassmorphism)

A sleek, high-performance, native macOS desktop client and robust CLI utility for archiving Substack publications into self-contained Markdown files, localizing inline images, and exporting engagement statistics to CSV. Built with a stunning dark-mode glassmorphic interface, it features automatic clipboard monitoring, custom delay control, save folder selection, and a persistent history log.

---

## 📦 Quick Start / Download (macOS)

If you want to try StackFlow immediately without installing Python, dependencies, or compiling the source code:

👉 **[Download StackFlow.dmg (macOS)](https://github.com/mfarivar/substack-scraper/raw/main/releases/StackFlow.dmg)**

1. Double-click the downloaded `StackFlow.dmg` file to open the installer.
2. Drag the **StackFlow** icon into your **Applications** folder.
3. Launch **StackFlow** from your Applications directory.

> [!IMPORTANT]
> **Bypassing macOS Gatekeeper ("Apple could not verify...")**
>
> Since StackFlow is compiled locally and not signed with an Apple Developer Account, macOS Gatekeeper will block execution on the first launch with a warning saying it "could not verify the developer". You can easily bypass this using one of the following methods:
> 
> * **Standard GUI Method**:
>   1. Open your **Applications** folder in Finder.
>   2. **Right-click (or Control-click) StackFlow.app** and select **Open** from the context menu.
>   3. In the dialog that appears, click the **Open** button to authorize and launch the application. This registers a permanent security exception.
> * **Terminal Method**:
>   If you prefer the command line or the GUI method is blocked on newer macOS versions, open your Terminal and run the following command to strip the quarantine attribute:
>   ```bash
>   xattr -cr /Applications/StackFlow.app
>   ```

---

## ⚡ Key Features

* **🚀 Zero-Click Clipboard Monitoring** — Automatically detects Substack URLs in your clipboard when the window gains focus, parsing and pasting them instantly.
* **🖼️ Local Image Hosting** — Parses and downloads all inline post images locally, rewriting image URLs in the Markdown files to point to relative local paths (`images/<hash>.<ext>`) for a completely self-contained offline archive.
* **📊 Engagement Metadata CSV** — Automatically extracts and logs publication statistics—**Likes** (`reaction_count`), **Reshares** (`restacks`), and **Comments** (`comment_count`)—into a `posts.csv` file for easy sorting and data analysis.
* **🔗 Linked Markdown Index** — Generates an `index.md` listing every scraped post by date with direct links to local files and showing their engagement metrics.
* **📂 Custom Save Locations** — Choose your preferred downloads folder. The app remembers your selection across restarts so you don't have to keep selecting it.
* **📜 Persistent Archive History** — Keep a running log of your scraped publications in a sliding sidebar drawer. Includes one-click actions to **Locate in Finder** or remove history items.
* **🍪 Session Cookie Support** — Free posts are archived in full. Paywalled posts are saved as public previews unless a session cookie is supplied, enabling authorized full-text archiving.

---

## 🛠️ Tech Stack

* **Frontend**: Vanilla HTML5, CSS3 (featuring HSL tailored Substack orange colors, backdrop-filters, custom micro-animations), and modern ES6+ Javascript.
* **Backend**: Python 3.13, using the [PyWebView](https://pywebview.flowrl.com/) framework for native macOS Cocoa window rendering.
* **Scraping Engine**: `requests`, `BeautifulSoup` (bs4), and `markdownify` for converting HTML body elements to clean Markdown.

---

## 🚀 Running from Source

### Prerequisites

To run or build the application from source, you will need:
1. **Python 3.13+** installed on your Mac.
2. A virtual environment set up.

### Running the Desktop App

1. **Clone the repository**:
   ```bash
   git clone https://github.com/mfarivar/substack-scraper.git
   cd substack-scraper
   ```

2. **Set up a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install requests beautifulsoup4 markdownify fpdf2 pywebview pyinstaller
   ```

4. **Run the app**:
   ```bash
   python3 app.py
   ```

### Running the CLI Scraper

If you prefer using a command-line interface, you can run the scraper directly:
```bash
python3 scrape_substack.py --url https://plotset2.substack.com/ --download-images --formats pdf,md
```

This command will:
1. Automatically detect the subdomain name and create an output directory named `./plotset2_md/`.
2. Page through and download all articles.
3. Download all inline images to `./plotset2_md/images/` and update references in the articles.
4. Export the metadata and engagement metrics of all articles to `./plotset2_md/posts.csv`.
5. Generate an archive catalog at `./plotset2_md/index.md`.

#### CLI Options

| Option | Default | Description |
| :--- | :--- | :--- |
| `--url` | `https://plotset2.substack.com/` | Base URL of the Substack publication. Supports custom domains and `*.substack.com`. |
| `--out` | *Auto-generated* | Directory to save files (e.g., `./plotset2_md`). Defaults to URL subdomain name. |
| `--limit` | `50` | Number of posts to fetch per API request (Substack pagination batch size). |
| `--delay` | `1.0` | Number of seconds to wait between HTTP requests (be polite). |
| `--cookie` | `""` | Logged-in session cookie string (to fetch full text for paid posts you own). |
| `--download-images`| *Disabled* | Flag to download inline images locally and rewrite Markdown image links. |
| `--max-posts` | *None* | Limit the total number of articles to download (useful for quick testing). |
| `--formats` | `pdf` | Comma-separated list of formats to save: `pdf`, `md`, `html`, `json`. |

---

## 📦 Building the Standalone macOS App (`.app` & `.dmg`)

If you want to package the source files into a compiled desktop application (`.app`) and a distribution installer (`.dmg`), follow these steps:

1. **Generate the ICNS Icon**:
   ```bash
   python3 create_icns.py
   ```

2. **Compile with PyInstaller**:
   ```bash
   .venv/bin/pyinstaller --clean -y StackFlow.spec
   ```
   This will output `StackFlow.app` in the `dist/` directory.

3. **Generate the DMG Installer**:
   ```bash
   .venv/bin/python3 build_dmg.py
   ```
   This will generate **`StackFlow.dmg`** in the `dist/` directory, which you can open and drag-and-drop into your `/Applications` folder.

---

## 🤝 Contributing

Contributions are welcome! If you'd like to improve the UI or optimize the scraper:

1. Fork the Project.
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`).
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the Branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
