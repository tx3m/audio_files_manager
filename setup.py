from setuptools import setup, find_packages
import platform

extras = []
if platform.system() == "Linux":
    extras.append("pyalsaaudio")
else:
    extras.append("sounddevice")
    extras.append("numpy")

setup(
    name='audio_file_manager',
    version='1.1',
    description='Cross-platform audio file staging, confirmation, and metadata manager for button-based recording',
    author='A.A.',
    packages=find_packages(),
    install_requires=extras,
    python_requires='>=3.7',
)
