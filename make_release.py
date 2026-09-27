# -*- coding: utf-8 -*-
"""Loom 织流 发布辅助：版本号 → PyInstaller onedir → Inno 安装包 → latest.json 清单。

产物：
  release/Loom-{v}-setup.exe   安装包（唯一分发形态）
  release/latest.json          软件内更新器与下载页共用的清单

用法：
  python make_icon.py                                   # 图标改过才需要
  python make_release.py --version 1.0.1 --notes "..."  # 全量
  python make_release.py --skip-build                   # 只按现有 setup 重建清单
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
REL = BASE / "release"
URL_BASE = "https://modelflow-1447874637.cos.ap-guangzhou.myqcloud.com"
APP = "Loom"


def find_iscc() -> Path:
    p = shutil.which("ISCC")
    if p:
        return Path(p)
    cands = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cands.append(Path(local) / "Programs" / "Inno Setup 6" / "ISCC.exe")
    for key in ("ProgramFiles(x86)", "ProgramFiles"):
        pf = os.environ.get(key)
        if pf:
            cands.append(Path(pf) / "Inno Setup 6" / "ISCC.exe")
    for c in cands:
        if c.exists():
            return c
    return Path("")


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_version() -> str:
    ns: dict = {}
    exec((BASE / "app" / "version.py").read_text(encoding="utf-8"), ns)
    return ns["APP_VERSION"]


def _rmtree_retry(path: Path, tries: int = 6):
    """删不干净就等一下再试：刚跑完 dist_app/Loom/Loom.exe 时，
    WebView2 的子进程还会捏着 DLL 句柄，WinError 32 是常事，不是错误。"""
    for i in range(tries):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(1.5)
    if path.exists():
        sys.exit(f"{path} 删不掉（有进程占用）。关掉正在运行的 Loom 后重试。")


def build_onedir() -> Path:
    _rmtree_retry(BASE / "dist_app")
    r = subprocess.run([sys.executable, "-m", "PyInstaller", "loom.spec",
                        "--noconfirm", "--distpath", "dist_app"], cwd=str(BASE))
    if r.returncode != 0:
        sys.exit("PyInstaller（onedir）失败")
    exe = BASE / "dist_app" / APP / f"{APP}.exe"
    if not exe.exists():
        sys.exit(f"找不到 {exe}")
    # 数据目录在冻结态是 exe 同级的 data/，构建目录里绝不能有 ——
    # 一旦带进去，安装包里就是开发机的数据库和运行产物。
    stray = exe.parent / "data"
    if stray.exists():
        sys.exit("dist_app/Loom/data 不应存在，会把本机数据打进安装包")
    return exe


def build_setup(version: str) -> Path:
    iscc = find_iscc()
    if not iscc:
        sys.exit("找不到 ISCC.exe（winget install JRSoftware.InnoSetup）")
    r = subprocess.run([str(iscc), f"/DMyAppVersion={version}", "installer.iss"], cwd=str(BASE))
    if r.returncode != 0:
        sys.exit("Inno Setup 编译失败")
    out = REL / f"{APP}-{version}-setup.exe"
    if not out.exists():
        sys.exit(f"未生成 {out.name}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="写回 app/version.py 并用于产物名")
    ap.add_argument("--notes", default="")
    ap.add_argument("--skip-build", action="store_true")
    a = ap.parse_args()

    if a.version:
        (BASE / "app" / "version.py").write_text(
            '# -*- coding: utf-8 -*-\n"""版本号（发版时手动修改）。"""\n'
            f'APP_VERSION = "{a.version}"\n', encoding="utf-8")
    ver = read_version()
    print(f"[release] version = {ver}")

    REL.mkdir(exist_ok=True)
    if a.skip_build:
        setup = REL / f"{APP}-{ver}-setup.exe"
        if not setup.exists():
            sys.exit(f"未找到 {setup.name}（--skip-build 需要已有产物）")
    else:
        build_onedir()
        setup = build_setup(ver)

    digest = sha256_of(setup)
    size = setup.stat().st_size
    print(f"[release] {setup.name}  {size/1048576:.1f} MB")
    print(f"[release]   sha256 = {digest}")

    manifest = {"version": ver, "url": f"{URL_BASE}/{setup.name}",
                "file": setup.name, "sha256": digest, "size": size,
                # 镜像列表先留空，由 publish_github.py 在把包发到 GitHub Releases
                # 之后回填；软件按实测速度在两个源里挑快的，但**装什么永远看 sha256**。
                "mirrors": [],
                "notes": a.notes or f"织流 Jacquard {ver}"}
    (REL / "latest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[release] latest.json -> {(REL/'latest.json').read_text(encoding='utf-8')}")

    setups = sorted(REL.glob(f"{APP}-*-setup.exe"),
                    key=lambda f: [int(x) for x in re.findall(r"\d+", f.stem.split("-setup")[0])])
    for old in setups[:-2]:
        old.unlink()
        print(f"[release] 清理本地旧包 {old.name}（只留最近两个）")

    print("\n下一步：python upload_cos.py   （上传 setup.exe + latest.json 到 COS 并设公有读）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
