from setuptools import setup, find_packages

setup(
    name="sonopipe",
    version="1.2.0",
    description="Stream system audio from PC (Linux/Windows) to Android smartphone via ADB USB.",
    author="ADBSound Team",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "soundcard>=0.4.6",
        "PySide6>=6.5.0",
        "numpy>=1.20.0",
    ],
    entry_points={
        "console_scripts": [
            "sonopipe = sonopipe.main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Topic :: Multimedia :: Sound/Audio",
    ],
)
