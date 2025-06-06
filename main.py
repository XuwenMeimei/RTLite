import sys
import requests
import keyboard
import base64
import time
from threading import Thread

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QInputDialog,
    QLabel, QMessageBox, QSlider, QTextBrowser, QTextEdit, QFrame, QListWidget, QListWidgetItem, QDialog
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import Qt, QUrl, QThread, Signal, QPropertyAnimation, QEasingCurve, QSize, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush, QPixmap, QLinearGradient, QFont, QTextCursor


class KeyListenerThread(QThread):
    toggle_visibility = Signal()

    def run(self):
        try:
            keyboard.add_hotkey('right shift', self.emit_toggle_signal)
            keyboard.wait()
        except Exception as e:
            print(f"键盘监听错误: {e}")

    def emit_toggle_signal(self):
        # 确保信号在主线程发出
        self.toggle_visibility.emit()


class SongItemWidget(QWidget):
    """自定义歌曲项Widget，显示封面、歌曲信息"""
    def __init__(self, song, api_url, parent=None):
        super().__init__(parent)
        self.song = song
        self.api_url = api_url
        
        # 主布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # 封面标签
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(60, 60)
        self.cover_label.setStyleSheet("""
            background: rgba(0, 0, 0, 0.3);
            border-radius: 5px;
        """)
        self.cover_label.setScaledContents(True)
        
        # 默认封面
        default_cover = QPixmap(60, 60)
        default_cover.fill(QColor(50, 50, 60))
        self.cover_label.setPixmap(default_cover)
        
        # 歌曲信息布局
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)
        
        # 歌曲名
        name = song.get("name", "未知歌曲")
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: white;
        """)
        self.name_label.setMaximumWidth(400)
        
        # 歌手
        artists = ", ".join([ar.get("name", "未知歌手") for ar in song.get("artists", song.get("ar", []))])
        self.artist_label = QLabel(artists)
        self.artist_label.setStyleSheet("""
            font-size: 14px;
            color: rgba(255, 255, 255, 0.7);
        """)
        
        # 添加到信息布局
        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.artist_label)
        info_layout.addStretch()
        
        # 时长
        duration = song.get("duration", 0)  # 单位: 毫秒
        minutes = duration // 60000
        seconds = (duration % 60000) // 1000
        duration_text = f"{minutes}:{seconds:02d}"
        
        self.duration_label = QLabel(duration_text)
        self.duration_label.setStyleSheet("""
            font-size: 14px;
            color: rgba(255, 255, 255, 0.7);
        """)
        self.duration_label.setFixedWidth(50)
        self.duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        # 添加到主布局
        layout.addWidget(self.cover_label)
        layout.addLayout(info_layout)
        layout.addWidget(self.duration_label)
        
        # 异步加载封面
        self.load_cover()
    
    def load_cover(self):
        """异步加载封面图片 - 通过/song/detail接口获取封面"""
        # 获取歌曲ID
        song_id = self.song.get("id")
        if not song_id:
            return
            
        # 启动线程获取歌曲详情
        def _load():
            try:
                # 调用/song/detail接口
                detail_res = requests.get(
                    f"{self.api_url}/song/detail", 
                    params={"ids": song_id}
                ).json()
                
                # 提取封面URL
                songs_detail = detail_res.get("songs", [])
                if not songs_detail:
                    return
                
                song_detail = songs_detail[0]
                cover_url = None
                if "al" in song_detail and "picUrl" in song_detail["al"]:
                    cover_url = song_detail["al"]["picUrl"]
                
                if not cover_url:
                    return
                
                # 加载封面图片
                img_data = requests.get(cover_url).content
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)
                
                # 创建圆形遮罩
                rounded = QPixmap(60, 60)
                rounded.fill(Qt.transparent)
                
                painter = QPainter(rounded)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setBrush(QBrush(pixmap.scaled(60, 60, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(0, 0, 60, 60, 5, 5)
                painter.end()
                
                # 更新UI
                self.cover_label.setPixmap(rounded)
            except Exception as e:
                print(f"加载封面失败: {e}")
        
        Thread(target=_load, daemon=True).start()


class SearchResultsWindow(QWidget):
    """搜索结果独立窗口"""
    def __init__(self, parent, songs, api_url):
        super().__init__()
        self.parent = parent
        self.api_url = api_url
        self.setWindowTitle("搜索结果")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(700, 500)  # 增加宽度以适应更多内容
        self.setMinimumSize(500, 400)
        
        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        self.main_layout.setSpacing(20)
        
        # 标题栏
        self.title_bar = QLabel("搜索结果")
        self.title_bar.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 10px;
                background: transparent;
            }
        """)
        self.title_bar.setAlignment(Qt.AlignCenter)
        
        # 窗口拖动相关变量
        self.drag_position = None
        
        # 搜索结果列表
        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: rgba(50, 50, 60, 0.7);
                border-radius: 15px;
                padding: 10px;
                color: white;
                font-size: 16px;
                border: 1px solid rgba(255, 255, 255, 0.1);
                outline: none;
            }
            QListWidget::item {
                background: transparent;
                padding: 5px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                outline: none;
            }
            QListWidget::item:hover {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                outline: none;
            }
            QListWidget::item:selected {
                background: rgba(0, 180, 255, 0.3);
                border-radius: 10px;
                outline: none;
            }
            QListWidget::item:focus {
                outline: none;
            }
        """)
        
        # 设置项高度
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(5)
        
        # 添加歌曲项
        for song in songs:
            self.add_song_item(song)
        
        # 播放按钮
        self.btn_play = QPushButton("播放")
        self.btn_play.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b4ff, stop:1 #0080ff
                );
                border-radius: 15px;
                padding: 12px;
                color: white;
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
        
        self.btn_play.clicked.connect(self.on_play)
        self.list_widget.itemDoubleClicked.connect(self.on_play)
        
        self.main_layout.addWidget(self.title_bar)
        self.main_layout.addWidget(self.list_widget)
        self.main_layout.addWidget(self.btn_play)
    
    def add_song_item(self, song):
        """添加歌曲项到列表"""
        # 创建自定义Widget
        item_widget = SongItemWidget(song, self.api_url)
        
        # 创建QListWidgetItem
        item = QListWidgetItem(self.list_widget)
        item.setSizeHint(QSize(0, 80))  # 设置项高度
        item.setData(Qt.UserRole, song["id"])  # 存储歌曲ID
        
        # 设置项Widget
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, item_widget)
    
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

    def mousePressEvent(self, event):
        """鼠标按下事件(用于窗口拖动)"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件(用于窗口拖动)"""
        if event.buttons() & Qt.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def show_cookie_input_dialog(self):
        """显示手动输入Cookie的对话框"""
        dialog = QInputDialog(self)
        dialog.setWindowTitle("手动输入Cookie")
        dialog.setLabelText("请输入网易云音乐Cookie:")
        dialog.setInputMode(QInputDialog.TextInput)
        dialog.setTextValue("")
        dialog.setStyleSheet("""
            QInputDialog {
                background: rgba(30, 30, 40, 0.9);
                color: white;
            }
            QLabel {
                color: white;
                font-size: 16px;
            }
            QLineEdit {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                padding: 10px;
                color: white;
                font-size: 16px;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 8px 16px;
                color: white;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        
        if dialog.exec():
            cookie = dialog.textValue()
            if not cookie:
                QMessageBox.warning(self, "警告", "Cookie不能为空")
                return
                
            # 验证Cookie格式
            if "MUSIC_U=" not in cookie or "NMTID=" not in cookie:
                QMessageBox.warning(self, "警告", "Cookie格式不正确，必须包含MUSIC_U和NMTID")
                return
                
            # 保存Cookie
            self.parent.cookies = {
                "MUSIC_U": cookie.split("MUSIC_U=")[1].split(";")[0],
                "NMTID": cookie.split("NMTID=")[1].split(";")[0]
            }
            self.parent.save_cookie(cookie)
            self.parent.update_login_status("已登录")
            self.close()

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def on_play(self):
        """播放选中的歌曲"""
        selected = self.list_widget.currentItem()
        if selected:
            self.parent.play_song(selected.data(Qt.UserRole))
            self.close()

class ModernMusicPlayer(QWidget):
    COOKIE_FILE = "user_cookie.json"  # Cookie保存文件名
    
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

        # 初始化时尝试加载cookie
        self.cookies = self.load_cookie()

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

        # 登录/重新登录按钮
        self.login_button = QPushButton("重新登录" if self.cookies else "登录")
        self.login_button.setFixedHeight(45)
        self.login_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        self.login_button.clicked.connect(self.show_qr_login)
        
        # 登录状态标签
        self.login_status = QLabel("未登录", self)
        self.login_status.setStyleSheet("""
            font-size: 14px;
            color: rgba(255, 255, 255, 0.7);
            padding-left: 10px;
        """)
        self.login_status.setObjectName("loginStatus")
        
        # 登录状态布局
        login_layout = QHBoxLayout()
        login_layout.addWidget(self.login_button)
        login_layout.addWidget(self.login_status)

        # 控制按钮布局
        control_button_layout = QHBoxLayout()
        control_button_layout.setSpacing(20)
        control_button_layout.setAlignment(Qt.AlignCenter)

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

        # 添加到控制按钮布局
        control_button_layout.addWidget(self.play_pause_button)
        control_layout.addLayout(progress_layout)
        control_layout.addLayout(control_button_layout)
        control_layout.addLayout(volume_layout)

        # 添加到右侧布局 - 将登录布局移到最上方
        right_layout.addLayout(login_layout)
        
        # 初始化完成后更新登录状态
        if self.cookies:
            self.update_login_status("已登录")  # 会自动触发获取用户名逻辑
        right_layout.addWidget(self.search_input)
        right_layout.addWidget(self.search_button)
        right_layout.addWidget(self.lyrics_display, stretch=1)
        right_layout.addWidget(control_panel)

        # 添加到主布局
        self.main_layout.addWidget(right_panel, stretch=2)

    def show_qr_login(self):
        """显示二维码登录窗口"""
        self.login_window = QRLoginWindow(self.api_url, self)
        self.login_window.show()
        
    def update_login_status(self, status):
        """更新登录状态"""
        if status == "已登录":
            # 异步获取用户名
            def get_username():
                try:
                    # 将cookie字典转换为字符串格式
                    cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                        "Cookie": cookie_str
                    }
                    response = requests.get(
                        f"{self.api_url}/user/account",
                        headers=headers
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('code') == 200:
                            nickname = data.get('profile', {}).get('nickname', '用户')
                            self.login_status.setText(f"你好！{nickname}")
                            return
                    # 如果获取失败，显示默认状态
                    self.login_status.setText("已登录")
                except Exception as e:
                    print(f"获取用户名失败: {e}")
                    self.login_status.setText("已登录")
            
            Thread(target=get_username, daemon=True).start()
        else:
            self.login_status.setText(status)

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
        try:
            if self.isVisible():
                # 先关闭所有子窗口
                if hasattr(self, 'search_window') and self.search_window:
                    self.search_window.close()
                if hasattr(self, 'exit_window') and self.exit_window:
                    self.exit_window.close()
                if hasattr(self, 'login_window') and self.login_window:
                    self.login_window.close()
                
                # 添加短暂延迟确保窗口完全关闭
                QApplication.processEvents()
                
                # 再隐藏主窗口
                self.hide()
            else:
                self.show()
                self.raise_()
                self.activateWindow()
        except Exception as e:
            print(f"切换可见性出错: {e}")

    def show_search_results(self, songs):
        """显示搜索结果窗口"""
        self.search_window = SearchResultsWindow(self, songs, self.api_url)
        self.search_window.show()

    def play_song(self, song_id):
        """播放指定ID的歌曲"""
        try:
            # 获取歌曲详情
            detail_res = requests.get(f"{self.api_url}/song/detail", params={"ids": song_id}).json()
            songs_detail = detail_res.get("songs", [])
            if not songs_detail:
                self.show_message("无法获取歌曲详情", "error")
                return
            
            detail = songs_detail[0]
            song_name = detail["name"]
            artist_name = detail["ar"][0]["name"] if detail.get("ar") else "未知艺术家"

            # 获取播放链接 - 分离cookies和headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            cookies = None
            if hasattr(self, 'cookies') and self.cookies:
                cookies = {
                    "MUSIC_U": self.cookies['MUSIC_U'],
                    "NMTID": self.cookies['NMTID']
                }
            
            url_res = requests.get(f"{self.api_url}/song/url", params={'id': song_id}, headers=headers, cookies=cookies).json()
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

    def search_and_play(self):
        """搜索音乐并显示结果列表"""
        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "提示", "请输入歌曲名称")
            return

        try:
            # 搜索歌曲 - 分离cookies和headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            cookies = None
            if hasattr(self, 'cookies') and self.cookies:
                cookies = {
                    "MUSIC_U": self.cookies['MUSIC_U'],
                    "NMTID": self.cookies['NMTID']
                }
                
            res = requests.get(f"{self.api_url}/search", params={"keywords": keyword}, headers=headers, cookies=cookies).json()
            songs = res.get("result", {}).get("songs", [])
            if not songs:
                self.show_message("未找到歌曲", "warning")
                return
            
            # 显示搜索结果对话框
            self.show_search_results(songs)

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

        # 上下各显示1行歌词
        start = max(0, self.lyric_index - 1)
        end = min(len(self.lyrics_data), self.lyric_index + 2)

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
            # 确保只有一个退出确认窗口实例
            if not hasattr(self, 'exit_window') or not self.exit_window:
                self.exit_window = ExitConfirmationWindow(self)
            self.exit_window.show()
            self.exit_window.raise_()
            self.exit_window.activateWindow()
        else:
            super().keyPressEvent(event)

    def load_cookie(self):
        """从注册表加载cookie"""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\RTLite", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "Cookie")
            winreg.CloseKey(key)
            return {
                "MUSIC_U": value.split("MUSIC_U=")[1].split(";")[0] if "MUSIC_U=" in value else "",
                "NMTID": value.split("NMTID=")[1].split(";")[0] if "NMTID=" in value else ""
            }
        except WindowsError as e:
            if e.errno == 2:  # 键不存在
                return None
            print(f"从注册表加载cookie失败: {e}")
            return None
        except Exception as e:
            print(f"加载cookie失败: {e}")
            return None
        
    def save_cookie(self, cookie):
        """保存cookie到注册表"""
        try:
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\RTLite")
            winreg.SetValueEx(key, "Cookie", 0, winreg.REG_SZ, cookie)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"保存cookie到注册表失败: {e}")

class QRLoginWindow(QWidget):
    """二维码登录窗口"""
    def __init__(self, api_url, parent=None):
        super().__init__(parent)
        self.api_url = api_url
        self.parent = parent
        self.drag_position = None  # 初始化拖动位置变量
        self.setWindowTitle("扫码登录")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(400, 500)
        
        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        self.main_layout.setSpacing(20)
        
        # 标题
        self.title_label = QLabel("扫码登录")
        self.title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        self.title_label.setAlignment(Qt.AlignCenter)
        
        # 二维码标签 - 添加鼠标点击事件
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setFixedSize(400, 400)
        self.qr_label.setStyleSheet("""
            background: white;
            border-radius: 15px;
        """)
        self.qr_label.setCursor(Qt.PointingHandCursor)  # 设置手型光标
        self.qr_label.mousePressEvent = self.refresh_qr_code  # 点击刷新
        
        # 状态标签
        self.status_label = QLabel("正在生成二维码...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
            }
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        
        # 手动输入Cookie按钮
        self.manual_cookie_btn = QPushButton("手动输入Cookie")
        self.manual_cookie_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 10px 20px;
                color: white;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        # 确保连接正确并添加调试输出
        def on_manual_cookie_click():
            self.show_cookie_input_dialog()
        self.manual_cookie_btn.clicked.connect(on_manual_cookie_click)
        
        # 关闭按钮
        self.close_button = QPushButton("关闭")
        self.close_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 10px 20px;
                color: white;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        self.close_button.clicked.connect(self.close)
        
        # 添加到布局
        self.main_layout.addWidget(self.title_label)
        self.main_layout.addWidget(self.qr_label)
        self.main_layout.addWidget(self.status_label)
        self.main_layout.addWidget(self.manual_cookie_btn)
        self.main_layout.addWidget(self.close_button)
        
        # 启动登录流程
        self.start_login()
    
    def start_login(self):
        """启动扫码登录流程"""
        # 获取二维码key
        try:
            # 添加时间戳防止缓存
            timestamp = int(time.time() * 1000)
            key_res = requests.get(f"{self.api_url}/login/qr/key", params={
                "timestamp": timestamp
            }).json()
            key = key_res.get("data", {}).get("unikey")
            if not key:
                self.status_label.setText("获取二维码key失败")
                return
                
            # 生成二维码
            # 添加时间戳防止缓存
            timestamp = int(time.time() * 1000)
            qr_res = requests.get(
                f"{self.api_url}/login/qr/create", 
                params={
                    "key": key, 
                    "qrimg": "true",
                    "timestamp": timestamp
                }
            ).json()
            qr_img = qr_res.get("data", {}).get("qrimg")
            if not qr_img:
                self.status_label.setText("生成二维码失败")
                return
                
            # 显示二维码
            self.show_qr_code(qr_img)
            self.status_label.setText("请使用网易云音乐APP扫码")
            
            # 启动轮询检查登录状态
            self.key = key
            self.check_timer = self.startTimer(1000)  # 每3秒检查一次
            
        except Exception as e:
            self.status_label.setText(f"登录失败: {str(e)}")
    
    def refresh_qr_code(self, event=None):
        """刷新二维码"""
        if event:  # 如果是鼠标事件触发
            event.accept()
        if hasattr(self, 'check_timer'):
            self.killTimer(self.check_timer)
        self.status_label.setText("正在刷新二维码...")
        QTimer.singleShot(100, self.start_login)  # 延迟100ms确保timer被清理

    def show_cookie_input_dialog(self):
        """显示手动输入Cookie的对话框"""
        dialog = CookieInputDialog(self)
        if dialog.exec():
            cookie = dialog.get_cookie()
            if not cookie:
                QMessageBox.warning(self, "警告", "Cookie不能为空")
                return
                
            # 验证Cookie格式
            if "MUSIC_U=" not in cookie or "NMTID=" not in cookie:
                QMessageBox.warning(self, "警告", "Cookie格式不正确，必须包含MUSIC_U和NMTID")
                return
                
            # 保存Cookie
            self.cookies = {
                "MUSIC_U": cookie.split("MUSIC_U=")[1].split(";")[0],
                "NMTID": cookie.split("NMTID=")[1].split(";")[0]
            }
            self.save_cookie(cookie)
            self.update_login_status("已登录")
        dialog.setWindowTitle("手动输入Cookie")
        dialog.setWindowFlags(Qt.FramelessWindowHint)
        dialog.setAttribute(Qt.WA_TranslucentBackground)
        dialog.resize(600, 400)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # 标题
        title = QLabel("请输入网易云音乐Cookie:")
        title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        
        # 多行输入框
        text_edit = QTextEdit()
        text_edit.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                padding: 15px;
                color: white;
                font-size: 16px;
                min-height: 200px;
            }
        """)
        text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        # 确认按钮
        btn_ok = QPushButton("确定")
        btn_ok.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b4ff, stop:1 #0080ff
                );
                border-radius: 15px;
                padding: 10px 20px;
                color: white;
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
        
        # 取消按钮
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 10px 20px;
                color: white;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        
        layout.addWidget(title)
        layout.addWidget(text_edit, stretch=1)
        layout.addLayout(btn_layout)
        
        def on_ok():
            cookie = text_edit.toPlainText().strip()
            if cookie:
                # 验证Cookie格式
                if "MUSIC_U=" not in cookie or "NMTID=" not in cookie:
                    QMessageBox.warning(dialog, "警告", "Cookie格式不正确，必须包含MUSIC_U和NMTID")
                    return
                    
                # 保存Cookie
                self.parent.cookies = {
                    "MUSIC_U": cookie.split("MUSIC_U=")[1].split(";")[0],
                    "NMTID": cookie.split("NMTID=")[1].split(";")[0]
                }
                self.parent.save_cookie(cookie)
                self.parent.update_login_status("已登录")
                dialog.close()
                self.close()
        
        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dialog.close)
        
        dialog.exec()

    def show_qr_code(self, base64_img):
        """显示base64格式的二维码图片"""
        try:
            # 移除base64前缀
            if "base64," in base64_img:
                base64_img = base64_img.split("base64,")[1]
                
            # 解码图片
            img_data = base64.b64decode(base64_img)
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            
            # 缩放并居中显示
            scaled_pixmap = pixmap.scaled(
                400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            
            # 创建空白画布并居中绘制二维码
            canvas = QPixmap(400, 400)
            canvas.fill(Qt.white)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # 计算居中位置
            x = (canvas.width() - scaled_pixmap.width()) // 2
            y = (canvas.height() - scaled_pixmap.height()) // 2
            
            # 绘制二维码
            painter.drawPixmap(x, y, scaled_pixmap)
            painter.end()
            
            # 设置二维码标签的对齐方式为居中
            self.qr_label.setAlignment(Qt.AlignCenter)
            self.qr_label.setPixmap(canvas)
            
        except Exception as e:
            self.status_label.setText(f"显示二维码失败: {str(e)}")
    
    def timerEvent(self, event):
        """定时器事件 - 检查登录状态"""
        if event.timerId() == self.check_timer:
            try:
                # 添加时间戳和noCookie参数防止502错误
                timestamp = int(time.time() * 1000)
                try:
                    check_res = requests.get(
                        f"{self.api_url}/login/qr/check", 
                        params={
                            "key": self.key,
                            "timestamp": timestamp,
                            "noCookie": "true"
                        }
                    ).json()
                    
                    if not isinstance(check_res, dict):
                        raise ValueError("Invalid response format")
                        
                    code = check_res.get("code", -1)
                    message = check_res.get("message", "")
                    cookie = check_res.get("cookie", "")
                except Exception as e:
                    print(f"检查登录状态出错: {e}")
                    self.status_label.setText("检查登录状态出错")
                    self.killTimer(self.check_timer)
                    return
                
                if code == 800:
                    self.status_label.setText("二维码已过期")
                    self.killTimer(self.check_timer)
                elif code == 801:
                    self.status_label.setText("等待扫码...")
                elif code == 802:
                    self.status_label.setText("扫码成功，请确认")
                elif code == 803:
                    # 登录成功
                    self.killTimer(self.check_timer)
                    self.status_label.setText("登录成功！")
                    if cookie:
                        print(f"登录成功，获取到cookie: {cookie}")  # 打印cookie
                        self.parent.cookies = cookie
                        self.parent.save_cookie(cookie)  # 保存cookie到文件
                        
                        # 直接获取用户信息
                        def get_user_info():
                            try:
                                # 调用用户详情接口
                                headers = {
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                                    "Cookie": cookie
                                }
                                response = requests.get(
                                    f"{self.api_url}/user/account",
                                    headers=headers
                                )
                                
                                if response.status_code != 200:
                                    print(f"请求失败，状态码: {response.status_code}")
                                    self.parent.update_login_status("已登录")
                                    return
                                    
                                detail_res = response.json()
                                if not isinstance(detail_res, dict):
                                    print("返回数据格式错误")
                                    self.parent.update_login_status("已登录")
                                    return
                                
                                if detail_res.get('code') == 200:
                                    profile = detail_res.get('profile', {})
                                    if not isinstance(profile, dict):
                                        profile = {}
                                    username = profile.get('nickname', '用户')
                                    self.parent.update_login_status(f"你好！{username}")
                                else:
                                    print(f"获取用户信息失败: {detail_res}")
                                    self.parent.update_login_status("已登录")
                            except Exception as e:
                                print(f"获取用户信息异常: {str(e)}")
                                self.parent.update_login_status("已登录")
                        
                        get_user_info()  # 立即执行
                        # 尝试播放一首歌测试登录状态
                        try:
                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                                "Cookie": cookie
                            }
                            test_res = requests.get(
                                f"{self.api_url}/recommend/songs",
                                headers=headers
                            ).json()
                            if test_res.get("code") == 200:
                                self.status_label.setText("登录成功！")
                            else:
                                self.status_label.setText("登录状态验证失败")
                        except Exception as e:
                            print(f"验证登录状态失败: {e}")
                    else:
                        self.status_label.setText("获取cookie失败")
                    QTimer.singleShot(1000, self.close)  # 1秒后关闭
                    
            except Exception as e:
                self.status_label.setText(f"检查登录状态失败: {str(e)}")
                self.killTimer(self.check_timer)
    
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

    def mousePressEvent(self, event):
        """鼠标按下事件(用于窗口拖动)"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件(用于窗口拖动)"""
        if event.buttons() & Qt.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()


class CookieInputDialog(QDialog):
    """自定义Cookie输入对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("手动输入Cookie")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(500, 300)
        
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # 标题
        title = QLabel("请输入网易云音乐Cookie:")
        title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        
        # 输入框
        self.text_edit = QTextEdit()
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                padding: 15px;
                color: white;
                font-size: 16px;
            }
        """)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        # 确认按钮
        btn_ok = QPushButton("确定")
        btn_ok.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b4ff, stop:1 #0080ff
                );
                border-radius: 15px;
                padding: 10px 20px;
                color: white;
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
        btn_ok.clicked.connect(self.accept)
        
        # 取消按钮
        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 10px 20px;
                color: white;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        
        layout.addWidget(title)
        layout.addWidget(self.text_edit, stretch=1)
        layout.addLayout(btn_layout)
    
    def get_cookie(self):
        """获取输入的Cookie"""
        return self.text_edit.toPlainText().strip()
    
    def paintEvent(self, event):
        """绘制窗口背景和边框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制半透明背景
        painter.setBrush(QBrush(QColor(20, 20, 30, 220)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 20, 20)
        
        # 绘制边框
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor(0, 180, 255, 80))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 20, 20)

    def mousePressEvent(self, event):
        """鼠标按下事件(用于窗口拖动)"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件(用于窗口拖动)"""
        if event.buttons() & Qt.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()


class ExitConfirmationWindow(QWidget):
    """退出确认窗口"""
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setWindowTitle("退出确认")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(400, 200)
        
        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        self.main_layout.setSpacing(20)
        
        # 标题
        self.title_label = QLabel("退出确认")
        self.title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        self.title_label.setAlignment(Qt.AlignCenter)
        
        # 提示文本
        self.message_label = QLabel("确定要退出RTLite吗?")
        self.message_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
            }
        """)
        self.message_label.setAlignment(Qt.AlignCenter)
        
        # 按钮布局
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(20)
        
        # 确认按钮
        self.confirm_button = QPushButton("确定")
        self.confirm_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b4ff, stop:1 #0080ff
                );
                border-radius: 15px;
                padding: 10px 20px;
                color: white;
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
        self.confirm_button.clicked.connect(self.on_confirm)
        
        # 取消按钮
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                padding: 10px 20px;
                color: white;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        self.cancel_button.clicked.connect(self.close)
        
        self.button_layout.addWidget(self.confirm_button)
        self.button_layout.addWidget(self.cancel_button)
        
        self.main_layout.addWidget(self.title_label)
        self.main_layout.addWidget(self.message_label)
        self.main_layout.addLayout(self.button_layout)
    
    def paintEvent(self, event):
        """绘制窗口背景和边框"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制半透明背景
        painter.setBrush(QBrush(QColor(20, 20, 30, 220)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 20, 20)
        
        # 绘制边框
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor(0, 180, 255, 80))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 20, 20)

    def on_confirm(self):
        """确认退出"""
        self.parent.close()
        self.close()

    def mousePressEvent(self, event):
        """鼠标按下事件(用于窗口拖动)"""
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件(用于窗口拖动)"""
        if event.buttons() & Qt.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def closeEvent(self, event):
        """关闭事件"""
        # 先关闭子窗口
        if hasattr(self, 'search_window') and self.search_window:
            self.search_window.close()
        
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置应用程序字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    player = ModernMusicPlayer()
    player.show()
    sys.exit(app.exec())
