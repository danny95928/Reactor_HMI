# 工业深色主题
DARK_STYLE = """
QMainWindow {
    background-color: #2b2b2b;
}

/* 左侧导航栏样式 */
QListWidget {
    background-color: #1e1e1e;
    border: none;
    outline: none;
    font-size: 16px;
    font-weight: bold;
    color: #a0a0a0;
}
QListWidget::item {
    height: 60px;
    padding-left: 15px;
    border-bottom: 1px solid #333;
}
QListWidget::item:selected {
    background-color: #007ACC;
    color: white;
    border-left: 5px solid #00AFFF;
}
QListWidget::item:hover {
    background-color: #333;
}

/* 右侧内容区背景 */
QWidget#content_area {
    background-color: #2b2b2b;
}

/* 顶部状态栏 */
QLabel#header_title {
    font-size: 20px;
    font-weight: bold;
    color: #00AFFF;
    padding: 10px;
    background-color: #1e1e1e;
}
QLabel#status_bar {
    background-color: #333;
    color: #0f0;
    padding: 5px;
    font-family: Consolas;
}
"""