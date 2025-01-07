from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="s3hop",
    version="0.1.2",
    author="John Cummings",
    author_email="john@hamsti.co",
    description="A tool to copy files between S3 buckets across AWS accounts",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/thehamsti/s3hop",
    packages=find_packages(),
    license="MIT",
    classifiers=[
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.6",
    install_requires=[
        "boto3>=1.26.0",
        "botocore>=1.29.0",
        "tqdm>=4.65.0",
        "humanize>=4.6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "isort>=5.0.0",
            "flake8>=4.0.0",
            "build>=0.10.0",
            "twine>=4.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "s3hop=s3hop.cli:main",
        ],
    },
)
