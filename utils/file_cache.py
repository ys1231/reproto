"""
文件内容缓存系统

用于缓存Java源码文件内容，避免重复的文件I/O操作
这是解决reproto性能瓶颈的核心优化组件

Author: AI Assistant
"""

from pathlib import Path
from typing import Optional, Dict
import threading

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from .logger import get_logger
except ImportError:
    # 绝对导入（开发环境）
    from utils.logger import get_logger


class FileContentCache:
    """
    文件内容缓存系统
    
    提供线程安全的文件内容缓存，显著减少重复的文件I/O操作
    特别适用于需要多次读取同一Java文件的场景
    """
    
    def __init__(self):
        """初始化缓存系统"""
        self._cache: Dict[str, str] = {}
        self._stats = {
            'hits': 0,
            'misses': 0,
            'errors': 0
        }
        self._lock = threading.RLock()  # 使用可重入锁
        self.logger = get_logger("file_cache")
    
    def get_content(self, file_path: Path) -> Optional[str]:
        """
        获取文件内容，优先从缓存读取
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容字符串，如果读取失败则返回None
        """
        cache_key = str(file_path.resolve())
        
        with self._lock:
            # 检查缓存
            if cache_key in self._cache:
                self._stats['hits'] += 1
                return self._cache[cache_key]
            
            # 缓存未命中，读取文件
            try:
                if not file_path.exists():
                    self._stats['errors'] += 1
                    return None
                
                content = file_path.read_text(encoding='utf-8')
                self._cache[cache_key] = content
                self._stats['misses'] += 1
                
                # 定期输出缓存统计
                total_requests = self._stats['hits'] + self._stats['misses']
                if total_requests % 50 == 0 and total_requests > 0:
                    hit_rate = self._stats['hits'] / total_requests * 100
                    self.logger.debug(f"📊 缓存统计: {total_requests} 次请求, 命中率 {hit_rate:.1f}%")
                
                return content
                
            except Exception as e:
                self._stats['errors'] += 1
                self.logger.error(f"❌ 读取文件失败 {file_path}: {e} - 这将影响Java源码分析！")
                return None
    
    def preload_files(self, file_paths: list[Path]) -> int:
        """
        预加载文件列表到缓存
        
        Args:
            file_paths: 要预加载的文件路径列表
            
        Returns:
            成功预加载的文件数量
        """
        loaded_count = 0
        
        for file_path in file_paths:
            if self.get_content(file_path) is not None:
                loaded_count += 1
        
        self.logger.info(f"📁 预加载完成: {loaded_count}/{len(file_paths)} 个文件")
        return loaded_count
    
    def clear_cache(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self.logger.info("🗑️  缓存已清空")
    
    def get_stats(self) -> dict:
        """
        获取缓存统计信息
        
        Returns:
            包含缓存统计的字典
        """
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'total_requests': total_requests,
                'cache_hits': self._stats['hits'],
                'cache_misses': self._stats['misses'],
                'hit_rate_percent': hit_rate,
                'errors': self._stats['errors'],
                'cached_files': len(self._cache)
            }
    
    def print_stats(self):
        """打印缓存统计信息"""
        stats = self.get_stats()
        
        self.logger.info("📊 文件缓存统计:")
        self.logger.info(f"   总请求数: {stats['total_requests']}")
        self.logger.info(f"   缓存命中: {stats['cache_hits']}")
        self.logger.info(f"   缓存未命中: {stats['cache_misses']}")
        self.logger.info(f"   命中率: {stats['hit_rate_percent']:.1f}%")
        self.logger.info(f"   错误数: {stats['errors']}")
        self.logger.info(f"   已缓存文件: {stats['cached_files']}")
        
        # 计算性能提升
        if stats['cache_hits'] > 0:
            io_saved = stats['cache_hits']
            self.logger.info(f"   🚀 节省I/O操作: {io_saved} 次")


# 全局缓存实例
_global_cache = None
_cache_lock = threading.Lock()


def get_file_cache() -> FileContentCache:
    """
    获取全局文件缓存实例（单例模式）
    
    Returns:
        FileContentCache实例
    """
    global _global_cache
    
    if _global_cache is None:
        with _cache_lock:
            if _global_cache is None:
                _global_cache = FileContentCache()
    
    return _global_cache


def clear_global_cache():
    """清空全局缓存"""
    global _global_cache
    if _global_cache is not None:
        _global_cache.clear_cache() 