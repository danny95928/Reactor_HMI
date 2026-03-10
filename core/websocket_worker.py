# core/websocket_worker.py

from PyQt6.QtCore import QThread, pyqtSignal
import websocket
import json
import time


class RealtimeDataWorker(QThread):
    """
    WebSocket 工作线程
    负责：
    1. 连接 Go 后端 (ws://127.0.0.1:8080/ws)
    2. 接收实时 JSON 数据
    3. 断线自动重连
    """
    # 信号定义：数据(字典), 连接状态(布尔, 消息)
    data_received = pyqtSignal(dict)
    connection_status = pyqtSignal(bool, str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.running = True
        self.ws = None

    def run(self):
        """线程主循环"""
        while self.running:
            try:
                self.connection_status.emit(False, "正在连接...")
                # 建立连接
                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )

                # 阻塞运行，直到连接断开
                # ping_interval=30: 每30秒发送心跳，防止防火墙切断连接
                self.ws.run_forever(ping_interval=30, ping_timeout=10)

                # 如果 run_forever 退出且线程未停止，说明意外断开，触发重连
                if self.running:
                    self.connection_status.emit(False, "连接断开，3秒后重试...")
                    time.sleep(3)

            except Exception as e:
                if self.running:
                    print(f"WebSocket 异常: {e}")
                    self.connection_status.emit(False, f"连接错误: {e}")
                    time.sleep(3)

    def on_open(self, ws):
        self.connection_status.emit(True, "已连接")
        print(f"✅ WebSocket 已连接到 {self.url}")

    def on_message(self, ws, message):
        try:
            # 解析 JSON 数据并通过信号发送给 UI
            data = json.loads(message)
            self.data_received.emit(data)
        except json.JSONDecodeError:
            print(f"⚠️ 收到非 JSON 数据: {message[:50]}...")
        except Exception as e:
            print(f"⚠️ 数据处理错误: {e}")

    def on_error(self, ws, error):
        print(f"❌ WebSocket 错误: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"🔌 WebSocket 连接关闭: {close_status_code} - {close_msg}")

    def stop(self):
        """安全停止线程"""
        self.running = False
        if self.ws:
            self.ws.close()
        self.quit()
        self.wait()