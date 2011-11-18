#!/usr/bin/python
import os
import sys
import optparse
sys.path.append("../")
from common import Globals
from common.utils.Build import syscall, check_build_assumptions, upload_file, make_tar, build, PACKAGE_DIR

parser = optparse.OptionParser()
parser.add_option("--no-input", action="store_true", dest="noInput", default=False)
parser.add_option("--version", dest="version", metavar="VERSION", default=Globals.VERSION)
parser.add_option("--upload", dest="upload", action="store_true", default=False)
(options, args) = parser.parse_args()

VERSION = options.version
TAR_NAME = "bitblinder-%s.tar.gz" % (VERSION)
DEB_NAME = "python-bitblinder_%s_all.deb" % (VERSION)
BASE_NAME = "bitblinder"
BUILD_DIR = "%s/%s-%s" % (PACKAGE_DIR, BASE_NAME, VERSION)

CONTROL_FILE_TEXT = """Source: bitblinder
Section: comm
Priority: optional
Maintainer: Matt Kaniaris <kans@bitblinder.com>
Build-Depends: debhelper (>= 4.1.65), binutils (>= 2.14.90.0.7), python-support (>= 0.3), python-dev, python-setuptools, devscripts
Standards-Version: 3.8.0
XS-Python-Version: 2.5, 2.6

Package: python-bitblinder
Architecture: all
Depends: ${python:Depends}, python-twisted (>=2.5.0), python-twisted-web, python-m2crypto, innomitor (>=0.5.0), python-gobject(>=2.0)
Recommends: python-gtk2 (>=2.0)
Description: Anonymous BitTorrent client and platform
 BitBlinder is built on top of the open source Tor project,
 though it uses its own network and client, innomitor.
 The goal of BitBlinder is to make Tor faster and more 
 user friendly even if it needs to sacrifice some
 anonymity.  If you need strong anonymity, use Tor instead.  
 BitBlinder includes a custom BitTorrent client (a fork of 
 BitTornado.)
"""
  
check_build_assumptions(BASE_NAME, VERSION, BUILD_DIR, CONTROL_FILE_TEXT, options.noInput)
syscall("cp %s/debian/setup.py %s/." % (BUILD_DIR, BUILD_DIR))
syscall("rm -rf %s/windows %s/experiments" % (BUILD_DIR, BUILD_DIR))
make_tar(TAR_NAME, BUILD_DIR, BASE_NAME, VERSION)
build(BUILD_DIR, DEB_NAME)
print "upload is: %s" % (options.upload)
if options.upload:
  upload_file(DEB_NAME, "/home/web/media/distribution/%sDeb" % (BASE_NAME))
  upload_file(TAR_NAME, "/home/web/media/distribution/%sSource" % (BASE_NAME))
