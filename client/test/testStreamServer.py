#!/usr/bin/env python

import sys
sys.path.append("..")

import socket
import threading
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

#create an INET, STREAMing socket
serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#bind the socket to a public host
serversocket.bind(("", 60000))
#become a server socket
serversocket.listen(5)

def listen(sock):
  buf = ''
  sock = MessageSocket(sock)
  while 1:
    msg, rate = sock.read_message()
    if msg == "TEST_STREAM":
      th = threading.Thread(target=send, args=[sock, int(rate)])
      th.start()

def send(sock, rate):
  while 1:
    sock.write_message("DATA", '&' * rate)
    time.sleep(0.2)

while 1:
  #accept connections from outside
  (clientsocket, address) = serversocket.accept()
  th = threading.Thread(target=listen, args=[clientsocket])
  th.start()

#th.join()
resp = raw_input("Just hit enter to close.  ")