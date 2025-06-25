"""
文件处理工具 (file_utils.py)
=============================

本模块提供与文件系统操作相关的各种辅助函数。

核心功能：
- **Java 源码定位**:
  - `get_java_file_path`: 根据 Java 类的完全限定名称（如 `com.example.MyMessage`）和 JADX `sources` 根目录，计算出对应的 Java 文件路径（如 `.../sources/com/example/MyMessage.java`）。
- **Proto 文件路径管理**:
  - `get_proto_file_path`: 根据 Java 类的包名和类名，计算出生成的 `.proto` 文件应该存放的相对路径和完整路径，确保了与原始包结构一致的目录层次。
- **文件读写**:
  - 提供简单的封装函数来读取文件内容和将生成的 .proto 字符串写入磁盘，并包含适当的错误处理。
"""

import os
from .logger import default_logger as logger

def get_java_file_path(source_dir: str, java_class_name: str) -> str:
    """
    根据 Java 类的完全限定名称，构建其在 JADX 输出目录中的文件路径。

    Args:
        source_dir (str): JADX 的 'sources' 根目录。
        java_class_name (str): Java 类的完全限定名称 (e.g., "com.example.messaging.v1.models.MessageData").

    Returns:
        str: 该 Java 文件的完整路径。
    """
    path_parts = java_class_name.split('.')
    relative_path = os.path.join(*path_parts) + ".java"
    full_path = os.path.join(source_dir, relative_path)
    logger.debug(f"将类名 '{java_class_name}' 解析为路径: {full_path}")
    return full_path

def get_proto_file_path(output_dir: str, package_name: str, proto_name: str) -> (str, str):
    """
    根据包名和消息名，构建 .proto 文件的目标路径。

    Args:
        output_dir (str): .proto 文件的输出根目录。
        package_name (str): .proto 的包名 (e.g., "com.example.messaging.v1.models").
        proto_name (str): .proto 的消息名 (e.g., "SearchResult").

    Returns:
        tuple[str, str]: 返回一个元组，包含：
                         - 相对路径 (用于 import 语句, e.g., "com/example/messaging/v1/models/MessageData.proto")
                         - 完整写入路径 (e.g., "/path/to/output/com/example/messaging/v1/models/MessageData.proto")
    """
    path_parts = package_name.split('.')
    relative_dir = os.path.join(*path_parts)
    relative_path = os.path.join(relative_dir, f"{proto_name}.proto")
    full_path = os.path.join(output_dir, relative_path)
    
    logger.debug(f"为 proto '{proto_name}' 在包 '{package_name}' 中生成路径:")
    logger.debug(f"  -> 相对路径 (for import): {relative_path}")
    logger.debug(f"  -> 完整路径 (for write): {full_path}")
    
    return relative_path, full_path

def read_file_content(file_path: str) -> str:
    """
    读取文件的全部内容。

    Args:
        file_path (str): 要读取的文件的完整路径。

    Returns:
        str: 文件的内容。
    
    Raises:
        FileNotFoundError: 如果文件不存在。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"尝试读取一个不存在的文件: {file_path}")
        raise
    except Exception as e:
        logger.error(f"读取文件时发生未知错误 {file_path}: {e}")
        raise

def write_proto_file(file_path: str, content: str):
    """
    将内容写入指定的 .proto 文件，如果目录不存在则创建它。

    Args:
        file_path (str): 要写入的文件的完整路径。
        content (str): 要写入的文件内容。
    """
    try:
        dir_name = os.path.dirname(file_path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
            logger.info(f"已创建目录: {dir_name}")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.success(f"成功将 .proto 文件写入到: {file_path}")
        
    except IOError as e:
        logger.error(f"无法写入文件 {file_path}: {e}")
        raise 