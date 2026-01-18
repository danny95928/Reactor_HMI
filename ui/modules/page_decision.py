import sys
import math

# --- 核心 PyQt6 模块导入 ---
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QFrame, QDialog, QFormLayout, QLineEdit,
    QDateEdit, QMessageBox, QTabWidget, QProgressBar,
    QGridLayout, QSplitter, QSizePolicy, QToolTip,
    QDialogButtonBox
)
from PyQt6.QtCore import (
    Qt, QTimer, QDate, QRect, QPoint, QPointF
)
from PyQt6.QtGui import (
    QColor, QPainter, QBrush, QPen, QFont, QCursor, QPainterPath
)


# ============================================================================
# 0. 自定义组件：时间切片可视化条 (保持不变)
# ============================================================================
class TimeSliceWidget(QWidget):
    def __init__(self, slices=None, total_hours=8.0, start_hour=8, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setStyleSheet("background-color: transparent;")
        self.slices = slices if slices else []
        self.total_hours = total_hours
        self.start_hour = start_hour
        self.setMouseTracking(True)

    def set_slices(self, slices):
        self.slices = slices
        self.update()

    def _pct_to_time_str(self, pct):
        total_mins = int(self.total_hours * 60 * pct)
        current_mins = self.start_hour * 60 + total_mins
        h = int(current_mins // 60)
        m = int(current_mins % 60)
        return f"{h:02d}:{m:02d}"

    def mouseMoveEvent(self, event):
        w = self.width()
        if w == 0: return
        mouse_x = event.pos().x()
        mouse_pct = mouse_x / w
        labels = {0: "正常运行", 1: "设备故障", 2: "换型/调试"}
        found = False
        for start_pct, end_pct, type_code, reason in self.slices:
            if start_pct <= mouse_pct <= end_pct:
                x_start = int(start_pct * w)
                x_width = int((end_pct - start_pct) * w)
                slice_rect = QRect(x_start, 0, x_width, self.height())
                start_time = self._pct_to_time_str(start_pct)
                end_time = self._pct_to_time_str(end_pct)

                if type_code == 1:
                    status_display = f"{reason}"
                    detail_line = ""
                else:
                    status_display = labels.get(type_code, "未知")
                    detail_line = f"<b>详情:</b> {reason}<br>" if reason else ""

                tooltip_text = (f"<div style='font-family:Microsoft YaHei; font-size:12px;'>"
                                f"<b>时间段:</b> {start_time} - {end_time}<br>"
                                f"<b>状态:</b> <span style='color:{self._get_color_hex(type_code)}'>{status_display}</span><br>"
                                f"{detail_line}</div>")

                QToolTip.showText(event.globalPosition().toPoint(), tooltip_text, self, slice_rect)
                found = True
                break
        if not found: QToolTip.hideText()
        super().mouseMoveEvent(event)

    def _get_color_hex(self, type_code):
        if type_code == 0: return "#4caf50"
        if type_code == 1: return "#f44336"
        return "#ff9800"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f0f0f0"))
        painter.drawRoundedRect(0, 15, w, 30, 4, 4)
        colors = {0: QColor("#4caf50"), 1: QColor("#f44336"), 2: QColor("#ff9800")}
        labels = {0: "运行", 1: "故障", 2: "调试"}
        for start_pct, end_pct, type_code, reason in self.slices:
            x = int(start_pct * w)
            width = int((end_pct - start_pct) * w)
            painter.setBrush(colors.get(type_code, Qt.GlobalColor.gray))
            painter.drawRoundedRect(x, 15, width, 30, 2, 2)
            if width > 30:
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.Bold))
                painter.drawText(QRect(x, 15, width, 30), Qt.AlignmentFlag.AlignCenter, labels.get(type_code, ""))
            if width > 50:
                start_time = self._pct_to_time_str(start_pct)
                end_time = self._pct_to_time_str(end_pct)
                time_str = f"{start_time}-{end_time}"
                painter.setPen(QColor("#666666"))
                painter.setFont(QFont("Arial", 7))
                painter.drawText(QRect(x, 50, width, 20), Qt.AlignmentFlag.AlignCenter, time_str)


# ============================================================================
# 1. 自定义组件：输入/输出控制图 (高频阶梯 + 初始非零 + 具体停机事件)
# ============================================================================
class InputOutputChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(350)
        self.setStyleSheet("background-color: white; border: 1px solid #ddd; border-radius: 4px;")

        # === 1. 输入数据 (Input - 理想计划) ===
        # 修改点：第一项不再是 (0,0)，而是 (0, 1500)，代表初始计划投料量
        self.input_events = [
            (0.0, 1500, "初始投料"),  # <-- 这里修改了，初始不为0
            (1.5, 3000, "计划_A"),
            (3.0, 4500, "计划_B"),
            (4.5, 6000, "计划_C"),
            (6.0, 7500, "计划_D")
        ]

        # === 2. 输出数据 (Output - 实际高频波动) ===
        # 数据结构：(时间点, 累计产量, 批次标签, 停机原因/备注)
        # 备注为 None 代表正常衔接，有字符串则代表该段水平线是故障导致的
        self.output_events = [
            # 初始状态
            (0.0, 0, "", None),

            # --- 第1天：正常 ---
            (0.5, 500, "", None),
            (0.8, 800, "Batch_1a", None),

            # --- 第2天：发生停机 ---
            # 1.2到1.8之间，产量一直是1200，说明这0.6天都在修机器
            (1.2, 1200, "", "电机过热"),
            (1.8, 1200, "", None),  # 修复完成
            (2.0, 1800, "Batch_1b", None),

            # --- 第3天：正常 ---
            (2.5, 2500, "Batch_2a", None),
            (2.8, 2800, "", None),

            # --- 第4天：发生缺料 ---
            # 3.0到4.0之间，产量没变，停机一整天
            (3.0, 2800, "", "原料等待"),
            (4.0, 2800, "", None),
            (4.2, 3500, "Batch_2b", None),

            # --- 第5-7天：追赶 ---
            (4.8, 4200, "", None),
            (5.5, 5000, "Batch_3", None),
            (6.2, 6200, "Batch_4", None),
            (6.8, 7000, "Batch_5", None)
        ]

        self.max_x = 7.0
        self.max_y = 8000

        self.margin_left = 70
        self.margin_right = 30
        self.margin_bottom = 40
        self.margin_top = 40

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        plot_w = w - self.margin_left - self.margin_right
        plot_h = h - self.margin_top - self.margin_bottom

        # 1. 坐标轴
        painter.setPen(QPen(QColor("#333"), 2))
        painter.drawLine(self.margin_left, self.margin_top, self.margin_left, h - self.margin_bottom)
        painter.drawLine(self.margin_left, h - self.margin_bottom, w - self.margin_right, h - self.margin_bottom)

        # 2. 网格与刻度
        painter.setPen(QPen(QColor("#eee"), 1, Qt.PenStyle.DashLine))
        painter.setFont(QFont("Arial", 8))

        # Y轴
        y_steps = 8
        for i in range(y_steps + 1):
            val = i * 1000
            y_pos = h - self.margin_bottom - (val / self.max_y) * plot_h
            painter.drawLine(self.margin_left, int(y_pos), w - self.margin_right, int(y_pos))
            painter.setPen(QColor("#666"))
            painter.drawText(QRect(0, int(y_pos) - 10, self.margin_left - 10, 20),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(val))
            painter.setPen(QPen(QColor("#eee"), 1, Qt.PenStyle.DashLine))

        # X轴 (天)
        for i in range(int(self.max_x) + 1):
            x_pos = self.margin_left + (i / self.max_x) * plot_w
            painter.setPen(QColor("#666"))
            painter.drawText(QRect(int(x_pos) - 20, h - self.margin_bottom + 5, 40, 20),
                             Qt.AlignmentFlag.AlignCenter, f"D{i}")
            # 竖向网格
            painter.setPen(QPen(QColor("#f9f9f9"), 1, Qt.PenStyle.SolidLine))
            painter.drawLine(int(x_pos), self.margin_top, int(x_pos), h - self.margin_bottom)

        # 3. 坐标转换
        def to_point(day, load):
            x = self.margin_left + (day / self.max_x) * plot_w
            y = h - self.margin_bottom - (load / self.max_y) * plot_h
            return QPoint(int(x), int(y))

        # --- A. 绘制趋势虚线 ---
        def draw_trend_line(events, color):
            if not events: return
            start_day, start_val, _ = events[0][:3]  # 取前3个元素(time, val, label)
            end_day, end_val, _ = events[-1][:3]
            p_start = to_point(start_day, start_val)
            p_end = to_point(end_day, end_val)
            pen = QPen(color, 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(p_start, p_end)

        draw_trend_line(self.input_events, QColor("#BBDEFB"))
        draw_trend_line(self.output_events, QColor("#C8E6C9"))

        # --- B. 绘制阶梯曲线 (包含具体停机原因) ---
        def draw_stepped_line(events, color, is_output=False):
            painter.setPen(QPen(color, 2))
            painter.setBrush(color)
            painter.setFont(QFont("Microsoft YaHei", 8))  # 字体稍微大一点以便显示中文

            if not events: return

            # 起点
            prev_day = events[0][0]
            prev_val = events[0][1]
            p0 = to_point(prev_day, prev_val)
            painter.drawEllipse(p0, 3, 3)

            for i in range(1, len(events)):
                # 数据解包：不同列表长度可能不同 (Input是3个，Output是4个)
                item = events[i]
                day = item[0]
                val = item[1]
                label = item[2]
                fault_reason = item[3] if len(item) > 3 else None  # 获取停机原因

                # 阶梯逻辑：水平 -> 垂直
                p_start = to_point(prev_day, prev_val)
                p_corner = to_point(day, prev_val)
                p_end = to_point(day, val)

                # 绘制水平线
                painter.drawLine(p_start, p_corner)

                # 绘制垂直线
                painter.drawLine(p_corner, p_end)

                # --- 修改点：绘制具体停机事件 ---
                if is_output and fault_reason:
                    # 在水平线中间上方绘制文字
                    mid_x = int((p_start.x() + p_corner.x()) / 2)
                    mid_y = p_corner.y()

                    painter.save()
                    # 画个小背景框让文字更清楚（可选）
                    # text_rect = QRect(mid_x - 30, mid_y - 22, 60, 18)
                    # painter.setBrush(QColor(255, 255, 255, 200))
                    # painter.setPen(Qt.PenStyle.NoPen)
                    # painter.drawRect(text_rect)

                    # 绘制红色文字
                    painter.setPen(QPen(QColor("#D32F2F"), 1))
                    painter.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.Bold))
                    painter.drawText(mid_x - 40, mid_y - 5, 80, 20,
                                     Qt.AlignmentFlag.AlignCenter, f"⚠ {fault_reason}")
                    painter.restore()
                    painter.setPen(QPen(color, 2))  # 恢复画笔

                # 绘制当前节点
                painter.drawEllipse(p_end, 3, 3)

                # 绘制批次标签 (如果有)
                if label:
                    text_y = p_end.y() - 12 if is_output else p_end.y() + 15
                    # 如果是输入曲线且是第一个点，特殊处理一下位置防止重叠
                    if not is_output and i == 0: text_y += 10

                    painter.save()
                    painter.setPen(QColor("#333"))
                    painter.drawText(p_end.x() + 5, text_y, label)
                    painter.restore()

                prev_day = day
                prev_val = val

            # 延伸到末尾
            p_last = to_point(prev_day, prev_val)
            p_final = to_point(self.max_x, prev_val)
            painter.drawLine(p_last, p_final)

        # 绘制 Input (蓝色 - 计划，直接从非零开始)
        draw_stepped_line(self.input_events, QColor("#1976D2"), is_output=False)

        # 绘制 Output (绿色 - 实际，包含具体故障原因)
        draw_stepped_line(self.output_events, QColor("#4CAF50"), is_output=True)

        # 4. 图例
        painter.setPen(QColor("#333"))
        painter.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        painter.drawText(QRect(0, 5, w, 20), Qt.AlignmentFlag.AlignCenter, "输入/输出控制图")

        painter.setFont(QFont("Microsoft YaHei", 9))

        # Input Legend
        painter.setBrush(QColor("#1976D2"))
        painter.drawRect(w - 220, 10, 10, 10)
        painter.drawText(QRect(w - 205, 5, 200, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "计划投料")

        # Output Legend
        painter.setBrush(QColor("#4CAF50"))
        painter.drawRect(w - 220, 25, 10, 10)
        painter.drawText(QRect(w - 205, 20, 200, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "实际产出")

        # Y轴标题
        painter.save()
        painter.translate(15, h / 2)
        painter.rotate(-90)
        painter.setPen(QColor("#333"))
        painter.drawText(QRect(-150, 0, 300, 20), Qt.AlignmentFlag.AlignCenter, "累积质量 (kg)")
        painter.restore()


# ============================================================================
# 2. 拆分批次模态框
# ============================================================================
class SplitOrderDialog(QDialog):
    def __init__(self, job_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"批次拆分计算 - {job_id}")
        self.setFixedSize(600, 450)
        self.setStyleSheet("background-color: white; color: #333;")

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        lbl_info = QLabel(f"<b>当前作业 {job_id} 计划提前期超出容差，正在执行二分搜索拆分...</b>")
        lbl_info.setStyleSheet("font-size: 13px; color: #F44336;")
        layout.addWidget(lbl_info)

        param_group = QGroupBox("初始参数")
        param_group.setStyleSheet("QGroupBox { border: 1px solid #ccc; font-weight: bold; }")
        pg_layout = QGridLayout(param_group)
        pg_layout.addWidget(QLabel("额定容积 (Q_full):"), 0, 0);
        pg_layout.addWidget(QLabel("1000 kg"), 0, 1)
        pg_layout.addWidget(QLabel("工艺系数 (α):"), 0, 2);
        pg_layout.addWidget(QLabel("0.05"), 0, 3)
        pg_layout.addWidget(QLabel("时间容差 (dij):"), 1, 0);
        pg_layout.addWidget(QLabel("2.0 h"), 1, 1)
        pg_layout.addWidget(QLabel("精度 (epsilon):"), 1, 2);
        pg_layout.addWidget(QLabel("0.1"), 1, 3)
        layout.addWidget(param_group)

        lbl_table = QLabel("二分搜索迭代过程:")
        layout.addWidget(lbl_table)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["迭代轮次", "Q_low", "Q_high", "Q_mid (试算)", "计划提前期"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(
            "QTableWidget { border: 1px solid #ddd; gridline-color: #eee; } QHeaderView::section { background-color: #f5f5f5; border: none; border-bottom: 1px solid #ddd; font-weight: bold; }")
        layout.addWidget(self.table)

        iterations = [
            (1, 0, 1000, 500, 4.5),
            (2, 0, 500, 250, 2.8),
            (3, 0, 250, 125, 1.6),
            (4, 125, 250, 187.5, 2.1),
            (5, 125, 187.5, 156.25, 1.9)
        ]

        for it, low, high, mid, l_val in iterations:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(it)))
            self.table.setItem(row, 1, QTableWidgetItem(f"{low:.1f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{high:.1f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{mid:.1f}"))

            item_l = QTableWidgetItem(f"{l_val:.2f} h")
            if l_val > 2.0:
                item_l.setForeground(QColor("#F44336"))
            else:
                item_l.setForeground(QColor("#4CAF50"))
            self.table.setItem(row, 4, item_l)

        res_frame = QFrame()
        res_frame.setStyleSheet("background-color: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 4px;")
        rf_layout = QHBoxLayout(res_frame)
        rf_layout.addWidget(QLabel("<b>计算完成:</b> 建议最优批量 Q = <b>156 kg</b> (计划提前期 1.9h <= 2.0h)"))
        layout.addWidget(res_frame)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)


# ============================================================================
# Main Page Class
# ============================================================================
class DecisionSupportPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("运维决策支持模块")
        self.setStyleSheet("background-color: white; color: black; font-family: 'Microsoft YaHei';")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        self.total_shift_hours = 8.0
        total_mins = self.total_shift_hours * 60

        # === 构造故障数据 ===
        def m2p(mins): return mins / total_mins

        self.shift_data_full = []
        current_time = 0

        self.shift_data_full.append((m2p(current_time), m2p(current_time + 30), 2, "开班设备调试", 0))
        current_time += 30
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 60), 0, "正常运行", 0))
        current_time += 60
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 15), 1, "进料泵堵塞", 0))
        current_time += 15
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 45), 0, "正常运行", 0))
        current_time += 45
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 10), 1, "温度传感器漂移", 0))
        current_time += 10
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 60), 0, "正常运行", 0))
        current_time += 60
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 30), 2, "更换产品配方", 0))
        current_time += 30
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 40), 0, "正常运行", 0))
        current_time += 40
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 20), 1, "搅拌电机过载保护", 0))
        current_time += 20
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 50), 0, "正常运行", 0))
        current_time += 50
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 10), 1, "主气路气压不足", 1))
        current_time += 10
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 40), 0, "正常运行", 0))
        current_time += 40
        self.shift_data_full.append((m2p(current_time), m2p(current_time + 10), 1, "控制柜电压异常", 1))
        current_time += 10
        if current_time < total_mins:
            self.shift_data_full.append((m2p(current_time), 1.0, 0, "正常运行", 0))

        self.shift_slices_viz = [(s, e, t, r) for s, e, t, r, st in self.shift_data_full]

        self.init_query_section()
        self.init_tab_section()
        self.init_maintenance_section()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_simulation_data)
        self.timer.start(2000)

    def get_group_style(self):
        return """
            QGroupBox { background-color: white; border: 1px solid #ccc; border-radius: 5px; margin-top: 10px; font-weight: bold; color: #333; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
        """

    def get_table_style(self):
        return """
            QTableWidget { border: none; font-size: 12px; color: #000000; background-color: white; gridline-color: #eee; }
            QHeaderView::section { background-color: #f0f0f0; border: none; height: 30px; color: #000000; font-weight: bold; border-bottom: 1px solid #ccc; }
            QTableWidget::item { color: #000000; padding-left: 5px; }
            QTableWidget::item:selected { background-color: #e3f2fd; color: #000; }
        """

    def get_tab_style(self):
        return """
            QTabWidget::pane { border: 1px solid #ccc; top: -1px; }
            QTabBar::tab { background: #f0f0f0; color: #333; padding: 6px 10px; min-width: 80px; border: 1px solid #ccc; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; font-size: 12px; }
            QTabBar::tab:selected { background: #ffffff; color: #2196F3; font-weight: bold; border-bottom: 2px solid #2196F3; }
            QTabBar::tab:hover { background: #e0e0e0; }
        """

    def get_btn_style(self, color):
        return f"QPushButton {{ background-color: {color}; color: white; border-radius: 4px; padding: 5px 15px; border: none; font-weight: bold; }} QPushButton:hover {{ opacity: 0.8; }}"

    def init_query_section(self):
        group = QGroupBox("动态作业查询")
        group.setStyleSheet(self.get_group_style())
        layout = QVBoxLayout(group)
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel("作业ID: <b style='color:#2196F3'>Job_1024</b>"))
        info_layout.addSpacing(20)
        info_layout.addWidget(QLabel("日期: <b>2023-11-26</b>"))
        info_layout.addStretch()
        layout.addLayout(info_layout)
        self.layout.addWidget(group)

    def init_tab_section(self):
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(self.get_tab_style())

        self.tab_mtfr = QWidget()
        self.init_tab_mtfr_ui(self.tab_mtfr)
        self.tabs.addTab(self.tab_mtfr, "时间切片与故障统计")

        self.tab_oee = QWidget()
        self.init_tab_oee_ui(self.tab_oee)
        self.tabs.addTab(self.tab_oee, "当班 OEE 统计")

        self.tab_schedule = QWidget()
        self.init_tab_schedule_ui(self.tab_schedule)
        self.tabs.addTab(self.tab_schedule, "作业执行情况统计")

        self.layout.addWidget(self.tabs, stretch=1)

    def init_tab_mtfr_ui(self, parent):
        layout = QVBoxLayout(parent)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)

        layout.addWidget(QLabel("设备运行状态时间切片:"))
        self.time_slice_bar = TimeSliceWidget(slices=self.shift_slices_viz, total_hours=self.total_shift_hours)
        layout.addWidget(self.time_slice_bar)

        total_mins = self.total_shift_hours * 60
        fault_count = 0
        total_fault_mins = 0
        total_run_mins = 0

        for start, end, type_code, reason, status in self.shift_data_full:
            duration = (end - start) * total_mins
            if type_code == 1:
                fault_count += 1
                total_fault_mins += duration
            elif type_code == 0:
                total_run_mins += duration

        mttr_val = total_fault_mins / fault_count if fault_count > 0 else 0
        mtbf_val = (total_run_mins / fault_count / 60) if fault_count > 0 else 0

        metrics_layout = QGridLayout()
        metrics_layout.setSpacing(15)

        def create_metric_card(title, value, subtext, bg_color):
            frame = QFrame()
            frame.setStyleSheet(f"background-color: {bg_color}; border-radius: 6px; border: 1px solid #e0e0e0;")
            l = QVBoxLayout(frame)
            lbl_t = QLabel(title);
            lbl_v = QLabel(value);
            lbl_s = QLabel(subtext)
            lbl_t.setStyleSheet("font-size:12px; color:#666; border:none; background:transparent;")
            lbl_v.setStyleSheet("font-size:22px; font-weight:bold; color:#333; border:none; background:transparent;")
            lbl_s.setStyleSheet("font-size:11px; color:#888; border:none; background:transparent;")
            l.addWidget(lbl_t);
            l.addWidget(lbl_v);
            l.addWidget(lbl_s)
            return frame

        self.card_mtbf = create_metric_card("平均故障间隔 (MTBF)", f"{mtbf_val:.1f} h", "目标: >4h", "#f9fbe7")
        self.card_mttr = create_metric_card("平均修复时间 (MTTR)", f"{mttr_val:.0f} min", "目标: <30min", "#fff3e0")
        self.card_downtime = create_metric_card("累计故障停机", f"{total_fault_mins / 60:.2f} h",
                                                f"班次总计: {self.total_shift_hours}h", "#ffebee")

        metrics_layout.addWidget(self.card_mtbf, 0, 0)
        metrics_layout.addWidget(self.card_mttr, 0, 1)
        metrics_layout.addWidget(self.card_downtime, 0, 2)
        layout.addLayout(metrics_layout)

        layout.addWidget(QLabel("故障事件统计:"))
        self.fault_table = QTableWidget(0, 5)
        self.fault_table.setHorizontalHeaderLabels(["时间切片ID", "故障类型", "持续时间", "修复状态", "操作"])
        self.fault_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.fault_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.fault_table.verticalHeader().setVisible(False)
        self.fault_table.setStyleSheet(self.get_table_style())
        self.fault_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        slice_duration_min = 15
        merge_spans = []

        for start, end, type_code, reason, status in self.shift_data_full:
            if type_code == 1:
                duration = (end - start) * total_mins
                start_min = start * total_mins
                end_min = end * total_mins

                start_slice_id = int(start_min // slice_duration_min) + 1
                end_slice_id = int((end_min - 0.01) // slice_duration_min) + 1

                start_row = self.fault_table.rowCount()

                for s_id in range(start_slice_id, end_slice_id + 1):
                    row = self.fault_table.rowCount()
                    self.fault_table.insertRow(row)

                    item_id = QTableWidgetItem(f"Slice_{s_id:02d}")
                    item_id.setForeground(QColor("#1565c0"))
                    item_id.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
                    self.fault_table.setItem(row, 0, item_id)

                    if row == start_row:
                        self.fault_table.setItem(row, 1, QTableWidgetItem(reason))
                        self.fault_table.setItem(row, 2, QTableWidgetItem(f"{duration:.0f} min"))

                        status_str = "已修复" if status == 0 else "未修复"
                        item_status = QTableWidgetItem(status_str)
                        if status == 1:
                            item_status.setForeground(QColor("#F44336"))
                            item_status.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
                        else:
                            item_status.setForeground(QColor("#4CAF50"))
                        self.fault_table.setItem(row, 3, item_status)

                        if status == 1:
                            btn_aas = QPushButton("发送维护工单")
                            btn_aas.setStyleSheet("""
                                QPushButton { background-color: #2196F3; color: white; border-radius: 3px; font-size: 11px; padding: 2px; }
                                QPushButton:hover { background-color: #1976D2; }
                            """)
                            btn_aas.clicked.connect(lambda _, r=reason, d=duration: self.send_fault_to_aas(r, d))
                            self.fault_table.setCellWidget(row, 4, btn_aas)
                        else:
                            self.fault_table.setItem(row, 4, QTableWidgetItem("-"))

                    else:
                        for c in range(1, 5): self.fault_table.setItem(row, c, QTableWidgetItem(""))

                row_span = end_slice_id - start_slice_id + 1
                if row_span > 1:
                    for c in range(1, 5):
                        merge_spans.append((start_row, c, row_span, 1))

        for r, c, rs, cs in merge_spans:
            self.fault_table.setSpan(r, c, rs, cs)

        layout.addWidget(self.fault_table)

    def send_fault_to_aas(self, reason, duration):
        QMessageBox.information(self, "AAS Integration",
                                f"【维护工单已发送】\n\n"
                                f"设备ID: Reactor_01\n"
                                f"故障代码: {reason}\n"
                                f"停机时长: {duration:.0f} min\n\n"
                                f"状态: 已通过 AAS 接口同步至 ERP 系统，维护人员将收到通知。")

    def init_tab_oee_ui(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        left_layout = QVBoxLayout()
        self.lbl_oee_score = QLabel("46.8%")
        self.lbl_oee_score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_oee_score.setStyleSheet("""
            font-size: 22px; font-weight: bold; color: #F44336; 
            border: 4px solid #FFCDD2; border-radius: 50px; background-color: white;
            min-width: 100px; min-height: 100px; max-width: 100px; max-height: 100px;
        """)
        score_box = QVBoxLayout()
        score_box.addWidget(QLabel("当班 OEE"))
        score_box.addWidget(self.lbl_oee_score)
        score_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addLayout(score_box)

        def create_bar(label, val, color):
            vbox = QVBoxLayout()
            hbox = QHBoxLayout()
            hbox.addWidget(QLabel(label))
            val_txt = QLabel(f"{val}%")
            val_txt.setStyleSheet(f"color:{color}; font-weight:bold;")
            hbox.addWidget(val_txt)
            hbox.addStretch()
            vbox.addLayout(hbox)
            bar = QProgressBar()
            bar.setValue(int(val))
            bar.setFixedHeight(6)
            bar.setTextVisible(False)
            bar.setStyleSheet(
                f"QProgressBar {{background:#f0f0f0; border-radius:3px;}} QProgressBar::chunk {{background:{color}; border-radius:3px;}}")
            vbox.addWidget(bar)
            return vbox

        left_layout.addLayout(create_bar("A (可用性):", 55.6, "#FF9800"))
        left_layout.addLayout(create_bar("P (性能):", 84.7, "#2196F3"))
        left_layout.addLayout(create_bar("Q (质量):", 99.3, "#4CAF50"))
        left_layout.addStretch()

        right_group = QGroupBox("时间损失分析")
        right_group.setStyleSheet(self.get_group_style())
        rg_layout = QFormLayout(right_group)
        rg_layout.setSpacing(8)

        self.lbl_total_time = QLabel("5.67 h (340 min)")
        self.lbl_loading_time = QLabel("4.41 h")
        self.lbl_operating_time = QLabel("3.15 h")
        self.lbl_net_operating_time = QLabel("2.67 h")
        self.lbl_effective_time = QLabel("2.65 h")

        for lbl in [self.lbl_total_time, self.lbl_loading_time, self.lbl_operating_time, self.lbl_net_operating_time,
                    self.lbl_effective_time]:
            lbl.setStyleSheet("color: #333; font-weight: bold;")

        rg_layout.addRow("1. 计划总时间:", self.lbl_total_time)
        lbl_loss_plan = QLabel("- 1.26 h (设备调试/清场)")
        lbl_loss_plan.setStyleSheet("color: #757575;")
        rg_layout.addRow("   [计划损失]:", lbl_loss_plan)

        rg_layout.addRow("2. 负荷时间:", self.lbl_loading_time)
        lbl_loss_unplan = QLabel("- 1.26 h (反应釜故障/缺料)")
        lbl_loss_unplan.setStyleSheet("color: #F44336;")
        rg_layout.addRow("   [停机损失]:", lbl_loss_unplan)

        rg_layout.addRow("3. 稼动时间:", self.lbl_operating_time)
        lbl_loss_perf = QLabel("- 0.48 h (搅拌速度低下)")
        lbl_loss_perf.setStyleSheet("color: #FF9800;")
        rg_layout.addRow("   [性能损失]:", lbl_loss_perf)

        rg_layout.addRow("4. 净稼动时间:", self.lbl_net_operating_time)
        lbl_loss_qual = QLabel("- 0.02 h (反应不完全)")
        lbl_loss_qual.setStyleSheet("color: #9C27B0;")
        rg_layout.addRow("   [质量损失]:", lbl_loss_qual)

        rg_layout.addRow("5. 有效生产时间:", self.lbl_effective_time)

        top_layout.addLayout(left_layout, stretch=2)
        top_layout.addWidget(right_group, stretch=3)
        layout.addWidget(top_widget, stretch=4)

        details_group = QGroupBox("停机事件详情")
        details_group.setStyleSheet(self.get_group_style())
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(5, 5, 5, 5)

        self.details_table = QTableWidget(0, 6)
        headers = ["日期", "时间段", "时长(min)", "时长(h)", "原因", "类别"]
        self.details_table.setHorizontalHeaderLabels(headers)
        self.details_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.details_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.details_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.details_table.verticalHeader().setVisible(False)
        self.details_table.setStyleSheet(self.get_table_style())

        csv_data = [
            ("11.26", "08:00-08:09", "9", "0.15", "设备调试", "计划内停机"),
            ("11.26", "08:09-09:15", "66", "1.11", "清场", "计划内停机"),
            ("11.26", "10:30-11:15", "45", "0.75", "反应釜搅拌电机异常", "设备故障"),
            ("11.26", "14:00-14:30", "30", "0.51", "缺少原液", "缺少原液"),
        ]

        for row_data in csv_data:
            row = self.details_table.rowCount()
            self.details_table.insertRow(row)
            for col, text in enumerate(row_data):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 5:
                    if "故障" in text:
                        item.setForeground(QColor("#F44336"))
                        item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
                    elif "缺少原液" in text:
                        item.setForeground(QColor("#FF9800"))
                    elif "计划内" in text:
                        item.setForeground(QColor("#757575"))
                self.details_table.setItem(row, col, item)

        details_layout.addWidget(self.details_table)
        layout.addWidget(details_group, stretch=5)

    def init_tab_schedule_ui(self, parent):
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        lbl_chart = QLabel("输入/输出控制图 (当周)")
        lbl_chart.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        layout.addWidget(lbl_chart)

        # 使用更新了阶梯图逻辑的 Chart Widget
        self.chart_widget = InputOutputChartWidget()
        layout.addWidget(self.chart_widget, stretch=1)

        lbl_list = QLabel("作业排程详情")
        lbl_list.setStyleSheet("font-size: 14px; font-weight: bold; color: #333; margin-top: 10px;")
        layout.addWidget(lbl_list)

        self.schedule_table = QTableWidget(0, 6)
        headers = ["作业ID", "订单截止日", "时间容差", "最优批量", "计划提前期", "状态判定"]
        self.schedule_table.setHorizontalHeaderLabels(headers)
        self.schedule_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.schedule_table.verticalHeader().setVisible(False)
        self.schedule_table.setStyleSheet(self.get_table_style())

        data = [
            ("J_1024", "11-28", "4.5 h", "520 kg", "3.8 h", "安全负载"),
            ("J_1025", "11-29", "2.0 h", "450 kg", "2.2 h", "SPLIT_REQUIRED"),
            ("J_1026", "11-30", "5.0 h", "600 kg", "4.1 h", "安全负载")
        ]

        for row_data in data:
            row = self.schedule_table.rowCount()
            self.schedule_table.insertRow(row)
            for idx, text in enumerate(row_data):
                if idx == 5:
                    if text == "SPLIT_REQUIRED":
                        btn_split = QPushButton("请拆分该批次")
                        btn_split.setStyleSheet("""
                            QPushButton { background-color: #FF9800; color: white; border-radius: 3px; font-weight: bold; padding: 3px; }
                            QPushButton:hover { background-color: #F57C00; }
                        """)
                        btn_split.clicked.connect(lambda _, j_id=row_data[0]: self.open_split_dialog(j_id))
                        self.schedule_table.setCellWidget(row, idx, btn_split)
                    else:
                        item = QTableWidgetItem(text)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        item.setForeground(QColor("#4CAF50"))
                        item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
                        self.schedule_table.setItem(row, idx, item)
                else:
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.schedule_table.setItem(row, idx, item)

        layout.addWidget(self.schedule_table, stretch=1)

    def open_split_dialog(self, job_id):
        dialog = SplitOrderDialog(job_id, self)
        dialog.exec()

    def init_maintenance_section(self):
        group = QGroupBox("维护决策")
        group.setStyleSheet(self.get_group_style())
        layout = QHBoxLayout(group)
        layout.addWidget(QLabel(
            " 异常检测: <b>反应釜搅拌电机异常 (频发)</b> -> 建议: <span style='color:red'>检查变频器与减速机</span>"))
        layout.addStretch()
        btn = QPushButton("生成工单")
        btn.setStyleSheet(self.get_btn_style("#F44336"))
        btn.clicked.connect(self.open_work_order_dialog)
        layout.addWidget(btn)
        self.layout.addWidget(group)

    def update_simulation_data(self):
        pass

    def open_work_order_dialog(self):
        QMessageBox.information(self, "Action", "工单已生成")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DecisionSupportPage()
    window.resize(1000, 750)
    window.show()
    sys.exit(app.exec())