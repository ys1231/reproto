"""
统一的日志管理模块
基于loguru提供结构化日志功能
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger


class LoggerManager:
    """日志管理器"""
    
    def __init__(self):
        self._configured = False
    
    def setup_logger(self, log_dir: str = "./logs") -> None:
        """
        设置日志系统
        
        Args:
            log_dir: 日志文件输出目录
        """
        if self._configured:
            return
            
        # 移除默认处理器
        logger.remove()
        
        # 创建日志目录
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)
        
        # 生成日志文件名：reproto-YYYY-MM-DD-HH-MM-SS.log
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        log_file = log_path / f"reproto-{timestamp}.log"
        
        # 控制台输出 - 彩色格式
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                   "<level>{message}</level>",
            level="INFO",
            colorize=True
        )
        
        # 文件输出 - 详细格式
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                   "{level: <8} | "
                   "{name}:{function}:{line} | "
                   "{message}",
            level="DEBUG",
            rotation="100 MB",
            retention="30 days",
            compression="zip",
            encoding="utf-8"
        )
        
        self._configured = True
        logger.info(f"日志系统已初始化，日志文件: {log_file}")
    
    def get_logger(self, name: Optional[str] = None):
        """获取logger实例"""
        if not self._configured:
            self.setup_logger()
        
        if name:
            return logger.bind(name=name)
        return logger


# 全局日志管理器实例
log_manager = LoggerManager()

def get_logger(name: Optional[str] = None):
    """获取logger实例的便捷函数"""
    return log_manager.get_logger(name)

def setup_logger(log_dir: str = "./logs") -> None:
    """设置日志系统的便捷函数"""
    log_manager.setup_logger(log_dir) 