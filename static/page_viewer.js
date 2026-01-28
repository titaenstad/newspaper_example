let currentIndex = 0;
let totalPages = 0;
let zoomLevel = 100;
let lastScrollPercent = { x: 0, y: 0 };
let cachedPageData = null;

const leftPanel = document.getElementById('leftPanel');
const rightPanel = document.getElementById('rightPanel');

// Track scroll position continuously
rightPanel.addEventListener('scroll', () => {
    const maxScrollX = rightPanel.scrollWidth - rightPanel.clientWidth;
    const maxScrollY = rightPanel.scrollHeight - rightPanel.clientHeight;
    if (maxScrollX > 0 || maxScrollY > 0) {
        lastScrollPercent.x = maxScrollX > 0 ? rightPanel.scrollLeft / maxScrollX : 0;
        lastScrollPercent.y = maxScrollY > 0 ? rightPanel.scrollTop / maxScrollY : 0;
    }
});

function adjustZoom(delta) {
    const newZoom = zoomLevel + delta * 25;
    if (newZoom >= 25 && newZoom <= 400) {
        zoomLevel = newZoom;
        document.getElementById('zoomLevel').textContent = zoomLevel + '%';
        loadPage(currentIndex, { scrollXPercent: lastScrollPercent.x, scrollYPercent: lastScrollPercent.y });
    }
}

function getVisibilityParams() {
    return {
        composedBlock: document.getElementById('showComposedBlock').checked,
        illustration: document.getElementById('showIllustration').checked,
        textLine: document.getElementById('showTextLine').checked,
        string: document.getElementById('showString').checked
    };
}

function updateOverlays() {
    // Just update overlays without reloading image
    if (!cachedPageData) return;
    const vis = getVisibilityParams();
    const data = cachedPageData;

    // Save scroll positions
    const scrollTop = rightPanel.scrollTop;
    const scrollLeft = rightPanel.scrollLeft;

    // Update left pane overlay
    const leftOverlay = leftPanel.querySelector('.left-overlay');
    if (leftOverlay) {
        let leftBoxes = '';
        if (vis.composedBlock) {
            for (const block of data.composed_blocks) {
                leftBoxes += `<div class="left-composed-block" style="left:${block.x}px;top:${block.y}px;width:${block.width}px;height:${block.height}px;"></div>`;
            }
        }
        if (vis.illustration) {
            for (const ill of data.illustrations) {
                leftBoxes += `<div class="left-illustration" style="left:${ill.x}px;top:${ill.y}px;width:${ill.width}px;height:${ill.height}px;"></div>`;
            }
        }
        if (vis.textLine) {
            for (const line of data.lines) {
                leftBoxes += `<div class="left-text-line" style="left:${line.x}px;top:${line.y}px;width:${line.width}px;height:${line.height}px;"></div>`;
            }
        }
        if (vis.string) {
            for (const box of data.boxes) {
                leftBoxes += `<div class="left-string" style="left:${box.x}px;top:${box.y}px;width:${box.width}px;height:${box.height}px;"></div>`;
            }
        }
        leftOverlay.innerHTML = leftBoxes;
    }

    // Update right pane
    const rightOverlay = rightPanel.querySelector('.text-overlay');
    if (rightOverlay) {
        let textHtml = '';
        if (vis.composedBlock) {
            for (const block of data.composed_blocks) {
                textHtml += `<div class="composed-block" style="left:${block.x}px;top:${block.y}px;width:${block.width}px;height:${block.height}px;"></div>`;
            }
        }
        if (vis.illustration) {
            for (const ill of data.illustrations) {
                textHtml += `<div class="illustration" style="left:${ill.x}px;top:${ill.y}px;width:${ill.width}px;height:${ill.height}px;"></div>`;
            }
        }
        if (vis.textLine) {
            for (const line of data.lines) {
                textHtml += `<div class="text-line" style="left:${line.x}px;top:${line.y}px;width:${line.width}px;height:${line.height}px;"></div>`;
            }
        }
        for (const box of data.boxes) {
            const fontSize = Math.max(8, Math.floor(box.height * 0.7));
            const borderStyle = vis.string ? '1px dashed blue' : 'none';
            textHtml += `<div class="text-box" style="left:${box.x}px;top:${box.y}px;width:${box.width}px;height:${box.height}px;font-size:${fontSize}px;border:${borderStyle};">${escapeHtml(box.content)}</div>`;
        }
        rightOverlay.innerHTML = textHtml;
    }

    // Restore scroll positions
    requestAnimationFrame(() => {
        rightPanel.scrollTop = scrollTop;
        rightPanel.scrollLeft = scrollLeft;
        leftPanel.scrollTop = scrollTop;
        leftPanel.scrollLeft = scrollLeft;
    });
}

// Synchronized scrolling
let syncing = false;

leftPanel.addEventListener('scroll', () => {
    if (syncing) return;
    syncing = true;
    rightPanel.scrollTop = leftPanel.scrollTop;
    rightPanel.scrollLeft = leftPanel.scrollLeft;
    syncing = false;
});

rightPanel.addEventListener('scroll', () => {
    if (syncing) return;
    syncing = true;
    leftPanel.scrollTop = rightPanel.scrollTop;
    leftPanel.scrollLeft = rightPanel.scrollLeft;
    syncing = false;
});

// Keyboard navigation
document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') navigate(-1);
    if (e.key === 'ArrowRight') navigate(1);
});

async function loadPage(index, restoreScroll = null) {
    currentIndex = index;

    // Update navigation
    document.getElementById('prevBtn').disabled = currentIndex <= 0;
    document.getElementById('nextBtn').disabled = currentIndex >= totalPages - 1;

    // Show loading
    leftPanel.innerHTML = '<div class="loading">Loading...</div>';
    rightPanel.innerHTML = '<div class="loading">Loading...</div>';

    try {
        // Get page data
        const vis = getVisibilityParams();
        const response = await fetch(`/api/page/${index}?zoom=${zoomLevel}`);
        const data = await response.json();

        if (data.error) {
            leftPanel.innerHTML = `<div class="loading">${data.error}</div>`;
            rightPanel.innerHTML = `<div class="loading">${data.error}</div>`;
            return;
        }

        cachedPageData = data;
        totalPages = data.total_pages;
        document.getElementById('pageInfo').textContent =
            `Page ${currentIndex + 1} of ${totalPages}: ${data.filename}`;

        // Load left panel (image with overlay boxes)
        let leftHtml = `
            <div class="canvas-container" style="position: relative;">
                <div class="loading" id="imageLoading">Image is rendering...</div>
                <img src="/api/image/${index}?zoom=${zoomLevel}" alt="Page image" style="display:none">
                <div class="left-overlay" style="width: ${data.display_width}px; height: ${data.display_height}px;">
        `;
        // ComposedBlock boxes (orange solid)
        if (vis.composedBlock) {
            for (const block of data.composed_blocks) {
                leftHtml += `<div class="left-composed-block" style="left:${block.x}px;top:${block.y}px;width:${block.width}px;height:${block.height}px;"></div>`;
            }
        }
        // Illustration boxes (magenta solid)
        if (vis.illustration) {
            for (const ill of data.illustrations) {
                leftHtml += `<div class="left-illustration" style="left:${ill.x}px;top:${ill.y}px;width:${ill.width}px;height:${ill.height}px;"></div>`;
            }
        }
        // TextLine boxes (green solid)
        if (vis.textLine) {
            for (const line of data.lines) {
                leftHtml += `<div class="left-text-line" style="left:${line.x}px;top:${line.y}px;width:${line.width}px;height:${line.height}px;"></div>`;
            }
        }
        // String boxes (blue solid)
        if (vis.string) {
            for (const box of data.boxes) {
                leftHtml += `<div class="left-string" style="left:${box.x}px;top:${box.y}px;width:${box.width}px;height:${box.height}px;"></div>`;
            }
        }
        leftHtml += '</div></div>';
        leftPanel.innerHTML = leftHtml;

        // Show image when loaded and sync scroll with right pane
        const img = leftPanel.querySelector('img');
        img.onload = () => {
            document.getElementById('imageLoading').style.display = 'none';
            img.style.display = 'block';
            // Sync left pane scroll to match right pane
            leftPanel.scrollTop = rightPanel.scrollTop;
            leftPanel.scrollLeft = rightPanel.scrollLeft;
        };

        // Load right panel (all bounding boxes)
        let textHtml = `<div class="text-overlay" style="width: ${data.display_width}px; height: ${data.display_height}px; position: relative;">`;
        // Draw ComposedBlock boxes first (orange dashed, background)
        if (vis.composedBlock) {
            for (const block of data.composed_blocks) {
                textHtml += `
                    <div class="composed-block" style="
                        left: ${block.x}px;
                        top: ${block.y}px;
                        width: ${block.width}px;
                        height: ${block.height}px;
                    "></div>
                `;
            }
        }
        // Draw Illustration boxes (magenta)
        if (vis.illustration) {
            for (const ill of data.illustrations) {
                textHtml += `
                    <div class="illustration" style="
                        left: ${ill.x}px;
                        top: ${ill.y}px;
                        width: ${ill.width}px;
                        height: ${ill.height}px;
                    "></div>
                `;
            }
        }
        // Draw TextLine boxes (green)
        if (vis.textLine) {
            for (const line of data.lines) {
                textHtml += `
                    <div class="text-line" style="
                        left: ${line.x}px;
                        top: ${line.y}px;
                        width: ${line.width}px;
                        height: ${line.height}px;
                    "></div>
                `;
            }
        }
        // Draw String boxes on top (blue) - always show text, border is optional
        for (const box of data.boxes) {
            const fontSize = Math.max(8, Math.floor(box.height * 0.7));
            const borderStyle = vis.string ? '1px dashed blue' : 'none';
            textHtml += `
                <div class="text-box" style="
                    left: ${box.x}px;
                    top: ${box.y}px;
                    width: ${box.width}px;
                    height: ${box.height}px;
                    font-size: ${fontSize}px;
                    border: ${borderStyle};
                ">${escapeHtml(box.content)}</div>
            `;
        }
        textHtml += '</div>';
        rightPanel.innerHTML = textHtml;

        // Restore scroll position after right pane renders (it's faster than image)
        if (restoreScroll) {
            requestAnimationFrame(() => {
                const maxScrollX = rightPanel.scrollWidth - rightPanel.clientWidth;
                const maxScrollY = rightPanel.scrollHeight - rightPanel.clientHeight;
                rightPanel.scrollLeft = restoreScroll.scrollXPercent * maxScrollX;
                rightPanel.scrollTop = restoreScroll.scrollYPercent * maxScrollY;
            });
        }

    } catch (err) {
        leftPanel.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
        rightPanel.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function navigate(delta) {
    const newIndex = currentIndex + delta;
    if (newIndex >= 0 && newIndex < totalPages) {
        loadPage(newIndex);
    }
}

// Initial load
fetch('/api/info').then(r => r.json()).then(data => {
    totalPages = data.total_pages;
    if (totalPages > 0) {
        loadPage(0);
    } else {
        document.getElementById('pageInfo').textContent = 'No OCR files found';
        leftPanel.innerHTML = '<div class="loading">No OCR files found. Run unpack.py first.</div>';
        rightPanel.innerHTML = '<div class="loading">No OCR files found. Run unpack.py first.</div>';
    }
});
