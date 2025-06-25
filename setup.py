#!/usr/bin/env python3
"""
Protobuf重构器安装脚本
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取README文件
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding='utf-8') if readme_file.exists() else ""

# 读取requirements文件
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = requirements_file.read_text().strip().split('\n')
    requirements = [req.strip() for req in requirements if req.strip() and not req.startswith('#')]

setup(
    name="proto-reconstructor",
    version="1.0.0",
    description="从JADX反编译的Java源码自动重构Protobuf .proto文件",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="AI Assistant",
    python_requires=">=3.8",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'proto-reconstructor=main:main',
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Code Generators", 
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="protobuf reverse-engineering jadx android decompiler",
) 