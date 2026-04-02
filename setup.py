from setuptools import setup

setup(
    name="mac-disk-cleaner-cli",
    version="1.0.0",
    description="Interactive macOS disk space cleaner CLI",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="raghut",
    url="https://github.com/raghut/mac-disk-cleaner-cli",
    py_modules=["disk_cleaner"],
    entry_points={
        "console_scripts": [
            "disk-cleaner=disk_cleaner:main",
        ],
    },
    python_requires=">=3.6",
    license="MIT",
    classifiers=[
        "Operating System :: MacOS",
        "Environment :: Console",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
)
