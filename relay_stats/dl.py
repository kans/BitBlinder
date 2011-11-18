#!/usr/bin/python

import os
import re
import httplib
import optparse

from serverCommon import Events
from serverCommon import EventLogging

#parse the options
parser = optparse.OptionParser()
parser.add_option("--live", action="store_true", dest="is_live", default=False)
parser.add_option("--dev", action="store_true", dest="is_dev", default=False)
(options, args) = parser.parse_args()
if options.is_live:
  from common.conf import Live as Conf
else:
  if not options.is_dev:
    print("You must use either the --live or --dev switches")
    sys.exit(1)
  from common.conf import Dev as Conf

#open the event logs
LOG_DIR = "/mnt/logs/consensus/"
if not os.path.exists(LOG_DIR):
  os.makedirs(LOG_DIR)
EventLogging.open_logs(os.path.join(LOG_DIR, "consensus_events.out"))

#get the document
conn = httplib.HTTPConnection("%s:%s" % (Conf.AUTH_SERVERS[0]["address"], Conf.AUTH_SERVERS[0]["dirport"]))
conn.request("GET", "/tor/status-vote/current/consensus")
response = conn.getresponse()
responseData = response.read()

#parse all of the bandwidths out of it
bandwidthRe = re.compile('w Bandwidth=(\d{1,10})')

#get bandwidth
bandwidths = [int(r) for r in bandwidthRe.findall(responseData)]
totalBandwidth = sum(bandwidths)
numRelays = len(bandwidths)
bandwidths.sort()
medianBandwidth = bandwidths[numRelays / 2]

#log the median bw, total bw, and number of relays
EventLogging.save_event(Events.NewConsensus(numRelays=numRelays, medianBandwidth=medianBandwidth, totalBandwidth=totalBandwidth))

#all done
EventLogging.close_logs()
