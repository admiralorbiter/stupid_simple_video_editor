# Illcutyou

A stupid simple video clipping tool built with Flask, HTMX, and FFmpeg.

## Current Features

### Video Management
- ✅ Browse and select video folders
- ✅ Scan and import videos
- ✅ Display video metadata (size, duration)
- ✅ Collapsible sidebar for video library
- ✅ Video playback interface
- ✅ Video thumbnails with lazy loading
- ✅ Thumbnail placeholders during loading
- ✅ Delete/remove videos from library (single or batch)

### Organization
- ✅ Create and manage folders
- ✅ Nested folder hierarchy
- ✅ Create and manage tags with custom colors
- ✅ Drag and drop tags onto videos
- ✅ Move videos to folders via modal interface
- ✅ Visual folder tree with collapsible sections
- ✅ Batch video organization
- ✅ Tag counts and video counts
- ✅ Context menus for folder management
- ✅ Folder state persistence
- ✅ Video preview in folder tree
- ✅ Smooth folder transitions
- ✅ Folder search/filter
- ✅ Tag search/filter
- ✅ Tag categories
- ✅ Folder reordering


### Clipping
- ✅ Set clip start/end times
- ✅ Name and create clips
- ✅ Custom output folder selection
- ✅ FFmpeg integration for clip creation
- ✅ Direct video serving
- ✅ List of created clips
- ✅ Clip management (delete individual/batch)
- ✅ Clips organized by source video
- ✅ Clip thumbnails
- ✅ Clip undo (individual deletes)
- ✅ Undo batch deletion
- ✅ Clip preview before creation
- ✅ Clip renaming
- ✅ Clip search/filter
- ✅ Multi-segment removal (remove ads/unwanted sections)
- ✅ Preview segments before removal
- ✅ Add/remove multiple segments
- [Bug] Multi segment removal not currently working

### UI/UX
- ✅ Bootstrap styling
- ✅ HTMX for dynamic updates
- ✅ Success/error messages
- ✅ Responsive layout
- ✅ Batch selection interface
- ✅ Confirmation dialogs
- ✅ Improved text contrast and readability
- ✅ Loading states and indicators
- ✅ Smooth transitions and animations
- ✅ Drag and drop interactions
- ✅ Interactive folder tree
- ✅ Modal dialogs for organization
- ✅ Enhanced Timeline Visualization
- ✅ Drag-and-drop segment adjustment
- ✅ Color-coded segment markers
- ✅ Progress bar when creating clips and scanning videos


## Bugs

- [Bug] Clip playback not working
- [Bug] Clip thumbnail not showing

## Missing Features

### Advanced Features for Production
- ❌ Transcoding options
- ❌ Background task queue
- ❌ Waveform visualization

## Setup

1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

2. Install FFmpeg:
   - Windows: Download from ffmpeg.org
   - Linux: `sudo apt install ffmpeg`
   - macOS: `brew install ffmpeg`

3. Run the application:
   ```bash
   python app.py
   ```

## Usage

1. Click "Browse Folder" to select a folder containing videos
2. Click "Set Clips Folder" to choose where clips will be saved
3. Select a video from the library
4. Use the video player to find start/end points
5. Enter a clip name and create your clip
6. Manage your clips in the Clips Library:
   - View all clips or filter by source video
   - Delete individual clips or select multiple for batch deletion
   - View clip thumbnails for easy identification
7. Manage your video library:
   - Delete individual or multiple videos using the trash icon
   - Select videos to delete with checkbox interface
   - Confirm deletion with a simple click
8. Organize your videos:
   - Create folders and subfolders
   - Create tags with custom colors
   - Drag and drop tags onto videos
   - Move videos to folders using the modal interface
   - Use context menus for folder management

## Tech Stack

- Frontend: HTML, Bootstrap, HTMX, JavaScript
- Backend: Python, Flask
- Database: SQLite
- Video Processing: FFmpeg

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.