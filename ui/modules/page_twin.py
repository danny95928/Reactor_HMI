import sys
import os
import random
import math
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QGroupBox, QTableWidget, QTableWidgetItem,
                             QTreeWidget, QTreeWidgetItem, QHeaderView,
                             QFrame, QPushButton, QSplitter, QProgressBar, QTextEdit,
                             QDialog, QListWidget, QListWidgetItem, QAbstractItemView, QMessageBox, QDialogButtonBox,
                             QComboBox, QSpinBox, QFormLayout, QButtonGroup, QRadioButton, QCheckBox, QLayout,
                             QApplication)
from PyQt6.QtCore import Qt, QTimer, QMimeData, QRect, QPointF
from PyQt6.QtGui import QColor, QBrush, QFont, QDrag, QIcon, QPainter, QPixmap

# === 尝试导入数据科学库 (用于 t-SNE 和 模型加载) ===
try:
    import pandas as pd
    import joblib
    import numpy as np
    from sklearn.manifold import TSNE
    from sklearn.preprocessing import MinMaxScaler

    HAS_ML_LIBS = True
except ImportError:
    HAS_ML_LIBS = False
    print("提示: 缺少 pandas/joblib/sklearn，将运行在纯模拟模式")

# === 尝试导入 3D 绘图库 PyVista ===
try:
    import pyvista as pv
    from pyvistaqt import QtInteractor

    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False
    print("提示: 未安装 pyvistaqt，将使用占位符显示 3D 区域")


# ============================================================================
# 0. 自定义组件：支持拖拽逻辑的列表
# ============================================================================
class DraggableListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item: return
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(item.text())
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)


class DroppableListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        model_name = event.mimeData().text()
        target_item = self.itemAt(event.position().toPoint())
        if target_item:
            original_text = target_item.data(Qt.ItemDataRole.UserRole)
            if not original_text:
                original_text = target_item.text()
                target_item.setData(Qt.ItemDataRole.UserRole, original_text)
            target_item.setText(f"{original_text}\n   ↳ 待执行算法: [{model_name}]")
            target_item.setBackground(QColor("#e8f5e9"))
            target_item.setForeground(QBrush(QColor("#2e7d32")))
            event.accept()
        else:
            event.ignore()


# ============================================================================
# NEW CLASS: 模型参数设置模态框
# ============================================================================
class ModelParamsDialog(QDialog):
    def __init__(self, model_type="unknown", model_name="", batch_items=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"参数配置 - {model_name}" if model_name else "模型参数设置")
        self.current_model_type = model_type

        self.setStyleSheet("""
            QDialog { background-color: #f5f5f5; color: black; font-family: 'Microsoft YaHei', 'Segoe UI'; font-size: 13px; }
            QGroupBox { background-color: #f5f5f5; font-weight: bold; border: 1px solid #ccc; margin-top: 10px; padding-top: 15px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QComboBox, QSpinBox, QListWidget, QLineEdit { background-color: #ffffff; border: 1px solid #ccc; border-radius: 3px; padding: 4px; }
        """)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        layout.setContentsMargins(25, 25, 25, 25)

        self.lbl_error = QLabel("未检测到选中的模型类型")
        self.lbl_error.setStyleSheet("color: red; font-weight: bold; padding: 20px;")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_error)

        # 1. 时序分析
        self.group_ts = QGroupBox("时序分析参数")
        self.group_ts.setStyleSheet("QGroupBox { border: 1px solid #d35400; } QGroupBox::title { color: #d35400; }")
        layout_ts = QFormLayout(self.group_ts)
        self.combo_ts_model = QComboBox()
        self.combo_ts_model.addItems(["LSTM (长短期记忆网络)", "BiGRU (双向GRU)"])
        self.spin_step = QSpinBox()
        self.spin_step.setRange(1, 9999)
        self.spin_step.setValue(5)
        self.spin_step.setSuffix(" 步")
        self.combo_attention = QComboBox()
        self.combo_attention.addItems(["自注意力 (Self-Attention)", "多头注意力 (Multi-head)"])
        layout_ts.addRow("模型架构:", self.combo_ts_model)
        layout_ts.addRow("采样步长:", self.spin_step)
        layout_ts.addRow("注意力机制:", self.combo_attention)
        layout.addWidget(self.group_ts)

        # 2. 深度学习
        self.group_dl = QGroupBox("深度学习参数")
        self.group_dl.setStyleSheet("QGroupBox { border: 1px solid #1976D2; } QGroupBox::title { color: #1976D2; }")
        layout_dl = QFormLayout(self.group_dl)
        self.chk_spectrogram = QCheckBox("启用频谱转换")
        self.combo_dl_model = QComboBox()
        self.combo_dl_model.addItems(["CNN (一维卷积)", "ResNet (残差网络)", "ViT (Transformer)"])
        layout_dl.addRow("数据预处理:", self.chk_spectrogram)
        layout_dl.addRow("骨干网络:", self.combo_dl_model)
        layout.addWidget(self.group_dl)

        # 3. 知识抽取
        self.group_kg = QGroupBox("知识抽取参数")
        self.group_kg.setStyleSheet("QGroupBox { border: 1px solid #7B1FA2; } QGroupBox::title { color: #7B1FA2; }")
        layout_kg = QFormLayout(self.group_kg)
        self.list_batches = QListWidget()
        self.list_batches.setFixedHeight(80)
        if batch_items:
            for txt in batch_items:
                item = QListWidgetItem(txt)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.list_batches.addItem(item)
        else:
            self.list_batches.addItem("无可用批次")
            self.list_batches.setEnabled(False)

        lay_embed = QHBoxLayout()
        self.chk_128 = QCheckBox("128 维")
        self.chk_128.setChecked(True)
        self.chk_256 = QCheckBox("256 维")
        lay_embed.addWidget(self.chk_128)
        lay_embed.addWidget(self.chk_256)
        lay_embed.addStretch()

        self.chk_ner = QCheckBox("执行实体识别")
        self.chk_ner.setChecked(True)
        self.combo_kg_model = QComboBox()
        self.combo_kg_model.addItems(["BERT-Base (中文版)", "BERT-PCNN"])
        layout_kg.addRow("目标批次:", self.list_batches)
        layout_kg.addRow("嵌入维度:", lay_embed)
        layout_kg.addRow("功能开关:", self.chk_ner)
        layout_kg.addRow("预训练模型:", self.combo_kg_model)
        layout.addWidget(self.group_kg)

        self.group_ts.setVisible(False)
        self.group_dl.setVisible(False)
        self.group_kg.setVisible(False)
        self.lbl_error.setVisible(False)

        if model_type == "time_series":
            self.group_ts.setVisible(True)
        elif model_type == "deep_learning":
            self.group_dl.setVisible(True)
        elif model_type == "knowledge_graph":
            self.group_kg.setVisible(True)
        else:
            self.lbl_error.setVisible(True)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_settings(self):
        params = []
        if self.current_model_type == "time_series":
            params.append(f"模型: {self.combo_ts_model.currentText().split(' ')[0]}")
            params.append(f"步长: {self.spin_step.value()}")
            params.append(f"机制: {self.combo_attention.currentText().split(' ')[0]}")
        elif self.current_model_type == "deep_learning":
            params.append(f"频谱图: {'是' if self.chk_spectrogram.isChecked() else '否'}")
            params.append(f"网络: {self.combo_dl_model.currentText().split(' ')[0]}")
        elif self.current_model_type == "knowledge_graph":
            dims = []
            if self.chk_128.isChecked(): dims.append("128")
            if self.chk_256.isChecked(): dims.append("256")
            dim_str = "+".join(dims) + "维" if dims else "无"
            params.append(f"维度: {dim_str}")
            params.append(f"NER: {'启用' if self.chk_ner.isChecked() else '禁用'}")
            params.append(f"模型: {self.combo_kg_model.currentText().split(' ')[0]}")
        return " | ".join(params)


# ============================================================================
# 1. 模态框：机器学习通道
# ============================================================================
class MLChannelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("机器学习任务通道与算法配置")
        self.resize(1100, 650)
        self.setStyleSheet("background-color: #f5f5f5; color: black; font-family: 'Microsoft YaHei', 'Segoe UI';")
        self.current_param_str = "参数: 默认设置"

        # 存储真实数据
        self.loaded_df = None

        main_layout = QHBoxLayout(self)

        # === 左侧 ===
        left_group = QGroupBox("1. 待处理批次与设备")
        left_group.setStyleSheet("QGroupBox { font-weight: bold; background: white; border: 1px solid #ccc; }")
        left_layout = QVBoxLayout(left_group)

        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.btn_preprocess = QPushButton("数据预处理")
        self.btn_preprocess.setStyleSheet(
            "background-color: #2196F3; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_preprocess.clicked.connect(self.on_preprocess_and_load)
        top_bar.addWidget(self.btn_preprocess)
        left_layout.addLayout(top_bar)

        self.batch_list = DroppableListWidget()
        self.batch_list.setStyleSheet("""
            QListWidget { border: 1px solid #ccc; background: #ffffff; font-size: 13px; border-radius: 4px; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #f0f0f0; color: #333; }
            QListWidget::item:selected { background-color: #e3f2fd; color: #1565C0; border-left: 4px solid #1565C0; }
        """)
        self.batch_list.addItem("请先点击 [数据预处理]...")
        self.batch_list.item(0).setFlags(Qt.ItemFlag.NoItemFlags)
        left_layout.addWidget(self.batch_list)

        self.lbl_left_status = QLabel("状态: 等待数据接入...")
        self.lbl_left_status.setStyleSheet("color: #666; margin-top: 5px; font-size: 11px;")
        left_layout.addWidget(self.lbl_left_status)
        main_layout.addWidget(left_group, stretch=5)

        # === 中间 ===
        arrow_layout = QVBoxLayout()
        arrow_layout.addStretch()
        lbl_arrow = QLabel("拖拽配置")
        lbl_arrow.setStyleSheet("color: #999; font-weight: bold;")
        arrow_layout.addWidget(lbl_arrow)
        arrow_layout.addStretch()
        main_layout.addLayout(arrow_layout)

        # === 右侧 ===
        right_group = QGroupBox("2. 算法模型库")
        right_group.setStyleSheet("""
            QGroupBox { font-weight: bold; background: white; border: 1px solid #ccc; margin-top: 10px; padding-top: 25px; }
            QGroupBox::title { subcontrol-origin: margin; top: 0px; left: 10px; padding: 0 5px; }
        """)
        right_layout = QVBoxLayout(right_group)
        right_layout.setContentsMargins(10, 20, 10, 10)

        self.model_list = DraggableListWidget()
        self.model_list.setSpacing(8)
        self.model_list.setStyleSheet("""
            QListWidget { border: 2px dashed #B0BEC5; background: #F5F7FA; font-size: 12px; outline: none; border-radius: 6px; }
            QListWidget::item { background: #FFFFFF; border: 1px solid #CFD8DC; border-radius: 6px; padding: 10px; margin: 2px 4px; color: #333; }
            QListWidget::item:hover { background: #FFF9C4; border: 1px solid #FBC02D; }
            QListWidget::item:selected { background: #FFF176; border: 2px solid #FBC02D; color: #000; }
        """)
        self.add_model_item("时序分析: LSTM-Attention", "time_series", "适用于处理长序列时间依赖。")
        self.add_model_item("时序分析: Prophet", "time_series", "适合分析周期性与节假日效应。")
        self.add_model_item("深度学习: 1D-CNN", "deep_learning", "快速提取局部特征波形。")
        self.add_model_item("深度学习: ViT (Transformer)", "deep_learning", "基于自注意力机制建模。")
        self.add_model_item("知识抽取: BERT-PCNN", "knowledge_graph", "高效抽取实体间的语义关系。")
        right_layout.addWidget(self.model_list)

        lbl_inst = QLabel("请将模型拖拽至左侧对应批次中")
        lbl_inst.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_inst.setStyleSheet("color: #777; font-style: italic; margin: 10px 0;")
        right_layout.addWidget(lbl_inst)

        btn_layout = QHBoxLayout()
        self.btn_settings = QPushButton("模型参数设置")
        self.btn_settings.setStyleSheet(
            "QPushButton { background-color: #607D8B; color: white; padding: 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #546E7A; }")
        self.btn_settings.clicked.connect(self.open_settings)
        btn_exec = QPushButton("执行选中模型")
        btn_exec.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; padding: 10px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #43A047; }")
        btn_exec.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_settings)
        btn_layout.addWidget(btn_exec)
        right_layout.addLayout(btn_layout)
        main_layout.addWidget(right_group, stretch=4)

    def add_model_item(self, name, model_type, description=""):
        item = QListWidgetItem(f"{name}\n{description}")
        item.setData(Qt.ItemDataRole.UserRole + 1, model_type)
        item.setToolTip(description)
        self.model_list.addItem(item)

    def on_preprocess_and_load(self):
        self.batch_list.clear()
        self.btn_preprocess.setText("处理中...")
        self.btn_preprocess.setEnabled(False)
        QTimer.singleShot(600, self._populate_list_from_csv)

    def _populate_list_from_csv(self):
        # 修正：使用正确的相对路径
        csv_path = os.path.join("ui", "modules", "dataset", "reactor_process_data.csv")

        if not HAS_ML_LIBS or not os.path.exists(csv_path):
            print(f"⚠️ 无法读取 CSV: {csv_path} (文件不存在或缺少pandas)")
            self._populate_list_dummy()
            return

        try:
            full_df = pd.read_csv(csv_path)
            self.loaded_df = full_df.sample(n=min(30, len(full_df)))

            for index, row in self.loaded_df.iterrows():
                # 🔥🔥🔥 修改点：固定批次号和设备编号
                batch_id = "B20241123"
                device_id = "QDZY-001"
                quality = "正常" if row['Code_Quality'] == 'Q_P' else "异常"

                display_text = f"批次: {batch_id} | 设备: {device_id} | 标签: {quality}"

                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, display_text)
                item.setData(Qt.ItemDataRole.UserRole + 2, row.to_dict())
                self.batch_list.addItem(item)

            self.lbl_left_status.setText(f"状态: 已加载 {len(self.loaded_df)} 条真实记录")
            self.btn_preprocess.setText("数据已加载")
            self.btn_preprocess.setEnabled(True)
            print(f"✅ 成功从 {csv_path} 加载数据")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"CSV 读取失败: {str(e)}\n切换到模拟模式")
            self._populate_list_dummy()

    def _populate_list_dummy(self):
        results = [
            "批次: B20241123 | 设备: QDZY-001 | 状态: 完成",
            "批次: B20241123 | 设备: QDZY-001 | 状态: 异常(High Visc)",
            "批次: B20241123 | 设备: QDZY-001 | 状态: 运行",
            "批次: B20241123 | 设备: QDZY-001 | 状态: 待机",
            "批次: B20241123 | 设备: QDZY-001 | 状态: 异常(Temp Dev)"
        ]
        self.loaded_df = None
        for r in results:
            item = QListWidgetItem(r)
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.batch_list.addItem(item)
        self.lbl_left_status.setText(f"状态: 已加载 {len(results)} 条模拟记录")
        self.btn_preprocess.setText("数据已就绪")
        self.btn_preprocess.setEnabled(True)

    def open_settings(self):
        selected_items = self.model_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请先在右侧列表中选中一个模型算法！")
            return
        item = selected_items[0]
        model_name = item.text().split('\n')[0]
        model_type = item.data(Qt.ItemDataRole.UserRole + 1)
        batch_items = []
        for i in range(self.batch_list.count()):
            txt = self.batch_list.item(i).text()
            if "批次:" in txt: batch_items.append(txt.split('|')[0].strip())
        dialog = ModelParamsDialog(model_type, model_name, batch_items, self)
        if dialog.exec():
            self.current_param_str = dialog.get_settings()
            QMessageBox.information(self, "设置已保存", f"参数已暂存:\n{self.current_param_str}")

    def get_selected_pipeline(self):
        count = 0
        last_model = "无"
        for i in range(self.batch_list.count()):
            txt = self.batch_list.item(i).text()
            if "待执行算法" in txt:
                count += 1
                last_model = txt.split("[")[1].split("]")[0]
        return f"{last_model} 等" if count > 0 else "未选择"

    def get_batch_data_for_analysis(self):
        if self.loaded_df is None: return None
        features = []
        labels = []
        raw_info_list = []
        feature_cols = ['Speed_Raw', 'Temp_Raw', 'Viscosity_Raw', 'MassFrac_Raw', 'MixTime_Raw']
        for i in range(self.batch_list.count()):
            item = self.batch_list.item(i)
            row_data = item.data(Qt.ItemDataRole.UserRole + 2)
            if row_data:
                vec = [row_data.get(c, 0) for c in feature_cols]
                features.append(vec)
                tag = "Anomaly" if row_data.get('Code_Quality') == 'Q_F' else "Normal"
                labels.append(tag)
                raw_info_list.append({
                    "status_tag": tag,
                    "model_assigned": "待执行算法" in item.text()
                })
        if not features: return None
        return np.array(features), labels, raw_info_list


# ============================================================================
# 2. 模态框：工艺标签定义 (Process Tag Definitions)
# ============================================================================
class ProcessTagDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("工艺中心线标签定义")
        self.resize(1000, 650)
        self.setStyleSheet("background-color: #ffffff; color: black; font-family: 'Segoe UI';")

        layout = QVBoxLayout(self)
        lbl_title = QLabel("工艺变量分箱与编码规则库")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; margin-bottom: 10px;")
        layout.addWidget(lbl_title)

        self.table = QTableWidget()
        headers = ["工艺变量", "符号与量纲", "变量分箱", "项集", "编码"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        # 恢复完整的样式表
        self.table.setStyleSheet("""
            QTableWidget { border: 1px solid #ccc; gridline-color: #eee; font-size: 13px; }
            QHeaderView::section { background-color: #f0f0f0; border: none; border-bottom: 2px solid #007acc; height: 35px; font-weight: bold; color: #333; }
            QTableWidget::item { padding: 6px; color: black; }
        """)

        data = [
            ("搅拌转速", "（N）rad/s", "[0,20]", "{Speed: L_Shear}", "N_0020"),
            ("", "", "(20,40]", "{Speed: M_ Shear}", "N_2040"),
            ("", "", "(40,60]", "{Speed: H_ Shear}", "N_4060"),
            ("", "", "(60,80]", "{Speed: E_ Shear}", "N_6080"),
            ("温度", "（T）℃", "[0,10]", "{Temp: V_Low}", "T_010"),
            ("", "", "(10,20]", "{Temp: Low}", "T_1020"),
            ("", "", "(20,30]", "{Temp: Ambient}", "T_2030"),
            ("", "", "(30,40]", "{Temp: Mild}", "T_3040"),
            ("", "", "(40,50]", "{Temp: Warm}", "T_4050"),
            ("", "", "(50,60]", "{Temp: Hot}", "T_5060"),
            ("原液粘度", "（μ）Pa·s", "[0,0.45]", "{Visc: V_Low}", "V_0045"),
            ("", "", "(0.45,0.50]", "{Visc: T_Low}", "V_4550"),
            ("质量占比", "（Mmix）wt%", "(0,5]", "{WF: T_Amt}", "WF_0005"),
            ("", "", "(5,15]", "{WF: C_Amt}", "WF_0515"),
            ("混合时间", "（tmix）min", "[0,10]", "{MT: V_Fast}", "TM_VFast"),
            ("加热时间", "（theat）min", "[0,10]", "{HT: Fast}", "HT_Fast"),
            ("冷却时间", "（tcold）min", "[0,10]", "{CT: V_Fast}", "CT_VFast"),
            ("所在阶段", "Si", "1", "{Phase: Charging}", "PH_1"),
            ("", "", "2", "{Phase: Reaction}", "PH_2"),
            ("合格标签", "Qi", "0", "{Quality: Pass}", "Q_P"),
            ("", "", "1", "{Quality: Fail}", "Q_F"),
        ]

        self.table.setRowCount(len(data))
        for r, row_data in enumerate(data):
            for c, val in enumerate(row_data):
                item = QTableWidgetItem(val)
                item.setForeground(QBrush(QColor("black")))
                if c == 0 and val != "":
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(QColor("#e3f2fd"))
                self.table.setItem(r, c, item)
        layout.addWidget(self.table)

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; padding: 8px 30px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background-color: #1976D2; }")
        btn_close.clicked.connect(self.accept)
        h_btn = QHBoxLayout()
        h_btn.addStretch()
        h_btn.addWidget(btn_close)
        layout.addLayout(h_btn)


# ============================================================================
# 自定义可拖拽缩放的散点图组件
# ============================================================================
class ClusterScatterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setStyleSheet("background-color: #ffffff; border: 1px solid #ccc; border-radius: 4px;")
        self.points = []
        self.colors = [QColor("#4CAF50"), QColor("#F44336"), QColor("#2196F3"), QColor("#FF9800")]
        self.chart_title = ""
        self.chart_params = ""
        self.scale_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.last_mouse_pos = None
        self.setVisible(False)

    def set_info(self, title, params):
        self.chart_title = title
        self.chart_params = params
        self.update()

    def update_data_points(self, points_list):
        self.points = points_list
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        header_height = 40

        painter.setPen(QColor("#f9f9f9"))
        grid_step = 40
        for i in range(header_height, h, grid_step): painter.drawLine(0, i, w, i)
        for i in range(0, w, grid_step): painter.drawLine(i, header_height, i, h)

        if self.chart_title:
            painter.setPen(QColor("#333"))
            painter.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
            painter.drawText(10, 25, self.chart_title)

        if self.chart_params:
            painter.setPen(QColor("#555"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            param_rect = QRect(200, 5, w - 210, 30)
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e3f2fd"))
            painter.drawRoundedRect(param_rect, 4, 4)
            painter.restore()
            painter.drawText(param_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"配置: {self.chart_params}  ")

        painter.setPen(QColor("#ddd"))
        painter.drawLine(0, header_height, w, header_height)

        plot_h = h - header_height
        center_y = header_height + plot_h / 2
        painter.translate(w / 2 + self.offset_x, center_y + self.offset_y)
        painter.scale(self.scale_factor, self.scale_factor)

        base_size = min(w, plot_h) * 0.8
        radius = 8
        painter.setPen(Qt.PenStyle.NoPen)

        for item in self.points:
            x, y, c_idx = item[0], item[1], item[2]
            px = (x - 0.5) * base_size
            py = (y - 0.5) * base_size * -1
            color = self.colors[c_idx % len(self.colors)]
            painter.setBrush(QBrush(color))
            painter.drawEllipse(int(px - radius / 2), int(py - radius / 2), radius, radius)

    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        self.scale_factor *= 1.1 if angle > 0 else 0.9
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.last_mouse_pos:
            delta = event.pos() - self.last_mouse_pos
            self.offset_x += delta.x()
            self.offset_y += delta.y()
            self.last_mouse_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        self.last_mouse_pos = None
        self.setCursor(Qt.CursorShape.ArrowCursor)


# ============================================================================
# 3. 主页面 (TwinDataPage)
# ============================================================================
class TwinDataPage(QWidget):
    def __init__(self):
        super().__init__()
        self.model_path = r"E:\Thesis\Reactor_HMI\model\reactor.obj"
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.left_panel = QWidget()
        self.init_3d_panel()
        splitter.addWidget(self.left_panel)

        self.right_panel = QWidget()
        self.init_data_panel()
        splitter.addWidget(self.right_panel)

        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)
        self.layout.addWidget(splitter)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(2000)

    def init_3d_panel(self):
        layout = QVBoxLayout(self.left_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        group = QGroupBox("3D 孪生可视化")
        group.setStyleSheet(self.get_group_style())
        g_layout = QVBoxLayout(group)

        if 'HAS_PYVISTA' in globals() and HAS_PYVISTA:
            self.plotter = QtInteractor(self.left_panel)
            self.plotter.set_background('white')
            self.load_3d_model()
            g_layout.addWidget(self.plotter.interactor)
        else:
            lbl = QLabel("未检测到 3D 库 (pyvistaqt)\n\n无法加载模型")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background-color: #eee; color: #555; border: 1px dashed #999;")
            g_layout.addWidget(lbl)

        ctrl_layout = QHBoxLayout()
        btn_reset = QPushButton("复位视图")
        btn_iso = QPushButton("等轴测")
        btn_front = QPushButton("前视图")
        for btn in [btn_reset, btn_iso, btn_front]:
            btn.setStyleSheet(
                "QPushButton { background-color: #e0e0e0; border: 1px solid #ccc; padding: 5px 10px; border-radius: 3px; color: #333; }")

        if 'HAS_PYVISTA' in globals() and HAS_PYVISTA:
            btn_reset.clicked.connect(self.reset_view)
            btn_iso.clicked.connect(lambda: self.plotter.view_isometric())
            btn_front.clicked.connect(lambda: self.plotter.view_xz())

        ctrl_layout.addWidget(btn_reset)
        ctrl_layout.addWidget(btn_iso)
        ctrl_layout.addWidget(btn_front)
        ctrl_layout.addStretch()
        g_layout.addLayout(ctrl_layout)
        layout.addWidget(group)

    def load_3d_model(self):
        try:
            if os.path.exists(self.model_path):
                mesh = pv.read(self.model_path)
                self.plotter.add_mesh(mesh, show_edges=False, smooth_shading=True)
            else:
                cylinder = pv.Cylinder(radius=3, height=8, center=(0, 0, 0), direction=(0, 0, 1))
                self.plotter.add_mesh(cylinder, color='#dcdcdc', show_edges=False)
            self.reset_view()
        except Exception as e:
            print(f"3D Error: {e}")

    def reset_view(self):
        if 'HAS_PYVISTA' in globals() and not HAS_PYVISTA: return
        self.plotter.view_xy()
        self.plotter.reset_camera()

    def init_data_panel(self):
        layout = QVBoxLayout(self.right_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # === 上半部分：溯源分析 ===
        group_rule = QGroupBox("溯源分析与异常模式挖掘")
        group_rule.setStyleSheet(self.get_group_style())
        rule_layout = QVBoxLayout(group_rule)

        self.rule_table = QTableWidget(0, 2)
        self.rule_table.setHorizontalHeaderLabels(["关联规则", "置信度"])
        self.rule_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.rule_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.rule_table.setColumnWidth(1, 80)
        self.rule_table.verticalHeader().setVisible(False)
        self.rule_table.setAlternatingRowColors(True)
        # 🔥 恢复了完整的样式
        self.rule_table.setStyleSheet("""
            QTableWidget { background-color: white; color: black; gridline-color: #f0f0f0; border: none; }
            QHeaderView::section { background-color: #f5f5f5; color: black; font-weight: bold; border: none; border-bottom: 1px solid #ccc; height: 25px; }
            QTableWidget::item { color: black; }
        """)
        # 🔥 恢复了3条规则
        self.rules = [
            ("{Temp > 90°C} -> {Viscosity < 20}", 0.85),
            ("{Pressure > 3Bar} & {Valve=Closed} -> {Alarm}", 0.92),
            ("{Speed < 50rpm} -> {Mixing=Poor}", 0.78)
        ]
        self.refresh_rules()
        rule_layout.addWidget(self.rule_table)

        btn_container = QHBoxLayout()
        self.btn_mining = QPushButton("机器学习通道")
        self.btn_tagging = QPushButton("工艺标签")
        for btn in [self.btn_mining, self.btn_tagging]:
            btn.setStyleSheet(
                "background-color: #e3f2fd; color: #0d47a1; border: 1px solid #2196F3; padding: 6px; border-radius: 4px; font-weight: bold;")
        self.btn_mining.clicked.connect(self.open_ml_channel)
        self.btn_tagging.clicked.connect(self.open_tag_dialog)
        btn_container.addWidget(self.btn_mining)
        btn_container.addWidget(self.btn_tagging)
        rule_layout.addLayout(btn_container)

        self.scatter_plot = ClusterScatterWidget()
        rule_layout.addWidget(self.scatter_plot)

        # Centerline Frame
        centerline_frame = QFrame()
        centerline_frame.setStyleSheet("background-color: #f4f6f8; border: 1px solid #d0d0d0; border-radius: 4px;")
        cl_layout = QVBoxLayout(centerline_frame)
        cl_layout.setContentsMargins(8, 8, 8, 8)
        cl_layout.setSpacing(6)
        lbl_cl_title = QLabel("📊 工艺中心线对比与状态评估")
        lbl_cl_title.setStyleSheet("font-weight: bold; color: #000000; border: none; font-size: 11px;")
        cl_layout.addWidget(lbl_cl_title)

        self.bar_temp = self.create_deviation_bar("温度偏差")
        self.bar_press = self.create_deviation_bar("压力偏差")
        cl_layout.addLayout(self.bar_temp)
        cl_layout.addLayout(self.bar_press)

        self.lbl_archive_status = QLabel("状态: [正常运行] | 数据已成功归档")
        self.lbl_archive_status.setStyleSheet(
            "color: #2e7d32; font-weight: bold; font-size: 10px; border: none; margin-top: 5px;")
        self.lbl_archive_status.setAlignment(Qt.AlignmentFlag.AlignRight)
        cl_layout.addWidget(self.lbl_archive_status)
        rule_layout.addWidget(centerline_frame)

        layout.addWidget(group_rule, stretch=6)

        # === 下半部分：知识图谱 ===
        group_kg = QGroupBox("工业知识图谱")
        group_kg.setStyleSheet(self.get_group_style())
        kg_layout = QVBoxLayout(group_kg)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["头实体", "关系", "尾实体"])
        self.tree.setStyleSheet(self.get_tree_style())
        self.tree.setColumnWidth(0, 120)
        self.tree.setColumnWidth(1, 80)
        self.init_knowledge_graph()
        kg_layout.addWidget(self.tree)
        layout.addWidget(group_kg, stretch=4)

    def generate_process_features(self, count=1):
        features = []
        for _ in range(count):
            speed = random.normalvariate(40, 25)
            temp = random.normalvariate(35, 20)
            visc = random.normalvariate(0.25, 0.2)
            mass = random.normalvariate(7, 5)
            vec = [
                max(0, min(100, speed)), max(0, min(80, temp)),
                max(0, min(1.0, visc)), max(0, min(20, mass)),
                random.uniform(0, 15)
            ]
            features.append(vec)
        return np.array(features)

    def run_tsne_analysis(self, feature_matrix):
        n_samples = feature_matrix.shape[0]
        if n_samples < 5: return np.random.rand(n_samples, 2)
        if 'HAS_ML_LIBS' in globals() and HAS_ML_LIBS:
            try:
                tsne = TSNE(n_components=2, perplexity=min(5, n_samples - 1), init='random', learning_rate=200)
                X_embedded = tsne.fit_transform(feature_matrix)
                scaler = MinMaxScaler()
                return scaler.fit_transform(X_embedded)
            except:
                return np.random.rand(n_samples, 2)
        else:
            x = feature_matrix[:, 0] * 0.3 + feature_matrix[:, 1] * 0.4
            y = feature_matrix[:, 2] * 0.5 + feature_matrix[:, 3] * 0.3
            noise_level = 0.3
            x += np.random.normal(0, noise_level * (x.max() - x.min()), n_samples)
            y += np.random.normal(0, noise_level * (y.max() - y.min()), n_samples)
            x = (x - x.min()) / (x.max() - x.min() + 1e-9)
            y = (y - y.min()) / (y.max() - y.min() + 1e-9)
            return np.column_stack((x, y))

    def open_ml_channel(self):
        """打开机器学习通道模态框，加载模型并执行推理 (带详细控制台日志)"""
        dialog = MLChannelDialog(self)

        if dialog.exec():
            print("\n" + "=" * 60)
            print("🚀 [系统] 收到执行指令")

            selected_info = dialog.get_selected_pipeline()
            param_str = dialog.current_param_str
            print(f"👉 [配置] 选中算法: {selected_info}")
            print(f"👉 [配置] 参数详情: {param_str}")

            data_pack = dialog.get_batch_data_for_analysis()

            if data_pack is None:
                n_samples = 25
                print(f"⚠️ [数据] 未检测到 CSV 数据，将生成 {n_samples} 条【模拟】样本...")
                batch_data_list = [{'status_tag': random.choice(['Normal', 'Anomaly', 'Finished'])} for _ in
                                   range(n_samples)]
            else:
                raw_matrix, labels, batch_data_list = data_pack
                n_samples = len(batch_data_list)
                print(f"✅ [数据] 成功获取 {n_samples} 条【真实】特征数据")
                if n_samples > 0:
                    print(f"   -> 样本示例 (Feature[0]): {raw_matrix[0]}")

            self.lbl_archive_status.setText(f"🚀 正在执行 {selected_info}...")
            QApplication.processEvents()

            model_path = "reactor_fault_model.pkl"
            scaler_path = "reactor_scaler.pkl"
            predictions = []

            print(f"📂 [模型] 正在寻找模型文件: {model_path}")

            if 'HAS_ML_LIBS' in globals() and HAS_ML_LIBS and os.path.exists(model_path) and os.path.exists(
                    scaler_path) and data_pack is not None:
                try:
                    print("⚡ [模型] 正在加载 .pkl 文件...")
                    clf = joblib.load(model_path)
                    scaler = joblib.load(scaler_path)

                    print("⚡ [模型] 正在进行标准化预处理...")
                    X_input = scaler.transform(raw_matrix)

                    print("⚡ [模型] 正在执行推理 (Predict)...")
                    predictions = clf.predict(X_input)

                    print(f"✅ [模型] 推理完成! 预测结果分布: {np.unique(predictions, return_counts=True)}")
                    self.lbl_archive_status.setText(f"✅ 模型推理完成 | 算法: 随机森林")
                except Exception as e:
                    print(f"❌ [模型] 加载或推理失败: {e}")
                    predictions = labels
            else:
                if not HAS_ML_LIBS:
                    print("⚠️ [模型] 缺少 sklearn/pandas 库，无法加载模型。")
                elif not os.path.exists(model_path):
                    print("⚠️ [模型] 未找到 .pkl 文件，请先运行 train_model.py。")

                print("🔄 [模型] 已切换至【规则/模拟】判断逻辑")
                if data_pack is None:
                    predictions = [item['status_tag'] for item in batch_data_list]
                else:
                    predictions = labels

            if data_pack is not None:
                raw_features = raw_matrix
            else:
                print("🎲 [特征] 生成高维模拟特征矩阵...")
                raw_features = self.generate_process_features(n_samples)
                for i, item in enumerate(batch_data_list):
                    jitter = random.uniform(-10, 10)
                    if item['status_tag'] == 'Anomaly':
                        raw_features[i, 0] += (40 + jitter)
                        raw_features[i, 1] += (30 + jitter)
                    elif item['status_tag'] == 'Finished':
                        raw_features[i, 2] += (0.4 + jitter / 100.0)

            print("📉 [t-SNE] 开始执行降维算法 (5D -> 2D)...")
            points_2d = self.run_tsne_analysis(raw_features)
            print("✅ [t-SNE] 降维完成")

            print("🎨 [UI] 正在渲染散点图...")
            plot_points = []
            for i in range(n_samples):
                pred_tag = predictions[i] if len(predictions) > i else "Unknown"

                c_id = 0
                if pred_tag == 'Q_F' or pred_tag == 'Anomaly':
                    c_id = 1
                elif pred_tag == 'Finished':
                    c_id = 2
                elif pred_tag == 'Q_P' or pred_tag == 'Normal':
                    c_id = 0

                fx = points_2d[i, 0] + random.uniform(-0.02, 0.02)
                fy = points_2d[i, 1] + random.uniform(-0.02, 0.02)

                plot_points.append((fx, fy, c_id, f"Sample {i}\nStatus: {pred_tag}"))

            if 'HAS_ML_LIBS' not in globals() or not HAS_ML_LIBS:
                self.lbl_archive_status.setText(f"🚀 {selected_info}，特征降维完成 (模拟)")

            self.scatter_plot.setVisible(True)
            self.scatter_plot.set_info("聚类分析结果 (t-SNE)", param_str)
            self.scatter_plot.update_data_points(plot_points)
            print("✨ [系统] 任务全部结束")
            print("=" * 60 + "\n")

    def open_tag_dialog(self):
        ProcessTagDialog(self).exec()

    # 🔥 恢复了完整的 create_deviation_bar
    def create_deviation_bar(self, label_text):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(110)
        lbl.setStyleSheet("color: #000; font-size: 10px; border: none;")
        pbar = QProgressBar()
        pbar.setRange(0, 100)
        pbar.setValue(50)
        pbar.setTextVisible(False)
        pbar.setFixedHeight(10)
        pbar.setStyleSheet(
            "QProgressBar { border: 1px solid #999; background-color: #eee; border-radius: 2px; } QProgressBar::chunk { background-color: #2196F3; }")
        val_lbl = QLabel("+0.0%")
        val_lbl.setFixedWidth(40)
        val_lbl.setStyleSheet("color: #000; font-size: 10px; font-weight: bold; border: none;")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(lbl);
        layout.addWidget(pbar);
        layout.addWidget(val_lbl)
        if "Temp" in label_text:
            self.pbar_temp_ref = (pbar, val_lbl)
        else:
            self.pbar_press_ref = (pbar, val_lbl)
        return layout

    # 🔥 恢复了完整的 init_knowledge_graph
    def init_knowledge_graph(self):
        data = {
            "设备层": [("1#反应釜", "包含", "加热棒_H01"), ("1#反应釜", "包含", "搅拌电机_M01"),
                       ("搅拌电机_M01", "连接", "减速机_G02")],
            "故障层": [("温度过高", "属于", "热失控风险"), ("搅拌停转", "导致", "物料凝固"),
                       ("热失控", "触发", "紧急泄压阀")],
            "工艺层": [("配方A", "需要", "温度85度"), ("配方A", "需要", "PH值6.5")]
        }
        for cat, trips in data.items():
            root = QTreeWidgetItem(self.tree);
            root.setText(0, cat);
            root.setExpanded(True)
            for i in range(3): root.setForeground(i, Qt.GlobalColor.black); root.setBackground(i,
                                                                                               Qt.GlobalColor.lightGray)
            for s, p, o in trips:
                child = QTreeWidgetItem(root);
                child.setText(0, s);
                child.setText(1, p);
                child.setText(2, o)
                child.setForeground(0, Qt.GlobalColor.black);
                child.setForeground(1, Qt.GlobalColor.blue);
                child.setForeground(2, Qt.GlobalColor.black)

    # 🔥 恢复了完整的 refresh_rules (带颜色)
    def refresh_rules(self):
        self.rule_table.setRowCount(0)
        for t, c in self.rules:
            r = self.rule_table.rowCount();
            self.rule_table.insertRow(r)
            it_r = QTableWidgetItem(t);
            it_r.setForeground(Qt.GlobalColor.black);
            it_r.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it_c = QTableWidgetItem(f"{c:.2f}");
            it_c.setForeground(Qt.GlobalColor.red if c > 0.9 else Qt.GlobalColor.black)
            if c > 0.9: it_c.setFont(self.get_bold_font())
            self.rule_table.setItem(r, 0, it_r);
            self.rule_table.setItem(r, 1, it_c)

    def update_data(self):
        self.rules = [(r, min(1.0, max(0.0, c + random.uniform(-0.02, 0.02)))) for r, c in self.rules]
        self.refresh_rules()
        if hasattr(self, 'pbar_temp_ref'):
            dev = random.uniform(-5, 5)
            self.pbar_temp_ref[0].setValue(int(50 + dev * 3))
            self.pbar_temp_ref[1].setText(f"{dev:+.1f}%")
            col = "#4CAF50" if abs(dev) < 3 else "#F44336"
            self.pbar_temp_ref[0].setStyleSheet(f"QProgressBar::chunk {{ background-color: {col}; }}")
        if hasattr(self, 'pbar_press_ref'):
            dev = random.uniform(-2, 2)
            self.pbar_press_ref[0].setValue(int(50 + dev * 6))
            self.pbar_press_ref[1].setText(f"{dev:+.1f}%")

    def get_group_style(self):
        return "QGroupBox { background-color: #ffffff; border: 1px solid #ccc; border-radius: 4px; margin-top: 10px; font-weight: bold; color: #000000; } QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; color: #000000; }"

    def get_tree_style(self):
        return "QTreeWidget { border: none; color: black; } QHeaderView::section { background-color: #f5f5f5; border: none; border-bottom: 1px solid #ccc; height: 25px; color: black; font-weight: bold; } QTreeWidget::item { padding: 4px; color: black; }"

    def get_bold_font(self):
        f = self.font();
        f.setBold(True);
        return f


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = TwinDataPage()
    win.resize(1200, 800)
    win.show()
    sys.exit(app.exec())