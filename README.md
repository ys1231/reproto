# Protobuf Reconstructor

🔧 **从JADX反编译的Java源码自动重构Protobuf .proto文件**

一个强大的逆向工程工具，能够从任何使用Google Protobuf Lite的Android应用中自动重构出完整的.proto文件结构。

## ✨ 特性

- 🎯 **精准解析**: 基于Google Protobuf Lite字节码的逆向工程
- 🔄 **递归依赖**: 自动发现和处理所有依赖的消息和枚举类型
- 📦 **完整支持**: 支持oneof、repeated、map、枚举等所有Protobuf特性
- 🌐 **通用性**: 适用于任何Android应用，无需硬编码映射
- 🚀 **高效处理**: 智能队列管理，避免重复处理
- 🧠 **智能推断**: 从Java源码直接读取类型信息，确保100%准确性
- 📝 **标准输出**: 严格遵循Google Proto Style Guide
- 📊 **结构化日志**: 基于loguru的专业日志系统

## 🛠️ 安装

### 方法1：直接运行
```bash
# 克隆项目
git clone git@github.com:ys1231/reproto.git
cd reproto

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py <java_sources_dir> <root_class> <output_dir>
```

### 方法2：安装为包
```bash
# 安装到系统
pip install -e .

# 使用命令行工具
proto-reconstructor <java_sources_dir> <root_class> <output_dir>
```

## 📖 使用方法

### 基本用法
```bash
python main.py ./out_jadx/sources com.example.Model ./protos_generated
```

### 完整参数
```bash
python main.py <java_sources_dir> <root_class> <output_dir> [--log-dir LOG_DIR] [--help]
```

### 参数说明
- `java_sources_dir`: JADX反编译的Java源码目录路径
- `root_class`: 要重构的根类完整类名（如：com.example.Model）
- `output_dir`: 生成的proto文件输出目录路径
- `--log-dir`: 日志文件输出目录（默认：./logs）
- `--help`: 显示帮助信息

### 示例
```bash
# 重构示例消息应用的数据模型
python main.py ./out_jadx/sources com.example.messaging.v1.models.MessageData ./protos_generated

# 指定日志目录
python main.py ./out_jadx/sources com.example.Model ./output --log-dir ./my_logs

# 重构其他应用的模型
python main.py /path/to/jadx/sources com.myapp.data.UserProfile ./output
```

## 🔍 工作原理

### 核心技术
1. **字节码解析**: 逆向工程Google Protobuf Lite的`newMessageInfo`调用
2. **依赖发现**: 递归分析Java文件中的类型引用
3. **智能推断**: 基于字段名和对象数组推断枚举和消息类型
4. **源码分析**: 直接从Java源码读取真实的字段类型声明
5. **标准生成**: 生成符合Protobuf规范的.proto文件

### 解析流程
```
Java源码 → 字节码提取 → 类型解码 → 依赖发现 → 源码验证 → Proto生成
```

## 📁 项目结构

```
proto_reconstructor/
├── main.py                     # 主程序入口
├── core/                       # 核心组件
│   ├── reconstructor.py        # 主协调器
│   └── info_decoder.py         # 字节码解码器
├── parsing/                    # 解析模块
│   ├── java_parser.py          # Java文件解析器
│   └── java_source_analyzer.py # Java源码分析器
├── generation/                 # 生成模块
│   └── proto_generator.py      # Proto文件生成器
├── models/                     # 数据模型

```

## 工作流程

1. 使用JADX反编译Android应用
2. 运行ReProto指定根Protobuf类
3. 自动解析所有相关类和依赖
4. 生成完整的.proto文件结构

## 输出示例

### 输入：Java源码

```java
public final class MessageData extends GeneratedMessageLite {
    private int dataCase_;
    private Object data_;
    
    public enum DataCase {
        TEXT_MESSAGE(1),
        MEDIA_MESSAGE(2),
        DATA_NOT_SET(0);
        
        private final int value;
        
        private DataCase(int value) {
            this.value = value;
        }
    }
    
    // 其他方法...
}
```

### 输出：Proto文件

```protobuf
syntax = "proto3";

package com.example.messaging.v1.models;

import "com/example/messaging/v1/models/message_data.proto";
import "com/example/messaging/v1/models/conversation_data.proto";

option java_package = "com.example.messaging.v1.models";
option java_multiple_files = true;

message MessageData {
  oneof data {
    TextMessage text_message = 1;
    MediaMessage media_message = 2;
  }
}
```

## 开发环境设置

### 使用Poetry

```bash
# 安装Poetry
curl -sSL https://install.python-poetry.org | python3 -

# 安装项目依赖
poetry install

# 进入虚拟环境
poetry shell
```

## 项目结构

```
reproto/
├── core/           # 核心重构逻辑
├── parsing/        # Java源码解析
├── generation/     # Proto文件生成
├── models/         # 数据模型定义
├── utils/          # 工具函数
└── main.py         # 入口点
```

## 🔧 配置选项

### 日志配置
```bash
# 指定日志目录
python main.py sources/ com.example.Model output/ --log-dir ./my_logs

# 日志文件格式: proto_reconstructor-YYYY-MM-DD-HH-MM-SS.log
# 例如: proto_reconstructor-2024-01-15-14-30-25.log
```

### 输出格式
生成的proto文件遵循Google Protobuf Style Guide：
- 文件名使用`snake_case.proto`格式
- 字段名使用`snake_case`
- 消息名使用`PascalCase`
- 枚举值使用`UPPER_SNAKE_CASE`
- 正确的包结构和导入语句

## 🏗️ 架构设计

本项目采用模块化设计，详细的架构说明请参考 [ARCHITECTURE.md](./ARCHITECTURE.md)。

核心模块：
- **Core Layer**: 主协调器 + 字节码解码器
- **Parsing Layer**: Java解析器 + 源码分析器  
- **Generation Layer**: Proto文件生成器
- **Model Layer**: 数据定义模型
- **Utility Layer**: 日志系统 + 文件工具


## 🤝 贡献

欢迎提交Issue和Pull Request！

### 代码规范
- 遵循PEP 8代码风格
- 使用类型注解
- 编写单元测试
- 更新文档

## 🙏 致谢

- Google Protobuf团队提供的优秀框架
- JADX项目提供的反编译工具
- 逆向工程社区的技术支持

---
