# core/api_client.py
import requests
import json
import time


class BackendClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url

    def upload_signal_state(self, device_code, signal_data, state_label):
        """
        上传信号数据和状态标签到 Go 后端，由后端写入 Milvus
        :param device_code: 设备编号
        :param signal_data: 字典，包含 temp, rpm, flow, aging_factor 等
        :param state_label: 字符串，当前状态 (e.g., "RUNNING", "IDLE", "FAULT")
        """
        url = f"{self.base_url}/api/upload_signal"
        payload = {
            "device_code": device_code,
            "timestamp": int(time.time()),
            "signal": signal_data,  # 原始信号
            "state": state_label  # 状态标签 (作为 Scalar Field 存入 Milvus)
        }

        try:
            # 设置较短超时，避免阻塞 UI
            resp = requests.post(url, json=payload, timeout=0.5)
            if resp.status_code != 200:
                print(f"[API] 上传失败: {resp.text}")
        except Exception as e:
            print(f"[API] 连接错误: {e}")