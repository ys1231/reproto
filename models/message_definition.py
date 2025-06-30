"""
Protobuf数据模型定义

定义了重构过程中使用的核心数据结构：
- FieldDefinition: 字段定义
- OneofDefinition: Oneof字段组定义  
- MessageDefinition: 消息定义

Author: AI Assistant
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FieldDefinition:
    """
    Protobuf字段定义
    
    表示单个字段的完整信息，包括名称、类型、标签和规则
    """
    name: str          # 字段名（snake_case格式）
    type_name: str     # 字段类型名（如 'string', 'int32', 'enum', 'message' 或具体类名）
    tag: int          # 字段标签（proto中的序号）
    rule: str = 'optional'  # 字段规则：'optional', 'required', 'repeated'
    
    def __str__(self) -> str:
        """字符串表示，便于调试"""
        rule_prefix = f"{self.rule} " if self.rule != 'optional' else ""
        return f"{rule_prefix}{self.type_name} {self.name} = {self.tag};"


@dataclass
class EnumValue:
    """
    Protobuf枚举值定义
    
    表示单个枚举值的名称和数字
    """
    name: str          # 枚举值名称（如 'GENDER_MALE'）
    value: int         # 枚举值数字（如 1）
    
    def __str__(self) -> str:
        """字符串表示，便于调试"""
        return f"{self.name} = {self.value};"


@dataclass
class EnumValueDefinition:
    """枚举值定义"""
    name: str       # 枚举值名称
    value: int      # 枚举值数值


@dataclass
class EnumDefinition:
    """枚举定义"""
    name: str           # 枚举名称
    package_name: str   # 包名
    full_name: str      # 完整类名
    values: List[EnumValueDefinition] = field(default_factory=list)  # 枚举值列表
    
    def __str__(self) -> str:
        """字符串表示，便于调试"""
        return f"Enum {self.name} ({len(self.values)} values)"
    
    @property
    def proto_filename(self) -> str:
        """
        获取对应的proto文件名
        
        Returns:
            proto文件名（snake_case格式）
        """
        import re
        # 将PascalCase转换为snake_case
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', self.name)
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower() + '.proto'


@dataclass  
class OneofDefinition:
    """
    Protobuf Oneof字段组定义
    
    表示一组互斥的字段，同一时间只能设置其中一个字段
    """
    name: str                                        # oneof组名称
    fields: List[FieldDefinition] = field(default_factory=list)  # 组内字段列表
    
    def __str__(self) -> str:
        """字符串表示，便于调试"""
        return f"oneof {self.name} ({len(self.fields)} fields)"


@dataclass
class MessageDefinition:
    """
    Protobuf消息定义
    
    表示完整的protobuf消息结构，包含所有字段、oneof组和元数据
    """
    name: str                                        # 消息名称（PascalCase格式）
    package_name: str                               # 包名（如 'com.example.models'）
    full_name: str                                  # 完整类名（包名.消息名）
    fields: List[FieldDefinition] = field(default_factory=list)      # 常规字段列表
    oneofs: List[OneofDefinition] = field(default_factory=list)      # oneof字段组列表
    inner_enums: List[EnumDefinition] = field(default_factory=list)  # 内部枚举列表
    
    # 原始数据（用于调试和追溯）
    info_string: Optional[str] = None               # 原始字节码字符串
    objects: List[str] = field(default_factory=list)  # 原始对象数组
    
    def __str__(self) -> str:
        """字符串表示，便于调试"""
        total_fields = len(self.fields) + sum(len(oneof.fields) for oneof in self.oneofs)
        return f"Message {self.name} ({total_fields} fields, {len(self.oneofs)} oneofs)"
    
    @property
    def proto_filename(self) -> str:
        """
        获取对应的proto文件名
        
        Returns:
            proto文件名（snake_case格式）
        """
        import re
        # 将PascalCase转换为snake_case
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', self.name)
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower() + '.proto'
    
    def get_all_field_types(self) -> List[str]:
        """
        获取所有字段的类型名列表
        
        Returns:
            所有字段类型名的列表（去重）
        """
        types = set()
        
        # 添加常规字段类型
        for field in self.fields:
            if field.type_name:
                types.add(field.type_name)
        
        # 添加oneof字段类型
        for oneof in self.oneofs:
            for field in oneof.fields:
                if field.type_name:
                    types.add(field.type_name)
        
        return list(types) 