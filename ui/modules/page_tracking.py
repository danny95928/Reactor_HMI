import sys
import random
import datetime
import math
from collections import Counter

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem,
                             QHeaderView, QFrame, QGroupBox, QApplication,
                             QPushButton, QMessageBox, QTabWidget, QProgressBar,
                             QSlider, QStyleOptionSlider, QStyle, QLineEdit, QDialog, QFormLayout, QDialogButtonBox,
                             QComboBox)  # Added QLineEdit, QDialog, etc.
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QAction  # Added QAction
from PyQt6.QtCore import Qt, QTimer, QPointF, QThread, pyqtSignal, QRect

import pyqtgraph as pg

# === 全局绘图配置 ===
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

# === 尝试导入 Neo4j 驱动 ===
try:
    from neo4j import GraphDatabase

    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False


# ============================================================================
# 0. Neo4j 连接管理类 (保持不变)
# ============================================================================
class Neo4jHandler:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Neo4jHandler, cls).__new__(cls)
            cls._instance.driver = None
            cls._instance.uri = "bolt://localhost:7687"
            cls._instance.auth = ("neo4j", "password")
        return cls._instance

    def connect(self):
        if not HAS_NEO4J: return False, "未安装 neo4j 库"
        try:
            if self.driver: self.driver.close()
            self.driver = GraphDatabase.driver(self.uri, auth=self.auth)
            self.driver.verify_connectivity()
            return True, "连接成功"
        except Exception as e:
            return False, str(e)

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
# 1. Tab 1: 状态追踪与拓扑图
# ============================================================================
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
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)
        self.timer_interval_ms = 1000
        self.hold_duration_sec = 2 * 60
        self.current_hold_counter = 0
        self.next_state_name = "空转"
        self.init_chart_area()
        self.init_bottom_area()
        self.data_x = list(range(100));
        self.data_y = [85.0] * 100;
        self.ptr = 100
        self.timer = QTimer();
        self.timer.timeout.connect(self.update_data);
        self.timer.start(self.timer_interval_ms)
        self.sm_widget.set_state(self.next_state_name)

    def init_chart_area(self):
        gb = QGroupBox("实时趋势")
        gb.setStyleSheet("""
            QGroupBox { background-color: white; border: 1px solid #ccc; border-radius: 5px; margin-top: 10px; font-weight: bold; color: #333; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
        """)
        l = QVBoxLayout(gb)
        self.lbl_timer = QLabel(f"当前状态保持中... ")
        self.lbl_timer.setStyleSheet("color: #666; font-size: 12px; margin-bottom: 5px;")
        self.lbl_timer.setAlignment(Qt.AlignmentFlag.AlignRight)
        l.addWidget(self.lbl_timer)
        self.plot = pg.PlotWidget()
        self.plot.setBackground('w');
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.curve = self.plot.plot(pen=pg.mkPen('#007acc', width=2))
        self.plot.addItem(
            pg.InfiniteLine(pos=85, angle=0, pen=pg.mkPen('#4CAF50', width=2, style=Qt.PenStyle.DashLine)))
        l.addWidget(self.plot)
        self.layout.addWidget(gb, stretch=3)

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

    def update_data(self):
        last_val = self.data_y[-1]
        new_val = last_val + random.uniform(-0.5, 0.5) + (85.0 - last_val) * 0.05
        self.data_y.pop(0);
        self.data_y.append(new_val)
        self.data_x.pop(0);
        self.data_x.append(self.ptr);
        self.ptr += 1
        self.curve.setData(self.data_x, self.data_y)
        self.current_hold_counter += 1
        self.lbl_timer.setText(f"当前状态: {self.next_state_name}")
        if self.current_hold_counter >= self.hold_duration_sec:
            self.current_hold_counter = 0
            self.transition_state()

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
# 2. Tab 2: 时间切片
# ============================================================================
class TimeSlicePage(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.panel = QFrame()
        self.panel.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ccc; border-radius: 4px; color: #333;")
        pl = QHBoxLayout(self.panel)
        self.lbl_idx = QLabel("当前切片: #1");
        self.lbl_idx.setStyleSheet("font-weight: bold; font-size: 13px; color: #000;")
        self.pbar = QProgressBar();
        self.pbar.setFixedWidth(200);
        self.pbar.setTextVisible(True)
        self.pbar.setStyleSheet("""QProgressBar { border: 1px solid #999; border-radius: 3px; background: white; color: black; text-align: center; }
            QProgressBar::chunk { background-color: #2196F3; width: 10px; }""")
        self.lbl_stats = QLabel("等待生成切片...");
        self.lbl_stats.setStyleSheet("color: #555; margin-left: 20px;")
        pl.addWidget(self.lbl_idx);
        pl.addWidget(self.pbar);
        pl.addWidget(self.lbl_stats);
        pl.addStretch()
        self.layout.addWidget(self.panel)
        self.plot = pg.PlotWidget();
        self.plot.setBackground('w');
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setLabel('left', '温度', units='C', color='k');
        self.plot.setLabel('bottom', '时间轴', color='k')
        self.curve = self.plot.plot(pen=pg.mkPen('#FF9800', width=2))
        self.layout.addWidget(self.plot, stretch=2)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["切片ID", "平均温度", "主导状态"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""QTableWidget { border: 1px solid #ccc; font-size: 12px; color: #000; background-color: white; }
            QHeaderView::section { background-color: #f0f0f0; border: none; height: 30px; color: #000; font-weight: bold; border-bottom: 1px solid #ccc; }
            QTableWidget::item { color: #000; padding-left: 5px; }""")
        self.layout.addWidget(self.table, stretch=1)

        self.data_x = [];
        self.data_y = [];
        self.ptr = 0;
        self.slice_int = 10;
        self.cnt = 0;
        self.slice_id = 1
        self.buf_data = [];
        self.buf_st = []
        self.timer = QTimer();
        self.timer.timeout.connect(self.update);
        self.timer.start(1000)

    def update(self):
        val = 85 + random.uniform(-2, 2);
        st = random.choice(["加热", "反应", "空转"])
        self.data_x.append(self.ptr);
        self.data_y.append(val);
        self.ptr += 1
        self.curve.setData(self.data_x, self.data_y)
        self.buf_data.append(val);
        self.buf_st.append(st);
        self.cnt += 1
        self.pbar.setValue(int((self.cnt / self.slice_int) * 100))
        if self.cnt >= self.slice_int:
            v = pg.InfiniteLine(pos=self.ptr, angle=90, pen=pg.mkPen('#999', width=1, style=Qt.PenStyle.DashLine),
                                label=f"切片 #{self.slice_id}",
                                labelOpts={'position': 0.1, 'color': '#333', 'movable': True})
            self.plot.addItem(v)
            avg = sum(self.buf_data) / len(self.buf_data);
            dom = Counter(self.buf_st).most_common(1)[0][0]
            self.lbl_stats.setText(f"✅ 切片 #{self.slice_id} 归档: {avg:.1f}°C ({dom})")
            r = self.table.rowCount();
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(f"#{self.slice_id}"))
            self.table.setItem(r, 1, QTableWidgetItem(f"{avg:.2f}"))
            self.table.setItem(r, 2, QTableWidgetItem(dom))
            self.table.scrollToBottom()
            self.slice_id += 1;
            self.cnt = 0;
            self.buf_data = [];
            self.buf_st = []
            self.lbl_idx.setText(f"当前切片: #{self.slice_id}")


# ============================================================================
# 3. Tab 3: FSM 逻辑定义 (Simulink 风格 - 全中文)
# ============================================================================

# 编辑逻辑块的对话框
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

        # 逻辑类型选择 (简单实现，仅支持现有类型的参数调整)
        self.logic_type_combo = QComboBox()
        self.logic_type_combo.addItems(["范围 (min <= x <= max)", "等于 (x == val)", "小于 (x < val)", "始终 False"])
        layout.addRow("逻辑类型:", self.logic_type_combo)

        # 参数输入
        self.param1_edit = QLineEdit()
        self.param2_edit = QLineEdit()
        self.target_var_edit = QComboBox()  # 选择变量 temp, rpm, flow
        self.target_var_edit.addItems(["temp", "rpm", "flow"])

        layout.addRow("目标变量:", self.target_var_edit)
        layout.addRow("参数 1:", self.param1_edit)
        layout.addRow("参数 2 (仅范围):", self.param2_edit)

        # 解析现有 check 函数尝试回填参数 (简化处理，实际需更复杂解析)
        # 这里仅提供界面，实际逻辑需用户重新定义

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self):
        # 构建新的 check 函数
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
    """
    可视化组件：Simulink Stateflow 风格
    使用专业术语：State, Logic Block, Guard Condition
    """

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(450)
        # 模拟输入数据
        self.inputs = {"temp": 15, "rpm": 0, "flow": 0, "active_state": "IDLE"}

        # 定义状态机布局与逻辑
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
            # 检测点击了哪个状态块的哪个逻辑块
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

        # 1. 绘制 Simulink 风格背景网格
        self.draw_grid(p)

        # 字体定义
        font_header = QFont("Microsoft YaHei", 10, QFont.Weight.Bold)
        font_tag = QFont("Consolas", 8, QFont.Weight.Bold)
        font_detail = QFont("Microsoft YaHei", 8)

        # 2. 绘制状态机连线
        p.setPen(QPen(QColor("#777"), 2, Qt.PenStyle.SolidLine))
        # IDLE -> RUNNING
        p.drawLine(330, 240, 400, 240)
        self.draw_arrow(p, QPointF(395, 240))
        # RUNNING -> FAULT
        p.drawLine(680, 240, 750, 240)
        self.draw_arrow(p, QPointF(745, 240))

        # 3. 绘制状态 (State Containers)
        for state_key, cfg in self.fsm_config.items():
            rect = cfg["rect"]
            is_active = (self.inputs["active_state"] == state_key)

            # 状态框样式
            if is_active:
                bg_color = QColor(225, 240, 255)  # Active Blue
                border_color = QColor(0, 100, 200)
                border_width = 3
            else:
                bg_color = QColor(245, 245, 245)  # Inactive Grey
                border_color = QColor(180, 180, 180)
                border_width = 1

            # 绘制容器
            p.setBrush(QBrush(bg_color))
            p.setPen(QPen(border_color, border_width))
            p.drawRoundedRect(rect, 10, 10)

            # 绘制标题栏
            header_h = 30
            p.setPen(QPen(border_color, 1))
            p.drawLine(rect.x(), rect.y() + header_h, rect.right(), rect.y() + header_h)

            p.setPen(QPen(QColor("#333")))
            p.setFont(font_header)
            p.drawText(QRect(rect.x() + 10, rect.y(), rect.width(), header_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, cfg["label"])

            # 激活状态指示灯
            if is_active:
                p.setBrush(QColor(0, 200, 0))  # Green LED
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(rect.right() - 20, rect.y() + 15), 5, 5)

            # 4. 绘制逻辑块 (Logic Blocks)
            block_h = 75
            spacing = 20
            start_y = rect.y() + 50

            for i, block in enumerate(cfg["logic_blocks"]):
                # 逻辑判定
                cond_met = block["check"](self.inputs)
                is_blk_active = is_active and cond_met

                # 块位置
                b_rect = QRect(rect.x() + 15, start_y + i * (block_h + spacing), rect.width() - 30, block_h)

                # 块样式 (Simulink Block)
                if is_blk_active:
                    b_bg = QColor(255, 193, 7)  # Amber for active
                    b_border = QColor(255, 111, 0)
                    line_w = 2
                else:
                    b_bg = QColor(255, 255, 255)
                    b_border = QColor(200, 200, 200)
                    line_w = 1

                p.setBrush(QBrush(b_bg))
                p.setPen(QPen(b_border, line_w))
                p.drawRoundedRect(b_rect, 4, 4)

                # 端口装饰 (Ports)
                p.setBrush(QColor("#555"))
                p.drawRect(b_rect.x() - 2, b_rect.y() + 15, 4, 6)  # In
                p.drawRect(b_rect.right() - 2, b_rect.y() + 15, 4, 6)  # Out

                # 内容文本
                # Name
                p.setPen(QPen(QColor("#000")))
                p.setFont(font_detail)
                p.drawText(b_rect.adjusted(10, 5, -5, 0), Qt.AlignmentFlag.AlignLeft, block["name"])

                # Tag (Variable)
                p.setPen(QPen(QColor("#0D47A1")))  # Engineering Blue
                p.setFont(font_tag)
                p.drawText(b_rect.adjusted(0, 5, -10, 0), Qt.AlignmentFlag.AlignRight, f"[{block['tag']}]")

                # Condition
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

        # --- 控制面板: 信号生成与状态切换 ---
        ctrl_grp = QGroupBox("信号接收器与状态跳转定义")
        ctrl_grp.setStyleSheet(
            "QGroupBox{font-weight:bold; border:1px solid #aaa; margin-top:10px;} QGroupBox::title{subcontrol-origin:margin; left:10px;}")
        h_layout = QHBoxLayout(ctrl_grp)

        # 1. 变量控制滑块
        self.sliders = {}
        # 定义: key, label, max_val, default_val
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

        # 2. 状态切换按钮
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

        # --- 可视化组件 ---

        self.visualizer = FSMVisualizer()
        layout.addWidget(self.visualizer, stretch=1)

        # --- 底部说明 ---
        desc = QLabel(
            "状态流：点击逻辑块可编辑其条件。当条件满足时，当前激活状态内的逻辑块将高亮显示。")
        desc.setStyleSheet("color:#666; font-style:italic;")
        layout.addWidget(desc)

        # 初始化视图
        self.switch_state(self.btn_idle)

    def on_slider_change(self, key, val, lbl_widget, label_text):
        lbl_widget.setText(f"{label_text}: {val}")
        self.update_viz()

    def switch_state(self, btn):
        for b in self.btns: b.setChecked(False)
        btn.setChecked(True)

        # 预设值演示
        if "空转" in btn.text():
            self.sliders["temp"].setValue(15)
            self.sliders["rpm"].setValue(0)
            self.sliders["flow"].setValue(0)
        elif "运行" in btn.text():
            self.sliders["temp"].setValue(45)  # 命中 T_Monitor
            self.sliders["rpm"].setValue(60)  # 命中 N_Range
            self.sliders["flow"].setValue(50)
        elif "故障" in btn.text():
            self.sliders["temp"].setValue(95)

        self.update_viz()

    def update_viz(self):
        t = self.sliders["temp"].value()
        r = self.sliders["rpm"].value()
        f = self.sliders["flow"].value()

        # 获取当前激活的按钮文本并映射到内部状态键
        s = "IDLE"
        if self.btn_run.isChecked():
            s = "RUNNING"
        elif self.btn_fault.isChecked():
            s = "FAULT"

        self.visualizer.update_signals(t, r, f, s)


# ============================================================================
# 主窗口整合
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = FullTrackingModule()
    # 调大窗口尺寸以容纳 FSM 图
    win.resize(1100, 800)
    win.setWindowTitle("生产过程状态追踪系统")
    win.show()
    sys.exit(app.exec())