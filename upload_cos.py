# -*- coding: utf-8 -*-
"""把 release/ 的安装包与 latest.json 传到腾讯云 COS，并设成公有读。

密钥不复制进本仓库：默认读同级开发目录里那份 cos_secrets.json，
也可以用环境变量 LOOM_COS_SECRETS 指定路径，或在仓库根放一个
同名文件（.gitignore 已拦）。

桶本身仍是私有桶，只有这两个对象开公有读：
  Loom-{v}-setup.exe   下载页直链 + 软件内更新器
  latest.json          版本清单（更新器与页面都读它）
旧版本保留最近两个，和 make_release.py 的本地策略一致。
"""
import hashlib
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
REL = BASE / "release"
CANDIDATES = [
    os.environ.get("LOOM_COS_SECRETS"),
    str(BASE / "cos_secrets.json"),
]
# 原先这里还硬编码了一个本机绝对路径（C:/Users/<用户名>/.../cos_secrets.json）。
# 本仓库是公开仓库，该路径会泄露本机 Windows 用户名与目录结构，已移除。
# 需要指定其它位置时请用环境变量 LOOM_COS_SECRETS，不要把个人路径写回源码。


def load_secrets() -> dict:
    for p in CANDIDATES:
        if p and Path(p).is_file():
            s = json.loads(Path(p).read_text(encoding="utf-8"))
            if s.get("secret_id") and s.get("secret_key"):
                print(f"[cos] 使用密钥文件 {p}")
                return s
    sys.exit("找不到 COS 密钥（设 LOOM_COS_SECRETS 或放一份 cos_secrets.json）")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def consistency_errors(manifest: dict, actual_sha: str, actual_size: int,
                       base_url: str) -> list:
    """发布前的自检：清单里那几个字段必须和**真正要传的那个文件**对得上。

    为什么必须在这儿算一遍而不是信 make_release.py：清单是磁盘上一份能手改的
    JSON，而更新器现在对着它做安全判定（sha256 不对就不装、file 与 url 对不上
    就不下）。传上去一份 sha256 与真身不符的清单，等于把所有人卡在"检查更新
    通过、点安装就报错"，而且只有已经装过的人才会遇到，本地测不出来。
    """
    errs = []
    f = str(manifest.get("file") or "")
    v = str(manifest.get("version") or "")
    url = str(manifest.get("url") or "")
    if not f or Path(f).name != f:
        errs.append(f"file 必须是个纯文件名，现在是 {f!r}")
    if not v:
        errs.append("清单里没有 version")
    elif f and f != f"Loom-{v}-setup.exe":
        errs.append(f"file={f!r} 和 version={v!r} 对不上（应为 Loom-{v}-setup.exe）")
    if not url.startswith("https://"):
        errs.append(f"url 必须是 https，现在是 {url!r}")
    elif f and not url.endswith("/" + f):
        errs.append(f"url 指向的不是 file 那个包：{url!r} vs {f!r}")
    elif base_url and not url.startswith(base_url + "/"):
        errs.append(f"url 不在我们要传的桶上：{url!r} 不是 {base_url}/… —— "
                    f"传完清单就会把用户指向另一台机器")
    got = str(manifest.get("sha256") or "").lower()
    if got != actual_sha:
        errs.append(f"sha256 与真身不符：清单 {got[:12]}… 实算 {actual_sha[:12]}…")
    try:
        size = int(manifest.get("size") or 0)
    except (TypeError, ValueError):
        size = -1
    if size != actual_size:
        errs.append(f"size 与真身不符：清单 {size} 实算 {actual_size}")
    if not str(manifest.get("notes") or "").strip():
        errs.append("notes 是空的：更新浮层里那段说明会一片空白")
    return errs


def main() -> int:
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError:
        sys.exit("缺少 qcloud_cos SDK：pip install qcloud_cos")

    s = load_secrets()
    bucket = s.get("bucket") or "modelflow-1447874637"
    region = s.get("region") or "ap-guangzhou"
    base = f"https://{bucket}.cos.{region}.myqcloud.com"
    client = CosS3Client(CosConfig(Region=region, SecretId=s["secret_id"],
                                   SecretKey=s["secret_key"]))

    manifest = json.loads((REL / "latest.json").read_text(encoding="utf-8"))
    exe = REL / manifest["file"]
    if not exe.is_file():
        sys.exit(f"缺少 {exe.name}，先跑 make_release.py")
    actual_sha, actual_size = sha256_of(exe), exe.stat().st_size
    errs = consistency_errors(manifest, actual_sha, actual_size, base)
    if errs:
        for e in errs:
            print(f"[cos] ✗ {e}")
        sys.exit("清单与真包对不上，已经停在这里 —— 一个字节都没往上传。")

    print(f"↑ {manifest['file']} ({actual_size/1048576:.1f} MB) "
          f"sha256={actual_sha[:12]}…")
    client.upload_file(Bucket=bucket, Key=manifest["file"], LocalFilePath=str(exe),
                       ACL="public-read")
    body = json.dumps(manifest, ensure_ascii=False)
    client.put_object(Bucket=bucket, Key="latest.json", Body=body.encode("utf-8"),
                      ACL="public-read", ContentType="application/json")
    print(f"↑ latest.json  version={manifest['version']}")

    # 匿名回读：签名请求成功不代表公网能下，这一步才是用户看到的真相。
    # 顺带确认跨域头 —— COS 默认就回 Access-Control-Allow-Origin: *，
    # 下载页的 fetch 能读到；真哪天变成空了，这里会先发现。
    import requests
    bad = []
    got = requests.get(f"{base}/latest.json", timeout=20,
                       headers={"Origin": "https://lxlrwxs.top"})
    got.raise_for_status()
    back = got.json()
    print("[cos] 匿名读 latest.json ->", back.get("version"),
          "| 跨域头:", got.headers.get("access-control-allow-origin") or "缺失（下载页读不到版本号）")
    if str(back.get("version")) != str(manifest.get("version")):
        bad.append(f"公网读回的版本是 {back.get('version')!r}，我们传的是 "
                   f"{manifest.get('version')!r} —— CDN 还在发旧的，或传错了桶")
    if str(back.get("sha256") or "").lower() != actual_sha:
        bad.append("公网那份清单的 sha256 与本地实算不符")
    head = requests.head(manifest["url"], timeout=20)
    mb = int(head.headers.get("content-length") or 0) / 1048576
    print(f"[cos] 匿名 HEAD 安装包 -> HTTP {head.status_code} {mb:.1f} MB")
    if head.status_code != 200:
        bad.append(f"安装包公网 HEAD 返回 {head.status_code}，用户点了下载就是 404")
    elif abs(int(head.headers.get("content-length") or 0) - actual_size) > 1024:
        bad.append(f"公网那个包的大小是 {head.headers.get('content-length')}，"
                   f"本地是 {actual_size} —— 上传被截断了")

    if bad:
        for e in bad:
            print(f"[cos] ✗ {e}")
        return 1
    print("[cos] 全部核对通过")
    return 0

    # 桶刚被清空过（2026-09-15 实测 0 对象），这里只列清单不自动删任何东西：
    # 攒够两个版本后再谈保留策略，删线上包必须是显式动作。
    listed = client.list_objects(Bucket=bucket, Prefix="Loom-", MaxKeys=200).get("Contents", [])
    print(f"[cos] 桶内 Loom 安装包 {len(listed)} 个：")
    for o in listed:
        print(f"      {o['Key']}  {int(o['Size'])/1048576:.1f} MB")
    print(f"\n下载直链：{manifest['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
