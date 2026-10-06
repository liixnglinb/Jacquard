# -*- coding: utf-8 -*-
"""集中管理路径：只读打包资源（static）与 可写数据目录（modex-data）。

源码运行（非 frozen）时数据落在项目根 modex-data/；
打包运行时落在安装根 data/，升级不丢数据。
"""
import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    INSTALL_ROOT = Path(sys.executable).parent.resolve()
    BASE = Path(getattr(sys, "_MEIPASS", INSTALL_ROOT))  # 打包只读资源
    DATA_DIR = INSTALL_ROOT / "data"
else:
    BASE = Path(__file__).resolve().parent.parent
    # FF_DATA_DIR：测试专用。E2E 要在一个临时沙箱里真增真删（建流程、删除、
    # 脏编辑器守卫），不能碰开发机的 modex-data。只认源码态；打包态不读它，
    # 装出去的软件永远用 data/。
    DATA_DIR = Path(os.environ["FF_DATA_DIR"]) if os.environ.get("FF_DATA_DIR") else BASE / "modex-data"

STATIC_DIR = BASE / "static"
DB_DIR = DATA_DIR
# 用户自建 skill 目录（软件内新建/编辑的 skill 落在这里，可写、升级不丢）
USER_SKILLS_DIR = DATA_DIR / "skills"
EXPORT_DIR = DATA_DIR / "export"
# 流程运行工作区：每次运行一个子目录 run-<id>/，产物文件（步骤 out）落在这里
WORKSPACES_DIR = DATA_DIR / "workspaces"

for _p in (USER_SKILLS_DIR, EXPORT_DIR, WORKSPACES_DIR):
    _p.mkdir(parents=True, exist_ok=True)
