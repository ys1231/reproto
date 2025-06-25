from dataclasses import dataclass, field
from typing import List, Dict, Set

@dataclass
class FieldDefinition:
    """表示一个 Protobuf 消息中的字段。"""
    name: str
    type: str
    tag: int
    rule: str # "optional", "repeated", or "oneof"

@dataclass
class OneofDefinition:
    """表示一个 Protobuf oneof 块。"""
    name: str
    fields: List[FieldDefinition] = field(default_factory=list)

@dataclass
class MessageDefinition:
    """表示一个完整的 Protobuf 消息的定义。"""
    name: str
    package: str
    info_string: str = ""
    objects: List[str] = field(default_factory=list)
    fields: List[FieldDefinition] = field(default_factory=list)
    oneofs: Dict[str, OneofDefinition] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set) 