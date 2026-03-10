# 1# 反应釜数字孪生智能监控系统 / 1# Reactor Digital Twin Intelligent Monitoring System

[![Language](https://img.shields.io/badge/Language-Python%203.10+-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Framework-PyQt6-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey.svg)](https://github.com/danny95928/Reactor_HMI)

## 📖 简介 / Introduction

本系统是一款针对工业配制反应釜开发的数字孪生监控系统（HMI）。系统基于 **Python** 与 **PyQt6** 框架，集成了 **Simulink** 仿真联调、状态追踪、**Neo4j** 知识图谱及智能运维决策功能，实现了物理生产过程与数字模型的深度双向映射。

This system is a Digital Twin monitoring HMI developed for industrial reactors. Built with Python and PyQt6, it integrates Simulink co-simulation, process tracking, Neo4j knowledge graphs, and intelligent maintenance decision-making.

---

## 🚀 核心功能模块 / Core Modules

* **虚实映射控制 / Virtual-Real Mapping**: 实现物理设备与 Simulink 仿真模型的双向数据同步。
* **状态追踪监控 / State Tracking**: 基于 FSM（有限状态机）实时追踪工序并计算 OEE 指标。
* **孪生数据管理 / Twin Data**: 整合 3D 可视化与 **Neo4j 图数据库** 管理资产逻辑。
* **运维决策支持 / Decision Support**: 实时监测网络延迟，利用预测模型提供维护建议。

---

## 📂 目录结构 / Directory Structure

为了确保程序正常运行并能正确找到模块，请保持以下文件布局：

```text
Reactor_HMI/
├── main.py              # 系统主入口 (Main Entry)
├── modules/             # 业务逻辑核心包 (Core Logic)
│   └── reactor_core.py  # 反应釜核心算法逻辑
├── ui/                  # UI 资源与界面包
│   └── modules/         # 各功能子模块页面
│       ├── page_virtual.py   # 虚实映射控制页
│       ├── page_tracking.py  # 状态追踪监控页
│       ├── page_twin.py      # 孪生数据管理页 (3D & 知识图谱)
│       └── page_decision.py  # 运维决策支持页
└── README.md            # 项目说明文档 (Project Documentation)

