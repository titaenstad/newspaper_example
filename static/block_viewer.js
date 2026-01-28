let currentBlock = 0;
let totalBlocks = 0;

async function loadFile() {
    const fileIndex = document.getElementById('fileSelect').value;
    const response = await fetch(`/api/load_file/${fileIndex}`);
    const data = await response.json();
    totalBlocks = data.total_blocks;
    currentBlock = 0;
    loadBlock();
}

async function loadBlock() {
    const response = await fetch(`/api/block/${currentBlock}`);
    const data = await response.json();

    document.getElementById('blockImage').src = 'data:image/png;base64,' + data.image;
    document.getElementById('blockText').textContent = data.text;
    document.getElementById('blockInfo').textContent =
        `Block ${currentBlock + 1} of ${totalBlocks} (${data.id})`;

    document.getElementById('prevBtn').disabled = currentBlock === 0;
    document.getElementById('nextBtn').disabled = currentBlock >= totalBlocks - 1;
}

function navigate(delta) {
    const newIndex = currentBlock + delta;
    if (newIndex >= 0 && newIndex < totalBlocks) {
        currentBlock = newIndex;
        loadBlock();
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') navigate(-1);
    if (e.key === 'ArrowRight') navigate(1);
});

// Initial load
loadFile();
