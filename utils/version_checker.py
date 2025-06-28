"""
通用版本检测模块

支持检测Python包的新版本并提供用户友好的提示信息
设计为通用模块，可以被其他Python库复用

支持的版本源：
- PyPI (Python Package Index)

Author: AI Assistant
"""

import json
import time
import threading
from typing import Optional, Callable
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from packaging import version
import tempfile
import importlib.metadata

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from .logger import get_logger
except ImportError:
    # 绝对导入（开发环境）
    from utils.logger import get_logger


def get_package_version(package_name: str) -> Optional[str]:
    """
    动态获取已安装包的版本号
    
    Args:
        package_name: 包名
        
    Returns:
        包版本号，如果获取失败则返回None
    """
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


class VersionChecker:
    """
    通用版本检测器
    
    功能：
    - 支持PyPI版本源
    - 异步检测，不阻塞主程序
    - 智能缓存，避免频繁请求
    - 可配置的检测间隔和提示样式
    - 动态获取当前版本
    """
    
    def __init__(self, 
                 package_name: str,
                 current_version: Optional[str] = None,
                 cache_duration: int = 3600,  # 缓存1小时
                 timeout: int = 5,            # 请求超时5秒
                 silent_mode: bool = False):  # 静默模式
        """
        初始化版本检测器
        
        Args:
            package_name: 包名
            current_version: 当前版本，如果为None则自动获取
            cache_duration: 缓存持续时间（秒）
            timeout: 网络请求超时时间（秒）
            silent_mode: 是否启用静默模式（不打印日志）
        """
        self.package_name = package_name
        self.current_version = current_version or get_package_version(package_name) or "0.0.0"
        self.cache_duration = cache_duration
        self.timeout = timeout
        self.silent_mode = silent_mode
        
        # 缓存配置
        self.cache_dir = Path(tempfile.gettempdir()) / f".{package_name}_version_cache"
        self.cache_file = self.cache_dir / "latest_version.json"
        
        # 日志配置
        self.logger = get_logger("version_checker") if not silent_mode else None
    
    def check_version_async(self, 
                           callback: Optional[Callable] = None,
                           show_notification: bool = True):
        """
        异步检测版本更新
        
        Args:
            callback: 检测完成后的回调函数
            show_notification: 是否显示更新提示
        """
        def _check():
            try:
                latest_version = self.check_version_sync()
                if latest_version and self._is_newer_version(latest_version):
                    if show_notification:
                        self._show_update_notification(latest_version)
                    if callback:
                        callback(True, latest_version)
                else:
                    if callback:
                        callback(False, latest_version)
            except Exception as e:
                if not self.silent_mode and self.logger:
                    self.logger.debug(f"版本检测失败: {e}")
                if callback:
                    callback(False, None)
        
        thread = threading.Thread(target=_check, daemon=True)
        thread.start()
    
    def check_version_sync(self) -> Optional[str]:
        """
        同步检测版本更新
        
        Returns:
            最新版本号，如果检测失败则返回None
        """
        # 检查缓存
        cached_version = self._get_cached_version()
        if cached_version:
            return cached_version
        
        # 从PyPI获取最新版本
        try:
            latest_version = self._check_pypi_version()
            if latest_version:
                self._cache_version(latest_version)
            return latest_version
        except Exception as e:
            if not self.silent_mode and self.logger:
                self.logger.debug(f"从PyPI检测版本失败: {e}")
        
        return None
    
    def _check_pypi_version(self) -> Optional[str]:
        """从PyPI检测最新版本"""
        url = f"https://pypi.org/pypi/{self.package_name}/json"
        
        try:
            request = Request(url, headers={'User-Agent': f'{self.package_name}-version-checker'})
            with urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode())
                return data['info']['version']
        except (URLError, HTTPError, KeyError, json.JSONDecodeError):
            return None
    
    def _is_newer_version(self, latest_version: str) -> bool:
        """检查是否有新版本"""
        try:
            return version.parse(latest_version) > version.parse(self.current_version)
        except Exception:
            # 如果版本解析失败，使用字符串比较
            return latest_version != self.current_version
    
    def _get_cached_version(self) -> Optional[str]:
        """获取缓存的版本信息"""
        try:
            if not self.cache_file.exists():
                return None
            
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 检查缓存是否过期
            cache_time = cache_data.get('timestamp', 0)
            if time.time() - cache_time > self.cache_duration:
                return None
            
            return cache_data.get('version')
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None
    
    def _cache_version(self, latest_version: str):
        """缓存版本信息"""
        try:
            self.cache_dir.mkdir(exist_ok=True)
            
            cache_data = {
                'version': latest_version,
                'timestamp': time.time()
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
        except Exception:
            pass  # 缓存失败不影响主功能
    
    def _show_update_notification(self, latest_version: str):
        """显示更新通知"""
        if self.silent_mode:
            return
        
        print(f"\n🎉 {self.package_name} 有新版本可用!")
        print(f"   当前版本: {self.current_version}")
        print(f"   最新版本: {latest_version}")
        print(f"   更新命令: pip install --upgrade {self.package_name}")
        print()
    
    def clear_cache(self):
        """清除版本缓存"""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
        except Exception:
            pass


def create_version_checker(package_name: str, 
                          current_version: Optional[str] = None,
                          **kwargs) -> VersionChecker:
    """
    创建版本检测器的便捷函数
    
    Args:
        package_name: 包名
        current_version: 当前版本，如果为None则自动获取
        **kwargs: 其他配置参数
        
    Returns:
        VersionChecker实例
    """
    return VersionChecker(package_name, current_version, **kwargs)


def check_pypi_version(package_name: str, 
                      current_version: Optional[str] = None,
                      show_notification: bool = True,
                      silent_mode: bool = False) -> Optional[str]:
    """
    快速检测PyPI版本的便捷函数
    
    Args:
        package_name: 包名
        current_version: 当前版本，如果为None则自动获取
        show_notification: 是否显示通知
        silent_mode: 是否静默模式
        
    Returns:
        最新版本号，如果检测失败则返回None
    """
    checker = VersionChecker(package_name, current_version, silent_mode=silent_mode)
    latest_version = checker.check_version_sync()
    
    if latest_version and checker._is_newer_version(latest_version) and show_notification:
        checker._show_update_notification(latest_version)
    
    return latest_version


def check_reproto_version(current_version: Optional[str] = None, 
                         show_notification: bool = True,
                         silent_mode: bool = False) -> Optional[str]:
    """
    检测reproto包的PyPI版本更新
    
    这是专门为reproto项目设计的便捷函数，使用PyPI作为版本源
    
    Args:
        current_version: 当前版本，如果为None则自动获取
        show_notification: 是否显示更新通知，默认True
        silent_mode: 是否静默模式，默认False
        
    Returns:
        最新版本号，如果检测失败则返回None
    """
    return check_pypi_version(
        package_name="reproto",
        current_version=current_version,
        show_notification=show_notification,
        silent_mode=silent_mode
    )


def check_version_on_startup(current_version: Optional[str] = None):
    """
    在程序启动时异步检测版本更新
    
    这个函数专门用于在reproto启动时进行版本检测，
    采用异步方式，不会阻塞主程序启动
    
    Args:
        current_version: 当前版本号，如果为None则自动获取
    """
    # 获取当前版本
    actual_version = current_version or get_package_version("reproto") or "0.0.0"
    
    def version_callback(has_update: bool, latest_version: Optional[str]):
        if has_update and latest_version:
            print(f"\n💡 提示：reproto有新版本 {latest_version} 可用")
            print(f"   当前版本：{actual_version}")
            print(f"   更新命令：pip install --upgrade reproto\n")
    
    checker = create_version_checker(
        package_name="reproto",
        current_version=actual_version,
        silent_mode=True  # 静默模式，只在有更新时通过回调显示
    )
    
    checker.check_version_async(
        callback=version_callback,
        show_notification=False  # 使用自定义回调，不使用默认通知
    ) 