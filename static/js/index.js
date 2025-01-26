function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('main-content');
    const toggleBtn = document.querySelector('.sidebar-toggle');
    const toggleIcon = document.getElementById('toggle-icon');
    
    sidebar.classList.toggle('collapsed');
    mainContent.classList.toggle('expanded');
    toggleBtn.classList.toggle('collapsed');
    
    if (sidebar.classList.contains('collapsed')) {
        toggleIcon.classList.replace('bi-chevron-left', 'bi-chevron-right');
    } else {
        toggleIcon.classList.replace('bi-chevron-right', 'bi-chevron-left');
    }
}

function toggleDeleteMode() {
    const deleteBtn = document.getElementById('delete-mode-btn');
    const deleteControls = document.getElementById('delete-controls');
    const isActive = deleteBtn.classList.toggle('active');
    
    if (isActive) {
        deleteControls.classList.remove('hide');
        deleteControls.classList.add('show');
        deleteControls.style.display = 'block';
    } else {
        deleteControls.classList.remove('show');
        deleteControls.classList.add('hide');
        setTimeout(() => {
            deleteControls.style.display = 'none';
        }, 300);
    }
    
    window.toggleSelectionMode(isActive);
}

function cancelDelete() {
    toggleDeleteMode();
}

function confirmDelete() {
    const selectedVideos = document.querySelectorAll('.video-list-item.selected');
    const videoIds = Array.from(selectedVideos).map(el => el.dataset.videoId);
    
    fetch('/delete-videos', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ video_ids: videoIds })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            selectedVideos.forEach(video => {
                video.style.animation = 'fadeOut 0.3s ease forwards';
                setTimeout(() => video.remove(), 300);
            });
            toggleDeleteMode();
        }
    })
    .catch(error => console.error('Error:', error));
}

// Add fadeOut animation styles
document.head.insertAdjacentHTML('beforeend', `
    <style>
        @keyframes fadeOut {
            from { opacity: 1; transform: scale(1); }
            to { opacity: 0; transform: scale(0.9); }
        }
    </style>
`); 