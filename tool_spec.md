# video_clipping_tool_spec.md

# Minimal Web-Based Video Clipping Tool - Technical Overview

This document outlines a proposed tech stack and architecture for a lightweight video clipping tool using the following technologies:

- **HTML/CSS + Bootstrap + HTMX** for the front end  
- **Python + Flask** for the back end  
- **SQLite** for database storage  
- **FFmpeg** for video processing (clipping)  
- Optional: **C++** extensions for advanced performance needs

---

## 1. High-Level Architecture

    User (Browser) -- HTMX Requests --> Flask (Python) -- (Subprocess) --> FFmpeg
                                             |
                                             v
                                        SQLite Database

1. **Front End**  
   - Displays a list of videos, a basic video player, input fields for start and end times, and a “Create Clip” button.  
   - Uses **HTMX** to make asynchronous requests to Flask without a full page reload.

2. **Backend (Flask)**  
   - Receives HTMX requests to create clips.  
   - Calls **FFmpeg** using Python’s `subprocess` module to cut videos at specified start/end times.  
   - Stores metadata (clip name, timestamps, file paths) in an **SQLite** database.

3. **Database (SQLite)**  
   - Tracks imported videos in a `videos` table.  
   - Tracks created clips in a `clips` table (with references to the source video and relevant timestamps).

---

## 2. Core Features

1. **Import and List Videos**  
   - Ability to import raw video files into a known directory.  
   - Store references (file path, title, etc.) in the `videos` table.  
   - Display them on the home page.

2. **Playback and Marking**  
   - HTML5 `<video>` element for playback.  
   - “Set Start” and “Set End” buttons to capture the current timestamp of the video.  
   - Manual override of start/end if the user wants to type a specific timestamp.

3. **Clip Creation**  
   - A form that captures clip name, start time, end time, and references the source video ID.  
   - **HTMX** sends a POST request to `/clip/create`.  
   - Flask calls FFmpeg to create a new clip:
     
         ffmpeg -ss <start> -to <end> -i source.mp4 -c copy output_clip.mp4
     
   - Stores the new clip’s metadata (`clip_name`, `start_time`, `end_time`, `clip_path`) in the `clips` table.

4. **List & Organize Clips**  
   - Display existing clips in a simple table or card layout.  
   - Provide rename or folder/tagging options if needed.

---

## 3. Example Schema

    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        file_path TEXT UNIQUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS clips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER,
        clip_name TEXT,
        start_time REAL,
        end_time REAL,
        clip_path TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (video_id) REFERENCES videos(id)
    );

- **videos**: Stores imported video references.  
- **clips**: Each row represents a created clip from a source video.

---

## 4. Potential Flask Routes

1. **GET `/`**  
   - Lists all imported videos (and optionally some recent clips).

2. **GET `/video/<int:video_id>`**  
   - Displays the selected video in a `<video>` player.  
   - Presents form fields for start/end times and clip name.

3. **POST `/clip/create`**  
   - HTMX POST endpoint.  
   - Extracts form data: `video_id`, `clip_name`, `start_time`, `end_time`.  
   - Calls FFmpeg to create the clip.  
   - Inserts a record into the `clips` table.  
   - Returns an HTML snippet or JSON response to update the UI.

4. **GET `/clips`**  
   - Lists all previously created clips in a simple table.

---

## 5. Front-End Example (HTMX + Bootstrap)

Below is a sample template snippet that can be used for the video detail page, allowing a user to set start/end times and create a clip. Adjust the structure as needed.

    <div class="container">
      <h2>{{ video_title }}</h2>
      <video
        id="videoPlayer"
        controls
        src="{{ url_for('static', filename='videos/' + video_file) }}"
        class="w-100"
        style="max-height:480px;"
      ></video>

      <!-- Clipping Form -->
      <form
        hx-post="/clip/create"
        hx-target="#clipResult"
        method="POST"
        class="mt-3"
      >
        <input type="hidden" name="video_id" value="{{ video_id }}">

        <div class="row mb-2">
          <div class="col">
            <label for="start_time">Start Time:</label>
            <input
              type="text"
              id="start_time"
              name="start_time"
              class="form-control"
              placeholder="00:00 or 00:00:00"
            >
          </div>
          <div class="col-auto d-flex align-items-end">
            <button
              type="button"
              class="btn btn-primary"
              onclick="document.getElementById('start_time').value =
                Math.floor(document.getElementById('videoPlayer').currentTime)"
            >
              Set Start
            </button>
          </div>
        </div>

        <div class="row mb-2">
          <div class="col">
            <label for="end_time">End Time:</label>
            <input
              type="text"
              id="end_time"
              name="end_time"
              class="form-control"
              placeholder="10 or 00:00:10"
            >
          </div>
          <div class="col-auto d-flex align-items-end">
            <button
              type="button"
              class="btn btn-primary"
              onclick="document.getElementById('end_time').value =
                Math.floor(document.getElementById('videoPlayer').currentTime)"
            >
              Set End
            </button>
          </div>
        </div>

        <div class="mb-2">
          <label for="clip_name">Clip Name:</label>
          <input
            type="text"
            id="clip_name"
            name="clip_name"
            class="form-control"
            required
          >
        </div>

        <button type="submit" class="btn btn-success">Create Clip</button>
      </form>

      <!-- HTMX response target for success messages or new clip info -->
      <div id="clipResult" class="mt-3"></div>
    </div>

- The **Set Start** / **Set End** buttons grab the current playback time from the `<video>` element and populate the inputs.  
- **HTMX** handles partial page updates upon the POST to `/clip/create`.

---

## 6. FFmpeg Execution in Python

Below is an example Flask route for creating a clip. It retrieves the source video path from the database, constructs the FFmpeg command, and stores the new clip record in `clips`.

    import subprocess
    from flask import Flask, request, render_template, jsonify
    import sqlite3
    import os
    from datetime import datetime

    app = Flask(__name__)

    @app.route('/clip/create', methods=['POST'])
    def create_clip():
        video_id = request.form.get('video_id')
        clip_name = request.form.get('clip_name')
        start_time = request.form.get('start_time')
        end_time = request.form.get('end_time')

        # Retrieve the source video path from the database
        conn = sqlite3.connect('video.db')
        c = conn.cursor()
        c.execute("SELECT file_path FROM videos WHERE id = ?", (video_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return "Video not found.", 400

        source_path = row[0]

        # Create an output path (unique filename or use clip_name)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f'{clip_name}_{timestamp}.mp4'
        output_path = os.path.join('static', 'clips', output_filename)

        # Build the FFmpeg command
        command = [
            'ffmpeg',
            '-ss', str(start_time),
            '-to', str(end_time),
            '-i', source_path,
            '-c', 'copy',
            output_path
        ]

        # Run the command
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            return f"FFmpeg error: {result.stderr}", 500

        # Insert clip info into database
        conn = sqlite3.connect('video.db')
        c = conn.cursor()
        c.execute("""
            INSERT INTO clips (video_id, clip_name, start_time, end_time, clip_path)
            VALUES (?, ?, ?, ?, ?)
        """, (video_id, clip_name, start_time, end_time, output_path))
        conn.commit()
        conn.close()

        # Return snippet of HTML for HTMX to display
        return f"""
        <div class="alert alert-success">
          Clip '{clip_name}' created successfully!
          <a href="/static/clips/{output_filename}" target="_blank">Open Clip</a>
        </div>
        """

    # ... Additional routes ...

---

## 7. Performance & Offloading

- **Simple Clipping (`-c copy`)**: Generally fast, avoiding re-encoding.  
- **Advanced Needs**: For complex filtering, real-time effects, or frame-precise edits:  
  1. Use FFmpeg’s re-encoding flags directly from Python.  
  2. Write a C++ extension or separate process for performance-critical tasks, then invoke from Flask.
- **Concurrency**: If many clip jobs occur simultaneously, consider adding a background job system (e.g., Celery or RQ).

---

## 8. Additional Considerations

1. **File Organization**  
   - Store original videos in `static/videos/`.  
   - Store clips in `static/clips/`.  
   - Use consistent naming to avoid collisions.

2. **Time Format Parsing**  
   - Users might enter seconds or `HH:MM:SS`.  
   - Add a small utility to standardize user input for FFmpeg.

3. **Thumbnails**  
   - Generate thumbnails for each video or clip with something like:  
     
         ffmpeg -ss <time> -i <video> -vframes 1 -q:v 2 <thumbnail.jpg>

4. **Security**  
   - If exposed on the internet, implement authentication and input validation.  
   - Validate uploaded files.

5. **Cross-Platform**  
   - Python + Flask + FFmpeg can run on Windows, macOS, or Linux with the correct FFmpeg installation.

---

## 9. Summary

This **HTML/CSS + Bootstrap + HTMX, Python/Flask, SQLite, and FFmpeg** stack enables a straightforward solution to import videos, define clips, name them, and store metadata. The core workflow is:

1. User selects a video and plays it in the browser.  
2. Marks start/end times and names the clip.  
3. Submits a request to Flask.  
4. Flask calls FFmpeg to create the clip and stores info in SQLite.  
5. The new clip is displayed immediately via an HTMX partial update.

For **simple cutting**, performance is generally good. If you need more advanced editing or real-time capabilities, you can integrate re-encoding or C++ extensions for specialized tasks.
