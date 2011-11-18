#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
""""""

import re
import os

from common import Globals

product_name = 'BitBlinder'
version_short = None
mapbase64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.-'
VERSION_RE = re.compile("(?P<major>\d)\.(?P<minor>\d)\.(?P<micro>\d)(rc)?(?P<rc>\d)?")

def get_version_string():
  """creates a 4 byte string out of the globals version number"""
  versionMatches = VERSION_RE.match(Globals.VERSION)
  major = versionMatches.group("major")
  assert major, "No major version for the version number found"
  minor = versionMatches.group("minor")
  assert minor, "No minor version for the version number found"
  micro = versionMatches.group("micro") or 0 
  rc = versionMatches.group("rc") or 0
  version = '%s%s%s%s'% (major, minor, micro, rc)
  assert len(version) == 4, "Version string is too long or short"
  return version
  
def create_bt_id_header():
  """creates a bittorrent header id of the azureus form like so:
  '-AZ2060-' where our client id is BL
  """
  version = get_version_string()
  return '-BL%s-' % (version)

def createPeerID():
  """need to generate 12 random characters for our id as the
  header takes 6"""
  filler = os.urandom(12)
  header = create_bt_id_header()
  peerId = header + filler
  return peerId

version_short = get_version_string()
