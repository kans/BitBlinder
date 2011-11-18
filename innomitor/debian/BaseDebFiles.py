#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""A module that contains some debian files and other goodies that we have to dynamically build each run"""

#: possible ubuntus to build against
KNOWN_UBUNTUS = ["lucid", "karmic", "jaunty", "intrepid", "hardy"]
KNOWN_ARCHES  = ['amd64', 'i386']
REQUIRED_PACKAGES = ['pbuilder', 'debootstrap', 'devscripts']
ROOT = '/var/cache/pbuilder'

BASE_CONTROL_FILE_TEXT = """\
Source: innomitor
Section: comm
Priority: optional
Maintainer: Matt Kaniaris <kans@bitblinder.com>
Build-Depends: automake, debhelper (>= 4.1.65), libssl-dev, libssl0.9.8(>=0.9.8f-1), dpatch, zlib1g-dev, libevent-dev (>= 1.1), transfig, binutils (>= 2.14.90.0.7)
Standards-Version: 3.8.0

Package: innomitor
Architecture: any
Depends: libc6, adduser, libevent1 (>=1.3) | libevent-1.4-2 | libevent-dev (>=1.1)
Conflicts: libssl0.9.8 (<< 0.9.8g-4), python-bitblinder (<=0.3.6)
Description: Modified Tor Client for use with BitBlinder
 BitBlinder is built on top of the open source Tor project,
 though it uses its own public network.  Innomitor tunnels micropayments
 between tor relays to allow for an actual bandwidth 
 economy- the idea being to ensure that the network is fast
 for everyone by maintaining an adequate supply of bandwidth.
 Innomitor is not compatible with the Tor network and is named differently
 to play nicely with an existing Tor installation.
"""

BASE_PBUILDERRC_TEXT ="""\
# Codenames for Debian suites according to their alias. Update these when
# needed.
UNSTABLE_CODENAME="sid"
TESTING_CODENAME="squeeze"
STABLE_CODENAME="lenny"
STABLE_BACKPORTS_SUITE="$STABLE_CODENAME-backports"

# List of Debian suites.
DEBIAN_SUITES=($UNSTABLE_CODENAME $TESTING_CODENAME $STABLE_CODENAME
    "unstable" "testing" "stable")

# List of Ubuntu suites. Update these when needed.
UBUNTU_SUITES=(%s)

# Mirrors to use. Update these to your preferred mirror.
DEBIAN_MIRROR="ftp.us.debian.org"
UBUNTU_MIRROR="mirrors.kernel.org"

# Optionally use the changelog of a package to determine the suite to use if
# none set.
if [ -z "${DIST}" ] && [ -r "debian/changelog" ]; then
    DIST=$(dpkg-parsechangelog | awk '/^Distribution: / {print $2}')
    # Use the unstable suite for certain suite values.
    if $(echo "experimental UNRELEASED" | grep -q $DIST); then
        DIST="$UNSTABLE_CODENAME"
    fi
fi

# Optionally set a default distribution if none is used. Note that you can set
# your own default (i.e. ${DIST:="unstable"}).
: ${DIST:="$(lsb_release --short --codename)"}

# Optionally change Debian release states in $DIST to their names.
case "$DIST" in
    unstable)
        DIST="$UNSTABLE_CODENAME"
        ;;
    testing)
        DIST="$TESTING_CODENAME"
        ;;
    stable)
        DIST="$STABLE_CODENAME"
        ;;
esac

# Optionally set the architecture to the host architecture if none set. Note
# that you can set your own default (i.e. ${ARCH:="i386"}).
: ${ARCH:="$(dpkg --print-architecture)"}

NAME="$DIST"
if [ -n "${ARCH}" ]; then
    NAME="$NAME-$ARCH"
    DEBOOTSTRAPOPTS=("--arch" "$ARCH" "${DEBOOTSTRAPOPTS[@]}")
fi
BASETGZ="%s/$NAME-base.tgz" #./pbuilder_tarballs
DISTRIBUTION="$DIST"
BUILDRESULT="%s/$NAME/result/" #./debs
APTCACHE="%s/$NAME/aptcache/"
BUILDPLACE="%s/build/" #./pbuilder_temp

if $(echo ${DEBIAN_SUITES[@]} | grep -q $DIST); then
    # Debian configuration
    MIRRORSITE="http://$DEBIAN_MIRROR/debian/"
    COMPONENTS="main contrib non-free"
    # This is for enabling backports for the Debian stable suite.
    if $(echo "$STABLE_CODENAME stable" | grep -q $DIST); then
        EXTRAPACKAGES="$EXTRAPACKAGES debian-backports-keyring"
        OTHERMIRROR="$OTHERMIRROR | deb http://www.backports.org/debian $STABLE_BACKPORTS_SUITE $COMPONENTS"
    fi
elif $(echo ${UBUNTU_SUITES[@]} | grep -q $DIST); then
    # Ubuntu configuration
    MIRRORSITE="http://$UBUNTU_MIRROR/ubuntu/"
    COMPONENTS="main restricted universe multiverse"
else
    echo "Unknown distribution: $DIST"
    exit 1
fi
"""
