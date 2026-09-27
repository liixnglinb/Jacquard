# -*- coding: utf-8 -*-
"""把这一版的安装包发到 GitHub Releases，然后回填 latest.json 的 mirrors。

**顺序**：make_release.py → publish_github.py → upload_cos.py。
这样只有 upload_cos 一个工具碰 COS，本脚本只跟 gh 和本地清单打交道。

为什么不在软件里"猜"GitHub 地址：猜的话"忘了发 Release"会变成一个静默的 404，
而不是一次显式的失败。清单里写了 mirrors 才代表那个源真的存在。
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REL = ROOT / "release"
REPO = "liixnglinb/Jacquard"


def mirror_url(ver: str, asset: str) -> str:
    return f"https://github.com/{REPO}/releases/download/v{ver}/{asset}"


def verify(url: str, size: int, timeout: int = 60) -> bool:
    """匿名 HEAD 回读：**先证明公网下得到，再把它写进清单**。
    Release 刚创建时 CDN 可能要几秒，所以重试几次。"""
    import time
    for _ in range(6):
        r = subprocess.run(["curl", "-sIL", "-m", str(timeout), url],
                           capture_output=True, text=True)
        head = r.stdout
        ok = "200" in head.split("\n")[0] or "\nHTTP/2 200" in head or "HTTP/1.1 200" in head
        if ok:
            cl = [ln for ln in head.splitlines() if ln.lower().startswith("content-length")]
            if cl and int(cl[-1].split(":")[1].strip()) == size:
                return True
        time.sleep(3)
    return False


def gh(args: list, **kw) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # 这两个环境变量会把凭据换成环境里那个（可能是另一个身份），先清掉走 gh 自己的登录态
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    return subprocess.run(["gh"] + args, capture_output=True, text=True, env=env, **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="不传就读 release/latest.json 里的 version")
    ap.add_argument("--skip-upload", action="store_true",
                    help="只回填 mirrors（Release 已经传过）")
    a = ap.parse_args()

    man_path = REL / "latest.json"
    if not man_path.is_file():
        sys.exit("找不到 release/latest.json，先跑 make_release.py")
    man = json.loads(man_path.read_text(encoding="utf-8"))
    ver = (a.version or man["version"]).lstrip("v")
    asset = man["file"]
    setup = REL / asset
    if not setup.is_file():
        sys.exit(f"找不到 {setup}，先跑 make_release.py")

    tag = f"v{ver}"
    if not a.skip_upload:
        notes_file = REL / f"notes-{ver}.txt"
        notes_file.write_text(man.get("notes") or f"织流 Jacquard {ver}", encoding="utf-8")
        exists = gh(["release", "view", tag, "--repo", REPO]).returncode == 0
        if exists:
            r = gh(["release", "upload", tag, str(setup), "--clobber", "--repo", REPO])
        else:
            r = gh(["release", "create", tag, str(setup), "--repo", REPO,
                    "--title", f"织流 Jacquard {ver}", "--notes-file", str(notes_file)])
        if r.returncode != 0:
            sys.exit(f"gh 失败：{(r.stderr or r.stdout).strip()[:400]}")
        print(f"[gh] {tag} 已上传 {asset}")

    url = mirror_url(ver, asset)
    if not verify(url, int(man["size"])):
        sys.exit(f"回读没通过，先别把镜像写进清单：{url}\n"
                 "（机器上 GitHub 时通时不通，重试几次；真不行就只留 COS 单源）")
    man["mirrors"] = [url]
    man_path.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[mirror] 已写入清单：{url}")
    print("下一步：python upload_cos.py（把带 mirrors 的清单推上去）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
