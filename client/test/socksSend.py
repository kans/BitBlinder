#!/usr/bin/env python
import socket
import socks

##works:
#import urllib
#socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5,"127.0.0.1", 9050)
#socket.socket = socks.socksocket
#x = urllib.urlopen("http://www.sourceforge.net.ares.exit/")

#s = socks.socksocket()
#s.setproxy(socks.PROXY_TYPE_SOCKS5, addr="127.0.0.1", port=9050)
#s.connect(("127.0.0.1", 60301))
#s.sendall("hey hey hey" + "\n")

s = socks.socksocket()
s.setproxy(socks.PROXY_TYPE_SOCKS5, addr="127.0.0.1", port=9050)
s.connect(("innomi.net", 443))
s.sendall("hey hey hey" + "\n")

resp = raw_input("Just hit enter to close.  ")
