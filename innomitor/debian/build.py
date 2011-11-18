#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Builds Innomitor"""

import os
import sys
import subprocess
import optparse
import stat

import BaseDebFiles
from common import Globals
from common.system import Files
from common.utils.Build import syscall, check_build_assumptions, make_tar, PACKAGE_DIR

class Suite(object):
  """convenience object for describing a combo ubuntu + arch and some behaviors for it"""
  def __init__(self, ubuntu, arch):
    self.ubuntu = ubuntu
    self.arch = arch
    self.isInitialized = False
    
  def verify(self):
    """makes sure you didn't pass me stupid arguments"""
    self._verify_ubuntu_is_known()
    self._verify_arch_is_known()
    
  def is_initialized(self):
    """looks for the pbuilder tarball"""
    tarball = "%s-%s-base.tgz" % (self.ubuntu, self.arch)
    command = "ls %s" % BaseDebFiles.ROOT
    process = subprocess.Popen([command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    stdout = process.stdout.read()
    stderr = process.stderr.read()
    if stderr:
      self.isInitialized = False
      raise Exception(stderr)
    if not stdout:
      self.isInitialized = False
      print "Base tarball: %s was not found in %s (nor anything else for that matter)." % (tarball, BaseDebFiles.ROOT)
      return False
    files = stdout.split('\n')
    if tarball not in files:
      self.isInitialized = False
      print "Base tarball: %s was not found in %s." % (tarball, BaseDebFiles.ROOT)
      return False
    self.isInitialized = True
    print "Base tarball: %s was found in %s." % (tarball, BaseDebFiles.ROOT)
    return True
    
  def build(self, doUpdateBeforeBuild):
    """@param doUpdateBeforeBuild: whether to update the tar ball's environment before the actual build"""
    if doUpdateBeforeBuild:
      print "Updating suite: %s %s." % (self.ubuntu, self.arch)
      syscall("DIST=%s ARCH=%s pbuilder update" % (self.ubuntu, self.arch))
    else:
      print "Did not update suite: %s %s before the build." % (self.ubuntu, self.arch)
    print "building suite: %s %s" % (self.ubuntu, self.arch)
    #TODO: ostensibly, could use --debsign-k k415C9DD2 --auto-debsign to sign the deb, but something tries to stat a read only .changes file and fails...
    syscall("DIST=%s ARCH=%s pdebuild" % (self.ubuntu, self.arch))
    
  def initialize(self):
    """issues the system call to make our tarball"""
    command = "DIST=%s ARCH=%s pbuilder create" % (self.ubuntu, self.arch)
    print 'Making %s %s tarball.\nThis will take a few forevers.' % (self.ubuntu, self.arch)
    syscall(command)
  
  def _verify_ubuntu_is_known(self):
    """verifies that the ubuntu is in BaseDebFiles.KNOWN_UBUNTUS or dies"""
    assert self.ubuntu in BaseDebFiles.KNOWN_UBUNTUS, "Ubuntu suite not known: %s;\
      either append it to the suite in BaseDebFiles and the pbuilderrc file or pick one that exists: %s!" % (self.ubuntu, BaseDebFiles.KNOWN_UBUNTUS)
      
  def _verify_arch_is_known(self):
    """verifies that the arch is in BaseDebFiles.KNOWN_ARCHES or dies"""
    assert self.arch in BaseDebFiles.KNOWN_ARCHES, "Arch not known: %s; \
        pick one that exists: %s!" % (self.arch, BaseDebFiles.KNOWN_ARCHES)
    
  def __str__(self):
    return "%s %s" % (self.ubuntu, self.arch)
    
def create_parser():
  """creates our optparser to do the actual parsing of command line flags"""
  usage = "usage: python %prog [[--no-input] --version VERSION] --build suite-arch | --initialize suite-arch\nNote, either build, initialize, or neither must be specified along with the suite.\nNeither checks for initialization, then tries to build.\
  \nThe build suite should be passed LAST!"
  parser = optparse.OptionParser(usage)
  parser.add_option("--no-input", action="store_true", dest="noInput", default=False, help="Don't prompt about the changelog")
  parser.add_option("--no-update", action="store_false", dest="noUpdate", default=True, help="Don't update the tarball before building")
  parser.add_option("-us", "--upload-src", action="store_true", dest="uploadSource", default=False, help="Upload the source tar ball as well as the deb?")
  parser.add_option("-ud", "--upload-deb", dest="uploadDeb", default=None, type="string", metavar="old", help="Upload the deb- must specify old or new?")
  parser.add_option('-v', "--version", dest="version", metavar="0.5.5", default=Globals.VERSION, help='the innomitor deb version- defaults to globals.version')
  parser.add_option('-i', "--initialize", dest="initialize", action="store_true", default=False, 
                    help='signals to make the bass tarball- do not call with build, Note: you must also supply the suite to build, like jaunty-i386')
  parser.add_option('-b', "--build", dest="build", action="store_true", default=False,
                    help='makes the debian- do not call with the initialize flag, Note: you must also supply the suite to build, like jaunty-i386Note: you must have called initialize for that suite first')
  return parser

def parse_and_verify_flags():
  """gets command line options and checks them"""
  parser = create_parser()
  (options, args) = parser.parse_args()
  
  assert args, 'You must call me with an ubuntu suite: me --build jaunty-i386.'
  assert not (options.initialize and options.build), 'You must call me with either initialize or build, not both.'
  
  suites = get_suites(args)
  verify_suites(suites)
  
  return (options, suites)

def get_suites(args):
  """parses the remaining arg string to extrac the ubuntu and arch we are building for
  @param initArgs: args that fulfill no requirement for an optparse options
  @type initArgs: list
  @returns a list of tuples of the form (ubuntu, arch)"""
  try:
    suites = []
    for arg in args:
      suiteArgs = arg.split('-')
      ubuntuSuite = Suite(*suiteArgs)
      suites.append(ubuntuSuite)
      print 'you passed me %s' % ubuntuSuite
    return suites
  except Exception, e:
    print 'you passed in incorrect arguments for the suite!\nThey must come at the end of the command line and be of the form: jaunty-i386 lucid-amd64.'
    raise Exception(e)
   
def verify_suites(suites):
  """verifies that the suites are correctly formated and are known or dies
  @param suites: the suites we are testing
  @type suites: get_suites return 
  @returns: None"""
  for suite in suites:
    assert suite, 'You must supply me with one or more suites and arch like so: me --initialize jaunty-i386 hardy-amd64 hardy-i386.'
    suite.verify()
    
def verify_backports_enabled():
  """checks for the backports in apt repo or dies"""
  enabled = False
  f = open('/etc/apt/sources.list')
  for line in f.readlines():
    if 'backports' in line and 'deb' in line:
      enabled = True
  f.close()
  assert enabled, "You must have backports enabled to build things, go edit /etc/apt/sources.list to enable them and then run sudo apt-get update."
  print 'Packports are enabled.'
      
def verify_required_packages():
  """verifies that the user has backports enabled for apt
  then, verifies that the BaseDebFiles required packages are installed in a probably correct manner"""
  
  #they really need to have backports enabled for a current copy of debootstrap from the devel branch
  verify_backports_enabled()
  
  def _is_package_installed(package):
    """does actual test for package installation through dpkg"""
    command = 'dpkg --get-selections | grep %s' % package
    process = subprocess.Popen([command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    stdout = process.stdout.read()
    stderr = process.stderr.read()
    if stderr:
      raise Exception(stderr)
    if not stdout:
      return False
    if 'install' in stdout:
      return True
    return False
  
  #check for the required packages
  uninstalledPackages = []
  for package in BaseDebFiles.REQUIRED_PACKAGES:
    packageIsInstalled = _is_package_installed(package)
    if not packageIsInstalled:
      uninstalledPackages.append(package)
  assert not uninstalledPackages, "Go install package(s): %s, then try again.\n" % (uninstalledPackages)
  print "All necessary packages are probably installed; on a side note, make sure debootstrap is up to date (I don't check)!\n"
  return 

def install_pdebuildrrc():
  """installs our rc file into the users ~ directory"""
  #convert the known ubuntus into a suitable format
  ubuntus = ' '.join(['"%s"'%s for s in BaseDebFiles.KNOWN_UBUNTUS])
  root = BaseDebFiles.ROOT
  pdebuilderrc = BaseDebFiles.BASE_PBUILDERRC_TEXT % (ubuntus, root, root, root, root)
  path = os.path.expanduser('~/.pbuilderrc')
  print 'Installed new pbuilder rc (nuked old one, since it uses absolute paths) file at: %s.' % (path)
  f = open(path, 'wb')
  f.write(pdebuilderrc)
  f.close()

def pdebuildrrc_exists():
  """verifies that the pdebuilderrc file exists
  this is necessary for pbuilder to work correctly"""
  path = os.path.expanduser('~/.pbuilderrc')
  if Files.file_exists(path):
    print 'Found the pbuilder rc file'
    return True
  print 'Did not find the pbuilder rc file.'
  return False
  
def get_uninitializied_suites(suites):
  """looks for the tar ball corresponding to the tar.gz root according to our rc file
  @returns: a list of unitializedSuites"""

  print "Checking for initialization."
  unitializedSuites = []
  for suite in suites:
    if not suite.is_initialized():
      unitializedSuites.append(suite)
  return unitializedSuites
  
def initialize(suites):
  """called to build a pbuilder tarball environment"""
  #check to see if they have the rc file installed...
  if pdebuildrrc_exists():
    #TODO: back it up- make sure not to nuke the backup after two runs
    pass
  install_pdebuildrrc()
  #need to make sure they can build the tarballs
  verify_required_packages()
  #create tar balls for each suite
  for suite in suites:
    suite.initialize()
  print '\n\n\nAll Done with initialization, now you can build stuffs!\n\n\n'
      
def pdebuild(suites, buildDir, doUpdateBeforeBuild=False):
  """does the actual build process"""
  cwd = os.getcwd()
  os.chdir(buildDir)
  for suite in suites:
    suite.build(doUpdateBeforeBuild)
  os.chdir(cwd)
  #syscall("mv %s/%s %s/" % (PACKAGE_DIR, DEB_NAME, ARCHIVE_DIR))
    
def build(options, suites):
  """the master build function
  checks that we can build, then does the work"""
  if options.version == Globals.VERSION:
    print "No version specified with --version flag, defaulting to %s." % (Globals.VERSION)
    
  if options.uploadDeb:
    uploadFolder = options.uploadDeb
    assert uploadFolder in ["old", "new"], "You must specify old or new for the upload folder, \
      as obviously debs can either go in innomitorDebOld or innomitorDebNew!."
  verify_required_packages()
  
  unitializedSuites = get_uninitializied_suites(suites)
  assert not unitializedSuites, "You must do initialize %s before doing a build." % (unitializedSuites)

  version = options.version
  TAR_NAME = "innomitor-%s.tar.gz" % (version)
  BASE_NAME = "innomitor"
  BUILD_DIR = "%s/%s-%s" % (PACKAGE_DIR, BASE_NAME, version)
  controlFile = BaseDebFiles.BASE_CONTROL_FILE_TEXT

  check_build_assumptions(BASE_NAME, version, BUILD_DIR, controlFile, options.noInput)
  print "Changing some permissions..."
  os.chmod('%s/autogen.sh' % (BUILD_DIR), stat.S_IXUSR)
  #no idea what needs to execute the rules file, maybe something stats it ?!?
  os.chmod('%s/debian/rules' %(BUILD_DIR), stat.S_IXUSR | stat.S_IWUSR | stat.S_IRUSR)
  make_tar(TAR_NAME, BUILD_DIR, BASE_NAME, version)
  
  pdebuild(suites, BUILD_DIR, options.noUpdate)
  
  print '\n\nAll done building.\n\n'
  
  #TODO: clean, upload file...
  #upload_file(DEB_NAME, "/home/web/media/distribution/%sDeb" % (BASE_NAME))
  #NOTE:  kinda weird.  Only want to upload this file once, so the 64bit machine does it...
#  if is64Bit:
#    upload_file(TAR_NAME, "/home/web/media/distribution/%sSource" % (BASE_NAME))

  
def main():
  """tries to determine the course of action from the flags, or dies"""
  
  options, suites = parse_and_verify_flags()
  
  if options.initialize:
    if options.uploadSource:
      print "Ignoring upload source argument."
    if options.uploadDeb:
      print "Ignoring upload deb argument."
    print "Starting to set up the build environment..."
    initialize(suites)
  elif options.build:
    print "Starting the build process..."
    build(options, suites)
  elif not options.initialize and not options.build:
    print "Doing the whole works..."
    unitializedSuites = get_uninitializied_suites(suites)
    if unitializedSuites:
      initialize(unitializedSuites)
    build(options, suites)
  else:
    print "I don't know what to do: /wrists."
    sys.exit(-1)
    
if __name__ == "__main__":
  main()
