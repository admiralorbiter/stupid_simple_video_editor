document.addEventListener('DOMContentLoaded', function() {
    const browseButton = document.getElementById('browse-button');
    const scanButton = document.getElementById('scan-button');
    const selectedFolder = document.getElementById('selected-folder');

    // Move existing folder selection code
    browseButton.addEventListener('click', async function(e) {
        e.preventDefault();
        try {
            const response = await fetch('/browse-folder');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            
            if (data.status === 'success') {
                selectedFolder.querySelector('.folder-path').textContent = data.folder;
                selectedFolder.style.display = 'block';
                scanButton.style.display = 'block';
            } else if (data.status === 'error') {
                console.error('Server error:', data.message);
            }
        } catch (error) {
            console.error('Error selecting folder:', error);
        }
    });

    // Handle scan button click
    scanButton.addEventListener('click', function(e) {
        e.preventDefault();
        const videoList = document.getElementById('video-list');
        
        // Show initial progress bar
        videoList.innerHTML = `
            <div class="progress-container p-4">
                <div class="progress" style="height: 20px;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated"
                         role="progressbar"
                         style="width: 0%"
                         aria-valuenow="0"
                         aria-valuemin="0"
                         aria-valuemax="100">
                        <span class="progress-text">0%</span>
                    </div>
                </div>
                <div class="progress-status text-center mt-2">
                    Initializing scan...
                </div>
            </div>
        `;

        // Start the scan
        fetch('/select-folder', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.total > 0) {
                startProgressUpdates(data.total);
            } else {
                videoList.innerHTML = `
                    <div class="alert alert-warning">
                        No video files found in selected folder.
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error starting scan:', error);
            videoList.innerHTML = `
                <div class="alert alert-danger">
                    Error starting scan. Please try again.
                </div>
            `;
        });
    });

    function startProgressUpdates(total) {
        let processed = 0;
        
        function updateProgress() {
            fetch('/scan-progress', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ processed, total })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                
                const progressBar = document.querySelector('.progress-bar');
                const progressText = document.querySelector('.progress-text');
                const statusText = document.querySelector('.progress-status');
                
                if (data.html) {
                    // Scan complete, update the video list
                    document.getElementById('video-list').innerHTML = data.html;
                    return;
                }
                
                progressBar.style.width = data.progress + '%';
                progressBar.setAttribute('aria-valuenow', data.progress);
                progressText.textContent = data.progress + '%';
                statusText.textContent = data.status;
                
                processed = data.processed;
                if (processed < total) {
                    setTimeout(updateProgress, 500);
                }
            })
            .catch(error => {
                console.error('Error during progress update:', error);
                document.getElementById('video-list').innerHTML = `
                    <div class="alert alert-danger">
                        Error scanning videos. Please try again.
                    </div>
                `;
            });
        }
        
        updateProgress();
    }
}); 