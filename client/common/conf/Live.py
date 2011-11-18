#!/usr/bin/python
#Copyright 2008 InnomiNet
import os

from common import Globals

#: location of the bank server
LOGIN_SERVER_HOST = "login.bitblinder.com"
#: clientside location of SSL certs
BANK_CERTIFICATE = os.path.join("data", "server.crt")
WEB_CERTIFICATE = os.path.join("data", "web.crt")
#: how long the tor consensus intervals are
INTERVAL_MINUTES = 15

#: what web servers to link and query:
BASE_HTTP = Globals.BASE_HTTP
BASE_HTTPS = Globals.BASE_HTTPS

SERVER_PORT = 33348
LOGIN_PORT = 33349

#: tor authority server details
AUTH_SERVERS = [
  { "v3ident":    "98F3E99CB993D6AC5BB80B8560AD80ABF389A7AC",
    "key":        "5FA1 51D8 803A 76F8 5812 A2FF 1586 DFE7 1999 5405",
    "address":    "174.129.199.15",
    "orport":     "33350",
    "dirport":    "33351",
    "name":       "InnomiNetAuth1"
  },
  { "v3ident":    "03624A0DB12AC7CA77C829CB9FD3DDB35A40FBB7",
    "key":        "DBE5 A0E3 E122 C67A CF22 BA02 44AE CCE9 7E3E 7B99",
    "address":    "174.143.240.110",
    "orport":     "33352",
    "dirport":    "33353",
    "name":       "InnomiNetAuth2"
  },
  { "v3ident":    "0361B04347FE6DCFA54D98A50AE5BCCC3D1F7597",
    "key":        "446D BB9A EC5A FE6A 799F 65B1 623D 34F9 80F2 85FD",
    "address":    "174.129.199.15",
    "orport":     "33354",
    "dirport":    "33355",
    "name":       "InnomiNetAuth3"
  }
]

CLIENT_EVENT_LOGGING_LEVELS = {
              "tracker":     4,
              "btprotocol":  2,
              "btconn":      3,
              "socks":       0,
              "circuit":     3,
              "stream":      3,
              "par":         3,
              "portforward": 2,
              "gui":         3,
              "bank":        4,
              "dht":         4}
