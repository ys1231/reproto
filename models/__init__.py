"""
模型定义模块

包含Protobuf消息、字段、枚举等数据结构的定义
所有具体的类定义都在相应的子模块中
"""

# 从子模块导入主要类，便于外部使用
from .message_definition import (
    MessageDefinition, 
    FieldDefinition, 
    OneofDefinition, 
    EnumDefinition, 
    EnumValueDefinition
)

__all__ = [
    'MessageDefinition',
    'FieldDefinition', 
    'OneofDefinition',
    'EnumDefinition',
    'EnumValueDefinition'
] 