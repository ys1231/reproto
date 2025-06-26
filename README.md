# Protobuf Reconstructor

🔧 **从JADX反编译的Java源码自动重构Protobuf .proto文件**

一个强大的逆向工程工具，能够从任何使用Google Protobuf Lite的Android应用中自动重构出完整的.proto文件结构。

## ✨ 特性

- 🎯 **精准解析**: 基于Google Protobuf Lite字节码的逆向工程
- 🔄 **递归依赖**: 自动发现和处理所有依赖的消息和枚举类型
- 📦 **完整支持**: 支持oneof、repeated、map、枚举等所有Protobuf特性
- 🌐 **通用性**: 适用于任何Android应用，无需硬编码映射
- 🧠 **智能推断**: 从Java源码直接读取类型信息，确保高准确性
- 📝 **标准输出**: 严格遵循Google Proto Style Guide

## 🛠️ 安装

```bash
# 克隆项目
git clone https://github.com/ys1231/reproto.git
cd reproto

# 安装依赖
pip install -r requirements.txt
```

## 📖 使用方法

### 基本用法
```bash
python main.py <java_sources_dir> <root_class> <output_dir> [--verbose]
```

### 参数说明
- `java_sources_dir`: JADX反编译的Java源码目录路径
- `root_class`: 要重构的根类完整类名（如：com.example.Model）
- `output_dir`: 生成的proto文件输出目录路径
- `--verbose`: 显示详细处理信息

### 示例
```bash
# 重构消息应用的数据模型
python main.py ./out_jadx/sources com.example.messaging.v1.models.MessageData ./protos_generated --verbose

# 重构内部类
python main.py ./out_jadx/sources 'com.truecaller.accountonboarding.v1.Models$Onboarded' ./output --verbose
```

## 🔍 工作原理

### 核心技术
1. **字节码解析**: 逆向工程Google Protobuf Lite的`newMessageInfo`调用
2. **依赖发现**: 递归分析Java文件中的类型引用
3. **智能推断**: 基于字段名和对象数组推断枚举和消息类型
4. **源码分析**: 直接从Java源码读取真实的字段类型声明

### 解析流程
```
Java源码 → 字节码提取 → 类型解码 → 依赖发现 → 源码验证 → Proto生成
```

## 📁 项目结构

```
reproto/
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
└── utils/                      # 工具函数
```

## 📊 输出示例

### 输入：Java源码
```java
public final class MessageData extends GeneratedMessageLite {
    public static final int TEXT_MESSAGE_FIELD_NUMBER = 1;
    public static final int MEDIA_MESSAGE_FIELD_NUMBER = 2;
    
    private int dataCase_;
    private Object data_;
    
    public enum DataCase {
        TEXT_MESSAGE(1),
        MEDIA_MESSAGE(2),
        DATA_NOT_SET(0);
    }
}
```

### 输出：Proto文件
```protobuf
syntax = "proto3";

package com.example.messaging.v1.models;

option java_package = "com.example.messaging.v1.models";
option java_multiple_files = true;

message MessageData {
  oneof data {
    TextMessage text_message = 1;
    MediaMessage media_message = 2;
  }
}
```

## 🚀 工作流程

1. 使用JADX反编译Android应用：`jadx -d out_jadx app.apk`
2. 运行ReProto指定根Protobuf类
3. 自动解析所有相关类和依赖
4. 生成完整的.proto文件结构

## 📝 配置选项

### 日志配置
- 日志文件自动保存到 `./logs/` 目录
- 文件格式: `reproto-YYYY-MM-DD-HH-MM-SS.log`
- 使用 `--verbose` 参数查看详细处理过程

### 输出格式
生成的proto文件遵循Google Protobuf Style Guide：
- 文件名：`snake_case.proto`
- 字段名：`snake_case`
- 消息名：`PascalCase`
- 枚举值：`UPPER_SNAKE_CASE`

## 🔧 开发

```bash
# 使用Poetry管理依赖
poetry install
poetry shell

# 运行测试
python main.py ../out_jadx/sources 'com.example.TestClass' ../test_output --verbose
```

## 📄 许可证

本项目为私有项目，仅供授权用户使用。

---
