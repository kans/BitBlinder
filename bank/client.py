# Copyright (c) 2008 Kans
# See LICENSE for details.

from twisted.internet import reactor, protocol
from twisted.protocols.basic import Int16StringReceiver as I
import time

global TEST_LOGIN_MESSAGE,  TEST_ACOIN_REQUEST #65537
TEST_LOGIN_MESSAGE = """LOGIN 65537 21301191353533816305461522730605208381291265231834528109575665104213133302659045798274685169665881175848507249502811 3E1783CF8631D9BD15E4568550AFB9AD6662E1AE 17679960004644593872563669678552833260188332978193562183212682523736198905068161654319377869928740207432040121140030 21139207504096030002684190427367327538509489721876821071592517545005838003900731229312960938255505578291225720777875"""

TEST_SCOIN_REQUEST="""6561C60178C9CB5EE0C47C8FC4D798DD95BB1DBB d1e3aa4c0504ea48d435d72cfc9fa32dd6f3e0d1e73f782263b654f612fffcae3f32e748ad031239ea52425be8c7b424a607f9321f0561756706393af7cc2a1f0af43b3424bbd85a0f556d05a1087ff53f8e511b48e0163fad6ab7e8bcd7564626d8cc144f34f063fd4bb80c9bb8ecca8915cc002b84c4a6bd6e032c359a39aa286e069b7cf28218cd6c134cb3acba99628236bd1f9b2e635f87d11b4bab202eee8190d2c373f248cdc069eed8f488b41f37d7d8d392b3c910280c26ac5b3e582a8435dab939d4dad0730d6012cef77903e58242bf9c791ef3728cd55f2e3dd0603f8208b61e29bd475ff5c82c866e5a2ef101dfd8e12968424b824a1d74ec4a7163779872cab79871449ea3127555ab66a0ed0206dc0c1d8753a38924973c61acd5ad8820ceae2207dfd7b1f15d631f8d12e1dec6f7cac0b0dbb1709d6747292839dcb0af5054aad5510ee47b8a8a9d3bc7e2876aade9b43bcd75720b532c2b"""

TEST_ACOIN_REQUEST="6561C60178C9CB5EE0C47C8FC4D798DD95BB1DBB 3a154874ea1b4176ad860c17ba7eb971040ce948bedf573e97a08619daa333f2ecb5193d1ffee59c21fc92020b1cc2ed231198c6288533ce9f83b34c154e786a06ce61779698aff7522d5d8cc2d724d54a913a00898845239f8a55ea21fd87ab0839933dccc45e989cf056f782d3a32b5f8c1ccbc31d0917b94d2270feea9727936d506663f5510d57a9a429b74bdecc"

test_deposit = "6561C60178C9CB5EE0C47C8FC4D798DD95BB1DBB 1d4a343b4e3f27dc6626a76fd04d4d529ad2073058aaf9b505f24dbd24107e9e0292589db92e96e851d78b93cd142dad80cb88fa3d10a5ae1adac12327d0d94a9df1edf71a5816ba5417f4ae95e986e2492f572a3f9411d8e8b940d537811f64f11f514fc65d2e129277384af3fef28847e2e702fdec933bd7cddfbf56ac49d08af1ae556b2d09fdf0f5d95601877ea18583842b4c23d9bbd02f155c919dd12e833c1f7071dff43d001fcba64482bc97f2738df87a36e3ad5e6b21abdea1b75ef9fec24f605a2485a4729c501e2d23795aa156b03c5250d1c621f2c5904b0934"

scoin = "6561C60178C9CB5EE0C47C8FC4D798DD95BB1DBB SCOIN_DEPOSIT 3 54 1 18433501684300172475182844141210172742504999558099243086877307031564931210744955993463283268799640186810779038945333 BB36F30EA4D75E2A56ED1BC5DA7D06E8D841BE97 6561C60178C9CB5EE0C47C8FC4D798DD95BB1DBB 17272985005729339437786177786230579434495573502503837224509404670358672444124551131934455402467868147172473480882339"
class GetAcoin(I):
  """Once connected, send a message, then print the result."""
  
  def connectionMade(self):
    #the request takes is prefixed by its length
    print('sending msg to server')
    self.a = time.time()
    self.sendString(scoin)
    
  def stringReceived(self, data):
    "As soon as any data is received, write it back."
    print "Server said:", data
    b = time.time()
    print("%s milliseconds"%((b-self.a)*1000))
    #self.sendString('received sym key!')
    self.transport.loseConnection()
  
  def connectionLost(self, reason):
    print ("connection lost: %s"%(reason))
  
  def connectionClosed(self, stuff):
    print ("connectionClosed: %s"%(stuff))

class Factory(protocol.ClientFactory):
  protocol = GetAcoin

  def clientConnectionFailed(self, connector, reason):
    print "Connection failed - goodbye!"
    reactor.stop()
  
  def clientConnectionLost(self, connector, reason):
    print "Connection lost - goodbye!"
    reactor.stop()

# this connects the protocol to a server runing on port 1092
def main():
  f = Factory()
  reactor.connectTCP("innomi.net", 33334, f,  timeout=5 )
  reactor.run()

# this only runs if the module was *not* imported
if __name__ == '__main__':
  main()
