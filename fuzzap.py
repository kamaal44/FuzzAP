#   Copyright 2013 Brendan Scherer
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#   Small portion of code was taken from Core Security Technologies' Power-saving DoS.
#   Their copyright follows, their code is marked below
#
#  Copyright (c) 2009 Core Security Technologies
#
#  Author: Leandro Meiners (lea@coresecurity.com)
# 
#  Permission to use, copy, modify, and distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
# 
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#  The common SSID list was pulled from https://wigle.net/gps/gps/Stat
#  The OUI vendor list was parsed from http://standards.ieee.org/develop/regauth/oui/oui.txt
#  for well known vendors (netgear, cisco, linksys, d-link, atheros, ralink, apple)

#!/usr/bin/python
import signal
import sys
import time
import logging
import argparse
import random
from multiprocessing import Process
from scapy.config import *
from scapy.layers.dot11 import *
from scapy.utils import *

logging.getLogger('scapy.runtime').setLevel(logging.ERROR)


class FuzzAP(object):
    def __init__(self, interface):
        self.interface = interface
        self.mlist = []
        self.sid = []
        self.ftime = time.time() * 1000000

    def uptime(self):
        microtime = int(round(time.time() * 1000000)) - self.ftime
        return microtime

    def generate_mac(self, ouifile):
        try:
            # Grab a common OUI from file based off of the IEEE list at
            # http://standards.ieee.org/develop/regauth/oui/oui.txt
            mac = random.choice(open(ouifile).readlines())

        except IOError as ioe:
            print 'Cannot read file. Does the file exist?: {0}: {1}'.format(ioe.errno, ioe.strerror)
            sys.exit(1)
        # We have to create the last three bits of the mac address
        # since we grabbed the first three from file
        loop = 0
        while loop < 3:

            # Generate a random integer between 0 and 255 to match the possible combinations for the MAC
            ranint = random.randint(0, 255)

            # We have an exception in case the random integer is less than 16,
            # as we would only get one character instead of two
            if ranint < 16:

                int2 = random.randint(0, 15)
                mac += ":" + hex(ranint)[2:] + hex(int2)[2:]
                loop += 1

            else:

                mac += ":" + hex(ranint)[2:]
                loop += 1

        # When we return the mac, it has newlines due to reading from file.
        # We need to strip those before we return the mac
        return mac.replace("\n", "")

    def beacon_frame(self, bssids, macaddrs, interface):
        while True:
            for n in range(len(bssids)):
                sendp(RadioTap() /
                      Dot11(addr1='ff:ff:ff:ff:ff:ff',
                            addr2=macaddrs[n],
                            addr3=macaddrs[n]) /
                      Dot11Beacon(cap='ESS', timestamp=self.uptime()) /
                      Dot11Elt(ID='SSID', info=bssids[n]) /
                      Dot11Elt(ID='Rates', info='\x82\x84\x0b\x16') /
                      Dot11Elt(ID='DSset', info="\x03") /
                      Dot11Elt(ID='TIM', info="\x00\x01\x00\x00"),
                      iface=interface, loop=0, verbose=False)
            time.sleep(.102)

    def load_vendor(self, num_of_aps, ouifile):
        # Generate some mac addresses and shove them in a list
        for n in range(num_of_aps):
            self.mlist.append(self.generate_mac(ouifile))

    def load_ssid(self, num_of_aps, ssidfile):
        # Grab some random SSIDs from the wigle list and shove'm in a list
        for n in range(num_of_aps):
            self.sid.append(self.generate_ssid(ssidfile))

    def generate_ssid(self, ssidfile):
        try:
            # Pull a random SSID from a file with the top 1000 most common SSIDs from https://wigle.net/gps/gps/Stat
            ssid = random.choice(open(ssidfile).readlines())
            # Return the SSID from file while stripping the new-line from the output
            return ssid.replace("\n", "")
        except IOError as ioer:
            print 'Could not open ssid.txt. Does the file exist? Do you have the correct permissions? {0}: {1}'.format(
                ioer.errno, ioer.strerror)
            sys.exit(1)

    def probe_response(self, ssid, macs, rates, stamac):
        sendp(RadioTap(present=18479L) /
              Dot11(addr2=macs, addr3=macs, addr1=stamac, FCfield=8L) /
              Dot11ProbeResp(beacon_interval=102, cap=12548L, timestamp=self.uptime()) /
              Dot11Elt(info=ssid, ID=0) /
              Dot11Elt(info=rates, ID=1) /
              Dot11Elt(info='\x01', ID=3, len=1) /
              Dot11Elt(info='\x00', ID=42, len=1) /
              Dot11Elt(
                  info='\x01\x00\x00\x0f\xac\x02\x02\x00\x00\x0f\xac\x02\x00\x0f\xac\x04\x01\x00\x00\x0f\xac\x02(\x00',
                  ID=48, len=24) /
              Dot11Elt(info='H`l', ID=50, len=3), iface=self.interface, loop=0, verbose=False)


def sig_int(sigint, frame):
    print('Shutting down....')
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('interface', help='Specifies the interface in monitor mode to use')
    parser.add_argument('APs', help='Number of fake access points to create', type=int)
    parser.add_argument('OUI', help='File with a OUI on each line')
    parser.add_argument('SSID', help='File with a SSID on each line')

    args = parser.parse_args()
    ifce = args.interface
    APs = args.APs
    oui = args.OUI
    ssid = args.SSID
    signal.signal(signal.SIGINT, sig_int)
    fuzz = FuzzAP(ifce)

    # load all of our MACs and SSIDs to spam
    fuzz.load_vendor(APs, oui)
    fuzz.load_ssid(APs,ssid)

    # Fork out the beacon frames
    Process(target=fuzz.beacon_frame, args=(fuzz.sid, fuzz.mlist, ifce)).start()

    # Start sniffing for probe request from our previously forked out
    # beacon frames, and grab the ssid, rates, and MAC they are referencing
    while True:
        ssid = None
        rates = None

        # start sniffing
        p = sniff(iface=ifce, count=1)[0]

        # If the sniffed packet is a probe request and is sending it to one of our MAC addresses
        if p.haslayer(Dot11ProbeReq) and p.addr1 in fuzz.mlist:
            pkt = p.getlayer(Dot11Elt)
            macs = p.addr1

            # Start Core Security's code
            while pkt:
                if pkt.ID == 0:
                    # ID 0's info portion of a 802.11 packet is the SSID, grab it
                    ssid = pkt.info
                if pkt.ID == 1:
                    # ID 1's info portion of a 802.11 packet is the supported rates, grab it
                    rates = pkt.info
                pkt = pkt.payload
            # End Core Security's code

            fuzz.probe_response(ssid, macs, rates, p.addr2)


if __name__ == "__main__":
    main()
