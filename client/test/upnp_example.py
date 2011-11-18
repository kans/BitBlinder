# (c) 2003 Myers Carpenter
import win32com.client

# The hard part is finding what VersionIndependentProgID to use
# This object is only used to get the collection of ports
theNatter = win32com.client.Dispatch("HNetCfg.NATUPnP")

# interface for this object at
# http://msdn.microsoft.com/library/default.asp?url=/library/en-us/ics/ics/istaticportmappingcollection.asp
mappingPorts = theNatter.StaticPortMappingCollection

def listPorts(mappingPorts):
    #Show the user how the ports are being used
    for ii in xrange(len(mappingPorts)):
        # the interface for the items in this collection is listed at
        # http://msdn.microsoft.com/library/default.asp?url=/library/en-us/ics/ics/istaticportmapping.asp
        mp = mps[ii]
        print "%d: %s %s %s %s %s %s %s" % (ii, mp.Enabled, mp.Description, mp.ExternalPort,
            mp.ExternalIPAddress, mp.Protocol, mp.InternalClient, mp.InternalPort,)

listPorts(mappingPorts)

# Add a port
mappingPorts.Add(1024, "TCP", 1024, "192.168.1.101", True, "IRC")

listPorts(mappingPorts)

# remove the forward that we added
# To uniquely specify a forward, you give the external port
# and the protocol
mappingPorts.Remove(1024, "TCP")

print "Done"
