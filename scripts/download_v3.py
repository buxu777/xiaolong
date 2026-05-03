#!/usr/bin/env python3
"""
小龙下载助手 v4.0 - AI 工作流全能下载工具
引擎: aria2c (C++工业级) > curl (C原生) > urllib (回退)
支持：GitHub/HF/ModelScope加速、多源并发聚合、多线程、断点续传、
      智能分类、SHA256校验、自动解压、病毒扫描、下载历史
"""

import urllib.request
import urllib.parse
import urllib.error
import ssl
import os
import sys
import time
import threading
import hashlib
import json
import re
import subprocess
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

# ============ 配置区 ============

# GitHub 专用镜像（releases/raw 等）— 自动维护，失效的移至 BLACKLIST
GITHUB_MIRRORS = [
    "https://ghfast.top/",
    "https://gh-proxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.idayer.com/",
    "https://ghproxy.net/",
    "https://gh.ddlc.top/",
    "https://gh.api.99988866.xyz/",
    "https://github.moeyy.xyz/",
    "https://gh.llkk.cc/",
    "https://ghp.ci/",
]

# 已知失效镜像（自动或手动标记）
MIRROR_BLACKLIST = {
    "gh.con.sh",      # 2026-05-03: 被封禁，返回 suspent.txt
    "ghps.cc",        # 2026-05-03: Range 请求返回错误 Content-Length
    "ghproxy.com",    # 原 ghproxy.com 已废弃，用 mirror.ghproxy.com
}

# HuggingFace 镜像
HF_MIRRORS = [
    "https://huggingface.co/",
    "https://hf-mirror.com/",
    "https://huggingface.co.cn/",
]

# ModelScope 镜像
MS_MIRRORS = [
    "https://modelscope.cn/",
    "https://www.modelscope.cn/",
]

# pip 镜像源
PIP_MIRRORS = [
    "https://pypi.org/simple/",
    "https://mirrors.aliyun.com/pypi/simple/",
    "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "https://mirrors.cloud.tencent.com/pypi/simple/",
]

# npm 镜像源
NPM_MIRRORS = [
    "https://registry.npmjs.org/",
    "https://registry.npmmirror.com/",
    "https://registry.npmmirror.com/",
]

# 配置参数
CHUNK_THRESHOLD = 30 * 1024 * 1024   # 30MB 启用多线程
CHUNK_SIZE = 20 * 1024 * 1024        # 20MB 分片
DEFAULT_WORKERS = 12
MAX_WORKERS = 32
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 60
MAX_RETRIES = 2
RETRY_DELAY = 1
BUFFER_SIZE = 1024 * 1024            # 1MB 缓冲区（原 64KB）
SPEED_TEST_SIZE = 256 * 1024          # 测速下载 256KB（太小不准确，TCP 慢启动需要暖机）
SPEED_CACHE = {}                      # 会话级镜像速度缓存

# aria2c 路径（自动探测）
def _find_aria2c():
    """查找 aria2c 可执行文件"""
    # 常见路径
    candidates = [
        '/c/Users/Administrator/android/aria2c.exe',
        os.path.expanduser('~/android/aria2c.exe'),
    ]
    # 也在 PATH 中找
    for d in os.environ.get('PATH', '').split(os.pathsep):
        p = os.path.join(d, 'aria2c.exe')
        if os.path.exists(p):
            candidates.insert(0, p)
            break
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

ARIA2C_PATH = _find_aria2c()

# 下载目录配置
DOWNLOAD_DIRS = {
    'default': os.path.expanduser('~/Downloads'),
    'github': os.path.expanduser('~/Downloads/GitHub'),
    'model': os.path.expanduser('~/Downloads/Models'),
    'dataset': os.path.expanduser('~/Downloads/Datasets'),
    'video': os.path.expanduser('~/Downloads/Videos'),
    'audio': os.path.expanduser('~/Downloads/Audio'),
    'document': os.path.expanduser('~/Downloads/Documents'),
    'software': os.path.expanduser('~/Downloads/Software'),
    'image': os.path.expanduser('~/Downloads/Images'),
    'archive': os.path.expanduser('~/Downloads/Archives'),
}

# SSL 上下文
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# ============ 工具函数 ============

def format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while size_bytes >= 1024 and idx < len(units) - 1:
        size_bytes /= 1024
        idx += 1
    return f"{size_bytes:.1f} {units[idx]}"


def format_time(seconds):
    """格式化时间"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.0f}m{seconds%60:.0f}s"
    else:
        return f"{seconds/3600:.0f}h{(seconds%3600)/60:.0f}m"


def safe_print(msg):
    """安全输出（兼容 Windows GBK）"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            print(msg.encode('gbk', errors='ignore').decode('gbk'), flush=True)
        except:
            print(msg.encode('ascii', errors='ignore').decode('ascii'), flush=True)


def calculate_hash(filepath, algorithm='sha256', chunk_size=8192):
    """计算文件哈希值"""
    hasher = hashlib.new(algorithm)
    with open(filepath, 'rb') as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_hash(filepath, expected_hash, algorithm='sha256'):
    """验证文件哈希"""
    if not os.path.exists(filepath):
        return False, "File not found"
    actual = calculate_hash(filepath, algorithm)
    expected = expected_hash.lower().strip()
    return actual == expected, f"Expected: {expected}\nActual:   {actual}"


class ProgressBar:
    """进度条"""
    def __init__(self, total, desc="Download"):
        self.total = total
        self.desc = desc[:20]
        self.downloaded = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
        self.last_print = 0
        self.done = False
    
    def update(self, n):
        with self.lock:
            self.downloaded += n
            now = time.time()
            if now - self.last_print < 0.5 and self.downloaded < self.total:
                return
            self.last_print = now
            
            if self.total > 0:
                percent = min(self.downloaded / self.total * 100, 100)
                elapsed = now - self.start_time
                speed = self.downloaded / (elapsed + 0.001)
                eta = (self.total - self.downloaded) / speed if speed > 0 else 0
                
                bar_len = 25
                filled = int(bar_len * min(self.downloaded / self.total, 1))
                bar = "=" * filled + ">" + " " * (bar_len - filled - 1)
                if filled == bar_len:
                    bar = "=" * bar_len
                
                safe_print(f"\r{self.desc} [{bar}] {percent:.1f}% | "
                          f"{format_size(self.downloaded)}/{format_size(self.total)} | "
                          f"{format_size(speed)}/s | {format_time(eta)}")
            else:
                safe_print(f"\r{self.desc} {format_size(self.downloaded)}")
    
    def finish(self):
        with self.lock:
            if not self.done:
                self.done = True
                elapsed = time.time() - self.start_time
                safe_print(f"\r{self.desc} [{'='*25}] 100.0% | "
                          f"{format_size(self.downloaded)} | "
                          f"{format_size(self.downloaded/elapsed)}/s | "
                          f"{format_time(elapsed)}")
                safe_print("")


# ============ 智能分类 ============

class SmartCategorizer:
    """智能文件分类器"""
    
    # 文件类型映射
    CATEGORIES = {
        'model': ['.pt', '.pth', '.safetensors', '.ckpt', '.bin', '.onnx', 
                  '.gguf', '.ggml', '.mlir', '.tflite', '.pb', '.h5', '.keras'],
        'dataset': ['.jsonl', '.parquet', '.csv', '.tsv', '.arrow', '.feather',
                    '.hdf5', '.h5', '.npz', '.npy', '.pkl', '.pickle'],
        'video': ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', 
                  '.m4v', '.3gp', '.ts', '.m2ts'],
        'audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma',
                  '.opus', '.aiff', '.ape'],
        'document': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                     '.txt', '.md', '.rst', '.epub', '.mobi', '.azw3'],
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg',
                  '.ico', '.tiff', '.raw', '.psd', '.ai'],
        'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',
                    '.lz4', '.zst', '.tar.gz', '.tar.bz2', '.tar.xz'],
        'software': ['.exe', '.msi', '.dmg', '.pkg', '.deb', '.rpm', '.appimage',
                     '.snap', '.flatpak', '.sh', '.bat', '.cmd'],
        'code': ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.hpp',
                 '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.scala'],
    }
    
    @classmethod
    def categorize(cls, url, content_type=''):
        """根据 URL 和 Content-Type 分类"""
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.lower()
        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lower()
        
        # 检查 URL 特征
        url_lower = url.lower()
        if any(x in url_lower for x in ['huggingface', 'modelscope', 'civitai']):
            if ext in cls.CATEGORIES['model']:
                return 'model'
            elif ext in cls.CATEGORIES['dataset']:
                return 'dataset'
        
        # 检查文件扩展名
        for category, extensions in cls.CATEGORIES.items():
            if ext in extensions:
                return category
        
        # 检查 Content-Type
        content_type = content_type.lower()
        type_mapping = {
            'video/': 'video',
            'audio/': 'audio',
            'image/': 'image',
            'application/pdf': 'document',
            'application/zip': 'archive',
            'application/x-executable': 'software',
        }
        for prefix, category in type_mapping.items():
            if prefix in content_type:
                return category
        
        # 检查 GitHub
        if 'github.com' in parsed.netloc:
            return 'github'
        
        return 'default'
    
    @classmethod
    def get_directory(cls, category):
        """获取分类目录"""
        dir_path = DOWNLOAD_DIRS.get(category, DOWNLOAD_DIRS['default'])
        os.makedirs(dir_path, exist_ok=True)
        return dir_path


# ============ 镜像源管理 ============

class MirrorManager:
    """镜像源管理器"""
    
    @staticmethod
    def get_mirrors(url):
        """获取适合 URL 的镜像列表（自动过滤黑名单）"""
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()

        mirrors = [url]  # 原始 URL 放第一个

        # GitHub
        if 'github.com' in host:
            for m in GITHUB_MIRRORS:
                mirror_host = urllib.parse.urlparse(m).netloc.lower()
                if mirror_host not in MIRROR_BLACKLIST:
                    mirrors.append(m + url)

        # HuggingFace
        elif 'huggingface.co' in host:
            for m in HF_MIRRORS[1:]:
                mirrors.append(m + path[1:] if m.endswith('/') else m + path)

        # ModelScope
        elif 'modelscope.cn' in host:
            for m in MS_MIRRORS[1:]:
                mirrors.append(m + path[1:] if m.endswith('/') else m + path)

        return mirrors
    
    @staticmethod
    def test_mirror(url, timeout=3):
        """测试镜像可用性"""
        try:
            req = urllib.request.Request(url, method='HEAD')
            req.add_header('User-Agent',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            with urllib.request.urlopen(req, context=ssl_context,
                                       timeout=timeout) as resp:
                return True, resp.status
        except Exception as e:
            return False, str(e)


# ============ 镜像测速 ============

def test_mirror_speed(url, timeout=5):
    """测试单个镜像速度 + 健康检测，返回速度 (bytes/s)，不健康返回 -1"""
    host = urllib.parse.urlparse(url).netloc
    cache_key = host
    if cache_key in SPEED_CACHE:
        cached_time, cached_speed = SPEED_CACHE[cache_key]
        if time.time() - cached_time < 300:
            return cached_speed
    if host in MIRROR_BLACKLIST:
        return 0

    try:
        if use_curl():
            cmd = ['curl', '-sL', '--connect-timeout', '3', '--max-time', str(timeout),
                   '--range', f'0-{SPEED_TEST_SIZE - 1}', '--output', '-', url]
            start = time.time()
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
            elapsed = time.time() - start
            if proc.returncode == 0 and len(proc.stdout) > 1024:
                # 健康检测：排除返回 HTML/文本 的假镜像
                if proc.stdout[:20].startswith(b'<!') or proc.stdout[:20].startswith(b'<?xml'):
                    MIRROR_BLACKLIST.add(host)
                    safe_print(f"  [UNHEALTHY] {host} (blacklisted)")
                    return 0
                speed = len(proc.stdout) / elapsed
                SPEED_CACHE[cache_key] = (time.time(), speed)
                return speed
        else:
            req = make_request(url)
            start = time.time()
            with urllib.request.urlopen(req, context=ssl_context,
                                        timeout=timeout) as resp:
                data = resp.read(SPEED_TEST_SIZE)
                elapsed = time.time() - start
                if elapsed > 0 and len(data) > 1024:
                    if data[:20].startswith(b'<!') or data[:20].startswith(b'<?xml'):
                        MIRROR_BLACKLIST.add(host)
                        safe_print(f"  [UNHEALTHY] {host} (blacklisted)")
                        return 0
                    speed = len(data) / elapsed
                    SPEED_CACHE[cache_key] = (time.time(), speed)
                    return speed
    except:
        pass
    return 0


def select_fastest_mirror(mirrors, max_workers=3):
    """并发测试所有镜像，返回最快的 URL"""
    ranked = rank_mirrors(mirrors, max_workers)
    return ranked[0][0] if ranked else (mirrors[0] if mirrors else None)


def rank_mirrors(mirrors, max_workers=3, top_n=5):
    """并发测试所有镜像（限制并发数），返回按速度排序的 (url, speed) 列表"""
    if len(mirrors) <= 1:
        return [(m, 0) for m in mirrors]

    safe_print(f"[SpeedTest] Testing {len(mirrors)} mirrors (max {max_workers} concurrent)...")

    results = {}
    # 限制并发测速数，避免互相抢带宽导致数据不准
    with ThreadPoolExecutor(max_workers=min(max_workers, len(mirrors))) as executor:
        futures = {executor.submit(test_mirror_speed, url): url for url in mirrors}
        for future in as_completed(futures):
            url = futures[future]
            try:
                speed = future.result()
                if speed > 0:
                    results[url] = speed
                    safe_print(f"  {format_size(speed)}/s - {url[:55]}...")
            except:
                pass

    if results:
        ranked = sorted(results.items(), key=lambda x: x[1], reverse=True)
        top = ranked[:top_n]
        total = sum(s for _, s in top)
        safe_print(f"[MultiSource] Top {len(top)} mirrors, combined ~{format_size(total)}/s")
        return [(u, s) for u, s in top]

    return [(mirrors[0], 0)]


# ============ curl 引擎 ============

def curl_available():
    """检查 curl 是否可用"""
    try:
        subprocess.run(['curl', '--version'], capture_output=True, timeout=5)
        return True
    except:
        return False


def curl_download_range(url, start, end, timeout=60):
    """用 curl 下载指定范围的数据，返回 bytes"""
    cmd = [
        'curl', '-sL',
        '--connect-timeout', '10',
        '--max-time', str(timeout),
        '--range', f'{start}-{end}',
        '--output', '-',
        '--compressed',
        url
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except:
        pass
    return None


def curl_get_size(url, timeout=10):
    """用 curl HEAD 获取文件大小"""
    cmd = ['curl', '-sL', '-I', '--connect-timeout', str(timeout), url]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
        if proc.returncode == 0:
            for line in proc.stdout.decode('utf-8', errors='ignore').split('\n'):
                if 'content-length' in line.lower():
                    return int(line.split(':')[1].strip())
    except:
        pass
    return 0


_USE_CURL = None

def use_curl():
    """延迟检测 curl 可用性（只检测一次）"""
    global _USE_CURL
    if _USE_CURL is None:
        _USE_CURL = curl_available()
    return _USE_CURL


# ============ aria2c 引擎 ============

def aria2_available():
    """检查 aria2c 是否可用"""
    if ARIA2C_PATH and os.path.exists(ARIA2C_PATH):
        try:
            subprocess.run([ARIA2C_PATH, '--version'], capture_output=True, timeout=5)
            return True
        except:
            pass
    return False


def aria2_download(mirrors, output_path, file_size=None, workers=16):
    """aria2c 多源聚合下载 — 工业级引擎"""
    output_dir = str(Path(output_path).parent)
    filename = Path(output_path).name

    cmd = [
        ARIA2C_PATH,
        '-x16',                          # 每服务器最大连接数
        '-s16',                          # 分片数
        '-j16',                          # 并发下载数
        '--max-connection-per-server=16',
        '--min-split-size=1M',
        '--max-tries=5',
        '--retry-wait=3',
        '--connect-timeout=10',
        '--timeout=60',
        '--file-allocation=none',        # Windows 下跳过预分配
        '--enable-color=false',          # 清理 ANSI 转义码
        '--console-log-level=notice',
        '--summary-interval=1',
        '--allow-overwrite=true',
        '--auto-file-renaming=false',
        '--dir', output_dir,
        '--out', filename,
    ]

    # 添加所有镜像 URL（aria2c 自动聚合带宽）
    for url in mirrors:
        cmd.append(url)

    safe_print(f"[aria2c] {len(mirrors)} sources, {workers} workers, aggregating...")

    try:
        # 直接运行，aria2c 自带进度条输出到 stderr
        proc = subprocess.run(cmd, timeout=3600)
        if proc.returncode == 0:
            return True
        else:
            safe_print(f"[aria2c] Exit code: {proc.returncode}")
    except subprocess.TimeoutExpired:
        safe_print("[aria2c] Timeout")
    except Exception as e:
        safe_print(f"[aria2c] Error: {e}")

    return False


# ============ 核心下载引擎 ============

def make_request(url, headers=None, method=None, data=None):
    """创建 HTTP 请求"""
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header('User-Agent', 
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    req.add_header('Accept', '*/*')
    req.add_header('Accept-Encoding', 'identity')
    req.add_header('Connection', 'keep-alive')
    req.add_header('Accept-Language', 'zh-CN,zh;q=0.9,en;q=0.8')
    req.add_header('Referer', 'https://www.google.com/')
    
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    
    return req


def download_with_retry(url, output_path, headers=None, progress=None,
                        retries=MAX_RETRIES, resume=False):
    """带重试和断点续传的下载 — 优先 curl"""
    temp_path = str(output_path) + ".tmp"

    # 检查是否需要续传
    start_pos = 0
    if resume and os.path.exists(temp_path):
        start_pos = os.path.getsize(temp_path)
        safe_print(f"[Resume] Starting from {format_size(start_pos)}")

    # curl 引擎
    if use_curl():
        for attempt in range(retries):
            try:
                cmd = ['curl', '-sL', '--connect-timeout', '10', '--max-time', '300',
                       '-o', temp_path, url]
                if start_pos > 0:
                    cmd.insert(3, '--continue-at')
                    cmd.insert(4, '-')
                proc = subprocess.run(cmd, capture_output=True, timeout=310)
                if proc.returncode == 0:
                    os.replace(temp_path, output_path)
                    downloaded = os.path.getsize(output_path)
                    return True, downloaded
                safe_print(f"  Retry {attempt+1}/{retries}: curl exit {proc.returncode}")
            except Exception as e:
                safe_print(f"  Retry {attempt+1}/{retries}: {str(e)[:50]}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
        return False, 0

    # urllib 回退
    for attempt in range(retries):
        try:
            req_headers = headers.copy() if headers else {}
            if start_pos > 0:
                req_headers['Range'] = f'bytes={start_pos}-'

            req = make_request(url, req_headers)

            with urllib.request.urlopen(req, context=ssl_context,
                                       timeout=CONNECT_TIMEOUT) as resp:
                if start_pos > 0 and resp.status != 206:
                    safe_print("[Warning] Server doesn't support resume, restarting...")
                    start_pos = 0
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                total = int(resp.headers.get('Content-Length', 0))
                if start_pos > 0:
                    total += start_pos

                mode = 'ab' if start_pos > 0 else 'wb'
                with open(temp_path, mode) as f:
                    downloaded = start_pos
                    while True:
                        chunk = resp.read(BUFFER_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress.update(len(chunk))

                os.replace(temp_path, output_path)
                return True, downloaded

        except Exception as e:
            error_str = str(e).lower()
            if 'timed out' in error_str:
                err_msg = "timeout"
            elif 'refused' in error_str:
                err_msg = "refused"
            elif 'reset' in error_str:
                err_msg = "reset"
            elif 'certificate' in error_str:
                err_msg = "ssl error"
            else:
                err_msg = str(e)[:50]

            safe_print(f"  Retry {attempt+1}/{retries}: {err_msg}")

            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

    return False, 0


def get_file_info(url):
    """获取文件信息。aria2c 可用时跳过测速（aria2c 自己会动态优化）"""
    mirrors = MirrorManager.get_mirrors(url)

    # aria2c 引擎：跳过测速，传入所有镜像，aria2c 自动选择最快的
    if aria2_available():
        safe_print(f"[Info] aria2c detected, skipping speed test ({len(mirrors)} mirrors)")
        # 快速获取文件大小（只测试原始 URL）
        size = 0
        try:
            if use_curl():
                size = curl_get_size(url, timeout=8)
        except:
            pass
        try:
            req = make_request(url, method='HEAD')
            with urllib.request.urlopen(req, context=ssl_context,
                                       timeout=CONNECT_TIMEOUT) as resp:
                if size == 0:
                    size = int(resp.headers.get('Content-Length', 0))
                content_type = resp.headers.get('Content-Type', '')
                return {
                    'size': size,
                    'accept_ranges': resp.headers.get('Accept-Ranges', '') == 'bytes',
                    'content_type': content_type,
                    'last_modified': resp.headers.get('Last-Modified', ''),
                    'etag': resp.headers.get('ETag', ''),
                    'working_url': url,
                    'mirrors': mirrors,
                    'fastest_mirrors': [(m, 0) for m in mirrors]  # 全部传入 aria2c
                }
        except:
            pass
        return {
            'size': size, 'accept_ranges': True, 'content_type': '',
            'last_modified': '', 'etag': '', 'working_url': url,
            'mirrors': mirrors, 'fastest_mirrors': [(m, 0) for m in mirrors]
        }

    # curl/urllib 模式：需要测速选最优镜像
    ranked = rank_mirrors(mirrors)
    fastest_url = ranked[0][0] if ranked else url

    try:
        req = make_request(fastest_url, method='HEAD')
        with urllib.request.urlopen(req, context=ssl_context,
                                   timeout=CONNECT_TIMEOUT) as resp:
            size = int(resp.headers.get('Content-Length', 0))
            accept_ranges = resp.headers.get('Accept-Ranges', '') == 'bytes'
            content_type = resp.headers.get('Content-Type', '')
            last_modified = resp.headers.get('Last-Modified', '')
            etag = resp.headers.get('ETag', '')
            return {
                'size': size,
                'accept_ranges': accept_ranges,
                'content_type': content_type,
                'last_modified': last_modified,
                'etag': etag,
                'working_url': fastest_url,
                'mirrors': mirrors,
                'fastest_mirrors': ranked
            }
    except:
        pass

    return {
        'size': 0, 'accept_ranges': False, 'content_type': '',
        'last_modified': '', 'etag': '', 'working_url': fastest_url,
        'mirrors': mirrors, 'fastest_mirrors': ranked
    }


def download_single(url, output_path, progress=None, resume=False):
    """单线程多镜像下载"""
    mirrors = MirrorManager.get_mirrors(url)
    
    for i, try_url in enumerate(mirrors):
        safe_print(f"[Mirror {i+1}/{len(mirrors)}] {try_url[:65]}...")
        
        success, size = download_with_retry(try_url, output_path, 
                                           progress=progress, 
                                           retries=MAX_RETRIES,
                                           resume=resume)
        
        if success:
            return True, size
        
        safe_print(f"  -> Failed, trying next...")
    
    return False, 0


def download_chunk(args):
    """分片下载任务 — 优先用 curl，返回数据直接内存"""
    url, start, end, chunk_id = args

    # curl 引擎（原生 C，无 GIL）
    if use_curl():
        for attempt in range(3):
            data = curl_download_range(url, start, end)
            if data is not None:
                return True, chunk_id, data
            if attempt < 2:
                time.sleep(0.5)
        return False, chunk_id, "curl failed"

    # urllib 回退
    headers = {'Range': f'bytes={start}-{end}'}
    for attempt in range(3):
        try:
            req = make_request(url, headers)
            with urllib.request.urlopen(req, context=ssl_context,
                                       timeout=CONNECT_TIMEOUT) as resp:
                data = resp.read()
            return True, chunk_id, data
        except Exception as e:
            if attempt < 2:
                time.sleep(1)

    return False, chunk_id, "download failed"


def download_multi_thread(mirrors_with_speed, output_path, file_size, progress=None,
                          workers=DEFAULT_WORKERS):
    """多线程分片下载 — 加权分配，直接 I/O，无临时文件"""
    # Handle input: [(url, speed), ...] or [url, ...]
    if mirrors_with_speed and isinstance(mirrors_with_speed[0], tuple):
        mirror_urls = [m[0] for m in mirrors_with_speed]
        mirror_speeds = {m[0]: max(m[1], 1) for m in mirrors_with_speed}
    elif mirrors_with_speed and isinstance(mirrors_with_speed[0], str):
        mirror_urls = mirrors_with_speed
        mirror_speeds = {m: 1 for m in mirror_urls}
    else:
        mirror_urls = [mirrors_with_speed] if isinstance(mirrors_with_speed, str) else []
        mirror_speeds = {mirror_urls[0]: 1} if mirror_urls else {}

    num_chunks = min((file_size + CHUNK_SIZE - 1) // CHUNK_SIZE, workers * 2)
    chunk_size = file_size // num_chunks
    num_mirrors = len(mirror_urls)
    total_weight = sum(mirror_speeds.values())

    if num_mirrors > 1:
        safe_print(f"[MultiSource] {num_chunks} chunks via {num_mirrors} mirrors, "
                  f"{workers} workers, weighted, direct I/O")
    else:
        safe_print(f"[Multi-thread] {num_chunks} chunks, {workers} workers, direct I/O")

    # 预分配文件
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'wb') as f:
        f.truncate(file_size)

    # 加权分配：按速度比例计算每个镜像负责的chunk数
    if num_mirrors > 1 and total_weight > 0:
        mirror_chunks = []
        remaining = num_chunks
        for i, url in enumerate(mirror_urls):
            if i == num_mirrors - 1:
                mirror_chunks.append((url, remaining))
            else:
                share = max(1, int(mirror_speeds[url] / total_weight * num_chunks))
                share = min(share, remaining - (num_mirrors - i - 1))
                mirror_chunks.append((url, share))
                remaining -= share
    else:
        mirror_chunks = [(mirror_urls[0], num_chunks)]

    # 准备分片任务 — 按加权分配
    tasks = []
    chunk_idx = 0
    for mirror_url, nchunks in mirror_chunks:
        for _ in range(nchunks):
            if chunk_idx >= num_chunks:
                break
            start = chunk_idx * chunk_size
            end = min(start + chunk_size - 1, file_size - 1)
            if chunk_idx == num_chunks - 1:
                end = file_size - 1
            tasks.append((mirror_url, start, end, chunk_idx))
            chunk_idx += 1

    # 并发下载 + 直接写入
    futures_to_offset = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for task in tasks:
            future = executor.submit(download_chunk, task)
            futures_to_offset[future] = (task[3], task[1])  # (chunk_id, start)

        completed = 0
        failed_chunks = []

        for future in as_completed(futures_to_offset):
            chunk_id, start_offset = futures_to_offset[future]
            try:
                success, cid, data = future.result()
                if success and data:
                    # 直接写入文件对应偏移位置（各线程写入不重叠区域，无需锁）
                    fd = os.open(str(output_path), os.O_WRONLY | os.O_BINARY)
                    try:
                        os.lseek(fd, start_offset, os.SEEK_SET)
                        os.write(fd, data)
                    finally:
                        os.close(fd)
                    completed += 1
                    if progress:
                        progress.update(len(data))
                else:
                    failed_chunks.append(chunk_id)
                    safe_print(f"  Chunk {chunk_id+1} failed: {data}")
            except Exception as e:
                failed_chunks.append(chunk_id)
                safe_print(f"  Chunk {chunk_id+1} error: {e}")

    if failed_chunks:
        safe_print(f"[ERROR] {len(failed_chunks)}/{num_chunks} chunks failed")
        output_path.unlink(missing_ok=True)
        return False

    if progress:
        progress.finish()

    return True


# ============ 后处理 ============

class PostProcessor:
    """下载后处理器"""
    
    @staticmethod
    def extract_archive(filepath, output_dir=None):
        """解压压缩包"""
        if not os.path.exists(filepath):
            return False, "File not found"
        
        ext = os.path.splitext(filepath)[1].lower()
        if output_dir is None:
            output_dir = os.path.splitext(filepath)[0]
        
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            if ext == '.zip':
                shutil.unpack_archive(filepath, output_dir, 'zip')
            elif ext in ['.tar', '.gz', '.bz2', '.xz']:
                shutil.unpack_archive(filepath, output_dir)
            elif ext == '.7z':
                # 需要 py7zr 或 7z 命令
                result = subprocess.run(['7z', 'x', filepath, f'-o{output_dir}'],
                                      capture_output=True, text=True)
                if result.returncode != 0:
                    return False, f"7z failed: {result.stderr}"
            else:
                return False, f"Unsupported format: {ext}"
            
            return True, f"Extracted to {output_dir}"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def install_software(filepath):
        """安装软件（Windows）"""
        ext = os.path.splitext(filepath)[1].lower()
        
        try:
            if ext == '.exe':
                # 静默安装尝试
                result = subprocess.run([filepath, '/S', '/silent', '/quiet'],
                                      capture_output=True, text=True, timeout=300)
                return result.returncode == 0, result.stdout or result.stderr
            elif ext == '.msi':
                result = subprocess.run(['msiexec', '/i', filepath, '/quiet', '/norestart'],
                                      capture_output=True, text=True, timeout=300)
                return result.returncode == 0, result.stdout or result.stderr
            elif ext == '.py':
                result = subprocess.run([sys.executable, '-m', 'pip', 'install', filepath],
                                      capture_output=True, text=True, timeout=300)
                return result.returncode == 0, result.stdout or result.stderr
            else:
                return False, f"Unsupported install format: {ext}"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def scan_virus(filepath):
        """病毒扫描（需要 Windows Defender 或其他杀毒软件）"""
        if not os.path.exists(filepath):
            return False, "File not found"
        
        try:
            # Windows Defender
            result = subprocess.run(
                ['"C:\\Program Files\\Windows Defender\\MpCmdRun.exe"', '-Scan', '-ScanType', '3', 
                 '-File', filepath],
                capture_output=True, text=True, shell=True, timeout=300
            )
            
            if "No threats found" in result.stdout or result.returncode == 0:
                return True, "No threats found"
            else:
                return False, f"Threat detected or scan failed: {result.stdout}"
        except Exception as e:
            return False, f"Scan error: {str(e)}"


# ============ 主下载函数 ============

def download_file(url, output_path=None, use_multi_thread=True, 
                  workers=DEFAULT_WORKERS, resume=False, auto_categorize=True,
                  extract=False, install=False, scan=False):
    """智能下载主函数"""
    
    # 获取文件信息
    safe_print(f"{'='*60}")
    safe_print(f"URL: {url}")
    safe_print(f"{'='*60}")
    
    safe_print("[Info] Checking...")
    info = get_file_info(url)
    
    file_size = info['size']
    accept_ranges = info['accept_ranges']
    content_type = info['content_type']
    working_url = info['working_url']
    
    # 智能分类
    category = 'default'
    if auto_categorize:
        category = SmartCategorizer.categorize(url, content_type)
        safe_print(f"[Category] {category}")
    
    # 确定输出路径
    if output_path is None:
        parsed = urllib.parse.urlparse(url)
        filename = os.path.basename(parsed.path)
        if not filename or '.' not in filename:
            # 从 Content-Type 推断扩展名
            ext_map = {
                'application/zip': '.zip',
                'application/x-7z-compressed': '.7z',
                'application/x-tar': '.tar',
                'application/gzip': '.tar.gz',
                'application/pdf': '.pdf',
                'video/mp4': '.mp4',
                'audio/mpeg': '.mp3',
            }
            ext = ext_map.get(content_type.split(';')[0].strip(), '')
            filename = f"download_{int(time.time())}{ext}"
        
        output_dir = SmartCategorizer.get_directory(category)
        output_path = os.path.join(output_dir, filename)
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    safe_print(f"Output: {output_path}")
    
    if file_size > 0:
        safe_print(f"[Info] Size: {format_size(file_size)} | Range: {'Yes' if accept_ranges else 'No'}")
    else:
        safe_print("[Info] Size unknown")
    
    # 检查已存在
    if output_path.exists() and not resume:
        safe_print(f"[Note] File exists: {output_path}")
        try:
            resp = input("Overwrite? (y/n/r for resume): ").strip().lower()
            if resp == 'r':
                resume = True
            elif resp != 'y':
                safe_print("Cancelled.")
                return False, str(output_path), 0
        except EOFError:
            safe_print("[Auto] Non-interactive mode, overwriting...")
    
    # 选择下载策略：aria2c > curl多源 > 单线程
    start_time = time.time()
    fastest_mirrors = info.get('fastest_mirrors', [working_url])
    # 提取纯 URL 列表（兼容 (url, speed) 元组格式）
    if fastest_mirrors and isinstance(fastest_mirrors[0], tuple):
        mirror_urls = [m[0] for m in fastest_mirrors]
    else:
        mirror_urls = fastest_mirrors

    # 引擎1: aria2c（工业级 C++ 引擎）
    if aria2_available():
        safe_print(f"[Engine] aria2c (industrial-grade)")
        safe_print(f"[Mode] MultiSource: {len(mirror_urls)} mirrors aggregating...")
        success = aria2_download(mirror_urls, output_path, file_size, workers)
        downloaded_size = file_size if success else 0
    # 引擎2: curl 多源 + 直接 I/O
    elif use_multi_thread and file_size > CHUNK_THRESHOLD and accept_ranges:
        if len(mirror_urls) > 1:
            safe_print(f"[Engine] curl multi-source ({len(mirror_urls)} mirrors)")
        else:
            safe_print(f"[Engine] curl multi-thread ({workers} workers)")
        progress = ProgressBar(file_size)
        success = download_multi_thread(fastest_mirrors, output_path, file_size,
                                       progress, workers)
        downloaded_size = file_size if success else 0
    # 引擎3: 单线程回退
    else:
        safe_print(f"[Engine] curl single-thread + mirrors")
        progress = ProgressBar(file_size) if file_size > 0 else ProgressBar(0)
        success, downloaded_size = download_single(working_url, output_path,
                                                    progress, resume)
        if success and progress:
            progress.finish()
    
    elapsed = time.time() - start_time
    
    if not success:
        safe_print(f"[FAILED] All sources failed")
        return False, str(output_path), 0
    
    # 下载成功后的处理
    actual_size = output_path.stat().st_size
    safe_print(f"{'='*60}")
    safe_print(f"[SUCCESS] Downloaded!")
    safe_print(f"  File: {output_path}")
    safe_print(f"  Size: {format_size(actual_size)}")
    safe_print(f"  Time: {format_time(elapsed)}")
    safe_print(f"  Speed: {format_size(actual_size/elapsed)}/s")
    
    # 计算哈希
    safe_print("[Hash] Calculating SHA256...")
    file_hash = calculate_hash(output_path)
    safe_print(f"  SHA256: {file_hash}")
    
    # 保存下载记录
    record = {
        'url': url,
        'path': str(output_path),
        'size': actual_size,
        'sha256': file_hash,
        'category': category,
        'timestamp': datetime.now().isoformat(),
        'elapsed': elapsed,
    }
    
    # 后处理
    if extract and category == 'archive':
        safe_print("[Extract] Extracting archive...")
        ok, msg = PostProcessor.extract_archive(str(output_path))
        safe_print(f"  {'OK' if ok else 'FAILED'}: {msg}")
        record['extracted'] = ok
    
    if install and category == 'software':
        safe_print("[Install] Installing software...")
        ok, msg = PostProcessor.install_software(str(output_path))
        safe_print(f"  {'OK' if ok else 'FAILED'}: {msg}")
        record['installed'] = ok
    
    if scan:
        safe_print("[Scan] Scanning for viruses...")
        ok, msg = PostProcessor.scan_virus(str(output_path))
        safe_print(f"  {'OK' if ok else 'WARNING'}: {msg}")
        record['scan_result'] = ok
    
    safe_print(f"{'='*60}")
    
    # 保存记录到 JSON
    record_file = os.path.join(os.path.expanduser('~/.qclaw'), 'download_history.json')
    os.makedirs(os.path.dirname(record_file), exist_ok=True)
    
    history = []
    if os.path.exists(record_file):
        try:
            with open(record_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except:
            pass
    
    history.append(record)
    
    # 只保留最近 1000 条
    history = history[-1000:]
    
    with open(record_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    
    return True, str(output_path), actual_size


def download_batch(urls, output_dir=None, **kwargs):
    """批量下载"""
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    results = []
    for i, url in enumerate(urls, 1):
        safe_print(f"\n[{i}/{len(urls)}] {url}")
        
        if output_dir:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path) or "download"
            output_path = os.path.join(output_dir, filename)
            success, path, size = download_file(url, output_path, **kwargs)
        else:
            success, path, size = download_file(url, **kwargs)
        
        results.append((url, success, path, size))
    
    safe_print(f"\n{'='*60}")
    safe_print(f"Summary: {sum(1 for r in results if r[1])}/{len(urls)} success")
    total = sum(r[3] for r in results if r[1])
    safe_print(f"Total: {format_size(total)}")
    safe_print(f"{'='*60}")
    
    return results


# ============ 命令行入口 ============

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='小龙下载助手 v3.0 - AI 工作流全能下载工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
Examples:
  # 基本下载
  %(prog)s https://github.com/.../file.zip
  
  # 指定输出路径
  %(prog)s https://example.com/file.exe -o D:\Downloads\
  
  # 批量下载
  %(prog)s url1 url2 url3
  %(prog)s -f urls.txt
  
  # 多线程下载大文件
  %(prog)s https://.../bigfile.zip --workers 16
  
  # 断点续传
  %(prog)s https://.../bigfile.zip --resume
  
  # 下载并解压
  %(prog)s https://.../archive.zip --extract
  
  # 下载并扫描病毒
  %(prog)s https://.../installer.exe --scan
  
  # 禁用智能分类
  %(prog)s https://.../file.zip --no-categorize
        """)
    
    parser.add_argument('urls', nargs='*', help='下载链接')
    parser.add_argument('-o', '--output', help='输出路径或目录')
    parser.add_argument('-f', '--file', help='URL 列表文件')
    parser.add_argument('--no-multi-thread', action='store_true', 
                       help='禁用多线程')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS,
                       help=f'线程数 (默认 {DEFAULT_WORKERS}, 最大 {MAX_WORKERS})')
    parser.add_argument('--timeout', type=int, default=CONNECT_TIMEOUT,
                       help=f'超时秒数 (默认 {CONNECT_TIMEOUT})')
    parser.add_argument('--resume', action='store_true',
                       help='启用断点续传')
    parser.add_argument('--no-categorize', action='store_true',
                       help='禁用智能分类')
    parser.add_argument('--extract', action='store_true',
                       help='下载后解压（仅压缩包）')
    parser.add_argument('--install', action='store_true',
                       help='下载后安装（仅软件包）')
    parser.add_argument('--scan', action='store_true',
                       help='下载后病毒扫描')
    
    args = parser.parse_args()
    
    # 收集 URL
    urls = []
    if args.urls:
        urls.extend(args.urls)
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            urls.extend(line.strip() for line in f 
                       if line.strip() and not line.startswith('#'))
    
    if not urls:
        parser.print_help()
        sys.exit(1)
    
    # 设置全局参数
    import types
    current_module = sys.modules[__name__]
    current_module.CONNECT_TIMEOUT = args.timeout
    current_module.MAX_WORKERS = min(args.workers, 32)
    
    # 执行下载
    kwargs = {
        'use_multi_thread': not args.no_multi_thread,
        'workers': args.workers,
        'resume': args.resume,
        'auto_categorize': not args.no_categorize,
        'extract': args.extract,
        'install': args.install,
        'scan': args.scan,
    }
    
    if len(urls) == 1 and args.output and not os.path.isdir(args.output):
        # 单文件指定输出路径
        download_file(urls[0], args.output, **kwargs)
    elif len(urls) == 1:
        download_file(urls[0], args.output, **kwargs)
    else:
        download_batch(urls, args.output, **kwargs)


if __name__ == '__main__':
    main()
