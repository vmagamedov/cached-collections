from setuptools import setup

setup(
    name='cached-collections',
    version='0.1.0',
    description=('Synchronized between processes in-memory cache for storing '
                 'frequently used data'),
    author='Vladimir Magamedov',
    author_email='vladimir@magamedov.com',
    url='https://github.com/vmagamedov/cached-collections',
    py_modules=['cached_collections'],
    license='BSD',
    install_requires=['redis'],
)
