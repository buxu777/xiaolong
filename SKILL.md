---
name: xiaolong-downloader
version: "4.0"
description: |
  小龙下载助手 v4.0 - AI 工作流全能下载工具。
  aria2c C++ 工业级多源聚合引擎 + curl 回退 + 直接 I/O，多源并发聚合、多线程分片、
  断点续传、智能文件分类、SHA256 校验、自动解压、病毒扫描、下载历史。
  v4.0: 集成 aria2c 工业级引擎(16连接多源聚合+自动故障切换+TCP优化)。
  当用户需要下载文件、模型、数据集、软件、视频或批量下载任务时使用此 skill。
triggers:
  - 下载
  - download
  - 下载文件
  - 批量下载
  - GitHub 下载
  - 模型下载
  - 数据集下载
  - 断点续传
  - 多线程下载
---

# 小龙下载助手 v4.0

AI 工作流全能下载工具，aria2c 工业级引擎 + 智能镜像发现。

## 功能特性

- **aria2c 工业级引擎**: C++ 实现，16 路多源聚合 + 自动故障切换 + TCP 优化（v4.0）
- **curl 回退引擎**: aria2c 不可用时自动回退 curl 引擎（v4.0）
- **直接文件 I/O**: 无临时文件，无需合并步骤（v3.3）
- **测速缓存**: 同一 host 5 分钟内复用测速结果（v3.3）
- **多源并发聚合下载**: 不同分片走不同镜像，总速度叠加（v3.2）
- **并发镜像测速**: 并发测试所有镜像，按速度排名（v3.1）
- **多平台镜像加速**: GitHub (10个镜像)、HuggingFace (2个镜像)
- **智能文件分类**: 自动按类型归类到 Models/Datasets/Software/Videos 等目录
- **多线程分片下载**: 大文件自动分片，并发下载（默认 12 线程，最大 32）
- **断点续传**: 支持中断后继续下载，自动检测已下载部分
- **哈希校验**: 自动计算 SHA256，支持验证文件完整性
- **自动解压**: 下载压缩包后自动解压（zip/tar/7z）
- **病毒扫描**: 集成 Windows Defender 扫描
- **下载历史**: JSON 格式记录，保留最近 1000 条
- **批量下载**: 支持多个 URL 或从文件读取
- **SSL 绕过**: 自动处理证书问题

## 安装方法

### 方法 1：复制 skill 目录

1. 复制 `xiaolong-downloader` 文件夹到目标 OpenClaw 的 skills 目录：
   ```
   {openclaw_config_dir}\skills\
   ```

2. 重启 OpenClaw Gateway 或重新加载 skills

### 方法 2：使用打包文件

1. 复制 `xiaolong-downloader.skill` 文件到目标机器
2. 解压到 skills 目录即可使用

## 使用方法

### 基本下载

```bash
python scripts/download_v3.py <URL>
python scripts/download_v3.py <URL> -o <输出路径>
```

### 多线程下载大文件

```bash
python scripts/download_v3.py <URL> --workers 16
```

### 断点续传

```bash
python scripts/download_v3.py <URL> --resume
```

### 批量下载

```bash
# 从文件读取 URL 列表
python scripts/download_v3.py -f urls.txt

# 命令行指定多个 URL
python scripts/download_v3.py <URL1> <URL2> <URL3>
```

### 下载并自动处理

```bash
# 下载并解压
python scripts/download_v3.py <URL> --extract

# 下载并扫描病毒
python scripts/download_v3.py <URL> --scan

# 下载软件并安装
python scripts/download_v3.py <URL> --install
```

### PowerShell 快捷方式

```powershell
# 使用 dl.ps1 快捷脚本
.\dl.ps1 <URL> [输出路径]
```

## 命令行参数

```
usage: download_v3.py [-h] [-o OUTPUT] [-f FILE] [--no-multi-thread]
                      [--workers WORKERS] [--timeout TIMEOUT] [--resume]
                      [--no-categorize] [--extract] [--install] [--scan]
                      [urls ...]

positional arguments:
  urls                  下载链接

options:
  -h, --help            显示帮助
  -o, --output OUTPUT   输出路径或目录
  -f, --file FILE       从文件读取 URL 列表
  --no-multi-thread     禁用多线程
  --workers WORKERS     线程数（默认 8，最大 32）
  --timeout TIMEOUT     超时秒数（默认 30）
  --resume              启用断点续传
  --no-categorize       禁用智能分类
  --extract             下载后解压（仅压缩包）
  --install             下载后安装（仅软件包）
  --scan                下载后病毒扫描
```

## 智能分类目录

下载的文件会自动分类到以下目录：

| 分类 | 目录 | 文件类型 |
|------|------|---------|
| model | ~/Downloads/Models | .pt, .pth, .safetensors, .gguf, .onnx |
| dataset | ~/Downloads/Datasets | .jsonl, .parquet, .csv, .npz |
| video | ~/Downloads/Videos | .mp4, .mkv, .avi, .mov |
| audio | ~/Downloads/Audio | .mp3, .wav, .flac, .aac |
| document | ~/Downloads/Documents | .pdf, .doc, .xls, .ppt, .md |
| image | ~/Downloads/Images | .jpg, .png, .gif, .webp |
| archive | ~/Downloads/Archives | .zip, .tar, .7z, .rar |
| software | ~/Downloads/Software | .exe, .msi, .dmg, .deb |
| github | ~/Downloads/GitHub | GitHub 链接 |
| default | ~/Downloads | 其他 |

## 下载策略

| 文件大小 | 支持断点续传 | 模式 | 说明 |
|---------|------------|------|------|
| < 30MB | - | 单线程 + 镜像切换 | 快速切换镜像源 |
| >= 30MB | 是 | 多线程分片 | 20MB/片，并发下载 |
| >= 30MB | 否 | 单线程 | 回退到单线程 |

## 镜像源列表

### GitHub 镜像（10个）
1. ghfast.top
2. gh-proxy.com
3. mirror.ghproxy.com
4. gh.idayer.com
5. ghproxy.net
6. gh.ddlc.top
7. gh.con.sh
8. gh.api.99988866.xyz
9. ghps.cc
10. github.moeyy.xyz

### HuggingFace 镜像（2个）
1. huggingface.co (官方)
2. hf-mirror.com

## 文件结构

```
xiaolong-downloader/
├── SKILL.md              # 本文件
├── scripts/
│   ├── download_v3.py    # 主程序 v3.0
│   ├── download.py       # 旧版本兼容
│   └── dl.ps1           # PowerShell 快捷脚本
```

## 环境要求

- Python 3.6+
- Windows/Linux/macOS
- 无需额外依赖（仅使用标准库）

## 下载历史

下载记录保存在：
```
~/.qclaw/download_history.json
```

格式：
```json
[
  {
    "url": "https://...",
    "path": "C:/Users/.../Downloads/...",
    "size": 12345678,
    "sha256": "abc123...",
    "category": "model",
    "timestamp": "2026-04-28T01:23:45",
    "elapsed": 12.34
  }
]
```

## 版本历史

- v4.0 (2026-05-03): 集成aria2c C++工业级引擎(16连接多源聚合+自动故障切换+动态负载均衡)、curl回退引擎、aria2c模式跳过测速(省10-15s)、镜像黑名单+健康检测、镜像列表精简优化
- v3.3 (2026-05-03): curl 原生C引擎替代Python urllib、os.pwrite直接I/O消灭临时文件合并步骤、测速会话缓存
- v3.2 (2026-05-03): 多源并发聚合下载(不同分片走不同镜像，总速度=各镜像速度之和)、镜像速度排名系统
- v3.1 (2026-05-03): 并发镜像测速自动选最快节点、1MB大缓冲区、超时优化(30s→10s)、线程提升(8→12)、分片提升(10MB→20MB)、更新镜像列表
- v3.0 (2026-04-28): 新增智能分类、哈希校验、自动解压、病毒扫描、下载历史
- v2.0 (2026-04-27): 新增多线程分片、断点续传、批量下载
- v1.0 (2026-04-27): 初始版本，GitHub 镜像加速
