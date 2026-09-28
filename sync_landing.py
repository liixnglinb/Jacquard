# -*- coding: utf-8 -*-
"""同步下载页里写死的兜底版本号与体积。

用法：python sync_landing.py <旧版本> <新版本> [新体积MB]
不带第三个参数就不动体积（两版体积常常一样）。

为什么不再是几个 str.replace：页里带版本号的位置会随产品图长出来（2026-09-26 加了
居中更新浮层之后，"预期 6 处"当场变成 8 处），而**漏一处不会报错** —— 它只会在
fetch 失败时给用户看一个说谎的兜底值。所以现在按名字列出每一处，逐处断言命中一次，
再把"没被任何已知位置解释掉"的残留单独挑出来：只允许它是注释里的历史说明，
多一处就直接失败，逼着加位置的人回来登记。
"""
import pathlib
import re
import sys

# 每一处会显示给用户看的版本号，一条一个正则（{V} 处填旧版本号）。
# class 一律不写死：页里这几枚 span 的 class 有两种（ver / en），按 id 认才认得住。
# 2026-09-28 下载页首屏撤掉了那张"已下载好"的更新浮层，于是少一处显示位、
# 也没有"浮层里那行当前版本"了 —— 这里同步收窄，别留一条永远命中不到的正则。
SPOTS = {
    "下载直链文件名": r"Loom-{V}-setup\.exe",
    "导航条版本": r'<span class="[^"]*" id="navVer">{V}</span>',
    "hero 大标题版本": r'<span class="[^"]*" id="heroVer">{V}</span>',
    "下载按钮版本": r'<span class="[^"]*" id="btnVer">{V}</span>',
    "页脚版本": r'<span class="[^"]*" id="ftVer">{V}</span>',
    "侧栏更新胶囊": r"更新至 {V}",
}


def _in_css_comment(text, pos):
    """pos 落在 /* … */ 之间才算注释。往后找不到闭合的 */ 就是注释外 ——
    第一版这里写成 `close == -1 or close > open_`，等于"注释开始之后的一切都是注释"，
    于是页尾新加一处显示位会被静默放过，残留检查当场失效。"""
    open_ = text.rfind("/*", 0, pos)
    close = text.find("*/", pos)
    return open_ != -1 and close != -1 and close > open_


def sync_versions(text, old_v, new_v):
    """把每一处显示位换成 new_v。命中数不对、或者页里出现了没登记过的版本号位置
    —— 直接抛，不静默改一半。"""
    ev = re.escape(old_v)
    hits = {}
    explained = set()
    for name, pat in SPOTS.items():
        found = list(re.finditer(pat.replace("{V}", ev), text))
        assert len(found) == 1, f"{name}：预期命中 1 处 {old_v}，实际 {len(found)}"
        hits[name] = found[0]
        # 解释的是**版本号本身**那几个字符的位置，不是整段匹配的起点：
        # 残留检查拿 re.finditer(版本号) 的位置来比，记起点会处处对不上。
        explained.add(found[0].start() + found[0].group(0).index(old_v))

    # 没被解释掉的旧版本号：只允许是注释里的历史说明
    stray = [m for m in re.finditer(ev, text) if m.start() not in explained]
    for m in stray:
        assert _in_css_comment(text, m.start()), (
            f"页里第 {m.start()} 处 {old_v} 不属于任何已登记的显示位，"
            f"也不在注释里 —— 给它加一条 SPOTS 再跑")

    for name, m in hits.items():
        text = text[:m.start()] + m.group(0).replace(old_v, new_v) + text[m.end():]

    assert len(re.findall(re.escape(new_v), text)) == len(SPOTS), "新版本号数量不对"
    return text



def sync_size(text, size_mb):
    """只认这三处安装包体积。页里还有"2.4 MB"（mock 日志与产物文件名）和
    "约 200 MB 磁盘"（另一件事），按"约 N MB"这种宽匹配会把它们一起改掉。"""
    anchors = ['id="heroSize">{V} MB<', 'id="btnSize">{V} MB<', "安装包约 {V} MB，"]
    cur = None
    for a in anchors:
        pat = a.replace("{V}", r"([\d.]+)")
        found = re.findall(pat, text)
        assert len(found) == 1, f"体积锚点没命中或命中多处：{a} -> {found}"
        cur = cur or found[0]
        text = re.sub(pat, a.replace("{V}", size_mb), text)
    return text, cur


def main() -> int:
    old_v, new_v = sys.argv[1], sys.argv[2]
    size_mb = sys.argv[3] if len(sys.argv) > 3 else None
    p = pathlib.Path(r"D:\Voyra 个人网站\public\modelflow\index.html")
    s = p.read_text(encoding="utf-8")
    s = sync_versions(s, old_v, new_v)
    print(f"{len(SPOTS)} 处版本号 {old_v} -> {new_v}")
    if size_mb:
        s, cur = sync_size(s, size_mb)
        print(f"体积 {cur} MB -> {size_mb} MB" if cur != size_mb else f"体积仍是 {cur} MB")
    p.write_text(s, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
