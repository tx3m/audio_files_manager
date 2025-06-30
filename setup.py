from setuptools import setup, find_packages

setup(
    name='audio_file_manager',
    version='1.0',
    description='Audio file staging, confirmation, and metadata manager for button-based recording',
    author='A.A.',
    packages=find_packages(),
    install_requires=[
        'pyalsaaudio',
    ],
    python_requires='>=3.7',
)
