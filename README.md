# 1# 反应釜数字孪生智能监控系统 / 1# Reactor Digital Twin Intelligent Monitoring System

[![Language](https://img.shields.io/badge/Language-Python%203.x-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-PyQt6-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 📖 简介 / Introduction

本系统是一款针对工业配制反应釜开发的数字孪生监控系统（HMI）。系统基于 **Python** 与 **PyQt6** 框架，集成了 **Simulink** 仿真联调、状态追踪、**Neo4j** 知识图谱及智能运维决策功能，实现了物理生产过程与数字模型的深度双向映射。

This system is a Digital Twin monitoring HMI developed for industrial reactors. Built with Python and PyQt6, it integrates Simulink co-simulation, process tracking, Neo4j knowledge graphs, and intelligent maintenance decision-making, achieving deep mapping between physical processes and digital models.

---

## 🚀 核心功能模块 / Core Modules

### 1. 虚实映射控制 / Virtual-Real Mapping
* **功能**: 实现物理设备与 Simulink 仿真模型的双向数据同步，支持手动/自动控制模式切换与参数下发。
* **Description**: Enables bi-directional data synchronization between physical equipment and Simulink models, supporting manual/automatic control and parameter downloading.

### 2. 状态追踪监控 / State Tracking & OEE
* **功能**: 基于有限状态机 (FSM) 实时追踪反应釜运行工序，动态计算 OEE (设备全局效率) 指标。
* **Description**: Tracks reactor operation processes in real-time based on Finite State Machine (FSM) and dynamically calculates OEE metrics.

### 3. 孪生数据管理 / Twin Data & Knowledge Graph
* **功能**: 整合 3D 可视化与 **Neo4j 图数据库**，管理设备静态属性、历史数据及其逻辑关联。
* **Description**: Integrates 3D visualization and **Neo4j Graph Database** to manage static attributes, historical data, and logical relationships.

### 4. 运维决策支持 / Maintenance Decision Support
* **功能**: 实时监测网络延迟与系统健康度，利用预测模型提供预防性维护建议。
* **Description**: Monitors network latency and system health in real-time, providing preventive maintenance suggestions via predictive models.

---

## 🛠️ 技术栈 / Tech Stack

* **GUI Framework**: PyQt6 (Professional Business Style)
* **Language**: Python 3.10+
* **Simulation**: MATLAB / Simulink Engine (Co-simulation)
* **Database**: Neo4j (Graph Database for asset management)
* **Multi-threading**: QThread (Used for real-time latency detection & UI updates)

---

## 📂 目录结构 / Directory Structure

```text
Reactor_HMI/
├── main.py              # 系统主入口 / Main Entry
├── modules/             # 业务逻辑层 / Business Logic
│   └── reactor_core.py  # 核心控制算法 / Core Control Algorithms
├── ui/                  # 界面组件层 / UI Components
│   └── modules/         # 各功能子模块 / Functional Sub-modules
│       ├── page_virtual.py   # 虚实映射页面 / Virtual Mapping Page
│       ├── page_tracking.py  # 状态追踪页面 / Status Tracking Page
│       ├── page_twin.py      # 孪生数据页面 / Twin Data Page
│       └── page_decision.py  # 决策支持页面 / Decision Support Page
└── README.md            # 项目文档 / Project Documentation
