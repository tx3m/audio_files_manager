from setuptools import setup, find_packages
import platform

# Base dependencies
base_deps = []

# Platform-specific audio dependencies
audio_deps = []
if platform.system() == "Linux":
    audio_deps.append("pyalsaaudio>=0.8.0")
else:
    audio_deps.extend(["sounddevice>=0.4.0", "numpy>=1.19.0"])

# All dependencies
install_requires = base_deps + audio_deps

# Optional dependencies for enhanced features
extras_require = {
    'dev': [
        'pytest>=6.0.0',
        'pytest-cov>=2.10.0',
        'black>=21.0.0',
        'flake8>=3.8.0',
        'coverage>=5.0.0',
    ],
    'legacy': [
        # Dependencies for legacy service integration
    ],
    'all': [
        'pyalsaaudio>=0.8.0',  # For Linux support
        'sounddevice>=0.4.0',  # For Windows/macOS support
        'numpy>=1.19.0',       # For sounddevice
    ]
}

setup(
    name='audio_file_manager',
    version='2.0.0',
    description='Enhanced cross-platform audio file manager with OS abstraction, legacy compatibility, and advanced features',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='A.A.',
    packages=find_packages(),
    install_requires=install_requires,
    extras_require=extras_require,
    python_requires='>=3.7',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Operating System :: OS Independent',
        'Topic :: Multimedia :: Sound/Audio',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    keywords='audio recording playback cross-platform alsa sounddevice',
    entry_points={
        'console_scripts': [
            'audio-manager-demo=example_enhanced_manager:main',
            'audio-record-demo=enhanced_record_example:main',
        ],
    },
)
