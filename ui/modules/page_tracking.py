import sys
import random
import datetime
import math
import json
import requests  # 新增：用于调用 Go 后端 API
from collections import Counter
from time import ctime

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem,
                             QHeaderView, QFrame, QGroupBox, QApplication,
                             QPushButton, QMessageBox, QTabWidget, QProgressBar,
                             QSlider, QStyleOptionSlider, QStyle, QLineEdit, QDialog, QFormLayout, QDialogButtonBox,
                             QComboBox, QTextEdit)
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QAction
from PyQt6.QtCore import Qt, QTimer, QPointF, QThread, pyqtSignal, QRect

import pyqtgraph as pg

# === 关键修改：导入通信类 ===
try:
    from core.websocket_worker import RealtimeDataWorker
except ImportError:
    print("提示: 未找到 core.websocket_worker 模块")
    RealtimeDataWorker = None

# === 全局绘图配置 ===
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')
pg.setConfigOption('antialias', True)

# === 尝试导入 Neo4j 驱动 ===
try:
    from neo4j import GraphDatabase

    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False

# === 尝试导入 ntplib (用于 UDP NTP 时间同步) ===
try:
    import ntplib

    HAS_NTP = True
except ImportError:
    HAS_NTP = False


# ============================================================================
# 0.1 KLMS 拟合工作线程 (核心新增模块)
# ============================================================================
class KLMSFitWorker(QThread):
    """
    负责执行 KLMS (Kernel Least Mean Squares) 流式学习算法。
    如果连接到 Go 后端，则调用 API；否则在本地生成符合日化产品
    三元体系层状网络凝胶结构形成特征的模拟曲线。
    """
    result_signal = pyqtSignal(bool, dict, str)

    def __init__(self, current_data):
        super().__init__()
        self.current_data = current_data

    def run(self):
        try:
            # 1. 尝试连接 Go 后端 API (假设运行在 localhost:8080)
            payload = {"batch_id": "current_batch", "data": self.current_data}
            # 设置较短的超时，以便快速回退到演示模式
            response = requests.post("http://localhost:8080/klms", json=payload, timeout=1)

            if response.status_code == 200:
                self.result_signal.emit(True, response.json(), "Go 引擎拟合成功")
            else:
                raise Exception(f"HTTP {response.status_code}")

        except Exception as e:
            # 2. 连接失败或超时，使用本地算法生成特征曲线 (图 a82a05 风格)
            # print(f"[KLMS] 后端连接异常 ({e})，切换至本地演示模式...")
            mock_result = self.generate_gel_structure_curve(len(self.current_data))
            self.result_signal.emit(True, mock_result, "演示模式 (本地拟合)")

    def generate_gel_structure_curve(self, length):
        """
        生成模拟曲线：日化产品三元体系层状网络凝胶结构形成过程
        特征：准备期(平稳) -> 结构形成(S形上升) -> 峰值(最大粘度/温度) -> 冷却(下降)
        """
        golden = []
        fitted = []

        # 归一化时间轴，模拟整个工艺过程
        for i in range(length):
            # 将当前数据长度映射到 0-100% 的工艺进度
            t = i / max(1, length) * 100

            # --- 1. 黄金曲线 (Golden Batch) - 理想形态 ---
            if t < 20:
                # [a] 准备期 (Preparation)
                val = 25.0
            elif t < 60:
                # [b-d] 结构形成期 (Structure formation) - S形上升
                # 使用 Sigmoid 函数模拟凝胶化过程中的温度/粘度突变
                val = 25.0 + 60.0 / (1 + math.exp(-0.2 * (t - 40)))
            elif t < 80:
                # [d-e] 峰值/保温
                val = 85.0
            else:
                # [f-g] 冷却期 (Cooling)
                val = 85.0 - (t - 80) * 2.0

            golden.append(val)

            # --- 2. KLMS 拟合曲线 (Fitted) ---
            # 模拟算法在线学习过程，带有一定的噪声和跟随滞后
            noise = random.uniform(-1.0, 1.0)
            fit_val = val + noise

            # 在剧烈变化区 (S形上升段)，拟合通常会有轻微滞后或偏差
            if 30 < t < 50:
                fit_val -= 2.5

            fitted.append(fit_val)

        return {"golden_curve": golden, "fitted_curve": fitted}


# ============================================================================
# 0.2 Neo4j 连接管理类 (修复握手失败版)
# ============================================================================
class Neo4jHandler:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Neo4jHandler, cls).__new__(cls)
            cls._instance.driver = None
            # 修改 1: 强制使用 127.0.0.1，避免 localhost 解析到 IPv6 导致连接被重置
            cls._instance.uri = "bolt://127.0.0.1:7687"
            cls._instance.auth = ("neo4j", "password")
        return cls._instance

    def connect(self):
        if not HAS_NEO4J: return False, "未安装 neo4j 库"
        try:
            if self.driver: self.driver.close()

            # 修改 2: 显式添加 encrypted=False
            # Docker 本地开发环境通常没有配置 SSL 证书，开启加密会导致握手失败
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=self.auth,
                encrypted=False
            )

            self.driver.verify_connectivity()
            return True, "连接成功"
        except Exception as e:
            return False, f"连接错误: {str(e)}"

    def upload_log(self, time_str, state_str):
        if not self.driver: return False, "未连接数据库"
        main_category = state_str
        sub_reason = None
        if " - " in state_str:
            parts = state_str.split(" - ")
            main_category = parts[0]
            sub_reason = parts[1]
        try:
            with self.driver.session() as session:
                query = """
                CREATE (e:Event {time: $time, full_log: $full_log, created_at: datetime()})
                MERGE (c:Category {name: $category})
                FOREACH (ignoreMe IN CASE WHEN $reason IS NOT NULL THEN [1] ELSE [] END |
                    MERGE (r:StopReason {name: $reason})
                    MERGE (r)-[:BELONGS_TO]->(c)
                    CREATE (e)-[:DUE_TO]->(r)
                )
                FOREACH (ignoreMe IN CASE WHEN $reason IS NULL THEN [1] ELSE [] END |
                    CREATE (e)-[:IS_STATE]->(c)
                )
                RETURN elementId(e) as node_id
                """
                session.run(query, time=time_str, full_log=state_str, category=main_category, reason=sub_reason)
                return True, "Success"
        except Exception as e:
            return False, str(e)

    def close(self):
        if self.driver: self.driver.close()


# === 修复点：确保 Neo4jWorker 定义在被调用之前 ===
class Neo4jWorker(QThread):
    finished_signal = pyqtSignal(bool, str)
    status_signal = pyqtSignal(str)

    def run(self):
        if not HAS_NEO4J:
            self.finished_signal.emit(False, "未安装 neo4j Python 库")
            return
        try:
            self.status_signal.emit("正在连接...")
            handler = Neo4jHandler()
            success, msg = handler.connect()
            self.finished_signal.emit(success, msg)
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class UploadButtonWidget(QWidget):
    def __init__(self, time_str, state_str, parent=None):
        super().__init__(parent)
        self.time_str = time_str
        self.state_str = state_str
        l = QHBoxLayout(self)
        l.setContentsMargins(2, 2, 2, 2)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn = QPushButton("☁️ 上传")
        self.btn.setStyleSheet("""
            QPushButton { background-color:#F44336; color:white; border-radius:4px; font-weight:bold; font-size:11px; padding: 4px; }
            QPushButton:disabled { background-color:#ccc; }
        """)
        self.btn.clicked.connect(self.on_click)
        l.addWidget(self.btn)

    def on_click(self):
        self.btn.setEnabled(False)
        self.btn.setText("...")
        handler = Neo4jHandler()
        success, msg = handler.upload_log(self.time_str, self.state_str)
        if success:
            self.btn.setText("✅")
            self.btn.setStyleSheet("background-color:#4CAF50; color:white; border-radius:4px;")
        else:
            self.btn.setEnabled(True)
            self.btn.setText("重试")


# ============================================================================
# 0.3 NTP (UDP) 时间同步工作线程
# ============================================================================
class NtpWorker(QThread):
    # 信号: (是否成功, 时间字符串/错误信息, 偏差值)
    result_signal = pyqtSignal(bool, str, float)

    def run(self):
        if not HAS_NTP:
            self.result_signal.emit(False, "未安装 ntplib 库", 0.0)
            return

        try:
            client = ntplib.NTPClient()
            # 使用阿里云 NTP 服务器
            ntp_server = 'ntp.aliyun.com'
            response = client.request(ntp_server, timeout=5)
            ntp_time_str = ctime(response.tx_time)
            offset = response.offset
            self.result_signal.emit(True, ntp_time_str, offset)
        except Exception as e:
            print(f"NTP同步错误: {e}")
            self.result_signal.emit(False, str(e), 0.0)


# ============================================================================
# 1. Tab 1: 状态追踪与拓扑图
# ============================================================================

# === 配方上下文面板 ===
class RecipeContextPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            RecipeContextPanel { background-color: #f8f9fa; border: 1px solid #ddd; border-radius: 6px; }
            QLabel { color: #333; }
            QLabel[class="title"] { font-size: 14px; font-weight: bold; color: #0d47a1; }
            QLabel[class="label"] { font-weight: bold; color: #555; }
            QLabel[class="value"] { color: #000; }
            QTextEdit[class="desc"] { font-style: italic; color: #444; background: #e3f2fd; padding: 5px; border-radius: 4px; }
        """)
        layout = QVBoxLayout(self)
        self.lbl_title = QLabel("洗发水Standard_Batch_A")
        self.lbl_title.setProperty("class", "title")
        layout.addWidget(self.lbl_title)
        grid = QFormLayout()
        grid.setSpacing(8)
        self.lbl_recipe_name = QLabel("Standard_Batch_A")
        self.lbl_step_name = QLabel("初始化")
        self.lbl_target_val = QLabel("---")
        self.lbl_ingredients = QLabel("---")

        def create_styled_label(text, style_class):
            l = QLabel(text)
            l.setProperty("class", style_class)
            return l

        grid.addRow(create_styled_label("执行配方:", "label"), self.lbl_recipe_name)
        grid.addRow(create_styled_label("当前工序:", "label"), self.lbl_step_name)
        grid.addRow(create_styled_label("目标设定(SP):", "label"), self.lbl_target_val)
        grid.addRow(create_styled_label("涉及物料:", "label"), self.lbl_ingredients)
        layout.addLayout(grid)
        layout.addWidget(create_styled_label("备注:", "label"))
        self.txt_explanation = QTextEdit()
        self.txt_explanation.setReadOnly(True)
        self.txt_explanation.setFixedHeight(80)
        self.txt_explanation.setProperty("class", "desc")
        self.txt_explanation.setStyleSheet("border: none; background: #e3f2fd; font-size: 12px;")
        layout.addWidget(self.txt_explanation)
        layout.addStretch()

    def update_context(self, state_name, recipe_data):
        info = recipe_data.get(state_name, recipe_data.get("default", {
            "target_temp": 0.0, "materials": "-", "logic_desc": "无描述"
        }))
        self.lbl_step_name.setText(state_name)
        self.lbl_target_val.setText(f"{info['target_temp']} °C")
        self.lbl_ingredients.setText(info['materials'])
        self.txt_explanation.setText(info['logic_desc'])


class StateMachineWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(350)
        self.setMouseTracking(True)
        self.current_state = "空转"
        self.zoom_level = 1.0
        self.node_radius_main = 35
        self.node_radius_leaf = 22
        self.dragging_node_key = None
        self.hovered_node_key = None
        self.main_nodes = {
            "计划内停机": {"label": "计划内停机", "pos": [0.2, 0.25], "type": "downtime"},
            "空转": {"label": "空转", "pos": [0.2, 0.55], "type": "main"},
            "计划外停机": {"label": "计划外停机", "pos": [0.2, 0.85], "type": "downtime"},
            "加热": {"label": "加热", "pos": [0.45, 0.55], "type": "process"},
            "混合": {"label": "混合", "pos": [0.65, 0.55], "type": "process"},
            "反应": {"label": "反应", "pos": [0.85, 0.55], "type": "process"}
        }
        self.connections = [("计划内停机", "空转"), ("计划外停机", "空转"), ("空转", "加热"), ("加热", "混合"),
                            ("混合", "反应")]
        self.leaf_data = {"计划内停机": ["设备调试", "清场", "午休", "维护"],
                          "计划外停机": ["突发故障", "缺料", "断电"]}

    def set_state(self, s):
        self.current_state = s
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.zoom_level *= 1.1 if delta > 0 else 0.9
        self.zoom_level = max(0.5, min(self.zoom_level, 2.0))
        self.update()

    def transform_pos_to_logical(self, screen_pos):
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        return ((screen_pos.x() - cx) / self.zoom_level + cx) / w, ((screen_pos.y() - cy) / self.zoom_level + cy) / h

    def transform_pos_to_screen(self, lx, ly):
        w, h = self.width(), self.height();
        cx, cy = w / 2, h / 2
        return QPointF((lx * w - cx) * self.zoom_level + cx, (ly * h - cy) * self.zoom_level + cy)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            n = self._get_node_at_pos(e.position())
            if n: self.dragging_node_key = n; self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self.dragging_node_key:
            lx, ly = self.transform_pos_to_logical(e.position())
            self.main_nodes[self.dragging_node_key]["pos"] = [max(0.05, min(lx, 0.95)), max(0.05, min(ly, 0.95))]
            self.update()
            return
        n = self._get_node_at_pos(e.position())
        if n and n != self.hovered_node_key:
            self.hovered_node_key = n;
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif not n and self.hovered_node_key:
            self.hovered_node_key = None;
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragging_node_key = None
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if self._get_node_at_pos(e.position()) else Qt.CursorShape.ArrowCursor)

    def _get_node_at_pos(self, p):
        vr = self.node_radius_main * self.zoom_level
        for k, n in self.main_nodes.items():
            sp = self.transform_pos_to_screen(n["pos"][0], n["pos"][1])
            if math.sqrt((p.x() - sp.x()) ** 2 + (p.y() - sp.y()) ** 2) <= vr: return k
        return None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        p.translate(cx, cy);
        p.scale(self.zoom_level, self.zoom_level);
        p.translate(-cx, -cy)

        p.setPen(QPen(QColor("#ddd"), 2))
        for s, e in self.connections:
            p1, p2 = self.main_nodes[s]["pos"], self.main_nodes[e]["pos"]
            p.drawLine(QPointF(w * p1[0], h * p1[1]), QPointF(w * p2[0], h * p2[1]))

        leaf_positions = self._calc_leaf_positions(w, h)
        for parent_key, leaves in leaf_positions.items():
            parent_pos = self.main_nodes[parent_key]["pos"]
            p_center = QPointF(w * parent_pos[0], h * parent_pos[1])
            for leaf_name, leaf_pos in leaves:
                p.setPen(QPen(QColor("#eee"), 1, Qt.PenStyle.DashLine))
                p.drawLine(p_center, leaf_pos)
                is_leaf_active = (leaf_name == self.current_state)
                fill = QColor("#ff9800") if is_leaf_active else QColor("#f5f5f5")
                border = QColor("#ef6c00") if is_leaf_active else QColor("#ccc")
                txt_c = Qt.GlobalColor.white if is_leaf_active else QColor("#666")
                radius = self.node_radius_leaf + 3 if is_leaf_active else self.node_radius_leaf
                p.setBrush(QBrush(fill));
                p.setPen(QPen(border, 2 if is_leaf_active else 1))
                p.drawEllipse(leaf_pos, radius, radius)
                p.setPen(QPen(txt_c))
                p.setFont(QFont("Microsoft YaHei", 7, QFont.Weight.Bold if is_leaf_active else QFont.Weight.Normal))
                p.drawText(QRect(int(leaf_pos.x() - 30), int(leaf_pos.y() - 15), 60, 30), Qt.AlignmentFlag.AlignCenter,
                           leaf_name)

        for k, n in self.main_nodes.items():
            is_direct_active = (k == self.current_state)
            is_parent_active = (k in self.leaf_data and self.current_state in self.leaf_data[k])
            if is_direct_active:
                fill = QColor("#ff5722" if n["type"] == "downtime" else "#007acc")
                border = QColor("darkred" if n["type"] == "downtime" else "darkblue")
                txt_c = Qt.GlobalColor.white
            elif is_parent_active:
                fill = QColor("#ffccbc");
                border = QColor("#ff5722");
                txt_c = QColor("#d84315")
            else:
                fill = Qt.GlobalColor.white;
                border = QColor("#ccc");
                txt_c = QColor("#555")

            cp = QPointF(w * n["pos"][0], h * n["pos"][1])
            if k == self.dragging_node_key:
                p.setPen(Qt.PenStyle.NoPen);
                p.setBrush(QColor(0, 0, 0, 50))
                p.drawEllipse(QPointF(cp.x() + 5, cp.y() + 5), self.node_radius_main, self.node_radius_main)

            p.setBrush(QBrush(fill));
            p.setPen(QPen(border, 3 if is_direct_active else (2 if is_parent_active else 2)))
            p.drawEllipse(cp, self.node_radius_main, self.node_radius_main)
            p.setPen(QPen(txt_c))
            p.setFont(QFont("Microsoft YaHei", 8,
                            QFont.Weight.Bold if (is_direct_active or is_parent_active) else QFont.Weight.Normal))
            p.drawText(QRect(int(cp.x() - 45), int(cp.y() - 20), 90, 40), Qt.AlignmentFlag.AlignCenter, n["label"])

    def _calc_leaf_positions(self, w, h):
        results = {}
        configs = {"计划内停机": (190, 350, 110), "计划外停机": (10, 170, 110)}
        for p_key, leaves in self.leaf_data.items():
            if p_key not in self.main_nodes: continue
            p_node = self.main_nodes[p_key]
            center = QPointF(w * p_node["pos"][0], h * p_node["pos"][1])
            results[p_key] = []
            start_ang, end_ang, radius = configs.get(p_key, (0, 360, 100))
            count = len(leaves)
            for i, text in enumerate(leaves):
                angle = (start_ang + end_ang) / 2 if count <= 1 else start_ang + i * (end_ang - start_ang) / (count - 1)
                rad = math.radians(angle)
                results[p_key].append(
                    (text, QPointF(center.x() + radius * math.cos(rad), center.y() + radius * math.sin(rad))))
        return results


class StateTrackingPage(QWidget):
    def __init__(self):
        super().__init__()

        self.recipe_db = {
            "空转": {
                "target_temp": 25.0,
                "materials": "无 (系统待机)",
                "logic_desc": "工艺说明：设备处于低功耗待机模式。此时监测温度应接近室温，若温度过高则提示散热异常。"
            },
            "加热": {
                "target_temp": 85.0,
                "materials": "去离子水 + 1618醇",
                "logic_desc": "工艺说明：升温熔化固态脂肪醇。关键控制点：温度需保持 >80°C 以确保油脂完全熔化，为乳化做准备。"
            },
            "混合": {
                "target_temp": 85.0,
                "materials": "基质 + 表面活性剂",
                "logic_desc": "工艺说明：恒温高速剪切。在此阶段保持高温是为了降低体系粘度，确保表面活性剂均匀分散。"
            },
            "反应": {
                "target_temp": 82.0,
                "materials": "全组分 (含催化剂)",
                "logic_desc": "工艺说明：放热反应阶段。虽然设定值为82°C，但由于反应放热，实际温度可能出现超调，需开启冷却水微调。"
            },
            "default": {
                "target_temp": 0.0,
                "materials": "未知",
                "logic_desc": "停机或未知状态，请检查设备连接。"
            }
        }

        self.current_real_temp = 25.0
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)
        self.timer_interval_ms = 500
        self.hold_duration_sec = 2 * 60
        self.current_hold_counter = 0
        self.next_state_name = "空转"
        self.stage_markers = []

        # 存储 KLMS 曲线句柄
        self.klms_curves = []

        self.init_top_section()
        self.init_bottom_area()

        self.data_x = list(range(100));
        self.data_y = [25.0] * 100;
        self.ptr = 100
        self.current_target = 25.0

        self.timer = QTimer();
        self.timer.timeout.connect(self.update_data);
        self.timer.start(self.timer_interval_ms)

        self.sm_widget.set_state(self.next_state_name)
        self.update_recipe_ui()

    def init_top_section(self):
        top_container = QWidget()
        h_layout = QHBoxLayout(top_container)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(10)

        gb_style = """
            QGroupBox { 
                background-color: white; 
                border: 1px solid #ccc; 
                border-radius: 5px; 
                font-weight: bold; 
                color: #333; 
                padding-top: 5px; 
                margin-top: 10px; 
            }
            QGroupBox::title { 
                subcontrol-origin: margin; 
                subcontrol-position: top left; 
                left: 10px; 
                padding: 0 5px; 
            }
        """

        gb_chart = QGroupBox("实时温度趋势 (关联配方设定)")
        gb_chart.setStyleSheet(gb_style)
        l_chart = QVBoxLayout(gb_chart)
        l_chart.setContentsMargins(10, 2, 10, 10)

        ntp_layout = QHBoxLayout()
        ntp_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_sync_ntp = QPushButton("⏱️ NTP 同步")
        self.btn_sync_ntp.setFixedWidth(100)
        self.btn_sync_ntp.setStyleSheet("""
            QPushButton { background-color:#673AB7; color:white; border-radius:3px; font-weight:bold; padding: 2px;}
            QPushButton:hover { background-color:#5E35B1; }
        """)
        self.btn_sync_ntp.clicked.connect(self.start_ntp_sync)

        # 新增 KLMS 拟合按钮
        self.btn_klms = QPushButton("🌊 KLMS 拟合")
        self.btn_klms.setFixedWidth(100)
        self.btn_klms.setStyleSheet("""
            QPushButton { background-color:#FF9800; color:white; border-radius:3px; font-weight:bold; padding: 2px;}
            QPushButton:hover { background-color:#F57C00; }
        """)
        self.btn_klms.setToolTip("调用 Go 引擎进行流式学习，拟合层状网络凝胶结构曲线")
        self.btn_klms.clicked.connect(self.start_klms_fitting)

        self.lbl_ntp_status = QLabel("NTP: 未同步")
        self.lbl_ntp_status.setStyleSheet("color: #555; margin-left: 5px; font-size: 11px;")
        self.lbl_ntp_offset = QLabel("偏差: --")
        self.lbl_ntp_offset.setStyleSheet("color: #E91E63; font-weight:bold; margin-left: 10px; font-size: 11px;")

        ntp_layout.addWidget(self.btn_sync_ntp)
        ntp_layout.addWidget(self.btn_klms)  # 添加按钮到布局
        ntp_layout.addWidget(self.lbl_ntp_status)
        ntp_layout.addWidget(self.lbl_ntp_offset)
        ntp_layout.addStretch()
        l_chart.addLayout(ntp_layout)

        self.lbl_timer = QLabel(f"状态保持中... ")
        self.lbl_timer.setStyleSheet("color: #666; font-size: 12px; margin-bottom: 5px;")
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignRight)
        l_chart.addWidget(self.lbl_timer)

        self.plot = pg.PlotWidget()
        self.plot.setBackground('w')
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.addLegend(offset=(50, 10))
        self.plot.setYRange(-10, 140, padding=0)

        self.curve = self.plot.plot(name="实际温度 PV", pen=pg.mkPen('#007acc', width=2))

        self.target_line = pg.InfiniteLine(
            pos=25,
            angle=0,
            pen=pg.mkPen('#F44336', width=2, style=Qt.PenStyle.DashLine),
            label="配方设定 SP: {value:0.1f}°C",
            labelOpts={'position': 0.8, 'color': '#D32F2F', 'movable': True, 'fill': (255, 255, 255, 200)}
        )
        self.plot.addItem(self.target_line)
        l_chart.addWidget(self.plot)
        h_layout.addWidget(gb_chart, stretch=2)

        gb_recipe = QGroupBox("当前配方工艺")
        gb_recipe.setStyleSheet(gb_style)
        l_recipe = QVBoxLayout(gb_recipe)
        l_recipe.setContentsMargins(0, 2, 0, 0)
        self.recipe_panel = RecipeContextPanel()
        self.recipe_panel.setStyleSheet(
            "RecipeContextPanel { background: transparent; border: none; } " + self.recipe_panel.styleSheet())
        l_recipe.addWidget(self.recipe_panel)
        h_layout.addWidget(gb_recipe, stretch=1)
        self.layout.addWidget(top_container, stretch=3)

    def init_bottom_area(self):
        container = QWidget();
        h_layout = QHBoxLayout(container);
        h_layout.setContentsMargins(0, 0, 0, 0)
        gb_left = QGroupBox("OEE 状态拓扑")
        gb_left.setStyleSheet("""
            QGroupBox { background-color: white; border: 1px solid #ccc; border-radius: 5px; margin-top: 10px; font-weight: bold; color: #333; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
        """)
        l_left = QVBoxLayout(gb_left)
        btn_layout = QHBoxLayout();
        btn_layout.addStretch()
        self.btn_neo = QPushButton("🔌 连接 Neo4j")
        self.btn_neo.setStyleSheet(
            "QPushButton{background:#2196F3; color:white; padding:5px 10px; border-radius:3px; font-weight:bold;}")
        self.btn_neo.clicked.connect(self.conn_neo4j)
        btn_layout.addWidget(self.btn_neo);
        l_left.addLayout(btn_layout)
        self.sm_widget = StateMachineWidget()
        l_left.addWidget(self.sm_widget)
        h_layout.addWidget(gb_left, stretch=2)

        gb_right = QGroupBox("异常事件日志")
        gb_right.setStyleSheet("""
            QGroupBox { background-color: white; border: 1px solid #ccc; border-radius: 5px; margin-top: 10px; font-weight: bold; color: #333; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
        """)
        l_right = QVBoxLayout(gb_right)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["时间", "详细状态", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(2, 80);
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget { border: none; font-size: 12px; color: #000000; background-color: white; gridline-color: #eee; }
            QHeaderView::section { background-color: #f0f0f0; border: none; height: 30px; color: #000000; font-weight: bold; border-bottom: 1px solid #ccc; }
            QTableWidget::item { color: #000000; padding-left: 5px; }
        """)
        l_right.addWidget(self.table)
        h_layout.addWidget(gb_right, stretch=1)
        self.layout.addWidget(container, stretch=2)

    def conn_neo4j(self):
        if not HAS_NEO4J:
            QMessageBox.critical(self, "错误", "未安装 neo4j 库");
            return
        self.btn_neo.setEnabled(False);
        self.btn_neo.setText("连接中...")
        self.nw = Neo4jWorker()
        self.nw.status_signal.connect(lambda s: self.btn_neo.setText(s))
        self.nw.finished_signal.connect(self.on_conn_res)
        self.nw.start()

    def on_conn_res(self, s, m):
        if s:
            self.btn_neo.setText("✅ 已连接");
            QMessageBox.information(self, "成功", m)
        else:
            self.btn_neo.setEnabled(True);
            self.btn_neo.setText("🔌 连接 Neo4j");
            QMessageBox.warning(self, "错误", m)

    def start_ntp_sync(self):
        self.btn_sync_ntp.setEnabled(False)
        self.btn_sync_ntp.setText("同步中...")
        self.ntp_thread = NtpWorker()
        self.ntp_thread.result_signal.connect(self.on_ntp_result)
        self.ntp_thread.start()

    def on_ntp_result(self, success, msg, offset):
        self.btn_sync_ntp.setEnabled(True)
        self.btn_sync_ntp.setText("⏱️ NTP 同步")
        if success:
            self.lbl_ntp_status.setText(f"NTP: {msg.split(' ')[3]}")
            self.lbl_ntp_offset.setText(f"偏差: {offset:.6f} s")
            QMessageBox.information(self, "同步成功",
                                    f"NTP 时间: {msg}\n本地偏差: {offset:.6f} 秒\n(已使用 UDP 协议校准)")
        else:
            self.lbl_ntp_status.setText("NTP: 失败")
            QMessageBox.warning(self, "同步失败", msg)

    # === KLMS 拟合逻辑 ===
    def start_klms_fitting(self):
        self.btn_klms.setText("计算中...")
        self.btn_klms.setEnabled(False)

        # 取出当前缓冲区的所有数据作为样本
        sample_data = self.data_y[:]

        self.klms_worker = KLMSFitWorker(sample_data)
        self.klms_worker.result_signal.connect(self.on_klms_result)
        self.klms_worker.start()

    def on_klms_result(self, success, result, msg):
        self.btn_klms.setText("🌊 KLMS 拟合")
        self.btn_klms.setEnabled(True)

        if not success:
            QMessageBox.warning(self, "拟合失败", msg)
            return

        # 1. 清除上一次的拟合曲线
        for curve_item in self.klms_curves:
            self.plot.removeItem(curve_item)
        self.klms_curves.clear()

        # 2. 绘制黄金曲线 (Golden Batch) - 绿色实线
        golden_data = result.get("golden_curve", [])
        if golden_data:
            # 这里的 x 坐标与当前实时数据对齐
            x_vals = [self.ptr - len(golden_data) + i for i in range(len(golden_data))]
            c1 = self.plot.plot(x_vals, golden_data,
                                pen=pg.mkPen('g', width=2),
                                name="黄金批次 (Golden)")
            self.klms_curves.append(c1)

        # 3. 绘制 KLMS 拟合曲线 - 红色虚线
        fitted_data = result.get("fitted_curve", [])
        if fitted_data:
            x_vals = [self.ptr - len(fitted_data) + i for i in range(len(fitted_data))]
            c2 = self.plot.plot(x_vals, fitted_data,
                                pen=pg.mkPen('r', width=2, style=Qt.PenStyle.DotLine),
                                name="KLMS 拟合")
            self.klms_curves.append(c2)

        QMessageBox.information(self, "拟合完成", f"{msg}\n已在图表中叠加显示凝胶结构拟合曲线。")

    def ingest_data(self, temp_val):
        self.current_real_temp = temp_val

    def update_data(self):
        new_val = self.current_real_temp
        self.data_y.pop(0);
        self.data_y.append(new_val)
        self.data_x.pop(0);
        self.data_x.append(self.ptr);
        self.ptr += 1

        self.curve.setData(self.data_x, self.data_y)

        min_x = self.data_x[0]
        active_markers = []
        for line, label, pos_x in self.stage_markers:
            if pos_x < min_x:
                self.plot.removeItem(line)
                self.plot.removeItem(label)
            else:
                active_markers.append((line, label, pos_x))
        self.stage_markers = active_markers

        self.current_hold_counter += 1
        self.lbl_timer.setText(f"当前状态: {self.next_state_name} ({self.current_hold_counter}s)")

        if self.current_hold_counter >= self.hold_duration_sec:
            self.current_hold_counter = 0
            self.transition_state()

    def update_recipe_ui(self):
        state_key = self.next_state_name
        if state_key in self.recipe_db:
            info = self.recipe_db[state_key]
        else:
            info = self.recipe_db["空转"]
        self.current_target = info["target_temp"]
        self.target_line.setPos(self.current_target)
        self.recipe_panel.update_context(state_key, self.recipe_db)

    def transition_state(self):
        roll = random.random()
        if roll < 0.2:
            next_state = random.choice(self.sm_widget.leaf_data["计划内停机"])
            parent_state = "计划内停机"
        elif roll < 0.4:
            next_state = random.choice(self.sm_widget.leaf_data["计划外停机"])
            parent_state = "计划外停机"
        else:
            next_state = random.choice(["空转", "加热", "混合", "反应"])
            parent_state = next_state

        self.next_state_name = next_state
        self.sm_widget.set_state(next_state)

        v_line = pg.InfiniteLine(pos=self.ptr, angle=90, movable=False,
                                 pen=pg.mkPen('#777', width=1, style=Qt.PenStyle.DashLine))
        label = pg.TextItem(text=f"▶ {next_state}", anchor=(0, 1), color='#333333')
        label.setPos(self.ptr, 125)

        self.plot.addItem(v_line)
        self.plot.addItem(label)
        self.stage_markers.append((v_line, label, self.ptr))
        self.update_recipe_ui()

        if parent_state in ["计划内停机", "计划外停机"]:
            upload_str = f"{parent_state} - {next_state}"
            display_str = next_state
        else:
            display_str = next_state
            upload_str = next_state
        self.add_log(datetime.datetime.now().strftime("%H:%M:%S"), display_str, upload_str)

    def add_log(self, t, d, u):
        r = self.table.rowCount();
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(t))
        self.table.setItem(r, 1, QTableWidgetItem(d))
        if "停机" in u:
            self.table.setCellWidget(r, 2, UploadButtonWidget(t, u))
        else:
            self.table.setItem(r, 2, QTableWidgetItem(""))
        self.table.scrollToBottom()


# ============================================================================
# 2. Tab 2: 时间切片 (TimeSlicePage) - 优化版 (后端驱动)
# ============================================================================
class TimeSlicePage(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        # --- 顶部状态栏 ---
        self.panel = QFrame()
        self.panel.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ccc; border-radius: 4px; color: #333;")
        pl = QHBoxLayout(self.panel)

        self.lbl_idx = QLabel("等待后端切片数据...")
        self.lbl_idx.setStyleSheet("font-weight: bold; font-size: 13px; color: #000;")

        self.pbar = QProgressBar()
        self.pbar.setFixedWidth(200)
        self.pbar.setTextVisible(True)
        self.pbar.setStyleSheet("""QProgressBar { border: 1px solid #999; border-radius: 3px; background: white; color: black; text-align: center; }
            QProgressBar::chunk { background-color: #FF9800; width: 10px; }""")

        self.lbl_stats = QLabel("暂无归档数据")
        self.lbl_stats.setStyleSheet("color: #555; margin-left: 20px;")

        pl.addWidget(self.lbl_idx)
        pl.addWidget(self.pbar)
        pl.addWidget(self.lbl_stats)
        pl.addStretch()
        self.layout.addWidget(self.panel)

        # --- 中部图表 (优化版) ---
        self.plot = pg.PlotWidget()
        self.plot.setBackground('w')
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel('left', '温度', units='C', color='k')
        self.plot.setClipToView(True)
        self.plot.setDownsampling(mode='peak')

        self.curve = self.plot.plot(pen=pg.mkPen('#FF9800', width=2))
        self.layout.addWidget(self.plot, stretch=2)

        # --- 底部表格 ---
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["切片ID", "开始时间", "平均温度", "极值 (Min/Max)", "持续时长"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""QTableWidget { border: 1px solid #ccc; font-size: 12px; color: #000; background-color: white; }
            QHeaderView::section { background-color: #f0f0f0; border: none; height: 30px; color: #000; font-weight: bold; border-bottom: 1px solid #ccc; }
            QTableWidget::item { color: #000; padding-left: 5px; }""")
        self.layout.addWidget(self.table, stretch=1)

        # 数据缓存 (用于绘图，设置上限)
        self.max_points = 2000
        self.data_x = []
        self.data_y = []
        self.ptr = 0

    def update_realtime_curve(self, temp_val):
        """仅更新曲线，不做切片计算"""
        self.data_x.append(self.ptr)
        self.data_y.append(temp_val)
        self.ptr += 1

        if len(self.data_x) > self.max_points:
            self.data_x = self.data_x[-self.max_points:]
            self.data_y = self.data_y[-self.max_points:]

        self.curve.setData(self.data_x, self.data_y)
        curr_val = self.pbar.value()
        self.pbar.setValue((curr_val + 1) % 100)

    def on_slice_received(self, slice_data):
        """当收到后端 type='slice' 消息时调用"""
        s_id = slice_data.get("id", -1)
        avg = slice_data.get("avg_temp", 0.0)
        max_v = slice_data.get("max_temp", 0.0)
        min_v = slice_data.get("min_temp", 0.0)
        start_t = slice_data.get("start_time", "--")
        dur = slice_data.get("duration", 0)

        self.lbl_idx.setText(f"上一切片: #{s_id}")
        self.lbl_stats.setText(f"✅ 归档完成: 均值 {avg:.2f}°C")
        self.pbar.setValue(100)

        v = pg.InfiniteLine(pos=self.ptr, angle=90, pen=pg.mkPen('#555', width=1, style=Qt.PenStyle.DashLine),
                            label=f"Slice #{s_id}",
                            labelOpts={'position': 0.9, 'color': '#333', 'movable': True})
        self.plot.addItem(v)

        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(f"#{s_id}"))
        self.table.setItem(r, 1, QTableWidgetItem(str(start_t)))
        self.table.setItem(r, 2, QTableWidgetItem(f"{avg:.2f} °C"))
        self.table.setItem(r, 3, QTableWidgetItem(f"{min_v:.1f} / {max_v:.1f}"))
        self.table.setItem(r, 4, QTableWidgetItem(f"{dur} 秒"))
        self.table.scrollToBottom()


# ============================================================================
# 3. Tab 3: FSM 逻辑定义 (Simulink 风格 - 全中文)
# ============================================================================
class LogicBlockEditorDialog(QDialog):
    def __init__(self, block_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑逻辑块")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit(block_data.get("name", ""))
        self.tag_edit = QLineEdit(block_data.get("tag", ""))
        self.cond_edit = QLineEdit(block_data.get("cond", ""))
        layout.addRow("名称:", self.name_edit)
        layout.addRow("标签:", self.tag_edit)
        layout.addRow("条件描述:", self.cond_edit)
        self.logic_type_combo = QComboBox()
        self.logic_type_combo.addItems(["范围 (min <= x <= max)", "等于 (x == val)", "小于 (x < val)", "始终 False"])
        layout.addRow("逻辑类型:", self.logic_type_combo)
        self.param1_edit = QLineEdit()
        self.param2_edit = QLineEdit()
        self.target_var_edit = QComboBox()
        self.target_var_edit.addItems(["temp", "rpm", "flow"])
        layout.addRow("目标变量:", self.target_var_edit)
        layout.addRow("参数 1:", self.param1_edit)
        layout.addRow("参数 2 (仅范围):", self.param2_edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self):
        l_type = self.logic_type_combo.currentText()
        var = self.target_var_edit.currentText()
        try:
            p1 = float(self.param1_edit.text()) if self.param1_edit.text() else 0
            p2 = float(self.param2_edit.text()) if self.param2_edit.text() else 0
        except ValueError:
            p1, p2 = 0, 0
        new_check = lambda d: False
        if "范围" in l_type:
            new_check = lambda d: p1 <= d[var] <= p2
        elif "等于" in l_type:
            new_check = lambda d: d[var] == p1
        elif "小于" in l_type:
            new_check = lambda d: d[var] < p1
        return {
            "name": self.name_edit.text(),
            "tag": self.tag_edit.text(),
            "cond": self.cond_edit.text(),
            "check": new_check
        }


class FSMVisualizer(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(450)
        self.inputs = {"temp": 15, "rpm": 0, "flow": 0, "active_state": "IDLE"}
        self.fsm_config = {
            "IDLE": {
                "label": "状态: IDLE (设备空转)",
                "rect": QRect(50, 60, 280, 360),
                "logic_blocks": [
                    {"name": "逻辑块 [类1-A]", "tag": "T_1020", "cond": "10 <= 温度 <= 20\nPH_2",
                     "check": lambda d: 10 <= d['temp'] <= 20},
                    {"name": "逻辑块 [类2-B]", "tag": "N_0020", "cond": "转速 < 5\n(电机正常)",
                     "check": lambda d: d['rpm'] < 5},
                    {"name": "逻辑块 [类3-C]", "tag": "Flow_Zero", "cond": "流量 == 0",
                     "check": lambda d: d['flow'] == 0},
                ]
            },
            "RUNNING": {
                "label": "状态: RUNNING (设备运行)",
                "rect": QRect(400, 60, 280, 360),
                "logic_blocks": [
                    {"name": "逻辑块 [类2-C]", "tag": "Flow_Mon", "cond": "流量 == 0\n(异常前兆)",
                     "check": lambda d: d['flow'] == 0},
                    {"name": "逻辑块 [类4-D]", "tag": "T_Monitor", "cond": "20 <= 温度 <= 60\n(重点监控)",
                     "check": lambda d: 20 <= d['temp'] <= 60},
                    {"name": "逻辑块 [类5-E]", "tag": "N_Range", "cond": "40 <= 转速 <= 80",
                     "check": lambda d: 40 <= d['rpm'] <= 80},
                ]
            },
            "FAULT": {
                "label": "状态: FAULT (设备故障)",
                "rect": QRect(750, 60, 240, 360),
                "logic_blocks": [
                    {"name": "异常检测器", "tag": "SEQ_Err", "cond": "时序异常\n(传感器定位)",
                     "check": lambda d: False}
                ]
            }
        }

    def update_signals(self, temp, rpm, flow, state):
        self.inputs = {"temp": temp, "rpm": rpm, "flow": flow, "active_state": state}
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            for state_key, cfg in self.fsm_config.items():
                rect = cfg["rect"]
                block_h = 75
                spacing = 20
                start_y = rect.y() + 50
                for i, block in enumerate(cfg["logic_blocks"]):
                    b_rect = QRect(rect.x() + 15, start_y + i * (block_h + spacing), rect.width() - 30, block_h)
                    if b_rect.contains(pos):
                        self.edit_logic_block(state_key, i, block)
                        return

    def edit_logic_block(self, state_key, index, block_data):
        dlg = LogicBlockEditorDialog(block_data, self)
        if dlg.exec():
            new_data = dlg.get_data()
            self.fsm_config[state_key]["logic_blocks"][index] = new_data
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        self.draw_grid(p)
        font_header = QFont("Microsoft YaHei", 10, QFont.Weight.Bold)
        font_tag = QFont("Consolas", 8, QFont.Weight.Bold)
        font_detail = QFont("Microsoft YaHei", 8)
        p.setPen(QPen(QColor("#777"), 2, Qt.PenStyle.SolidLine))
        p.drawLine(330, 240, 400, 240)
        self.draw_arrow(p, QPointF(395, 240))
        p.drawLine(680, 240, 750, 240)
        self.draw_arrow(p, QPointF(745, 240))
        for state_key, cfg in self.fsm_config.items():
            rect = cfg["rect"]
            is_active = (self.inputs["active_state"] == state_key)
            if is_active:
                bg_color = QColor(225, 240, 255)
                border_color = QColor(0, 100, 200)
                border_width = 3
            else:
                bg_color = QColor(245, 245, 245)
                border_color = QColor(180, 180, 180)
                border_width = 1
            p.setBrush(QBrush(bg_color))
            p.setPen(QPen(border_color, border_width))
            p.drawRoundedRect(rect, 10, 10)
            header_h = 30
            p.setPen(QPen(border_color, 1))
            p.drawLine(rect.x(), rect.y() + header_h, rect.right(), rect.y() + header_h)
            p.setPen(QPen(QColor("#333")))
            p.setFont(font_header)
            p.drawText(QRect(rect.x() + 10, rect.y(), rect.width(), header_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, cfg["label"])
            if is_active:
                p.setBrush(QColor(0, 200, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(rect.right() - 20, rect.y() + 15), 5, 5)
            block_h = 75
            spacing = 20
            start_y = rect.y() + 50
            for i, block in enumerate(cfg["logic_blocks"]):
                cond_met = block["check"](self.inputs)
                is_blk_active = is_active and cond_met
                b_rect = QRect(rect.x() + 15, start_y + i * (block_h + spacing), rect.width() - 30, block_h)
                if is_blk_active:
                    b_bg = QColor(255, 193, 7)
                    b_border = QColor(255, 111, 0)
                    line_w = 2
                else:
                    b_bg = QColor(255, 255, 255)
                    b_border = QColor(200, 200, 200)
                    line_w = 1
                p.setBrush(QBrush(b_bg))
                p.setPen(QPen(b_border, line_w))
                p.drawRoundedRect(b_rect, 4, 4)
                p.setBrush(QColor("#555"))
                p.drawRect(b_rect.x() - 2, b_rect.y() + 15, 4, 6)
                p.drawRect(b_rect.right() - 2, b_rect.y() + 15, 4, 6)
                p.setPen(QPen(QColor("#000")))
                p.setFont(font_detail)
                p.drawText(b_rect.adjusted(10, 5, -5, 0), Qt.AlignmentFlag.AlignLeft, block["name"])
                p.setPen(QPen(QColor("#0D47A1")))
                p.setFont(font_tag)
                p.drawText(b_rect.adjusted(0, 5, -10, 0), Qt.AlignmentFlag.AlignRight, f"[{block['tag']}]")
                p.setPen(QPen(QColor("#444")))
                p.setFont(font_detail)
                desc_rect = QRect(b_rect.x() + 10, b_rect.y() + 25, b_rect.width() - 20, 45)
                p.drawText(desc_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, block["cond"])

    def draw_grid(self, p):
        p.save()
        p.setPen(QPen(QColor(240, 240, 240), 1))
        step = 20
        for x in range(0, self.width(), step): p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step): p.drawLine(0, y, self.width(), y)
        p.restore()

    def draw_arrow(self, p, tip):
        p.save()
        p.setBrush(QColor("#777"))
        p.setPen(Qt.PenStyle.NoPen)
        size = 8
        arrow = [tip, QPointF(tip.x() - size, tip.y() - size / 2), QPointF(tip.x() - size, tip.y() + size / 2)]
        p.drawPolygon(arrow)
        p.restore()


class FSMControllerPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        ctrl_grp = QGroupBox("信号接收器与状态跳转定义")
        ctrl_grp.setStyleSheet(
            "QGroupBox{font-weight:bold; border:1px solid #aaa; margin-top:10px;} QGroupBox::title{subcontrol-origin:margin; left:10px;}")
        h_layout = QHBoxLayout(ctrl_grp)
        self.sliders = {}
        controls = [("temp", "温度 Temp (°C)", 100, 15), ("rpm", "转速 RPM", 120, 0), ("flow", "流量 Flow", 100, 0)]
        for key, label, r_max, val in controls:
            v_layout = QVBoxLayout()
            lbl = QLabel(f"{label}: {val}")
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, r_max);
            sl.setValue(val)
            sl.valueChanged.connect(lambda v, k=key, l=lbl, txt=label: self.on_slider_change(k, v, l, txt))
            v_layout.addWidget(lbl)
            v_layout.addWidget(sl)
            h_layout.addLayout(v_layout)
            self.sliders[key] = sl
        v_state = QVBoxLayout()
        v_state.addWidget(QLabel("当前激活状态:"))
        self.btn_idle = QPushButton("空转 (IDLE)")
        self.btn_idle.setCheckable(True);
        self.btn_idle.setChecked(True)
        self.btn_run = QPushButton("运行 (RUNNING)")
        self.btn_run.setCheckable(True)
        self.btn_fault = QPushButton("故障 (FAULT)")
        self.btn_fault.setCheckable(True)
        self.btns = [self.btn_idle, self.btn_run, self.btn_fault]
        for b in self.btns:
            b.clicked.connect(lambda c, btn=b: self.switch_state(btn))
            v_state.addWidget(b)
        h_layout.addLayout(v_state)
        layout.addWidget(ctrl_grp)
        self.visualizer = FSMVisualizer()
        layout.addWidget(self.visualizer, stretch=1)
        desc = QLabel("状态流：点击逻辑块可编辑其条件。当条件满足时，当前激活状态内的逻辑块将高亮显示。")
        desc.setStyleSheet("color:#666; font-style:italic;")
        layout.addWidget(desc)
        self.switch_state(self.btn_idle)

    def on_slider_change(self, key, val, lbl_widget, label_text):
        lbl_widget.setText(f"{label_text}: {val}")
        self.update_viz()

    def switch_state(self, btn):
        for b in self.btns: b.setChecked(False)
        btn.setChecked(True)
        if "空转" in btn.text():
            self.sliders["temp"].setValue(15)
            self.sliders["rpm"].setValue(0)
            self.sliders["flow"].setValue(0)
        elif "运行" in btn.text():
            self.sliders["temp"].setValue(45)
            self.sliders["rpm"].setValue(60)
            self.sliders["flow"].setValue(50)
        elif "故障" in btn.text():
            self.sliders["temp"].setValue(95)
        self.update_viz()

    def update_viz(self):
        t = self.sliders["temp"].value()
        r = self.sliders["rpm"].value()
        f = self.sliders["flow"].value()
        s = "IDLE"
        if self.btn_run.isChecked():
            s = "RUNNING"
        elif self.btn_fault.isChecked():
            s = "FAULT"
        self.visualizer.update_signals(t, r, f, s)


# ============================================================================
# 主窗口整合 (增加 WebSocket 路由逻辑)
# ============================================================================
class FullTrackingModule(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: white; color: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ccc; top: -1px; }
            QTabBar::tab { 
                background: #e0e0e0; 
                color: #333; 
                padding: 6px 10px; 
                min-width: 80px;   
                max-width: 200px;  
                border: 1px solid #ccc; 
                border-bottom: none; 
                border-top-left-radius: 4px; 
                border-top-right-radius: 4px; 
                margin-right: 2px; 
                font-size: 12px;
            }
            QTabBar::tab:selected { background: #ffffff; color: #2196F3; font-weight: bold; border-bottom: 2px solid #2196F3; }
            QTabBar::tab:hover { background: #f0f0f0; }
        """)

        # 实例化页面
        self.page1 = StateTrackingPage()
        self.page2 = TimeSlicePage()
        self.page3 = FSMControllerPage()

        self.tabs.addTab(self.page1, "实时状态追踪")
        self.tabs.addTab(self.page2, "实时时间切片")
        self.tabs.addTab(self.page3, "状态跳转逻辑")

        layout.addWidget(self.tabs)

        if RealtimeDataWorker:
            self.ws_worker = RealtimeDataWorker("ws://localhost:8080/ws")
            # [Fix] on_ws_data is now a proper method
            self.ws_worker.data_received.connect(self.on_ws_data)
            self.ws_worker.start()
        else:
            self.ws_worker = None

    def on_ws_data(self, data):
        """
        核心分发逻辑 (Router) + 自动上传 Milvus
        """
        msg_type = data.get("type", "realtime")

        # 情况 A: 实时高频数据
        if msg_type == "realtime":
            # 1. 提取基础信号
            temp = data.get("temp", 0.0)
            flow = data.get("flow", 0.0)
            rpm = data.get("rpm", 0.0)  # 如果 Go 端还没发 rpm，这里默认为 0
            aging = data.get("aging_factor", 0.0)
            device_code = data.get("device_code", "R-101")

            # 2. UI 更新 (保持原有逻辑)
            self.page1.ingest_data(temp)
            self.page2.update_realtime_curve(temp)

            # === 👇👇👇 [新增] 核心上传逻辑 👇👇👇 ===

            # 3. 简单的状态判定逻辑 (模拟 FSM)
            current_state = "IDLE"
            if temp > 90:
                current_state = "FAULT"
            elif flow > 10:  # 假设流量大于 10 就算运行
                current_state = "RUNNING"
            elif temp > 40:
                current_state = "HEATING"

            # 4. 调用 API 上传到 Go -> Milvus
            # 注意：api_client 是由 main.py 注入的
            if hasattr(self, 'api_client') and self.api_client:
                signal_payload = {
                    "temp": float(temp),
                    "flow": float(flow),
                    "rpm": float(rpm)
                }

                # 为了避免阻塞 UI，最好用 QTimer 异步发送，或者直接发送(如果网络够快)
                # 这里直接发送演示：
                try:
                    # 采样上传：并不是每一帧都传，比如每秒传一次，避免数据库爆炸
                    # 这里简单起见，每次都传
                    self.api_client.upload_signal_state(device_code, signal_payload, current_state)
                except Exception as e:
                    print(f"上传异常: {e}")

        # 情况 B: 统计切片数据
        elif msg_type == "slice":
            self.page2.on_slice_received(data)

        # 情况 C: 报警图片
        elif msg_type == "alarm_image":
            print(f"收到报警图片: {data.get('image_url')}")

    def closeEvent(self, event):
        if self.ws_worker:
            self.ws_worker.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = FullTrackingModule()
    win.resize(1100, 800)
    win.show()
    sys.exit(app.exec())