from setuptools import setup, find_packages

setup(
    name="filetool",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "Flask==2.3.3",
        "Werkzeug==2.3.7",
    ],
    entry_points={
        'console_scripts': [
            'filetool=launcher.main:main',
        ],
    },
)