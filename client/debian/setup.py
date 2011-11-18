#!/usr/bin/env python

# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Distutils installer for BitBlinder
"""
import sys
sys.path.append("./bitblinder")
sys.path.append("/home/build/client")
print sys.path
from common import Globals

if sys.version_info < (2,4):
    print >>sys.stderr, "You must use at least Python 2.4 for BitBlinder"
    sys.exit(3)

from distutils.core import setup
from setuptools import find_packages
packages=find_packages() #get all dirs
for position, package in enumerate(packages):
    packages[position]= '.'.join(['bitblinder',package]) #add bitblinder to the front
packages.append('bitblinder') #we need the root dir too
setup(
    name="bitblinder",
    version=Globals.VERSION,
    description="An anonymous bitTorrent client written in Python",
    author="InnomiNet LLC",
    author_email="kans@bitblinder.com",
    maintainer="Matt Kaniaris",
    maintainer_email="kans@bitblinder.com",
    url="%s/" % (Globals.BASE_HTTP),
    license="MIT",
    packages = packages,
    package_dir={'bitblinder': "."},
    package_data={'bitblinder':['data/*', 'innominetSettings.ini','licenses/Tor/*', 'licenses/Twisted-8.2.0/*', 'README.txt', 'logs/*', 'tor_data/*', 'common/keys/*']},
    long_description="""\
BitBlinder is an overlay anonymizing network built using the open
source Tor project.  Basically, people run proxies on their home 
computers and users bounce their traffic around through the network.

To keep the network fast, we require that users either give bandwidth
to the network or pay for the service.
""",
)



