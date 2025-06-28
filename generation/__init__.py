"""
代码生成模块

负责将解析得到的消息定义转换为Protobuf .proto文件
"""

from .proto_generator import ProtoGenerator

__all__ = [
    'ProtoGenerator'
]



