import sys
import ctypes
import cv2
import numpy as np
import mss
import keyboard
import time
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, 
                             QComboBox, QFileDialog, QLabel, QHBoxLayout, 
                             QSpinBox, QCheckBox)
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
    def __init__(self):
        super().__init__()
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
        self.resize(380, 250)
        layout = QVBoxLayout()

        # 1. 저장 경로 설정
        path_layout = QHBoxLayout()
        self.path_label = QLabel("저장 경로: output.avi")
        self.btn_path = QPushButton("경로 변경")
        self.btn_path.clicked.connect(self.set_save_path)
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.btn_path)
        layout.addLayout(path_layout)

        # 2. 모니터 선택
        self.monitor_combo = QComboBox()
        self.populate_monitors()
        layout.addWidget(QLabel("녹화할 모니터(영역) 선택:"))
        layout.addWidget(self.monitor_combo)

        # 3. 예약 녹화 종료 설정
        timer_layout = QHBoxLayout()
        self.chk_timer = QCheckBox("예약 종료 사용")
        self.chk_timer.stateChanged.connect(self.toggle_timer_input)
        
        self.spin_time = QSpinBox()
        self.spin_time.setRange(1, 1440)
        self.spin_time.setValue(20)
        self.spin_time.setEnabled(False)
        
        timer_layout.addWidget(self.chk_timer)
        timer_layout.addWidget(self.spin_time)
        timer_layout.addWidget(QLabel("분 후 자동 종료"))
        layout.addLayout(timer_layout)

        # 4. 상태 및 버튼
        self.status_label = QLabel("상태: 대기 중 (단축키: F12)")
        self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.btn_record = QPushButton("녹화 시작 (F12)")
        self.btn_record.setStyleSheet("background-color: #ff4d4d; color: white; font-weight: bold; padding: 10px;")
        self.btn_record.clicked.connect(self.toggle_record)
        layout.addWidget(self.btn_record)

        self.setLayout(layout)

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
            self.path_label.setText(f"저장 경로: {self.save_path.split('/')[-1]}")

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
            self.status_label.setText(f"상태: 녹화 중... (🔴 {minutes}분 후 자동 종료)")
        else:
            self.status_label.setText("상태: 녹화 중... 🔴")

        self.btn_record.setText("녹화 종료 (F12)")
        self.btn_record.setStyleSheet("background-color: gray; color: white; padding: 10px;")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")

    def stop_recording(self):
        if self.stop_timer.isActive():
            self.stop_timer.stop()

        if self.recording_thread:
            self.recording_thread.stop()
            self.recording_thread.wait()

        self.overlay.hide() # 빨간 테두리 숨기기
        self.btn_record.setText("녹화 시작 (F12)")
        self.btn_record.setStyleSheet("background-color: #ff4d4d; color: white; font-weight: bold; padding: 10px;")
        self.status_label.setText("상태: 대기 중 (단축키: F12)")
        self.status_label.setStyleSheet("color: blue; font-weight: bold;")

    def closeEvent(self, event):
        self.stop_recording()
        self.overlay.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ScreenRecorderApp()
    ex.show()
    sys.exit(app.exec_())
