import sys

from setuptools import setup
from weatherflow2mqtt.__version__ import VERSION

if sys.version_info < (3,10):
    sys.exit('Sorry, Python < 3.10 is not supported')

install_requires = list(val.strip() for val in open('requirements.txt'))
tests_require = list(val.strip() for val in open('test_requirements.txt'))

setup(name='weatherflow2mqtt',
      version=VERSION,
      description=('WeatherFlow-2-MQTT for Home Assistant'),
      author='Bjarne Riis',
      author_email='bjarne@briis.com',
      url='https://github.com/briis/hass-weatherflow2mqtt',
      package_data={
          '': ['LICENSE.txt'],
          'weatherflow2mqtt': ['translations/*.json'],
      },
      include_package_data=True,
      packages=['weatherflow2mqtt'],
      entry_points={
          'console_scripts': [
              'weatherflow2mqtt = weatherflow2mqtt.__main__:main'
          ]
      },
      license='MIT',
      install_requires=install_requires,
      tests_require=tests_require,
      classifiers=[
        'Programming Language :: Python :: 3.10',
      ]

)
