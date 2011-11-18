#!/usr/bin/python
import os
import random
from serverCommon import EventLogging
from serverCommon import Events

os.system("rm ./testevents.ou*") == 0
EventLogging.open_logs("testevents.out")

def random_hex(size):
  size /= 2
  data = "".join(chr(random.randrange(0, 256)) for i in xrange(size))
  return data.encode("hex")

def reduce_size(data, amount):
  keys = data.keys()
  count = 0
  for key in keys:
    del data[key]
    count += 1
    if count >= amount:
      return

emails = {}
for i in range(0,40):
  emails["%s@gmail.com"%(random_hex(10))] = random_hex(20)

for email, ref in emails.iteritems():
  EventLogging.save_event(Events.EmailSent(address=email, hexkey=ref))
reduce_size(emails, 5)

for email, ref in emails.iteritems():
  EventLogging.save_event(Events.EmailOpened(hexkey=ref))
  EventLogging.save_event(Events.EmailOpened(hexkey=ref))
reduce_size(emails, 5)

for email, ref in emails.iteritems():
  EventLogging.save_event(Events.EmailLinkVisit(hexkey=ref))
  EventLogging.save_event(Events.EmailLinkVisit(hexkey=ref))
reduce_size(emails, 5)

users = {}
for email, ref in emails.iteritems():
  username = random_hex(8)
  EventLogging.save_event(Events.AccountCreated(username=username, hexkey=ref))
  EventLogging.save_event(Events.AccountCreated(username=username, hexkey=ref))
  users[username] = ref
reduce_size(users, 5)

for username, ref in users.iteritems():
  EventLogging.save_event(Events.BankLogin(username=username))
  EventLogging.save_event(Events.BankLogin(username=username))

EventLogging.close_logs()

assert os.system("mv ./testevents.out.* ./testevents.out") == 0
