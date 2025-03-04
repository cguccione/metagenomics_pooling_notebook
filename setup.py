#!/usr/bin/env python

# ----------------------------------------------------------------------------
# Copyright (c) 2015--, metapool development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
# ----------------------------------------------------------------------------

from setuptools import find_packages, setup

import versioneer

classifiers = [
    'Development Status :: 2 - Pre-Alpha',
    'License :: OSI Approved :: MIT License',
    'Environment :: Console',
    'Topic :: Software Development :: Libraries :: Application Frameworks',
    'Topic :: Scientific/Engineering',
    'Topic :: Scientific/Engineering :: Bio-Informatics',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Operating System :: Unix',
    'Operating System :: POSIX',
    'Operating System :: MacOS :: MacOS X',
    'Operating System :: Microsoft :: Windows']


description = 'Metagenomics pooling Jupyter notebook helper'

with open('README.md') as f:
    long_description = f.read()

keywords = 'microbiome wetlab bioinformatics',

base = ['numpy', 'pandas', 'matplotlib >= 2.0', 'seaborn >= 0.7.1', 'click',
        'sample_sheet', 'openpyxl']
test = ["nose", "pep8", "flake8"]
coverage = ['coverage']
notebook = ['jupyter', 'notebook', 'jupyter_contrib_nbextensions', 'watermark']
all_deps = base + test + coverage + notebook

setup(name='metapool',
      version=versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      license='MIT',
      description=description,
      long_description=long_description,
      keywords=keywords,
      classifiers=classifiers,
      author="Jon Sanders",
      maintainer="Jon Sanders",
      url='https://github.com/tanaes/metagenomics_pooling_notebook',
      test_suite='nose.collector',
      packages=find_packages(),
      package_data={
        'metapool': ['data/*.tsv', 'data/*.xlsx', 'tests/data/*.csv']},
      install_requires=base,
      extras_require={'test': test,
                      'coverage': coverage,
                      'all': all_deps},
      entry_points='''
          [console_scripts]
          seqpro=metapool.scripts.seqpro:format_preparation_files
      ''')
