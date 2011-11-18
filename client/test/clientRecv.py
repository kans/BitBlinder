#!/usr/bin/env python
import socket
import threading

#create an INET, STREAMing socket
serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#bind the socket to a public host, 
# and a well-known port
#host = socket.gethostname()   #returns ares
#host = "127.0.0.1"
host = ""
port = 80
serversocket.bind((host, port))
#become a server socket
serversocket.listen(5)

delim = "|"

def listen(sock):
  buf = ''
  while 1:
    chunk = sock.recv(4096)
    print chunk
#    while buf.find(delim) == -1:
#      chunk = sock.recv(4096)
#      print("CHUNK:<" + chunk + ">")
#      if chunk == '':
#        raise RuntimeError, "socket connection broken"
#      buf = buf + chunk
#    while buf.find(delim) != -1:
#      idx = buf.find(delim)
#      msg = buf[0:idx]
#      print("S: " + msg)
#      if idx < len(buf)-1:
#        buf = buf[idx+1:]
#      else:
#        buf = ''

while 1:
  #accept connections from outside
  (clientsocket, address) = serversocket.accept()
  th = threading.Thread(target=listen, args=[clientsocket])
  th.start()

#(clientsocket, address) = serversocket.accept()

#th.join()
resp = raw_input("Just hit enter to close.  ")
