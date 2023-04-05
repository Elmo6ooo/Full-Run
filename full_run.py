from functions import *
import sys

# set parameters
if len(sys.argv) > 1:
    platform = sys.argv[1].lower()
    build = sys.argv[2].lower()
    test_suite = sys.argv[3].lower()
    full_retry = int(sys.argv[4])
    triage_retry = int(sys.argv[5])
    devices = []
    s = ""
    for i in range(6,len(sys.argv)):
        devices.append(sys.argv[i])
        s += " -s "+sys.argv[i]
else:
    print("Which platform (sh, ...)")
    platform = input().lower()
    print("Which build (tm, udc, ...)")
    build = input().lower()
    print("Which testsuite (cts,gsi, ...)")
    test_suite = input().lower()
    print("Full run retry rounds")
    full_retry = int(input())
    print("Triage retry rounds")
    triage_retry = int(input())
    print("Devices serial number (33f983b8 b341002c ...)")
    tmp = input()
    devices = []
    s = ""
    for num in tmp.split(' '):
        devices.append(num)
        s += " -s "+num

# make sure device can be detected by adb devices
check_device_exist(devices)
# make sure sheet exist otherwise add new sheet to TMP
check_sheet_exist(build, platform,test_suite)
# run full run and retry
path = shard(test_suite, "", full_retry, devices, s)
# upload test result to TMP sheet. return: not found module
not_found = upload(test_suite, build, platform, path, True)
# retry entire cmds file 
path = shard(test_suite, single_cmd(), triage_retry, devices, s)
# upload triage result to TMP, set clear to False no need return
upload(test_suite, build, platform, path, False)
# retry 1:1 for bug open
thread(devices, triage_failure, test_suite, build, list_cmd(), platform)
print("Not Found Modules: ")
print(colored(not_found, 'red'))