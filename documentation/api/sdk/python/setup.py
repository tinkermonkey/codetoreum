"""
Setup configuration for Codetoreum Python SDK
"""
from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="codetoreum-client",
    version="2.0.0",
    author="Codetoreum Team",
    author_email="support@codetoreum.com",
    description="Official Python client library for the Codetoreum AI Agent Orchestration Platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/codetoreum/codetoreum",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
    ],
    extras_require={
        "websocket": ["websockets>=11.0"],
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "mypy>=1.0",
            "flake8>=6.0",
            "types-requests>=2.28.0",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/codetoreum/codetoreum/issues",
        "Documentation": "https://docs.codetoreum.com",
        "Source": "https://github.com/codetoreum/codetoreum",
    },
)
