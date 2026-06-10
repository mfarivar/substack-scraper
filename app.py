import os
import sys
import json
import csv
import subprocess
import threading
import time
from urllib.parse import urlparse

# If running as a PyInstaller executable, configure SSL CA bundle paths to use certifi
if getattr(sys, 'frozen', False):
    try:
        import certifi
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
        os.environ['SSL_CERT_FILE'] = certifi.where()
    except Exception as e:
        print("Error configuring certifi bundle paths:", e)

# Ensure common macOS executable directories are in the PATH.
paths_to_add = ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin']
current_path = os.environ.get('PATH', '')
for path_dir in paths_to_add:
    if path_dir not in current_path:
        current_path = path_dir + os.pathsep + current_path
os.environ['PATH'] = current_path

import webview
import requests
from bs4 import BeautifulSoup

# Import scraping engines from scrape_substack.py
from scrape_substack import (
    fetch_archive,
    fetch_post,
    post_to_markdown,
    localize_html_images,
    get_default_out_dir,
    make_session,
    slugify,
    generate_pdf,
    generate_html,
    generate_json
)

class StackFlowAPI:
    def __init__(self):
        self.window = None
        self._cancelled = False
        self._scrape_thread = None

    def set_window(self, window):
        self.window = window

    def resize_window(self, height):
        """Dynamically resize the window height to fit content."""
        if self.window:
            h = max(420, min(int(height), 700))
            try:
                w = self.window.width
            except Exception:
                w = 840
            self.window.resize(w, h)

    def get_substack_info(self, url):
        """Fetch Substack publication metadata (title, description, logo) from its homepage."""
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                )
            }
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                return {'error': f"Failed to connect to publication (HTTP {r.status_code})"}
            
            soup = BeautifulSoup(r.text, 'html.parser')
            title_meta = soup.find("meta", property="og:title")
            title = title_meta.get("content") if title_meta else None
            if not title:
                title = soup.find("title").text if soup.find("title") else "Substack Publication"
            
            desc_meta = soup.find("meta", property="og:description")
            description = desc_meta.get("content") if desc_meta else "No description provided."
            
            logo = None
            icon_tags = soup.find_all("link", rel=lambda x: x and any(y in x.lower() for y in ["icon", "apple-touch-icon"]))
            for tag in icon_tags:
                href = tag.get("href")
                if href and ("logo" in href or "favicon" in href or "apple-touch-icon" in href):
                    logo = href
                    break
            if not logo:
                og_image = soup.find("meta", property="og:image")
                logo = og_image.get("content") if og_image else "logo.png"
                
            return {
                'title': title,
                'description': description,
                'logo': logo
            }
        except Exception as e:
            return {'error': str(e)}

    def start_scrape(self, url, download_images, delay, cookie, max_posts, formats="pdf"):
        """Starts the scraping process in a background thread."""
        if self._scrape_thread and self._scrape_thread.is_alive():
            print("Warning: Scraping is already in progress.")
            return False
        self._cancelled = False
        self._scrape_thread = threading.Thread(
            target=self._scrape_worker,
            args=(url, download_images, delay, cookie, max_posts, formats),
            daemon=True
        )
        self._scrape_thread.start()
        return True

    def cancel_scrape(self):
        """Signals the active scraping thread to cancel."""
        self._cancelled = True
        return True

    def get_download_folder(self):
        """Loads configured download folder, defaulting to ~/Downloads."""
        config_file = os.path.expanduser('~/.stackflow_config.json')
        default_folder = os.path.expanduser('~/Downloads')
        if not os.path.exists(config_file):
            return default_folder
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('download_folder', default_folder)
        except Exception:
            return default_folder

    def _save_download_folder(self, folder_path):
        """Saves configured download folder to local config."""
        config_file = os.path.expanduser('~/.stackflow_config.json')
        try:
            config = {}
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            config['download_folder'] = folder_path
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def select_download_folder(self):
        """Opens native directory picker dialog."""
        if not self.window:
            return None
        current_dir = self.get_download_folder()
        result = self.window.create_file_dialog(dialog_type=20, directory=current_dir)
        if result and len(result) > 0:
            chosen_path = result[0]
            self._save_download_folder(chosen_path)
            return chosen_path
        return None

    def get_history(self):
        """Loads and returns archive history from config file."""
        history_file = os.path.expanduser('~/.stackflow_history.json')
        if not os.path.exists(history_file):
            return []
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def _add_to_history(self, title, filename, filepath, url):
        """Helper to append a successful scrape to history."""
        history_file = os.path.expanduser('~/.stackflow_history.json')
        history = []
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                pass
        
        new_item = {
            'id': str(time.time()),
            'title': title,
            'filename': filename,
            'filepath': filepath,
            'url': url,
            'timestamp': int(time.time())
        }
        history.insert(0, new_item)
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def remove_from_history(self, item_id):
        """Removes a single item from archive history."""
        history_file = os.path.expanduser('~/.stackflow_history.json')
        if not os.path.exists(history_file):
            return False
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            history = [item for item in history if item.get('id') != item_id]
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def clear_history(self):
        """Clears all history logs."""
        history_file = os.path.expanduser('~/.stackflow_history.json')
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump([], f, indent=2)
            return True
        except Exception:
            return False

    def get_clipboard(self):
        """Reads macOS clipboard text natively via pbpaste."""
        try:
            result = subprocess.run(['pbpaste'], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception:
            return ""

    def reveal_in_finder(self, filepath):
        """Opens parent folder and highlights the file/directory in Finder."""
        if os.path.exists(filepath):
            subprocess.run(["open", "-R", filepath])
            return True
        else:
            parent_dir = os.path.dirname(filepath)
            if os.path.exists(parent_dir):
                subprocess.run(["open", parent_dir])
                return True
        return False

    def _scrape_worker(self, url, download_images, delay, cookie, max_posts, formats="pdf"):
        session = make_session(cookie)
        try:
            base = url.rstrip("/")
            downloads_dir = self.get_download_folder()
            
            # Substack default directory name (e.g. plotset2_md)
            out_folder_name = get_default_out_dir(base).lstrip("./")
            out_dir = os.path.join(downloads_dir, out_folder_name)
            os.makedirs(out_dir, exist_ok=True)
            img_dir = os.path.join(out_dir, "images")
            
            img_cache = {}
            formats_list = [f.strip().lower() for f in formats.split(",")]
            
            self.window.evaluate_js("window.updateStatusText('Enumerating publication archive...')")
            
            # Fetch all metadata of posts
            posts = []
            for post in fetch_archive(session, base, limit=50, delay=delay):
                if self._cancelled:
                    self.window.evaluate_js("window.updateProgress(0, '0%', 'Cancelled')")
                    return
                posts.append(post)
                if max_posts and len(posts) >= max_posts:
                    break
                    
            if not posts:
                import scrape_substack
                api_err = scrape_substack.LAST_API_ERROR or "No articles returned from Substack archive API."
                err_msg = f"Scraping failed: {api_err}"
                self.window.evaluate_js(f"window.scrapeFailed({json.dumps(err_msg)})")
                return
                
            total_items = len(posts)
            index_rows = []
            csv_path = os.path.join(out_dir, "posts.csv")
            
            # Write CSV file
            with open(csv_path, "w", newline="", encoding="utf-8") as csv_file:
                csv_writer = csv.writer(csv_file)
                csv_writer.writerow(["Date", "Title", "Slug", "Audience", "Likes", "Reshares", "Comments", "URL", "File"])
                
                for idx, meta in enumerate(sorted(posts, key=lambda p: p.get("post_date", ""), reverse=True)):
                    if self._cancelled:
                        self.window.evaluate_js("window.updateProgress(0, '0%', 'Cancelled')")
                        return
                        
                    current_idx = idx + 1
                    slug = meta.get("slug")
                    if not slug:
                        continue
                        
                    title = meta.get("title") or slug
                    status_text = f"Fetching post: {title[:40]}..."
                    self.window.evaluate_js(f"window.updateStatusText({json.dumps(status_text)})")
                    
                    # Fetch details
                    detail = fetch_post(session, base, slug, delay) or meta
                    detail_copy = detail.copy()
                    
                    if download_images:
                        status_text = f"Localizing images for: {title[:30]}..."
                        self.window.evaluate_js(f"window.updateStatusText({json.dumps(status_text)})")
                        detail_copy["body_html"] = localize_html_images(
                            session, detail.get("body_html", ""), img_dir, delay, img_cache
                        )
                        
                    date = (detail.get("post_date") or meta.get("post_date") or "")[:10]
                    base_name = f"{date}_{slugify(slug)}".lstrip("_")
                    
                    # Select primary representative filename for posts.csv and index.md
                    primary_fname = ""
                    if "pdf" in formats_list:
                        primary_fname = f"{base_name}.pdf"
                    elif "md" in formats_list:
                        primary_fname = f"{base_name}.md"
                    elif "html" in formats_list:
                        primary_fname = f"{base_name}.html"
                    elif "json" in formats_list:
                        primary_fname = f"{base_name}.json"
                    else:
                        primary_fname = f"{base_name}.pdf"

                    # Generate files based on formats
                    if "pdf" in formats_list:
                        generate_pdf(meta, detail_copy, out_dir, f"{base_name}.pdf")
                        
                    if "md" in formats_list:
                        md = post_to_markdown(meta, detail_copy)
                        with open(os.path.join(out_dir, f"{base_name}.md"), "w", encoding="utf-8") as f:
                            f.write(md)
                            
                    if "html" in formats_list:
                        generate_html(meta, detail_copy, out_dir, f"{base_name}.html")
                        
                    if "json" in formats_list:
                        generate_json(meta, detail_copy, out_dir, f"{base_name}.json")
                        
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
                    
                    # Calculate progress
                    percent = int((current_idx / total_items) * 100)
                    speed_str = f"Archived {current_idx} of {total_items}"
                    eta_str = f"Remaining: {total_items - current_idx}"
                    self.window.evaluate_js(
                        f"window.updateProgress({percent}, {json.dumps(speed_str)}, {json.dumps(eta_str)}, {current_idx}, {total_items})"
                    )
                    time.sleep(delay)
                    
            # Write index.md
            with open(os.path.join(out_dir, "index.md"), "w", encoding="utf-8") as f:
                f.write("# Archive index\n\n")
                f.write(f"Download the complete metadata and engagement stats as a [CSV file](./posts.csv).\n\n")
                f.write("| Date | Title | Likes | Reshares | Comments | File |\n|---|---|---|---|---|---|\n")
                for date, title, fname, likes, reshares, comments in index_rows:
                    safe = title.replace("|", "\\|")
                    f.write(f"| {date} | {safe} | {likes} | {reshares} | {comments} | [{fname}](./{fname}) |\n")
                    
            # Add to history
            pub_info = self.get_substack_info(url)
            pub_title = pub_info.get("title") if (pub_info and not pub_info.get("error")) else out_folder_name.replace("_md", "").replace("-", " ").title()
            
            self._add_to_history(pub_title, out_folder_name, out_dir, url)
            
            success_msg = f"Archived {total_items} posts successfully!"
            self.window.evaluate_js(f"window.scrapeComplete({json.dumps(out_dir)}, {json.dumps(success_msg)})")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.window.scrapeFailed(f"Unexpected error: {str(e)}")
        finally:
            session.close()


def main():
    # Resolve static web directory path
    if hasattr(sys, '_MEIPASS'):
        web_dir = os.path.join(sys._MEIPASS, 'web')
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        web_dir = os.path.join(current_dir, 'web')
        
    html_file = os.path.join(web_dir, 'index.html')

    api = StackFlowAPI()
    
    # Create the native macOS desktop window
    window = webview.create_window(
        title='StackFlow Archiver',
        url=html_file,
        js_api=api,
        width=840,
        height=480,
        min_size=(680, 420),
        resizable=True,
        background_color='#0d0e12'
    )
    
    api.set_window(window)
    webview.start(debug=False)


if __name__ == '__main__':
    main()
