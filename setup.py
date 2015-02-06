#!/usr/bin/env python
from setuptools import setup, find_packages

version = '0.2.1'

setup(name='tenyks-cah',
      version=version,
      description="Cards Against Humanity service for Tenyks",
      long_description="""\
""",
      classifiers=[],  # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='clients cardsagainsthumanity tenyks ircbot services tenyks-service',
      author='Kyle Terry',
      author_email='kyle@kyleterry.com',
      url='https://github.com/kyleterry/tenyks-cah',
      license='LICENSE',
      packages=find_packages('tenykscah', exclude=['ez_setup', 'examples', 'tests']),
      package_dir={'': 'tenykscah'},
      package_data={'tenykscah': ['*.txt']},
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          # -*- Extra requirements: -*-
          'tenyksservice>=1.5',
          'python-dateutil',
          'requests',
          'nose',
      ],
      entry_points={
          'console_scripts': [
              'tenykscah = tenykscah.main:main',
          ]
      },
      )
