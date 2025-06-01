import sys
import requests
import keyboard
from threading import Thread

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QMessageBox, QSlider, QTextBrowser, QTextEdit, QFrame
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import Qt, QUrl, QThread, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QBrush, QPixmap, QLinearGradient, QFont, QTextCursor


class KeyListenerThread(QThread):
    toggle_visibility = Signal()

    def run(self):
        keyboard.add_hotkey('right shift', lambda: self.toggle_visibility.emit())
        keyboard.wait()


class ModernMusicPlayer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTLite")
        self.resize(1000, 600)
        self.setMinimumSize(800, 500)
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.api_url = "https://ncm.zhenxin.me"

        # 初始化播放器
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(1.0)  # 默认音量100%

        self.playing = False
        self.current_song = None

        # 初始化UI
        self.init_ui()
        self.init_animations()

        # 连接信号槽
        self.connect_signals()

        # 键盘监听
        self.key_listener = KeyListenerThread()
        self.key_listener.toggle_visibility.connect(self.toggle_visibility)
        self.key_listener.start()

        # 歌词数据
        self.lyrics_data = []
        self.lyric_index = -1
        self.user_is_seeking = False

    def init_ui(self):
        """初始化所有UI组件"""
        # 主布局
        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        self.main_layout.setSpacing(30)

        # 左侧面板 (封面和歌曲信息)
        self.init_left_panel()
        
        # 右侧面板 (搜索框、歌词和控制)
        self.init_right_panel()

        # 设置主布局
        self.setLayout(self.main_layout)

        # 窗口样式
        self.setStyleSheet("""
            QWidget {
                background: transparent;
                color: #f0f0f0;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }
            QLineEdit {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 15px;
                padding: 12px 20px;
                font-size: 16px;
                color: white;
                selection-background-color: rgba(0, 150, 255, 150);
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 15px;
                padding: 10px 20px;
                font-size: 16px;
                color: white;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.05);
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
                background: white;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b4ff, stop:1 #0080ff
                );
                border-radius: 3px;
            }
            QTextEdit {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 15px;
                font-size: 16px;
                color: white;
            }
        """)

    def init_left_panel(self):
        """初始化左侧面板"""
        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")
        left_panel.setStyleSheet("""
            #leftPanel {
                background: rgba(30, 30, 40, 0.5);
                border-radius: 20px;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(20)

        # 封面图
        self.cover_label = QLabel()
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setFixedSize(300, 300)
        self.cover_label.setScaledContents(True)
        self.cover_label.setStyleSheet("""
            background: rgba(0, 0, 0, 0.3);
            border-radius: 15px;
        """)
        
        # 默认封面
        default_cover = QPixmap(300, 300)
        default_cover.fill(QColor(50, 50, 60))
        self.cover_label.setPixmap(default_cover)

        # 歌曲信息
        self.song_label = QLabel("未播放")
        self.song_label.setAlignment(Qt.AlignCenter)
        self.song_label.setStyleSheet("""
            font-size: 22px;
            font-weight: bold;
            color: white;
        """)
        self.song_label.setWordWrap(True)

        # 艺术家信息
        self.artist_label = QLabel("未知艺术家")
        self.artist_label.setAlignment(Qt.AlignCenter)
        self.artist_label.setStyleSheet("""
            font-size: 16px;
            color: rgba(255, 255, 255, 0.7);
        """)

        # 添加到左侧布局
        left_layout.addWidget(self.cover_label)
        left_layout.addWidget(self.song_label)
        left_layout.addWidget(self.artist_label)
        left_layout.addStretch()

        # 添加到主布局
        self.main_layout.addWidget(left_panel, stretch=1)

    def init_right_panel(self):
        """初始化右侧面板"""
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_panel.setStyleSheet("""
            #rightPanel {
                background: rgba(40, 40, 50, 0.5);
                border-radius: 20px;
            }
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(20)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索歌曲、歌手或专辑...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet("font-size: 16px;")

        # 搜索按钮
        self.search_button = QPushButton("搜索")
        self.search_button.setFixedHeight(45)
        self.search_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b4ff, stop:1 #0080ff
                );
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00c4ff, stop:1 #0090ff
                );
            }
        """)

        # 歌词显示
        self.lyrics_display = QTextEdit()
        self.lyrics_display.setReadOnly(True)
        self.lyrics_display.setStyleSheet("""
            font-size: 18px;
            line-height: 1.5;
        """)
        self.lyrics_display = QTextBrowser(self)
        self.lyrics_display.setAlignment(Qt.AlignCenter)
        self.lyrics_display.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lyrics_display.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lyrics_display.setTextInteractionFlags(Qt.NoTextInteraction)

        # 控制面板
        control_panel = QFrame()
        control_panel.setStyleSheet("background: transparent;")
        control_layout = QVBoxLayout(control_panel)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(15)

        # 进度条和时间显示
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(10)
        
        self.time_current = QLabel("00:00")
        self.time_current.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 0.7);")
        self.time_current.setFixedWidth(50)
        
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 100)
        
        self.time_total = QLabel("00:00")
        self.time_total.setStyleSheet("font-size: 14px; color: rgba(255, 255, 255, 0.7);")
        self.time_total.setFixedWidth(50)
        
        progress_layout.addWidget(self.time_current)
        progress_layout.addWidget(self.progress_slider)
        progress_layout.addWidget(self.time_total)

        # 控制按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        button_layout.setAlignment(Qt.AlignCenter)

        # 播放/暂停按钮
        self.play_pause_button = QPushButton()
        self.play_pause_button.setFixedSize(60, 60)
        self.play_pause_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b4ff, stop:1 #0080ff
                );
                border-radius: 30px;
                font-size: 24px;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00c4ff, stop:1 #0090ff
                );
            }
        """)
        self.play_pause_button.setText("▶")

        # 音量控制
        volume_layout = QHBoxLayout()
        volume_layout.setSpacing(10)
        volume_layout.setAlignment(Qt.AlignCenter)
        
        self.volume_button = QPushButton("🔊")
        self.volume_button.setFixedSize(40, 40)
        self.volume_button.setStyleSheet("font-size: 18px;")
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(120)
        
        self.volume_label = QLabel("100%")
        self.volume_label.setStyleSheet("font-size: 14px;")
        self.volume_label.setFixedWidth(40)
        
        volume_layout.addWidget(self.volume_button)
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_label)

        # 添加到控制布局
        button_layout.addWidget(self.play_pause_button)
        control_layout.addLayout(progress_layout)
        control_layout.addLayout(button_layout)
        control_layout.addLayout(volume_layout)

        # 添加到右侧布局
        right_layout.addWidget(self.search_input)
        right_layout.addWidget(self.search_button)
        right_layout.addWidget(self.lyrics_display, stretch=1)
        right_layout.addWidget(control_panel)

        # 添加到主布局
        self.main_layout.addWidget(right_panel, stretch=2)

    def init_animations(self):
        """初始化动画效果"""
        # 封面旋转动画
        self.cover_rotation = 0
        self.cover_animation = QPropertyAnimation(self.cover_label, b"rotation")
        self.cover_animation.setDuration(20000)  # 20秒一圈
        self.cover_animation.setStartValue(0)
        self.cover_animation.setEndValue(360)
        self.cover_animation.setLoopCount(-1)  # 无限循环
        self.cover_animation.setEasingCurve(QEasingCurve.Linear)

        # 按钮悬停动画
        self.button_hover_anim = QPropertyAnimation(self.play_pause_button, b"geometry")
        self.button_hover_anim.setDuration(200)
        self.button_hover_anim.setEasingCurve(QEasingCurve.OutQuad)

    def connect_signals(self):
        """连接所有信号槽"""
        self.search_button.clicked.connect(self.search_and_play)
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.volume_slider.valueChanged.connect(self.update_volume)
        
        self.progress_slider.sliderPressed.connect(self.on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self.on_slider_released)
        self.progress_slider.sliderMoved.connect(self.on_slider_moved)
        
        self.media_player.positionChanged.connect(self.on_position_changed)
        self.media_player.durationChanged.connect(self.on_duration_changed)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)

    def paintEvent(self, event):
        """绘制窗口背景和边框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制半透明背景
        painter.setBrush(QBrush(QColor(20, 20, 30, 220)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 20, 20)
        
        # 绘制边框
        border_gradient = QLinearGradient(0, 0, self.width(), self.height())
        border_gradient.setColorAt(0, QColor(0, 180, 255, 100))
        border_gradient.setColorAt(1, QColor(0, 100, 255, 100))
        
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor(0, 180, 255, 80))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 20, 20)

    def toggle_visibility(self):
        """切换窗口可见性"""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def search_and_play(self):
        """搜索并播放音乐"""
        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "提示", "请输入歌曲名称")
            return

        try:
            # 1. 搜索歌曲
            res = requests.get(f"{self.api_url}/search", params={"keywords": keyword}).json()
            songs = res.get("result", {}).get("songs", [])
            if not songs:
                self.show_message("未找到歌曲", "warning")
                return
            
            # 获取第一首歌曲
            song = songs[0]
            song_id = song["id"]

            # 2. 获取歌曲详情
            detail_res = requests.get(f"{self.api_url}/song/detail", params={"ids": song_id}).json()
            songs_detail = detail_res.get("songs", [])
            if not songs_detail:
                self.show_message("无法获取歌曲详情", "error")
                return
            
            detail = songs_detail[0]
            song_name = detail["name"]
            artist_name = detail["ar"][0]["name"] if detail.get("ar") else "未知艺术家"

            # 3. 获取播放链接
            url_res = requests.get(f"{self.api_url}/song/url", params={"id": song_id}).json()
            song_url = url_res.get("data", [{}])[0].get("url")
            if not song_url:
                self.show_message("无法获取播放链接", "error")
                return

            # 更新UI
            self.song_label.setText(song_name)
            self.artist_label.setText(artist_name)
            
            # 加载封面
            if "al" in detail and "picUrl" in detail["al"]:
                self.load_cover(detail["al"]["picUrl"])
            else:
                self.reset_cover()

            # 加载歌词
            self.load_lyrics(song_id)

            # 播放音乐
            self.media_player.setSource(QUrl(song_url))
            self.media_player.play()
            self.playing = True
            self.play_pause_button.setText("⏸")
            self.cover_animation.start()

        except Exception as e:
            self.show_message(f"请求失败: {str(e)}", "error")

    def load_cover(self, url):
        """加载封面图片"""
        def _load():
            try:
                img_data = requests.get(url).content
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)
                
                # 创建圆形遮罩
                rounded = QPixmap(pixmap.size())
                rounded.fill(Qt.transparent)
                
                painter = QPainter(rounded)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setBrush(QBrush(pixmap))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(pixmap.rect(), 15, 15)
                painter.end()
                
                self.cover_label.setPixmap(rounded)
            except Exception as e:
                print(f"加载封面失败: {e}")
                self.reset_cover()

        Thread(target=_load, daemon=True).start()

    def reset_cover(self):
        """重置封面为默认图片"""
        default_cover = QPixmap(300, 300)
        default_cover.fill(QColor(50, 50, 60))
        self.cover_label.setPixmap(default_cover)

    def load_lyrics(self, song_id):
        """加载歌词"""
        try:
            res = requests.get(f"{self.api_url}/lyric", params={"id": song_id}).json()
            lrc_str = res.get("lrc", {}).get("lyric", "")
            
            if not lrc_str:
                self.lyrics_display.setText("无歌词")
                self.lyrics_data = []
                return

            self.lyrics_data = self.parse_lyrics(lrc_str)
            self.lyric_index = -1
            self.lyrics_display.setText("\n".join([line for _, line in self.lyrics_data]))

        except Exception as e:
            print(f"加载歌词失败: {e}")
            self.lyrics_display.setText("无歌词")
            self.lyrics_data = []

    def parse_lyrics(self, lrc_text):
        """解析歌词文本"""
        import re
        pattern = re.compile(r"\[(\d+):(\d+)\.(\d+)\](.*)")
        lyrics = []
        
        for line in lrc_text.splitlines():
            m = pattern.match(line)
            if m:
                minutes = int(m.group(1))
                seconds = int(m.group(2))
                millis = int(m.group(3))
                text = m.group(4).strip()
                time_sec = minutes * 60 + seconds + millis / 1000
                lyrics.append((time_sec, text))
        
        lyrics.sort(key=lambda x: x[0])
        return lyrics

    def toggle_play_pause(self):
        """切换播放/暂停状态"""
        if self.playing:
            self.media_player.pause()
            self.play_pause_button.setText("▶")
            self.playing = False
            self.cover_animation.pause()
        else:
            self.media_player.play()
            self.play_pause_button.setText("⏸")
            self.playing = True
            self.cover_animation.resume()

    def update_volume(self, value):
        """更新音量"""
        volume = value / 100
        self.audio_output.setVolume(volume)
        self.volume_label.setText(f"{value}%")
        
        # 更新音量按钮图标
        if value == 0:
            self.volume_button.setText("🔇")
        elif value < 30:
            self.volume_button.setText("🔈")
        elif value < 70:
            self.volume_button.setText("🔉")
        else:
            self.volume_button.setText("🔊")

    def on_slider_pressed(self):
        """进度条按下事件"""
        self.user_is_seeking = True

    def on_slider_released(self):
        """进度条释放事件"""
        if self.media_player.duration() > 0:
            new_pos = int(self.media_player.duration() * self.progress_slider.value() / 100)
            self.media_player.setPosition(new_pos)
        self.user_is_seeking = False

    def on_slider_moved(self, value):
        """进度条拖动事件"""
        if self.media_player.duration() > 0:
            pos = int(self.media_player.duration() * value / 100)
            self.time_current.setText(self.format_time(pos))

    def on_position_changed(self, position):
        """播放位置变化事件"""
        if self.user_is_seeking:
            return

        duration = self.media_player.duration()
        if duration > 0:
            # 更新进度条
            self.progress_slider.blockSignals(True)
            self.progress_slider.setValue(int(position / duration * 100))
            self.progress_slider.blockSignals(False)
            
            # 更新时间显示
            self.time_current.setText(self.format_time(position))

        # 更新歌词
        if not self.lyrics_data:
            return

        pos_sec = position / 1000
        index = 0
        for i, (time_sec, _) in enumerate(self.lyrics_data):
            if time_sec > pos_sec:
                break
            index = i

        if index != self.lyric_index:
            self.lyric_index = index
            self.update_lyrics_display()

    def on_duration_changed(self, duration):
        """歌曲时长变化事件"""
        self.time_total.setText(self.format_time(duration))

    def on_playback_state_changed(self, state):
        """播放状态变化事件"""
        if state == QMediaPlayer.PlayingState:
            self.cover_animation.start()
        elif state == QMediaPlayer.PausedState:
            self.cover_animation.pause()
        else:  # StoppedState
            self.cover_animation.stop()
            self.cover_label.setPixmap(self.cover_label.pixmap())  # 重置旋转

    def update_lyrics_display(self):
        if not self.lyrics_data:
            # 没有歌词，垂直居中显示提示文字
            html = """
            div style="display:flex; align-items:center; justify-content:center; height:100%;">
                <span style="color:#888888; font-size:16px;">暂无歌词</span>
            </div>
            """
            self.lyrics_display.setHtml(html)
            return

        if self.lyric_index < 0 or self.lyric_index >= len(self.lyrics_data):
            return

        # 上下各显示2行歌词
        start = max(0, self.lyric_index - 2)
        end = min(len(self.lyrics_data), self.lyric_index + 3)

        display_lines = []
        for i in range(start, end):
            line = self.lyrics_data[i][1]
            if i == self.lyric_index:
                line_html = f"<div style='color:#ffffff; font-size:20px; font-weight:bold; line-height:1.6; margin:0; text-align:center;'>{line}</div>"
            else:
                line_html = f"<div style='color:#cccccc; font-size:16px; line-height:1.4; margin:0; text-align:center;'>{line}</div>"
            display_lines.append(line_html)

        full_html = "<div style='display:flex; flex-direction:column; justify-content:center; height:100%;'>" + "".join(display_lines) + "</div>"
        self.lyrics_display.setHtml(full_html)


        
        # 滚动到当前歌词
        cursor = self.lyrics_display.textCursor()
        cursor.movePosition(QTextCursor.Start)
        for _ in range(self.lyric_index - start):
            cursor.movePosition(QTextCursor.Down)
        self.lyrics_display.setTextCursor(cursor)

    def format_time(self, milliseconds):
        """格式化时间(毫秒 -> MM:SS)"""
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def show_message(self, text, msg_type="info"):
        """显示消息提示"""
        msg = QMessageBox(self)
        msg.setText(text)
        
        if msg_type == "warning":
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("警告")
        elif msg_type == "error":
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("错误")
        else:
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("提示")
        
        msg.exec()

    def mousePressEvent(self, event):
        """鼠标按下事件(用于窗口拖动)"""
        if event.button() == Qt.LeftButton:
            self.offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件(用于窗口拖动)"""
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.offset)
            event.accept()

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        """关闭事件"""
        self.key_listener.terminate()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置应用程序字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    player = ModernMusicPlayer()
    player.show()
    sys.exit(app.exec())