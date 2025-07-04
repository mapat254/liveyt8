import sys
import subprocess
import threading
import time
import os
import json
import sqlite3
from datetime import datetime, timedelta
import streamlit.components.v1 as components
import pandas as pd
from pathlib import Path
import queue
import signal

# Install required packages
try:
    import streamlit as st
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit", "pandas"])
    import streamlit as st

class StreamingDatabase:
    def __init__(self):
        self.db_path = "streaming_data.db"
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stream_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                stream_key TEXT,
                video_path TEXT,
                is_shorts BOOLEAN,
                bitrate INTEGER,
                resolution TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stream_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_name TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT,
                duration INTEGER,
                video_path TEXT,
                stream_key_hash TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stream_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message TEXT,
                log_type TEXT DEFAULT 'INFO'
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_config(self, name, config):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO stream_configs 
            (name, stream_key, video_path, is_shorts, bitrate, resolution)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, config['stream_key'], config['video_path'], 
              config['is_shorts'], config['bitrate'], config['resolution']))
        conn.commit()
        conn.close()
    
    def load_configs(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM stream_configs ORDER BY created_at DESC')
        configs = cursor.fetchall()
        conn.close()
        return configs
    
    def delete_config(self, name):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM stream_configs WHERE name = ?', (name,))
        conn.commit()
        conn.close()
    
    def save_stream_history(self, config_name, start_time, end_time, status, video_path, stream_key):
        duration = int((end_time - start_time).total_seconds()) if end_time else 0
        stream_key_hash = str(hash(stream_key))[:8] if stream_key else ""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO stream_history 
            (config_name, start_time, end_time, status, duration, video_path, stream_key_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (config_name, start_time, end_time, status, duration, video_path, stream_key_hash))
        conn.commit()
        conn.close()
    
    def get_stream_history(self, limit=50):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM stream_history 
            ORDER BY start_time DESC LIMIT ?
        ''', (limit,))
        history = cursor.fetchall()
        conn.close()
        return history
    
    def save_setting(self, key, value):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()
        conn.close()
    
    def get_setting(self, key, default=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM app_settings WHERE key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else default
    
    def save_log(self, message, log_type='INFO'):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO stream_logs (message, log_type)
            VALUES (?, ?)
        ''', (message, log_type))
        conn.commit()
        conn.close()
    
    def get_logs(self, limit=100):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, message, log_type FROM stream_logs 
            ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))
        logs = cursor.fetchall()
        conn.close()
        return logs
    
    def clear_logs(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM stream_logs')
        conn.commit()
        conn.close()

class StreamingProcess:
    def __init__(self, db):
        self.db = db
        self.process = None
        self.is_running = False
        self.stats = {
            'frames_processed': 0,
            'bitrate': 0,
            'fps': 0,
            'size': 0
        }
        self.log_queue = queue.Queue()
        self.stats_queue = queue.Queue()
    
    def log_message(self, message, log_type='INFO'):
        """Thread-safe logging"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.db.save_log(log_entry, log_type)
        self.log_queue.put(log_entry)
    
    def parse_ffmpeg_output(self, line):
        """Parse FFmpeg output for statistics"""
        if "frame=" in line and "fps=" in line and "bitrate=" in line:
            try:
                parts = line.split()
                stats_update = {}
                for part in parts:
                    if part.startswith("frame="):
                        stats_update['frames_processed'] = int(part.split("=")[1])
                    elif part.startswith("fps="):
                        stats_update['fps'] = float(part.split("=")[1])
                    elif part.startswith("bitrate="):
                        bitrate_str = part.split("=")[1]
                        if "kbits/s" in bitrate_str:
                            stats_update['bitrate'] = float(bitrate_str.replace("kbits/s", ""))
                    elif part.startswith("size="):
                        stats_update['size'] = part.split("=")[1]
                
                if stats_update:
                    self.stats.update(stats_update)
                    self.stats_queue.put(self.stats.copy())
            except Exception as e:
                self.log_message(f"Error parsing FFmpeg output: {e}", 'ERROR')
    
    def run_ffmpeg_stream(self, config):
        """Run FFmpeg streaming in separate thread"""
        try:
            output_url = f"rtmp://a.rtmp.youtube.com/live2/{config['stream_key']}"
            
            cmd = [
                "ffmpeg", "-re", "-stream_loop", "-1", "-i", config['video_path'],
                "-c:v", "libx264", "-preset", "veryfast", 
                "-b:v", f"{config['bitrate']}k",
                "-maxrate", f"{config['bitrate']}k", 
                "-bufsize", f"{config['bitrate'] * 2}k",
                "-g", "60", "-keyint_min", "60",
                "-c:a", "aac", "-b:a", "128k",
                "-f", "flv"
            ]
            
            if config['is_shorts']:
                cmd.extend(["-vf", "scale=720:1280"])
            elif config['resolution'] != "original":
                if config['resolution'] == "1080p":
                    cmd.extend(["-vf", "scale=1920:1080"])
                elif config['resolution'] == "720p":
                    cmd.extend(["-vf", "scale=1280:720"])
                elif config['resolution'] == "480p":
                    cmd.extend(["-vf", "scale=854:480"])
            
            cmd.append(output_url)
            
            self.log_message(f"Starting stream: {config.get('name', 'Manual Stream')}")
            self.log_message(f"Video: {config['video_path']}")
            self.log_message(f"Resolution: {config['resolution']}")
            self.log_message(f"Bitrate: {config['bitrate']}k")
            
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True,
                universal_newlines=True,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            self.is_running = True
            
            # Read FFmpeg output
            for line in self.process.stdout:
                if not self.is_running:
                    break
                
                if line.strip():
                    self.parse_ffmpeg_output(line)
                    if "error" in line.lower() or "failed" in line.lower():
                        self.log_message(line.strip(), 'ERROR')
                    else:
                        self.log_message(line.strip(), 'DEBUG')
            
            self.process.wait()
            
        except Exception as e:
            self.log_message(f"Streaming error: {str(e)}", 'ERROR')
        finally:
            self.is_running = False
            self.log_message("Streaming process ended")
    
    def start_stream(self, config):
        """Start streaming process"""
        if self.is_running:
            return False, "Stream already running"
        
        # Start streaming thread
        thread = threading.Thread(
            target=self.run_ffmpeg_stream, 
            args=(config,), 
            daemon=True
        )
        thread.start()
        
        return True, "Stream started successfully"
    
    def stop_stream(self):
        """Stop streaming process"""
        if not self.is_running:
            return False, "No stream running"
        
        self.is_running = False
        
        try:
            if self.process:
                if os.name == 'nt':  # Windows
                    self.process.terminate()
                else:  # Unix/Linux
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                
                # Wait for process to terminate
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        self.process.kill()
                    else:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
        except Exception as e:
            self.log_message(f"Error stopping stream: {e}", 'ERROR')
        
        self.log_message("Stream stopped by user")
        return True, "Stream stopped successfully"
    
    def get_stats(self):
        """Get current streaming statistics"""
        return self.stats.copy()
    
    def get_new_logs(self):
        """Get new log messages"""
        logs = []
        while not self.log_queue.empty():
            try:
                logs.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        return logs
    
    def get_new_stats(self):
        """Get new statistics"""
        stats = None
        while not self.stats_queue.empty():
            try:
                stats = self.stats_queue.get_nowait()
            except queue.Empty:
                break
        return stats

class AdvancedStreamer:
    def __init__(self):
        self.db = StreamingDatabase()
        self.streaming_process = StreamingProcess(self.db)
        self.init_session_state()
    
    def init_session_state(self):
        """Initialize session state with persistent data"""
        if 'streaming_active' not in st.session_state:
            st.session_state['streaming_active'] = False
        if 'stream_start_time' not in st.session_state:
            st.session_state['stream_start_time'] = None
        if 'current_config' not in st.session_state:
            st.session_state['current_config'] = None
        if 'stream_logs' not in st.session_state:
            # Load recent logs from database
            recent_logs = self.db.get_logs(50)
            st.session_state['stream_logs'] = [f"[{log[0]}] {log[1]}" for log in recent_logs]
        if 'stream_stats' not in st.session_state:
            st.session_state['stream_stats'] = {
                'frames_processed': 0,
                'bitrate': 0,
                'fps': 0,
                'size': 0
            }
        if 'last_update' not in st.session_state:
            st.session_state['last_update'] = time.time()
    
    def update_from_process(self):
        """Update session state from streaming process"""
        # Get new logs
        new_logs = self.streaming_process.get_new_logs()
        if new_logs:
            st.session_state['stream_logs'].extend(new_logs)
            # Keep only last 100 logs
            if len(st.session_state['stream_logs']) > 100:
                st.session_state['stream_logs'] = st.session_state['stream_logs'][-100:]
        
        # Get new stats
        new_stats = self.streaming_process.get_new_stats()
        if new_stats:
            st.session_state['stream_stats'] = new_stats
        
        # Update streaming status
        st.session_state['streaming_active'] = self.streaming_process.is_running
    
    def start_streaming(self, config):
        """Start streaming"""
        success, message = self.streaming_process.start_stream(config)
        
        if success:
            st.session_state['streaming_active'] = True
            st.session_state['stream_start_time'] = datetime.now()
            st.session_state['current_config'] = config
            
            # Save to database
            self.db.save_stream_history(
                config.get('name', 'Manual Stream'),
                st.session_state['stream_start_time'],
                None,
                'Started',
                config['video_path'],
                config['stream_key']
            )
        
        return success, message
    
    def stop_streaming(self):
        """Stop streaming"""
        success, message = self.streaming_process.stop_stream()
        
        if success and st.session_state['stream_start_time']:
            end_time = datetime.now()
            config = st.session_state.get('current_config', {})
            self.db.save_stream_history(
                config.get('name', 'Manual'),
                st.session_state['stream_start_time'],
                end_time,
                'Stopped',
                config.get('video_path', ''),
                config.get('stream_key', '')
            )
            
            st.session_state['streaming_active'] = False
            st.session_state['stream_start_time'] = None
        
        return success, message

def main():
    st.set_page_config(
        page_title="🚀 Advanced YouTube Live Streamer",
        page_icon="🎥",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize streamer
    if 'streamer' not in st.session_state:
        st.session_state['streamer'] = AdvancedStreamer()
    
    streamer = st.session_state['streamer']
    
    # Update from streaming process
    streamer.update_from_process()
    
    # Custom CSS for better UI
    st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(90deg, #ff0000 0%, #ff4444 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stat-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        border-left: 4px solid #ff0000;
    }
    .status-active {
        background-color: #d4edda;
        color: #155724;
        padding: 0.5rem;
        border-radius: 5px;
        border: 1px solid #c3e6cb;
        text-align: center;
        font-weight: bold;
    }
    .status-inactive {
        background-color: #f8d7da;
        color: #721c24;
        padding: 0.5rem;
        border-radius: 5px;
        border: 1px solid #f5c6cb;
        text-align: center;
        font-weight: bold;
    }
    .log-container {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 5px;
        padding: 1rem;
        max-height: 300px;
        overflow-y: auto;
        font-family: monospace;
        font-size: 12px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Main header
    st.markdown("""
    <div class="main-header">
        <h1>🚀 Advanced YouTube Live Streamer Pro</h1>
        <p>Professional live streaming solution with advanced features</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar for navigation
    with st.sidebar:
        st.title("🎛️ Control Panel")
        
        page = st.selectbox(
            "Select Page",
            ["🎥 Stream Control", "⚙️ Configurations", "📊 Analytics", "📁 File Manager", "🔧 Settings"]
        )
        
        # Stream status indicator
        if st.session_state['streaming_active']:
            st.markdown('<div class="status-active">🔴 LIVE STREAMING</div>', unsafe_allow_html=True)
            if st.session_state['stream_start_time']:
                duration = datetime.now() - st.session_state['stream_start_time']
                st.write(f"⏱️ Duration: {str(duration).split('.')[0]}")
        else:
            st.markdown('<div class="status-inactive">⭕ OFFLINE</div>', unsafe_allow_html=True)
        
        # Auto-refresh toggle
        auto_refresh = st.checkbox("🔄 Auto Refresh (5s)", value=True)
        
        if auto_refresh and st.session_state['streaming_active']:
            time.sleep(5)
            st.rerun()
    
    # Main content based on selected page
    if page == "🎥 Stream Control":
        show_stream_control(streamer)
    elif page == "⚙️ Configurations":
        show_configurations(streamer)
    elif page == "📊 Analytics":
        show_analytics(streamer)
    elif page == "📁 File Manager":
        show_file_manager(streamer)
    elif page == "🔧 Settings":
        show_settings(streamer)

def show_stream_control(streamer):
    st.header("🎥 Live Stream Control Center")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Video selection
        st.subheader("📹 Video Selection")
        
        video_files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.flv', '.mov', '.avi', '.mkv', '.webm'))]
        
        tab1, tab2 = st.tabs(["📂 Existing Videos", "⬆️ Upload New"])
        
        with tab1:
            if video_files:
                selected_video = st.selectbox("Select video file:", video_files)
                if selected_video:
                    file_size = os.path.getsize(selected_video) / (1024*1024)
                    st.info(f"📁 File: {selected_video} ({file_size:.2f} MB)")
            else:
                st.warning("No video files found in current directory")
                selected_video = None
        
        with tab2:
            uploaded_file = st.file_uploader(
                "Upload video file", 
                type=['mp4', 'flv', 'mov', 'avi', 'mkv', 'webm'],
                help="Supported formats: MP4, FLV, MOV, AVI, MKV, WebM"
            )
            
            if uploaded_file:
                with open(uploaded_file.name, "wb") as f:
                    f.write(uploaded_file.read())
                st.success(f"✅ Video uploaded: {uploaded_file.name}")
                selected_video = uploaded_file.name
            else:
                selected_video = st.session_state.get('selected_video')
        
        # Stream configuration
        st.subheader("⚙️ Stream Configuration")
        
        col_config1, col_config2 = st.columns(2)
        
        with col_config1:
            stream_key = st.text_input(
                "🔑 YouTube Stream Key", 
                type="password",
                value=streamer.db.get_setting('last_stream_key', ''),
                help="Get this from YouTube Studio > Go Live"
            )
            
            config_name = st.text_input(
                "💾 Configuration Name (optional)",
                placeholder="e.g., 'Gaming Stream Setup'"
            )
        
        with col_config2:
            resolution = st.selectbox(
                "📺 Resolution",
                ["original", "1080p", "720p", "480p"],
                index=1
            )
            
            bitrate = st.slider(
                "📡 Bitrate (kbps)",
                min_value=500,
                max_value=8000,
                value=int(streamer.db.get_setting('default_bitrate', 2500)),
                step=100,
                help="Higher bitrate = better quality but requires more bandwidth"
            )
        
        is_shorts = st.checkbox(
            "🔄 YouTube Shorts Mode (9:16 aspect ratio)",
            help="Optimizes stream for YouTube Shorts format"
        )
        
        # Advanced options
        with st.expander("🔧 Advanced Options"):
            preset = st.selectbox(
                "Encoding Preset",
                ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium"],
                index=2,
                help="Faster presets use less CPU but may reduce quality"
            )
            
            audio_bitrate = st.slider("Audio Bitrate (kbps)", 64, 320, 128, 32)
            
            loop_video = st.checkbox("🔄 Loop Video", value=True)
    
    with col2:
        # Stream statistics
        st.subheader("📊 Live Statistics")
        
        if st.session_state['streaming_active']:
            stats = st.session_state['stream_stats']
            
            st.metric("Frames Processed", stats['frames_processed'])
            st.metric("Current FPS", f"{stats['fps']:.1f}")
            st.metric("Bitrate", f"{stats['bitrate']:.1f} kbps")
            st.metric("Output Size", stats['size'])
        else:
            st.info("🔴 Start streaming to see live statistics")
        
        # Quick actions
        st.subheader("🎮 Quick Actions")
        
        # Control buttons
        if not st.session_state['streaming_active']:
            if st.button("🚀 Start Streaming", type="primary", use_container_width=True):
                if not selected_video or not stream_key:
                    st.error("❌ Please select a video and enter stream key!")
                else:
                    config = {
                        'name': config_name or 'Manual Stream',
                        'video_path': selected_video,
                        'stream_key': stream_key,
                        'is_shorts': is_shorts,
                        'bitrate': bitrate,
                        'resolution': resolution
                    }
                    
                    # Save last used stream key
                    streamer.db.save_setting('last_stream_key', stream_key)
                    
                    # Save configuration if name provided
                    if config_name:
                        streamer.db.save_config(config_name, config)
                    
                    success, message = streamer.start_streaming(config)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                    st.rerun()
        else:
            if st.button("⏹️ Stop Streaming", type="secondary", use_container_width=True):
                success, message = streamer.stop_streaming()
                if success:
                    st.success(message)
                else:
                    st.error(message)
                st.rerun()
        
        # Emergency stop
        if st.button("🚨 Emergency Stop", help="Force stop all streaming processes"):
            try:
                # Kill all ffmpeg processes
                if os.name == 'nt':  # Windows
                    os.system("taskkill /f /im ffmpeg.exe")
                else:  # Unix/Linux
                    os.system("pkill -9 -f ffmpeg")
                
                st.session_state['streaming_active'] = False
                st.warning("Emergency stop executed!")
                st.rerun()
            except Exception as e:
                st.error(f"Emergency stop failed: {e}")
    
    # Stream logs
    st.subheader("📋 Stream Logs")
    
    if st.session_state['stream_logs']:
        # Show logs in a styled container
        logs_text = "\n".join(st.session_state['stream_logs'][-30:])  # Show last 30 logs
        st.markdown(f'<div class="log-container">{logs_text}</div>', unsafe_allow_html=True)
        
        col_log1, col_log2 = st.columns(2)
        with col_log1:
            if st.button("🗑️ Clear Logs"):
                st.session_state['stream_logs'] = []
                streamer.db.clear_logs()
                st.rerun()
        
        with col_log2:
            if st.button("📥 Download Logs"):
                logs_content = "\n".join(st.session_state['stream_logs'])
                st.download_button(
                    "💾 Download",
                    data=logs_content,
                    file_name=f"stream_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )
    else:
        st.info("No logs yet. Start streaming to see logs here.")

def show_configurations(streamer):
    st.header("⚙️ Stream Configurations")
    
    tab1, tab2 = st.tabs(["💾 Saved Configs", "➕ Create New"])
    
    with tab1:
        st.subheader("Saved Configurations")
        
        configs = streamer.db.load_configs()
        
        if configs:
            for config in configs:
                with st.expander(f"🎛️ {config[1]} ({config[7]})"):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"**Video:** {config[3]}")
                        st.write(f"**Resolution:** {config[6]}")
                        st.write(f"**Bitrate:** {config[5]} kbps")
                        st.write(f"**Shorts Mode:** {'Yes' if config[4] else 'No'}")
                    
                    with col2:
                        if st.button(f"🚀 Use Config", key=f"use_{config[0]}"):
                            # Load this configuration for streaming
                            st.session_state['selected_config'] = {
                                'name': config[1],
                                'stream_key': config[2],
                                'video_path': config[3],
                                'is_shorts': config[4],
                                'bitrate': config[5],
                                'resolution': config[6]
                            }
                            st.success(f"Configuration '{config[1]}' loaded!")
                    
                    with col3:
                        if st.button(f"🗑️ Delete", key=f"del_{config[0]}"):
                            streamer.db.delete_config(config[1])
                            st.success("Configuration deleted!")
                            st.rerun()
        else:
            st.info("No saved configurations yet. Create one in the 'Create New' tab.")
    
    with tab2:
        st.subheader("Create New Configuration")
        
        with st.form("new_config_form"):
            config_name = st.text_input("Configuration Name*", placeholder="e.g., 'Gaming Stream HD'")
            
            col1, col2 = st.columns(2)
            
            with col1:
                video_files = [f for f in os.listdir('.') if f.endswith(('.mp4', '.flv', '.mov', '.avi', '.mkv', '.webm'))]
                video_path = st.selectbox("Video File*", video_files if video_files else ["No videos found"])
                resolution = st.selectbox("Resolution", ["original", "1080p", "720p", "480p"])
            
            with col2:
                stream_key = st.text_input("Stream Key*", type="password")
                bitrate = st.slider("Bitrate (kbps)", 500, 8000, 2500, 100)
            
            is_shorts = st.checkbox("YouTube Shorts Mode")
            
            if st.form_submit_button("💾 Save Configuration"):
                if config_name and stream_key and video_path and video_path != "No videos found":
                    config = {
                        'stream_key': stream_key,
                        'video_path': video_path,
                        'is_shorts': is_shorts,
                        'bitrate': bitrate,
                        'resolution': resolution
                    }
                    
                    streamer.db.save_config(config_name, config)
                    st.success(f"✅ Configuration '{config_name}' saved successfully!")
                else:
                    st.error("❌ Please fill in all required fields!")

def show_analytics(streamer):
    st.header("📊 Streaming Analytics")
    
    # Get streaming history
    history = streamer.db.get_stream_history(100)
    
    if history:
        # Convert to DataFrame for easier analysis
        df = pd.DataFrame(history, columns=[
            'ID', 'Config Name', 'Start Time', 'End Time', 'Status', 
            'Duration', 'Video Path', 'Stream Key Hash'
        ])
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_streams = len(df)
            st.metric("Total Streams", total_streams)
        
        with col2:
            total_duration = df['Duration'].sum()
            hours = total_duration // 3600
            minutes = (total_duration % 3600) // 60
            st.metric("Total Duration", f"{hours}h {minutes}m")
        
        with col3:
            completed_streams = len(df[df['Status'] == 'Completed'])
            completion_rate = (completed_streams / total_streams * 100) if total_streams > 0 else 0
            st.metric("Completion Rate", f"{completion_rate:.1f}%")
        
        with col4:
            avg_duration = df['Duration'].mean() if total_streams > 0 else 0
            avg_hours = int(avg_duration // 3600)
            avg_minutes = int((avg_duration % 3600) // 60)
            st.metric("Avg Duration", f"{avg_hours}h {avg_minutes}m")
        
        # Recent streams table
        st.subheader("📈 Recent Streams")
        
        # Display formatted table
        display_df = df[['Config Name', 'Start Time', 'Status', 'Duration', 'Video Path']].copy()
        display_df['Duration'] = display_df['Duration'].apply(
            lambda x: f"{x//3600}h {(x%3600)//60}m {x%60}s" if pd.notnull(x) and x > 0 else "N/A"
        )
        
        st.dataframe(display_df, use_container_width=True)
        
        # Charts
        if len(df) > 1:
            st.subheader("📊 Stream Statistics")
            
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                # Status distribution
                status_counts = df['Status'].value_counts()
                st.bar_chart(status_counts)
                st.caption("Stream Status Distribution")
            
            with col_chart2:
                # Streams over time (last 30 days)
                df['Date'] = pd.to_datetime(df['Start Time']).dt.date
                daily_streams = df.groupby('Date').size()
                st.line_chart(daily_streams)
                st.caption("Daily Stream Count")
    
    else:
        st.info("📈 No streaming history yet. Start streaming to see analytics here!")

def show_file_manager(streamer):
    st.header("📁 File Manager")
    
    # Current directory files
    current_dir = os.getcwd()
    st.subheader(f"📂 Current Directory: {current_dir}")
    
    # List all video files
    all_files = os.listdir('.')
    video_files = [f for f in all_files if f.endswith(('.mp4', '.flv', '.mov', '.avi', '.mkv', '.webm'))]
    
    if video_files:
        st.subheader("🎬 Video Files")
        
        for video_file in video_files:
            with st.expander(f"📹 {video_file}"):
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    file_size = os.path.getsize(video_file) / (1024*1024)
                    file_modified = datetime.fromtimestamp(os.path.getmtime(video_file))
                    
                    st.write(f"**Size:** {file_size:.2f} MB")
                    st.write(f"**Modified:** {file_modified.strftime('%Y-%m-%d %H:%M:%S')}")
                
                with col2:
                    if st.button(f"🎥 Preview", key=f"preview_{video_file}"):
                        st.video(video_file)
                
                with col3:
                    if st.button(f"🗑️ Delete", key=f"delete_{video_file}"):
                        try:
                            os.remove(video_file)
                            st.success(f"Deleted {video_file}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting file: {e}")
    
    else:
        st.info("📁 No video files found in current directory")
    
    # Upload new files
    st.subheader("⬆️ Upload Video Files")
    
    uploaded_files = st.file_uploader(
        "Choose video files",
        type=['mp4', 'flv', 'mov', 'avi', 'mkv', 'webm'],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            with open(uploaded_file.name, "wb") as f:
                f.write(uploaded_file.read())
            st.success(f"✅ Uploaded: {uploaded_file.name}")
        
        if st.button("🔄 Refresh File List"):
            st.rerun()

def show_settings(streamer):
    st.header("🔧 Application Settings")
    
    # General settings
    st.subheader("⚙️ General Settings")
    
    with st.form("settings_form"):
        # Default settings
        default_bitrate = st.slider(
            "Default Bitrate (kbps)",
            500, 8000,
            int(streamer.db.get_setting('default_bitrate', 2500)),
            100
        )
        
        default_resolution = st.selectbox(
            "Default Resolution",
            ["original", "1080p", "720p", "480p"],
            index=["original", "1080p", "720p", "480p"].index(
                streamer.db.get_setting('default_resolution', '720p')
            )
        )
        
        auto_restart = st.checkbox(
            "Auto-restart on failure",
            value=streamer.db.get_setting('auto_restart', 'false') == 'true'
        )
        
        log_level = st.selectbox(
            "Log Level",
            ["ERROR", "WARNING", "INFO", "DEBUG"],
            index=["ERROR", "WARNING", "INFO", "DEBUG"].index(
                streamer.db.get_setting('log_level', 'INFO')
            )
        )
        
        if st.form_submit_button("💾 Save Settings"):
            streamer.db.save_setting('default_bitrate', str(default_bitrate))
            streamer.db.save_setting('default_resolution', default_resolution)
            streamer.db.save_setting('auto_restart', str(auto_restart).lower())
            streamer.db.save_setting('log_level', log_level)
            
            st.success("✅ Settings saved successfully!")
    
    # Database management
    st.subheader("🗄️ Database Management")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Export Data"):
            # Export configurations and history
            configs = streamer.db.load_configs()
            history = streamer.db.get_stream_history(1000)
            logs = streamer.db.get_logs(1000)
            
            export_data = {
                'configurations': configs,
                'history': history,
                'logs': logs,
                'exported_at': datetime.now().isoformat()
            }
            
            st.download_button(
                "💾 Download Export",
                data=json.dumps(export_data, indent=2),
                file_name=f"streaming_data_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
    
    with col2:
        if st.button("🗑️ Clear History"):
            if st.checkbox("Confirm clear history"):
                conn = sqlite3.connect(streamer.db.db_path)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM stream_history')
                cursor.execute('DELETE FROM stream_logs')
                conn.commit()
                conn.close()
                st.success("History cleared!")
    
    with col3:
        if st.button("🔄 Reset Database"):
            if st.checkbox("Confirm reset (this will delete everything!)"):
                if os.path.exists(streamer.db.db_path):
                    os.remove(streamer.db.db_path)
                    streamer.db.init_database()
                    st.success("Database reset!")
    
    # System information
    st.subheader("💻 System Information")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Check FFmpeg installation
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                st.success("✅ FFmpeg is installed")
                version_line = result.stdout.split('\n')[0]
                st.info(f"Version: {version_line}")
            else:
                st.error("❌ FFmpeg not found")
        except Exception as e:
            st.error(f"❌ FFmpeg error: {e}")
    
    with col2:
        # Disk space
        try:
            if os.name == 'nt':  # Windows
                import shutil
                total, used, free = shutil.disk_usage('.')
                free_gb = free / (1024**3)
                total_gb = total / (1024**3)
            else:  # Unix/Linux
                disk_usage = os.statvfs('.')
                free_gb = disk_usage.f_frsize * disk_usage.f_bavail / (1024**3)
                total_gb = disk_usage.f_frsize * disk_usage.f_blocks / (1024**3)
            
            st.info(f"💾 Free Space: {free_gb:.2f} GB / {total_gb:.2f} GB")
        except Exception as e:
            st.info(f"💾 Disk space info unavailable: {e}")

if __name__ == '__main__':
    main()
