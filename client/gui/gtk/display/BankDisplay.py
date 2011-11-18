#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Show credits, allow users to get more credits"""

import time
import gtk
import gobject

import time
from twisted.internet.defer import Deferred

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Basic
from common.events import GlobalEvents
from common.classes import EncryptedDatagram
from gui import GUIController
from core import ClientUtil
from core.bank import ACoin
from core.bank import Bank
from core.bank import BankMessages
from core.bank import UDPPayment
from core.bank import ACoinRequestFactory
from core.bank import ACoinDepositFactory
from Applications import Tor
from Applications import CoreSettings

#: when the user's expected bank balance dips below this, we suggest that they become a relay...
LOW_MONEY_WARNING_LEVEL = 100L
#: whether the user has seen a warning about their lack of credits yet this run:
_showedLowMoneyWarning = False

class BankDisplay(GlobalEvents.GlobalEventMixin):
  def __init__(self):    
    ClientUtil.add_updater(self)
    #Statistics
    stat_vbox = gtk.VBox()
    self.statistics = {}
    for stat in ("Local Balance", "Bank Balance", "Credits Earned"):
      gtkObj = gtk.Label(stat+": ")
      gtkObj.stat_value = ""
      align = gtk.Alignment(xalign=0.0, yalign=0.5, xscale=0.0, yscale=0.0)
      align.add(gtkObj)
      align.set_padding(0, 0, 5, 0)
      stat_vbox.pack_end(align, False, False, 5)
      align.show()
      gtkObj.show()
      self.statistics[stat] = gtkObj
    stat_align = gtk.Alignment(xalign=0.0, yalign=0.5, xscale=0.0, yscale=0.0)
    stat_align.add(stat_vbox)
    stat_vbox.show()
    stat_align.show()
    
    self.payments = 0
    self.failures = 0
    self.withdrawals = 0
    self.deposits = 0
    self.TEST_DONE = True
    
    self.buttonRow = gtk.HBox()
    
    b = gtk.Button("Request ACoins")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.request_cb)
    
    b = gtk.Button("Deposit ACoins")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.deposit_cb)
    
    b = gtk.Button("ACoin Payment")
    self.buttonRow.pack_start(b)
    b.connect('clicked', self.payment_cb)
    
    self.buttonRow.show_all()
    
    self.entry = gtk.Entry(0)
    self.entry.connect('activate', self.entry_cb)
    balanceEntryBox = gtk.HBox()
    balanceEntryBox.pack_start(gtk.Label("Pretend bank balance is:  "), False, False, 0)
    balanceEntryBox.pack_start(self.entry, True, True, 0)
    
    #Glue:
    self.vbox = gtk.VBox()
    self.vbox.pack_start(stat_align, False, False, 10)
    self.vbox.pack_end(self.buttonRow, False, False, 10)
    self.vbox.pack_end(balanceEntryBox, False, False, 10)
    self.vbox.show()
    
    self.container = self.vbox
    self.label = gtk.Label("Bank")
    return
  
  def entry_cb(self, *args):
    balance = int(self.entry.get_text())
    Bank.get()._forceSetBalance = balance
    Bank.get().on_new_balance_from_bank(balance)
    
  def request_cb(self, widget, event=None):
    """Attempts to get the acoin low level number of coins- for debugging only.
    Note, this might send the number past the high level at which point the client
    will automatically attempt to deposit coins to meet the target level"""

    Bank.get().request_coins(1, Bank.ACOIN_LOW_LEVEL)
    
  def payment_cb(self, widget, event = None):
    self.start_payment_loop()
#    self.startTime = time.time()
#    self.payments = 0
#    self.failures = 0
#    self.withdrawals = 0
#    self.deposits = 0
#    NUM_PAYMENTS = 80.0
#    TEST_INTERVAL = 10.0
#    STATS_DELAY = 5.0
#    self.TEST_DONE = False
#    j=0
##    for j in range(0, int(TEST_INTERVAL)):
#    for i in range(0, int(NUM_PAYMENTS)):
#        t = j+i*(1.0/NUM_PAYMENTS)
##        print t
##        Scheduler.schedule_once(t, self.start_withdrawal_loop)
#        Scheduler.schedule_once(t, self.start_payment_loop)
#    def finish_test():
#      #self.TEST_DONE = True
#      elapsedTime = float(time.time()-self.startTime)
#      log_msg("\n\nCompleted %s payments per second\n\n" % (float(self.payments)/elapsedTime))
##      log_msg("\n\nCompleted %s withdrawals per second\n\n" % (float(self.withdrawals)/elapsedTime))
##      def stats():
##        log_msg("\n\nCompleted %s payments per second\n\n" % (float(self.payments)/float(time.time()-STATS_DELAY-self.startTime)))
##      Scheduler.schedule_once(STATS_DELAY, stats)
#    Scheduler.schedule_once(TEST_INTERVAL, finish_test)
    
  def start_deposit_loop(self):
    coin = Bank.get().get_acoins(1)
    if not coin:
      log_msg("No ACoins left!")
      return
    Globals.reactor.connectTCP(Bank.get().host, Bank.get().port, ACoinDepositFactory.ACoinDepositFactory(Bank.get(), coin))
    
  def start_withdrawal_loop(self):
    Globals.reactor.connectTCP(Bank.get().host, Bank.get().port, ACoinRequestFactory.ACoinRequestFactory(Bank.get(), 1, 40))
    
  def start_payment_loop(self):
    coin = Bank.get().get_acoins(1)
    if not coin:
      log_msg("No ACoins left!")
      return
    coin = coin[0]
    #generate ACoin request
    request = BankMessages.make_acoin_request(Bank.get(), Bank.get().currentACoinInterval, 1)
    #make the message:
    bankMsg = Basic.write_byte(1)
    bankMsg += coin.write_binary() + request.msg
    key = EncryptedDatagram.ClientSymKey(Bank.get().PUBLIC_KEY)
    bankMsg = Basic.write_byte(1) + key.encrypt(Basic.write_byte(3) + bankMsg)
    payment = UDPPayment.UDPPayment(Bank.get(), bankMsg)
    paymentDeferred = payment.get_deferred()
    def success(result, request=request):
      log_msg("success")
      self.payments += 1
#      self.start_payment_loop()
      #validate the ACoin
      code, sig = Basic.read_byte(result)
      coin = BankMessages.parse_acoin_response(Bank.get(), sig, request, False)
      if not coin:
        log_msg("Invalid ACoin sent for payment!")
      else:
        Bank.get().on_earned_coin(coin)
    paymentDeferred.addCallback(success)
    def failure(error):
      self.start_payment_loop()
      log_ex(error, "Failure during test?")
      self.failures += 1
    paymentDeferred.addErrback(failure)
    
  #JUST FOR DEBUGGING:
  def deposit_cb(self, widget, event=None):
    """Attempts to deposit all coins- for debugging only"""
    coins = Bank.get().get_acoins(Bank.get().get_wallet_balance())
    if not coins:
      log_msg("No ACoins left!")
      return
    Bank.get().deposit_acoins(coins)
   
  def on_update(self):
    """is responsible for updating the stat_dict"""
    global _showedLowMoneyWarning
    currentBalance = Bank.get().get_expected_balance()
    #if you have <HIGH_WATER credits:
    if currentBalance < LOW_MONEY_WARNING_LEVEL:
      #if you are NOT correctly set up as a relay, inform the user that they must be a relay for this system to keep working
      #are we not yet acting as a relay?
      if not Tor.get().settings.beRelay:
        #have we already warned them?
        if not _showedLowMoneyWarning:
          _showedLowMoneyWarning = True
          #Prompt the user about whether they want to run a relay and earn credits or not:
          if CoreSettings.get().askAboutRelay:
            GUIController.get().on_low_credits()
    
    self.statistics["Local Balance"].stat_value = str(Bank.get().get_wallet_balance())
    self.statistics["Bank Balance"].stat_value = str(currentBalance)
    self.statistics["Credits Earned"].stat_value = str(Bank.get().get_earnings())
    for text, label in self.statistics.iteritems():
      label.set_text(text + ": "  + label.stat_value)

  
