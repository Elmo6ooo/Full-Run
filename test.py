from functions import *
import sys

devices = []
for i in range(1,len(sys.argv)):
    devices.append(sys.argv[i])

thread(devices, reset)