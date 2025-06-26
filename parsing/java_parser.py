"""
Java文件解析器

从JADX反编译的Java文件中提取Protobuf的newMessageInfo信息
解析字节码字符串和对象数组，为后续的类型解码做准备

Author: AI Assistant
"""

import re
from pathlib import Path
from typing import Optional, Tuple, List

from utils.logger import get_logger


class JavaParser:
    """
    Java文件解析器
    
    专门解析包含Google Protobuf Lite的newMessageInfo调用的Java文件
    提取其中的字节码字符串和对象数组信息
    """
    
    def __init__(self):
        """初始化解析器，编译正则表达式模式"""
        self.logger = get_logger("java_parser")
        
        # 匹配newMessageInfo调用的正则表达式
        # 格式：GeneratedMessageLite.newMessageInfo(DEFAULT_INSTANCE, "字节码", new Object[]{对象数组})
        self.new_message_info_pattern = re.compile(
            r'GeneratedMessageLite\.newMessageInfo\(\s*'
            r'DEFAULT_INSTANCE\s*,\s*'
            r'"([^"]*)",\s*'  # 捕获字节码字符串
            r'new\s+Object\[\]\s*\{([^}]*)\}',  # 捕获对象数组
            re.DOTALL
        )
    
    def parse_java_file(self, java_file_path: Path) -> Tuple[Optional[str], Optional[List[str]]]:
        """
        解析Java文件，提取newMessageInfo中的关键信息
        
        Args:
            java_file_path: Java文件路径
            
        Returns:
            Tuple[字节码字符串, 对象数组] 或 (None, None) 如果解析失败
        """
        try:
            # 读取Java文件内容
            content = java_file_path.read_text(encoding='utf-8')
            
            # 查找newMessageInfo调用
            match = self.new_message_info_pattern.search(content)
            if not match:
                return None, None
            
            # 提取字节码字符串和对象数组字符串
            info_string = match.group(1)
            objects_str = match.group(2)
            
            # 解析对象数组
            objects_array = self._parse_objects_array(objects_str)
            
            return info_string, objects_array
            
        except Exception as e:
            self.logger.error(f"❌ 解析Java文件失败 {java_file_path}: {e}")
            return None, None
    
    def _parse_objects_array(self, objects_str: str) -> List[str]:
        """
        解析Java对象数组字符串
        
        处理复杂的Java对象数组语法，包括：
        - 字符串字面量（带引号）
        - 类引用（如ContactPhone.class）
        - 嵌套的括号和逗号分隔
        
        Args:
            objects_str: 对象数组的字符串表示
            
        Returns:
            解析后的对象列表
        """
        objects = []
        
        # 预处理：清理空白字符
        objects_str = objects_str.strip()
        if not objects_str:
            return objects
        
        # 智能分割：处理嵌套括号和字符串
        parts = self._smart_split(objects_str)
        
        # 后处理：清理和标准化每个对象
        for part in parts:
            cleaned_part = self._clean_object_part(part)
            if cleaned_part:
                objects.append(cleaned_part)
        
        return objects
    
    def _smart_split(self, text: str) -> List[str]:
        """
        智能分割字符串，正确处理嵌套括号和字符串字面量
        
        Args:
            text: 要分割的文本
            
        Returns:
            分割后的部分列表
        """
        parts = []
        current_part = ""
        paren_count = 0
        in_string = False
        escape_next = False
        
        for char in text:
            # 处理转义字符
            if escape_next:
                current_part += char
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                current_part += char
                continue
            
            # 处理字符串字面量
            if char == '"' and not escape_next:
                in_string = not in_string
                current_part += char
                continue
                
            if in_string:
                current_part += char
                continue
            
            # 处理括号嵌套
            if char in '([{':
                paren_count += 1
                current_part += char
            elif char in ')]}':
                paren_count -= 1
                current_part += char
            elif char == ',' and paren_count == 0:
                # 顶层逗号，分割点
                parts.append(current_part.strip())
                current_part = ""
            else:
                current_part += char
        
        # 添加最后一部分
        if current_part.strip():
            parts.append(current_part.strip())
        
        return parts
    
    def _clean_object_part(self, part: str) -> Optional[str]:
        """
        清理和标准化对象部分
        
        Args:
            part: 原始对象字符串
            
        Returns:
            清理后的对象字符串，如果无效则返回None
        """
        part = part.strip()
        if not part:
            return None
        
        # 移除字符串字面量的引号
        if part.startswith('"') and part.endswith('"'):
            part = part[1:-1]
        
        # 处理类引用：ContactPhone.class -> ContactPhone
        if part.endswith('.class'):
            part = part[:-6]
        
        return part if part else None
    
    def parse_enum_file(self, java_file_path: Path) -> Optional[List[tuple]]:
        """
        解析Java枚举文件，提取枚举值和数值
        
        Args:
            java_file_path: Java文件路径
            
        Returns:
            枚举值列表 [(name, value), ...] 或 None 如果解析失败
        """
        try:
            # 读取Java文件内容
            content = java_file_path.read_text(encoding='utf-8')
            
            # 检查是否是Protobuf枚举类
            if not self._is_protobuf_enum(content):
                return None
            
            # 提取枚举值
            enum_values = self._extract_enum_values(content)
            
            return enum_values if enum_values else None
            
        except Exception as e:
            self.logger.error(f"❌ 解析枚举文件失败 {java_file_path}: {e}")
            return None
    
    def _is_protobuf_enum(self, content: str) -> bool:
        """
        判断是否是Protobuf枚举类
        
        Args:
            content: Java文件内容
            
        Returns:
            是否为Protobuf枚举
        """
        # 检查关键特征
        return (
            'implements Internal.EnumLite' in content and
            'enum ' in content and
            'forNumber(' in content
        )
    
    def _extract_enum_values(self, content: str) -> List[tuple]:
        """
        从Java枚举类中提取枚举值和数值
        
        Args:
            content: Java文件内容
            
        Returns:
            枚举值列表 [(name, value), ...]
        """
        enum_values = []
        
        # 正则表达式匹配枚举定义
        # 例如：UNKNOWN(0), SUCCESS(1), INTERNAL_ERROR(2)
        enum_pattern = re.compile(r'(\w+)\((\d+)\)')
        
        matches = enum_pattern.findall(content)
        
        for name, value in matches:
            # 跳过UNRECOGNIZED枚举值（通常值为-1）
            if name != 'UNRECOGNIZED':
                enum_values.append((name, int(value)))
        
        # 按数值排序
        enum_values.sort(key=lambda x: x[1])
        
        return enum_values

    def get_raw_field_type(self, java_file_path: Path, field_name_raw: str) -> Optional[str]:
        """
        从Java文件中获取指定字段的原始类型
        
        Args:
            java_file_path: Java文件路径
            field_name_raw: 原始字段名（如 latitude_）
            
        Returns:
            字段的Java原始类型，如果找不到则返回None
        """
        try:
            # 读取Java文件内容
            content = java_file_path.read_text(encoding='utf-8')
            
            # 查找字段声明
            field_type = self._extract_field_type_from_content(content, field_name_raw)
            return field_type
            
        except Exception as e:
            self.logger.debug(f"获取字段类型失败 {java_file_path} - {field_name_raw}: {e}")
            return None
    
    def _extract_field_type_from_content(self, content: str, field_name_raw: str) -> Optional[str]:
        """
        从Java文件内容中提取指定字段的类型
        
        Args:
            content: Java文件内容
            field_name_raw: 原始字段名（如 latitude_）
            
        Returns:
            字段的Java类型，如果找不到则返回None
        """
        # 构建字段声明的正则表达式模式
        # 匹配: private Type fieldName_ = ...;
        # 或: private Type fieldName_;
        
        # 转义字段名中的特殊字符
        escaped_field_name = re.escape(field_name_raw)
        
        # 字段声明模式
        patterns = [
            # 标准字段声明: private Type fieldName_ = value;
            rf'private\s+([^\s]+(?:<[^>]*>)?(?:\[\])?)\s+{escaped_field_name}\s*=',
            # 简单字段声明: private Type fieldName_;
            rf'private\s+([^\s]+(?:<[^>]*>)?(?:\[\])?)\s+{escaped_field_name}\s*;',
            # 其他访问修饰符
            rf'(?:public|protected|package)\s+([^\s]+(?:<[^>]*>)?(?:\[\])?)\s+{escaped_field_name}\s*[=;]',
            # 无访问修饰符
            rf'([^\s]+(?:<[^>]*>)?(?:\[\])?)\s+{escaped_field_name}\s*[=;]',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                field_type = match.group(1).strip()
                
                # 清理类型字符串
                cleaned_type = self._clean_field_type(field_type)
                if cleaned_type:
                    self.logger.debug(f"找到字段类型: {field_name_raw} -> {cleaned_type}")
                    return cleaned_type
        
        self.logger.debug(f"未找到字段类型: {field_name_raw}")
        return None
    
    def _clean_field_type(self, field_type: str) -> Optional[str]:
        """
        清理和标准化字段类型字符串
        
        Args:
            field_type: 原始字段类型字符串
            
        Returns:
            清理后的字段类型，如果无效则返回None
        """
        if not field_type:
            return None
        
        # 移除多余的空白字符
        field_type = field_type.strip()
        
        # 跳过明显不是类型的字符串
        if field_type in ['private', 'public', 'protected', 'static', 'final', 'volatile', 'transient']:
            return None
        
        # 处理泛型类型，保留完整的泛型信息
        # 例如: MapFieldLite<String, Contact> 保持不变
        
        # 处理数组类型
        # 例如: String[] 保持不变
        
        # 处理完全限定类名，提取简单类名
        if '.' in field_type and not field_type.startswith('java.'):
            # 对于非java包的类，保留完整路径以便后续处理
            pass
        
        return field_type 