// Frontend Javascript for StackFlow Archiver

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const urlInput = document.getElementById('url-input');
  const pasteBtn = document.getElementById('paste-btn');
  const urlError = document.getElementById('url-error');
  
  const pubPreviewCard = document.getElementById('pub-preview-card');
  const pubLogo = document.getElementById('pub-logo');
  const pubTitle = document.getElementById('pub-title');
  const pubDesc = document.getElementById('pub-desc');
  
  const downloadImages = document.getElementById('download-images');
  const delaySlider = document.getElementById('delay-slider');
  const delayValue = document.getElementById('delay-value');
  
  const cookieInput = document.getElementById('cookie-input');
  const maxPostsInput = document.getElementById('max-posts-input');
  
  const downloadBtn = document.getElementById('download-btn');
  const downloadBtnText = document.getElementById('download-btn-text');
  
  const loadingOverlay = document.getElementById('loading-overlay');
  const downloadOverlay = document.getElementById('download-overlay');
  const dlStatusTitle = document.getElementById('dl-status-title');
  const dlStatusFilename = document.getElementById('dl-status-filename');
  const dlProgressFill = document.getElementById('dl-progress-fill');
  const dlProgressPercent = document.getElementById('dl-progress-percent');
  const dlProgressSpeed = document.getElementById('dl-progress-speed');
  const dlProgressEta = document.getElementById('dl-progress-eta');
  const cancelBtn = document.getElementById('cancel-btn');
  
  const completeOverlay = document.getElementById('complete-overlay');
  const successFilename = document.getElementById('success-filename');
  const showFinderBtn = document.getElementById('show-finder-btn');
  const resetBtn = document.getElementById('reset-btn');

  // History Elements
  const historyToggleBtn = document.getElementById('history-toggle-btn');
  const historyDrawer = document.getElementById('history-drawer');
  const closeDrawerBtn = document.getElementById('close-drawer-btn');
  const clearHistoryBtn = document.getElementById('clear-history-btn');
  const historyList = document.getElementById('history-list');
  const historyEmpty = document.getElementById('history-empty');

  // Save Folder Elements
  const changeFolderBtn = document.getElementById('change-folder-btn');
  const folderPathDisplay = document.getElementById('folder-path-display');

  // State
  let activeUrl = "";
  let currentOutputDir = "";

  // Dynamic window sizing — measure content and resize the native window
  function fitWindow() {
    requestAnimationFrame(() => {
      const container = document.querySelector('.app-container');
      const card = document.querySelector('.app-card');
      if (!container || !card) return;

      const origBodyHeight = document.body.style.height;
      const origContainerHeight = container.style.height;
      const origCardFlex = card.style.flex;
      const origCardHeight = card.style.height;
      const origCardOverflow = card.style.overflowY;

      document.body.style.height = 'auto';
      container.style.height = 'auto';
      card.style.flex = 'none';
      card.style.height = 'auto';
      card.style.overflowY = 'visible';

      const contentHeight = container.offsetHeight;

      document.body.style.height = origBodyHeight;
      container.style.height = origContainerHeight;
      card.style.flex = origCardFlex;
      card.style.height = origCardHeight;
      card.style.overflowY = origCardOverflow;

      // Calculate final target window height (add title bar ~28px + small buffer ~16px)
      const targetHeight = contentHeight + 28 + 16;

      if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.resize_window(targetHeight);
      }
    });
  }

  // Update delay value text on slider input
  delaySlider.addEventListener('input', () => {
    delayValue.innerText = `${delaySlider.value}s`;
  });

  // Simple Substack domain detection regex (matches *.substack.com or standard HTTP/S domains)
  const SUBSTACK_REGEX = /^(https?:\/\/)?([a-zA-Z0-9_-]+\.)+[a-zA-Z]{2,}(\/.*)?$/;

  function parseSubstackUrl(text) {
    if (!text) return null;
    const trimmed = text.trim();
    if (trimmed.match(SUBSTACK_REGEX)) {
      // Basic check: starts with http/https or looks like a domain
      return trimmed.startsWith('http') ? trimmed : `https://${trimmed}`;
    }
    return null;
  }

  // Clipboard Paste Handler
  pasteBtn.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      urlInput.value = text;
      urlInput.dispatchEvent(new Event('input'));
    } catch (err) {
      console.warn('Clipboard read failed, focusing input', err);
      urlInput.focus();
    }
  });

  // URL Input listener
  urlInput.addEventListener('input', () => {
    const rawText = urlInput.value;
    const detectedUrl = parseSubstackUrl(rawText);
    
    if (!detectedUrl) {
      if (rawText.trim() === "") {
        urlError.classList.add('hidden');
      } else {
        urlError.innerText = "Please enter a valid Substack URL (e.g. publication.substack.com or custom domain).";
        urlError.classList.remove('hidden');
      }
      resetMetadataState();
      return;
    }
    
    urlError.classList.add('hidden');
    
    if (activeUrl !== detectedUrl) {
      activeUrl = detectedUrl;
      fetchMetadata(activeUrl);
    }
  });

  // Fetch Metadata from Python Backend
  async function fetchMetadata(url) {
    showLoading(true);
    resetMetadataState(false); // don't clear URL input, just clear preview
    
    try {
      if (window.pywebview && window.pywebview.api) {
        const info = await window.pywebview.api.get_substack_info(url);
        if (info && !info.error) {
          pubTitle.innerText = info.title || "Substack Publication";
          pubDesc.innerText = info.description || "No description provided.";
          pubLogo.src = info.logo || "logo.png";
          
          pubPreviewCard.classList.remove('hidden');
          downloadBtn.removeAttribute('disabled');
          fitWindow();
        } else {
          showError(info.error || "Failed to retrieve Substack publication details.");
        }
      } else {
        // Mock fallback for standard browser testing
        setTimeout(() => {
          pubTitle.innerText = "PlotSet Visualization Blog";
          pubDesc.innerText = "Democratizing data visualization stories through interactive and animated charts.";
          pubLogo.src = "logo.png";
          pubPreviewCard.classList.remove('hidden');
          downloadBtn.removeAttribute('disabled');
          fitWindow();
          showLoading(false);
        }, 1000);
        return;
      }
    } catch (err) {
      console.error(err);
      showError("An error occurred connecting to Python backend.");
    }
    showLoading(false);
  }

  function showError(msg) {
    urlError.innerText = msg;
    urlError.classList.remove('hidden');
    resetMetadataState();
  }

  function showLoading(show) {
    if (show) {
      loadingOverlay.classList.remove('hidden');
    } else {
      loadingOverlay.classList.add('hidden');
    }
  }

  // Reset preview states
  function resetMetadataState(clearInput = true) {
    if (clearInput) {
      urlInput.value = "";
      activeUrl = "";
      syncLastClipboardWithoutPaste();
    }
    pubPreviewCard.classList.add('hidden');
    pubLogo.src = "";
    pubTitle.innerText = "";
    pubDesc.innerText = "";
    
    downloadBtn.setAttribute('disabled', 'true');
    fitWindow();
  }

  // Click Download Button
  downloadBtn.addEventListener('click', async () => {
    const images = downloadImages.checked;
    const delay = parseFloat(delaySlider.value);
    const cookie = cookieInput.value.trim();
    
    let maxPosts = null;
    const maxPostsVal = maxPostsInput.value.trim();
    if (maxPostsVal !== "") {
      maxPosts = parseInt(maxPostsVal, 10);
      if (isNaN(maxPosts) || maxPosts <= 0) {
        alert("Please enter a valid positive integer for Max Posts limit.");
        maxPostsInput.focus();
        return;
      }
    }
    
    dlStatusTitle.innerText = "Archiving Substack";
    dlStatusFilename.innerText = `Connecting to ${pubTitle.innerText}...`;
    
    dlProgressFill.style.width = '0%';
    dlProgressPercent.innerText = '0%';
    dlProgressSpeed.innerText = 'Waiting...';
    dlProgressEta.innerText = 'ETA: --:--';
    dlProgressFill.classList.remove('processing-pulse');
    
    downloadOverlay.classList.remove('hidden');
    
    try {
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.start_scrape(activeUrl, images, delay, cookie, maxPosts);
      } else {
        // Mock Progress for browser debugging
        console.log(`Starting mock scrape for: ${activeUrl}, images: ${images}, delay: ${delay}, maxPosts: ${maxPosts}`);
        let currentItem = 1;
        const totalItems = maxPosts || 15;
        
        const interval = setInterval(() => {
          if (currentItem > totalItems) {
            clearInterval(interval);
            window.scrapeComplete("plotset2_md", `Successfully scraped all ${totalItems} articles!`);
            return;
          }
          const pct = Math.round((currentItem / totalItems) * 100);
          window.updateProgress(
            pct, 
            `Scraped ${currentItem} of ${totalItems}`, 
            `Remaining: ${totalItems - currentItem}`, 
            currentItem, 
            totalItems
          );
          currentItem++;
        }, 300);
        
        cancelBtn.onclick = () => {
          clearInterval(interval);
          downloadOverlay.classList.add('hidden');
        };
      }
    } catch (err) {
      console.error("Scraper triggering error: ", err);
      alert("Error starting scraper.");
      downloadOverlay.classList.add('hidden');
    }
  });

  // Cancel Button
  cancelBtn.addEventListener('click', async () => {
    try {
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.cancel_scrape();
      }
    } catch (err) {
      console.error(err);
    }
    downloadOverlay.classList.add('hidden');
  });

  // Show in Finder
  showFinderBtn.addEventListener('click', async () => {
    try {
      if (window.pywebview && window.pywebview.api && currentOutputDir) {
        await window.pywebview.api.reveal_in_finder(currentOutputDir);
      }
    } catch (err) {
      console.error(err);
    }
  });

  // Reset / Scrape Another
  resetBtn.addEventListener('click', () => {
    completeOverlay.classList.add('hidden');
    resetMetadataState(true);
  });

  // Global Callbacks for Python to trigger
  window.updateProgress = function(percent, speedStr, etaStr, currentIdx, totalCount) {
    if (totalCount && totalCount > 0) {
      dlStatusTitle.innerText = `Archiving Articles (${currentIdx} of ${totalCount})`;
    }
    if (percent < 100) {
      dlProgressFill.classList.remove('processing-pulse');
    }
    dlProgressFill.style.width = `${percent}%`;
    dlProgressPercent.innerText = `${percent}%`;
    dlProgressSpeed.innerText = speedStr; // Scraped count description
    dlProgressEta.innerText = etaStr; // ETA or status
  };

  window.updateStatusText = function(statusText) {
    dlStatusFilename.innerText = statusText;
  };

  window.scrapeComplete = function(outputDir, message) {
    currentOutputDir = outputDir;
    downloadOverlay.classList.add('hidden');
    completeOverlay.classList.remove('hidden');
    successFilename.innerText = message;
    loadHistory();
  };

  window.scrapeFailed = function(errorMsg) {
    downloadOverlay.classList.add('hidden');
    alert(`Scraping failed:\n${errorMsg}`);
  };

  // --- Clipboard Monitoring & Auto-Detection ---
  let lastClipboardText = "";

  async function checkClipboard() {
    if (window.pywebview && window.pywebview.api) {
      try {
        const text = await window.pywebview.api.get_clipboard();
        if (text && text.trim() !== "" && text !== lastClipboardText) {
          const detected = parseSubstackUrl(text);
          if (detected) {
            lastClipboardText = text;
            urlInput.value = text;
            urlInput.dispatchEvent(new Event('input'));
          }
        }
      } catch (err) {
        console.error("Clipboard check failed:", err);
      }
    }
  }

  async function syncLastClipboardWithoutPaste() {
    if (window.pywebview && window.pywebview.api) {
      try {
        const text = await window.pywebview.api.get_clipboard();
        lastClipboardText = text;
      } catch (err) {
        console.error(err);
      }
    }
  }

  // Check clipboard when window gains focus
  window.addEventListener('focus', () => {
    checkClipboard();
  });

  // Poll clipboard every 1.5 seconds if window has focus
  setInterval(() => {
    if (document.hasFocus()) {
      checkClipboard();
    }
  }, 1500);

  // Sync clipboard on startup
  setTimeout(syncLastClipboardWithoutPaste, 1000);

  // --- Save Folder Logic ---
  async function initDownloadFolder() {
    try {
      if (window.pywebview && window.pywebview.api) {
        const folder = await window.pywebview.api.get_download_folder();
        updateFolderDisplay(folder);
      } else {
        updateFolderDisplay('/Users/mock/Downloads');
      }
    } catch (err) {
      console.error("Failed to initialize download folder:", err);
    }
  }

  function updateFolderDisplay(folderPath) {
    if (folderPathDisplay) {
      folderPathDisplay.innerText = folderPath;
      folderPathDisplay.title = folderPath;
    }
    const successLoc = document.querySelector('.success-location');
    if (successLoc) {
      successLoc.innerText = `Saved to: ${folderPath}`;
    }
  }

  if (changeFolderBtn) {
    changeFolderBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      try {
        if (window.pywebview && window.pywebview.api) {
          const chosen = await window.pywebview.api.select_download_folder();
          if (chosen) {
            updateFolderDisplay(chosen);
          }
        } else {
          updateFolderDisplay('/Users/mock/CustomFolder');
        }
      } catch (err) {
        console.error("Failed to change download folder:", err);
      }
    });
  }

  // --- History Drawer Logic ---
  historyToggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    historyDrawer.classList.toggle('open');
    if (historyDrawer.classList.contains('open')) {
      loadHistory();
    }
  });

  closeDrawerBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    historyDrawer.classList.remove('open');
  });

  document.addEventListener('click', (e) => {
    if (historyDrawer.classList.contains('open') &&
        !historyDrawer.contains(e.target) &&
        !e.target.closest('#history-toggle-btn')) {
      historyDrawer.classList.remove('open');
    }
  });

  clearHistoryBtn.addEventListener('click', async () => {
    if (confirm('Are you sure you want to clear your archive history?')) {
      if (window.pywebview && window.pywebview.api) {
        await window.pywebview.api.clear_history();
      }
      loadHistory();
    }
  });

  async function loadHistory() {
    try {
      if (window.pywebview && window.pywebview.api) {
        const history = await window.pywebview.api.get_history();
        renderHistoryList(history);
      } else {
        const mockHistory = [
          {
            id: "1",
            title: "PlotSet Visualization Blog",
            filename: "plotset2_md",
            filepath: "/Users/max/Downloads/plotset2_md",
            url: "https://plotset2.substack.com",
            format: "archive",
            timestamp: Math.floor(Date.now() / 1000) - 3600
          }
        ];
        renderHistoryList(mockHistory);
      }
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  }

  function renderHistoryList(history) {
    historyList.innerHTML = "";
    if (!history || history.length === 0) {
      historyEmpty.classList.remove('hidden');
      historyList.classList.add('hidden');
      return;
    }

    historyEmpty.classList.add('hidden');
    historyList.classList.remove('hidden');

    history.forEach(item => {
      const itemEl = document.createElement('div');
      itemEl.className = 'history-item';

      const dateStr = new Date(item.timestamp * 1000).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });

      itemEl.innerHTML = `
        <div class="history-item-info">
          <span class="history-item-title" title="${item.title}">${item.title}</span>
          <div class="history-item-meta">
            <span class="history-item-badge badge-complete">Complete</span>
            <span>${dateStr}</span>
          </div>
        </div>
        <div class="history-item-actions">
          <button class="history-action-btn locate" title="Locate in Finder">
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
            </svg>
          </button>
          <button class="history-action-btn delete" title="Delete from history">
            <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </div>
      `;

      // Locate in Finder Action
      const locateBtn = itemEl.querySelector('.locate');
      locateBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (window.pywebview && window.pywebview.api) {
          const success = await window.pywebview.api.reveal_in_finder(item.filepath);
          if (!success) {
            alert("Could not locate this directory. It may have been moved or deleted.");
          }
        } else {
          alert(`Mock locating: ${item.filename}`);
        }
      });

      // Delete from History list
      const deleteBtn = itemEl.querySelector('.delete');
      deleteBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (window.pywebview && window.pywebview.api) {
          await window.pywebview.api.remove_from_history(item.id);
          loadHistory();
        } else {
          const idx = history.findIndex(i => i.id === item.id);
          if (idx !== -1) history.splice(idx, 1);
          renderHistoryList(history);
        }
      });

      historyList.appendChild(itemEl);
    });
  }

  // Initial load
  if (window.pywebview && window.pywebview.api) {
    loadHistory();
    initDownloadFolder();
    fitWindow();
  } else {
    window.addEventListener('pywebviewready', () => {
      loadHistory();
      initDownloadFolder();
      fitWindow();
    });
  }
});
