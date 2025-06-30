"""
Java文件解析器

从JADX反编译的Java文件中提取Protobuf的newMessageInfo信息
解析字节码字符串和对象数组，为后续的类型解码做准备

Author: AI Assistant
"""

import re
from pathlib import Path
from typing import Optional, Tuple, List

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from ..utils.logger import get_logger
except ImportError:
    # 绝对导入（开发环境）
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
        # 格式1：GeneratedMessageLite.newMessageInfo(DEFAULT_INSTANCE, "字节码", new Object[]{对象数组})
        # 格式2：GeneratedMessageLite.newMessageInfo(DEFAULT_INSTANCE, "字节码", null)
        self.new_message_info_pattern = re.compile(
            r'GeneratedMessageLite\.newMessageInfo\(\s*'
            r'DEFAULT_INSTANCE\s*,\s*'
            r'"([^"]*)",\s*'  # 捕获字节码字符串
            r'(?:new\s+Object\[\]\s*\{([^}]*)\}|null)',  # 捕获对象数组或null
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
            
            # 查找所有newMessageInfo调用
            matches = self.new_message_info_pattern.findall(content)
            if not matches:
                return None, None
            
            # 获取主类的字段标签
            main_class_field_tags = self._extract_field_number_constants(content)
            
            # 根据字段匹配选择正确的newMessageInfo调用
            best_match = self._select_main_class_message_info(matches, main_class_field_tags)
            if not best_match:
                return None, None
            
            info_string, objects_str = best_match
            
            # 解析对象数组（允许null/空对象数组）
            if objects_str and objects_str.strip():
                objects_array = self._parse_objects_array(objects_str)
            else:
                objects_array = []  # 空消息的情况（null或空字符串）
            
            return info_string, objects_array
            
        except Exception as e:
            self.logger.error(f"❌ 解析Java文件失败 {java_file_path}: {e}")
            return None, None
    
    def parse_inner_class_from_file(self, java_file_path: Path, inner_class_name: str) -> Tuple[Optional[str], Optional[List[str]]]:
        """
        从外部类文件中解析指定的内部类的protobuf信息
        
        Args:
            java_file_path: 外部类Java文件路径
            inner_class_name: 内部类名（如"SkipRecovery"）
            
        Returns:
            Tuple[字节码字符串, 对象数组] 或 (None, None) 如果解析失败
        """
        try:
            # 读取Java文件内容
            content = java_file_path.read_text(encoding='utf-8')
            
            # 提取指定内部类的内容
            inner_class_content = self._extract_inner_class_content(content, inner_class_name)
            if not inner_class_content:
                self.logger.error(f"❌ 在文件 {java_file_path} 中找不到内部类: {inner_class_name}")
                return None, None
            
            # 在内部类内容中查找newMessageInfo调用
            matches = self.new_message_info_pattern.findall(inner_class_content)
            if not matches:
                self.logger.debug(f"  🔍 内部类 {inner_class_name} 中没有找到newMessageInfo调用")
                return None, None
            
            # 对于内部类，通常只有一个newMessageInfo调用
            info_string, objects_str = matches[0]
            
            # 解析对象数组（允许null/空对象数组）
            if objects_str and objects_str.strip():
                objects_array = self._parse_objects_array(objects_str)
            else:
                objects_array = []  # 空消息的情况（null或空字符串）
            
            # 为内部类单独提取字段标签
            self._extract_inner_class_field_tags(java_file_path, inner_class_name, inner_class_content)
            
            self.logger.info(f"  ✅ 成功解析内部类 {inner_class_name}: {len(objects_array)} 个对象")
            return info_string, objects_array
            
        except Exception as e:
            self.logger.error(f"❌ 解析内部类失败 {inner_class_name} from {java_file_path}: {e}")
            return None, None
    
    def _extract_inner_class_content(self, content: str, inner_class_name: str) -> Optional[str]:
        """
        从Java文件内容中提取指定内部类的内容
        
        Args:
            content: Java文件内容
            inner_class_name: 内部类名
            
        Returns:
            内部类的内容，如果找不到则返回None
        """
        # 查找内部类定义的开始
        # 匹配模式：public static final class InnerClassName extends ...
        class_pattern = rf'public\s+static\s+final\s+class\s+{re.escape(inner_class_name)}\s+extends\s+'
        match = re.search(class_pattern, content)
        
        if not match:
            # 尝试更宽松的匹配
            class_pattern = rf'class\s+{re.escape(inner_class_name)}\s+extends\s+'
            match = re.search(class_pattern, content)
            
        if not match:
            return None
        
        # 找到类定义的开始位置
        class_start = match.start()
        
        # 从类定义开始位置往前找到第一个'{'
        content_from_class = content[class_start:]
        brace_start = content_from_class.find('{')
        if brace_start == -1:
            return None
        
        # 从第一个'{'开始，找到匹配的'}'
        start_pos = class_start + brace_start + 1
        brace_count = 1
        pos = start_pos
        
        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1
        
        if brace_count == 0:
            # 找到了匹配的结束位置
            inner_class_content = content[start_pos:pos-1]
            return inner_class_content
        
        return None
    
    def _extract_inner_class_field_tags(self, java_file_path: Path, inner_class_name: str, inner_class_content: str) -> None:
        """
        为内部类提取字段标签，并缓存到文件系统中
        
        Args:
            java_file_path: Java文件路径
            inner_class_name: 内部类名
            inner_class_content: 内部类的源码内容
        """
        # 从内部类内容中提取字段标签
        field_tags = self._extract_field_tags_from_source(inner_class_content)
        
        if field_tags:
            # 创建内部类的虚拟文件路径，用于缓存字段标签
            # 如：Service$CompleteOnboardingRequest.java -> Service$CompleteOnboardingRequest$InstallationInfo.java
            virtual_file_path = java_file_path.parent / f"{java_file_path.stem}${inner_class_name}.java"
            
            # 将字段标签缓存到虚拟文件路径
            self._cache_field_tags(virtual_file_path, field_tags)
            
            self.logger.debug(f"  🏷️ 为内部类 {inner_class_name} 提取了 {len(field_tags)} 个字段标签")
        else:
            self.logger.debug(f"  🔍 内部类 {inner_class_name} 没有字段标签")
    
    def _cache_field_tags(self, file_path: Path, field_tags: dict) -> None:
        """
        缓存字段标签到内存中，供后续使用
        
        Args:
            file_path: 文件路径（可能是虚拟路径）
            field_tags: 字段标签字典
        """
        # 使用简单的内存缓存
        if not hasattr(self, '_field_tags_cache'):
            self._field_tags_cache = {}
        
        self._field_tags_cache[str(file_path)] = field_tags
    
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
    
    def _select_main_class_message_info(self, matches: List[tuple], main_class_field_tags: dict) -> Optional[tuple]:
        """
        根据字段匹配选择主类的newMessageInfo调用
        
        Args:
            matches: 所有newMessageInfo匹配结果 [(info_string, objects_str), ...]
            main_class_field_tags: 主类字段标签 {const_name: tag_value}
            
        Returns:
            主类的newMessageInfo匹配结果或None
        """
        if not matches:
            return None
        
        if len(matches) == 1:
            return matches[0]
        
        # 从主类字段标签生成期望的字段名列表
        expected_fields = set()
        for const_name in main_class_field_tags.keys():
            field_name = self._const_name_to_field_name(const_name)
            expected_fields.add(field_name)
        
        self.logger.debug(f"  🔍 主类期望字段: {expected_fields}")
        
        best_match = None
        best_score = 0
        
        for info_string, objects_str in matches:
            # 解析对象数组（允许null/空对象数组）
            if objects_str and objects_str.strip():
                objects_array = self._parse_objects_array(objects_str)
            else:
                objects_array = []  # 空消息的情况（null或空字符串）
            
            # 计算匹配分数
            score = self._calculate_field_match_score(objects_array, expected_fields)
            
            self.logger.debug(f"  📊 对象数组 {objects_array[:3]}... 匹配分数: {score}")
            
            if score > best_score:
                best_score = score
                best_match = (info_string, objects_str)
        
        if best_match:
            self.logger.info(f"  ✅ 选择主类newMessageInfo，匹配分数: {best_score}")
        else:
            self.logger.warning(f"  ⚠️  无法找到匹配的主类newMessageInfo")
        
        return best_match
    
    def _calculate_field_match_score(self, objects_array: List[str], expected_fields: set) -> int:
        """
        计算对象数组与期望字段的匹配分数
        
        Args:
            objects_array: 解析后的对象数组
            expected_fields: 期望的字段名集合
            
        Returns:
            匹配分数（匹配的字段数量）
        """
        if not objects_array or not expected_fields:
            return 0
        
        match_count = 0
        
        for obj in objects_array:
            # 检查是否是字段名（以_结尾的字符串）
            if obj.endswith('_'):
                if obj in expected_fields:
                    match_count += 1
            # 检查是否是类引用（不以_结尾，可能是oneof字段的类型）
            elif not obj.endswith('_'):
                # 类引用也算作有效匹配，但权重较低
                match_count += 0.5
        
        return int(match_count)
    
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
        判断是否是Protobuf枚举类 - 增强版，正确区分消息类和枚举类
        
        Args:
            content: Java文件内容
            
        Returns:
            是否为Protobuf枚举（整个文件的主类是枚举，而不是包含内部枚举的消息类）
        """
        # 首先检查是否为消息类：如果包含 'extends GeneratedMessageLite'，则这是消息类
        if 'extends GeneratedMessageLite' in content:
            self.logger.debug("  🔍 检测到GeneratedMessageLite，这是消息类，不是枚举")
            return False
        
        # 然后检查是否为枚举类：查找主类的定义
        # 查找文件开头的主类定义（跳过注释）
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
                    self.logger.debug(f"  ✅ 检测到主类为枚举: {line}")
                    return True
                # 如果是类定义但不是枚举，则返回False
                elif 'class ' in line:
                    self.logger.debug(f"  🔍 检测到主类为普通类: {line}")
                    return False
        
        # 如果没有找到明确的类定义，使用原有的简单检查作为后备
        # 但要确保这确实是一个枚举文件，而不是包含内部枚举的消息类
        has_enum_features = (
            'implements Internal.EnumLite' in content and
            'enum ' in content and
            ('forNumber(' in content or 'getNumber()' in content)
        )
        
        if has_enum_features:
            # 进一步检查：如果同时包含消息类的特征，则不是枚举
            if ('GeneratedMessageLite' in content or 
                'newMessageInfo(' in content or
                'FIELD_NUMBER' in content):
                self.logger.debug("  🔍 虽然包含枚举特征，但也包含消息类特征，判断为消息类")
                return False
            else:
                self.logger.debug("  ✅ 包含枚举特征且无消息类特征，判断为枚举类")
                return True
        
        return False
    
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

    def extract_field_tags(self, java_file_path: Path) -> Optional[dict]:
        """
        从Java文件中提取字段标签信息
        
        优先从Java源码中直接找到字段名与标签的对应关系，
        而不是依赖常量名的转换推测
        
        Args:
            java_file_path: Java文件路径
            
        Returns:
            字段标签映射 {field_name: tag} 或 None 如果解析失败
        """
        try:
            # 首先检查是否有缓存的字段标签（用于内部类）
            if hasattr(self, '_field_tags_cache'):
                cache_key = str(java_file_path)
                if cache_key in self._field_tags_cache:
                    self.logger.debug(f"  🎯 使用缓存的字段标签: {java_file_path}")
                    return self._field_tags_cache[cache_key]
            
            # 检查是否为内部类的虚拟文件路径
            # 内部类文件名模式：Package$MainClass$InnerClass.java
            file_name = java_file_path.name
            if file_name.count('$') >= 2:
                # 这是内部类的虚拟文件路径，如果缓存中没有，直接返回None
                # 因为内部类的字段标签应该已经在解析主文件时缓存了
                self.logger.debug(f"  📁 内部类虚拟文件路径，缓存中未找到字段标签: {java_file_path}")
                return None
            
            # 检查实际文件是否存在
            if not java_file_path.exists():
                self.logger.debug(f"  📁 文件不存在，跳过字段标签提取: {java_file_path}")
                return None
            
            # 读取Java文件内容
            content = java_file_path.read_text(encoding='utf-8')
            
            # 方法1：直接从源码中找到字段声明和对应的FIELD_NUMBER常量
            field_tags = self._extract_field_tags_from_source(content)
            
            if field_tags:
                return field_tags
            
            # 方法2：如果方法1失败，回退到常量名转换方法
            return self._extract_field_tags_from_constants(content)
            
        except Exception as e:
            self.logger.error(f"❌ 提取字段标签失败 {java_file_path}: {e}")
            return None
    
    def _extract_field_tags_from_source(self, content: str) -> Optional[dict]:
        """
        直接从Java源码中提取字段名和标签的对应关系
        
        通过分析实际的字段声明和常量定义来建立准确的映射
        
        Args:
            content: Java文件内容
            
        Returns:
            字段标签映射 {field_name: tag} 或 None
        """
        # 提取所有字段声明
        field_declarations = self._extract_all_field_declarations(content)
        
        # 提取所有FIELD_NUMBER常量
        field_constants = self._extract_field_number_constants(content)
        
        if not field_declarations or not field_constants:
            return None
        
        # 建立字段名到标签的映射
        field_tags = {}
        
        # 尝试通过字段名匹配找到对应的常量
        for field_name in field_declarations:
            # 生成可能的常量名
            possible_const_names = self._generate_possible_constant_names(field_name)
            
            # 查找匹配的常量
            for const_name in possible_const_names:
                if const_name in field_constants:
                    field_tags[field_name] = field_constants[const_name]
                    self.logger.debug(f"    🎯 直接匹配字段: {field_name} -> {const_name} = {field_constants[const_name]}")
                    break
        
        return field_tags if field_tags else None
    
    def _extract_all_field_declarations(self, content: str) -> List[str]:
        """
        提取所有字段声明
        
        Args:
            content: Java文件内容
            
        Returns:
            字段名列表
        """
        field_pattern = re.compile(
            r'private\s+(?:static\s+)?(?:final\s+)?'  # 访问修饰符
            r'[^\s]+(?:<[^>]*>)?(?:\[\])?'             # 类型（包括泛型和数组）
            r'\s+([a-zA-Z_][a-zA-Z0-9_]*_?)\s*[=;]',  # 字段名
            re.MULTILINE
        )
        
        field_names = []
        for match in field_pattern.finditer(content):
            field_name = match.group(1)
            # 跳过明显的常量字段（全大写）
            if not field_name.isupper() and not field_name.startswith('DEFAULT_'):
                field_names.append(field_name)
        
        return field_names
    
    def _extract_field_number_constants(self, content: str) -> dict:
        """
        提取主类的FIELD_NUMBER常量（排除内部类）
        
        Args:
            content: Java文件内容
            
        Returns:
            常量名到值的映射 {const_name: value}
        """
        # 首先找到主类的定义范围
        main_class_content = self._extract_main_class_content(content)
        
        field_tag_pattern = re.compile(
            r'\s*public\s+static\s+final\s+int\s+'  # 允许行首有空白字符
            r'([A-Z0-9_]+)_FIELD_NUMBER\s*=\s*(\d+)\s*;'  # 允许常量名包含数字
        )
        
        constants = {}
        for match in field_tag_pattern.finditer(main_class_content):
            const_name = match.group(1)
            tag_value = int(match.group(2))
            constants[const_name] = tag_value
        
        return constants
    
    def _extract_main_class_content(self, content: str) -> str:
        """
        提取主类的内容，排除内部类定义
        
        Args:
            content: Java文件内容
            
        Returns:
            主类内容（不包括内部类）
        """
        # 找到主类的开始位置
        main_class_pattern = re.compile(
            r'public\s+final\s+class\s+\w+(?:\$\w+)?\s+extends\s+GeneratedMessageLite.*?\{',
            re.DOTALL
        )
        
        main_class_match = main_class_pattern.search(content)
        if not main_class_match:
            # 如果找不到主类定义，返回整个内容作为回退
            return content
        
        main_class_start = main_class_match.end()
        
        # 找到第一个内部类的开始位置
        inner_class_pattern = re.compile(
            r'\n\s*public\s+(?:static\s+)?(?:final\s+)?class\s+\w+\s+extends\s+',
            re.MULTILINE
        )
        
        # 从主类开始位置搜索内部类
        content_from_main_class = content[main_class_start:]
        inner_class_match = inner_class_pattern.search(content_from_main_class)
        
        if inner_class_match:
            # 如果找到内部类，只返回主类部分
            inner_class_start = main_class_start + inner_class_match.start()
            main_class_content = content[:inner_class_start]
        else:
            # 如果没有内部类，返回整个内容
            main_class_content = content
        
        return main_class_content
    
    def _generate_possible_constant_names(self, field_name: str) -> List[str]:
        """
        根据字段名生成可能的常量名
        
        Args:
            field_name: 字段名（如 e164Format_, telType_）
            
        Returns:
            可能的常量名列表
        """
        # 移除末尾的下划线
        clean_name = field_name.rstrip('_')
        
        possible_names = []
        
        # 方法1：直接转换为大写
        # e164Format -> E164FORMAT
        possible_names.append(clean_name.upper())
        
        # 方法2：在camelCase边界添加下划线
        # e164Format -> E164_FORMAT
        camel_to_snake = re.sub('([a-z0-9])([A-Z])', r'\1_\2', clean_name).upper()
        possible_names.append(camel_to_snake)
        
        # 方法3：处理数字和字母的边界
        # e164Format -> E_164_FORMAT
        with_number_boundaries = re.sub('([a-zA-Z])([0-9])', r'\1_\2', clean_name)
        with_number_boundaries = re.sub('([0-9])([a-zA-Z])', r'\1_\2', with_number_boundaries)
        with_number_boundaries = re.sub('([a-z])([A-Z])', r'\1_\2', with_number_boundaries).upper()
        possible_names.append(with_number_boundaries)
        
        return list(set(possible_names))  # 去重
    
    def _extract_field_tags_from_constants(self, content: str) -> Optional[dict]:
        """
        从常量定义中提取字段标签（回退方法）
        
        Args:
            content: Java文件内容
            
        Returns:
            字段标签映射 {field_name: tag} 或 None
        """
        # 匹配字段标签常量定义
        field_tag_pattern = re.compile(
            r'\s*public\s+static\s+final\s+int\s+'  # 允许行首有空白字符
            r'([A-Z0-9_]+)_FIELD_NUMBER\s*=\s*(\d+)\s*;'  # 允许常量名包含数字
        )
        
        field_tags = {}
        
        # 查找所有字段标签定义
        for match in field_tag_pattern.finditer(content):
            field_const_name = match.group(1)  # 如 TEXT, ISFINAL
            tag_value = int(match.group(2))     # 如 1, 2
            
            # 转换常量名为字段名
            field_name = self._const_name_to_field_name(field_const_name)
            field_tags[field_name] = tag_value
            
            self.logger.debug(f"    🔄 回退转换字段标签: {field_name} = {tag_value}")
        
        return field_tags if field_tags else None
    
    def _const_name_to_field_name(self, const_name: str) -> str:
        """
        将常量名转换为字段名（通用算法，无硬编码）
        
        Args:
            const_name: 常量名（如 TEXT, ISFINAL, PAYLOADTYPE, E164_FORMAT）
            
        Returns:
            字段名（如 text_, isFinal_, payloadType_, e164Format_）
        """
        # 通用转换算法：将UPPER_CASE转换为camelCase
        if '_' in const_name:
            # 处理下划线分隔的常量名：E164_FORMAT -> e164Format
            parts = const_name.lower().split('_')
            field_name = parts[0] + ''.join(word.capitalize() for word in parts[1:])
        else:
            # 处理单个单词的常量名：TEXT -> text
            # 处理复合词常量名：ISFINAL -> isFinal, PAYLOADTYPE -> payloadType
            field_name = self._split_compound_word(const_name)
        
        return field_name + '_'
    
    def _split_compound_word(self, word: str) -> str:
        """
        智能分割复合词并转换为camelCase
        
        Args:
            word: 大写复合词（如 ISFINAL, PAYLOADTYPE, USERID）
            
        Returns:
            camelCase格式的字段名（如 isFinal, payloadType, userId）
        """
        # 将单词转换为小写
        word_lower = word.lower()
        
        # 使用启发式规则分割复合词
        # 这些是常见的英语词汇模式，无需硬编码特定应用的词汇
        common_prefixes = ['is', 'has', 'can', 'should', 'will', 'get', 'set']
        common_suffixes = ['type', 'id', 'code', 'number', 'name', 'data', 'info', 'status', 'mode', 'format']
        
        # 检查前缀模式
        for prefix in common_prefixes:
            if word_lower.startswith(prefix) and len(word_lower) > len(prefix):
                rest = word_lower[len(prefix):]
                return prefix + rest.capitalize()
        
        # 检查后缀模式
        for suffix in common_suffixes:
            if word_lower.endswith(suffix) and len(word_lower) > len(suffix):
                prefix_part = word_lower[:-len(suffix)]
                return prefix_part + suffix.capitalize()
        
        # 如果没有匹配的模式，尝试基于常见的英语单词边界进行分割
        # 这里可以使用更复杂的NLP技术，但为了保持简单，使用基本的启发式
        
        # 检查常见的双词组合模式
        if len(word_lower) >= 6:
            # 尝试在中间位置分割
            mid_point = len(word_lower) // 2
            for i in range(max(3, mid_point - 2), min(len(word_lower) - 2, mid_point + 3)):
                first_part = word_lower[:i]
                second_part = word_lower[i:]
                
                # 检查是否是合理的分割（基于常见英语单词长度）
                if (3 <= len(first_part) <= 8 and 3 <= len(second_part) <= 8 and
                    not first_part.endswith(second_part[:2]) and  # 避免重复
                    not second_part.startswith(first_part[-2:])):  # 避免重复
                    return first_part + second_part.capitalize()
        
        # 如果无法智能分割，直接返回小写形式
        return word_lower 