# SPDX-License-Identifier: BSD-3-Clause
# SPDX-FileCopyrightText: Czech Technical University in Prague

import os

from setuptools import find_packages, setup

package_name = 'cras_rqt_common'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        (os.path.join('share', package_name), ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Martin Pecka',
    maintainer_email='peckama2@fel.cvut.cz',
    description='Shared Python and Qt components for CRAS RQt plugins',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    license='BSD-3-Clause',
)
