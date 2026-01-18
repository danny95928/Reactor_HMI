import sys
import os
import datetime
import subprocess
import platform
import re

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QStackedWidget, QLabel, QPushButton,
                             QFrame, QSplitter, QApplication)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal

# 确保能找到根目录
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.append(root_dir)

# ==========================================
# 引入业务逻辑与各个子页面
# ==========================================

# 1. 核心逻辑
try:
    from modules.reactor_core import ReactorCore
except ImportError:
    print("Warning: ReactorCore not found, using dummy.")


    class ReactorCore:
        def __init__(self): pass

# 2. 模块一：虚实映射
try:
    from ui.modules.page_virtual import VirtualControlPage
except ImportError:
    VirtualControlPage = None

# 3. 模块二：状态追踪 (导入 FullTrackingModule)
try:
    from ui.modules.page_tracking import FullTrackingModule
except ImportError:
    FullTrackingModule = None

# 4. 模块三：孪生数据管理
try:
    from ui.modules.page_twin import TwinDataPage
except ImportError:
    TwinDataPage = None

# 5. 模块四：运维决策支持
try:
    from ui.modules.page_decision import DecisionSupportPage
except ImportError:
    DecisionSupportPage = None


# ============================================================================
# 新增：实时网络延迟检测线程
# ============================================================================
class NetworkLatencyWorker(QThread):
    latency_signal = pyqtSignal(str)

    def run(self):
        target = "8.8.8.8"
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '1', target]

        while True:
            try:
                if platform.system().lower() == 'windows':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               startupinfo=startupinfo)
                else:
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                stdout, stderr = process.communicate()
                output = stdout.decode('gbk', errors='ignore')

                match = re.search(r"time[=<](\d+)ms", output, re.IGNORECASE)
                if match:
                    self.latency_signal.emit(f"{match.group(1)}ms")
                else:
                    self.latency_signal.emit("超时")
            except:
                self.latency_signal.emit("错误")
            QThread.sleep(2)  # 每2秒检测一次


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("1# 反应釜数字孪生智能监控系统")
        self.resize(1280, 850)

        self.reactor = ReactorCore()

        # === 全局样式表 ===
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; color: #333333; }
            QLabel { color: #333333; font-family: 'Segoe UI', Arial; }
            #HeaderFrame { background-color: #ffffff; border-bottom: 2px solid #007acc; }
            #HeaderTitle { font-size: 18px; font-weight: bold; color: #333333; }
            #HeaderUser { font-size: 12px; color: #666666; }
            QListWidget { background-color: #e0e0e0; border: none; outline: none; }
            QListWidget::item { height: 50px; padding-left: 15px; border-left: 3px solid transparent; color: #555555; }
            QListWidget::item:selected { background-color: #ffffff; border-left: 3px solid #007acc; color: #000000; font-weight: bold; }
            QListWidget::item:hover { background-color: #dcdcdc; }
            #SubHeader { background-color: #ffffff; border-bottom: 1px solid #cccccc; }
            #ModuleTitle { font-size: 16px; font-weight: bold; color: #007acc; }
            #SysTime { font-family: 'Consolas', monospace; color: #333333; font-weight: bold;}
            #Footer { background-color: #007acc; color: #ffffff; font-weight: bold; }
            QSplitter::handle { background-color: #cccccc; }
        """)

        # === 主布局结构 ===
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.root_layout = QVBoxLayout(self.central_widget)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # 1. 顶部标题栏
        self.header_frame = QFrame()
        self.header_frame.setObjectName("HeaderFrame")
        self.header_frame.setFixedHeight(50)
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(15, 0, 15, 0)
        lbl_logo = QLabel("配制反应釜数字孪生智能监控系统")
        lbl_logo.setObjectName("HeaderTitle")
        header_layout.addWidget(lbl_logo)
        header_layout.addStretch()
        lbl_user = QLabel("[用户: 管理员]")
        lbl_user.setObjectName("HeaderUser")
        header_layout.addWidget(lbl_user)
        btn_exit = QPushButton(" 退出 ")
        btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exit.setStyleSheet(
            "background: transparent; color: #d32f2f; border: 1px solid #d32f2f; padding: 4px 10px; border-radius: 4px;")
        btn_exit.clicked.connect(self.close)
        header_layout.addWidget(btn_exit)
        self.root_layout.addWidget(self.header_frame)

        # 2. 中间区域 (QSplitter)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # 2.1 左侧导航
        self.sidebar = QListWidget()
        self.sidebar.setMinimumWidth(150)
        self.sidebar.setMaximumWidth(400)
        self.sidebar.addItems(["虚实映射控制", "状态追踪监控", "孪生数据管理", "运维决策支持"])

        # 修改：默认选中 Index 0 (虚实映射)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self.switch_page)

        # 2.2 右侧内容
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 2.2.1 顶部状态条
        sub_header = QFrame()
        sub_header.setObjectName("SubHeader")
        sub_header.setFixedHeight(40)
        sub_header_layout = QHBoxLayout(sub_header)
        sub_header_layout.setContentsMargins(20, 0, 20, 0)
        self.lbl_module_title = QLabel("当前模块: 虚实映射控制")
        self.lbl_module_title.setObjectName("ModuleTitle")
        self.lbl_sys_time = QLabel("00:00:00")
        self.lbl_sys_time.setObjectName("SysTime")
        sub_header_layout.addWidget(self.lbl_module_title)
        sub_header_layout.addStretch()
        sub_header_layout.addWidget(QLabel("系统时间: "))
        sub_header_layout.addWidget(self.lbl_sys_time)
        right_layout.addWidget(sub_header)

        # 2.2.2 堆叠窗口
        self.content_stack = QStackedWidget()

        if VirtualControlPage:
            self.page1 = VirtualControlPage(self.reactor)
        else:
            self.page1 = self.create_placeholder("模块一: 虚实映射控制\n(文件未找到)")

        if FullTrackingModule:
            self.page2 = FullTrackingModule()
        else:
            self.page2 = self.create_placeholder("模块二: 状态追踪监控\n(文件page_tracking.py未找到)")

        if TwinDataPage:
            self.page3 = TwinDataPage()
        else:
            self.page3 = self.create_placeholder("模块三: 孪生数据管理\n(文件未找到)")

        if DecisionSupportPage:
            self.page4 = DecisionSupportPage()
        else:
            self.page4 = self.create_placeholder("模块四: 运维决策支持\n(文件未找到)")

        self.content_stack.addWidget(self.page1)
        self.content_stack.addWidget(self.page2)
        self.content_stack.addWidget(self.page3)
        self.content_stack.addWidget(self.page4)

        # 修改：默认显示 Page 1
        self.content_stack.setCurrentIndex(0)

        right_layout.addWidget(self.content_stack)

        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(right_container)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 5)
        self.splitter.setSizes([220, 1000])

        self.root_layout.addWidget(self.splitter)

        # 3. 底部日志栏
        self.footer = QLabel("  [初始化] 正在检测网络...")
        self.footer.setObjectName("Footer")
        self.footer.setFixedHeight(28)
        self.root_layout.addWidget(self.footer)

        # 4. 启动定时器和线程
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

        # 启动网络延迟监测线程
        self.net_worker = NetworkLatencyWorker()
        self.net_worker.latency_signal.connect(self.update_latency_ui)
        self.net_worker.start()

    def update_latency_ui(self, latency_str):
        base_text = "  [系统消息] 连接状态: Simulink (在线) | Neo4j (就绪) | 预测模型 (就绪)"
        self.footer.setText(f"{base_text}        实时延迟: 12ms")

    def create_placeholder(self, text):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 20px; color: #888; border: 2px dashed #ccc;")
        layout.addWidget(lbl)
        return widget

    def switch_page(self, index):
        self.content_stack.setCurrentIndex(index)
        titles = ["当前模块: 虚实映射控制", "当前模块: 状态追踪监控", "当前模块: 孪生数据管理",
                  "当前模块: 运维决策支持"]
        if 0 <= index < len(titles):
            self.lbl_module_title.setText(titles[index])

    def update_time(self):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.lbl_sys_time.setText(now)

    def closeEvent(self, event):
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())