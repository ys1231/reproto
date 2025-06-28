"""
解析器模块

包含各种源码解析器：
- Java解析器：解析Java源码，提取字段标签和类型信息
- 枚举解析器：专门处理Java枚举类的解析
"""

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from .java_parser import JavaParser
    from .enum_parser import EnumParser
except ImportError:
    # 绝对导入（开发环境）
    from parsing.java_parser import JavaParser
    from parsing.enum_parser import EnumParser

__all__ = [
    'JavaParser',
    'EnumParser'
]



