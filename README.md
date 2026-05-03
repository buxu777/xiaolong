# 🐉 小龙下载器 (XiaoLong Downloader) v4.0

**AI-Native 全能下载 Skill — aria2c 工业引擎 + 智能镜像加速**

[![Version](https://img.shields.io/badge/version-4.0-blue)](https://github.com)
[![Python](https://img.shields.io/badge/python-3.7+-green)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

## 是什么

一个专为 **AI Agent 工作流** 设计的下载工具。当 AI 助手需要下载文件时，自动触发，智能选择最优镜像，用工业级引擎高速下载。

不是桌面应用，不是浏览器插件 —— 是 **AI 的原生下载能力**。

## 为什么需要它

| 场景 | 没有小龙 | 有小龙 |
|------|---------|--------|
| AI 帮你下载 GitHub 文件 | 几十 KB/s，超时 | 4-7 MiB/s，稳定 |
| AI 下载模型/数据集 | 手动找镜像 | 自动测速选最优 |
| 文件下完后 | 不知道放哪 | 自动归类到 Models/Datasets/Software |
| 文件安全性 | 无校验 | SHA256 + 病毒扫描 |
| 下载中断 | 重新来 | 断点续传 |

## 引擎架构

```
下载请求 → 镜像发现(10+) → 并发测速 → 引擎选择
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
              aria2c (C++)         curl (C)            urllib (Py)
          16路多源聚合+自动容错    直接I/O无临时文件       兼容保底
```

## 快速开始

```bash
# 基本下载
python scripts/download_v3.py <URL>

# 指定输出路径
python scripts/download_v3.py <URL> -o /path/to/output

# 大文件高速下载
python scripts/download_v3.py <URL> --workers 16

# 断点续传
python scripts/download_v3.py <URL> --resume

# 下载+解压+扫描
python scripts/download_v3.py <URL> --extract --scan
```

## 核心特性

- **AI 触发**: 关键词自动激活（下载/download/模型下载/数据集下载...）
- **智能选源**: 并发测速 10+ 镜像，自动选最快（会话缓存 5 分钟）
- **多源聚合**: 不同分片走不同镜像，速度叠加
- **工业引擎**: aria2c (16连接) → curl (直接I/O) → urllib，三级回退
- **镜像健康**: 自动检测失效镜像并加入黑名单
- **智能分类**: Models / Datasets / Software / Videos / Archives 自动归类
- **安全校验**: SHA256 哈希 + Windows Defender 病毒扫描
- **断点续传**: 支持中断恢复
- **下载历史**: JSON 格式，最近 1000 条

## 速度实测

| 文件 | 大小 | 耗时 | 速度 | 引擎 |
|------|------|------|------|------|
| JDK 17 (GitHub) | 182 MB | 43s | 4.4 MiB/s | aria2c |
| JDK 17 (GitHub) | 182 MB | 44s | 4.2 MB/s | curl |
| Android SDK (Google) | 147 MB | 30s | 4.9 MB/s | curl |

## 环境要求

- Python 3.7+
- aria2c（可选，有则速度更快）
- curl（可选，有则速度更快）
- Windows / Linux / macOS

## 项目结构

```
xiaolong-downloader/
├── SKILL.md              # AI Skill 配置（触发词+功能描述）
├── scripts/
│   ├── download_v3.py    # 主程序（aria2c + curl + urllib）
│   └── download.py       # 兼容旧版
└── README.md
```

## 竞品对比

| | Motrix | Xget | flt6/github_down | **小龙** |
|------|--------|------|-----------------|---------|
| 类型 | 桌面GUI | 代理服务 | 脚本 | **AI Skill** |
| 下载引擎 | aria2 | Cloudflare | aria2c | **aria2c→curl→urllib 三级** |
| AI触发 | 无 | 无 | 无 | **关键词自动触发** |
| 镜像站 | 无 | 自建 | 70+ | **10+ 自检+黑名单** |
| 智能分类 | 无 | 无 | 无 | **8 类自动归类** |
| 安全扫描 | 无 | 无 | 无 | **SHA256 + 病毒** |

## 版本历史

- **v4.0** (2026-05): aria2c 工业引擎、镜像健康检测、aria2c 模式跳过测速、curl 回退引擎
- **v3.3** (2026-05): curl C引擎、os.pwrite 直接I/O、测速缓存
- **v3.2** (2026-05): 多源并发聚合（不同镜像叠加）
- **v3.1** (2026-05): 并发测速、1MB 大缓冲、超时优化
- **v3.0** (2026-04): 智能分类、SHA256、解压、病毒扫描

## License

MIT

---

> 小龙下载器 — 让 AI Agent 拥有工业级下载能力
