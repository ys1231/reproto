"""
代码生成模块

负责将解析得到的消息定义转换为Protobuf .proto文件
"""

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from .proto_generator import ProtoGenerator
except ImportError:
    # 绝对导入（开发环境）
    from generation.proto_generator import ProtoGenerator

__all__ = [
    'ProtoGenerator'
]



