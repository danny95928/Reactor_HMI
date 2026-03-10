import sys
import os
import datetime
import subprocess
import platform
import re
import time
import importlib
import traceback
import socket  # 新增：用于检测端口占用

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QStackedWidget, QLabel, QPushButton,
                             QFrame, QSplitter, QApplication, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont  # ✅ 修复：导入 QFont 防止报错

# ==========================================
# 路径配置 & 导入核心通信模块
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# 尝试导入核心通信组件
try:
    from core.api_client import BackendClient
except ImportError:
    print("提示: 未找到 core.api_client 模块，系统将运行在离线模式。")
    BackendClient = None


# ==========================================
# 全局异常捕获 (防止子模块错误导致程序直接闪退)
# ==========================================
def exception_hook(exctype, value, tb):
    err_msg = "".join(traceback.format_exception(exctype, value, tb))
    print("\n" + "!" * 60)
    print("【系统核心崩溃诊断】")
    print(err_msg)
    print("!" * 60 + "\n")
    sys.exit(1)


sys.excepthook = exception_hook


# ==========================================
# 1. Go 后端计算引擎管理器 (智能启动版)
# ==========================================
class GoBackendManager(QThread):
    status_signal = pyqtSignal(str)

    def is_port_open(self, port=8080):
        """检测端口是否被占用 (避免重复启动 Go 后端)"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            # connect_ex 返回 0 表示连接成功（即端口已被占用）
            return s.connect_ex(('127.0.0.1', port)) == 0

    def run(self):
        # 1. 先检查端口
        if self.is_port_open(8080):
            self.status_signal.emit("检测到外部 Go 核心已在运行 (Attach Mode)")
            return

        # 2. 端口未占用，则启动子进程
        self.status_signal.emit("正在同步启动 Go 计算核心...")
        exe_name = "reactor_backend.exe" if platform.system().lower() == 'windows' else "reactor_backend"
        go_exe_path = os.path.join(current_dir, exe_name)

        if os.path.exists(go_exe_path):
            try:
                # 隐藏控制台窗口启动后端服务
                flags = subprocess.CREATE_NO_WINDOW if platform.system().lower() == 'windows' else 0
                self.process = subprocess.Popen(
                    [go_exe_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=current_dir,
                    creationflags=flags
                )
                self.status_signal.emit("Go 核心已启动 | Milvus 通道就绪")
            except Exception as e:
                self.status_signal.emit(f"Go 启动异常: {e}")
        else:
            # 如果没有找到二进制文件，则认为是在纯开发环境下运行
            time.sleep(0.5)
            self.status_signal.emit("Go 核心未找到 (运行在 Mock 模式)")

    def stop(self):
        # 只有是我们自己启动的进程才负责关闭
        if hasattr(self, 'process'):
            try:
                self.process.terminate()
            except:
                pass


# ==========================================
# 2. 实时网络延迟监测
# ==========================================
class NetworkLatencyWorker(QThread):
    latency_signal = pyqtSignal(str)

    def run(self):
        target = "127.0.0.1"
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        cmd = ['ping', param, '1', target]

        while True:
            try:
                startupinfo = None
                if platform.system().lower() == 'windows':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
                out, _ = proc.communicate()
                out_str = out.decode('gbk', errors='ignore')
                match = re.search(r"time[=<](\d+)ms", out_str, re.IGNORECASE)
                self.latency_signal.emit(f"{match.group(1)}ms" if match else "<1ms")
            except:
                self.latency_signal.emit("边缘连接中断")
            QThread.sleep(3)


# ==========================================
# 3. 数字孪生系统主界面
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("配制反应釜数字孪生智能监控系统 v2.0")
        self.resize(1300, 850)

        self.reactor = None
        self.loaded_modules = {}

        # === 核心：初始化与 Go 通信的 API 客户端 ===
        self.api_client = None
        if BackendClient:
            # 默认连接本地 Go 服务的 API 端口
            self.api_client = BackendClient("http://localhost:8080")
            print("[Main] 全局 API 客户端初始化完成")

        # 定义功能导航映射
        self.menu_items = [
            ("虚实映射控制", "ui.modules.page_virtual", "VirtualControlPage"),
            ("状态追踪监控", "ui.modules.page_tracking", "FullTrackingModule"),
            ("孪生数据管理", "ui.modules.page_twin", "TwinDataPage"),
            ("运维决策支持", "ui.modules.page_decision", "DecisionSupportPage")
        ]

        self.init_ui_styles()
        self.init_ui_structure()

        # 启动计时与监控服务
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)

        self.net_worker = NetworkLatencyWorker()
        self.net_worker.latency_signal.connect(self.update_latency_ui)
        self.net_worker.start()

        self.go_worker = GoBackendManager()
        self.go_worker.status_signal.connect(self.update_go_status)
        self.go_worker.start()

        # 预加载首个模块
        QTimer.singleShot(100, self.auto_load_first_page)

    def init_ui_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f8f9fa; }
            #HeaderFrame { background-color: #ffffff; border-bottom: 3px solid #007acc; }
            #HeaderTitle { font-size: 22px; font-weight: bold; color: #1a1a1a; font-family: 'Microsoft YaHei'; }
            QListWidget { background-color: #2c3e50; border: none; outline: none; }
            QListWidget::item { height: 60px; padding-left: 20px; color: #bdc3c7; border-bottom: 1px solid #34495e; }
            QListWidget::item:selected { background-color: #34495e; color: #ffffff; border-left: 5px solid #007acc; font-weight: bold; }
            #SubHeader { background-color: #ffffff; border-bottom: 1px solid #dee2e6; }
            #ModuleTitle { font-size: 16px; font-weight: bold; color: #007acc; }
            #Footer { background-color: #007acc; color: #ffffff; font-size: 12px; }
            QSplitter::handle { background-color: #dee2e6; }
        """)

    def init_ui_structure(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.root_layout = QVBoxLayout(self.central_widget)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # 头部区域
        self.header_frame = QFrame()
        self.header_frame.setObjectName("HeaderFrame")
        self.header_frame.setFixedHeight(70)
        h_layout = QHBoxLayout(self.header_frame)
        lbl_logo = QLabel("1# 反应釜数字孪生智能监控系统")
        lbl_logo.setObjectName("HeaderTitle")
        h_layout.addWidget(lbl_logo)
        h_layout.addStretch()

        btn_exit = QPushButton(" 安全退出系统 ")
        btn_exit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_exit.setStyleSheet("""
            QPushButton { border: 2px solid #e74c3c; color: #e74c3c; padding: 6px 15px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #e74c3c; color: white; }
        """)
        btn_exit.clicked.connect(self.close)
        h_layout.addWidget(btn_exit)
        self.root_layout.addWidget(self.header_frame)

        # 中间主体：Splitter 布局
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)

        # 侧边导航栏
        self.sidebar = QListWidget()
        self.sidebar.setMinimumWidth(200)
        self.sidebar.setMaximumWidth(300)
        self.sidebar.addItems([item[0] for item in self.menu_items])
        self.sidebar.currentRowChanged.connect(self.switch_page_lazy)
        self.splitter.addWidget(self.sidebar)

        # 右侧内容区
        right_container = QWidget()
        r_layout = QVBoxLayout(right_container)
        r_layout.setContentsMargins(0, 0, 0, 0)

        # 子标题栏（显示当前路径与时间）
        sub_header = QFrame();
        sub_header.setObjectName("SubHeader");
        sub_header.setFixedHeight(50)
        sh_layout = QHBoxLayout(sub_header)
        self.lbl_module_title = QLabel("系统初始化中...")
        self.lbl_module_title.setObjectName("ModuleTitle")
        self.lbl_sys_time = QLabel("00:00:00")
        self.lbl_sys_time.setStyleSheet("font-family: 'Consolas'; font-size: 14px; color: #666;")
        sh_layout.addWidget(self.lbl_module_title)
        sh_layout.addStretch();
        sh_layout.addWidget(self.lbl_sys_time)
        r_layout.addWidget(sub_header)

        # 堆叠布局：核心模块展示区
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.create_placeholder("正在连接计算引擎...", loading=True))
        r_layout.addWidget(self.content_stack)

        self.splitter.addWidget(right_container)
        self.splitter.setSizes([220, 1080])
        self.root_layout.addWidget(self.splitter)

        # 底部状态栏
        self.footer = QLabel("  [系统自检] 正在同步边缘计算节点状态...")
        self.footer.setObjectName("Footer")
        self.footer.setFixedHeight(35)
        self.root_layout.addWidget(self.footer)

    def auto_load_first_page(self):
        self.sidebar.setCurrentRow(0)

    def switch_page_lazy(self, index):
        """懒加载模块并注入 API 依赖"""
        if index < 0 or index >= len(self.menu_items): return

        name, module_path, class_name = self.menu_items[index]
        self.lbl_module_title.setText(f"当前运行模块: {name}")

        # 检查缓存
        if index in self.loaded_modules:
            self.content_stack.setCurrentWidget(self.loaded_modules[index])
            return

        try:
            print(f"[Main] 动态挂载子系统: {module_path}")
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)

            instance = None
            # 虚实映射模块通常需要 ReactorCore 硬件抽象
            if index == 0:
                if not self.reactor:
                    try:
                        core_mod = importlib.import_module("modules.reactor_core")
                        self.reactor = getattr(core_mod, "ReactorCore")()
                    except:
                        self.reactor = None
                try:
                    instance = cls(self.reactor)
                except TypeError:
                    instance = cls()
            else:
                instance = cls()

            # === 核心依赖注入：将 API 客户端下发至子页面 ===
            if self.api_client:
                instance.api_client = self.api_client
                print(f"[Main] API 通道已成功注入 {class_name}")

            self.content_stack.addWidget(instance)
            self.content_stack.setCurrentWidget(instance)
            self.loaded_modules[index] = instance

        except Exception as e:
            traceback.print_exc()
            self.content_stack.addWidget(self.create_placeholder(f"子系统挂载失败: {e}", error=True))

    def create_placeholder(self, text, loading=False, error=False):
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color = "#007acc" if loading else ("#e74c3c" if error else "#7f8c8d")
        lbl.setStyleSheet(f"font-size: 16px; color: {color}; background: #ffffff;")
        return lbl

    def update_time(self):
        self.lbl_sys_time.setText(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def update_latency_ui(self, latency_str):
        current = self.footer.text()
        prefix = current.split("|")[0] if "|" in current else "  [系统状态] 网络延时: --"
        suffix = current.split("|")[1] if "|" in current else ""
        self.footer.setText(f"  [系统状态] 链路延时: {latency_str} |{suffix}")

    def update_go_status(self, status):
        current = self.footer.text()
        prefix = current.split("|")[0] if "|" in current else "  [系统状态] 链路延时: --"
        self.footer.setText(f"{prefix} | 核心状态: {status}")

    def closeEvent(self, event):
        reply = QMessageBox.question(self, '退出确认', '确定要关闭监控系统并停止计算核心吗？',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if hasattr(self, 'go_worker'):
                self.go_worker.stop()
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 设置应用级别的图标和字体
    app.setFont(QFont("Segoe UI", 9) if platform.system() == "Windows" else QFont("Arial", 9))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())