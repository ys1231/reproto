"""
🔢 枚举解析器 - 从Java枚举类中提取Protobuf枚举定义

这个模块专门处理Java枚举类，提取枚举值和对应的数字，
生成对应的Protobuf枚举定义。
"""

import re
import os
from typing import List, Optional, Dict, Tuple

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from ..models.message_definition import EnumDefinition, EnumValueDefinition
    from ..utils.logger import get_logger
except ImportError:
    # 绝对导入（开发环境）
    from models.message_definition import EnumDefinition, EnumValueDefinition
    from utils.logger import get_logger


class EnumParser:
    """📋 Java枚举解析器"""
    
    def __init__(self, source_dir: str):
        """
        初始化枚举解析器
        
        Args:
            source_dir: Java源码根目录
        """
        self.source_dir = source_dir
        self.logger = get_logger("enum_parser")
    
    def find_enum_files(self, package_path: str) -> List[str]:
        """
        查找指定包路径下的所有枚举文件
        
        Args:
            package_path: 包路径，如 com.example.messaging.v1.models
            
        Returns:
            枚举类的完整类名列表
        """
        enum_files = []
        package_dir = os.path.join(self.source_dir, package_path.replace('.', '/'))
        
        if not os.path.exists(package_dir):
            return enum_files
            
        for file_name in os.listdir(package_dir):
            if file_name.endswith('.java'):
                file_path = os.path.join(package_dir, file_name)
                if self._is_enum_file(file_path):
                    class_name = file_name[:-5]  # 移除.java后缀
                    full_class_name = f"{package_path}.{class_name}"
                    enum_files.append(full_class_name)
        
        return enum_files
    
    def _is_enum_file(self, file_path: str) -> bool:
        """
        判断Java文件是否是枚举类 - 增强版，正确区分主类和内部类
        
        Args:
            file_path: Java文件路径
            
        Returns:
            是否为枚举类（主类是枚举，而不是包含内部枚举的消息类）
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 首先检查是否为消息类：如果包含 'extends GeneratedMessageLite'，则这是消息类
            if 'extends GeneratedMessageLite' in content:
                self.logger.debug(f"  🔍 {file_path} 包含GeneratedMessageLite，这是消息类，不是枚举")
                return False
            
            # 然后检查主类是否为枚举：查找文件开头的主类定义（跳过注释）
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                
                # 跳过注释行和空行
                if not line or line.startswith('//') or line.startswith('/*') or line.startswith('*'):
                    continue
                
                # 跳过package和import语句
                if line.startswith('package ') or line.startswith('import '):
                    continue
                
                # 查找类定义行
                if 'class ' in line or 'enum ' in line or 'interface ' in line:
                    # 检查是否为枚举类定义
                    if ('public enum ' in line or 'enum ' in line) and 'implements Internal.EnumLite' in line:
                        self.logger.debug(f"  ✅ {file_path} 主类为枚举")
                        return True
                    # 如果是类定义但不是枚举，则返回False
                    elif 'class ' in line:
                        self.logger.debug(f"  🔍 {file_path} 主类为普通类")
                        return False
            
            # 如果没有找到明确的类定义，使用原有的简单检查作为后备
            # 但要确保这确实是一个枚举文件，而不是包含内部枚举的消息类
            has_enum_features = bool(re.search(r'public\s+enum\s+\w+\s+implements\s+Internal\.EnumLite', content))
            
            if has_enum_features:
                # 进一步检查：如果同时包含消息类的特征，则不是枚举
                if ('GeneratedMessageLite' in content or 
                    'newMessageInfo(' in content or
                    'FIELD_NUMBER' in content):
                    self.logger.debug(f"  🔍 {file_path} 虽然包含枚举特征，但也包含消息类特征，判断为消息类")
                    return False
                else:
                    self.logger.debug(f"  ✅ {file_path} 包含枚举特征且无消息类特征，判断为枚举类")
                    return True
            
            return False
            
        except Exception:
            return False
    
    def parse_enum(self, enum_class_name: str) -> Optional[EnumDefinition]:
        """
        解析指定的枚举类
        
        Args:
            enum_class_name: 完整的枚举类名
            
        Returns:
            EnumDefinition对象 或 None
        """
        try:
            # 构建文件路径
            file_path = os.path.join(
                self.source_dir,
                enum_class_name.replace('.', '/') + '.java'
            )
            
            if not os.path.exists(file_path):
                return None
            
            # 读取Java文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析枚举定义
            return self._parse_enum_content(enum_class_name, content)
            
        except Exception as e:
            self.logger.error(f"❌ 解析枚举失败 {enum_class_name}: {e}")
            return None
    
    def _parse_enum_content(self, enum_class_name: str, content: str) -> Optional[EnumDefinition]:
        """
        解析Java枚举类的内容
        
        Args:
            enum_class_name: 枚举类名
            content: Java文件内容
            
        Returns:
            EnumDefinition对象
        """
        # 提取枚举名
        parts = enum_class_name.split('.')
        enum_name = parts[-1]
        package_name = '.'.join(parts[:-1])
        
        # 创建枚举定义
        enum_def = EnumDefinition(
            name=enum_name,
            package_name=package_name,
            full_name=enum_class_name
        )
        
        # 解析枚举值
        enum_values = self._extract_enum_values(content)
        enum_def.values.extend(enum_values)
        
        return enum_def
    
    def _extract_enum_values(self, content: str) -> List[EnumValueDefinition]:
        """
        从Java内容中提取枚举值
        
        Args:
            content: Java文件内容
            
        Returns:
            EnumValue列表
        """
        enum_values = []
        
        # 查找枚举声明部分 (从enum声明到第一个分号)
        enum_declaration_pattern = r'public\s+enum\s+\w+[^{]*\{([^;]*);'
        match = re.search(enum_declaration_pattern, content, re.DOTALL)
        
        if not match:
            return enum_values
        
        enum_body = match.group(1)
        
        # 解析枚举值: ENUM_NAME(value)
        enum_pattern = r'(\w+)\((\d+)\)'
        matches = re.findall(enum_pattern, enum_body)
        
        for name, value_str in matches:
            # 跳过UNRECOGNIZED
            if name == 'UNRECOGNIZED':
                continue
                
            try:
                value = int(value_str)
                enum_values.append(EnumValueDefinition(name=name, value=value))
            except ValueError:
                continue
        
        # 按值排序
        enum_values.sort(key=lambda x: x.value)
        
        return enum_values
    
    def parse_all_enums(self, package_path: str) -> List[EnumDefinition]:
        """
        解析指定包下的所有枚举类
        
        Args:
            package_path: 包路径
            
        Returns:
            EnumDefinition列表
        """
        enum_definitions = []
        
        # 查找所有枚举文件
        enum_files = self.find_enum_files(package_path)
        
        self.logger.info(f"🔍 发现 {len(enum_files)} 个枚举类...")
        
        # 解析每个枚举
        for enum_class_name in enum_files:
            enum_def = self.parse_enum(enum_class_name)
            if enum_def:
                self.logger.info(f"  ✅ 解析枚举: {enum_def.name} ({len(enum_def.values)} 个值)")
                enum_definitions.append(enum_def)
            else:
                self.logger.error(f"  ❌ 解析失败: {enum_class_name}")
        
        return enum_definitions 