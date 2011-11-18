#!/usr/bin/python
#Copyright 2008 InnomiNet
import os

#: base dev server address
DEV_SERVER = "192.168.1.121"
AUTHORITY_SERVERS = "174.143.240.110"

#: location of the bank server
LOGIN_SERVER_HOST = DEV_SERVER
#: clientside location of our SSL certs
BANK_CERTIFICATE = os.path.join("data", "server.crt")
WEB_CERTIFICATE = os.path.join("data", "web.crt")
#: length of tor consensus intervals
INTERVAL_MINUTES = 5

#: what web servers to link and query:
BASE_HTTP = "http://innomi.net"
BASE_HTTPS = "https://innomi.net"

SERVER_PORT = 33376
LOGIN_PORT = 33377

#: auth server details
AUTH_SERVERS = [
  { "v3ident":    "98F3E99CB993D6AC5BB80B8560AD80ABF389A7AC",
    "key":        "5FA1 51D8 803A 76F8 5812 A2FF 1586 DFE7 1999 5405",
    "address":    AUTHORITY_SERVERS,
    "orport":     "33370",
    "dirport":    "33371",
    "name":       "InnomiNetAuth1Dev"
  },
  { "v3ident":    "03624A0DB12AC7CA77C829CB9FD3DDB35A40FBB7",
    "key":        "DBE5 A0E3 E122 C67A CF22 BA02 44AE CCE9 7E3E 7B99",
    "address":    AUTHORITY_SERVERS,
    "orport":     "33372",
    "dirport":    "33373",
    "name":       "InnomiNetAuth2Dev"
  },
  { "v3ident":    "0361B04347FE6DCFA54D98A50AE5BCCC3D1F7597",
    "key":        "446D BB9A EC5A FE6A 799F 65B1 623D 34F9 80F2 85FD",
    "address":    AUTHORITY_SERVERS,
    "orport":     "33374",
    "dirport":    "33375",
    "name":       "InnomiNetAuth3Dev"
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
              "bank":        3,
              "dht":         4}
