# Database Migration Tool 🚀

选择语言：[English](README-EN.md) | [中文](README.md)

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

轻量级、可扩展的数据库迁移解决方案，支持MySQL/PostgreSQL/Sqlserver/Oracle

## 📌 目录

- [核心功能](#✨-核心功能)
- [系统要求](#⚙️-系统要求)
- [安装指南](#📦-安装指南)
- [快速入门](#🚀-快速入门)
- [配置详解](#⚙️-配置详解)
- [项目结构](#📂-项目结构)
- [开发指南](#👨💻-开发指南)
- [FAQ](#❓-faq)
- [贡献指南](#🤝-贡献指南)
- [许可证](#📄-许可证)

## ✨ 核心功能

- **多数据库支持**
  - MySQL
  - PostgreSQL
  - SqlServer
  - Oracle
- **迁移生命周期管理**
  - 自动生成迁移版本号
  - 原子性迁移操作
  - 版本回滚（Downgrade）支持
- **智能校验**
  - 迁移文件哈希校验
  - 冲突检测
  - 历史版本完整性检查
- **扩展接口**
  - 自定义迁移模板
  - 插件系统（开发中）
  - Webhook支持（开发中）

## ⚙️ 系统要求

- Python 3+
- 数据库驱动程序

## 📦 使用指南

```bash
# 克隆仓库
git clone https://github.com/yourusername/database-migration.git
cd database-migration

# 验证安装
python sync_table-2.0.py --version

# 更改配置文件
./config-v1.0.yaml

#运行
python sync_table-2.0.py
