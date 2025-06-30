"""
Protobuf信息解码器

解码Google Protobuf Lite的newMessageInfo字节码
这是项目的核心技术突破：首次成功逆向工程Protobuf Lite的字节码格式

字节码格式说明：
- 每2个字节表示一个字段：[字段标签, 字段类型]
- 特殊字符 '<' (ord=60) 标识oneof字段
- 类型映射：1=float, 2=int64, 3=int32, 4=bool, 9=message, 12=enum, 27=repeated_message, 520=string, 538=repeated_string

Author: AI Assistant
"""

import re
from typing import Optional, List, Dict, Tuple
from pathlib import Path

# 智能导入：同时支持相对导入（包环境）和绝对导入（开发环境）
try:
    # 相对导入（包环境）
    from ..models.message_definition import MessageDefinition, FieldDefinition, OneofDefinition
    from ..utils.logger import get_logger
    from ..utils.type_utils import type_mapper, naming_converter
    from ..parsing.java_parser import JavaParser
except ImportError:
    # 绝对导入（开发环境）
    from models.message_definition import MessageDefinition, FieldDefinition, OneofDefinition
    from utils.logger import get_logger
    from utils.type_utils import type_mapper, naming_converter
    from parsing.java_parser import JavaParser


class InfoDecoder:
    """
    Protobuf信息解码器
    
    核心功能：解码Google Protobuf Lite的newMessageInfo字节码
    将字节码转换为结构化的消息定义，包括字段类型、标签和规则
    """
    
    def __init__(self, java_source_analyzer=None):
        """
        初始化信息解码器
        
        Args:
            java_source_analyzer: Java源码分析器实例（可选）
        """
        self.logger = get_logger("info_decoder")
        self.java_source_analyzer = java_source_analyzer
        
        # 导入JavaParser
        self.java_parser = JavaParser()
        
        # Protobuf字段类型映射表
        # 键：字节码中的类型值，值：对应的protobuf字段类型
        self.type_mapping = {
            0: 'double',      # 64位浮点数 (double) - 基于ContactAddress.latitude_和longitude_的分析
            1: 'float',      # FLOAT
            2: 'int64',      # INT64  
            3: 'int32',      # INT32
            4: 'int32',      # INT32 (修正：4对应int32，不是bool)
            5: 'int64',      # INT64 - 基于Models$Onboarded.userId_和phoneNumber_的分析
            6: 'int32',      # INT32 - 基于Assistant$Payload.action_的分析
            7: 'bool',       # BOOL (修正：7对应bool)
            9: 'message',    # MESSAGE (嵌套消息)
            12: 'enum',      # ENUM (枚举类型)
            27: 'repeated_message',   # REPEATED MESSAGE (修正：27表示repeated message)
            39: 'repeated_int32',     # REPEATED INT32 (packed)
            44: 'repeated_enum',      # PACKED ENUM (修正：44表示repeated enum)
            50: 'map',       # Map字段 - 基于BulkSearchResult.contacts的分析
            92: 'string',    # STRING - 基于Assistant$Payload.title_的分析
            520: 'string',   # UTF-8字符串
            538: 'repeated_string',   # REPEATED STRING (Ț = 538)  
            4100: 'int32',   # INT32 - 基于Assistant$Payload.action_的分析
            4108: 'enum',    # ENUM - 基于Assistant$Payload.payloadType_的分析
            4616: 'string',  # STRING - 基于Assistant$Payload.summary_的分析
        }
        
        # 统计未知字节码类型
        self.unknown_types_stats = {}
    
    def decode_message_info(self, class_name: str, info_string: str, objects: List[str], java_file_path=None) -> Optional[MessageDefinition]:
        """
        解码Protobuf消息信息
        
        Args:
            class_name: 完整的Java类名
            info_string: newMessageInfo中的字节码字符串
            objects: newMessageInfo中的对象数组
            java_file_path: Java文件路径（用于提取字段标签）
            
        Returns:
            MessageDefinition对象 或 None（如果解码失败）
        """
        try:
            # 解码字节码字符串
            bytes_data = self._decode_info_string(info_string)
            if bytes_data is None:
                return None
            
            # 创建消息定义
            message_def = self._create_message_definition(class_name)
            
            # 存储当前处理的类名，供依赖推断使用
            self._current_processing_class = class_name
            
            # 提取字段标签（如果有Java文件路径）
            field_tags = None
            if java_file_path:
                # 存储当前Java文件路径，供其他方法使用
                self._current_java_file_path = java_file_path
                field_tags = self.java_parser.extract_field_tags(java_file_path)
                if field_tags:
                    self.logger.info(f"    🏷️ 从Java源码提取到 {len(field_tags)} 个字段标签")
            else:
                self._current_java_file_path = None
            
            # 解析字段信息
            self._parse_fields(message_def, bytes_data, objects, field_tags)
            
            # 🆕 新增：提取内部枚举
            if java_file_path and java_file_path.exists():
                inner_enums = self._extract_inner_enums(java_file_path, class_name)
                if inner_enums:
                    message_def.inner_enums = inner_enums
                    self.logger.info(f"    🔢 提取到 {len(inner_enums)} 个内部枚举")
            
            return message_def
            
        except Exception as e:
            self.logger.error(f"❌ 解码消息信息失败: {e}")
            return None
    
    def _decode_info_string(self, info_string: str) -> Optional[List[int]]:
        """
        将Unicode转义序列解码为字节数组
        
        Args:
            info_string: 包含Unicode转义序列的字符串
            
        Returns:
            字节数组 或 None（如果解码失败）
        """
        try:
            # 首先解码Unicode转义序列（如\u0000）但保持Unicode字符的原始值
            # 使用raw_unicode_escape来避免将Unicode字符编码为UTF-8
            decoded_string = info_string.encode('raw_unicode_escape').decode('raw_unicode_escape')
            return [ord(c) for c in decoded_string]
        except Exception as e:
            try:
                # 如果包含转义序列，手动处理
                import re
                def replace_unicode_escape(match):
                    return chr(int(match.group(1), 16))
                
                # 替换\uXXXX格式的转义序列
                decoded_string = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode_escape, info_string)
                return [ord(c) for c in decoded_string]
            except Exception as e2:
                try:
                    # 最后的备用方法：直接使用ord值
                    return [ord(c) for c in info_string]
                except Exception as e3:
                    self.logger.error(f"❌ 解码字节码字符串失败: {e}, 方法2: {e2}, 方法3: {e3}")
                    return None
    
    def _create_message_definition(self, class_name: str) -> MessageDefinition:
        """
        根据类名创建消息定义的基础结构
        
        Args:
            class_name: 完整的Java类名
            
        Returns:
            初始化的MessageDefinition对象
        """
        # 分离包名和消息名
        parts = class_name.split('.')
        package_name = '.'.join(parts[:-1])
        message_name = parts[-1]
        
        return MessageDefinition(
            name=message_name,
            package_name=package_name,
            full_name=class_name
        )
    
    def _parse_fields(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str], field_tags: Optional[dict] = None) -> None:
        """
        解析字段信息的主调度方法
        
        Args:
            message_def: 消息定义对象
            bytes_data: 解码后的字节数组
            objects: 对象数组
            field_tags: 字段标签映射 {field_name: tag}
        """
        try:
            # 检查是否包含oneof字段（通过查找'<'字符，ord=60）
            oneof_positions = [i for i, byte_val in enumerate(bytes_data) if byte_val == 60]
            
            self.logger.info(f"    🔍 字节码长度: {len(bytes_data)}, oneof_positions: {oneof_positions}")
            self.logger.info(f"    🔍 字节码内容: {[f'{b:02x}' for b in bytes_data[:20]]}...")
            
            if oneof_positions:
                self.logger.info(f"    🎯 检测到oneof结构，调用_parse_oneof_fields")
                self._parse_oneof_fields(message_def, bytes_data, objects, oneof_positions)
            else:
                self.logger.info(f"    🎯 未检测到oneof结构，调用_parse_regular_fields")
                self._parse_regular_fields(message_def, bytes_data, objects, field_tags)
                
        except Exception as e:
            self.logger.error(f"❌ 解析字段失败: {e}")
    
    def _parse_regular_fields(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str], field_tags: Optional[dict] = None) -> None:
        """
        解析常规字段（非oneof字段）
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节码数据
            objects: 对象数组
            field_tags: 字段标签映射 {field_name: tag}
        """
        # 跳过前10个字节的元数据
        field_start = 10
        object_index = 0
        
        self.logger.info(f"    📊 开始解析字段，字节码长度: {len(bytes_data)}, objects数组长度: {len(objects)}")
        self.logger.info(f"    📊 完整字节码数据: {[f'{b:02x}' for b in bytes_data]}")
        self.logger.info(f"    📊 Objects数组: {objects}")
        
        # 如果有字段标签，优先使用Java源码信息
        self.logger.info(f"    🔍 field_tags类型: {type(field_tags)}, 值: {field_tags}, 布尔值: {bool(field_tags)}")
        if field_tags:
            self.logger.info(f"    🏷️ 使用Java源码字段标签: {field_tags}")
            self._parse_fields_with_java_tags(message_def, bytes_data, objects, field_tags)
        else:
            # 回退到字节码解析
            self.logger.info(f"    🔍 回退到字节码解析，field_tags为: {field_tags}")
            self._parse_fields_from_bytecode(message_def, bytes_data, objects, field_start)
        
        self.logger.info(f"    📊 字段解析完成，共解析 {len(message_def.fields)} 个字段")
    
    def _parse_fields_with_java_tags(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str], field_tags: dict) -> None:
        """
        使用Java源码提取的字段标签解析字段，同时处理objects数组中的类引用
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节码数据
            objects: 对象数组
            field_tags: Java源码提取的字段标签映射
        """
        self.logger.info(f"    🔍 开始_parse_fields_with_java_tags")
        self.logger.info(f"    📊 Objects数组: {objects}")
        self.logger.info(f"    📊 字段标签: {field_tags}")
        
        # 首先检查是否有oneof结构
        oneof_field = None
        class_refs = []
        
        for obj in objects:
            if not obj.endswith('_') and obj not in ['action', 'actionCase', 'result', 'resultCase'] and len(obj) > 2:
                class_refs.append(obj)
            elif obj.endswith('_') and obj.rstrip('_') + 'Case_' in objects:
                oneof_field = obj
        
        # 分离普通字段和oneof相关的对象
        oneof_related_objects = set()
        if oneof_field and class_refs:
            # 标记oneof相关的对象
            oneof_related_objects.add(oneof_field)  # action_
            oneof_related_objects.add(oneof_field.rstrip('_') + 'Case_')  # actionCase_
            oneof_related_objects.update(class_refs)  # SkipRecovery, InstallationInfo
            self.logger.info(f"    🎯 检测到oneof结构: {oneof_field}，包含类引用: {class_refs}")
            
            # 特殊处理：如果oneof字段的名称与field_tags中的某些字段名相似，
            # 说明这些field_tags可能是错误的（来自Java常量的错误转换）
            # 例如：result_ oneof 但 field_tags 中有 singlesearchresult_, bulksearChresult_
            oneof_base_name = oneof_field.rstrip('_').lower()
            for field_name in list(field_tags.keys()):
                field_base_name = field_name.rstrip('_').lower()
                # 如果字段名包含oneof的基础名称，或者包含类引用的名称，很可能是错误的字段标签
                if (oneof_base_name in field_base_name or 
                    any(class_ref.lower() in field_base_name for class_ref in class_refs)):
                    oneof_related_objects.add(field_name)
                    self.logger.debug(f"    🔍 标记疑似错误字段标签: {field_name} (与oneof {oneof_field} 或类引用相关)")
        
        # 处理普通字段（从field_tags中提取，排除oneof相关的字段）
        for field_name_raw, field_tag in field_tags.items():
            # 跳过oneof相关的字段
            if field_name_raw in oneof_related_objects:
                self.logger.debug(f"    ⏭️  跳过oneof相关字段: {field_name_raw}")
                continue
                
            # 清理字段名
            field_name = self._clean_field_name(field_name_raw)
            
            # 从Java源码获取字段类型
            # 首先尝试作为枚举类型获取
            java_type = self._get_real_field_type_from_source(field_name_raw, 'enum')
            if not java_type:
                # 如果枚举类型获取失败，再尝试作为消息类型获取
                java_type = self._get_real_field_type_from_source(field_name_raw, 'message')
            if java_type:
                # 使用Java源码类型，直接处理原始Java类型
                if java_type.startswith('Internal.ProtobufList<') and java_type.endswith('>'):
                    # Internal.ProtobufList<Contact> -> Contact (repeated)
                    element_type = java_type[len('Internal.ProtobufList<'):-1]
                    field_type_name = self._convert_java_to_proto_type(element_type)
                    rule = 'repeated'
                elif java_type.startswith('MapFieldLite<') and java_type.endswith('>'):
                    # MapFieldLite<String, Contact> -> map<string, Contact>
                    field_type_name = self._convert_java_to_proto_type(java_type)
                    rule = 'optional'
                elif java_type == 'Internal.IntList':
                    # Internal.IntList -> 需要从setter方法获取真正的枚举类型
                    if self.java_source_analyzer:
                        enum_type = self.java_source_analyzer._get_enum_type_from_list_setter(field_name_raw.rstrip('_'))
                        if enum_type:
                            # 获取到枚举类型，转换为简单类名
                            field_type_name = self._convert_java_to_proto_type(enum_type)
                            rule = 'repeated'
                        else:
                            # 如果获取不到，回退到默认处理
                            field_type_name = 'int32'
                            rule = 'repeated'
                    else:
                        field_type_name = 'int32'
                        rule = 'repeated'
                else:
                    # 普通Java类型
                    if java_type in ['int', 'long', 'short', 'byte']:
                        # 基础整数类型可能对应枚举，但需要检查是否有对应的setter
                        if self.java_source_analyzer:
                            enum_type = self.java_source_analyzer._get_type_from_setter(field_name_raw.rstrip('_'))
                            if enum_type:
                                field_type_name = self._convert_java_to_proto_type(enum_type)
                                rule = 'optional'
                            else:
                                # 确实是基础整数类型
                                field_type_name = self._convert_java_to_proto_type(java_type)
                                rule = 'optional'
                        else:
                            # 确实是基础整数类型
                            field_type_name = self._convert_java_to_proto_type(java_type)
                            rule = 'optional'
                    else:
                        # 非基础整数类型，正常处理
                        field_type_name = self._convert_java_to_proto_type(java_type)
                        # 判断是否为repeated类型
                        if (java_type.startswith('Internal.ProtobufList<') or 
                            java_type.startswith('List<') or
                            java_type.startswith('ArrayList<')):
                            rule = 'repeated'
                        else:
                            rule = 'optional'
                
                self.logger.info(f"    🔍 从Java源码获取类型: {field_name_raw} -> {java_type} -> {field_type_name} (rule: {rule})")
            else:
                # Java源码分析失败，这是一个严重错误
                error_msg = f"❌ Java源码分析失败: 无法获取字段 {field_name_raw} 的类型信息"
                self.logger.error(error_msg)
                raise ValueError(f"字段类型分析失败: {field_name_raw}. 请检查Java源码是否完整或字段声明是否正确。")
            
            # 记录字段信息
            self.logger.info(f"    📝 字段信息: name={field_name}, type={field_type_name}, tag={field_tag}")
            
            # 特殊情况处理：根据字段名修正类型
            field_type_name = self._refine_field_type(field_name, field_type_name, 0)  # 使用0作为占位符
            
            # 创建字段定义
            field_def = FieldDefinition(
                name=field_name,
                type_name=field_type_name,
                tag=field_tag,
                rule=rule
            )
            
            message_def.fields.append(field_def)
            self.logger.info(f"    ✅ 添加字段: {field_name} = {field_tag} ({rule} {field_type_name})")
        
        # 最后处理objects数组中的类引用，检测oneof结构
        self._parse_oneof_from_objects(message_def, objects, field_tags)
    
    def _parse_oneof_from_objects(self, message_def: MessageDefinition, objects: List[str], field_tags: dict) -> None:
        """
        从objects数组中解析oneof结构和类引用
        
        Args:
            message_def: 消息定义对象
            objects: 对象数组
            field_tags: 已知的字段标签映射
        """
        # 查找类引用（以.class结尾的对象）
        class_refs = []
        oneof_field = None
        
        # 首先识别已经作为字段类型的类引用，避免重复处理
        # 通过Java源码分析结果来识别已使用的类引用
        used_class_refs = set()
        
        # 从已解析的字段中提取使用的类引用
        for field in message_def.fields:
            # 如果字段类型不是基础类型，就是类引用
            if (field.type_name not in ['string', 'int32', 'int64', 'long', 'int', 'bool', 'double', 'float', 'bytes'] and
                not field.type_name.startswith('google.protobuf.') and
                not field.type_name.startswith('repeated ') and
                not field.type_name.startswith('map<')):
                
                # 提取类名（去掉包名部分）
                class_name = field.type_name.split('.')[-1]
                used_class_refs.add(class_name)
                self.logger.debug(f"    📝 从已解析字段 {field.name} 中识别类引用: {class_name}")
        
        # 识别连续的类引用（oneof选项）
        consecutive_class_refs = []
        for i, obj in enumerate(objects):
            if not obj.endswith('_') and obj not in ['action', 'actionCase', 'result', 'resultCase'] and len(obj) > 2:
                consecutive_class_refs.append(i)
        
        # 如果有多个连续的类引用，它们很可能是oneof选项
        is_oneof_group = len(consecutive_class_refs) > 1
        if is_oneof_group:
            # 检查是否连续
            for i in range(len(consecutive_class_refs) - 1):
                if consecutive_class_refs[i+1] - consecutive_class_refs[i] == 1:
                    # 连续的类引用，很可能是oneof选项
                    self.logger.debug(f"    🔍 检测到连续类引用，可能是oneof选项: {[objects[idx] for idx in consecutive_class_refs]}")
                    break
        
        for i, obj in enumerate(objects):
            # 检查是否是类引用（不以_结尾且不是基础字段名）
            if not obj.endswith('_') and obj not in ['action', 'actionCase'] and len(obj) > 2:
                # 跳过已经作为字段类型的类引用
                if obj in used_class_refs:
                    self.logger.debug(f"    ⏭️  跳过已用作字段类型的类引用: {obj}")
                    continue
                # 这可能是一个独立的类引用（用于oneof）
                class_refs.append((i, obj))
                self.logger.info(f"    🔍 发现独立类引用: {obj}")
            elif obj.endswith('_') and obj.rstrip('_') + 'Case_' in objects:
                # 发现oneof字段（通过检查是否有对应的Case字段）
                oneof_field = obj
                self.logger.info(f"    🔍 发现oneof字段: {obj}")
        
        if class_refs and oneof_field:
            # 这是一个oneof结构
            self._create_oneof_structure(message_def, oneof_field, class_refs, field_tags)
        elif class_refs:
            # 有类引用但没有明确的oneof字段，可能是直接的消息字段
            self._create_message_fields_from_class_refs(message_def, class_refs, field_tags)
    
    def _create_oneof_structure(self, message_def: MessageDefinition, oneof_field: str, class_refs: List[tuple], field_tags: dict) -> None:
        """
        创建oneof结构
        
        Args:
            message_def: 消息定义对象
            oneof_field: oneof字段名（如"action_"）
            class_refs: 类引用列表[(索引, 类名)]
            field_tags: 字段标签映射
        """
        from models.message_definition import OneofDefinition
        
        # 创建oneof定义
        oneof_name = self._clean_field_name(oneof_field)
        oneof_def = OneofDefinition(name=oneof_name)
        
        # 收集已使用的字段标签
        used_tags = set()
        for field in message_def.fields:
            used_tags.add(field.tag)
        for oneof in message_def.oneofs:
            for field in oneof.fields:
                used_tags.add(field.tag)
        
        # 为每个类引用创建oneof字段
        for _, class_name in class_refs:
            # 查找对应的字段标签
            field_tag = self._find_tag_for_class(class_name, field_tags, used_tags)
            if field_tag is None:
                self.logger.warning(f"    ⚠️  无法找到类 {class_name} 的字段标签")
                continue
            
            # 生成字段名：SkipRecovery -> skip_recovery
            field_name = self._class_name_to_field_name(class_name)
            
            # 为oneof字段生成正确的类型名
            # 直接使用原始类名，将$替换为_符号，符合protobuf命名规范
            clean_class_name = class_name.replace('$', '_')
            
            # 创建字段定义
            field_def = FieldDefinition(
                name=field_name,
                type_name=clean_class_name,
                tag=field_tag,
                rule='optional'
            )
            
            # 保存完整的类名信息，用于导入路径生成
            field_def.full_class_name = self._infer_full_dependency_class_name(class_name)
            
            oneof_def.fields.append(field_def)
            self.logger.info(f"    ✅ 添加oneof字段: {field_name} = {field_tag} ({clean_class_name})")
            
            # 记录依赖类
            self._record_dependency_class(class_name)
        
        if oneof_def.fields:
            message_def.oneofs.append(oneof_def)
            self.logger.info(f"    🎯 创建oneof: {oneof_name} (包含 {len(oneof_def.fields)} 个字段)")
    
    def _create_message_fields_from_class_refs(self, message_def: MessageDefinition, class_refs: List[tuple], field_tags: dict) -> None:
        """
        从类引用创建普通消息字段
        
        Args:
            message_def: 消息定义对象
            class_refs: 类引用列表[(索引, 类名)]
            field_tags: 字段标签映射
        """
        # 收集已使用的字段标签
        used_tags = set()
        for field in message_def.fields:
            used_tags.add(field.tag)
        for oneof in message_def.oneofs:
            for field in oneof.fields:
                used_tags.add(field.tag)
        
        for _, class_name in class_refs:
            # 查找对应的字段标签
            field_tag = self._find_tag_for_class(class_name, field_tags, used_tags)
            if field_tag is None:
                self.logger.warning(f"    ⚠️  无法找到类 {class_name} 的字段标签")
                continue
            
            # 生成字段名
            field_name = self._class_name_to_field_name(class_name)
            
            # 为oneof字段生成正确的类型名
            # 如果是内部类（包含$），需要使用完整的类名来生成类型名
            full_class_name = self._infer_full_dependency_class_name(class_name)
            if '$' in full_class_name:
                # 对于内部类，使用完整的类名部分（如Service$SkipRecovery）
                class_part = full_class_name.split('.')[-1]  # Service$SkipRecovery
                clean_class_name = class_part.replace('$', '')  # ServiceSkipRecovery
            else:
                # 对于普通类，直接清理$符号
                clean_class_name = class_name.replace('$', '')
            
            # 创建字段定义
            field_def = FieldDefinition(
                name=field_name,
                type_name=clean_class_name,
                tag=field_tag,
                rule='optional'
            )
            
            # 保存完整的类名信息，用于导入路径生成
            field_def.full_class_name = full_class_name
            
            message_def.fields.append(field_def)
            self.logger.info(f"    ✅ 添加消息字段: {field_name} = {field_tag} ({clean_class_name})")
            
            # 记录依赖类
            self._record_dependency_class(class_name)
    
    def _find_tag_for_class(self, class_name: str, field_tags: dict, used_tags: set = None) -> Optional[int]:
        """
        为类名查找对应的字段标签，完全基于Java源码分析
        
        Args:
            class_name: 类名（如"SkipRecovery"）
            field_tags: 字段标签映射
            used_tags: 已使用的字段标签集合
            
        Returns:
            字段标签，如果找不到则返回None
        """
        if used_tags is None:
            used_tags = set()
        # 完全基于Java源码分析，智能推断字段标签
        
        # 1. 直接匹配：类名转换为字段名
        direct_field_name = self._to_snake_case(class_name) + '_'
        if direct_field_name in field_tags:
            self.logger.debug(f"    🎯 直接匹配类 {class_name}: {direct_field_name} -> {field_tags[direct_field_name]}")
            return field_tags[direct_field_name]
        
        # 2. 小写匹配
        lowercase_field_name = class_name.lower() + '_'
        if lowercase_field_name in field_tags:
            self.logger.debug(f"    🎯 小写匹配类 {class_name}: {lowercase_field_name} -> {field_tags[lowercase_field_name]}")
            return field_tags[lowercase_field_name]
        
        # 3. 智能模式匹配：处理各种命名约定
        # 移除常见后缀并尝试匹配
        class_variants = [class_name]
        if class_name.endswith('Result'):
            class_variants.append(class_name[:-6])  # 移除Result
        if class_name.endswith('Info'):
            class_variants.append(class_name[:-4])  # 移除Info
        if class_name.endswith('Data'):
            class_variants.append(class_name[:-4])  # 移除Data
        
        for variant in class_variants:
            for suffix in ['_', 'result_', 'info_', 'data_']:
                test_field_name = variant.lower() + suffix
                if test_field_name in field_tags:
                    self.logger.debug(f"    🎯 变体匹配类 {class_name}: {test_field_name} -> {field_tags[test_field_name]}")
                    return field_tags[test_field_name]
        
        # 4. 模糊匹配：在字段名中查找类名
        class_lower = class_name.lower()
        for field_name, tag in field_tags.items():
            # 跳过已使用的标签
            if tag in used_tags:
                self.logger.debug(f"    ⏭️  跳过已使用的标签: {field_name} -> {tag}")
                continue
                
            field_clean = field_name.lower().rstrip('_')
            if class_lower == field_clean or class_lower in field_clean:
                self.logger.debug(f"    🎯 模糊匹配类 {class_name}: {field_name} -> {tag}")
                return tag
        
        # 5. 使用Java源码分析器获取更精确的信息
        if self.java_source_analyzer:
            tag = self._get_class_field_tag_from_source(class_name)
            if tag is not None:
                self.logger.debug(f"    🎯 源码分析匹配类 {class_name}: -> {tag}")
                return tag
        
        return None
    
    def _get_class_field_tag_from_source(self, class_name: str) -> Optional[int]:
        """
        从Java源码中获取类对应的字段标签
        
        Args:
            class_name: 类名
            
        Returns:
            字段标签，如果找不到则返回None
        """
        if not self.java_source_analyzer:
            return None
        
        try:
            # 处理内部类名称：Models$Onboarded -> Onboarded
            simple_class_name = class_name
            if '$' in class_name:
                simple_class_name = class_name.split('$')[-1]  # 取最后一部分
            
            # 尝试通过Java源码分析器获取字段标签
            # 查找形如 CLASSNAME_FIELD_NUMBER 的常量
            possible_constant_names = [
                # 使用简化的类名（最重要的模式）
                f"{simple_class_name.upper()}_FIELD_NUMBER",
                f"{self._to_snake_case(simple_class_name).upper()}_FIELD_NUMBER",
                # 对于特殊命名，去掉常见后缀
                f"{simple_class_name.replace('Required', '').upper()}_FIELD_NUMBER",  # AttestationRequired -> ATTESTATION_FIELD_NUMBER
                f"{simple_class_name.replace('Error', '').upper()}_FIELD_NUMBER",     # HandledError -> HANDLED_FIELD_NUMBER
                f"{simple_class_name.replace('Found', '').upper()}_FIELD_NUMBER",     # BackUpFound -> BACKUP_FIELD_NUMBER
                f"{simple_class_name.replace('Otp', '').upper()}_FIELD_NUMBER",       # ExpectingOtp -> EXPECTING_FIELD_NUMBER
                # 使用完整类名（备选方案）
                f"{class_name.upper()}_FIELD_NUMBER",
                f"{self._to_snake_case(class_name).upper()}_FIELD_NUMBER", 
                f"{class_name.upper()}",
                f"{simple_class_name.upper()}",
                f"{simple_class_name.upper()}_NUMBER",
                # 处理缩写情况
                f"{simple_class_name.upper()[:4]}_FIELD_NUMBER",  # 前4个字符
                f"{simple_class_name.upper()[:5]}_FIELD_NUMBER",  # 前5个字符
                f"{simple_class_name.upper()[:6]}_FIELD_NUMBER",  # 前6个字符
                # 特殊映射（基于实际观察到的模式）
                "ERROR_FIELD_NUMBER" if simple_class_name.endswith('Error') else None,
                "BACKUPFOUND_FIELD_NUMBER" if 'BackUp' in simple_class_name else None,
                "ATTESTATIONREQUIRED_FIELD_NUMBER" if 'Attestation' in simple_class_name else None,
                "EXPECTINGOTP_FIELD_NUMBER" if 'Expecting' in simple_class_name else None,
            ]
            
            # 过滤掉None值
            possible_constant_names = [name for name in possible_constant_names if name is not None]
            
            for constant_name in possible_constant_names:
                # 尝试从Java源码中提取常量值
                tag = self.java_source_analyzer._extract_constant_value(constant_name)
                if tag is not None:
                    self.logger.debug(f"    🎯 从源码获取字段标签: {class_name} -> {constant_name} = {tag}")
                    return tag
            
            return None
            
        except Exception as e:
            self.logger.debug(f"    ⚠️  源码分析失败: {e}")
            return None
    
    def _to_snake_case(self, camel_str: str) -> str:
        """
        将驼峰命名转换为蛇形命名
        
        Args:
            camel_str: 驼峰命名字符串
            
        Returns:
            蛇形命名字符串
        """
        # 处理$符号
        camel_str = camel_str.replace('$', '_')
        
        # 在大写字母前插入下划线
        result = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', camel_str)
        
        # 转换为小写
        result = result.lower()
        
        # 清理连续的下划线
        result = re.sub(r'_+', '_', result)
        
        # 移除首尾下划线
        return result.strip('_')
    
    def _class_name_to_field_name(self, class_name: str) -> str:
        """
        将类名转换为字段名
        
        Args:
            class_name: 类名（如"SkipRecovery"）
            
        Returns:
            字段名（如"skip_recovery"）
        """
        # 移除$符号并转换为snake_case
        clean_name = class_name.replace('$', '')
        return self._to_snake_case(clean_name)
    
    def _record_dependency_class(self, class_name: str) -> None:
        """
        记录依赖类，用于后续处理
        
        Args:
            class_name: 类名
        """
        # 记录依赖类到实例变量中，供重构器获取
        if not hasattr(self, 'discovered_dependencies'):
            self.discovered_dependencies = []
        
        # 构造完整的类名，智能处理内部类情况
        full_class_name = self._infer_full_dependency_class_name(class_name)
        
        if full_class_name not in self.discovered_dependencies:
            self.discovered_dependencies.append(full_class_name)
            self.logger.info(f"    📦 记录依赖类: {full_class_name}")
    
    def _infer_full_dependency_class_name(self, class_name: str) -> str:
        """
        推断依赖类的完整类名，特别处理内部类情况
        
        Args:
            class_name: 简单类名（如Models$Onboarded）
            
        Returns:
            完整的类名
        """
        # 如果已经是完整类名，直接返回
        if '.' in class_name:
            return class_name
        
        # 获取当前处理的类
        current_class = getattr(self, '_current_processing_class', None)
        if not current_class:
            self.logger.warning(f"    ⚠️  无法获取当前处理类，无法推断 {class_name} 的完整类名")
            return class_name
        
        # 动态提取当前类的包名
        if '.' in current_class:
            last_dot = current_class.rfind('.')
            package_name = current_class[:last_dot]
        else:
            self.logger.warning(f"    ⚠️  当前类 {current_class} 没有包名，无法推断依赖类包名")
            return class_name
        
        # 直接使用包名+类名，不继承当前类的内部类结构
        full_class_name = f"{package_name}.{class_name}"
        self.logger.debug(f"    🔍 推断依赖类: {class_name} -> {full_class_name}")
        return full_class_name
    
    def get_discovered_dependencies(self) -> List[str]:
        """
        获取在解析过程中发现的依赖类
        
        Returns:
            依赖类名列表
        """
        return getattr(self, 'discovered_dependencies', [])
    
    def _determine_field_rule(self, field_type_byte: int, field_type_name: str = None, java_type: str = None) -> str:
        """
        根据字节码、字段类型和Java类型确定字段规则
        
        Args:
            field_type_byte: 字段类型字节
            field_type_name: 字段类型名（可选）
            java_type: Java源码中的类型（可选）
            
        Returns:
            字段规则：'optional' 或 'repeated'
        """
        # map类型永远不使用repeated规则，因为map本身就表示键值对集合
        if field_type_name and field_type_name.startswith('map<'):
            return 'optional'
        
        # 检查Java源码类型是否为集合类型
        if java_type:
            if (java_type.startswith('Internal.ProtobufList<') or 
                java_type.startswith('List<') or
                java_type.startswith('ArrayList<') or
                java_type.startswith('java.util.List<')):
                return 'repeated'
        
        # 检查字段类型名是否包含repeated标识
        if field_type_name and field_type_name.startswith('repeated_'):
            return 'repeated'
        
        # repeated类型的字节码
        repeated_types = {27, 39, 44, 538}  # repeated_message, repeated_int32, repeated_enum, repeated_string
        return 'repeated' if field_type_byte in repeated_types else 'optional'
    
    def _infer_field_type_from_bytecode(self, field_name_raw: str, field_type: str) -> str:
        """
        从Java源码推断字段类型
        
        Args:
            field_name_raw: 原始字段名（带下划线）
            field_type: 字节码推断的字段类型
            
        Returns:
            推断的字段类型
        """
        # 首先尝试从Java源码获取真实类型
        real_type = self._get_real_field_type_from_source(field_name_raw)
        if real_type:
            self.logger.info(f"    🔍 从Java源码获取类型: {field_name_raw} -> {real_type} -> {self._convert_java_to_proto_type(real_type)}")
            return self._convert_java_to_proto_type(real_type)
        
        # 如果源码分析失败，使用字节码类型
        self.logger.info(f"    🔍 使用字节码类型: {field_name_raw} -> {field_type}")
        return field_type
    
    def _convert_java_to_proto_type(self, java_type: str) -> str:
        """
        将Java类型转换为protobuf类型
        
        Args:
            java_type: Java类型名
            
        Returns:
            对应的protobuf类型名
        """
        return type_mapper.java_to_proto_type(java_type)
    
    def _parse_fields_from_bytecode(self, message_def: MessageDefinition, bytes_data: List[int], objects: List[str], field_start: int) -> None:
        """
        从字节码解析字段（原有的解析逻辑）
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节码数据
            objects: 对象数组
            field_start: 字段数据开始位置
        """
        object_index = 0
        
        # 每次处理2个字节：[字段标签, 字段类型]
        for i in range(field_start, len(bytes_data) - 1, 2):
            field_tag = bytes_data[i]
            field_type_byte = bytes_data[i + 1]
            
            self.logger.info(f"    🔍 处理字段 #{(i-field_start)//2 + 1}: tag={field_tag}, type_byte={field_type_byte} (0x{field_type_byte:02x})")
            
            # 查找类型映射，对未知类型进行智能处理
            if field_type_byte not in self.type_mapping:
                # 统计未知类型
                self.unknown_types_stats[field_type_byte] = self.unknown_types_stats.get(field_type_byte, 0) + 1
                
                # 记录未知类型，但不跳过字段
                self.logger.warning(f"    ⚠️  发现未知字节码类型: {field_type_byte} (0x{field_type_byte:02x})")
                field_type = self._analyze_unknown_type_with_source_priority(field_type_byte, objects, object_index)
                self.logger.info(f"    🔍 推断未知类型: {field_type_byte} -> {field_type}")
            else:
                field_type = self.type_mapping[field_type_byte]
                self.logger.info(f"    ✅ 已知类型: {field_type_byte} -> {field_type}")
            
            # 从对象数组获取字段信息
            field_info = self._extract_field_info(objects, object_index, field_type)
            if not field_info:
                self.logger.warning(f"    ⚠️  无法获取字段信息，跳过字段 tag={field_tag}")
                continue
                
            field_name, field_type_name, new_object_index = field_info
            object_index = new_object_index
            
            self.logger.info(f"    📝 字段信息: name={field_name}, type={field_type_name}, tag={field_tag}")
            
            # 特殊情况处理：根据字段名修正类型
            field_type_name = self._refine_field_type(field_name, field_type_name, field_type_byte)
            
            # 确定字段规则
            rule = self._determine_field_rule(field_type_byte, field_type_name, None)
            
            # 创建字段定义
            field_def = FieldDefinition(
                name=field_name,
                type_name=field_type_name,
                tag=field_tag,
                rule=rule
            )
            
            message_def.fields.append(field_def)
            self.logger.info(f"    ✅ 添加字段: {field_name} = {field_tag} ({field_type_name})")
    
    def _extract_field_info(self, objects: List[str], object_index: int, field_type: str) -> Optional[tuple]:
        """
        从对象数组中提取字段信息
        
        混合策略：优先使用objects数组中的显式引用，对于枚举类型进行智能推断
        
        Args:
            objects: 对象数组
            object_index: 当前对象索引
            field_type: 字段类型
            
        Returns:
            (字段名, 类型名, 新的对象索引) 或 None
        """
        if object_index >= len(objects):
            return None
        
        # 获取字段名
        field_name_raw = objects[object_index]
        
        # 跳过内部状态字段（protobuf内部使用的字段，不是实际的proto字段）
        if self._is_internal_field(field_name_raw):
            self.logger.info(f"    ⏭️ 跳过内部字段: {field_name_raw}")
            object_index += 1
            # 递归调用获取下一个字段
            return self._extract_field_info(objects, object_index, field_type)
        
        field_name = self._to_snake_case(field_name_raw.rstrip('_'))
        object_index += 1
        
        # 确定字段类型名
        field_type_name = field_type  # 默认使用基础类型
        
        # 处理repeated类型：repeated_message -> message，但保留repeated信息
        if field_type.startswith('repeated_'):
            base_field_type = field_type[9:]  # 移除 'repeated_' 前缀
            field_type_name = base_field_type
        
        # 对于消息类型、枚举类型和map类型，检查objects数组中是否有具体的类型引用
        if field_type_name in ['message', 'enum', 'map'] or field_type in ['repeated_message', 'repeated_enum']:
            if object_index < len(objects):
                next_obj = objects[object_index]
                if self._is_type_reference(next_obj):
                    # 直接使用objects数组中的类型引用，这是最准确的信息源
                    if field_type == 'map':
                        # 对于map类型，从MapEntry引用中推断键值类型
                        field_type_name = self._extract_map_type_from_entry(next_obj, field_name_raw)
                        self.logger.info(f"    🗺️ 从MapEntry获取map类型: {field_name} -> {field_type_name}")
                    else:
                        field_type_name = self._clean_type_reference(next_obj)
                        self.logger.info(f"    🔗 从objects数组获取类型: {field_name} -> {field_type_name}")
                    object_index += 1
                else:
                    # 没有显式引用，优先从Java源码中获取真实类型
                    real_type = self._get_real_field_type_from_source(field_name_raw, field_type_name)
                    if real_type:
                        field_type_name = real_type
                        self.logger.info(f"    🔍 源码获取类型: {field_name} -> {field_type_name}")
                    else:
                        # 如果源码分析失败，才进行智能推断
                        if field_type_name == 'enum':
                            field_type_name = self._infer_enum_type_from_field_name(field_name_raw)
                            self.logger.info(f"    🔍 推断枚举类型: {field_name} -> {field_type_name}")
                        elif field_type_name == 'message':
                            field_type_name = self._infer_message_type_from_field_name(field_name_raw)
                            self.logger.info(f"    🔍 推断消息类型: {field_name} -> {field_type_name}")
                        elif field_type == 'map':
                            field_type_name = self._infer_map_type_from_source(field_name_raw)
                            self.logger.info(f"    🔍 推断map类型: {field_name} -> {field_type_name}")
            else:
                # objects数组已结束，优先从Java源码中获取真实类型
                real_type = self._get_real_field_type_from_source(field_name_raw, field_type_name)
                if real_type:
                    field_type_name = real_type
                    self.logger.info(f"    🔍 源码获取类型: {field_name} -> {field_type_name}")
                else:
                    # 如果源码分析失败，才进行智能推断
                    if field_type_name == 'enum':
                        field_type_name = self._infer_enum_type_from_field_name(field_name_raw)
                        self.logger.info(f"    🔍 推断枚举类型: {field_name} -> {field_type_name}")
                    elif field_type_name == 'message':
                        field_type_name = self._infer_message_type_from_field_name(field_name_raw)
                        self.logger.info(f"    🔍 推断消息类型: {field_name} -> {field_type_name}")
                    elif field_type == 'map':
                        field_type_name = self._infer_map_type_from_source(field_name_raw)
                        self.logger.info(f"    🔍 推断map类型: {field_name} -> {field_type_name}")
        
        return field_name, field_type_name, object_index

    def _get_real_field_type_from_source(self, field_name_raw: str, expected_type: str = 'message') -> Optional[str]:
        """
        从Java源码中获取字段的真实Java类型（原始类型，不转换）
        
        Args:
            field_name_raw: 原始字段名（如 contacts_）
            expected_type: 期望的基础类型（message、enum 或 map）
            
        Returns:
            原始的Java类型名，如果无法获取则返回None
        """
        if not self.java_source_analyzer:
            return None
            
        try:
            # 调用Java源码分析器获取真实Java类型（原始类型）
            real_type = self.java_source_analyzer.get_field_type(field_name_raw, expected_type)
            if real_type:
                self.logger.info(f"    🔍 源码分析成功: {field_name_raw} -> {real_type}")
                return real_type  # 返回原始Java类型
            return None
        except Exception as e:
            self.logger.debug(f"    🔍 源码分析失败: {e}")
            return None

    def _infer_message_type_from_field_name(self, field_name_raw: str) -> str:
        """
        根据字段名智能推断消息类型名（通用算法）
        
        Args:
            field_name_raw: 原始字段名（如 businessProfile_）
            
        Returns:
            推断出的消息类型名
        """
        # 优先从Java源码中获取真实类型
        if self.java_source_analyzer:
            real_type = self.java_source_analyzer.get_field_type(field_name_raw, 'message')
            if real_type and real_type not in ['string', 'int32', 'int64', 'bool', 'float', 'double', 'bytes']:
                return real_type
        
        # 移除末尾的下划线
        clean_name = field_name_raw.rstrip('_')
        
        if not clean_name:
            return 'UnknownMessage'
        
        # 检查是否为基础字段类型
        if self._is_likely_basic_field(clean_name):
            # 对于基础字段，返回相应的protobuf基础类型
            return self._get_basic_field_proto_type(clean_name)
        
        # 将camelCase转换为PascalCase
        type_name = self._camel_to_pascal_case(clean_name)
        
        # 通用推断规则（无硬编码）
        # 1. 处理复数形式
        if clean_name.lower().endswith('s') and len(clean_name) > 2:
            # contacts -> Contact, phones -> Phone
            singular = clean_name[:-1]
            return self._camel_to_pascal_case(singular)
        
        # 2. 处理常见后缀
        elif clean_name.lower().endswith('profile'):
            # businessProfile -> BusinessProfile，保持原样
            return type_name
        elif clean_name.lower().endswith('info'):
            # spamInfo -> SpamInfo，保持原样
            return type_name
        elif clean_name.lower().endswith('data'):
            # userData -> UserData，保持原样
            return type_name
        elif clean_name.lower().endswith('config'):
            # systemConfig -> SystemConfig，保持原样
            return type_name
        
        # 3. 默认处理
        else:
            return type_name

    def _is_likely_basic_field(self, field_name: str) -> bool:
        """
        检查字段名是否可能是基础类型字段
        
        Args:
            field_name: 清理后的字段名
            
        Returns:
            是否可能是基础类型
        """
        # 常见的基础字段模式
        basic_patterns = [
            'tags',       # 标签数组
            'ids',        # ID数组
            'values',     # 值数组
            'names',      # 名称数组
            'urls',       # URL数组
            'emails',     # 邮箱数组
            'phones',     # 电话号码数组（如果是字符串）
            'addresses',  # 地址数组（如果是字符串）
            'keywords',   # 关键词数组
            'categories', # 分类数组
            'labels',     # 标签数组
        ]
        
        field_lower = field_name.lower()
        
        # 检查是否匹配基础模式
        for pattern in basic_patterns:
            if field_lower == pattern or field_lower.endswith(pattern):
                return True
        
        return False

    def _get_basic_field_proto_type(self, field_name: str) -> str:
        """
        获取基础字段的protobuf类型
        
        Args:
            field_name: 字段名
            
        Returns:
            protobuf基础类型
        """
        field_lower = field_name.lower()
        
        # 根据字段名推断基础类型
        if field_lower in ['tags', 'names', 'urls', 'emails', 'keywords', 'categories', 'labels']:
            return 'string'  # repeated string
        elif field_lower in ['ids', 'values'] and 'id' in field_lower:
            return 'int64'   # repeated int64
        elif field_lower in ['counts', 'numbers', 'amounts']:
            return 'int32'   # repeated int32
        else:
            return 'string'  # 默认为string

    def _camel_to_pascal_case(self, camel_str: str) -> str:
        """
        将camelCase转换为PascalCase
        
        Args:
            camel_str: camelCase字符串
            
        Returns:
            PascalCase字符串
        """
        if not camel_str:
            return camel_str
        return camel_str[0].upper() + camel_str[1:]
    
    def _infer_enum_type_from_field_name(self, field_name_raw: str) -> str:
        """
        根据字段名智能推断枚举类型名（通用算法）
        
        Args:
            field_name_raw: 原始字段名（如 gender_）
            
        Returns:
            推断出的枚举类型名
        """
        # 移除末尾的下划线
        clean_name = field_name_raw.rstrip('_')
        
        if not clean_name:
            return 'UnknownEnum'
        
        # 将camelCase转换为PascalCase
        type_name = self._camel_to_pascal_case(clean_name)
        
        # 通用推断规则（无硬编码）
        # 1. 处理复数形式
        if clean_name.lower().endswith('s') and len(clean_name) > 2:
            # badges -> Badge, access -> Acces (但应该修正为Access)
            singular = clean_name[:-1]
            result = self._camel_to_pascal_case(singular)
            # 特殊处理：如果去掉s后以ss结尾，说明原词应该保留s
            if singular.lower().endswith('s'):
                result = result + 's'
            return result
        
        # 2. 处理常见后缀
        elif clean_name.lower().endswith('type'):
            # messageType -> MessageType，保持原样
            return type_name
        elif clean_name.lower().endswith('status'):
            # spamStatus -> SpamStatus，保持原样
            return type_name
        elif clean_name.lower().endswith('mode'):
            # displayMode -> DisplayMode，保持原样
            return type_name
        
        # 3. 默认处理
        else:
            return type_name
    
    def _is_type_reference(self, obj: str) -> bool:
        """
        判断对象是否是类型引用
        
        Args:
            obj: 对象字符串
            
        Returns:
            是否为类型引用
        """
        return (obj.endswith('.class') or 
                '.' in obj and not obj.endswith('_') or
                (not obj.endswith('_') and obj[0].isupper()))
    
    def _clean_type_reference(self, obj: str) -> str:
        """
        清理类型引用字符串
        
        Args:
            obj: 原始类型引用
            
        Returns:
            清理后的类型名
        """
        if obj.endswith('.class'):
            return obj[:-6]
        return obj
    
    def _refine_field_type(self, field_name: str, field_type_name: str, field_type_byte: int) -> str:
        """
        根据字段名和上下文信息修正字段类型
        
        Args:
            field_name: 字段名
            field_type_name: 当前推断的类型名
            field_type_byte: 原始字节码
            
        Returns:
            修正后的类型名
        """
        # 只进行必要的基础类型修正，不做复杂推断
        return field_type_name
    
    def _parse_oneof_fields(self, message_def: MessageDefinition, bytes_data: List[int], 
                           objects: List[str], oneof_positions: List[int]) -> None:
        """
        解析oneof字段（增强版，支持Java源码字段标签）
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节数组
            objects: 对象数组
            oneof_positions: oneof标记位置列表
        """
        self.logger.info(f"    🎯 开始解析oneof字段")
        self.logger.info(f"    📊 Objects数组: {objects}")
        self.logger.info(f"    📊 oneof_positions: {oneof_positions}")
        
        # 首先尝试从Java源码获取字段标签
        field_tags = None
        if hasattr(self, 'java_parser') and self.java_parser:
            try:
                # 获取当前类的Java文件路径
                java_file_path = getattr(self, '_current_java_file_path', None)
                if java_file_path:
                    field_tags = self.java_parser.extract_field_tags(java_file_path)
                    if field_tags:
                        self.logger.info(f"    🏷️ 获取到字段标签: {field_tags}")
            except Exception as e:
                self.logger.debug(f"    ⚠️  获取字段标签失败: {e}")
        
        # 如果有字段标签，使用新的解析逻辑
        if field_tags:
            self.logger.info(f"    🎯 使用Java源码字段标签解析oneof")
            # 先处理普通字段
            self._parse_fields_with_java_tags(message_def, bytes_data, objects, field_tags)
        else:
            # 回退到旧的字节码解析逻辑
            self.logger.info(f"    🎯 使用字节码解析oneof")
            self._parse_oneof_fields_legacy(message_def, bytes_data, objects, oneof_positions)
    
    def _parse_oneof_fields_legacy(self, message_def: MessageDefinition, bytes_data: List[int], 
                                  objects: List[str], oneof_positions: List[int]) -> None:
        """
        传统的oneof字段解析方法（作为备用）
        
        Args:
            message_def: 消息定义对象
            bytes_data: 字节数组
            objects: 对象数组
            oneof_positions: oneof标记位置列表
        """
        if len(objects) < 2:
            return
        
        # 提取oneof信息
        oneof_field_name = objects[0]  # 如 "result_"
        oneof_name = self._to_snake_case(oneof_field_name.rstrip('_'))
        
        # 创建oneof定义
        oneof_def = OneofDefinition(name=oneof_name)
        
        # 解析oneof中的字段
        object_index = 2  # 从第3个对象开始
        
        for pos in oneof_positions:
            if pos > 0:
                field_tag = bytes_data[pos - 1]
                
                if object_index < len(objects):
                    field_type_name = objects[object_index]
                    field_name = self._to_snake_case(field_type_name)
                    
                    field_def = FieldDefinition(
                        name=field_name,
                        type_name=field_type_name,
                        tag=field_tag,
                        rule='optional'
                    )
                    
                    oneof_def.fields.append(field_def)
                    object_index += 1
        
        if oneof_def.fields:
            message_def.oneofs.append(oneof_def)
    
    def _extract_map_type_from_entry(self, entry_ref: str, field_name_raw: str) -> str:
        """
        从MapEntry引用中提取map的键值类型
        
        Args:
            entry_ref: MapEntry引用，如 "qux.f107553a"
            field_name_raw: 原始字段名，用于推断类型
            
        Returns:
            map类型字符串，如 "map<string, Contact>"
        """
        try:
            # 优先从Java源码中获取真实的map类型
            if self.java_source_analyzer:
                real_type = self.java_source_analyzer.get_field_type(field_name_raw, 'map')
                if real_type and real_type.startswith('map<'):
                    return real_type
            
            # 如果无法从源码获取，进行智能推断
            return self._infer_map_type_from_source(field_name_raw)
            
        except Exception as e:
            self.logger.warning(f"    ⚠️  从MapEntry提取类型失败: {e}")
            return self._infer_map_type_from_source(field_name_raw)
    
    def _infer_map_type_from_source(self, field_name_raw: str) -> str:
        """
        从字段名推断map类型
        
        Args:
            field_name_raw: 原始字段名（如 contacts_）
            
        Returns:
            推断的map类型字符串
        """
        # 移除末尾的下划线
        clean_name = field_name_raw.rstrip('_')
        
        # 基于字段名的通用推断规则
        if clean_name.lower().endswith('map') or clean_name.lower().endswith('mapping'):
            # xxxMap -> map<string, Xxx>
            base_name = clean_name[:-3] if clean_name.lower().endswith('map') else clean_name[:-7]
            value_type = self._camel_to_pascal_case(base_name) if base_name else 'string'
            return f"map<string, {value_type}>"
        elif clean_name.lower() in ['contacts', 'users', 'profiles']:
            # 常见的复数形式字段，推断为实体映射
            singular = clean_name[:-1] if clean_name.endswith('s') else clean_name
            value_type = self._camel_to_pascal_case(singular)
            return f"map<string, {value_type}>"
        elif clean_name.lower().endswith('tags'):
            # xxxTags -> map<string, string> (标签通常是字符串到字符串的映射)
            return "map<string, string>"
        elif clean_name.lower().endswith('ids'):
            # xxxIds -> map<string, string> (ID映射)
            return "map<string, string>"
        else:
            # 默认推断：字段名作为值类型
            value_type = self._camel_to_pascal_case(clean_name)
            return f"map<string, {value_type}>"

    def _analyze_unknown_type_with_source_priority(self, field_type_byte: int, objects: List[str], object_index: int) -> str:
        """
        分析未知字节码类型，进行智能推断，优先使用Java源码分析结果
        
        Args:
            field_type_byte: 未知的字节码类型
            objects: 对象数组
            object_index: 当前对象索引
            
        Returns:
            推断的字段类型
        """
        # 分析字节码的结构
        wire_type = field_type_byte & 7  # 低3位是wire type
        field_number = field_type_byte >> 3  # 高位是field number
        
        self.logger.debug(f"    🔬 字节码分析: byte={field_type_byte}, wire_type={wire_type}, field_number={field_number}")
        
        # 第一步：尝试从Java源码获取真实类型
        java_type = None
        if object_index < len(objects) and self.java_source_analyzer:
            field_name_raw = objects[object_index]
            try:
                java_type = self._get_java_field_type_for_unknown(field_name_raw)
                if java_type:
                    self.logger.info(f"    ✅ Java源码分析: {field_name_raw} -> {java_type}")
            except Exception as e:
                self.logger.debug(f"    ⚠️  Java源码分析失败: {e}")
        
        # 第二步：基于wire type进行字节码推断
        bytecode_type = self._analyze_unknown_type_by_wire_type(wire_type, objects, object_index, field_type_byte)
        
        # 第三步：交叉校验和最终决策
        final_type = self._cross_validate_types(java_type, bytecode_type, wire_type, field_type_byte)
        
        if java_type and java_type != final_type:
            self.logger.info(f"    🔄 类型校验: Java({java_type}) vs 字节码({bytecode_type}) -> 最终({final_type})")
        
        return final_type
    
    def _get_java_field_type_for_unknown(self, field_name_raw: str) -> Optional[str]:
        """
        从Java源码中获取未知字段的真实类型
        
        Args:
            field_name_raw: 原始字段名（如 latitude_）
            
        Returns:
            Java字段的proto类型，如果无法获取则返回None
        """
        if not self.java_source_analyzer:
            return None
            
        try:
            # 获取Java字段的原始类型
            java_raw_type = self.java_source_analyzer.get_raw_field_type(field_name_raw)
            if not java_raw_type:
                return None
            
            # 将Java类型转换为proto类型
            proto_type = self._convert_java_to_proto_type(java_raw_type)
            return proto_type
            
        except Exception as e:
            self.logger.debug(f"    ⚠️  获取Java字段类型失败: {e}")
            return None
    
    def _analyze_unknown_type_by_wire_type(self, wire_type: int, objects: List[str], object_index: int, field_type_byte: int) -> str:
        """
        基于wire type分析未知字节码类型
        
        Args:
            wire_type: wire type (0-5)
            objects: 对象数组
            object_index: 当前对象索引
            field_type_byte: 原始字节码类型
            
        Returns:
            推断的字段类型
        """
        if wire_type == 0:
            # VARINT: int32, int64, uint32, uint64, sint32, sint64, bool, enum
            return self._infer_varint_type(objects, object_index)
        elif wire_type == 1:
            # 64-BIT: fixed64, sfixed64, double
            return 'double'  # 默认为double（比int64更常见）
        elif wire_type == 2:
            # LENGTH_DELIMITED: string, bytes, embedded messages, packed repeated fields
            return self._infer_length_delimited_type(objects, object_index, field_type_byte)
        elif wire_type == 5:
            # 32-BIT: fixed32, sfixed32, float
            return 'float'  # 默认为float
        else:
            # 其他未知wire type
            self.logger.warning(f"    ⚠️  未知wire type: {wire_type}")
            return self._fallback_type_inference(objects, object_index)
    
    def _cross_validate_types(self, java_type: Optional[str], bytecode_type: str, wire_type: int, field_type_byte: int) -> str:
        """
        交叉校验Java类型和字节码类型，返回最终类型
        
        Args:
            java_type: Java源码分析得到的类型
            bytecode_type: 字节码分析得到的类型
            wire_type: wire type
            field_type_byte: 原始字节码类型
            
        Returns:
            最终确定的字段类型
        """
        # 如果没有Java类型信息，使用字节码推断
        if not java_type:
            return bytecode_type
        
        # 如果Java类型和字节码类型一致，直接返回
        if java_type == bytecode_type:
            return java_type
        
        # 类型不一致时的校验逻辑
        if wire_type == 0:  # VARINT
            # 对于VARINT类型，Java源码更准确
            if java_type in ['bool', 'int32', 'int64', 'uint32', 'uint64', 'sint32', 'sint64']:
                return java_type
            elif java_type == 'message':  # 可能是enum
                return 'enum' if bytecode_type == 'enum' else java_type
        elif wire_type == 1:  # 64-BIT
            # 对于64位类型，Java源码更准确
            if java_type in ['double', 'fixed64', 'sfixed64']:
                return java_type
        elif wire_type == 2:  # LENGTH_DELIMITED
            # 对于长度分隔类型，Java源码更准确
            if java_type in ['string', 'bytes', 'message', 'map']:
                return java_type
        elif wire_type == 5:  # 32-BIT
            # 对于32位类型，Java源码更准确
            if java_type in ['float', 'fixed32', 'sfixed32']:
                return java_type
        
        # 默认优先使用Java类型
        self.logger.info(f"    🔧 类型冲突，优先使用Java类型: {java_type} (字节码推断: {bytecode_type})")
        return java_type

    def _infer_varint_type(self, objects: List[str], object_index: int) -> str:
        """推断VARINT类型字段"""
        # 检查objects数组中是否有类型提示
        if object_index < len(objects):
            field_name = objects[object_index].rstrip('_')
            
            # 基于字段名推断
            if any(keyword in field_name.lower() for keyword in ['type', 'status', 'mode', 'enum']):
                return 'enum'
            elif field_name.lower() in ['count', 'size', 'length', 'number']:
                return 'int32'
            elif field_name.lower().endswith('_id') or field_name.lower() == 'id':
                return 'int64'
            elif field_name.lower() in ['enabled', 'visible', 'active', 'valid']:
                return 'bool'
        
        return 'int32'  # 默认为int32
    
    def _infer_length_delimited_type(self, objects: List[str], object_index: int, field_type_byte: int) -> str:
        """推断LENGTH_DELIMITED类型字段"""
        # 检查是否可能是map类型（基于已知的map类型字节码模式）
        if field_type_byte == 50 or field_type_byte in range(48, 60):  # 扩展map类型的可能范围
            return 'map'
        
        # 检查objects数组中是否有类型提示
        if object_index < len(objects):
            field_name = objects[object_index].rstrip('_')
            
            # 基于字段名推断
            if field_name.lower().endswith('map') or field_name.lower().endswith('mapping'):
                return 'map'
            elif field_name.lower() in ['name', 'title', 'description', 'text', 'url', 'email']:
                return 'string'
            elif field_name.lower().endswith('data') or field_name.lower().endswith('bytes'):
                return 'bytes'
            elif field_name.lower().endswith('s') and len(field_name) > 2:
                # 复数形式，可能是repeated字段
                return 'message'  # repeated message
        
        return 'string'  # 默认为string
    
    def _fallback_type_inference(self, objects: List[str], object_index: int) -> str:
        """兜底类型推断"""
        if object_index < len(objects):
            field_name = objects[object_index].rstrip('_')
            
            # 基于字段名的通用推断
            if any(keyword in field_name.lower() for keyword in ['id', 'count', 'size', 'number']):
                return 'int32'
            elif any(keyword in field_name.lower() for keyword in ['name', 'title', 'text', 'url']):
                return 'string'
            elif field_name.lower().endswith('s'):
                return 'message'  # 可能是repeated字段
        
        return 'string'  # 最终兜底

    @staticmethod
    def _to_snake_case(camel_str: str) -> str:
        """
        将CamelCase转换为snake_case
        
        Args:
            camel_str: 驼峰命名字符串
            
        Returns:
            蛇形命名字符串
        """
        return naming_converter.to_snake_case(camel_str)

    def _is_internal_field(self, field_name_raw: str) -> bool:
        """
        判断是否为protobuf内部字段（不是实际的proto字段）
        
        Args:
            field_name_raw: 原始字段名
            
        Returns:
            True如果是内部字段，False如果是实际字段
        """
        # 移除末尾的下划线进行判断
        clean_name = field_name_raw.rstrip('_').lower()
        
        # protobuf内部字段模式
        internal_patterns = [
            'bitfield0',    # bitField0_ - 用于标记optional字段的位掩码
            'bitfield1',    # bitField1_ - 多个位掩码字段
            'bitfield2',    # bitField2_
            'bitfield',     # 通用位字段模式
            'memoizedhashcode',  # memoizedHashCode_ - 缓存的hash值
            'memoizedsize',      # memoizedSize_ - 缓存的大小
            'unknownfields'      # unknownFields_ - 未知字段存储
        ]
        
        # 检查是否匹配内部字段模式
        for pattern in internal_patterns:
            if clean_name == pattern or clean_name.startswith(pattern):
                return True
        
        return False

    def _clean_field_name(self, field_name_raw: str) -> str:
        """
        清理字段名并转换为snake_case格式
        
        Args:
            field_name_raw: 原始字段名
            
        Returns:
            清理后的字段名
        """
        return self._to_snake_case(field_name_raw.rstrip('_'))

    def _parse_generic_types(self, type_params: str) -> List[str]:
        """
        解析泛型类型参数，处理嵌套的尖括号
        
        Args:
            type_params: 泛型参数字符串，如 "String, Contact" 或 "String, List<Contact>"
            
        Returns:
            类型列表
        """
        types = []
        bracket_count = 0
        current_type = ""
        
        for char in type_params:
            if char == '<':
                bracket_count += 1
                current_type += char
            elif char == '>':
                bracket_count -= 1
                current_type += char
            elif char == ',' and bracket_count == 0:
                # 找到分隔符
                if current_type.strip():
                    types.append(current_type.strip())
                current_type = ""
            else:
                current_type += char
        
        # 添加最后一个类型
        if current_type.strip():
            types.append(current_type.strip())
        
        return types
    
    def _extract_inner_enums(self, java_file_path, class_name: str) -> List:
        """
        从Java文件中提取内部枚举定义 - 复用现有的枚举解析器
        
        Args:
            java_file_path: Java文件路径
            class_name: 主类名
            
        Returns:
            内部枚举定义列表
        """
        try:
            # 导入EnumDefinition
            from models.message_definition import EnumDefinition
            
            content = java_file_path.read_text(encoding='utf-8')
            inner_enums = []
            
            # 查找所有内部枚举定义
            import re
            enum_pattern = r'public\s+enum\s+(\w+)\s+implements\s+Internal\.EnumLite\s*\{'
            enum_matches = re.finditer(enum_pattern, content)
            
            for match in enum_matches:
                enum_name = match.group(1)
                enum_start = match.end()
                
                # 找到枚举定义的结束位置
                brace_count = 1
                pos = enum_start
                while pos < len(content) and brace_count > 0:
                    if content[pos] == '{':
                        brace_count += 1
                    elif content[pos] == '}':
                        brace_count -= 1
                    pos += 1
                
                if brace_count == 0:
                    # 提取枚举内容
                    enum_content = content[enum_start:pos-1]
                    
                    # 🔄 复用JavaParser的现有函数来提取枚举值
                    enum_values_tuples = self.java_parser._extract_enum_values(enum_content)
                    
                    if enum_values_tuples:
                        # 创建枚举定义
                        enum_def = EnumDefinition(
                            name=enum_name,
                            package_name='.'.join(class_name.split('.')[:-1]),
                            full_name=f"{class_name}${enum_name}"
                        )
                        
                        # 🔄 复用现有的EnumValueDefinition创建逻辑
                        from models.message_definition import EnumValueDefinition
                        for name, value in enum_values_tuples:
                            enum_def.values.append(EnumValueDefinition(name=name, value=value))
                        
                        inner_enums.append(enum_def)
                        self.logger.info(f"    📝 提取内部枚举: {enum_name} ({len(enum_def.values)} 个值)")
            
            return inner_enums
            
        except Exception as e:
            self.logger.error(f"❌ 提取内部枚举失败: {e}")
            return []