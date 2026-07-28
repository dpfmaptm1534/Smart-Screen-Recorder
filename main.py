import sys
import ctypes
import ctypes.wintypes
import cv2
import numpy as np
import mss
import keyboard
import time
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout,
                             QComboBox, QFileDialog, QLabel, QHBoxLayout,
                             QSpinBox, QCheckBox, QFrame)
from PyQt5.QtCore import Qt, QThread, QTimer
from PyQt5.QtGui import QPainter, QPen, QColor

# --- 1. 화면에만 보이고 영상엔 안 찍히는 오버레이 창 ---
class RedBorderOverlay(QWidget):
    def __init__(self):
        super().__init__()
        # 중요: 테두리 없고, 항상 위에 뜨고, 클릭 통과, 작업표시줄 안 나오게 설정
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        # 핵심: 이 창은 캡처(`mss`)에서 제외되도록 운영체제 수준에서 '레이어'를 분리
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_PaintOnScreen) # 오버레이 창에 직접 그리기
        self.hide() # 처음엔 숨겨둠

    def set_area(self, x, y, w, h):
        self.setGeometry(x, y, w, h)
        self.show()
        self.exclude_from_capture()

    def exclude_from_capture(self):
        if sys.platform != "win32":
            return

        hwnd = int(self.winId())
        WDA_EXCLUDEFROMCAPTURE = 0x00000011
        WDA_MONITOR = 0x00000001

        user32 = ctypes.windll.user32
        if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
            user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR)

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(255, 0, 0), 6) # 빨간색, 두께 6px
        painter.setPen(pen)
        # 창 가장자리를 따라 빨간 네모 그리기
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)


# --- 2. 녹화를 처리하는 백그라운드 스레드 (변경 없음) ---
class RecordThread(QThread):
    def __init__(self, monitor, save_path):
        super().__init__()
        self.monitor = monitor
        self.save_path = save_path
        self.recording = True

    def run(self):
        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        fps = 20.0
        out = cv2.VideoWriter(self.save_path, fourcc, fps, (self.monitor["width"], self.monitor["height"]))
        
        with mss.mss() as sct:
            while self.recording:
                # mss는 진짜 화면만 캡처하므로 오버레이 레이어는 무시됨
                img = sct.grab(self.monitor)
                frame = np.array(img)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                out.write(frame)
                time.sleep(1/fps)

        out.release()

    def stop(self):
        self.recording = False


# --- 3. 메인 UI 창 ---
class ScreenRecorderApp(QWidget):
    RESIZE_BORDER_WIDTH = 8

    def __init__(self):
        super().__init__()
        self.drag_position = None
        self.initUI()
        self.recording_thread = None
        self.overlay = RedBorderOverlay() # 수정된 오버레이 클래스 사용
        self.save_path = "output.avi"
        
        # 예약 종료용 타이머
        self.stop_timer = QTimer()
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(self.stop_recording)
        
        # F12 단축키 등록
        keyboard.add_hotkey('F12', self.toggle_record)

    def initUI(self):
        self.setWindowTitle('Smart-Screen-Recorder')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.resize(720, 500)
        self.setMinimumSize(680, 460)
        self.setStyleSheet("""
            QWidget {
                background-color: #1f2833;
                color: #d8e1ea;
                font-family: "Malgun Gothic", "Segoe UI", Arial;
                font-size: 13px;
            }
            QLabel {
                background-color: transparent;
                color: #d8e1ea;
            }
            QLabel#appTitle {
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 0px;
            }
            QLabel#sectionTitle {
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#mutedLabel {
                color: #8fa0af;
                font-size: 12px;
            }
            QLabel#statusLabel {
                color: #7fb7ff;
                font-weight: 700;
            }
            QLabel#fieldLabel {
                color: #9fb0bf;
                font-size: 12px;
                font-weight: 700;
            }
            QFrame#titleBar {
                background-color: #111821;
                border-bottom: 1px solid #263443;
            }
            QFrame#topBar {
                background-color: #17202a;
                border-bottom: 1px solid #334251;
            }
            QFrame#contentPanel {
                background-color: #26313d;
                border: 1px solid #3a4958;
            }
            QFrame#optionRow {
                background-color: #202a35;
                border: 1px solid #3a4958;
                border-radius: 4px;
                min-height: 64px;
            }
            QPushButton {
                background-color: #334251;
                border: 1px solid #465769;
                border-radius: 4px;
                color: #edf4fb;
                height: 34px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #3d4f61;
            }
            QPushButton#recordButton {
                background-color: #202934;
                border: 3px solid #ff4d57;
                border-radius: 34px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 800;
                min-width: 68px;
                min-height: 68px;
                padding: 0;
            }
            QPushButton#recordButton:hover {
                background-color: #2b1217;
            }
            QPushButton#windowButton {
                background-color: transparent;
                border: none;
                border-radius: 0;
                color: #c8d2dc;
                font-size: 13px;
                min-width: 42px;
                min-height: 30px;
                padding: 0;
            }
            QPushButton#windowButton:hover {
                background-color: #263443;
            }
            QPushButton#closeButton {
                background-color: transparent;
                border: none;
                border-radius: 0;
                color: #c8d2dc;
                font-size: 13px;
                min-width: 42px;
                min-height: 30px;
                padding: 0;
            }
            QPushButton#closeButton:hover {
                background-color: #d9434e;
                color: #ffffff;
            }
            QComboBox, QSpinBox {
                background-color: #101820;
                border: 1px solid #465769;
                border-radius: 4px;
                color: #f4f8fb;
                height: 34px;
                padding: 0 8px;
            }
            QCheckBox {
                color: #d8e1ea;
                spacing: 8px;
            }
        """)

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.title_bar = QFrame()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(34)
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(12, 0, 0, 0)
        title_bar_layout.setSpacing(0)

        window_title = QLabel("Smart-Screen-Recorder")
        window_title.setObjectName("mutedLabel")
        title_bar_layout.addWidget(window_title)
        title_bar_layout.addStretch()

        btn_minimize = QPushButton("_")
        btn_minimize.setObjectName("windowButton")
        btn_minimize.clicked.connect(self.showMinimized)
        title_bar_layout.addWidget(btn_minimize)

        self.btn_maximize = QPushButton("□")
        self.btn_maximize.setObjectName("windowButton")
        self.btn_maximize.clicked.connect(self.toggle_maximize)
        title_bar_layout.addWidget(self.btn_maximize)

        btn_close = QPushButton("X")
        btn_close.setObjectName("closeButton")
        btn_close.clicked.connect(self.close)
        title_bar_layout.addWidget(btn_close)

        root_layout.addWidget(self.title_bar)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(92)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(14, 8, 12, 8)
        top_layout.setSpacing(10)

        title = QLabel("SMART SCREEN RECORDER")
        title.setObjectName("appTitle")
        top_layout.addWidget(title)
        top_layout.addStretch()

        self.status_label = QLabel("대기 중 | F12")
        self.status_label.setObjectName("statusLabel")
        top_layout.addWidget(self.status_label)

        self.btn_record = QPushButton("REC")
        self.btn_record.setObjectName("recordButton")
        self.btn_record.clicked.connect(self.toggle_record)
        top_layout.addWidget(self.btn_record)
        root_layout.addWidget(top_bar)

        content = QFrame()
        content.setObjectName("contentPanel")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(16)

        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        section_title = QLabel("화면 녹화")
        section_title.setObjectName("sectionTitle")
        section_subtitle = QLabel("녹화 영역과 저장 옵션을 선택하세요")
        section_subtitle.setObjectName("mutedLabel")
        header_text.addWidget(section_title)
        header_text.addWidget(section_subtitle)
        header_layout.addLayout(header_text)
        header_layout.addStretch()
        content_layout.addLayout(header_layout)

        # 1. 저장 경로 설정
        path_row = QFrame()
        path_row.setObjectName("optionRow")
        path_row.setFixedHeight(64)
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(12, 7, 10, 7)
        path_layout.setSpacing(8)
        path_caption = QLabel("저장")
        path_caption.setObjectName("fieldLabel")
        path_caption.setFixedWidth(78)
        path_caption.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.path_label = QLabel("output.avi")
        self.path_label.setObjectName("sectionTitle")
        self.path_label.setMinimumWidth(220)
        self.path_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.btn_path = QPushButton("경로 변경")
        self.btn_path.setMinimumWidth(92)
        self.btn_path.setFixedHeight(34)
        self.btn_path.clicked.connect(self.set_save_path)
        path_layout.addWidget(path_caption, 0, Qt.AlignVCenter)
        path_layout.addWidget(self.path_label, 0, Qt.AlignVCenter)
        path_layout.addStretch()
        path_layout.addWidget(self.btn_path, 0, Qt.AlignVCenter)
        content_layout.addWidget(path_row)

        # 2. 모니터 선택
        monitor_row = QFrame()
        monitor_row.setObjectName("optionRow")
        monitor_row.setFixedHeight(64)
        monitor_layout = QHBoxLayout(monitor_row)
        monitor_layout.setContentsMargins(12, 7, 10, 7)
        monitor_layout.setSpacing(8)
        monitor_label = QLabel("녹화 화면")
        monitor_label.setObjectName("fieldLabel")
        monitor_label.setFixedWidth(78)
        monitor_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.monitor_combo = QComboBox()
        self.monitor_combo.setMinimumWidth(360)
        self.monitor_combo.setFixedHeight(34)
        self.populate_monitors()
        monitor_layout.addWidget(monitor_label, 0, Qt.AlignVCenter)
        monitor_layout.addWidget(self.monitor_combo, 0, Qt.AlignVCenter)
        content_layout.addWidget(monitor_row)

        # 3. 예약 녹화 종료 설정
        timer_row = QFrame()
        timer_row.setObjectName("optionRow")
        timer_row.setFixedHeight(64)
        timer_layout = QHBoxLayout(timer_row)
        timer_layout.setContentsMargins(12, 7, 10, 7)
        timer_layout.setSpacing(8)
        self.chk_timer = QCheckBox("예약 종료 사용")
        self.chk_timer.stateChanged.connect(self.toggle_timer_input)
        
        self.spin_time = QSpinBox()
        self.spin_time.setRange(1, 1440)
        self.spin_time.setValue(20)
        self.spin_time.setEnabled(False)
        self.spin_time.setFixedWidth(80)
        self.spin_time.setFixedHeight(34)
        timer_suffix = QLabel("분 후 자동 종료")
        timer_suffix.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        
        timer_layout.addWidget(self.chk_timer, 0, Qt.AlignVCenter)
        timer_layout.addWidget(self.spin_time, 0, Qt.AlignVCenter)
        timer_layout.addWidget(timer_suffix, 0, Qt.AlignVCenter)
        timer_layout.addStretch()
        content_layout.addWidget(timer_row)

        hint = QLabel("F12로 언제든 녹화를 시작하거나 종료할 수 있습니다.")
        hint.setObjectName("mutedLabel")
        hint.setMinimumHeight(24)
        content_layout.addWidget(hint)
        content_layout.addStretch()

        root_layout.addWidget(content)

        self.setLayout(root_layout)

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.btn_maximize.setText("□")
        else:
            self.showMaximized()
            self.btn_maximize.setText("❐")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() <= self.title_bar.height():
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_position and event.buttons() & Qt.LeftButton and not self.isMaximized():
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        event.accept()

    def nativeEvent(self, event_type, message):
        if sys.platform != "win32" or event_type != b"windows_generic_MSG":
            return super().nativeEvent(event_type, message)

        msg = ctypes.wintypes.MSG.from_address(int(message))
        WM_NCHITTEST = 0x0084
        if msg.message != WM_NCHITTEST or self.isMaximized():
            return super().nativeEvent(event_type, message)

        HTLEFT = 10
        HTRIGHT = 11
        HTTOP = 12
        HTTOPLEFT = 13
        HTTOPRIGHT = 14
        HTBOTTOM = 15
        HTBOTTOMLEFT = 16
        HTBOTTOMRIGHT = 17

        cursor_x = ctypes.c_short(msg.lParam & 0xFFFF).value
        cursor_y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        window_rect = self.frameGeometry()
        border = self.RESIZE_BORDER_WIDTH

        on_left = window_rect.left() <= cursor_x < window_rect.left() + border
        on_right = window_rect.right() - border < cursor_x <= window_rect.right()
        on_top = window_rect.top() <= cursor_y < window_rect.top() + border
        on_bottom = window_rect.bottom() - border < cursor_y <= window_rect.bottom()

        if on_top and on_left:
            return True, HTTOPLEFT
        if on_top and on_right:
            return True, HTTOPRIGHT
        if on_bottom and on_left:
            return True, HTBOTTOMLEFT
        if on_bottom and on_right:
            return True, HTBOTTOMRIGHT
        if on_left:
            return True, HTLEFT
        if on_right:
            return True, HTRIGHT
        if on_top:
            return True, HTTOP
        if on_bottom:
            return True, HTBOTTOM

        return super().nativeEvent(event_type, message)

    def populate_monitors(self):
        with mss.mss() as sct:
            self.monitors = sct.monitors
            for i, mon in enumerate(self.monitors):
                if i == 0:
                    self.monitor_combo.addItem(f"모든 모니터 전체 ({mon['width']}x{mon['height']})")
                else:
                    self.monitor_combo.addItem(f"모니터 {i} ({mon['width']}x{mon['height']})")

    def set_save_path(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "저장 경로 설정", "output.avi", "AVI Files (*.avi)", options=options)
        if file_name:
            self.save_path = file_name
            self.path_label.setText(self.save_path.split('/')[-1])

    def toggle_timer_input(self, state):
        self.spin_time.setEnabled(state == Qt.Checked)

    def toggle_record(self):
        if self.recording_thread is None or not self.recording_thread.isRunning():
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        monitor_idx = self.monitor_combo.currentIndex()
        selected_monitor = self.monitors[monitor_idx]

        # 빨간 테두리 띄우기 (이제 캡처 레이어 위에만 떠 있음)
        self.overlay.set_area(selected_monitor["left"], selected_monitor["top"], 
                              selected_monitor["width"], selected_monitor["height"])

        # 녹화 시작
        self.recording_thread = RecordThread(selected_monitor, self.save_path)
        self.recording_thread.start()

        # 예약 종료 타이머
        if self.chk_timer.isChecked():
            minutes = self.spin_time.value()
            milliseconds = minutes * 60 * 1000
            self.stop_timer.start(milliseconds)
            self.status_label.setText(f"녹화 중 | {minutes}분 후 종료")
        else:
            self.status_label.setText("녹화 중 | F12")

        self.btn_record.setText("STOP")
        self.btn_record.setStyleSheet("""
            QPushButton#recordButton {
                background-color: #ff4d57;
                border: 3px solid #ff7b82;
                border-radius: 34px;
                color: #ffffff;
                font-size: 13px;
                font-weight: 800;
                min-width: 68px;
                min-height: 68px;
                padding: 0;
            }
        """)
        self.status_label.setStyleSheet("color: #ff6972; font-weight: 700;")

    def stop_recording(self):
        if self.stop_timer.isActive():
            self.stop_timer.stop()

        if self.recording_thread:
            self.recording_thread.stop()
            self.recording_thread.wait()

        self.overlay.hide() # 빨간 테두리 숨기기
        self.btn_record.setText("REC")
        self.btn_record.setStyleSheet("")
        self.status_label.setText("대기 중 | F12")
        self.status_label.setStyleSheet("color: #7fb7ff; font-weight: 700;")

    def closeEvent(self, event):
        self.stop_recording()
        self.overlay.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ScreenRecorderApp()
    ex.show()
    sys.exit(app.exec_())
