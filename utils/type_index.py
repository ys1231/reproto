"""
类型匹配索引系统

用于快速查找Java类型，避免重复的目录扫描操作
这是解决reproto性能瓶颈的第二个核心优化组件

Author: AI Assistant
"""

from pathlib import Path
from typing import Dict, List, Optional, Set
import threading

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from .logger import get_logger
except ImportError:
    # 绝对导入（开发环境）
    from utils.logger import get_logger


class TypeMatchingIndex:
    """
    类型匹配索引系统
    
    构建从类型名到完整类名的多级索引，支持：
    - 精确匹配（完整类名）
    - 简单名匹配（类名）
    - 后缀匹配（如 IdData -> ContactIdData）
    - 包名相似度匹配
    """
    
    def __init__(self, sources_dir: Path):
        """
        初始化索引系统
        
        Args:
            sources_dir: Java源码根目录
        """
        self.sources_dir = sources_dir
        self.logger = get_logger("type_index")
        
        # 多级索引结构
        self._exact_index: Dict[str, str] = {}          # 完整类名 -> 完整类名
        self._simple_index: Dict[str, List[str]] = {}   # 简单类名 -> [完整类名列表]
        self._suffix_index: Dict[str, List[str]] = {}   # 后缀 -> [完整类名列表]
        self._package_index: Dict[str, List[str]] = {}  # 包名 -> [完整类名列表]
        
        # 基础类型集合（快速过滤）
        self._basic_types: Set[str] = {
            'int', 'long', 'float', 'double', 'boolean', 'byte', 'short', 'char',
            'String', 'Object', 'Integer', 'Long', 'Float', 'Double', 'Boolean',
            'Byte', 'Short', 'Character', 'List', 'Map', 'Set', 'Collection'
        }
        
        # 索引统计
        self._stats = {
            'total_classes': 0,
            'index_hits': 0,
            'index_misses': 0,
            'basic_type_skips': 0
        }
        
        self._lock = threading.RLock()
        self._is_built = False
    
    def build_index(self) -> None:
        """构建所有索引"""
        if self._is_built:
            return
            
        with self._lock:
            if self._is_built:
                return
                
            self.logger.info("🏗️  开始构建类型索引...")
            
            # 扫描所有Java文件
            java_files = list(self.sources_dir.rglob("*.java"))
            self.logger.info(f"📁 发现 {len(java_files)} 个Java文件")
            
            for java_file in java_files:
                self._index_single_file(java_file)
            
            self._stats['total_classes'] = len(self._exact_index)
            self._is_built = True
            
            self.logger.info(f"✅ 索引构建完成: {self._stats['total_classes']} 个类")
            self._print_index_stats()
    
    def _index_single_file(self, java_file: Path) -> None:
        """
        为单个Java文件建立索引
        
        Args:
            java_file: Java文件路径
        """
        try:
            # 获取类名和包名
            class_name = java_file.stem
            relative_path = java_file.relative_to(self.sources_dir)
            package_parts = relative_path.parts[:-1]  # 排除文件名
            
            if package_parts:
                package_name = '.'.join(package_parts)
                full_class_name = f"{package_name}.{class_name}"
            else:
                package_name = ""
                full_class_name = class_name
            
            # 1. 精确索引：完整类名
            self._exact_index[full_class_name] = full_class_name
            
            # 2. 简单名索引
            if class_name not in self._simple_index:
                self._simple_index[class_name] = []
            self._simple_index[class_name].append(full_class_name)
            
            # 3. 后缀索引（用于匹配如 IdData -> ContactIdData）
            if len(class_name) > 4:
                for suffix_len in [4, 6, 8]:  # 多种后缀长度
                    if len(class_name) >= suffix_len:
                        suffix = class_name[-suffix_len:]
                        if suffix not in self._suffix_index:
                            self._suffix_index[suffix] = []
                        self._suffix_index[suffix].append(full_class_name)
            
            # 4. 包名索引
            if package_name:
                if package_name not in self._package_index:
                    self._package_index[package_name] = []
                self._package_index[package_name].append(full_class_name)
                
        except Exception as e:
            self.logger.warning(f"⚠️  索引文件失败 {java_file}: {e}")
    
    def find_best_match(self, type_name: str, current_package: str = "") -> Optional[str]:
        """
        查找类型名的最佳匹配
        
        Args:
            type_name: 要查找的类型名
            current_package: 当前包名（用于相似度计算）
            
        Returns:
            最佳匹配的完整类名，如果没有找到则返回None
        """
        if not self._is_built:
            self.build_index()
        
        # 快速过滤基础类型
        if type_name in self._basic_types:
            self._stats['basic_type_skips'] += 1
            return None
        
        with self._lock:
            # 1. 精确匹配
            if type_name in self._exact_index:
                self._stats['index_hits'] += 1
                return self._exact_index[type_name]
            
            # 2. 简单名匹配
            if type_name in self._simple_index:
                candidates = self._simple_index[type_name]
                if len(candidates) == 1:
                    self._stats['index_hits'] += 1
                    return candidates[0]
                else:
                    # 多个候选，选择包名最相似的
                    best_match = self._select_best_by_package(candidates, current_package)
                    if best_match:
                        self._stats['index_hits'] += 1
                        return best_match
            
            # 3. 后缀匹配
            for suffix_len in [4, 6, 8]:
                if len(type_name) >= suffix_len:
                    suffix = type_name[-suffix_len:]
                    if suffix in self._suffix_index:
                        candidates = self._suffix_index[suffix]
                        # 过滤：确保候选类名以type_name结尾
                        filtered_candidates = [
                            c for c in candidates 
                            if c.split('.')[-1].endswith(type_name)
                        ]
                        if filtered_candidates:
                            best_match = self._select_best_by_package(filtered_candidates, current_package)
                            if best_match:
                                self._stats['index_hits'] += 1
                                return best_match
            
            # 4. 未找到匹配
            self._stats['index_misses'] += 1
            return None
    
    def _select_best_by_package(self, candidates: List[str], current_package: str) -> Optional[str]:
        """
        根据包名相似度选择最佳候选
        
        Args:
            candidates: 候选类名列表
            current_package: 当前包名
            
        Returns:
            最佳匹配的类名
        """
        if not candidates:
            return None
        
        if len(candidates) == 1:
            return candidates[0]
        
        if not current_package:
            return candidates[0]  # 无包名信息时返回第一个
        
        # 计算包名相似度
        best_candidate = None
        best_similarity = -1
        
        for candidate in candidates:
            candidate_package = '.'.join(candidate.split('.')[:-1])
            similarity = self._calculate_package_similarity(candidate_package, current_package)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_candidate = candidate
        
        return best_candidate
    
    def _calculate_package_similarity(self, package1: str, package2: str) -> float:
        """
        计算两个包名的相似度
        
        Args:
            package1: 第一个包名
            package2: 第二个包名
            
        Returns:
            相似度分数（0-1）
        """
        if not package1 or not package2:
            return 0.0
        
        parts1 = package1.split('.')
        parts2 = package2.split('.')
        
        # 计算公共前缀长度
        common_prefix = 0
        for i in range(min(len(parts1), len(parts2))):
            if parts1[i] == parts2[i]:
                common_prefix += 1
            else:
                break
        
        # 相似度 = 公共前缀长度 / 最大包深度
        max_depth = max(len(parts1), len(parts2))
        return common_prefix / max_depth if max_depth > 0 else 0.0
    
    def get_classes_in_package(self, package_name: str) -> List[str]:
        """
        获取指定包中的所有类
        
        Args:
            package_name: 包名
            
        Returns:
            类名列表
        """
        if not self._is_built:
            self.build_index()
        
        return self._package_index.get(package_name, [])
    
    def get_stats(self) -> dict:
        """
        获取索引统计信息
        
        Returns:
            包含索引统计的字典
        """
        with self._lock:
            total_requests = self._stats['index_hits'] + self._stats['index_misses']
            hit_rate = (self._stats['index_hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'total_classes': self._stats['total_classes'],
                'total_requests': total_requests,
                'index_hits': self._stats['index_hits'],
                'index_misses': self._stats['index_misses'],
                'hit_rate_percent': hit_rate,
                'basic_type_skips': self._stats['basic_type_skips'],
                'is_built': self._is_built
            }
    
    def _print_index_stats(self):
        """打印索引构建统计"""
        self.logger.info("📊 索引统计:")
        self.logger.info(f"   精确索引: {len(self._exact_index)} 个类")
        self.logger.info(f"   简单名索引: {len(self._simple_index)} 个条目")
        self.logger.info(f"   后缀索引: {len(self._suffix_index)} 个条目")
        self.logger.info(f"   包名索引: {len(self._package_index)} 个包")
    
    def print_stats(self):
        """打印使用统计信息"""
        stats = self.get_stats()
        
        self.logger.info("📊 类型索引统计:")
        self.logger.info(f"   总类数: {stats['total_classes']}")
        self.logger.info(f"   查询请求: {stats['total_requests']}")
        self.logger.info(f"   索引命中: {stats['index_hits']}")
        self.logger.info(f"   索引未命中: {stats['index_misses']}")
        self.logger.info(f"   命中率: {stats['hit_rate_percent']:.1f}%")
        self.logger.info(f"   基础类型跳过: {stats['basic_type_skips']}")


# 全局索引实例
_global_index = None
_index_lock = threading.Lock()


def get_type_index(sources_dir: Path = None) -> TypeMatchingIndex:
    """
    获取全局类型索引实例（单例模式）
    
    Args:
        sources_dir: 源码目录（仅在首次调用时需要）
        
    Returns:
        TypeMatchingIndex实例
    """
    global _global_index
    
    if _global_index is None:
        with _index_lock:
            if _global_index is None:
                if sources_dir is None:
                    raise ValueError("首次调用 get_type_index 时必须提供 sources_dir 参数")
                _global_index = TypeMatchingIndex(sources_dir)
                _global_index.build_index()
    
    return _global_index


def clear_global_index():
    """清空全局索引"""
    global _global_index
    _global_index = None 