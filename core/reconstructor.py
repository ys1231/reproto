"""
Protobuf重构器 - 主协调器

负责管理整个重构过程：
1. 任务队列管理和依赖发现
2. Java文件解析和字节码解码
3. Proto文件生成和输出

Author: AI Assistant
"""

import re
from pathlib import Path
from collections import deque
from typing import Set, Dict, List, Optional

from parsing.java_parser import JavaParser
from core.info_decoder import InfoDecoder
from generation.proto_generator import ProtoGenerator
from models.message_definition import MessageDefinition, EnumDefinition, EnumValueDefinition
from utils.logger import get_logger


class JavaSourceAnalyzer:
    """Java源码分析器，用于从源码中获取真实的字段类型"""
    
    def __init__(self, sources_dir: Path):
        self.sources_dir = sources_dir
        self._current_class_content = None
        self._current_class_name = None
    
    def set_current_class(self, class_name: str):
        """设置当前分析的类"""
        self._current_class_name = class_name
        self._current_class_content = self._load_class_content(class_name)
    
    def get_field_type(self, field_name_raw: str, expected_type: str) -> Optional[str]:
        """
        从Java源码中获取字段的真实类型
        
        Args:
            field_name_raw: 原始字段名（如 id_）
            expected_type: 期望的基础类型（message 或 enum）
            
        Returns:
            真实的类型名，如果无法获取则返回None
        """
        if not self._current_class_content:
            return None
        
        # 清理字段名
        field_name = field_name_raw.rstrip('_')
        
        # 对于枚举类型，优先从setter方法中获取类型
        if expected_type == 'enum':
            setter_type = self._get_type_from_setter(field_name)
            if setter_type:
                return setter_type
        
        # 查找字段声明模式：private SomeType fieldName_;
        pattern = rf'private\s+(\w+)\s+{re.escape(field_name)}_\s*;'
        matches = re.findall(pattern, self._current_class_content)
        
        if matches:
            simple_type = matches[0]
            
            # 如果字段声明是基础类型（如int），但期望类型是enum，跳过
            if expected_type == 'enum' and simple_type in ['int', 'long', 'short', 'byte']:
                return None
            
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
        
        # 查找setter方法：public void setSpamType(SpamType spamType)
        pattern = rf'public\s+void\s+{re.escape(setter_name)}\s*\(\s*(\w+)\s+\w+\s*\)'
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
        """加载类的源码内容"""
        try:
            # 标准路径：com.example.Model -> com/example/Model.java
            file_path = class_name.replace('.', '/') + '.java'
            full_path = self.sources_dir / file_path
            
            if full_path.exists():
                return full_path.read_text(encoding='utf-8')
            
            # 备选方案：按简单类名搜索
            simple_name = class_name.split('.')[-1]
            for java_file in self.sources_dir.rglob(f"{simple_name}.java"):
                return java_file.read_text(encoding='utf-8')
            
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
        # 创建Java源码分析器并传递给InfoDecoder
        self.java_source_analyzer = JavaSourceAnalyzer(sources_dir)
        self.info_decoder = InfoDecoder(self.java_source_analyzer)    # 字节码解码器
        self.proto_generator = ProtoGenerator()  # Proto文件生成器
        
        # 任务调度状态
        self.processed_classes: Set[str] = set()  # 已处理的类
        self.pending_classes: deque = deque()     # 待处理的类队列
        self.message_definitions: Dict[str, MessageDefinition] = {}  # 消息定义
        self.enum_definitions: Dict[str, EnumDefinition] = {}        # 枚举定义
        
    def reconstruct_from_root(self, root_class: str) -> Dict[str, any]:
        """
        从根类开始重构所有相关的proto文件
        
        Args:
            root_class: 根类的完整类名，如 'com.example.Model'
            
        Returns:
            重构结果字典
        """
        self.logger.info(f"开始重构，根类: {root_class}")
        
        # 启动任务队列
        self.pending_classes.append(root_class)
        
        # 广度优先处理所有依赖类
        self._process_all_classes()
        
        # 生成最终的proto文件
        self._generate_all_proto_files()
        
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
            # 1. 查找Java文件
            java_file_path = self._find_java_file(class_name)
            if not java_file_path:
                self.logger.info(f"  ⚠️  找不到Java文件: {class_name}")
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
                self.logger.info(f"  ⚠️  无法解析Java文件: {class_name}")
                return
            
            # 4. 解码字节码为消息定义
            message_def = self.info_decoder.decode_message_info(
                class_name, info_string, objects_array
            )
            
            if message_def:
                self.message_definitions[class_name] = message_def
                self.logger.info(f"  ✅ 成功解析消息: {len(message_def.fields)} 个字段")
                
                # 5. 发现并添加依赖类到队列
                self._discover_dependencies(message_def)
            else:
                self.logger.info(f"  ❌ 解码失败: {class_name}")
                
        except Exception as e:
            self.logger.error(f"  ❌ 处理异常: {class_name} - {e}")
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
            dep = self._resolve_field_dependency(field.type_name, message_def.package_name)
            if dep:
                dependencies.append(dep)
        
        # 从oneof字段提取依赖
        for oneof in message_def.oneofs:
            for field in oneof.fields:
                dep = self._resolve_field_dependency(field.type_name, message_def.package_name)
                if dep:
                    dependencies.append(dep)
        
        return dependencies
    
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
            
        # 跳过基础类型
        basic_types = {'string', 'int32', 'int64', 'bool', 'float', 'double', 'bytes', 'message', 'enum'}
        if type_name in basic_types:
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
        return self._find_best_matching_class(type_name, current_package, current_class)
    
    def _find_java_file(self, class_name: str) -> Optional[Path]:
        """
        根据类名查找对应的Java文件
        
        Args:
            class_name: 完整的Java类名
            
        Returns:
            Java文件路径，如果找不到则返回None
        """
        # 标准路径：com.example.Model -> com/example/Model.java
        file_path = class_name.replace('.', '/') + '.java'
        full_path = self.sources_dir / file_path
        
        if full_path.exists():
            return full_path
        
        # 备选方案：按简单类名搜索
        simple_name = class_name.split('.')[-1]
        for java_file in self.sources_dir.rglob(f"{simple_name}.java"):
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
            common_siblings = ['models', 'model', 'types', 'entities', 'data', 'proto', 'protobuf']
            for sibling in common_siblings:
                if sibling != package_parts[-1]:  # 避免重复
                    candidates.append(f"{parent}.{sibling}")
        
        # 4. 根包下的常见子包
        if len(package_parts) > 2:
            root_package = '.'.join(package_parts[:2])  # 如 com.example
            common_subpackages = ['models', 'model', 'types', 'entities', 'common', 'shared', 'proto']
            for subpkg in common_subpackages:
                candidates.append(f"{root_package}.{subpkg}")
        
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
        查找最佳匹配的类（用于处理推断失败的情况）
        
        Args:
            type_name: 类型名（如 IdData）
            current_package: 当前包名
            current_class: 当前类名（用于分析源码）
            
        Returns:
            最佳匹配的完整类名
        """
        # 首先尝试从当前类的Java源码中获取实际类型
        if current_class:
            actual_type = self._extract_actual_field_type(current_class, type_name)
            if actual_type:
                self.logger.info(f"    🔍 源码分析: {type_name} -> {actual_type}")
                return actual_type
        
        # 如果源码分析失败，回退到模糊匹配
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
                    matching_classes.append((full_class_name, self._calculate_package_similarity(package_name, current_package)))
        
        if not matching_classes:
            return None
            
        # 按包名相似度排序，选择最佳匹配
        matching_classes.sort(key=lambda x: x[1], reverse=True)
        best_match = matching_classes[0][0]
        
        self.logger.info(f"    🔍 智能匹配: {type_name} -> {best_match}")
        return best_match

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
        从Java源码中提取字段的实际类型
        
        Args:
            class_name: 当前类的完整名称
            inferred_type: 推断出的类型名（如 IdData）
            
        Returns:
            实际的完整类型名
        """
        try:
            java_file = self._find_java_file(class_name)
            if not java_file:
                return None
                
            # 读取Java源码
            content = java_file.read_text(encoding='utf-8')
            
            # 查找字段声明模式：private SomeType fieldName_;
            # 我们要找的是以inferred_type结尾的类型声明
            import re
            
            # 匹配模式：private (.*IdData) .*_;
            pattern = rf'private\s+(\w*{re.escape(inferred_type)})\s+\w+_;'
            matches = re.findall(pattern, content)
            
            if matches:
                # 取第一个匹配的类型
                actual_type_simple = matches[0]
                
                # 检查是否有import语句
                import_pattern = rf'import\s+([^;]*\.{re.escape(actual_type_simple)});'
                import_matches = re.findall(import_pattern, content)
                
                if import_matches:
                    return import_matches[0]  # 返回完整的包名.类名
                else:
                    # 如果没有import，假设在同一个包中
                    package_name = '.'.join(class_name.split('.')[:-1])
                    return f"{package_name}.{actual_type_simple}"
            
            return None
            
        except Exception as e:
            self.logger.error(f"    ⚠️  源码分析失败: {e}")
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
                message_def, self.message_definitions
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
    
    @staticmethod
    def _to_snake_case(camel_str: str) -> str:
        """
        将CamelCase转换为snake_case
        
        Args:
            camel_str: 驼峰命名字符串
            
        Returns:
            蛇形命名字符串
        """
        # 处理连续大写字母：XMLParser -> XML_Parser
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camel_str)
        # 处理小写字母后跟大写字母：userId -> user_Id
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower() 