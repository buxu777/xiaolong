# 小龙下载器 v4.0

**Claude Code / OpenClaw / Hermes 可用 — 说"下载"就加速**

> *XiaoLong Downloader — a downloadable skill for AI coding assistants (Claude Code, OpenClaw, Hermes). aria2c industrial engine + GitHub mirror acceleration + smart categorization. Peak 7.2 MiB/s. MIT licensed.*

> **关键词**：`AI Agent` `下载加速` `GitHub镜像` `aria2` `国内加速` `Gitee` `Skill` `多源下载` `断点续传` `大模型下载`

[![Version](https://img.shields.io/badge/version-4.0-blue)](https://github.com/buxu777/xiaolong)
[![Python](https://img.shields.io/badge/python-3.7+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)
[![Stars](https://img.shields.io/badge/dynamic/json?label=stars&query=%24.stargazers_count&url=https%3A%2F%2Fapi.github.com%2Frepos%2Fbuxu777%2Fxiaolong)](https://github.com/buxu777/xiaolong)
[![Lang](https://img.shields.io/badge/lang-中文%20%7C%20English-blue)](https://github.com/buxu777/xiaolong)

## 定位

在 **Claude Code、OpenClaw、Hermes** 等 AI 编程助手里，说句话就能用的下载 Skill。

当你的 AI 助手需要下载 GitHub 文件、模型权重、数据集、软件包时：

-   **没有小龙**：几十 KB/s，频繁超时，下载失败
-   **有了小龙**：自动选最优镜像，aria2c 16 路并发拉满带宽

不是桌面应用，不是浏览器插件 —— 是 **AI 的原生下载能力**。

## 为什么选小龙

| 对比 | Motrix | Xget | github_down | **小龙** |
|:---|:---|:---|:---|:---|
| 类型 | 桌面 GUI | 代理服务 | 批处理脚本 | **AI Agent Skill** |
| 下载引擎 | aria2 | Cloudflare | aria2c | **aria2c → curl → urllib 三级** |
| AI 触发 | 无 | 无 | 无 | **关键词自动激活** |
| 镜像选择 | 无 | 自建节点 | 手动配置 | **并发测速 + 健康检测** |
| 文件分类 | 无 | 无 | 无 | **8 类自动归档** |
| 安全校验 | 无 | 无 | 无 | **SHA256 + 病毒扫描** |

## 引擎架构

```
AI Agent 触发下载
        ↓
  镜像发现层（10+ 镜像源）
        ↓
  并发测速层（自动选最快 + 健康检测）
        ↓
  ┌─────────────────────────────────┐
  │  aria2c (C++)    16路多源聚合    │  ← 工业级主引擎
  │  curl (C)       直接 I/O 写入   │  ← 回退引擎
  │  urllib (Py)     兼容保底       │  ← 保底引擎
  └─────────────────────────────────┘
        ↓
  安全校验层（SHA256 + 病毒扫描）
        ↓
  智能归档层（Models/Datasets/Software/...）
```

## 快速开始

```bash
# 基本下载
python scripts/download_v3.py <URL>

# 大文件高速下载
python scripts/download_v3.py <URL> --workers 16

# 指定路径
python scripts/download_v3.py <URL> -o D:\downloads\

# 断点续传
python scripts/download_v3.py <URL> --resume

# 下载 + 解压 + 安全扫描
python scripts/download_v3.py <URL> --extract --scan
```

## 实测数据

| 文件 | 大小 | 耗时 | 平均速度 | 峰值 |
|:---|:---|:---|:---|:---|
| JDK 17 (GitHub) | 182 MB | 43s | 4.4 MiB/s | 7.2 MiB/s |
| Android SDK (Google) | 147 MB | 30s | 4.9 MiB/s | - |

> 注：速度瓶颈在 GitHub 镜像端带宽，非客户端。直连高速服务器时 aria2c 可跑满千兆。

## 环境要求

- Python 3.7+
- aria2c（可选，有则启用工业引擎）
- curl（可选，aria2c 不可用时回退）

## 版本历史

- **v4.0** （2026-05）: 集成 aria2c 工业引擎、镜像健康检测 + 自动黑名单、引擎三级回退
- **v3.3** （2026-05）: curl C 引擎、os.pwrite 直接 I/O、测速会话缓存
- **v3.2** （2026-05）: 多源并发聚合下载
- **v3.1** （2026-05）: 并发测速、1MB 大缓冲、超时优化

## License

MIT © 2026

---

**GitHub**：[github.com/buxu777/xiaolong](https://github.com/buxu777/xiaolong) · **Gitee**：[gitee.com/buxu777/xiaolong-downloader](https://gitee.com/buxu777/xiaolong-downloader)
