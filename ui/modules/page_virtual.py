import sys
import os  # 用于处理路径
import json
import random
import math
import time
from threading import Thread

# PyQt6 导入
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QPushButton, QFrame, QGroupBox, QProgressBar,
                             QDialog, QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit,
                             QFileDialog, QMessageBox, QPlainTextEdit, QTableWidget,
                             QTableWidgetItem, QHeaderView, QTabWidget)
from PyQt6.QtCore import Qt, QTimer, QPointF, pyqtSignal, QObject, QRect, QThread
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QCursor

# === 尝试导入 Matlab Engine ===
try:
    import matlab.engine

    HAS_MATLAB = True
except ImportError:
    HAS_MATLAB = False
    print("提示: 未检测到 matlab.engine 库，将在模拟模式下运行界面。")


# ============================================================================
# 0. 后台连接线程
# ============================================================================
class ConnectionThread(QThread):
    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)

    def run(self):
        if not HAS_MATLAB:
            self.error_signal.emit("未安装 matlab.engine")
            return
        try:
            eng = matlab.engine.start_matlab()
            self.finished_signal.emit(eng)
        except Exception as e:
            self.error_signal.emit(str(e))


# ============================================================================
# 1. 配方导入模态框 (Recipe Import Dialog)
# ============================================================================
class RecipeImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("多批次配方参数导入")
        self.resize(900, 600)
        self.setStyleSheet("background-color: #f0f0f0; color: black; font-family: 'Segoe UI', Arial;")

        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.btn_select_file = QPushButton("选择 JSON 文件...")
        self.btn_select_file.setStyleSheet("""
            QPushButton { background-color: #2196F3; color: white; border-radius: 4px; padding: 6px 12px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #1976D2; }
        """)
        self.lbl_file_path = QLabel("未选择文件")
        self.lbl_file_path.setStyleSheet("color: #666; font-style: italic;")

        top_layout.addWidget(self.btn_select_file)
        top_layout.addWidget(self.lbl_file_path)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        layout.addWidget(QLabel("批次任务列表 (JSON 数组):"))
        self.text_edit = QPlainTextEdit()
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_edit.setStyleSheet("""
            QPlainTextEdit { 
                background-color: white; color: black; border: 1px solid #ccc; 
                font-family: Consolas, Monospace; font-size: 12px; padding: 5px;
            }
        """)

        # 默认展示 JSON
        batch_list = [
            {"batchID": "Batch_20231027_A", "productType": "Shampoo_TypeC", "subMolarity": 2.5, "subDensity": 1150.0,
             "subVolume": 45.0, "addMolarity": 0.8, "addDensity": 950.0, "addVolume": 2.5, "waterVolume": 80.0,
             "priority": "High"},
            {"batchID": "Batch_20231027_B", "productType": "Conditioner_TypeA", "subMolarity": 3.0,
             "subDensity": 1200.0, "subVolume": 50.0, "addMolarity": 1.2, "addDensity": 980.0, "addVolume": 3.0,
             "waterVolume": 100.0, "priority": "Normal"},
            {"batchID": "Batch_20231027_C", "productType": "BodyWash_TypeZ", "subMolarity": 2.2, "subDensity": 1100.0,
             "subVolume": 40.0, "addMolarity": 0.5, "addDensity": 920.0, "addVolume": 2.0, "waterVolume": 90.0,
             "priority": "Low"}
        ]

        json_text = json.dumps(batch_list, indent=4)
        self.text_edit.setPlainText(json_text)
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        self.btn_sample = QPushButton(" 采样 ")
        self.btn_cancel = QPushButton(" 取消 ")
        self.btn_sample.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 4px; padding: 8px 20px; font-weight: bold; border: none;} QPushButton:hover { background-color: #45a049; }")
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #9E9E9E; color: white; border-radius: 4px; padding: 8px 20px; font-weight: bold; border: none;} QPushButton:hover { background-color: #757575; }")

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_sample)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_select_file.clicked.connect(self.browse_file)
        self.btn_sample.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def browse_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "选择配方文件", "", "JSON Files (*.json);;All Files (*)")
        if file_name:
            self.lbl_file_path.setText(file_name)
            try:
                with open(file_name, 'r', encoding='utf-8') as f:
                    content = f.read()
                    parsed = json.loads(content)
                    self.text_edit.setPlainText(json.dumps(parsed, indent=4))
            except Exception as e:
                QMessageBox.warning(self, "读取错误", f"无法读取文件:\n{str(e)}")

    def get_data(self):
        try:
            return json.loads(self.text_edit.toPlainText())
        except:
            return None


# ============================================================================
# 2. 指令列表生成模态框 (Command List Dialog)
# ============================================================================
class CommandListDialog(QDialog):
    def __init__(self, recipe_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成多批次任务指令列表")
        self.resize(1200, 500)
        self.setStyleSheet("background-color: #f0f0f0; color: black; font-family: 'Segoe UI', Arial;")
        self.recipe_data = recipe_data

        layout = QVBoxLayout(self)
        lbl_info = QLabel("系统已将导入的配方解析为以下批次任务，详细物性参数如下：")
        lbl_info.setStyleSheet("font-weight: bold; color: #333; margin-bottom: 5px;")
        layout.addWidget(lbl_info)

        self.table = QTableWidget()
        columns = ["任务批次 ID", "产品配方", "基质浓度 (mol/L)", "基质密度 (kg/m³)", "基质体积 (L)",
                   "添加剂浓度 (mol/L)", "添加剂密度 (kg/m³)", "添加剂体积 (L)", "加水量 (L)", "执行优先级"]
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setStyleSheet("""
            QTableWidget { background-color: white; border: 1px solid #ccc; gridline-color: #e0e0e0; color: black; font-size: 13px; }
            QHeaderView::section { background-color: #e0e0e0; padding: 6px; border: 1px solid #ccc; font-weight: bold; color: black; }
            QTableWidget::item { padding: 5px; border-bottom: 1px solid #f0f0f0; color: black; }
        """)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for i in range(2, 9): header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(9, 100)

        self.populate_table()
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_send = QPushButton(" 发送 ")
        self.btn_cancel = QPushButton(" 取消 ")
        self.btn_send.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border-radius: 4px; padding: 8px 20px; font-weight: bold; border: none; } QPushButton:hover { background-color: #45a049; }")
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #9E9E9E; color: white; border-radius: 4px; padding: 8px 20px; font-weight: bold; border: none; } QPushButton:hover { background-color: #757575; }")
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_send)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_send.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def populate_table(self):
        data_source = self.recipe_data
        if not data_source:
            data_source = []
            priorities = ["High", "Normal", "Low"]
            products = ["Shampoo_Classic", "Shampoo_Moist", "Conditioner_Pro"]

            # === 配方比例常量 (wt%) ===
            RATIO_FA = 0.0706
            RATIO_WATER = 0.9059
            RATIO_BTAC = 0.0235
            MOLAR_MASS_FA = 255.0
            MOLAR_MASS_BTAC = 404.0

            for i in range(1, 11):
                total_mass_kg = round(random.uniform(500, 1000), 1)
                mass_fa = total_mass_kg * RATIO_FA
                mass_water = total_mass_kg * RATIO_WATER
                mass_btac = total_mass_kg * RATIO_BTAC
                density_fa = round(random.uniform(805, 825), 1)
                density_btac = round(random.uniform(940, 980), 1)
                density_water = round(random.uniform(980, 1000), 1)

                vol_fa_L = (mass_fa / density_fa) * 1000
                vol_btac_L = (mass_btac / density_btac) * 1000
                vol_water_L = (mass_water / density_water) * 1000
                total_vol_L = vol_fa_L + vol_btac_L + vol_water_L

                molarity_fa = ((mass_fa * 1000) / MOLAR_MASS_FA) / total_vol_L
                molarity_btac = ((mass_btac * 1000) / MOLAR_MASS_BTAC) / total_vol_L

                mock_item = {
                    "batchID": f"Batch_Auto_{str(i).zfill(3)}",
                    "productType": random.choice(products),
                    "subMolarity": round(molarity_fa, 4),
                    "subDensity": density_fa,
                    "subVolume": round(vol_fa_L, 2),
                    "addMolarity": round(molarity_btac, 4),
                    "addDensity": density_btac,
                    "addVolume": round(vol_btac_L, 2),
                    "waterVolume": round(vol_water_L, 2),
                    "priority": random.choice(priorities)
                }
                data_source.append(mock_item)

        self.table.setRowCount(len(data_source))
        for row_idx, batch in enumerate(data_source):
            vals = [
                str(batch.get("batchID", "")), str(batch.get("productType", "")),
                str(batch.get("subMolarity", "-")), str(batch.get("subDensity", "-")),
                str(batch.get("subVolume", "-")), str(batch.get("addMolarity", "-")),
                str(batch.get("addDensity", "-")), str(batch.get("addVolume", "-")),
                str(batch.get("waterVolume", "-")), str(batch.get("priority", "Normal"))
            ]
            for col_idx, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setForeground(QColor("black"))
                self.table.setItem(row_idx, col_idx, item)

            p_item = self.table.item(row_idx, 9)
            p_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if vals[9] == "High":
                p_item.setForeground(QColor("red"))
                p_item.setFont(QFont("Arial", weight=QFont.Weight.Bold))

    def get_batch_commands(self):
        commands = []
        for row in range(self.table.rowCount()):
            cmd = {"batch_id": self.table.item(row, 0).text(), "recipe": self.table.item(row, 1).text()}
            commands.append(cmd)
        return commands


# ============================================================================
# 3. 模拟 Simulink 示波器 (GUI部分) - 【修改点：默认颜色改为白色】
# ============================================================================
class SimulinkScope(QWidget):
    # 修改默认值为白底黑字 (#FFFFFF, #000000) 和灰网格 (#AAAAAA)
    def __init__(self, bg_color="#FFFFFF", line_color="#FFFF00", y_min=0, y_max=100,
                 grid_color="#AAAAAA", text_color="#000000"):
        super().__init__()
        self.setMinimumHeight(250)
        self.bg_color = QColor(bg_color)
        self.line_color = QColor(line_color)
        self.grid_color = QColor(grid_color)
        self.text_color = QColor(text_color)

        self.data_points = []
        self.max_points = 200
        self.y_min = y_min
        self.y_max = y_max

        self.margin_left = 45
        self.margin_top = 10
        self.margin_right = 15
        self.margin_bottom = 25

        self.scale_x = 1.0
        self.scale_y = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.last_mouse_pos = None

        self.setMouseTracking(True)

    def update_data(self, new_value):
        self.data_points.append(new_value)
        if len(self.data_points) > self.max_points:
            self.data_points.pop(0)
        self.update()

    def reset_view(self):
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.update()

    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        factor = 1.1 if angle > 0 else 0.9
        if self.scale_x * factor > 0.1:
            self.scale_x *= factor
            self.scale_y *= factor
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_mouse_pos = event.pos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

    def mouseMoveEvent(self, event):
        if self.last_mouse_pos is not None:
            delta = event.pos() - self.last_mouse_pos
            self.offset_x += delta.x()
            self.offset_y += delta.y()
            self.last_mouse_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_mouse_pos = None
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.bg_color)

        w = self.width()
        h = self.height()

        graph_x = self.margin_left
        graph_y = self.margin_top
        graph_w = w - self.margin_left - self.margin_right
        graph_h = h - self.margin_top - self.margin_bottom

        self.draw_grid_and_labels(painter, graph_x, graph_y, graph_w, graph_h)

        painter.setClipRect(QRect(int(graph_x), int(graph_y), int(graph_w), int(graph_h)))
        self.draw_curve(painter, graph_x, graph_y, graph_w, graph_h)
        painter.setClipping(False)

        painter.setPen(QPen(self.text_color, 1))
        painter.drawRect(int(graph_x), int(graph_y), int(graph_w), int(graph_h))

        if self.scale_x != 1.0 or self.offset_x != 0:
            painter.setPen(QColor("#666666"))
            painter.drawText(w - 100, 20, "Zoom/Pan Active")

    def draw_grid_and_labels(self, painter, x, y, w, h):
        font = QFont("Arial", 8)
        painter.setFont(font)

        ticks_y = 5
        for i in range(ticks_y + 1):
            ratio = i / ticks_y
            py = y + h - (h * ratio)
            val = self.y_min + (self.y_max - self.y_min) * ratio

            if i == 0 or i == ticks_y:
                painter.setPen(QPen(self.grid_color, 1, Qt.PenStyle.SolidLine))
            else:
                painter.setPen(QPen(self.grid_color, 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(x), int(py), int(x + w), int(py))

            painter.setPen(self.text_color)
            text_rect = QRect(0, int(py) - 10, int(self.margin_left - 5), 20)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{val:.1f}")

        ticks_x = 5
        for i in range(ticks_x + 1):
            ratio = i / ticks_x
            px = x + (w * ratio)
            val = int(self.max_points * ratio)

            if 0 < i < ticks_x:
                painter.setPen(QPen(self.grid_color, 1, Qt.PenStyle.DashLine))
                painter.drawLine(int(px), int(y), int(px), int(y + h))

            painter.setPen(self.text_color)
            text_rect = QRect(int(px) - 20, int(y + h) + 2, 40, 20)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, str(val))

    def draw_curve(self, painter, x, y, w, h):
        if len(self.data_points) < 2: return

        painter.setPen(QPen(self.line_color, 2))
        polyline = []

        x_step = w / (self.max_points - 1) if self.max_points > 1 else 0
        y_range = self.y_max - self.y_min
        if y_range == 0: y_range = 1

        for i, val in enumerate(self.data_points):
            raw_x_rel = i * x_step
            px = x + (raw_x_rel * self.scale_x) + self.offset_x
            draw_val = val
            normalized = (draw_val - self.y_min) / y_range
            pixel_height_rel = normalized * h
            pixel_height_scaled = pixel_height_rel * self.scale_y
            py = (y + h) - pixel_height_scaled + self.offset_y
            polyline.append(QPointF(px, py))

        painter.drawPolyline(polyline)


# ============================================================================
# 4. 弹窗：Simulink 交互界面
# ============================================================================
class MatlabWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def run(self):
        if not HAS_MATLAB:
            self.error.emit("环境未安装 matlab.engine")
            return
        try:
            eng = matlab.engine.start_matlab()
            self.finished.emit(eng)
        except Exception as e:
            self.error.emit(str(e))


class SimulinkBridgeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Matlab/Simulink 联合仿真接口")
        self.resize(1100, 800)
        self.setStyleSheet("background-color: #f0f0f0; color: black;")
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint)

        self.eng = None
        self.model_name = "Heating_PID_Model_V1"
        self.block_temp = "Plant_Output"
        self.block_pos = "Pos_Output"
        self.block_vel = "Vel_Output"
        self.block_acc = "Acc_Output"

        layout = QHBoxLayout(self)

        left_panel = QFrame()
        left_panel.setFixedWidth(340)
        left_panel.setStyleSheet("QFrame { background: white; border-radius: 8px; color: black; }")
        left_layout = QVBoxLayout(left_panel)

        gb_conn = QGroupBox("Simulink 连接状态")
        gb_conn.setStyleSheet(
            "QGroupBox { font-weight: bold; border: 1px solid #ccc; margin-top: 10px; color: black; }")
        conn_layout = QVBoxLayout(gb_conn)
        conn_layout.addSpacing(15)

        self.btn_connect = QPushButton(" 连接 Matlab Engine")
        self.btn_connect.setStyleSheet(
            "background-color: #2196F3; color: white; padding: 8px; border-radius: 4px; border:none;")
        self.lbl_conn_status = QLabel("状态: 未连接")
        self.lbl_conn_status.setStyleSheet("color: #F44336; font-weight: bold;")
        conn_layout.addWidget(self.btn_connect)
        conn_layout.addWidget(self.lbl_conn_status)
        left_layout.addWidget(gb_conn)

        gb_pid = QGroupBox("控制器参数")
        gb_pid.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #ccc; margin-top: 10px; color: black; }")
        pid_main_layout = QVBoxLayout(gb_pid)
        pid_main_layout.setContentsMargins(10, 40, 10, 10)

        self.pid_tabs = QTabWidget()
        self.pid_tabs.setTabPosition(QTabWidget.TabPosition.South)
        self.pid_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ccc; background: white; border-bottom: none; }
            QTabWidget::tab-bar { alignment: center; } 
            QTabBar::tab { 
                background: #e0e0e0; color: black; padding: 6px 10px; margin: 2px;
                border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; min-width: 60px;
            }
            QTabBar::tab:selected { background: #2196F3; color: white; font-weight: bold; }
        """)

        self.tab_temp = QWidget()
        self.spin_temp_kp, self.spin_temp_ki, self.spin_temp_kd = self.create_pid_inputs(self.tab_temp, 2.5, 0.5, 2.1)
        self.pid_tabs.addTab(self.tab_temp, " 温度")

        self.tab_speed1 = QWidget()
        self.spin_spd1_kp, self.spin_spd1_ki, self.spin_spd1_kd = self.create_pid_inputs(self.tab_speed1, 5.0, 1.2,
                                                                                         0.05)
        self.pid_tabs.addTab(self.tab_speed1, " 转速环1")

        self.tab_speed2 = QWidget()
        self.spin_spd2_kp, self.spin_spd2_ki, self.spin_spd2_kd = self.create_pid_inputs(self.tab_speed2, 8.5, 2.0, 0.1)
        self.pid_tabs.addTab(self.tab_speed2, " 转速环2")

        pid_main_layout.addWidget(self.pid_tabs)

        btn_update_pid = QPushButton(" 发送参数至仿真模型")
        btn_update_pid.setStyleSheet(
            "background-color: #FF9800; color: white; padding: 8px; border-radius: 4px; margin-top: 5px; font-weight: bold; border:none;")
        btn_update_pid.clicked.connect(self.update_pid_params)
        pid_main_layout.addWidget(btn_update_pid)

        left_layout.addWidget(gb_pid)

        left_layout.addWidget(QLabel("仿真日志:", styleSheet="color: black; font-weight: bold;"))
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet(
            "border: 1px solid #ddd; background: #fafafa; font-family: Consolas; font-size: 11px; color: black;")
        left_layout.addWidget(self.log_area)

        # === 右侧示波器面板 ===
        # 【修改点】：统一应用白底样式
        right_panel = QVBoxLayout()
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        # 1. 温度示波器
        l_temp = QVBoxLayout()
        l_temp.addWidget(QLabel("1. 温度 (℃) ", styleSheet="font-weight:bold; color:#333"))
        self.scope_temp = SimulinkScope(bg_color="#FFFFFF", line_color="#FF0000",
                                        y_min=0, y_max=100,
                                        grid_color="#AAAAAA", text_color="#000000")
        l_temp.addWidget(self.scope_temp)
        grid_layout.addLayout(l_temp, 0, 0)

        # 2. 角位置示波器
        l_pos = QVBoxLayout()
        l_pos.addWidget(QLabel("2. 角位置 (rad) ", styleSheet="font-weight:bold; color:#333"))
        # 显式传入白底参数
        self.scope_pos = SimulinkScope(bg_color="#FFFFFF", line_color="#4CAF50", y_min=0, y_max=1000,
                                       grid_color="#AAAAAA", text_color="#000000")
        l_pos.addWidget(self.scope_pos)
        grid_layout.addLayout(l_pos, 0, 1)

        # 3. 角速度示波器
        l_vel = QVBoxLayout()
        l_vel.addWidget(QLabel("3. 角速度 (rad/s)", styleSheet="font-weight:bold; color:#333"))
        # 显式传入白底参数
        self.scope_vel = SimulinkScope(bg_color="#FFFFFF", line_color="#2196F3", y_min=0, y_max=50,
                                       grid_color="#AAAAAA", text_color="#000000")
        l_vel.addWidget(self.scope_vel)
        grid_layout.addLayout(l_vel, 1, 0)

        # 4. 角加速度示波器
        l_acc = QVBoxLayout()
        l_acc.addWidget(QLabel("4. 角加速度 (rad/s²)", styleSheet="font-weight:bold; color:#333"))
        # 显式传入白底参数
        self.scope_acc = SimulinkScope(bg_color="#FFFFFF", line_color="#9C27B0", y_min=-10, y_max=10,
                                       grid_color="#AAAAAA", text_color="#000000")
        l_acc.addWidget(self.scope_acc)
        grid_layout.addLayout(l_acc, 1, 1)

        right_panel.addLayout(grid_layout, stretch=1)

        ctrl_bar = QHBoxLayout()
        self.btn_start = QPushButton(" 开始")
        self.btn_refresh = QPushButton(" 重启")
        self.btn_stop = QPushButton(" 停止")

        btn_ctrl_style = "color: white; font-weight: bold; padding: 10px; border-radius: 4px; border: none;"
        self.btn_start.setStyleSheet("background-color: #4CAF50;" + btn_ctrl_style)
        self.btn_refresh.setStyleSheet("background-color: #2196F3;" + btn_ctrl_style)
        self.btn_stop.setStyleSheet("background-color: #F44336;" + btn_ctrl_style)

        ctrl_bar.addWidget(self.btn_start)
        ctrl_bar.addWidget(self.btn_refresh)
        ctrl_bar.addWidget(self.btn_stop)
        ctrl_bar.addStretch()
        right_panel.addLayout(ctrl_bar)

        layout.addWidget(left_panel)
        layout.addLayout(right_panel, stretch=1)

        self.btn_connect.clicked.connect(self.connect_matlab_engine)
        self.btn_start.clicked.connect(self.start_sim)
        self.btn_stop.clicked.connect(self.stop_sim)
        self.btn_refresh.clicked.connect(self.restart_sim)

        self.sim_timer = QTimer()
        self.sim_timer.timeout.connect(self.generate_mock_data)
        self.sim_time_step = 0

    def create_pid_inputs(self, parent_widget, def_p, def_i, def_d):
        layout = QGridLayout(parent_widget)
        layout.setContentsMargins(5, 15, 5, 5)
        skp, ski, skd = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        spin_style = "QDoubleSpinBox { padding: 5px; color: black; background-color: white; border: 1px solid #ccc; border-radius: 4px; }"

        skp.setRange(0, 5000)
        skp.setValue(def_p)
        skp.setStyleSheet(spin_style)
        ski.setRange(0, 5000)
        ski.setValue(def_i)
        ski.setStyleSheet(spin_style)
        skd.setRange(0, 5000)
        skd.setValue(def_d)
        skd.setStyleSheet(spin_style)

        lbl_style = "color: black;"
        layout.addWidget(QLabel("Kp (比例):", styleSheet=lbl_style), 0, 0)
        layout.addWidget(skp, 0, 1)
        layout.addWidget(QLabel("Ki (积分):", styleSheet=lbl_style), 1, 0)
        layout.addWidget(ski, 1, 1)
        layout.addWidget(QLabel("Kd (微分):", styleSheet=lbl_style), 2, 0)
        layout.addWidget(skd, 2, 1)
        return skp, ski, skd

    def log(self, text):
        self.log_area.append(f">> {text}")

    def connect_matlab_engine(self):
        if not HAS_MATLAB:
            QMessageBox.critical(self, "错误", "未找到 matlab.engine 库。")
            self.log("连接失败：缺少 matlab.engine 库")
            return
        self.log("正在启动 Matlab Engine...")
        self.btn_connect.setEnabled(False)
        self.lbl_conn_status.setText("状态: 正在连接...")
        self.lbl_conn_status.setStyleSheet("color: orange; font-weight: bold;")
        self.worker = MatlabWorker()
        self.worker.finished.connect(self.on_matlab_connected)
        self.worker.error.connect(self.on_matlab_error)
        import threading
        t = threading.Thread(target=self.worker.run)
        t.start()

    def on_matlab_connected(self, eng):
        self.eng = eng
        self.lbl_conn_status.setText("状态: 已连接")
        self.lbl_conn_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self.log("Matlab Engine 启动成功！")
        self.btn_connect.setText("已连接")
        try:
            target_path = r"E:\Thesis\Reactor_HMI\model"
            if not os.path.exists(target_path):
                current_dir = os.path.dirname(os.path.abspath(__file__))
                target_path = os.path.abspath(os.path.join(current_dir, "../../model"))
            if os.path.exists(target_path):
                self.eng.cd(target_path, nargout=0)
                self.eng.load_system(self.model_name, nargout=0)
                self.log("模型加载成功！")
            else:
                self.log(f"错误: 无法找到 'model' 文件夹。")
        except Exception as e:
            self.log(f"模型加载错误: {str(e)}")

    def on_matlab_error(self, err_msg):
        self.lbl_conn_status.setText("状态: 连接失败")
        self.lbl_conn_status.setStyleSheet("color: red; font-weight: bold;")
        self.log(f"Matlab 连接错误: {err_msg}")
        self.btn_connect.setEnabled(True)

    def update_pid_params(self):
        if self.eng is None:
            self.log("提示：未连接真实 Matlab")
            return
        idx = self.pid_tabs.currentIndex()
        try:
            kp, ki, kd = 0, 0, 0
            var_suffix = ""
            var_name_log = ""

            if idx == 0:
                kp, ki, kd = self.spin_temp_kp.value(), self.spin_temp_ki.value(), self.spin_temp_kd.value()
                var_suffix = "_Temp"
                var_name_log = "温度"
            elif idx == 1:
                kp, ki, kd = self.spin_spd1_kp.value(), self.spin_spd1_ki.value(), self.spin_spd1_kd.value()
                var_suffix = "_Spd1"
                var_name_log = "转速环1"
            else:
                kp, ki, kd = self.spin_spd2_kp.value(), self.spin_spd2_ki.value(), self.spin_spd2_kd.value()
                var_suffix = "_Spd2"
                var_name_log = "转速环2"

            self.eng.eval(f"Kp{var_suffix} = {float(kp)};", nargout=0)
            self.eng.eval(f"Ki{var_suffix} = {float(ki)};", nargout=0)
            self.eng.eval(f"Kd{var_suffix} = {float(kd)};", nargout=0)

            self.eng.set_param(self.model_name, 'SimulationCommand', 'update', nargout=0)
            self.log(f"{var_name_log} 参数已同步 (Kp={kp}, Ki={ki}, Kd={kd})")

        except Exception as e:
            self.log(f"参数下发失败: {str(e)}")
            print(f"DEBUG: Error details: {e}")

    def start_sim(self):
        if self.eng:
            try:
                self.eng.set_param(self.model_name, 'SimulationCommand', 'start', nargout=0)
                self.log("仿真指令已发送。")
            except Exception as e:
                self.log(f"启动失败: {str(e)}")
        else:
            self.log("模拟模式：仿真开始...")
        self.sim_timer.start(50)

    def stop_sim(self):
        if self.eng:
            try:
                self.eng.set_param(self.model_name, 'SimulationCommand', 'stop', nargout=0)
                self.log("仿真停止指令已发送。")
            except Exception as e:
                self.log(f"停止失败: {str(e)}")
        self.sim_timer.stop()
        self.log("本地监视已暂停。")

    def restart_sim(self):
        if not self.eng: return
        self.log("正在重置仿真...")
        try:
            self.eng.set_param(self.model_name, 'SimulationCommand', 'stop', nargout=0)
        except:
            pass
        self.update_pid_params()

        self.scope_temp.data_points = []
        self.scope_temp.reset_view()
        self.scope_pos.data_points = []
        self.scope_pos.reset_view()
        self.scope_vel.data_points = []
        self.scope_vel.reset_view()
        self.scope_acc.data_points = []
        self.scope_acc.reset_view()

        self.sim_time_step = 0.0
        try:
            self.eng.set_param(self.model_name, 'SimulationCommand', 'start', nargout=0)
            self.log("仿真已重启")
            self.sim_timer.start(100)
        except Exception as e:
            self.log(f"重启失败: {e}")

    def generate_mock_data(self):
        """生成模拟数据（未连接 Matlab 时使用）"""

        # 1. 尝试从 Matlab 获取数据
        if self.eng:
            try:
                status = self.eng.get_param(self.model_name, 'SimulationStatus')
                if status == 'running' or status == 'paused':
                    try:
                        self.scope_temp.update_data(float(self.eng.eval(
                            f"get_param('{self.model_name}/{self.block_temp}', 'RuntimeObject').OutputPort(1).Data")))
                    except:
                        pass
                    try:
                        self.scope_pos.update_data(float(self.eng.eval(
                            f"get_param('{self.model_name}/{self.block_pos}', 'RuntimeObject').OutputPort(1).Data")))
                    except:
                        pass
                    try:
                        self.scope_vel.update_data(float(self.eng.eval(
                            f"get_param('{self.model_name}/{self.block_vel}', 'RuntimeObject').OutputPort(1).Data")))
                    except:
                        pass
                    try:
                        self.scope_acc.update_data(float(self.eng.eval(
                            f"get_param('{self.model_name}/{self.block_acc}', 'RuntimeObject').OutputPort(1).Data")))
                    except:
                        pass
                    return
            except Exception as e:
                pass

        # 2. 纯 Python 模拟数据生成
        self.sim_time_step += 0.2

        # 温度：二阶欠阻尼响应模拟 (平滑无拐点)
        target_val = 58.1
        zeta = 0.2
        wn = 0.1
        beta = math.sqrt(1 - zeta ** 2)
        wd = wn * beta
        phi = math.atan(beta / zeta)

        response = target_val * (
                    1 - (math.exp(-zeta * wn * self.sim_time_step) / beta) * math.sin(wd * self.sim_time_step + phi))
        drift = 0
        if self.sim_time_step > 100: drift = (self.sim_time_step - 100) * 0.02
        final_temp = max(0, response + drift + random.uniform(-0.05, 0.05))

        self.scope_temp.update_data(final_temp)

        # 其他示波器
        pos_val = self.sim_time_step * 10.0 + random.uniform(-0.1, 0.1)
        self.scope_pos.update_data(pos_val)

        vel_val = 10.0 + random.uniform(-1.0, 1.0)
        self.scope_vel.update_data(vel_val)

        acc_val = random.uniform(-2.0, 2.0)
        self.scope_acc.update_data(acc_val)


# ============================================================================
# 5. InstrumentBlock
# ============================================================================
class InstrumentBlock(QFrame):
    def __init__(self, title, unit, initial_sp):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            InstrumentBlock { background-color: #ffffff; border: 1px solid #cccccc; border-radius: 6px; }
            QLabel { color: #333333; border: none; font-weight: bold; }
            .value_label { font-size: 28px; font-weight: bold; color: #007acc; }
        """)
        layout = QVBoxLayout(self)
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(lbl_title)
        value_layout = QHBoxLayout()
        self.lbl_value = QLabel("0.0")
        self.lbl_value.setProperty("class", "value_label")
        self.lbl_value.setStyleSheet("font-size: 28px; font-weight: bold; color: #007acc;")
        lbl_unit = QLabel(unit)
        lbl_unit.setStyleSheet("font-size: 14px; color: #666; margin-top: 10px;")
        value_layout.addStretch()
        value_layout.addWidget(self.lbl_value)
        value_layout.addWidget(lbl_unit)
        value_layout.addStretch()
        layout.addLayout(value_layout)
        sp_layout = QHBoxLayout()
        sp_layout.addWidget(QLabel("SP (设定):"))
        self.lbl_sp = QLabel(f"[ {initial_sp} ]")
        self.lbl_sp.setStyleSheet("color: #e65100; font-weight: bold;")
        sp_layout.addWidget(self.lbl_sp)
        layout.addLayout(sp_layout)
        self.chart_bar = QProgressBar()
        self.chart_bar.setTextVisible(False)
        self.chart_bar.setFixedHeight(8)
        self.chart_bar.setStyleSheet(
            "QProgressBar {background: #e0e0e0; border: none; border-radius: 4px;} QProgressBar::chunk {background: #007acc; border-radius: 4px;}")
        self.chart_bar.setValue(50)
        layout.addWidget(self.chart_bar)

    def update_value(self, value):
        self.lbl_value.setText(f"{value:.1f}")
        self.chart_bar.setValue(int(value) % 100)


# ============================================================================
# 6. 主界面 VirtualControlPage
# ============================================================================
class VirtualControlPage(QWidget):
    def __init__(self, reactor_core=None):
        super().__init__()
        self.reactor = reactor_core
        self.current_batches = []
        self.setStyleSheet("color: black; font-family: 'Segoe UI', Arial;")

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        group_style = """
            QGroupBox { border: 1px solid #bbbbbb; margin-top: 10px; font-weight: bold; color: #333; background-color: #fafafa; border-radius: 4px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }
        """
        recipe_group = QGroupBox("配方与指令控制")
        recipe_group.setStyleSheet(group_style)
        recipe_layout = QVBoxLayout(recipe_group)
        info_layout = QHBoxLayout()
        self.lbl_batch = QLabel("当前批次: Batch_20241123_A")
        self.lbl_product = QLabel("产品类型: 洗发水_TypeC")
        self.lbl_batch.setStyleSheet("font-size: 14px; color: #000; font-weight: bold;")
        self.lbl_product.setStyleSheet("font-size: 14px; color: #555;")
        info_layout.addWidget(self.lbl_batch)
        info_layout.addSpacing(30)
        info_layout.addWidget(self.lbl_product)
        info_layout.addStretch()
        recipe_layout.addLayout(info_layout)
        btn_layout = QHBoxLayout()
        self.btn_import = QPushButton("导入配方 JSON")
        self.btn_gen = QPushButton("生成指令列表")
        self.btn_act = QPushButton("激活执行器 (联合仿真)")
        self.lbl_status = QLabel("状态: 等待中")
        self.lbl_status.setStyleSheet("color: #f57c00; font-weight: bold; padding-left: 10px;")
        btn_style = "QPushButton { background-color: #e0e0e0; color: #000; border: 1px solid #999; padding: 8px 15px; border-radius: 4px; } QPushButton:hover { background-color: #d5d5d5; }"
        for btn in [self.btn_import, self.btn_gen, self.btn_act]: btn.setStyleSheet(btn_style)
        self.btn_act.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; border: 1px solid #388E3C; padding: 8px 15px; border-radius: 4px; } QPushButton:hover { background-color: #45a049; }")
        btn_layout.addWidget(self.btn_import)
        btn_layout.addWidget(self.btn_gen)
        btn_layout.addWidget(self.btn_act)
        btn_layout.addWidget(self.lbl_status)
        btn_layout.addStretch()
        recipe_layout.addLayout(btn_layout)
        main_layout.addWidget(recipe_group)
        monitor_group = QGroupBox("实时监控仪表盘")
        monitor_group.setStyleSheet(group_style)
        monitor_layout = QHBoxLayout(monitor_group)
        self.inst_temp = InstrumentBlock("釜内温度", "°C", "85.0")
        self.inst_speed = InstrumentBlock("搅拌转速", "r/min", "120")
        self.inst_flow = InstrumentBlock("进料流量", "L/m", "5.0")
        monitor_layout.addWidget(self.inst_temp)
        monitor_layout.addWidget(self.inst_speed)
        monitor_layout.addWidget(self.inst_flow)
        main_layout.addWidget(monitor_group)
        pred_group = QGroupBox("物理场预测结果")
        pred_group.setStyleSheet(group_style)
        pred_main_layout = QVBoxLayout(pred_group)
        pred_main_layout.setSpacing(10)
        pred_info_layout = QHBoxLayout()
        self.lbl_pred_reactor_id = QLabel("当前反应釜ID: Reactor_01")
        self.lbl_pred_exec_batch = QLabel("执行批次: -")
        info_style = "font-size: 14px; color: #000; font-weight: bold;"
        self.lbl_pred_reactor_id.setStyleSheet(info_style)
        self.lbl_pred_exec_batch.setStyleSheet(info_style)
        pred_info_layout.addWidget(self.lbl_pred_reactor_id)
        pred_info_layout.addSpacing(30)
        pred_info_layout.addWidget(self.lbl_pred_exec_batch)
        pred_info_layout.addStretch()
        pred_main_layout.addLayout(pred_info_layout)
        pred_values_layout = QHBoxLayout()

        def create_pred_label(text, value):
            container = QFrame()
            l = QVBoxLayout(container)
            l.setSpacing(2)
            lbl_t = QLabel(text)
            lbl_t.setStyleSheet("color: #666; font-size: 12px;")
            lbl_v = QLabel(value)
            lbl_v.setStyleSheet("color: #007acc; font-size: 16px; font-weight: bold;")
            l.addWidget(lbl_t)
            l.addWidget(lbl_v)
            return container

        pred_values_layout.addWidget(create_pred_label("热扩散率", "0.145 m²/s"))
        pred_values_layout.addStretch()
        pred_values_layout.addWidget(create_pred_label("传热系数", "230 W/m²K"))
        pred_values_layout.addStretch()
        pred_values_layout.addWidget(create_pred_label("预计完成时间", "45 min"))
        pred_main_layout.addLayout(pred_values_layout)
        main_layout.addWidget(pred_group)
        main_layout.addStretch()
        self.btn_act.clicked.connect(self.on_activate)
        self.btn_import.clicked.connect(self.on_import_recipe)
        self.btn_gen.clicked.connect(self.on_generate_commands)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(1000)

    def on_import_recipe(self):
        dialog = RecipeImportDialog(self)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if data and isinstance(data, list):
                self.current_batches = data
                self.lbl_status.setText(f"状态: 已加载 {len(data)} 个批次配方")
                self.lbl_status.setStyleSheet("color: #4CAF50; font-weight: bold; padding-left: 10px;")
            else:
                self.lbl_status.setText("状态: JSON 格式错误")
                self.lbl_status.setStyleSheet("color: red; font-weight: bold; padding-left: 10px;")
        else:
            self.lbl_status.setText("状态: 取消导入")
            self.lbl_status.setStyleSheet("color: gray; font-weight: bold; padding-left: 10px;")

    def on_generate_commands(self):
        dialog = CommandListDialog(recipe_data=self.current_batches, parent=self)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            commands = dialog.get_batch_commands()
            self.lbl_status.setText(f"状态: 已下发 {len(commands)} 个批次任务")
            self.lbl_status.setStyleSheet("color: #2196F3; font-weight: bold; padding-left: 10px;")
            if commands:
                first_batch_id = commands[0]['batch_id']
                self.lbl_pred_exec_batch.setText(f"执行批次: {first_batch_id}")
        else:
            self.lbl_status.setText("状态: 取消指令生成")
            self.lbl_status.setStyleSheet("color: gray; font-weight: bold; padding-left: 10px;")

    def on_activate(self):
        self.lbl_status.setText("状态: 联合仿真窗口已打开...")
        self.lbl_status.setStyleSheet("color: #2196F3; font-weight: bold; padding-left: 10px;")
        dialog = SimulinkBridgeDialog(self)
        dialog.exec()
        self.lbl_status.setText("状态: 仿真结束，等待指令")
        self.lbl_status.setStyleSheet("color: #f57c00; font-weight: bold; padding-left: 10px;")

    def refresh_data(self):
        base_temp = 85.0 + random.uniform(-0.5, 0.5)
        base_speed = 120 + random.randint(-2, 2)
        base_flow = 5.2 + random.uniform(-0.1, 0.1)
        self.inst_temp.update_value(base_temp)
        self.inst_speed.update_value(base_speed)
        self.inst_flow.update_value(base_flow)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VirtualControlPage()
    window.resize(1000, 700)
    window.show()
    sys.exit(app.exec())