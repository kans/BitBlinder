#!/usr/bin/python
#Copyright 2008 InnomiNet
"""Contains a variety of globals and settings."""

import re
import os
import sys
import copy

#: current version
VERSION = "0.5.8"

#: what web servers to link and query:
BASE_HTTP = "http://www.bitblinder.com"
BASE_HTTPS = "https://www.bitblinder.com"

#: Whether to anonymize all of the log messages
CLEAN_LOGS = True
#: how many Tor cells make up 1MB of traffic (roughly)
#TODO:  change to this, which is more accurate:
#CELLS_PER_MB = ((1024 * 1024) / BYTES_PER_CELL) + 1
CELLS_PER_MB = 2048
#: How many relayed data cells are allowed for each payment?  (5MB)
CELLS_PER_PAYMENT = 5 * CELLS_PER_MB
#: How many bytes are relayed by each cell?
#TODO:  change to 498, which is correct  :(
BYTES_PER_CELL = 499
#: how much of a buffer should we pay for?  If the buffer is too low, and someone
#sends WAY more data than we expect before we can send more payments, the circuit
#will be hopefully paused until it gets paid...
LOW_PAR_BYTES = 1 * CELLS_PER_MB * BYTES_PER_CELL
#where to store images, data files, etc:
#TODO:  this is hardcoded in *Conf  :(
DATA_DIR = u"data"
#: where the windows exe's live
WINDOWS_BIN = u"windows\\bin"
#: where the user data lives:
USER_DATA_DIR = u"users"
#name of the downloaded update:
if sys.platform == "win32":
  #name of the Tor process:
  TOR_RE = re.compile("^tor\\.exe$", re.IGNORECASE)
  UPDATE_FILE_NAME = u"BitBlinderUpdate.exe"
else:
  #name of the Tor process:
  TOR_RE = re.compile("^innomitor$", re.IGNORECASE)
  #TODO:  linux updates need to retain the file name:
  UPDATE_FILE_NAME = u"BitBlinderUpdate.exe"
#: whether to allow multiple instances of innomitor and bitblinder to run at the same time
ALLOW_MULTIPLE_INSTANCES = False
#: how many bytes in the PAR symmetric key:
PAR_SYM_KEY_LEN = 32
#: how many bytes in the Tor identity key:
TOR_ID_KEY_BYTES = 128
#: how many bytes in the bank login token key:
TOKEN_KEY_BYTES = 128
#TODO:  move to Logging module.  Actually, a lot of these constant/variables should move out of here
#: a place to put all of our logs
LOG_FOLDER = u"logs"
#: filename for the bugreport:
BUG_REPORT_NAME = u'splort.zip'
#: Place to download a file from when launching a test:
#TEST_URL = 'http://www.bitblinder.com/media/temp.jpg'
TEST_URL = 'http://bitblinder.com/media/windows/bigdownload.temp'
#TEST_URL = 'http://torrent.ubuntu.com:6969/announce?uploaded=0&compact=1&numwant=200&no_peer_id=1&ip=67.16.3.24&info_hash=3%82%0D%B6%DD%5EY%28%D2%3B%C8%11%BB%AC%2FJ%E9L%B8%82&event=started&downloaded=0&key=e181c2b0&peer_id=-DE1100-eNDm.%7EgU9qMU&port=11060&supportcrypto=1&left=732766208'
#: FTP server info for bug report submission:
FTP_HOST = '174.129.199.15'
FTP_PORT = 33330
FTP_USER = 'laxituber'
FTP_PASSWORD = 'relaxatube'
#: default folder to save torrents:
TORRENT_FOLDER = u"torrentFolder"
#: how often to test whether our OR/DIR ports are reachable.
#: also renews UPNP at the same time
REACHABILITY_INTERVAL = 30 * 60.0
#TODO:  move this to be part of the Tor config.   I dont think we use it right now
#Default ports that require Stable routers for connecting to:
STABLE_PORTS = [21, 22, 706, 1863, 5050, 5190, 5222, 5223, 6667, 6697, 8300]
#: time between update() function calls (in seconds)
INTERVAL_BETWEEN_UPDATES = 1.0
#: the max number of circuits to open (per application).  NOTE:  this is not yet strictly followed (BT can open more when it needs a tracker, etc)
MAX_OPEN_CIRCUITS = 5
#: address for other local instances to connect to on startup (so they can pass argv and only one instance is ever running at once)
NOMNET_STARTUP_HOST = "127.0.0.1"
NOMNET_STARTUP_PORT = 50393
#: Mapping between lowercase 2-letter country codes and actual names:
COUNTRY_NAMES = None
#: Stores the fingerprint of our relay.  If None, then we have not initialized yet, or have no relay:
FINGERPRINT = None
#: how many bytes are in an ACoin?
ACOIN_BYTES = 32
#: how many bytes in an ACoin signature key?
ACOIN_KEY_BYTES = 96
#: how many bytes in our symmetric key
SYMMETRIC_KEY_BYTES = 32
#: How many bytes are in the fingerprint?  (half the number of hex characters)
HEX_ID_BYTES = 20
#: file with user settings for Tor
TOR_CONFIG_FILE_NAME = u"tor.conf"
#: just a constant because I'm sick of remembering 65536.  Represents the range of valid port numbers:
PORT_RANGE = (0, 65535)
#TODO:  change to 443/80
#: tor defaults:
TOR_DEFAULT_OR_PORT = 10001
TOR_DEFAULT_DIR_PORT = 10030
TOR_DEFAULT_SOCKS_PORT = 10050
TOR_DEFAULT_CONTROL_PORT = 10051
#: valid username regex:  A-Z, 0-9, and dash, underscore, middle spaces
USERNAME_REGEX = re.compile("^[a-z0-9_-][a-z0-9_ -]+[a-z0-9_-]$", re.IGNORECASE)

#: These are for the current running BitBlinder relay (its public and private key)
PRIVATE_KEY = None
PUBLIC_KEY = None
#: the Twisted reactor will be stored here as soon as it is installed
reactor = None
#: the logging object for writing to various logs
logger = None

DEFAULT_EXIT_POLICY_BASE = [
("ExitPolicy", "accept 127.0.0.1:60301"),
("ExitPolicy", "reject 0.0.0.0/8:*"),
("ExitPolicy", "reject 169.254.0.0/16:*"),
("ExitPolicy", "reject 127.0.0.0/8:*"),
("ExitPolicy", "reject 192.168.0.0/16:*"),
("ExitPolicy", "reject 10.0.0.0/8:*"),
("ExitPolicy", "reject 172.16.0.0/12:*"),
("ExitPolicy", "reject *:25"),
("ExitPolicy", "reject *:119"),
("ExitPolicy", "reject *:135-139"),
("ExitPolicy", "reject *:445")]

DEFAULT_EXIT_POLICY_ALL = copy.copy(DEFAULT_EXIT_POLICY_BASE) + [
("ExitPolicy", "accept *:*")]

DEFAULT_EXIT_POLICY_WEB = copy.copy(DEFAULT_EXIT_POLICY_BASE) + [
("ExitPolicy", "accept *:%s" % (TOR_DEFAULT_OR_PORT)),
("ExitPolicy", "accept *:%s" % (TOR_DEFAULT_DIR_PORT)),
("ExitPolicy", "accept *:80"),
("ExitPolicy", "accept *:443"),
("ExitPolicy", "reject *:*")]

DEFAULT_EXIT_POLICY_BITTORRENT = copy.copy(DEFAULT_EXIT_POLICY_BASE) + [
("ExitPolicy", "accept *:%s" % (TOR_DEFAULT_OR_PORT)),
("ExitPolicy", "accept *:%s" % (TOR_DEFAULT_DIR_PORT)),
("ExitPolicy", "reject *:80"),
("ExitPolicy", "reject *:443"),
("ExitPolicy", "accept *:*")]

DEFAULT_EXIT_POLICY_NONE = copy.copy(DEFAULT_EXIT_POLICY_BASE) + [
("ExitPolicy", "reject *:*")]

TORRC_DATA = [
("TestingTorNetwork", "1"),
#Ignore the situation that private relays are not aware of any name servers.
("ServerDNSAllowBrokenResolvConf", "1"),
#Allow router descriptors containing private IP addresses.
("DirAllowPrivateAddresses", "0"),
#Permit building circuits with relays in the same subnet.
("EnforceDistinctSubnets", "0"),
#Believe in DNS responses resolving to private IP addresses.
("ClientDNSRejectInternalAddresses", "0"),
#ClientDNSRejectInternalAddresses 1
#Allow exiting to private IP addresses. (This one is a matter of taste---it might be dangerous to make this a default in a private network, although people setting up private Tor networks should know what they are doing.)
("ExitPolicyRejectPrivate", "0"),
#For single hop circuits
("AllowSingleHopExits", "1"),
("ExcludeSingleHopRelays", "0"),
("AllowSingleHopCircuits", "1"),
]
