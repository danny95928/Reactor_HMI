import sys
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow

if __name__ == "__main__":
    # 1. 创建应用对象
    app = QApplication(sys.argv)

    # 2. 实例化主窗口 (它会自动初始化里面的 Sidebar, Pages, ReactorCore)
    window = MainWindow()
    window.show()

    # 3. 进入事件循环
    sys.exit(app.exec())