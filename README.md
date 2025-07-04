# 🚀 Advanced YouTube Live Streamer Pro

Professional live streaming application built with Streamlit and FFmpeg for YouTube Live streaming.

## ✨ Features

### Core Streaming Features
- 🎥 **Multi-format Video Support**: MP4, FLV, MOV, AVI, MKV, WebM
- 🔑 **Secure Stream Key Management**: Encrypted storage and management
- 📺 **Multiple Resolutions**: Original, 1080p, 720p, 480p
- 🔄 **YouTube Shorts Mode**: Automatic 9:16 aspect ratio optimization
- 📡 **Customizable Bitrate**: 500-8000 kbps range
- 🎮 **Real-time Controls**: Start, stop, emergency stop

### Advanced Features
- 💾 **Configuration Management**: Save and reuse streaming setups
- 📊 **Live Statistics**: Real-time FPS, bitrate, and frame monitoring
- 📈 **Analytics Dashboard**: Stream history and performance metrics
- 📁 **File Manager**: Built-in video file management
- 🔧 **Advanced Settings**: Encoding presets, audio bitrate, auto-restart
- 📋 **Live Logging**: Real-time FFmpeg output monitoring

### Data Persistence
- 🗄️ **SQLite Database**: Persistent storage for all configurations
- 💾 **Session Management**: No data loss on page refresh
- 📊 **History Tracking**: Complete streaming history with analytics
- ⚙️ **Settings Persistence**: User preferences saved automatically

### Professional UI/UX
- 🎨 **Modern Interface**: Clean, professional design
- 📱 **Responsive Layout**: Works on all screen sizes
- 🔄 **Real-time Updates**: Live status and statistics
- 🎛️ **Intuitive Controls**: Easy-to-use interface

## 🚀 Quick Start

### Prerequisites
- Python 3.7+
- FFmpeg installed and accessible in PATH
- YouTube Live streaming enabled on your channel

### Installation

1. **Clone or download the project**
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   streamlit run app.py
   ```

4. **Access the web interface**:
   - Open your browser to `http://localhost:8501`

### First Time Setup

1. **Get YouTube Stream Key**:
   - Go to YouTube Studio
   - Click "Go Live"
   - Copy your stream key

2. **Upload or Select Video**:
   - Use the file manager to upload videos
   - Or select from existing files

3. **Configure Stream**:
   - Enter your stream key
   - Select video file
   - Choose resolution and bitrate
   - Enable Shorts mode if needed

4. **Start Streaming**:
   - Click "Start Streaming"
   - Monitor live statistics
   - View logs in real-time

## 📊 Features Overview

### Stream Control Center
- Video selection and upload
- Stream configuration
- Live statistics monitoring
- Real-time logging
- Emergency controls

### Configuration Management
- Save streaming setups
- Quick-load configurations
- Template management
- Bulk configuration operations

### Analytics Dashboard
- Stream history tracking
- Performance metrics
- Duration analysis
- Success rate monitoring
- Visual charts and graphs

### File Manager
- Video file browser
- Upload management
- File information display
- Video preview
- Cleanup tools

### Settings
- Default preferences
- Database management
- Export/import functionality
- System information
- Advanced options

## 🔧 Technical Details

### Database Schema
- **stream_configs**: Saved streaming configurations
- **stream_history**: Complete streaming history
- **app_settings**: User preferences and settings

### FFmpeg Integration
- Automatic process management
- Real-time output parsing
- Statistics extraction
- Error handling and recovery

### Security Features
- Encrypted stream key storage
- Secure configuration management
- Safe file operations
- Process isolation

## 📈 Performance Optimization

### Recommended Settings
- **1080p Streaming**: 4000-6000 kbps bitrate
- **720p Streaming**: 2500-4000 kbps bitrate
- **480p Streaming**: 1000-2500 kbps bitrate
- **Shorts Mode**: 2500-4000 kbps bitrate

### System Requirements
- **CPU**: Multi-core processor (4+ cores recommended)
- **RAM**: 4GB+ available memory
- **Network**: Stable upload bandwidth (2x bitrate minimum)
- **Storage**: Sufficient space for video files

## 🛠️ Troubleshooting

### Common Issues

**FFmpeg Not Found**:
- Install FFmpeg: `https://ffmpeg.org/download.html`
- Add to system PATH
- Restart application

**Stream Won't Start**:
- Check stream key validity
- Verify video file format
- Check network connectivity
- Review logs for errors

**Poor Stream Quality**:
- Reduce bitrate
- Lower resolution
- Check network bandwidth
- Adjust encoding preset

**Database Issues**:
- Use "Reset Database" in settings
- Check file permissions
- Restart application

## 📝 Tips for Best Results

1. **Test your setup** with a short video first
2. **Monitor bandwidth** usage during streaming
3. **Use wired connection** for stability
4. **Keep backup configurations** for different scenarios
5. **Regular cleanup** of old video files
6. **Monitor system resources** during streaming

## 🔄 Updates and Maintenance

- Configuration data persists across updates
- Database automatically upgrades schema
- Settings preserved during application restart
- Stream history maintained indefinitely

## 📞 Support

For issues and feature requests:
1. Check the troubleshooting section
2. Review system information in settings
3. Check FFmpeg installation and configuration
4. Verify YouTube Live streaming permissions

---

made nididchy with ❤️ using Streamlit and FFmpeg
