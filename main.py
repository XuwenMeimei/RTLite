import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QFrame, QLabel, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, Property
from PySide6.QtGui import QCursor, QMouseEvent

class ModuleButton(QPushButton):
    def __init__(self, name):
        super().__init__(name)
        self.setCheckable(True)
        self.setFixedHeight(28)
        self.setStyleSheet("""
            QPushButton {
                background-color: rgba(40, 40, 40, 220);
                color: white;
                border-radius: 6px;
                padding-left: 10px;
                text-align: left;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: rgba(70, 70, 70, 220);
            }
            QPushButton:checked {
                background-color: rgba(100, 180, 100, 220);
            }
        """)

        self.setting_panel = None
        self.setting_panel_anim = None
        self.anim_running = False  # 动画运行标志，防止动画冲突
        self.panel_expanded = False

    def contextMenuEvent(self, event):
        event.accept()  # 阻止默认系统菜单弹出
        if self.anim_running:
            return  # 动画进行中不响应点击
        if self.setting_panel and self.setting_panel.isVisible():
            self.collapse_setting_panel()
        else:
            self.expand_setting_panel()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            # 屏蔽右键导致按钮状态改变
            event.accept()
            self.contextMenuEvent(event)
        else:
            super().mousePressEvent(event)

    def nextCheckState(self):
        # 阻止右键点击导致切换按钮状态
        mouse_buttons = QApplication.mouseButtons()
        if mouse_buttons & Qt.RightButton:
            return  # 什么都不做
        super().nextCheckState()

    def expand_setting_panel(self, from_restore=False):
        if self.anim_running:
            return
        self.anim_running = True
        if not from_restore:
            self.panel_expanded = True

        if not self.setting_panel:
            self.setting_panel = SettingPanel(self)
            idx = self.parentWidget().layout().indexOf(self)
            self.parentWidget().layout().insertWidget(idx + 1, self.setting_panel)

        self.setting_panel.setMaximumHeight(0)
        self.setting_panel.show()

        self.setting_panel_anim = QPropertyAnimation(self.setting_panel, b"maximumHeight")
        self.setting_panel_anim.setDuration(200)
        self.setting_panel_anim.setStartValue(0)
        self.setting_panel_anim.setEndValue(80)  # 展开高度，根据内容调整
        self.setting_panel_anim.setEasingCurve(QEasingCurve.OutCubic)

        def on_anim_value_changed():
            parent_window = self.window()
            if hasattr(parent_window, "adjust_height"):
                parent_window.adjust_height()

        def on_anim_finished():
            self.anim_running = False

        self.setting_panel_anim.valueChanged.connect(lambda _: on_anim_value_changed())
        self.setting_panel_anim.finished.connect(on_anim_finished)

        self.setting_panel_anim.start()

        # 这里取消 setChecked，右键不改按钮状态
        # if not from_restore:
        #     self.setChecked(True)

    def collapse_setting_panel(self, temporary=False):
        if not self.setting_panel or self.anim_running:
            return
        if not temporary:
            self.panel_expanded = False

        self.anim_running = True

        self.setting_panel_anim = QPropertyAnimation(self.setting_panel, b"maximumHeight")
        self.setting_panel_anim.setDuration(200)
        self.setting_panel_anim.setStartValue(self.setting_panel.height())
        self.setting_panel_anim.setEndValue(0)
        self.setting_panel_anim.setEasingCurve(QEasingCurve.OutCubic)

        def on_finished():
            self.setting_panel.hide()
            parent_window = self.window()
            if hasattr(parent_window, "adjust_height"):
                parent_window.adjust_height()
            self.anim_running = False

        def on_anim_value_changed():
            parent_window = self.window()
            if hasattr(parent_window, "adjust_height"):
                parent_window.adjust_height()

        self.setting_panel_anim.finished.connect(on_finished)
        self.setting_panel_anim.valueChanged.connect(lambda _: on_anim_value_changed())

        self.setting_panel_anim.start()

        # 这里取消 setChecked，右键不改按钮状态
        # self.setChecked(False)


class SettingPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            background-color: rgba(60, 60, 60, 230);
            border-radius: 6px;
            color: white;
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)

        # 示例设置内容
        layout.addWidget(QLabel("设置项1"))
        layout.addWidget(QLabel("设置项2"))
        layout.addWidget(QLabel("设置项3"))


class FloatingCategoryWindow(QMainWindow):
    def __init__(self, title, modules, pos):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(180)
        self.move(QPoint(*pos))

        self.dragging = False
        self.drag_start_position = QPoint()
        self.drag_threshold = 5

        self.central = QWidget()
        self.layout = QVBoxLayout(self.central)
        self.layout.setSpacing(2)
        self.layout.setContentsMargins(5, 5, 5, 5)

        self.toggle_button = QPushButton(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setFixedHeight(30)
        self.toggle_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(50, 50, 50, 230);
                color: white;
                border-radius: 8px;
                text-align: left;
                padding-left: 10px;
                margin: 0;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 230);
            }
            QPushButton:checked {
                background-color: rgba(100, 180, 100, 230);
            }
        """)
        self.toggle_button.clicked.connect(self.toggle_modules)

        # 添加鼠标事件处理器实现拖动
        self.toggle_button.installEventFilter(self)

        self.layout.addWidget(self.toggle_button)

        self.module_buttons = []
        for mod in modules:
            btn = ModuleButton(mod)
            btn.setVisible(False)
            self.layout.addWidget(btn)
            self.module_buttons.append(btn)

        self.module_states = {}

        self.setCentralWidget(self.central)

        self.collapsed_height = self.toggle_button.height() + self.layout.contentsMargins().top() + self.layout.contentsMargins().bottom()
        # 初始展开高度计算为折叠高度+所有按钮高度和间距
        self.expanded_height = self.collapsed_height + len(self.module_buttons) * (28 + self.layout.spacing())

        self.setFixedHeight(self.collapsed_height)

    def eventFilter(self, obj, event):
        """事件过滤器，用于处理标题按钮的鼠标事件"""
        if obj == self.toggle_button:
            if event.type() == QMouseEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self.dragging = True
                    self.drag_start_position = QCursor.pos() - self.geometry().topLeft()
                    # 调用原始鼠标按下事件处理
                    QPushButton.mousePressEvent(self.toggle_button, event)
                    return True

            elif event.type() == QMouseEvent.MouseMove:
                if self.dragging and event.buttons() & Qt.LeftButton:
                    new_pos = QCursor.pos() - self.drag_start_position
                    self.move(new_pos)
                    return True

            elif event.type() == QMouseEvent.MouseButtonRelease:
                if event.button() == Qt.LeftButton:
                    self.dragging = False
                    # 调用原始鼠标释放事件处理
                    QPushButton.mouseReleaseEvent(self.toggle_button, event)
                    return True

        return super().eventFilter(obj, event)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QBrush, QColor
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QBrush(QColor(30, 30, 30, 230)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 12, 12)

    def getHeight(self):
        return self.height()

    def setHeight(self, h):
        self.setFixedHeight(h)

    height_anim = Property(int, getHeight, setHeight)

    def toggle_modules(self):
        expanded = self.toggle_button.isChecked()
        if expanded:
            for btn in self.module_buttons:
                btn.setVisible(True)
                btn.setChecked(self.module_states.get(btn.text(), False))  # 恢复状态
                if btn.panel_expanded:
                    btn.expand_setting_panel(from_restore=True)
            self.adjust_height()
        else:
            for btn in self.module_buttons:
                self.module_states[btn.text()] = btn.isChecked()  # 保存状态
                btn.setChecked(False)
                if btn.setting_panel and btn.setting_panel.isVisible():
                    btn.collapse_setting_panel(temporary=True)
                btn.setVisible(False)
            self.setFixedHeight(self.collapsed_height)

    def adjust_height(self):
        height = self.toggle_button.height() + self.layout.contentsMargins().top() + self.layout.contentsMargins().bottom()
        spacing = self.layout.spacing()
        for btn in self.module_buttons:
            if btn.isVisible():
                height += btn.height() + spacing
                if btn.setting_panel and btn.setting_panel.isVisible():
                    height += btn.setting_panel.height() + spacing + 12
        self.setFixedHeight(height)


class MainApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setStyle("Fusion")

        self.entertainment_window = FloatingCategoryWindow("娱乐", ["Test1", "Test2", "Test3"], (300, 200))
        self.settings_window = FloatingCategoryWindow("设置", ["Test1", "Test2", "Test3"], (510, 200))

        self.entertainment_window.hide()
        self.settings_window.hide()

        self.visible = False
        self.key_was_down = False

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_key)
        self.timer.start(50)

    def toggle_windows(self):
        if self.visible:
            self.entertainment_window.hide()
            self.settings_window.hide()
        else:
            self.entertainment_window.show()
            self.settings_window.show()
        self.visible = not self.visible

    def check_key(self):
        import ctypes
        key_down = ctypes.windll.user32.GetAsyncKeyState(0xA1) & 0x8000  # Right Shift
        if key_down and not self.key_was_down:
            self.toggle_windows()
        self.key_was_down = key_down


if __name__ == "__main__":
    app = MainApp(sys.argv)
    sys.exit(app.exec())
