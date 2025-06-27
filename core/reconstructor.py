"""
Protobuf重构器 - 主协调器

负责管理整个重构过程：
1. 任务队列管理和依赖发现
2. Java文件解析和字节码解码
3. Proto文件生成和输出

Author: AI Assistant
"""

import re
import os
from pathlib import Path
from collections import deque
from typing import Set, Dict, List, Optional, Tuple

from parsing.java_parser import JavaParser
from parsing.enum_parser import EnumParser
from core.info_decoder import InfoDecoder
from generation.proto_generator import ProtoGenerator
from models.message_definition import MessageDefinition, EnumDefinition, EnumValueDefinition
from utils.logger import get_logger
from utils.file_cache import get_file_cache
from utils.type_utils import type_mapper, naming_converter


class JavaSourceAnalyzer:
    """Java源码分析器，用于从源码中获取真实的字段类型"""
    
    def __init__(self, sources_dir: Path):
        self.sources_dir = sources_dir
        self._current_class_content = None
        self._current_class_name = None
        # 初始化JavaParser用于字段类型解析
        self.java_parser = JavaParser()
        # 使用文件缓存系统优化I/O性能
        self.file_cache = get_file_cache()
    
    def set_current_class(self, class_name: str):
        """设置当前分析的类"""
        self._current_class_name = class_name
        self._current_class_content = self._load_class_content(class_name)
    
    def get_raw_field_type(self, field_name_raw: str) -> Optional[str]:
        """
        获取字段的原始Java类型
        
        Args:
            field_name_raw: 原始字段名（如 latitude_）
            
        Returns:
            字段的Java原始类型，如果找不到则返回None
        """
        if not self._current_class_name:
            return None
        
        # 构建Java文件路径
        file_path = self._current_class_name.replace('.', '/') + '.java'
        java_file_path = self.sources_dir / file_path
        
        if not java_file_path.exists():
            return None
        
        # 使用JavaParser获取字段类型
        return self.java_parser.get_raw_field_type(java_file_path, field_name_raw)
    
    def get_field_type(self, field_name_raw: str, expected_type: str) -> Optional[str]:
        """
        从Java源码中获取字段的真实类型
        
        Args:
            field_name_raw: 原始字段名（如 contacts_）
            expected_type: 期望的基础类型（message、enum 或 map）
            
        Returns:
            真实的类型名，如果无法获取则返回None
        """
        if not self._current_class_content:
            return None
        
        # 清理字段名
        field_name = field_name_raw.rstrip('_')
        
        # 查找字段声明模式，支持多种声明格式
        patterns = [
            # Internal.ProtobufList<Contact> contacts_ = ...
            rf'private\s+Internal\.ProtobufList<([^>]+)>\s+{re.escape(field_name)}_\s*=',
            # MapFieldLite<String, Contact> contacts_ = ...
            rf'private\s+MapFieldLite<([^,]+),\s*([^>]+)>\s+{re.escape(field_name)}_\s*=',
            # List<Contact> contacts_ = ...
            rf'private\s+List<([^>]+)>\s+{re.escape(field_name)}_\s*=',
            # Internal.IntList badges_ = ... (用于枚举列表)
            rf'private\s+(Internal\.IntList)\s+{re.escape(field_name)}_\s*=',
            # 普通字段声明: private Contact contact_ = ...
            rf'private\s+(\w+(?:\.\w+)*)\s+{re.escape(field_name)}_\s*=',
            # 简单字段声明: private Contact contact_;
            rf'private\s+(\w+(?:\.\w+)*)\s+{re.escape(field_name)}_\s*;'
        ]
        
        for i, pattern in enumerate(patterns):
            matches = re.findall(pattern, self._current_class_content)
            if matches:
                if i == 0:  # Internal.ProtobufList<Contact>
                    element_type = matches[0]
                    return f"Internal.ProtobufList<{element_type}>"
                elif i == 1:  # MapFieldLite<String, Contact>
                    key_type, value_type = matches[0]
                    return f"MapFieldLite<{key_type.strip()}, {value_type.strip()}>"
                elif i == 2:  # List<Contact>
                    element_type = matches[0]
                    return f"List<{element_type}>"
                elif i == 3:  # Internal.IntList
                    return "Internal.IntList"
                else:  # 普通类型
                    simple_type = matches[0]
                    
                    # 检查是否为Java基础类型，如果是则直接返回
                    basic_java_types = {
                        'int', 'long', 'float', 'double', 'boolean', 'byte', 'short', 'char',
                        'String', 'Object', 'Integer', 'Long', 'Float', 'Double', 'Boolean',
                        'Byte', 'Short', 'Character'
                    }
                    
                    if simple_type in basic_java_types:
                        return simple_type  # 直接返回基础类型，不添加包名
                    
                    # 如果字段声明是基础类型（如int），但期望类型是enum，尝试从setter方法获取真实类型
                    if expected_type == 'enum' and simple_type in ['int', 'long', 'short', 'byte']:
                        setter_type = self._get_type_from_setter(field_name)
                        if setter_type:
                            return setter_type
                        continue
                    
                    # 特殊处理：Internal.IntList可能对应枚举列表
                    if simple_type == 'Internal.IntList':
                        # 检查是否有对应的枚举setter方法
                        enum_type = self._get_enum_type_from_list_setter(field_name)
                        if enum_type:
                            return f"Internal.ProtobufList<{enum_type}>"
                    
                    # 查找import语句获取完整类名
                    import_pattern = rf'import\s+([^;]*\.{re.escape(simple_type)});'
                    import_matches = re.findall(import_pattern, self._current_class_content)
                    
                    if import_matches:
                        return import_matches[0]  # 返回完整的包名.类名
                    else:
                        # 如果没有import，假设在同一个包中
                        if self._current_class_name:
                            package_name = '.'.join(self._current_class_name.split('.')[:-1])
                            return f"{package_name}.{simple_type}"
        
        return None
    
    def _get_map_type_from_field(self, field_name: str) -> Optional[str]:
        """
        从MapFieldLite字段声明中获取map的键值类型
        
        Args:
            field_name: 字段名（如 contacts）
            
        Returns:
            map类型字符串，如 "map<string, Contact>"
        """
        # 查找MapFieldLite字段声明：private MapFieldLite<String, Contact> contacts_ = ...
        pattern = rf'private\s+MapFieldLite<([^,]+),\s*([^>]+)>\s+{re.escape(field_name)}_\s*='
        matches = re.findall(pattern, self._current_class_content)
        
        if matches:
            key_type, value_type = matches[0]
            key_type = key_type.strip()
            value_type = value_type.strip()
            
            # 转换Java类型到protobuf类型
            proto_key_type = self._java_type_to_proto_type(key_type)
            proto_value_type = self._java_type_to_proto_type(value_type)
            
            return f"map<{proto_key_type}, {proto_value_type}>"
        
        return None
    
    def _java_type_to_proto_type(self, java_type: str) -> str:
        """
        将Java类型转换为protobuf类型
        
        Args:
            java_type: Java类型名
            
        Returns:
            对应的protobuf类型名
        """
        return type_mapper.java_to_proto_type(java_type)

    def _get_type_from_setter(self, field_name: str) -> Optional[str]:
        """
        从setter方法中获取字段的真实类型（特别适用于枚举类型）
        
        Args:
            field_name: 字段名（如 spamType）
            
        Returns:
            真实的类型名
        """
        # 将字段名转换为setter方法名
        setter_name = f"set{field_name[0].upper()}{field_name[1:]}"
        
        # 查找私有setter方法：/* JADX INFO: Access modifiers changed from: private */ 
        # public void setSpamType(SpamType spamType)
        patterns = [
            # 查找setter方法签名，支持public或private
            rf'(?:public|private)\s+void\s+{re.escape(setter_name)}\s*\(\s*(\w+)\s+\w+\s*\)',
            # 也支持注释中的private标记
            rf'\/\*[^*]*private[^*]*\*\/\s*(?:public|private)\s+void\s+{re.escape(setter_name)}\s*\(\s*(\w+)\s+\w+\s*\)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, self._current_class_content, re.DOTALL)
            if matches:
                simple_type = matches[0]
                
                # 查找import语句获取完整类名
                import_pattern = rf'import\s+([^;]*\.{re.escape(simple_type)});'
                import_matches = re.findall(import_pattern, self._current_class_content)
                
                if import_matches:
                    return import_matches[0]
                else:
                    # 如果没有import，假设在同一个包中
                    if self._current_class_name:
                        package_name = '.'.join(self._current_class_name.split('.')[:-1])
                        return f"{package_name}.{simple_type}"
        
        return None
    
    def _get_enum_type_from_list_setter(self, field_name: str) -> Optional[str]:
        """
        从列表setter方法中获取枚举类型（如setBadges(int i10, Badge badge)）
        
        Args:
            field_name: 字段名（如 badges）
            
        Returns:
            枚举类型名
        """
        # 将字段名转换为setter方法名
        setter_name = f"set{field_name[0].upper()}{field_name[1:]}"
        
        # 查找列表setter方法：setBadges(int i10, Badge badge)
        pattern = rf'(?:public|private)\s+void\s+{re.escape(setter_name)}\s*\(\s*int\s+\w+,\s*(\w+)\s+\w+\s*\)'
        matches = re.findall(pattern, self._current_class_content)
        
        if matches:
            simple_type = matches[0]
            
            # 查找import语句获取完整类名
            import_pattern = rf'import\s+([^;]*\.{re.escape(simple_type)});'
            import_matches = re.findall(import_pattern, self._current_class_content)
            
            if import_matches:
                return import_matches[0]
            else:
                # 如果没有import，假设在同一个包中
                if self._current_class_name:
                    package_name = '.'.join(self._current_class_name.split('.')[:-1])
                    return f"{package_name}.{simple_type}"
        
        return None
    
    def _load_class_content(self, class_name: str) -> Optional[str]:
        """加载类的源码内容（使用缓存优化）"""
        try:
            # 标准路径：com.example.Model -> com/example/Model.java
            file_path = class_name.replace('.', '/') + '.java'
            full_path = self.sources_dir / file_path
            
            # 使用缓存系统获取文件内容
            content = self.file_cache.get_content(full_path)
            if content:
                return content
            
            # 备选方案：按简单类名搜索
            simple_name = class_name.split('.')[-1]
            for java_file in self.sources_dir.rglob(f"{simple_name}.java"):
                return self.file_cache.get_content(java_file)
            
            return None
        except Exception:
            return None


class ProtoReconstructor:
    """
    Protobuf重构器主类
    
    协调整个从Java字节码到Proto文件的重构过程，包括：
    - 依赖发现和任务调度
    - 文件解析和类型解码
    - Proto文件生成和输出
    """
    
    def __init__(self, sources_dir: Path, output_dir: Path):
        """
        初始化重构器
        
        Args:
            sources_dir: JADX反编译的Java源码目录
            output_dir: Proto文件输出目录
        """
        self.sources_dir = sources_dir
        self.output_dir = output_dir
        self.logger = get_logger("reconstructor")
        
        # 初始化核心组件
        self.java_parser = JavaParser()      # Java文件解析器
        self.enum_parser = EnumParser(str(sources_dir))  # 枚举解析器需要字符串路径
        self.info_decoder = InfoDecoder()
        self.proto_generator = ProtoGenerator()  # Proto文件生成器
        
        # 初始化Java源码分析器
        self.java_source_analyzer = JavaSourceAnalyzer(sources_dir)
        self.info_decoder.java_source_analyzer = self.java_source_analyzer
        
        # 🚀 性能优化：移除未使用的索引系统，简化代码
        # 索引系统在实际使用中被基础类型检测绕过，且构建耗时
        # 改为使用直接的文件路径构造和智能包名推断
        
        # 任务调度状态
        self.processed_classes: Set[str] = set()  # 已处理的类
        self.pending_classes: deque = deque()     # 待处理的类队列
        self.message_definitions: Dict[str, MessageDefinition] = {}  # 消息定义
        self.enum_definitions: Dict[str, EnumDefinition] = {}        # 枚举定义
        
        # 错误和状态跟踪
        self.failed_classes: Dict[str, str] = {}  # 失败的类 -> 失败原因
        self.skipped_classes: Dict[str, str] = {}  # 跳过的类 -> 跳过原因
        
        # 当前处理的类名（用于调试）
        self._current_processing_class = None
        
    def reconstruct_from_root(self, root_class: str) -> Dict[str, any]:
        """
        从根类开始重构protobuf定义
        
        Args:
            root_class: 根类的完整名称
            
        Returns:
            包含统计信息的字典
        """
        self.logger.info(f"🚀 开始重构，根类: {root_class}")
        
        # 1. 添加根类到处理队列
        self.pending_classes.append(root_class)
        
        # 2. 处理所有消息类
        self._process_all_classes()
        
        # 3. 解析所有枚举类
        self._process_all_enums()
        
        # 4. 生成proto文件
        self._generate_all_proto_files()
        
        # 5. 输出性能统计信息
        from utils.file_cache import get_file_cache
        file_cache = get_file_cache()
        file_cache.print_stats()
        
        # 🚀 性能优化：索引系统已移除，无需统计
        
        # 6. 返回统计信息
        # 报告未知类型统计
        self._report_unknown_types()
        
        # 返回处理结果
        results = {}
        for class_name, message_def in self.message_definitions.items():
            results[class_name] = message_def
        for class_name, enum_def in self.enum_definitions.items():
            results[class_name] = enum_def
            
        return results
        
    def _process_all_classes(self) -> None:
        """处理队列中的所有类，自动发现并添加依赖类"""
        while self.pending_classes:
            class_name = self.pending_classes.popleft()
            
            if class_name in self.processed_classes:
                continue
                
            self.logger.info(f"处理类: {class_name}")
            self._process_single_class(class_name)
            
    def _process_all_enums(self) -> None:
        """解析目标包下的所有枚举类"""
        self.logger.info("🔢 开始解析枚举类...")
        
        # 从已处理的类中推断目标包名
        target_package = None
        if self.message_definitions:
            # 取第一个消息定义的包名
            first_message = next(iter(self.message_definitions.values()))
            target_package = first_message.package_name
        elif self.processed_classes:
            # 从已处理的类名中推断包名
            first_class = next(iter(self.processed_classes))
            target_package = '.'.join(first_class.split('.')[:-1])
        
        if not target_package:
            self.logger.warning("⚠️  无法推断目标包名，跳过枚举解析")
            return
        
        # 解析目标包下的所有枚举
        enum_definitions = self.enum_parser.parse_all_enums(target_package)
        
        # 存储枚举定义
        for enum_def in enum_definitions:
            self.enum_definitions[enum_def.full_name] = enum_def
            self.logger.info(f"  ✅ 解析枚举: {enum_def.name} ({len(enum_def.values)} 个值)")
        
        self.logger.info(f"📊 枚举解析完成，共解析 {len(enum_definitions)} 个枚举")
            
    def _process_single_class(self, class_name: str) -> None:
        """
        处理单个Java类
        
        Args:
            class_name: 完整的Java类名
        """
        # 设置当前处理的类名，用于源码分析
        self._current_processing_class = class_name
        # 设置Java源码分析器的当前类
        self.java_source_analyzer.set_current_class(class_name)
        
        try:
            # 检查是否应该跳过这个类
            if self._should_skip_class(class_name):
                skip_reason = self._get_skip_reason(class_name)
                self.skipped_classes[class_name] = skip_reason
                self.logger.info(f"  ⏭️  跳过类: {class_name} ({skip_reason})")
                return
            
            # 1. 查找Java文件
            java_file_path = self._find_java_file(class_name)
            if not java_file_path:
                error_msg = "找不到对应的Java文件"
                self.failed_classes[class_name] = error_msg
                self.logger.warning(f"  ❌ {error_msg}: {class_name}")
                return
            
            # 2. 尝试解析为枚举
            enum_values = self.java_parser.parse_enum_file(java_file_path)
            if enum_values:
                # 这是一个枚举类
                enum_def = self._create_enum_definition(class_name, enum_values)
                self.enum_definitions[class_name] = enum_def
                self.logger.info(f"  ✅ 成功解析枚举: {len(enum_def.values)} 个值")
                return
            
            # 3. 尝试解析为消息类
            info_string, objects_array = self.java_parser.parse_java_file(java_file_path)
            if not info_string:
                error_msg = "无法从Java文件中提取protobuf信息"
                self.failed_classes[class_name] = error_msg
                self.logger.warning(f"  ❌ {error_msg}: {class_name}")
                return
            
            # 4. 解码字节码为消息定义
            message_def = self.info_decoder.decode_message_info(
                class_name, info_string, objects_array, java_file_path
            )
            
            if message_def:
                self.message_definitions[class_name] = message_def
                self.logger.info(f"  ✅ 成功解析消息: {len(message_def.fields)} 个字段")
                
                # 5. 发现并添加依赖类到队列
                self._discover_dependencies(message_def)
            else:
                error_msg = "字节码解码失败，可能不是protobuf消息类"
                self.failed_classes[class_name] = error_msg
                self.logger.warning(f"  ❌ {error_msg}: {class_name}")
                
        except Exception as e:
            error_msg = f"处理异常: {str(e)}"
            self.failed_classes[class_name] = error_msg
            self.logger.error(f"  ❌ {error_msg}: {class_name}")
            if hasattr(self, '_verbose') and self._verbose:
                self.logger.exception(f"详细异常信息 ({class_name}):")
        finally:
            # 无论成功失败都标记为已处理，避免无限循环
            self.processed_classes.add(class_name)
            # 清理当前处理的类名
            self._current_processing_class = None
            
    def _discover_dependencies(self, message_def: MessageDefinition) -> None:
        """
        发现消息定义中的依赖类并添加到处理队列
        
        Args:
            message_def: 消息定义对象
        """
        dependencies = self._extract_dependencies(message_def)
        for dep in dependencies:
            if dep not in self.processed_classes:
                self.pending_classes.append(dep)
                self.logger.info(f"  🔗 发现依赖: {dep}")
                
        # 处理枚举依赖
        self.logger.info(f"  🔍 开始处理枚举依赖...")
        enum_count = 0
        for field in message_def.fields:
            if self._is_enum_type(field.type_name):
                self.logger.info(f"  🔢 发现枚举字段: {field.name} -> {field.type_name}")
                self._process_enum_dependency(field.type_name)
                enum_count += 1
        
        if enum_count == 0:
            self.logger.info(f"  📊 未发现枚举依赖")
                
    def _extract_dependencies(self, message_def: MessageDefinition) -> List[str]:
        """
        从消息定义中提取所有依赖的类名
        
        Args:
            message_def: 消息定义对象
            
        Returns:
            依赖类名列表
        """
        dependencies = []
        
        # 从常规字段提取依赖
        for field in message_def.fields:
            deps = self._extract_field_dependencies(field.type_name, message_def.package_name)
            dependencies.extend(deps)
        
        # 从oneof字段提取依赖
        for oneof in message_def.oneofs:
            for field in oneof.fields:
                deps = self._extract_field_dependencies(field.type_name, message_def.package_name)
                dependencies.extend(deps)
        
        # 去重
        return list(set(dependencies))
    
    def _extract_field_dependencies(self, type_name: str, current_package: str) -> List[str]:
        """
        从字段类型中提取所有依赖（包括map类型的键值类型和枚举类型）
        
        Args:
            type_name: 字段类型名
            current_package: 当前包名
            
        Returns:
            依赖类名列表
        """
        dependencies = []
        
        if not type_name:
            return dependencies
            
        # 处理map类型: map<string, Contact> -> [Contact]
        if type_name.startswith('map<') and type_name.endswith('>'):
            map_content = type_name[4:-1]  # 移除 'map<' 和 '>'
            # 分割键值类型，处理嵌套的尖括号
            key_type, value_type = self._parse_map_types(map_content)
            
            # 递归处理键类型和值类型
            dependencies.extend(self._extract_field_dependencies(key_type, current_package))
            dependencies.extend(self._extract_field_dependencies(value_type, current_package))
            
        # 处理普通类型
        else:
            # 检查是否为枚举类型（以Enum开头或已知的枚举模式）
            if self._is_enum_type(type_name):
                # 直接处理枚举类型，尝试解析并添加到枚举定义中
                self._process_enum_dependency(type_name)
            else:
                # 处理消息类型依赖
                dep = self._resolve_field_dependency(type_name, current_package)
                if dep:
                    dependencies.append(dep)
        
        return dependencies
    
    def _is_enum_type(self, type_name: str) -> bool:
        """
        判断类型名是否为枚举类型
        
        Args:
            type_name: 类型名
            
        Returns:
            是否为枚举类型
        """
        # 检查是否以Enum开头（混淆后的枚举名）
        if type_name.startswith('Enum'):
            return True
        
        # 检查是否在已知的枚举类型列表中
        # 这里可以添加更多的枚举类型判断逻辑
        return False
    
    def _process_enum_dependency(self, type_name: str) -> None:
        """
        处理枚举依赖，查找并解析枚举类
        
        Args:
            type_name: 枚举类型名
        """
        try:
            self.logger.info(f"    🔍 搜索枚举文件: {type_name}")
            # 尝试在所有包中查找这个枚举类
            enum_file_path = self._find_enum_file(type_name)
            if enum_file_path:
                self.logger.info(f"    ✅ 找到枚举文件: {enum_file_path}")
                # 解析枚举文件
                enum_values = self.java_parser.parse_enum_file(enum_file_path)
                if enum_values:
                    # 构造完整的枚举类名
                    enum_class_name = self._get_enum_class_name_from_path(enum_file_path)
                    self.logger.info(f"    📝 枚举类名: {enum_class_name}")
                    
                    # 创建枚举定义
                    enum_def = self._create_enum_definition(enum_class_name, enum_values)
                    
                    # 检查是否有原始名称，如果有则使用原始名称
                    original_name = self._extract_original_enum_name(enum_file_path)
                    if original_name:
                        self.logger.info(f"    🏷️ 使用原始名称: {original_name}")
                        enum_def.name = original_name
                    
                    # 添加到枚举定义中
                    self.enum_definitions[enum_class_name] = enum_def
                    self.logger.info(f"    ✅ 成功处理枚举依赖: {enum_def.name} ({len(enum_def.values)} 个值)")
                else:
                    self.logger.warning(f"    ❌ 枚举值解析失败: {enum_file_path}")
            else:
                self.logger.warning(f"    ❌ 未找到枚举文件: {type_name}")
                    
        except Exception as e:
            self.logger.warning(f"  ⚠️ 处理枚举依赖失败 {type_name}: {e}")
            import traceback
            self.logger.debug(f"  详细错误: {traceback.format_exc()}")
    
    def _find_enum_file(self, type_name: str) -> Optional[Path]:
        """
        在所有包中查找枚举文件
        
        Args:
            type_name: 枚举类型名
            
        Returns:
            枚举文件路径或None
        """
        # 在整个源码目录中搜索匹配的枚举文件
        for root, dirs, files in os.walk(self.sources_dir):
            for file in files:
                if file.endswith('.java') and type_name in file:
                    file_path = Path(root) / file
                    # 检查是否确实是这个枚举类
                    if self._is_target_enum_file(file_path, type_name):
                        return file_path
        return None
    
    def _is_target_enum_file(self, file_path: Path, type_name: str) -> bool:
        """
        检查文件是否是目标枚举类
        
        Args:
            file_path: Java文件路径
            type_name: 目标枚举类型名
            
        Returns:
            是否为目标枚举文件
        """
        try:
            content = file_path.read_text(encoding='utf-8')
            # 检查是否包含目标枚举类声明
            enum_pattern = f'public\\s+enum\\s+{re.escape(type_name)}\\s+implements\\s+Internal\\.EnumLite'
            return bool(re.search(enum_pattern, content))
        except Exception:
            return False
    
    def _get_enum_class_name_from_path(self, file_path: Path) -> str:
        """
        从文件路径构造完整的枚举类名
        
        Args:
            file_path: 枚举文件路径
            
        Returns:
            完整的枚举类名
        """
        # 获取相对于源码目录的路径
        relative_path = file_path.relative_to(self.sources_dir)
        
        # 移除.java后缀并转换为类名
        class_path = str(relative_path)[:-5]  # 移除.java
        class_name = class_path.replace('/', '.')
        
        return class_name
    
    def _extract_original_enum_name(self, file_path: Path) -> Optional[str]:
        """
        从Java源码中提取实际的枚举类名
        
        Args:
            file_path: Java文件路径
            
        Returns:
            Java源码中定义的实际枚举类名
        """
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # 查找枚举类定义: public enum ClassName 或 enum ClassName
            enum_pattern = r'(?:public\s+)?enum\s+(\w+)'
            match = re.search(enum_pattern, content)
            
            if match:
                enum_name = match.group(1)
                self.logger.info(f"    🏷️ 从Java源码提取枚举名: {enum_name}")
                return enum_name
            else:
                # 如果没找到enum定义，可能是接口或其他类型，使用文件名
                file_name = file_path.stem
                self.logger.info(f"    🏷️ 未找到enum定义，使用文件名: {file_name}")
                return file_name
                
        except Exception as e:
            self.logger.debug(f"    提取枚举名失败: {e}")
            # 出错时使用文件名作为fallback
            return file_path.stem
    
    def _parse_map_types(self, map_content: str) -> tuple:
        """
        解析map类型的键值类型
        
        Args:
            map_content: map内容，如 "string, Contact" 或 "string, List<Contact>"
            
        Returns:
            (key_type, value_type) 元组
        """
        # 简单情况：没有嵌套的尖括号
        if '<' not in map_content:
            parts = [part.strip() for part in map_content.split(',', 1)]
            if len(parts) == 2:
                return parts[0], parts[1]
        
        # 复杂情况：处理嵌套的尖括号
        bracket_count = 0
        for i, char in enumerate(map_content):
            if char == '<':
                bracket_count += 1
            elif char == '>':
                bracket_count -= 1
            elif char == ',' and bracket_count == 0:
                # 找到分隔符
                key_type = map_content[:i].strip()
                value_type = map_content[i+1:].strip()
                return key_type, value_type
        
        # 如果解析失败，返回默认值
        return 'string', 'string'
    
    def _should_skip_class(self, class_name: str) -> bool:
        """
        判断是否应该跳过某个类的处理
        
        Args:
            class_name: 类名
            
        Returns:
            是否应该跳过
        """
        # 已处理过的类
        if class_name in self.processed_classes:
            return True
        
        # 使用TypeMapper判断基础类型和系统包
        if type_mapper.is_java_basic_type(class_name) or type_mapper.is_system_package(class_name):
            return True
            
        # 跳过明显不是protobuf类的包
        if self._is_system_or_internal_type(class_name):
            return True
            
        return False
    
    def _is_system_or_internal_type(self, class_name: str) -> bool:
        """
        判断是否为系统类型或内部类型
        
        Args:
            class_name: 类名
            
        Returns:
            是否为系统或内部类型
        """
        # 跳过明显不是protobuf类的包
        skip_packages = [
            'java.', 'javax.', 'android.', 'androidx.',
            'kotlin.', 'kotlinx.', 'com.google.common.',
            'org.apache.', 'org.junit.', 'junit.',
            'com.unity3d.',  # 添加Unity3D包，避免误匹配
            'Internal.'      # 跳过Internal包下的类型
        ]
        
        for skip_pkg in skip_packages:
            if class_name.startswith(skip_pkg):
                return True
                
        # 跳过明显的内部类型
        internal_patterns = [
            'Internal.ProtobufList',
            'MapFieldLite',
            'GeneratedMessageLite',
            'MessageLiteOrBuilder'
        ]
        
        for pattern in internal_patterns:
            if pattern in class_name:
                return True
                
        return False
    
    def _get_skip_reason(self, class_name: str) -> str:
        """
        获取跳过类的原因
        
        Args:
            class_name: 类名
            
        Returns:
            跳过原因
        """
        # 基础类型
        basic_types = {
            'java.lang.String', 'java.lang.Integer', 'java.lang.Long', 
            'java.lang.Boolean', 'java.lang.Float', 'java.lang.Double',
            'java.lang.Object', 'java.util.List', 'java.util.Map',
            'com.google.protobuf.ByteString', 'com.google.protobuf.MessageLite'
        }
        
        if class_name in basic_types:
            return "基础类型"
            
        # 已处理
        if class_name in self.processed_classes:
            return "已处理"
            
        # 系统包
        system_packages = {
            'java.': 'Java系统包',
            'javax.': 'Java扩展包', 
            'android.': 'Android系统包',
            'androidx.': 'AndroidX包',
            'kotlin.': 'Kotlin标准库',
            'kotlinx.': 'Kotlin扩展库',
            'com.google.common.': 'Google通用库',
            'org.apache.': 'Apache库',
            'org.junit.': 'JUnit测试库',
            'junit.': 'JUnit库'
        }
        
        for prefix, reason in system_packages.items():
            if class_name.startswith(prefix):
                return reason
                
        return "未知原因"

    def _resolve_field_dependency(self, type_name: str, current_package: str) -> Optional[str]:
        """
        解析字段类型名为完整的类名
        
        Args:
            type_name: 字段类型名
            current_package: 当前类的包名
            
        Returns:
            完整的类名，如果不是依赖类则返回None
        """
        if not type_name:
            return None
            
        # 检查是否为基础类型
        if type_mapper.is_basic_proto_type(type_name):
            return None
            
        # 如果已经是完整类名，直接返回
        if '.' in type_name:
            return type_name
            
        # 首先尝试推断简单类名的完整包名
        inferred_name = self._infer_full_class_name(type_name, current_package)
        if inferred_name:
            return inferred_name
            
        # 如果推断失败，尝试查找所有可能的匹配类
        # 需要传递当前类名以便进行源码分析
        current_class = getattr(self, '_current_processing_class', None)
        best_match = self._find_best_matching_class(type_name, current_package, current_class)
        
        # 如果找到匹配，验证该类是否确实存在
        if best_match and self._find_java_file(best_match):
            return best_match
            
        return None
    
    def _find_java_file(self, class_name: str) -> Optional[Path]:
        """
        根据类名查找对应的Java文件（优化版本）
        
        Args:
            class_name: 完整的Java类名
            
        Returns:
            Java文件路径，如果找不到则返回None
        """
        # 🚀 优化1：直接根据包名和类名构造文件路径（你的建议）
        # 标准路径：com.example.Model -> com/example/Model.java
        file_path = class_name.replace('.', '/') + '.java'
        full_path = self.sources_dir / file_path
        
        if full_path.exists():
            return full_path
        
        # 🚀 优化2：处理内部类，但避免全目录扫描
        if '$' in class_name:
            # 内部类处理：com.example.Models$Inner -> com/example/Models.java
            last_dot_index = class_name.rfind('.')
            if last_dot_index != -1:
                package_path = class_name[:last_dot_index].replace('.', '/')
                class_part = class_name[last_dot_index + 1:]
                
                # 提取外部类名（$之前的部分）
                outer_class = class_part.split('$')[0]
                outer_class_file_path = f"{package_path}/{outer_class}.java"
                outer_class_full_path = self.sources_dir / outer_class_file_path
                
                if outer_class_full_path.exists():
                    return outer_class_full_path
        
        # 🚀 优化3：简化文件查找逻辑，移除索引依赖
        
        # 🚀 优化4：最后的备选方案 - 限制搜索范围
        # 只在当前包及其父包中搜索，避免全目录扫描
        package_parts = class_name.split('.')[:-1]  # 获取包名部分
        simple_name = class_name.split('.')[-1].split('$')[0]  # 提取简单类名
        
        # 构造搜索路径列表，限制搜索范围
        search_paths = []
        for i in range(len(package_parts), 0, -1):
            package_path = '/'.join(package_parts[:i])
            search_paths.append(self.sources_dir / package_path)
        
        # 在限定范围内搜索
        for search_path in search_paths:
            if search_path.exists():
                for java_file in search_path.rglob(f"{simple_name}.java"):
                    # 验证找到的文件是否匹配
                    relative_path = java_file.relative_to(self.sources_dir)
                    if relative_path.stem == simple_name:
                        return java_file
        
        return None
    
    def _infer_full_class_name(self, simple_name: str, current_package: str) -> Optional[str]:
        """
        推断简单类名的完整包名（通用算法，适用于任何应用）
        
        Args:
            simple_name: 简单类名，如 'Contact'
            current_package: 当前类的包名
            
        Returns:
            推断出的完整类名
        """
        # 动态生成候选包名列表
        candidate_packages = self._generate_candidate_packages(current_package)
        
        for package in candidate_packages:
            candidate = f"{package}.{simple_name}"
            if self._find_java_file(candidate):
                return candidate
        
        return None

    def _generate_candidate_packages(self, current_package: str) -> List[str]:
        """
        动态生成候选包名列表
        
        Args:
            current_package: 当前包名
            
        Returns:
            候选包名列表，按优先级排序
        """
        candidates = []
        
        # 1. 当前包（最高优先级）
        candidates.append(current_package)
        
        # 2. 当前包的父级包
        package_parts = current_package.split('.')
        for i in range(len(package_parts) - 1, 0, -1):
            parent_package = '.'.join(package_parts[:i])
            candidates.append(parent_package)
        
        # 3. 当前包的同级包（常见的模块组织方式）
        if len(package_parts) > 1:
            parent = '.'.join(package_parts[:-1])
            # 常见的同级包名
            common_siblings = ['models', 'model', 'types', 'entities', 'data', 'proto', 'protobuf', 
                             'enums', 'enum', 'common', 'shared', 'core', 'base']
            for sibling in common_siblings:
                if sibling != package_parts[-1]:  # 避免重复
                    candidates.append(f"{parent}.{sibling}")
        
        # 4. 根包下的常见子包
        if len(package_parts) > 2:
            root_package = '.'.join(package_parts[:2])  # 如 com.example
            common_subpackages = ['models', 'model', 'types', 'entities', 'common', 'shared', 'proto',
                                'enums', 'enum', 'core', 'base', 'data', 'dto', 'vo']
            for subpkg in common_subpackages:
                candidates.append(f"{root_package}.{subpkg}")
        
        # 5. 深度搜索：在当前包的各级父包下寻找常见子包
        for i in range(len(package_parts) - 1, 1, -1):
            parent_package = '.'.join(package_parts[:i])
            # 在每个父包下寻找常见的子包
            search_patterns = ['models', 'enums', 'types', 'common', 'shared', 'core']
            for pattern in search_patterns:
                candidates.append(f"{parent_package}.{pattern}")
                # 也尝试更深一层的组合
                if i > 2:
                    candidates.append(f"{parent_package}.{pattern}.{package_parts[-1]}")
        
        # 6. 特殊情况：如果当前是v1包，也尝试其他版本
        if 'v1' in package_parts:
            for i, part in enumerate(package_parts):
                if part == 'v1':
                    # 尝试v2, v3等
                    for version in ['v2', 'v3', 'v4']:
                        version_package = package_parts.copy()
                        version_package[i] = version
                        candidates.append('.'.join(version_package))
        
        # 去重并保持顺序
        seen = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)
        
        return unique_candidates

    def _find_best_matching_class(self, type_name: str, current_package: str, current_class: str = None) -> Optional[str]:
        """
        查找最佳匹配的类（高性能版本）
        
        Args:
            type_name: 类型名（如 IdData）
            current_package: 当前包名
            current_class: 当前类名（用于分析源码）
            
        Returns:
            最佳匹配的完整类名
        """
        # 🚀 性能优化：优先进行基础类型检测，避免不必要的文件IO
        if self._is_basic_field_type(type_name, current_class):
            self.logger.debug(f"    🔍 基础字段类型检测: {type_name} -> 跳过类匹配")
            return None
        
        # 🚀 性能优化：直接使用智能包名推断，避免索引开销
        # 1. 首先尝试推断完整类名
        inferred_name = self._infer_full_class_name(type_name, current_package)
        if inferred_name:
            self.logger.info(f"    🔍 包名推断: {type_name} -> {inferred_name}")
            return inferred_name
        
        # 2. 如果推断失败，使用限制范围的目录搜索
        self.logger.debug(f"    🔍 启用目录搜索: {type_name}")
        return self._fallback_directory_search(type_name, current_package)
    
    def _fallback_directory_search(self, type_name: str, current_package: str) -> Optional[str]:
        """
        回退的目录扫描方法（当索引匹配失败时使用）
        
        Args:
            type_name: 类型名
            current_package: 当前包名
            
        Returns:
            匹配的类名或None
        """
        matching_classes = []
        
        # 在源码目录中搜索
        for java_file in self.sources_dir.rglob("*.java"):
            file_name = java_file.stem  # 不包含.java后缀的文件名
            if file_name.endswith(type_name):
                # 根据文件路径推断包名
                relative_path = java_file.relative_to(self.sources_dir)
                package_parts = relative_path.parts[:-1]  # 排除文件名
                if package_parts:
                    package_name = '.'.join(package_parts)
                    full_class_name = f"{package_name}.{file_name}"
                    
                    # 添加包名过滤，避免匹配到无关的第三方库
                    if self._is_valid_package_for_matching(package_name, current_package):
                        similarity = self._calculate_package_similarity(package_name, current_package)
                        matching_classes.append((full_class_name, similarity))
        
        if not matching_classes:
            return None
            
        # 按包名相似度排序，选择最佳匹配
        matching_classes.sort(key=lambda x: x[1], reverse=True)
        best_match = matching_classes[0][0]
        
        self.logger.info(f"    🔍 目录扫描匹配: {type_name} -> {best_match}")
        return best_match

    def _is_basic_field_type(self, type_name: str, current_class: str = None) -> bool:
        """
        快速检查是否为基础字段类型（高性能版本）
        
        Args:
            type_name: 类型名
            current_class: 当前类名
            
        Returns:
            是否为基础字段类型
        """
        # 🚀 性能优化：使用缓存的类型检查器，避免重复计算
        from utils.type_utils import TypeMapper
        
        # 直接使用统一的基础类型检查，无需额外逻辑
        return TypeMapper.is_java_basic_type(type_name)

    def _is_valid_package_for_matching(self, candidate_package: str, current_package: str) -> bool:
        """
        检查候选包名是否适合用于匹配
        
        Args:
            candidate_package: 候选包名
            current_package: 当前包名
            
        Returns:
            是否为有效的匹配候选
        """
        # 获取当前包的根包名（通常是前两部分，如 com.truecaller）
        current_parts = current_package.split('.')
        if len(current_parts) >= 2:
            current_root = '.'.join(current_parts[:2])
        else:
            current_root = current_package
        
        # 过滤规则
        filters = [
            # 1. 排除明显的第三方库
            lambda pkg: 'unity3d' not in pkg.lower(),
            lambda pkg: 'facebook' not in pkg.lower(),
            lambda pkg: 'google' not in pkg.lower() or pkg.startswith(current_root),
            lambda pkg: 'android' not in pkg.lower() or pkg.startswith(current_root),
            lambda pkg: 'androidx' not in pkg.lower(),
            lambda pkg: 'kotlin' not in pkg.lower(),
            lambda pkg: 'java' not in pkg.lower(),
            lambda pkg: 'javax' not in pkg.lower(),
            
            # 2. 优先选择同根包的类
            lambda pkg: pkg.startswith(current_root) or self._calculate_package_similarity(pkg, current_package) > 0.3
        ]
        
        # 应用所有过滤规则
        for filter_func in filters:
            if not filter_func(candidate_package):
                return False
        
        return True

    def _calculate_package_similarity(self, package1: str, package2: str) -> float:
        """
        计算两个包名的相似度
        
        Args:
            package1: 第一个包名
            package2: 第二个包名
            
        Returns:
            相似度分数（0-1）
        """
        parts1 = package1.split('.')
        parts2 = package2.split('.')
        
        # 计算公共前缀长度
        common_prefix = 0
        for i in range(min(len(parts1), len(parts2))):
            if parts1[i] == parts2[i]:
                common_prefix += 1
            else:
                break
        
        # 相似度 = 公共前缀长度 / 最大包深度
        max_depth = max(len(parts1), len(parts2))
        return common_prefix / max_depth if max_depth > 0 else 0.0

    def _extract_actual_field_type(self, class_name: str, inferred_type: str) -> Optional[str]:
        """
        从Java源码中提取字段的实际类型（优化版本）
        
        Args:
            class_name: 当前类的完整名称
            inferred_type: 推断出的类型名（如 IdData）
            
        Returns:
            实际的完整类型名
        """
        # 🚀 优化：使用统一的类型检查器
        from utils.type_utils import TypeMapper
        
        if TypeMapper.is_java_basic_type(inferred_type):
            self.logger.debug(f"    跳过基础类型: {inferred_type}")
            return None
        
        # 🚀 性能优化：简化源码分析，避免复杂的正则表达式匹配
        # 对于大多数情况，索引系统已经能够提供足够准确的匹配
        # 这里只做最基本的检查，避免耗时的文件IO和正则匹配
        
        try:
            # 使用索引系统进行快速查找，避免文件IO
            from utils.type_index import get_type_index
            type_index = get_type_index(self.sources_dir)
            
            # 构造可能的完整类名
            package_name = '.'.join(class_name.split('.')[:-1])
            possible_full_name = f"{package_name}.{inferred_type}"
            
            # 使用索引快速检查
            result = type_index.find_best_match(inferred_type, package_name)
            if result:
                self.logger.debug(f"    索引快速匹配: {inferred_type} -> {result}")
                return result
            
            return None
            
        except Exception as e:
            self.logger.debug(f"    ⚠️  快速类型匹配失败: {e}")
            return None
    
    def _create_enum_definition(self, class_name: str, enum_values: List[tuple]) -> EnumDefinition:
        """
        根据类名和枚举值创建枚举定义
        
        Args:
            class_name: 完整的Java类名
            enum_values: 枚举值列表 [(name, value), ...]
            
        Returns:
            EnumDefinition对象
        """
        # 分离包名和枚举名
        parts = class_name.split('.')
        package_name = '.'.join(parts[:-1])
        enum_name = parts[-1]
        
        # 创建枚举定义
        enum_def = EnumDefinition(
            name=enum_name,
            package_name=package_name,
            full_name=class_name
        )
        
        # 添加枚举值
        for name, value in enum_values:
            enum_value_def = EnumValueDefinition(name=name, value=value)
            enum_def.values.append(enum_value_def)
        
        return enum_def
    
    def _generate_all_proto_files(self) -> None:
        """生成所有解析成功的proto文件"""
        message_count = len(self.message_definitions)
        enum_count = len(self.enum_definitions)
        total_count = message_count + enum_count
        
        self.logger.info(f"\n📝 开始生成proto文件，共 {total_count} 个 ({message_count} 消息, {enum_count} 枚举)...")
        
        # 生成消息proto文件
        for class_name, message_def in self.message_definitions.items():
            self._generate_single_proto_file(class_name, message_def)
        
        # 生成枚举proto文件
        for class_name, enum_def in self.enum_definitions.items():
            self._generate_single_enum_file(class_name, enum_def)
            
    def _generate_single_proto_file(self, class_name: str, message_def: MessageDefinition) -> None:
        """
        生成单个proto文件
        
        Args:
            class_name: Java类名
            message_def: 消息定义对象
        """
        try:
            # 生成proto文件内容
            proto_content = self.proto_generator.generate_proto_file(
                message_def, self.message_definitions, self.enum_definitions
            )
            
            # 确定输出路径并创建目录
            output_path = self._get_output_path(class_name)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            output_path.write_text(proto_content, encoding='utf-8')
            
            self.logger.info(f"📄 生成: {output_path.relative_to(self.output_dir)}")
            
        except Exception as e:
            self.logger.error(f"❌ 生成失败 {class_name}: {e}")
    
    def _generate_single_enum_file(self, class_name: str, enum_def: EnumDefinition) -> None:
        """
        生成单个枚举proto文件
        
        Args:
            class_name: Java类名
            enum_def: 枚举定义对象
        """
        try:
            # 生成proto文件内容
            proto_content = self.proto_generator.generate_enum_proto_file(
                enum_def, self.message_definitions, self.enum_definitions
            )
            
            # 确定输出路径并创建目录
            output_path = self._get_output_path(class_name)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            output_path.write_text(proto_content, encoding='utf-8')
            
            self.logger.info(f"📄 生成枚举: {output_path.relative_to(self.output_dir)}")
            
        except Exception as e:
            self.logger.error(f"❌ 生成枚举失败 {class_name}: {e}")
    
    def _get_output_path(self, class_name: str) -> Path:
        """
        根据类名确定proto文件的输出路径
        
        Args:
            class_name: Java类名
            
        Returns:
            Proto文件的完整路径
        """
        # com.example.Model -> com/example/model.proto
        parts = class_name.split('.')
        proto_name = self._to_snake_case(parts[-1]) + '.proto'
        package_path = '/'.join(parts[:-1])
        
        return self.output_dir / package_path / proto_name
    
    def _report_unknown_types(self) -> None:
        """报告未知字节码类型的统计信息"""
        if not self.info_decoder.unknown_types_stats:
            return
            
        self.logger.warning("📊 发现未知字节码类型统计:")
        for byte_code, count in sorted(self.info_decoder.unknown_types_stats.items()):
            wire_type = byte_code & 7
            self.logger.warning(f"   类型 {byte_code} (0x{byte_code:02x}, wire_type={wire_type}): {count} 次")
        
        self.logger.warning("💡 建议: 请将这些信息反馈给开发者，以便完善类型映射表")

    @staticmethod
    def _to_snake_case(camel_str: str) -> str:
        """
        将CamelCase转换为snake_case（使用统一的命名转换器）
        
        Args:
            camel_str: 驼峰命名字符串
            
        Returns:
            蛇形命名字符串
        """
        # 🚀 优化：使用统一的命名转换器，避免重复实现
        from utils.type_utils import NamingConverter
        return NamingConverter.to_snake_case(camel_str) 