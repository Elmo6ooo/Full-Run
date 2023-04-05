import subprocess
import gspread
import datetime as dt
import time
import threading
from bs4 import BeautifulSoup
from oauth2client.service_account import ServiceAccountCredentials
from gspread.cell import Cell
from termcolor import colored

base_path = subprocess.Popen("cd ~/Downloads && pwd", shell=True, text=True,
								stdout=subprocess.PIPE).stdout.read().rstrip('\n')+"/"

# avoid devices run module at same time (tiage_failure)
previous_execute_time = 0

def thread(devices, targ, *options):
	threads = []
	for device in devices:
		t = threading.Thread(target = targ , args = (device, *options,))
		threads.append(t)
	#excute thread
	for i in range(len(devices)):
		threads[i].start()
	#wait for end of t
	for i in range(len(devices)):
		threads[i].join()

def check_device_exist(devices):
	check = process(["adb devices"], base_path)
	for device in devices:
		if device not in check:
			print(colored("Not found "+device+" in adb devices", 'red'))
			exit()

def check_sheet_exist(build, device, test_suite):
	sheet = build.upper() + "-" + device.upper() + "-" +test_suite.upper()
	scopes = ["https://spreadsheets.google.com/feeds"]
	credentials = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scopes)
	client = gspread.authorize(credentials)
	try:
		sheet = client.open_by_key("1eSp4g_2Z86MnZLUVljhMoDt1OgRIPeEV0KYMVq22zag").worksheet(sheet)
	except:
		print(colored("Not found "+sheet+" in TMP", 'red'))
		exit()

# factory reset
def reset(device):
	# check device adb enabled
	while True:
		fb = process(["adb devices"], base_path)
		if device in fb:
			break
	# bootloader and check fastboot enabled
	fb = process(["adb -s "+device+" reboot bootloader"], base_path)
	while True:
		fb = process(["fastboot devices"], base_path)
		if device in fb:
			break
	# fastboot -w aka factory reset & reboot
	fb =  process(["fastboot -s "+device+" -w"], base_path)
	while not "Erase successful" in fb: print("fastboot -w FAIL")
	fb = process(["fastboot -s "+device+" reboot"], base_path)
	# make sure device enable adb
	while True:
		fb = process(["adb devices"], base_path)
		if device in fb:
			break
	# enable location & wifi
	while True:
		fb = process(["adb -s "+device+" shell getprop sys.boot_completed"], base_path)
		if "1" in fb:
			break
	time.sleep(3)
	fb = process(["adb -s "+device+" shell input keyevent 4"], base_path)
	fb = process(["adb -s "+device+" shell cmd location set-location-enabled true"], base_path)
	fb = process(["adb -s "+device+" shell cmd wifi add-suggestion GoogleGuest-Legacy open"], base_path)

# subprocess
def process(cmd, dir):
	p = subprocess.Popen(cmd, shell=True, text=True, stdout=subprocess.PIPE,
							stderr=subprocess.STDOUT, cwd=dir, bufsize=-1)
	return p.stdout.read()

# get specific line
def select_line(string, line_index):
	return string.splitlines()[line_index]

# extract results time
def extract_time(target, log):
	i = 0
	while True:
		tmp = select_line(log, i)
		if target in tmp:
			Time = tmp[0:14]
			break
		i += 1
	Time = Time.replace(Time[2], '.').replace(Time[5],'_').replace(':','.')	
	return Time
	
# extract full_run session 
def extract_session(log, Time, session, pre_session_Fail):
	for x in log.splitlines():
		if "Fail" in x:
			for i in range(len(x)):
				if x[i] == 'F':
					index = i

		elif Time in x:
			new_session_fail = int(x[index:index+6])
			if(new_session_fail < pre_session_Fail):
				pre_session_Fail = new_session_fail
				session = int(x[0:3])
				break
			
		# this might not work when Time[sec] is 59
		elif Time.replace(Time[-1], str(int(Time[-1])+1)) in x: 
			new_session_fail = int(x[index:index+6])
			if(new_session_fail < pre_session_Fail):
				pre_session_Fail = new_session_fail
				session = int(x[0:3])
				break
	return session, pre_session_Fail

# full run and entire cmds. use cmds as switch.
def shard(test_suite, cmds, retry_round, devices, s): 
	# set dir and cmd for popen use
	if test_suite == 'gsi':
		dir = base_path+"android-cts"
		cmd = "./tools/cts-tradefed run commandAndExit cts-on-gsi "+cmds+"--shard-count "
	elif test_suite == 'sts':
		dir = base_path+"android-"+test_suite
		cmd = "./tools/sts-tradefed run commandAndExit sts-dynamic-full "+cmds+"--shard-count "
	else:
		dir = base_path+"android-"+test_suite
		cmd = "./tools/"+test_suite+"-tradefed run commandAndExit "+test_suite+" "+cmds+"--shard-count " 

	# To print logs
	log = subprocess.Popen([cmd+str(len(devices))+s], shell=True, text=True, stdout=subprocess.PIPE,
							stderr=subprocess.STDOUT, cwd=dir, bufsize=-1)
	# print logs and extract Time
	Time = ""
	while log.poll() == None:
		lg = log.stdout.readline()
		if "Skipping dynamic download due to local sharding detected." in lg:
			Time = extract_time("Skipping dynamic download due to local sharding detected.", lg)
		print(lg,end="")
		
	session = 0
	pre_session_Fail = 999999

	# retry
	for i in range(retry_round):
		# add factory reset
		thread(devices, reset)

		# get session from l r
		if test_suite == 'gsi':
			lr = process(["./tools/cts-tradefed l r"], dir)
		else:
			lr = process(["./tools/"+test_suite+"-tradefed l r"], dir)
		session, pre_session_Fail = extract_session(lr, Time, session, pre_session_Fail)

		# run retry
		if test_suite == 'gsi':
			rlog = process(["./tools/cts-tradefed run commandAndExit retry -r "+str(session)+" --shard-count "+str(len(devices))+s], dir)
		else:
			rlog = process(["./tools/"+test_suite+"-tradefed run commandAndExit retry -r "+str(session)+" --shard-count "+str(len(devices))+s], dir)

		# using terminal log to extract time 
		Time = extract_time("Skipping dynamic download due to local sharding detected.", rlog)

	# return path for upload.py
	if test_suite == 'gsi':
		lr = process(["./tools/cts-tradefed l r"], dir)
	else:
		lr = process(["./tools/"+test_suite+"-tradefed l r"], dir)

	result_dir = ""
	numFail = 9999999
	fail_index = 0
	result_index = 0
	for x in lr.splitlines():
		if "Fail" in x:
			for i in range(len(x)):
				if x[i] == 'F':
					fail_index = i
				if x[i] == 'R':
					result_index = i

		if test_suite+" " in x and not "unknown" in x: # +" " to avoid ats.json
			if int(x[fail_index:fail_index+6]) < numFail:
				numFail = int(x[fail_index:fail_index+6])
				result_dir = x[result_index:result_index+19]

	if test_suite == 'gsi':
		return base_path+"android-cts/results/"+result_dir+"/test_result_failures_suite.html"
	else:
		return base_path+"android-"+test_suite+"/results/"+result_dir+"/test_result_failures_suite.html"

def upload_cts(soup, sheet, dic, incompletes, cmds, fw, row_count, cells, cells2, not_found):
	# combine [instant] into the parent test ?? other[...]
	i = 0
	while i < len(cmds)-1:	
		if i != len(cmds)-2 and cmds[i] == cmds[i+2]:
			cmds[i+1] += cmds[i+3] + " "
			del cmds[i+2:i+4]
		i += 2
	
	# crawl data and keep it in result as string list
	rows = soup.find("table", {"class": "testsummary"}).find_all("tr")
	result = []
	k = 0
	for row in rows:
		if "Module" in str(row):
			continue
		r = []
		j = 0
		for i in row.find_all('td'):
			r.append(str(i).replace('<td>', '').replace('</td>',''))
			j = j+1 
		result.append(r)
		k = k+1
	
	#remove href & arm64-v8a
	for i in range(len(rows)-1):
		if "href" in result[i][0]:
			tmp = result[i][0].split(">")
			result[i][0] = tmp[1].replace('arm64-v8a ','').replace('</a','')
		else:
			tmp = result[i][0].split()
			result[i][0] = tmp[1]
	
	#0:Module, 1:Passed, 2:Failed, 3:Assumption Failure, 4:Ignored, 5:Total Tests, 6:Done
	while result:
		family = []
		family.append(0)
		i = 0 #constant
		j = 1 #check later result family or not
		while len(result) > 1:
			if len(result) <= j:	break
			elif result[i][0]+"[instant]" == result[j][0] or \
			result[i][0]+"[run-on-secondary-user]" == result[j][0] or \
			result[i][0]+"[run-on-work-profile]" == result[j][0] or \
			result[i][0]+"[run-on-clone-profile]" == result[j][0]:	
				family.append(j)
			if j == 20:	break
			else:	j = j+1
				
		P, F, A, I, T, D = (0,0,0,0,0,True)
		for k in family:		
			P = P + int(result[k][1])
			F = F + int(result[k][2])
			A = A + int(result[k][3])
			I = I + int(result[k][4])
			T = T + int(result[k][5])
			if result[k][6] == "false":
				D = False
			
		M = result[i][0]
		for k in reversed(family):
			result.pop(k)
		family.clear()

		# Add not found into dic
		if M not in dic:
			row_count += 1
			dic[M] = row_count
			sheet.append_row([M],table_range="A"+str(row_count))
			not_found.append(M)

		cells.append(Cell(dic[M], 2, T))			
		if F != 0 and D:
			cells.append(Cell(dic[M], 3, F))
			cells.append(Cell(dic[M], 4, 'FAIL'))		
		elif not D:
			cells.append(Cell(dic[M], 4, 'INCOMPLETED'))
		elif A == I and A == T:
			cells.append(Cell(dic[M], 4, 'NO RESULT'))
		elif I == T and I != 0:
			cells.append(Cell(dic[M], 4, 'IGNORED'))
		elif A != 0 and (A == T or A+I == T):
			cells.append(Cell(dic[M], 4, 'ASSUMPTION'))
		else:
			cells.append(Cell(dic[M], 4, 'PASS'))
		
		# find module and upload command
		if cmds and M == cmds[0]:
			
			# if failed == total tests then just filter the module
			if F == T:
				cells2.append(Cell(dic[M], 5, "--include-filter \"" + cmds[0] + "\""))
			else:
				cells2.append(Cell(dic[M], 5, cmds[1]))
			del cmds[0:2]

			# cells can only upload maximum 50000 char at once
			if sum(len(str(i)) for i in cells2) > 30000:
				sheet.update_cells(cells2)
				cells2.clear()
		
		# the rest of incomplete modules		
		if incompletes and M == incompletes[0]:
			fw.write("--include-filter \"" + incompletes[0] + "\" \n")
			cells2.append(Cell(dic[M], 5, "--include-filter \"" + incompletes[0] + "\""))
			del incompletes[0]
	
def upload_other(soup, sheet, dic, incompletes, cmds, fw, row_count, cells, cells2, not_found, clear):
	# crawl data and keep it in result as string list
		rows = soup.find("table", {"class": "testsummary"}).find_all("tr")
		result = []
		for row in rows:	
			for i in row.find_all('td'):
				result.append(str(i).replace('<td>', '').replace('</td>',''))

		# 0:Module, 1:Passed, 2:Failed, 3:Assumption Failure, 4:Ignored, 5:Total Tests, 6:Done
		for i in range(0, len(result), 7):
			# remove unnecessary data from Module
			if "href" in result[i]:
				tmp = result[i].split(">")
				result[i] = tmp[1].replace('arm64-v8a ','').replace('</a','')
			else:
				tmp = result[i].split()
				result[i] = tmp[1]

			M = result[i]

			# Add not found into dic
			if M not in dic:
				row_count += 1
				dic[M] = row_count
				sheet.append_row([M],table_range="A"+str(row_count))
				not_found.append(M)
				
			# data to upload
			if clear:
				cells.append(Cell(dic[M], 2, int(result[i+5])))
			if result[i+2] != '0' and result[i+6] == 'true':
				cells.append(Cell(dic[M], 3, int(result[i+2])))
				cells.append(Cell(dic[M], 4, 'FAIL'))
			elif result[i+6] == 'false':
				cells.append(Cell(dic[M], 4, 'INCOMPLETED'))
			elif result[i+3] == result[i+4] and result[i+3] == result[i+5]:
				cells.append(Cell(dic[M], 4, 'NO RESULT'))
			elif result[i+4] == result[i+5] and result[i+4] != '0':
				cells.append(Cell(dic[M], 4, 'IGNORED'))
			elif result[i+3] != '0' and (result[i+4] == result[i+5] or int(result[i+3])+int(result[i+4]) == int(result[i+5])):
				cells.append(Cell(dic[M], 4, 'ASSUMPTION'))
			else:
				cells.append(Cell(dic[M], 4, 'PASS'))

			# find module and upload command
			if cmds and M == cmds[0]:

				# if failed == total tests then just filter the module
				if result[i+2] == result[i+5]:
					cells2.append(Cell(dic[M], 5, "--include-filter \"" + cmds[0] + "\""))
				else:
					cells2.append(Cell(dic[M], 5, cmds[1]))
				del cmds[0:2]

				# cells can only upload maximum 50000 char at once
				if sum(len(str(i)) for i in cells2) > 30000:
					sheet.update_cells(cells2)
					cells2.clear()

			# the rest of incomplete modules
			if incompletes and M == incompletes[0]:
				fw.write("--include-filter \"" + incompletes[0] + "\" \n")
				cells2.append(Cell(dic[M], 5, "--include-filter \"" + incompletes[0] + "\""))
				del incompletes[0]

# upload to sheet & parse fail
def upload(test_suite, build, device, path, clear):
	sheet = build.upper() + "-" + device.upper() + "-" +test_suite.upper()
	with open(path) as fp:
		soup = BeautifulSoup(fp, 'lxml')

	scopes = ["https://spreadsheets.google.com/feeds"]
	credentials = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scopes)
	client = gspread.authorize(credentials)
	sheet = client.open_by_key("1eSp4g_2Z86MnZLUVljhMoDt1OgRIPeEV0KYMVq22zag").worksheet(sheet)

	# Not found (return value)
	row_count = sheet.row_count
	not_found = []

	# clear previous sheet result
	if clear:
		sheet.batch_clear(['B:E'])

	# keeps data that we want to upload
	cells = []		# basic results
	cells2 = []		# commands

	# create module dictionary
	dic = {}
	col = sheet.col_values(1)
	index = 1
	for i in col:
		dic[i] = index
		if clear:
			cells.append(Cell(dic[i], 4, 'REMOVE'))
		index = index + 1
	
	# get all module from testsummary
	all_module = []
	tests = soup.find("table", {"class": "testsummary"}).find_all("tr")
	for test in tests:
		if "Module" in str(test):
			continue
		for i in test.find_all('td'):
			if len(i.contents[0]) > 10:
				all_module.append(i.contents[0].split()[1])
			elif len(str(i)) > 20:
				all_module.append(str(i).split()[2].split('<')[0])

	# parse incompletemodules
	incompletes = []
	try:
		modules = soup.find('table', 'incompletemodules').find_all('td')
		for module in modules:
			module = module.contents[0].contents[0].split()[1]
			tmodule = module.replace("[instant]","").replace("[run-on-secondary-user]","") \
				.replace("[run-on-work-profile]","").replace("[run-on-clone-profile]","")
			if tmodule in all_module and tmodule not in incompletes:
				incompletes.append(tmodule)
			elif tmodule in all_module and tmodule in incompletes:
				next
			elif module not in incompletes:
				incompletes.append(module)
	except: pass
	backup_incompletes = incompletes.copy()

	# keep all commands
	cmds = []
	fw = open('./cmds','w')

	# parse testdetails turn into --include-filter, if incomplete just filter module
	tests = soup.find_all('table', 'testdetails')
	for test in tests:
		cmd = ""
		module = test.find('td', 'module').contents[0].contents[0].split()[1]
		tmodule = module.replace("[instant]","").replace("[run-on-secondary-user]","") \
			.replace("[run-on-work-profile]","").replace("[run-on-clone-profile]","")
		try: # combine child module to parent if there is one
			if tmodule in all_module or tmodule in incompletes:
				module = tmodule
		except: pass

		if module in incompletes:
			cmd += "--include-filter \"" + module + "\" "
			incompletes.remove(module)
		else:
			testcases = test.find_all('td', 'testname')
			for tc in testcases:
				cmd += "--include-filter \"" + module + " " + tc.contents[0] + "\" "
		try:
			if cmds[-2] and module != cmds[-2]:
				fw.write('\n')
		except: pass

		if module not in cmds:
			cmds.append(module)
			cmds.append(cmd)
			fw.write(cmd)
		elif module not in backup_incompletes and module == cmds[-2]:
			dif_testcase = cmd.split("\"")
			for i in range(1,len(dif_testcase),2):
				if dif_testcase[i] not in cmds[-1]:
					cmds[-1] += "--include-filter \""+dif_testcase[i]+ "\" "
					fw.write("--include-filter \""+dif_testcase[i]+ "\" ")
	fw.write('\n')

	if test_suite == "CTS":
		upload_cts(soup, sheet, dic, incompletes, cmds, fw, row_count, cells, cells2, not_found)
	else:
		upload_other(soup, sheet, dic, incompletes, cmds, fw, row_count, cells, cells2, not_found)
	
	fw.close()

	#upload data	
	sheet.update_cells(cells)
	sheet.update_cells(cells2)

	return not_found

# upload triage_failure pass result
def upload_single(test_suite, build, device, M):
	sheet = build.upper() + "-" + device.upper() + "-" +test_suite.upper()
	scopes = ["https://spreadsheets.google.com/feeds"]
	credentials = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scopes)
	client = gspread.authorize(credentials)
	sheet = client.open_by_key("1eSp4g_2Z86MnZLUVljhMoDt1OgRIPeEV0KYMVq22zag").worksheet(sheet)

	# create module dictionary
	dic = {}
	col = sheet.col_values(1)
	index = 1
	for i in col:
		dic[i] = index
		index = index + 1
	
	cells = []
	cells.append(Cell(dic[M], 3, ''))
	cells.append(Cell(dic[M], 4, 'PASS'))
	cells.append(Cell(dic[M], 5, ''))

	#upload data
	sheet.update_cells(cells)

# get data from log
def status(log,P,F,C,Run_time,A,I,T,remove):
	i = -1
	while True:
		tmp = select_line(log, i)
		if "PASSED            :" in tmp:	P = int(tmp[20:])
		elif "FAILED            :" in tmp:	F = int(tmp[20:]) 
		elif "ASSUMPTION_FAILURE:" in tmp: A = int(tmp[20:])
		elif "Total Tests" in tmp:	T = int(tmp[20:])
		elif "IGNORED           :" in tmp: I = int(tmp[20:])
		elif "IMPORTANT" in tmp:	C = False
		elif "Total Run time" in tmp:	Run_time = tmp[16:]
		elif "No modules found matching" in tmp:	remove = True
		elif "=============== Summary " in tmp: break
		i -= 1
	return P,F,C,Run_time,A,I,T,remove

# get triage session
def get_session(log, pre_Time, Time, pre_session_fail, session, unknown):
	tTime = Time
	for x in log.splitlines():
		#inscase new result worst than previous, consider multiple machine running
		tmp = 0
		if pre_Time in x:
			tmp = int(x[0:3])

		if tTime in x:
			if "unknown" in x:
				unknown = True
				break
			pre_Time = tTime
			try:
				pre_session_fail = int(x[15:20])
			except:
				pre_session_fail = int(x[18:23])
			session = int(x[0:3])
			break
		elif tTime[0:12]+'09' in x:
			Time = tTime[0:12]+'09'
			if "unknown" in x:
				unknown = True
				break
			pre_Time = Time
			try:
				pre_session_fail = int(x[15:20])
			except:
				pre_session_fail = int(x[18:23])
			session = int(x[0:3])
			break
		elif tTime[0:13]+str(int(tTime[13])-1) in x:
			Time = tTime[0:13]+str(int(Time[13])-1)
			if "unknown" in x:
				unknown = True
				break
			pre_Time = Time
			try:
				pre_session_fail = int(x[15:20])
			except:
				pre_session_fail = int(x[18:23])
			session = int(x[0:3])
			break	
		elif tTime[0:12] + str(int(tTime[-2:])-1) in x:
			Time = tTime[0:12] + str(int(tTime[-2:])-1)
			if "unknown" in x:
				unknown = True
				break
			pre_Time = Time
			try:
				pre_session_fail = int(x[15:20])
			except:
				pre_session_fail = int(x[18:23])
			session = int(x[0:3])
			break		
		elif tTime[0:9] + str(int(tTime[9:11])-1)+'.59' in x:
			Time = tTime[0:9] + str(int(tTime[9:11])-1)+'.59'
			if "unknown" in x:
				unknown = True
				break
			pre_Time = Time
			try:
				pre_session_fail = int(x[15:20])
			except:
				pre_session_fail = int(x[18:23])
			session = int(x[0:3])
			break
	return pre_Time, pre_session_fail, session, unknown, Time
	
# print result on terminal
def result(cmd,S,P,F,C,R,A,I,T,pt,un,rm):
	if un == True: print(cmd.strip()+" [Done]\n"+colored(pt+"\t[Session: %s] [Build shows unknown] [Run time: %s]"%(S,R), 'yellow'))
	elif rm == True: print(cmd.strip()+" [Done]\n"+colored(pt+"\t[Session: %s] [No modules found] [Run time: %s]"%(S,R), 'yellow'))
	elif C != True:	print(cmd.strip()+" [Done]\n"+colored(pt+"\t[Session: %s] [Not Complete] [Run time: %s]"%(S,R), 'yellow'))
	elif F > 0:	print(cmd.strip()+" [Done]\n"+colored(pt+"\t[Session: %s] [Total Tests: %s] [Passed: %s] [Failed: %s] [Assumption: %s] [Ignored: %s] [Run time: %s]"%(S,T,P,F,A,I,R), 'red'))
	else:	print(cmd.strip()+" [Done]\n"+colored(pt+"\t[Session: %s] [Total Tests: %s] [Passed: %s] [Failed: %s] [Assumption: %s] [Ignored: %s] [Run time: %s]"%(S,T,P,F,A,I,R), 'green'))

# write terminal log
def write(test_suite, time, data):
	if test_suite == 'gsi':
		fw = open(base_path+'android-cts/logs/'+
					str(dt.date.today().year)+'.'+time+'/Terminal_logs', "w")
	else:	
		fw = open(base_path+'android-'+test_suite+'/logs/'+
					str(dt.date.today().year)+'.'+time+'/Terminal_logs', "w")
	fw.write(data)
	fw.close()

def triage_failure(device, test_suite, build, cmds, platform):
	global previous_execute_time
	
	# only run one cmd in same second
	while cmds:
		# set dir and cmd for popen use
		if test_suite == 'gsi':
			dir = base_path+"android-cts"
			cmd = "./tools/cts-tradefed run commandAndExit cts-on-gsi "
		elif test_suite == 'sts':
			dir = base_path+"android-"+test_suite
			cmd = "./tools/sts-tradefed run commandAndExit sts-dynamic-full "
		else:
			dir = base_path+"android-"+test_suite
			cmd = "./tools/"+test_suite+"-tradefed run commandAndExit "+test_suite+" "

		current_time = int(round(time.time()))
		if current_time <= previous_execute_time:
			time.sleep(1)
		else:
			previous_execute_time = current_time
			include_filter = cmds[0].strip()
			del cmds[0]
			cmd += include_filter
			log = process([cmd+" -s "+device], dir) # +" --bugreport-on-failure"
			pre_Time = "XXXXXXXXXXXXXXXXX"
			Time = extract_time("I/TestInvocation: Starting invocation for", log)
			session = 0
			pre_session_fail = 0
			unknown = False

			# get session from l r
			if test_suite == 'gsi':
				lr = process(["./tools/cts-tradefed l r"], dir)
			else:
				lr = process(["./tools/"+test_suite+"-tradefed l r"], dir)
			pre_Time, pre_session_fail, session, unknown, Time = get_session(lr, pre_Time, Time, pre_session_fail, session, unknown)
			write(test_suite, Time, log)

			# T = Total P = Pass F = Fail A = Assumption I = Ignored C = Complete 
			T = P = F = A = I = 0
			C = True
			Run_time = ""
			remove = False
			P,F,C,Run_time,A,I,T,remove = status(log,P,F,C,Run_time,A,I,T,remove)
			
			include_filter = include_filter.split()[1].replace('\"','')
			# upload pass result to TMP sheet
			path = ""
			if C == True and F == 0 and unknown == False:
				upload_single(test_suite, build, platform, include_filter)
			result(include_filter,session,P,F,C,Run_time,A,I,T,pre_Time,unknown,remove)
			
			#region <option2>
			# if C == False or F != 0 or unknown == True:
			# 	for i in range(retry_round):
			# 		if test_suite == 'gsi':
			# 			rlog = process(["./tools/cts-tradefed run commandAndExit retry -r "+str(session)+s], dir)
			# 		else:
			# 			rlog = process(["./tools/"+test_suite+"-tradefed run commandAndExit retry -r "+str(session)+s], dir)
			# 		Time = extract_time("I/TestInvocation: Starting invocation for", rlog)
			# 		unknown = False

			# 		# get session from l r
			# 		if test_suite == 'gsi':
			# 			lr = process(["./tools/cts-tradefed l r"], dir)
			# 		else:
			# 			lr = process(["./tools/"+test_suite+"-tradefed l r"], dir)

			# 		pre_session = session
			# 		pre_Time, pre_session_fail, session, unknown, Time = get_session(lr, pre_Time, Time, pre_session_fail, session, unknown)
			# 		write(test_suite, Time, log)

			# 		# T = Total P = Pass F = Fail A = Assumption I = Ignored C = Complete 
			# 		T = P = F = A = I = 0
			# 		C = True
			# 		Run_time = ""
			# 		remove = False
			# 		P,F,C,Run_time,A,I,T,remove = status(log,P,F,C,Run_time,A,I,T,remove)
			# 		result("run retry -r "+str(pre_session),session,P,F,C,Run_time,A,I,T,pre_Time,unknown,remove)

			# 		if C == True and F == 0 and unknown == False:
			# 			break
			#endregion

# make cmds file in one line
def single_cmd():
	fr = open('./cmds','r')
	cmds = ""
	cmd = fr.readline()
	while cmd:
		cmds += cmd.strip('\n')
		cmd = fr.readline()
	fr.close()
	return cmds

# open cmd file and keep each command in cmds list
def list_cmd():
	cmds = []
	fr = open("./cmds", "r")
	for i in fr:
		cmds.append(i)
	return cmds
