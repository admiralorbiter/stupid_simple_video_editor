console.log('Video Editor JS loaded');

class VideoEditor {
    static instance = null;

    constructor() {
        // Singleton pattern to maintain state
        if (VideoEditor.instance) {
            return VideoEditor.instance;
        }
        VideoEditor.instance = this;

        // Wait for elements to exist
        const initializeInterval = setInterval(() => {
            const videoPlayer = document.getElementById('videoPlayer');
            const timelineSlider = document.querySelector('.timeline-slider');
            
            if (videoPlayer && timelineSlider) {
                clearInterval(initializeInterval);
                this.videoPlayer = videoPlayer;
                this.timelineSlider = timelineSlider;
                this.segments = this.segments || [];  // Maintain existing segments if they exist
                this.isDragging = false;
                this.currentSegment = null;
                this.isSelecting = false;
                this.selectionStart = null;
                
                this.initializeEventListeners();
                this.initializeTimeMarkers();
                this.updateSegmentsList(); // Update UI with current segments
                console.log('Video Editor initialized with segments:', this.segments);
            }
        }, 100);
    }

    initializeEventListeners() {
        // Video events
        this.videoPlayer.addEventListener('loadedmetadata', () => {
            this.timelineSlider.max = Math.floor(this.videoPlayer.duration);
            document.querySelector('.total-time').textContent = this.formatTime(this.videoPlayer.duration);
            this.initializeTimeMarkers();
        });

        this.videoPlayer.addEventListener('timeupdate', () => {
            if (!this.isDragging) {
                this.timelineSlider.value = this.videoPlayer.currentTime;
                document.querySelector('.current-time').textContent = this.formatTime(this.videoPlayer.currentTime);
                this.updateTimelineProgress();
            }
        });

        // Timeline controls
        this.timelineSlider.addEventListener('input', (e) => {
            this.isDragging = true;
            document.querySelector('.current-time').textContent = this.formatTime(e.target.value);
            this.updateTimelineProgress();
            this.showTimeTooltip(e);
        });

        this.timelineSlider.addEventListener('change', (e) => {
            this.isDragging = false;
            this.videoPlayer.currentTime = e.target.value;
            this.hideTimeTooltip();
        });

        // Play/Pause button
        document.getElementById('playPauseBtn').addEventListener('click', () => {
            if (this.videoPlayer.paused) {
                this.videoPlayer.play();
            } else {
                this.videoPlayer.pause();
            }
        });

        // Form submission
        const form = document.getElementById('createClipForm');
        if (form) {
            form.removeEventListener('submit', this.handleSubmit); // Remove existing listener
            form.addEventListener('submit', this.handleSubmit.bind(this)); // Bind to instance
        }

        // Add timeline click/drag events for segment selection
        this.timelineSlider.addEventListener('mousedown', (e) => {
            this.isSelecting = true;
            this.selectionStart = this.getTimeFromPosition(e);
            this.showSelectionOverlay(e);
        });

        document.addEventListener('mousemove', (e) => {
            if (this.isSelecting) {
                this.updateSelectionOverlay(e);
            }
        });

        document.addEventListener('mouseup', (e) => {
            if (this.isSelecting) {
                this.isSelecting = false;
                const overlay = document.querySelector('.selection-overlay');
                if (overlay) {
                    const startX = parseInt(overlay.style.left);
                    const width = parseInt(overlay.style.width);
                    const endX = startX + width;
                    this.addSegmentFromSelection(startX, endX);
                }
            }
        });
    }

    initializeTimeMarkers() {
        const duration = this.videoPlayer.duration;
        const markersContainer = document.querySelector('.timeline-markers');
        markersContainer.innerHTML = '';

        // Add markers every 30 seconds
        for (let time = 0; time <= duration; time += 30) {
            const marker = document.createElement('div');
            marker.className = 'time-marker';
            marker.style.left = `${(time / duration) * 100}%`;
            marker.setAttribute('data-time', this.formatTime(time));
            markersContainer.appendChild(marker);
        }
    }

    updateTimelineProgress() {
        const progress = (this.timelineSlider.value / this.timelineSlider.max) * 100;
        document.querySelector('.timeline-progress').style.width = `${progress}%`;
    }

    showTimeTooltip(event) {
        const tooltip = document.querySelector('.time-tooltip');
        const rect = this.timelineSlider.getBoundingClientRect();
        const position = (event.clientX - rect.left) / rect.width;
        
        tooltip.style.display = 'block';
        tooltip.style.left = `${position * 100}%`;
        tooltip.textContent = this.formatTime(this.timelineSlider.value);
    }

    hideTimeTooltip() {
        document.querySelector('.time-tooltip').style.display = 'none';
    }

    setSegmentTime(type) {
        const currentTime = this.formatTime(this.videoPlayer.currentTime);
        document.getElementById(`new-segment-${type}`).value = currentTime;
    }

    addSegment(startTime, endTime) {
        // If no arguments provided, get values from input fields
        if (startTime === undefined || endTime === undefined) {
            const startInput = document.getElementById('new-segment-start');
            const endInput = document.getElementById('new-segment-end');
            
            // Convert input times to seconds
            startTime = this.timeToSeconds(startInput.value);
            endTime = this.timeToSeconds(endInput.value);
        }

        // Ensure we have valid numbers
        if (typeof startTime !== 'number' || typeof endTime !== 'number' || 
            isNaN(startTime) || isNaN(endTime)) {
            this.showAlert('Invalid segment times', 'warning');
            return;
        }
        
        // Ensure times are within video bounds
        startTime = Math.max(0, Math.min(startTime, this.videoPlayer.duration));
        endTime = Math.max(0, Math.min(endTime, this.videoPlayer.duration));
        
        // Ensure start is before end
        if (startTime >= endTime) {
            this.showAlert('End time must be after start time', 'warning');
            return;
        }
        
        const segment = {
            start: this.formatTime(startTime),
            end: this.formatTime(endTime),
            startSeconds: startTime,
            endSeconds: endTime
        };

        this.segments.push(segment);
        this.segments.sort((a, b) => a.startSeconds - b.startSeconds);
        console.log('Added segment, current segments:', this.segments); // Debug log
        this.updateSegmentsList();
        this.updateSegmentsVisualization();
        
        // Clear any existing inputs
        const startInput = document.getElementById('new-segment-start');
        const endInput = document.getElementById('new-segment-end');
        if (startInput) startInput.value = '';
        if (endInput) endInput.value = '';
    }

    removeSegment(index) {
        if (index >= 0 && index < this.segments.length) {
            this.segments.splice(index, 1);
            this.updateSegmentsList();
            this.updateSegmentsVisualization();
            this.showAlert('Segment removed', 'success');
        }
    }

    updateSegmentsList() {
        const segmentsList = document.getElementById('segments-list');
        const segmentsCount = document.querySelector('.segments-count');
        
        console.log('Updating segments list:', this.segments); // Debug log
        
        // Update segments count
        segmentsCount.textContent = `${this.segments.length} segments to keep`;
        
        // Clear existing list
        segmentsList.innerHTML = '';
        
        // Add each segment
        this.segments.forEach((segment, index) => {
            const segmentDiv = document.createElement('div');
            segmentDiv.className = 'segment-item p-2 d-flex justify-content-between align-items-center';
            segmentDiv.innerHTML = `
                <span>Keep: ${segment.start} - ${segment.end}</span>
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-primary" onclick="videoEditor.previewSegment(${index})">
                        <i class="bi bi-play-fill"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="videoEditor.removeSegment(${index})">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            `;
            segmentsList.appendChild(segmentDiv);
        });
    }

    updateSegmentsVisualization() {
        const timelineSegments = document.querySelector('.timeline-segments');
        timelineSegments.innerHTML = '';
        
        this.segments.forEach((segment, index) => {
            const startPercent = (segment.startSeconds / this.videoPlayer.duration) * 100;
            const width = ((segment.endSeconds - segment.startSeconds) / this.videoPlayer.duration) * 100;
            
            const segmentEl = document.createElement('div');
            segmentEl.className = 'timeline-segment';
            segmentEl.style.left = `${startPercent}%`;
            segmentEl.style.width = `${width}%`;
            
            segmentEl.innerHTML = `
                <div class="handle handle-left" data-index="${index}" data-type="start"></div>
                <div class="handle handle-right" data-index="${index}" data-type="end"></div>
            `;
            
            timelineSegments.appendChild(segmentEl);
        });
    }

    previewSegment(index) {
        const segment = this.segments[index];
        this.videoPlayer.currentTime = segment.startSeconds;
        this.videoPlayer.play();
        
        const checkEnd = setInterval(() => {
            if (this.videoPlayer.currentTime >= segment.endSeconds) {
                this.videoPlayer.pause();
                clearInterval(checkEnd);
            }
        }, 100);
    }

    // Separate method for handling form submission
    handleSubmit = async (e) => {
        e.preventDefault();
        console.log('Form submitted, current segments:', this.segments);
        
        if (!this.segments || this.segments.length === 0) {
            console.log('No segments found!');
            this.showAlert('Please select at least one segment to keep', 'warning');
            return;
        }

        const formData = new FormData(e.target);
        const segmentsData = {
            type: 'keep',
            segments: this.segments
        };
        console.log('Sending segments data:', segmentsData);
        
        formData.set('segments', JSON.stringify(segmentsData));

        try {
            const response = await fetch('/create-clip', {
                method: 'POST',
                body: formData
            });
            
            console.log('Response status:', response.status);
            const result = await response.json();
            console.log('Response data:', result);
            
            if (result.status === 'success') {
                this.showAlert('Clip created successfully!', 'success');
                setTimeout(() => window.location.reload(), 1500);
            } else {
                this.showAlert(result.message || 'Error creating clip', 'error');
            }
        } catch (error) {
            console.error('Error creating clip:', error);
            this.showAlert('Error creating clip', 'error');
        }
    }

    formatTime(seconds) {
        const pad = (num) => String(num).padStart(2, '0');
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = Math.floor(seconds % 60);
        return `${pad(minutes)}:${pad(remainingSeconds)}`;
    }

    timeToSeconds(timeStr) {
        if (!timeStr) return NaN;
        
        // Handle direct number input
        if (!isNaN(timeStr)) {
            return parseFloat(timeStr);
        }
        
        // Handle MM:SS format
        const parts = timeStr.split(':');
        if (parts.length !== 2) return NaN;
        
        const minutes = parseInt(parts[0], 10);
        const seconds = parseInt(parts[1], 10);
        
        if (isNaN(minutes) || isNaN(seconds)) return NaN;
        
        return minutes * 60 + seconds;
    }

    showAlert(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.segments-container');
        container.insertBefore(alertDiv, container.firstChild);
        
        setTimeout(() => alertDiv.remove(), 3000);
    }

    getTimeFromPosition(event) {
        const rect = this.timelineSlider.getBoundingClientRect();
        const position = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
        const time = position * this.videoPlayer.duration;
        return Math.max(0, Math.min(time, this.videoPlayer.duration));
    }

    showSelectionOverlay(event) {
        const timelineTrack = document.querySelector('.timeline-track');
        const rect = timelineTrack.getBoundingClientRect();
        const overlay = document.createElement('div');
        overlay.className = 'selection-overlay';
        overlay.style.left = `${event.clientX - rect.left}px`;
        overlay.style.width = '0px';
        timelineTrack.appendChild(overlay);
    }

    updateSelectionOverlay(event) {
        const overlay = document.querySelector('.selection-overlay');
        const timelineTrack = document.querySelector('.timeline-track');
        if (overlay && timelineTrack) {
            const rect = timelineTrack.getBoundingClientRect();
            const startX = parseInt(overlay.style.left);
            const currentX = event.clientX - rect.left;
            const width = Math.abs(currentX - startX);
            
            overlay.style.width = `${width}px`;
            if (currentX < startX) {
                overlay.style.left = `${currentX}px`;
            }
        }
    }

    addSegmentFromSelection(startX, endX) {
        const timelineTrack = document.querySelector('.timeline-track');
        const rect = timelineTrack.getBoundingClientRect();
        
        // Convert pixel positions to timeline positions (0 to 1)
        const startPos = Math.max(0, Math.min(1, (startX - rect.left) / rect.width));
        const endPos = Math.max(0, Math.min(1, (endX - rect.left) / rect.width));
        
        // Convert positions to times
        const startTime = startPos * this.videoPlayer.duration;
        const endTime = endPos * this.videoPlayer.duration;
        
        // Add the segment
        this.addSegment(Math.min(startTime, endTime), Math.max(startTime, endTime));
        
        // Remove the selection overlay
        const overlay = document.querySelector('.selection-overlay');
        if (overlay) {
            overlay.remove();
        }
    }
}

// Create global instance
window.videoEditor = window.videoEditor || new VideoEditor();

// Update HTMX handler to maintain instance
document.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id === 'editor-content') {
        console.log('Editor content loaded, reinitializing VideoEditor');
        window.videoEditor = new VideoEditor(); // Will return existing instance
    }
}); 