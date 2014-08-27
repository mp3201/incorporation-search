#!/usr/bin/python

import os, sys, getopt, fileinput
import random, time
import re

from datetime import datetime

import urllib, urllib2, urlparse

from BeautifulSoup import BeautifulSoup as bs

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

in_delimiter = ','
out_delimiter = '|'

field_index = { i:n for i,n in
	enumerate([
		"id1", "id2", "companyName", "sta", "num_results", "status",
		"url_result", "ss_id", "founding_date", "status_date", "taxid",
		"jurisdiction", "agent_name", "last_report", "entity_type",
		"inactive_date", "expiration_date", "cached_file"])
	}

mindelay = 10
maxdelay = 12
ackdelay = 2
random.seed()

whitespace = re.compile(r'\s+')

def delay():
	currentdelay = random.randint(mindelay, maxdelay)
	print "sleeping for {0} seconds...".format(currentdelay)
	time.sleep(currentdelay)

def wait(length=ackdelay):
	time.sleep(length)

def acknowledge(browser):
	time.sleep(ackdelay) # form needs time to stabilize; 1 sec enough, 2 for good measure
	try:
		alert = browser.switch_to_alert()
		alert.dismiss()
	except:
		pass	

def wait_for_user(message):
	print "********************************************************"
	print "* WAITING FOR MANUAL RESPONSE                          *"
	print "********************************************************"
	print message
	response = raw_input("Press return when finished:")

class LoadFailedError(Exception): pass

def getsoup(url, form_params, context, key='page', retries=0):
	if form_params:
		request = urllib2.Request(url=url, data=urllib.urlencode(form_params))
	else:
		request = urllib2.Request(url=url)
	count = 0
	while count <= retries:
		try:
			response = urllib2.urlopen(request)
			page = response.read()
			context[key] = page
			return bs(page)
		except:
			count += 1
			print ("page load failed: {}".format(url))
			time.sleep(1)
		finally:
			response.close()
	raise LoadFailedError()

def set_context_details(context, url, id, date, status,
		taxid="", jurisdiction="", agent_name="", last_report="", status_date="",
		entity_type="", inactive_date="", expiration_date=""):
	context['num_results'] = 1
	context['url_result'] = url
	context['ss_id'] = id
	context['founding_date'] = date
	context['status'] = status
	context['taxid'] = taxid
	context['jurisdiction'] = jurisdiction
	context['agent_name'] = agent_name
	context['last_report'] = last_report
	context['status_date'] = status_date
	context['entity_type'] = entity_type
	context['inactive_date'] = inactive_date
	context['expiration_date'] = expiration_date

def fill_context_AK(browser, context):
	url = "http://commerce.alaska.gov/CBP/Main/CBPLSearch.aspx?mode=Corp"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="ctl00_cphMain_TextBoxEntityName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="ctl00_cphMain_Search"]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	try:
		rows = soup.find("table", { 'id': "ctl00_cphMain_GridViewResults" }).findAll('tr')
	except:
		context['num_results'] = 0
		return
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(url, rows[1].findAll('td')[1].a['href'])
	soup = getsoup(details_url, None, context)
	if soup == None:
		context['status'] = "site error"
		return
	details = soup.findAll('div', { 'class': "table" })[0]
	set_context_details(context,
		details_url,
		details.findAll('span')[1].text,
		details.findAll('span')[3].text,
		details.findAll('span')[2].text,
		agent_name=soup.findAll('div', { 'class': "table" })[1].findAll('span')[0].text,
		last_report=soup.findAll('table')[2].findAll('tr')[-1].findAll('span')[0].text
		)

def fill_context_AL(browser, context):
	url = "http://arc-sos.state.al.us/CGI/CORPNAME.MBR/INPUT"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="divMainContent"]/table[1]/tbody/tr[2]/td[2]/table/tbody/tr/td/table[1]/tbody/tr[1]/td[2]/input').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="divMainContent"]/table[1]/tbody/tr[2]/td[2]/table/tbody/tr/td/table[1]/tbody/tr[11]/td/input').click()
	if browser.page_source.find("No matches found.") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[2].findAll('tr')
	if len(rows) > 3:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(url, rows[1].findAll('a')[0]['href'])
	soup = getsoup(details_url, None, context)
	data = soup.findAll('table')[1].findAll('tr')
	reg_date = ""
	jurisdiction = ""
	agent_name = ""
	expiration_date = ""
	for row in data:
		cells = row.findAll('td')
		if cells[0].text == "Formation Date":
			reg_date = cells[1].text
		elif cells[0].text == "Place of Formation":
			jurisdiction = cells[1].text
		elif cells[0].text == "Registered Agent Name":
			agent_name = cells[1].text
		elif cells[0].text in ("Dissolved Date", "Revoked Date", "Merged Date"):
			expiration_date = cells[1].text
	set_context_details(context,
		details_url,
		data[1].findAll('td')[1].text,
		reg_date,
		data[5].findAll('td')[1].text,
		jurisdiction=jurisdiction,
		agent_name=agent_name,
		entity_type=data[2].findAll('td')[1].text,
		expiration_date=expiration_date,
		)

def fill_context_AR(browser, context):
	url = "http://www.sos.arkansas.gov/corps/search_all.php"
	results_url = "http://www.sos.arkansas.gov/corps/search_corps.php"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="mainContent"]/form/table/tbody/tr[4]/td[2]/font/input').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="mainContent"]/form/table/tbody/tr[11]/td/font/input').click()
	if browser.page_source.find("There were no records found!") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[3].findAll('a')
	if len(rows) > 1:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(results_url, rows[0]['href'])
	soup = getsoup(details_url, None, context)
	data = soup.findAll('table')[1].findAll('tr')
	set_context_details(context,
		details_url,
		data[3].findAll('td')[1].text,
		data[10].findAll('td')[1].text,
		data[6].findAll('td')[1].text,
		agent_name=data[8].findAll('td')[1].text,
		entity_type=data[4].findAll('td')[1].text,
		)

def fill_context_AZ(browser, context):
	url = "http://starpas.azcc.gov/scripts/cgiip.exe/WService=wsbroker1/connect.p?app=history-report.p"
	browser.get(url)
	browser.find_element_by_xpath('/html/body/form/table/tbody/tr[2]/td[1]/input').send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/form/table/tbody/tr[4]/td/input[2]').click()
	browser.find_element_by_xpath('/html/body/form/table/tbody/tr[3]/th[2]/input').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[2].findAll('tr')
	if len(rows) == 1:
		context['num_results'] = 0
		return
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('/html/body/table[2]/tbody/tr[2]/td[2]/a').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	details_url = browser.current_url
	data = soup.findAll('table')
	for x in range (0, len(data)):
		if len(data[x].findAll('caption'))>0:
			if data[x].findAll('caption')[0].text == "Additional Corporate Information":
				numtable = x
	status_date = data[numtable].findAll('tr')[4].findAll('td')[1].text.split(':')[1]
	set_context_details(context,
		details_url,
		data[3].findAll('tr')[1].td.text.split(':')[1],
		data[numtable].findAll('tr')[1].td.text.split(':')[1],
		data[numtable].findAll('tr')[4].td.text.split(':')[1],
		)
	context['status_date'] = status_date

def fill_context_CA(browser, context):
	name = context['companyName']
	print "testing CA for:", name
	browser.get("http://kepler.sos.ca.gov/")
	corporate_select = browser.find_element_by_id("ctl00_content_placeholder_body_BusinessSearch1_RadioButtonList_SearchType_0")
	corporate_select.click()
	company_name = browser.find_element_by_id("ctl00_content_placeholder_body_BusinessSearch1_TextBox_NameSearch")
	company_name.send_keys(name)
	submit_button = browser.find_element_by_id("ctl00_content_placeholder_body_BusinessSearch1_Button_Search")
	submit_button.click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	table = soup.find("table", { "id": "ctl00_content_placeholder_body_SearchResults1_GridView_SearchResults_Corp" })
	rows = table.findAll("tr")
	if len(rows) == 1:
		context['num_results'] = 0
		return
	elif len(rows) > 2:
		context['num_results'] = 'many'
		return
	else:
		cells = rows[1].findAll("td")
		set_context_details(context, 
		browser.current_url,
		cells[0].text, 
		cells[1].text, 
		'CA')
		entitynum = cells[0].text
		context['status'] = cells[2].text
		browser.find_element_by_id("ctl00_content_placeholder_body_SearchResults1_GridView_SearchResults_Corp_ctl02_ctl00").click()
		context['page'] = browser.page_source.encode('ascii', 'ignore')		
		print "Found 1 result, now extracting exit date for CA:", entitynum
		browser.get("https://businessfilings.sos.ca.gov/DefaultBottom.asp")
		entity_number = browser.find_element_by_xpath('.//*[@id="TABLE1"]/tbody/tr[2]/td/form/table/tbody/tr[2]/td[3]/input')
		entity_number.send_keys(entitynum)
		entity_submit = browser.find_element_by_xpath('.//*[@id="TABLE1"]/tbody/tr[2]/td/form/table/tbody/tr[3]/td[3]/input')
		entity_submit.click()
		browser.find_element_by_xpath('html/body/table/tbody/tr[2]/td[4]/a').click()
		details = bs(browser.page_source)
		context['page2'] = browser.page_source.encode('ascii', 'ignore')
		data = details.findAll('font')
		last_statement = re.search(r'\d{1,}/\d{1,}/\d{4}', str(data[1]))
		if last_statement is not None:
			print "Last statement was filed on:", last_statement.group()
		if last_statement is not None:
			context['last_report'] = last_statement.group()
		else:
			context['last_report'] = context['founding_date']

def fill_context_CO(browser, context):
	date = ""
	url = "http://www.sos.state.co.us/biz/BusinessEntityCriteriaExt.do"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="application"]/table/tbody/tr/td[2]/table/tbody/tr[3]/td/form/table[1]/tbody/tr[5]/td[2]/font/input').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="application"]/table/tbody/tr/td[2]/table/tbody/tr[3]/td/form/table[2]/tbody/tr/td[1]/input').click()
	if browser.page_source.find("No results found for the specified name.") >= 0:
		context['num_results'] = 0
		return
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	if browser.page_source.find("Exceeded Record Count, please refine search") >= 0:
		context['num_results'] = 'many'
		return
	soup = bs(browser.page_source)
	rows = soup.findAll('form')[2].table.table.findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(url, rows[1].a['href'])
	browser.get(details_url)
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[5].findAll('tr')
	nrows = len(rows)
	for x in range (0, nrows):
		cells = rows[x].findAll('td')
		ncells = len(cells)
		# Lood for Status
		for y in range (0, ncells):
			if cells[y].text == "Status":
				print "Status: ", cells[y+1].text
				status = cells[y+1].text
				context['status'] = cells[y+1].text
		# Look for Founding date
		for y in range (0, ncells):
			if cells[y].text == "Formation date":
				print "Formation date: ", cells[y+1].text	
				date = cells[y+1].text
				context['founding_date'] = cells[y+1].text		
		# Look for ID
		for y in range (0, ncells):
			if cells[y].text == "ID number":
				print "ID number: ", cells[y+1].text	
				id = cells[y+1].text		
				context['ss_id'] = cells[y+1].text
	# Now we go an look for date of last report
#	browser.find_element_by_xpath('//*[@id="application"]/table/tbody/tr/td[2]/table/tbody/tr[3]/td/form/table[1]/tbody/tr[2]/td/dl/dd[1]/a').click()
	browser.find_element_by_link_text("Filing history and documents").click()
	browser.find_element_by_xpath('.//*[@id="box"]/table/tbody/tr[1]/th[3]/a/b').click()
	browser.find_element_by_xpath('.//*[@id="box"]/table/tbody/tr[1]/th[3]/a/b').click()
	detailssoup = bs(browser.page_source)
	rows = detailssoup.findAll('table')[7].findAll('tr')
	details_url = browser.current_url
	nrows = len(rows)
	found = 0
	last_report=""
	for x in range (0, nrows):
		cells = rows[x].findAll('td')
		ncells = len(cells)
		# Lood for Status
		for y in range (0, ncells):
			if found == 0:
				if cells[y].text == "Report":
					print "Date of last report: ", cells[y+1].text
					last_report = cells[y+1].text
					found = 1
	context['page2'] = browser.page_source.encode('ascii', 'ignore')
	set_context_details(context, 
	details_url,
	id, 
	date, 
	status)
	context['last_report'] = last_report


def fill_context_CT(browser, context):
	global didscrape
	details_url = "cache"
	filename = "{0}_{1}.html".format(context['id2'], context['sta'])
	context['cached_file'] = filename
	filename = "{0}/{1}".format(cachedir, filename)
	if os.path.exists(filename):
		didscrape = 0
		print "didscrape is now : ", didscrape
		f = open(filename, "r")
		data = f.read().decode('ascii')
		print "Now passing file to beatifulsoup"
		soup = bs(data)
		context['page'] = data.encode('ascii', 'ignore')
		if soup.find(text=re.compile('Business Search Results')) is not None:
			print "many"
			context['num_results'] = 'many'
			return
	else:
		url = "http://www.concord-sots.ct.gov/CONCORD/online?eid=99&sn=InquiryServlet"
		details_url = "unknown"
		browser.get(url)
		browser.switch_to_frame(browser.find_element_by_xpath('/html/frameset/frameset/frame'))
		browser.find_element_by_xpath('//*[@id="txtBusName"]').send_keys(context['companyName'])
		browser.find_element_by_xpath('/html/body/form/table/tbody/tr[1]/td/table/tbody/tr[2]/td/table/tbody/tr[1]/td/table/tbody/tr[1]/td/table/tbody/tr[6]/td[2]/table/tbody/tr/td[1]/input').click()	
		try:
			WebDriverWait(browser, 1).until(EC.alert_is_present(), "")
			alert = browser.switch_to_alert()
			alert.accept()
			context['num_results'] = 0
			return
		except TimeoutException:
			pass
		soup = bs(browser.page_source)
		context['page'] = browser.page_source.encode('ascii', 'ignore')
		rows = soup.findAll('table')[6].findAll('tr')
		if len(rows) > 3:
			context['num_results'] = 'many'
			return
		browser.find_element_by_xpath('/html/body/form/table/tbody/tr[1]/td/table/tbody/tr[2]/td/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[2]/td[2]/a').click()
		soup = bs(browser.page_source)
		context['page'] = browser.page_source.encode('ascii', 'ignore')
	
	data = soup.findAll('table')[3].findAll('td')

	date = ""
	id = ""
	lastreport = ""
	status = ""
	agent = ""
	
	for i in range (0, len(data)):
		line = data[i].text 
		if re.search('Business ID:', line) is not None:
			id = data[i+1].text
		if re.search('Last Report Filed Year:', line) is not None:
			lastreport = data[i+1].text
		if re.search('Business Status:', line) is not None:
			status = data[i+1].text
		if re.search('Date Inc/Registration:', line) is not None:
			date = data[i+1].text

	print "URL :", details_url
	print "ID :", id
	print "Date :", date
	print "Status: ", status
	print "Last report: ", lastreport
	
	set_context_details(context,
		details_url,
		id,
		date,
		status,
		last_report=lastreport,
		)
def fill_context_DE(browser, context):
	name = context['companyName']
	print "testing DE for:", name
	browser.get("https://delecorp.delaware.gov/tin/GINameSearch.jsp")
	acknowledge(browser)
	company_name = browser.find_element_by_xpath('//*[@id="mainBody"]/table[3]/tbody/tr[5]/td[2]/input')
	company_name.send_keys(name)
	submit_button = browser.find_element_by_xpath('//*[@id="mainBody"]/table[3]/tbody/tr[8]/td[2]/input')
	submit_button.click()
	acknowledge(browser)
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	table = soup.find("div", { "id": "mainBody" }).findAll("table")[2]
	rows = table.findAll("tr")
	if len(table.findAll(text = "No matches found. Please try a new search.")) > 0:
		context['num_results'] = 0
		return
	elif len(rows) > 2:
		acknowledge(browser)
		browser.delete_all_cookies()
		context['num_results'] = 'many'
		return
	else:
		company_link = browser.find_element_by_xpath('//*[@id="mainBody"]/table[3]/tbody/tr[2]/td[2]/a')
		company_link.click()
		acknowledge(browser)
		browser.delete_all_cookies()
		soup = bs(browser.page_source)
		context['page'] = browser.page_source.encode('ascii', 'ignore')
		row = soup.find("div", { "id": "mainBody" }).findAll("table")[1].tbody.findAll("tr")[1]
		cells = row.findAll("td")
		set_context_details(context, 
		browser.current_url,
		cells[1].b.text, 
		cells[3].b.text, 
		'DE')


def fill_context_FL(browser, context):
	url = "http://search.sunbiz.org/Inquiry/CorporationSearch/ByName"
	companyName = context['companyName']
	companyName = re.sub(r'\sINC$', ', INC.', companyName)
	companyName = re.sub(r'\sLTD$', ', LTD.', companyName)
	print "Looking for companyName : ", companyName
	form_action = urlparse.urljoin(url, "/Inquiry/CorporationSearch/ByName")
	params = {
		'SearchTerm': context['companyName'],
		}
	soup = getsoup(form_action, params, context, retries=5)
	if soup == None:
		context['status'] = "site error"
		return
	table = soup.find('div', { 'id': "search-results" }).table.tbody
	if len(table.findAll('tr')) == 0:
		context['num_results'] = 0
		return
	# Search always return many. Go over list and look for exact match
	found = 0
	numrows = len(table.findAll('tr'))
	for x in range (0, numrows):
		if re.search(table.findAll('tr')[x].td.a.text, companyName):
			if found == 1:
				context['num_results'] = "many"
				return
			else:
				details_url = urlparse.urljoin(form_action, table.findAll('tr')[x].td.a['href'])
				found = 1
		if x == numrows-1:
			print "reached end of rows"
			if found == 0:
				print "and nothing was found"
				context['num_results'] = 0
				return
	soup = getsoup(details_url, None, context, retries=5)
	if soup == None:
		context['status'] = "site error"
		return
	details = soup.findAll('div', {'class':"detailSection filingInformation"})[0].div
	data = details.findAll('span')
	label = details.findAll('label')
	id = ""
	tid = ""
	fdate = ""
	sdate = ""
	status = ""
	
	for i in range (0, len(data)):
		if label[i].text == "Document Number":
			id = data[i].text
		if label[i].text == "FEI/EIN Number":
			tid = data[i].text
		if label[i].text == "Date Filed":
			fdate = data[i].text
		if label[i].text == "Last Event":
			status = data[i].text
		if label[i].text == "Event Date Filed":
			sdate = data[i].text
	
	print "ID : ", id
	print "tax ID : ", tid
	print "F Date : ", fdate
	print "Status : ", status
	print "S Date : ", sdate
	
	set_context_details(context,
		details_url,
		id,
		fdate,
		status,
		taxid=tid,
		status_date=sdate,
		)

def fill_context_GA(browser, context):
	url = "https://cgov.sos.state.ga.us/"
	browser.get(url)
	companyName = context['companyName']
	companyName = companyName.replace(" INC", "")
	companyName = companyName.replace(" LTD", "")
	browser.find_element_by_xpath('/html/body/div[2]/div[3]/div/div/form/div/div/div/fieldset/table[1]/tbody/tr/td[2]/input').clear()
	browser.find_element_by_xpath('/html/body/div[2]/div[3]/div/div/form/div/div/div/fieldset/table[1]/tbody/tr/td[2]/input').send_keys(companyName)
	browser.find_element_by_xpath('html/body/div[2]/div[3]/div/div/form/div/div/div/fieldset/table[1]/tbody/tr/td[3]/button').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')

	if browser.page_source.find("No Results were found.") >= 0:
		print "Zero"
		context['num_results'] = 0
		return
		
	table = soup.find( "table", {'id':"BizEntitySearch_SearchResultsTable"} )

	if len(table.findAll('tr')) > 2:
		print "many"
		context['num_results'] = 'many'
		return

	print "Now clicking!"
	browser.find_element_by_xpath('html/body/div[2]/div[3]/div/div/form/div/div/div/div/table/tbody/tr/td[2]/a').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	
	field = soup.findAll('fieldset')
	spans = field[0].findAll('span')

	ID = ""
	Founding = ""
	Status = ""
	StatusDate = ""
	
	for y in range (0, len(spans)):
		if spans[y].text == "Entity Id":
			ID = spans[y+1].text
			print "ID: ", ID
		if spans[y].text == "Registration Date":
			Founding = spans[y+1].text
			print "F Date: ", Founding
		if spans[y].text == "Entity Status":
			Status = spans[y+1].text
			print "Status: ", Status
		if spans[y].text == "Entity Status Date":
			StatusDate = spans[y+1].text
			print "StatusDate: ", StatusDate
		
	set_context_details(context,
		browser.current_url,
		ID,
		Founding,
		Status,
		status_date = StatusDate,
		)

def fill_context_HI(browser, context):
	url = "http://hbe.ehawaii.gov/documents/search.html"
	browser.get(url)
	element = browser.find_element_by_xpath('/html/body/table[2]/tbody/tr/td[2]/div[1]/form/label[2]/input')
	element.clear()
	element.send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/table[2]/tbody/tr/td[2]/div[1]/form/input[4]').click()
	if browser.page_source.find("There are no businesses for this search term.") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[4].findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[1].a['href'])
	soup = getsoup(details_url, None, context)
	data = soup.findAll('table')[2].findAll('tr')
	reg_date = ""
	filenum = ""
	status = ""
	agent_name = ""
	expiration_date = ""

	for row in data:
		cells = row.findAll('td')
		if cells[0].text == "STATUS":
			status = cells[1].text
		elif cells[0].text == "FILE NUMBER":
			filenum = cells[1].text
		elif cells[0].text == "REGISTRATION DATE":
			reg_date = cells[1].text
		elif cells[0].text == "REGISTRANT":
			agent_name = cells[1].text
		elif cells[0].text == "EXPIRATION DATE":
			expiration_date = cells[1].text

	set_context_details(context,
		details_url,
		filenum,
		reg_date,
		status,
		agent_name=agent_name,
		expiration_date=expiration_date,
		)

def fill_context_IA(browser, context):
	url = "http://sos.iowa.gov/search/business/search.aspx"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="busName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="btnBusName"]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table', { 'class': "results" })[0].findAll('tr')
	if len(rows) == 2:
		context['num_results'] = 0
		return
	if len(rows) > 3:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[1].a['href'])
	soup = getsoup(details_url, None, context)
	data = soup.table.findAll('tr')
	details2_url = urlparse.urljoin(details_url, soup.find('a', { 'title': "Filings" })['href'])
	soup2 = getsoup(details2_url, None, context, key='page2')
	last_report = soup2.table.findAll('tr')[-1].findAll('td')[2].text
	set_context_details(context,
		details_url,
		data[1].findAll('td')[0].text,
		data[5].findAll('td')[1].text,
		data[1].findAll('td')[2].text,
		expiration_date=data[5].findAll('td')[0].text,
		last_report=last_report,
		)

def fill_context_ID(browser, context):
	url = "http://www.accessidaho.org/public/sos/corp/search.html?ScriptForm.startstep=crit"
	browser.get(url)
	browser.find_element_by_xpath('/html/body/form/table/tbody/tr[5]/td[2]/table/tbody/tr[1]/td[2]/input').send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/form/table/tbody/tr[4]/td[2]/p[1]/input').click()
	if browser.page_source.find("No Business Entities Found") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[2].findAll('tr')
	if len(rows) > 6:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[0].a['href'])
	soup = getsoup(details_url, None, context)
	data = soup.findAll('table')[1].findAll('tr')
	set_context_details(context,
		details_url,
		data[9].findAll('td')[2].text,
		data[8].findAll('td')[2].text,
		data[6].findAll('td')[2].text,
		)

def fill_context_IL(browser, context):
	url = "http://www.ilsos.gov/corporatellc"
	form_action = urlparse.urljoin(url, "/corporatellc/CorporateLlcController")
	params = {
		'command': "index",
		'type': "corporate", # 'llc', 'corporate', 'both'
		'search': "startsWith", # 'startsWith', 'exactWord', 'partialWord', 'fileNumber'
		'searchkeyword': context['companyName'],
		}
	soup = getsoup(form_action, params, context)
	if soup.text.find("did not match any records in the Corporation/LLC-GS Search database.") >= 0:
		context['num_results'] = 0
		return
	table = soup.findAll('table')[3].tbody
	if len(table.findAll('tr')) > 2:
		context['num_results'] = 'many'
		return
	details = table.findAll('tr')[1].findAll('td')[2].a['href'].split("'")
	params = {
		'command': "details",
		'fileNumber': details[1],
		'sysId': details[3],
		'nameType': details[5],
		'seriesNbr': details[7],
		'certName': details[9],
		}
	soup = getsoup(form_action, params, context)
	table = soup.findAll('table')[3]
	status = table.findAll('tr')[1].findAll('td')[1].font.text
	inactive_date = ""
	if status != "Active":
		inactive_date = table.findAll('tr')[6].findAll('td')[3].font.text
	set_context_details(context,
		url,
		table.tr.findAll('td')[3].font.text,
		table.findAll('tr')[3].findAll('td')[1].font.text,
		status,
		agent_name=table.findAll('tr')[4].findAll('td')[1].font.text,
		inactive_date=inactive_date,
		)

def fill_context_IN(browser, context):
	url = "https://secure.in.gov/sos/online_corps/name_search.aspx"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="search"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="pad"]/div[1]/form/input[5]').click()
	if browser.page_source.find("There were no Entity Names found for your search criteria:") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.table.findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[1].a['href'])
	browser.find_element_by_xpath('//*[@id="grdViewResults"]/tbody/tr[2]/td[1]/a').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.find('div', { 'id': "pad" }).findAll('p')[3].findAll('b')
	set_context_details(context,
		details_url,
		data[1].text,
		data[4].text,
		data[2].text,
		expiration_date=data[5].text,
		inactive_date=data[6].text,
		)

def fill_context_KS(browser, context):
	url = "http://www.kansas.gov/bess/flow/main?execution=e2s3"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="startSearchLink"]').click()
	browser.find_element_by_xpath('//*[@id="byNameLink"]').click()
	browser.find_element_by_xpath('//*[@id="searchFormForm:businessName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="searchFormForm:searchSubmit"]').click()
	if browser.page_source.find("The name or number you searched for was not found in the business entity database") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[2].findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('//*[@id="j_id12:0:searchFormForm:j_id13"]').click()
	details_url = browser.current_url
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.find('div', { 'class': "bodyIndent" })
	inactive_date = ""
	if data.text.find("Last Annual Report"):
		inactive_date = data.text[data.text.find("Last Annual Report"):].split(':')[1].split('N')[0]
	status = ""
	formation_date = ""
	for x in range(0, len(data.findAll('p'))):
		if re.search('Current', data.findAll('p')[x].text.split(': ')[0]) is not None:
			status = data.findAll('p')[x].text.split(': ')[1]
		if re.search('Formation', data.findAll('p')[x].text.split(': ')[0]) is not None:
			formation_date = data.findAll('p')[x].text.split(': ')[1]
	print "Status : ", status
	print "Date of formation : ", formation_date
	set_context_details(context,
		details_url,
		data.findAll('table')[1].findAll('tr')[1].findAll('td')[1].text,
		formation_date,
		status,
		last_report=inactive_date,
		)

def fill_context_KY(browser, context):
	url = "https://app.sos.ky.gov/ftsearch/"
	browser.get(url)
	element = browser.find_element_by_xpath('//*[@id="ctl00_ContentPlaceHolder1_FTUC_TextBox1"]')
	element.send_keys('\b' * 22 + context['companyName'])
	browser.find_element_by_xpath('//*[@id="ctl00_ContentPlaceHolder1_FTUC_Button2"]').click()
	if browser.page_source.find("No matching organizations were found") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.findAll('table')[3].findAll('tr')
	try:
		data[0].findAll('td')[1].text
	except:
		context['num_results'] = 'many'
		return
	details_url = browser.current_url
	set_context_details(context,
		details_url,
		data[0].findAll('td')[2].text,
		data[8].findAll('td')[2].text,
		data[4].findAll('td')[2].text,
		agent_name=data[11].findAll('td')[2].text,
		last_report=data[9].findAll('td')[2].text,
		entity_type=data[3].findAll('td')[2].text,
		)

def fill_context_LA(browser, context):
	url = "http://www.sos.la.gov/BusinessServices/SearchForLouisianaBusinessFilings/Pages/default.aspx"
	browser.get(url)
	browser.switch_to_frame(browser.find_element_by_xpath('//*[@id="WebPartWPQ1"]/iframe'))
	browser.find_element_by_xpath('//*[@id="txtEntityName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="btnSearchEntity"]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	table = soup.find('table', { 'id': "grdSearchResults_EntityNameOrCharterNumber" })
	if table != None:
		rows = table.findAll('tr')
		if len(rows) == 1:
			context['num_results'] = 0
			return
		if len(rows) > 2:
			context['num_results'] = 'many'
			return
		raise Exception("unknown parse error")
	data1 = soup.find('table', { 'id': "tblHeader" }).findAll('tr')
	data2 = soup.find('table', { 'id': "tblStatus" }).findAll('tr')
	details_url = browser.current_url
	inactive_date = ""
	expiration_date = ""
	amendments = soup.find('table', { 'id': "grdAmendments" })
	if amendments != None:
		rows = amendments.findAll('tr')
		rows.reverse()
		for row in rows:
			cells = row.findAll('td')
			if cells[0].text == "Revoked":
				if expiration_date == "":
					expiration_date = cells[1].text
			elif cells[0].text == "Affidavit to Dissolve":
				if inactive_date == "":
					inactive_date = cells[1].text
	print "inactive_date:", inactive_date, "\nexpiration_date:", expiration_date
	set_context_details(context,
		details_url,
		data1[1].findAll('td')[1].text,
		data1[2].findAll('td')[1].text,
		data2[1].findAll('td')[1].text,
		entity_type=data2[5].findAll('td')[1].text,
		inactive_date=inactive_date,
		expiration_date=expiration_date
		)

def fill_context_MA(browser, context):
	global didscrape
	filename = "{0}_{1}.html".format(context['id2'], context['sta'])
	context['cached_file'] = filename
	filename = "{0}/{1}".format(cachedir, filename)
	if os.path.exists(filename):
		details_url = "cache"
		didscrape = 0
		print "didscrape is now : ", didscrape
		f = open(filename, "r")
		data = f.read().decode('ascii')
		print "Now passing file to beatifulsoup"
		soup = bs(data)
		context['page'] = data.encode('ascii', 'ignore')
		table = soup.findAll('table', {'id': "MainContent_SearchControl_grdSearchResultsEntity"})
		if len(table) > 0:
			if len(table[0].findAll('tr')) > 2:
				print "many"
				context['num_results'] = 'many'
				return
	else:
		url = "http://corp.sec.state.ma.us/corpweb/corpsearch/CorpSearch.aspx"
		browser.get(url)
		browser.find_element_by_xpath('//*[@id="MainContent_txtEntityName"]').send_keys(context['companyName'])
		browser.find_element_by_xpath('//*[@id="MainContent_btnSearch"]').click()
		soup = bs(browser.page_source)
		context['page'] = browser.page_source.encode('ascii', 'ignore')
		try:
			table = soup.findAll('table', {'id': "MainContent_SearchControl_grdSearchResultsEntity"})[0]
		except:
			context['num_results'] = 0
			return
		if len(table.findAll('tr')) > 2:
			context['num_results'] = 'many'
			return
		browser.find_element_by_xpath('//*[@id="MainContent_SearchControl_grdSearchResultsEntity"]/tbody/tr[2]/td[1]/a').click()
		soup = bs(browser.page_source)
		details_url = browser.current_url
		context['page'] = browser.page_source.encode('ascii', 'ignore')
	expiration_date = ""
	status = ""
	try:
		expiration_date = soup.findAll('span', {'id':"MainContent_lblInactiveDate"})[0].text
		status = soup.findAll('span', {'id':"MainContent_lblInactiveDateLabel"})[0].text.split(':')[0].split('Date of ')[1]
		print "Reason : ", status
		print "Date : ", expiration_date
	except:
		pass
	id = soup.findAll('span', {'id':"MainContent_lblIDNumber"})[0].text.split(':')[1]
	Founding = soup.findAll('span', {'id': "MainContent_lblOrganisationDate"})[0].text
	set_context_details(context,
		details_url,
		id,
		Founding,
		status,
		status_date=expiration_date,
		)
			
def fill_context_MD(browser, context):
	url = "http://sdatcert3.resiusa.org/ucc-charter/CharterSearch_f.aspx"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="VisibleEntityName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="Column800a"]/div/table/tbody/tr/td[2]/table/tbody/tr/td[2]/input[2]').click()
	if browser.page_source.find("No Information available.") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.find('table', { 'id': "Results" }).findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	id = rows[1].td.text[1:-1]
	date = "unknown"
	status = rows[1].findAll('td')[5].text
	details_url = "unknown"
	inactive_date = ""
	try:
		browser.find_element_by_xpath('//*[@id="Results"]/tbody/tr[2]/td[3]/a').click()
		soup = bs(browser.page_source)
		context['page'] = browser.page_source.encode('ascii', 'ignore')
		details_url = browser.current_url
		data = soup.find('table', { 'id': "Results" }).findAll('table')[1].findAll('tr', recursive=False)
		for row in data:
			if row.text.find("Formation") >= 0:
				date = row.findAll('td')[1].text
		browser.find_element_by_xpath('//*[@id="Amendments"]/div/a').click()
		context['page2'] = browser.page_source.encode('ascii', 'ignore')
		soup2 = bs(browser.page_source)
		inactive_date = soup2.findAll('table')[5].findAll('tr')[1].findAll('td')[1].text
	except:
		pass
	set_context_details(context,
		details_url,
		id,
		date,
		status,
		inactive_date=inactive_date,
		)

def fill_context_ME(browser, context):
	url = "http://icrs.informe.org/nei-sos-icrs/ICRS?MainPage=x"
	browser.get(url)
	browser.find_element_by_xpath('/html/body/form/center/table/tbody/tr[3]/td/table/tbody/tr[4]/td/table/tbody/tr/td[2]/input').send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/form/center/table/tbody/tr[3]/td/table/tbody/tr[6]/td/font/b/input[1]').click()
	time.sleep(3)
	if browser.page_source.find("Found 0 entities for query:") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[1].findAll('tr')
	if len(rows) > 6:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('/html/body/form/center/table/tbody/tr[3]/td/table[1]/tbody/tr[6]/td[4]/font/a').click()
	details_url = browser.current_url
	time.sleep(3)
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.findAll('table')[1].findAll('tr')
	set_context_details(context,
		details_url,
		data[4].findAll('td')[1].text,
		data[6].findAll('td')[0].text,
		data[4].findAll('td')[3].text,
		agent_name=data[12].findAll('td')[0].text,
		)
	details2_url = urlparse.urljoin(details_url, soup.findAll('a')[2]['href'])
	browser.get(details2_url)
	time.sleep(3)
	context['page2'] = browser.page_source.encode('ascii', 'ignore')
	soup = bs(browser.page_source)
	context['last_report'] = soup.findAll('table')[1].findAll('tr')[-3].findAll('td')[1].text
	if context['status'] != "ACTIVE":
		context['inactive_date'] = context['last_report']

def fill_context_MI(browser, context):
	url = "http://www.dleg.state.mi.us/bcs_corp/sr_corp.asp"
	browser.get(url)
	browser.find_element_by_xpath('/html/body/table[3]/tbody/tr/td/form/div/table[2]/tbody/tr[6]/td[2]/font/input[1]').send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/table[3]/tbody/tr/td/form/div/table[2]/tbody/tr[7]/td[2]/font/input[1]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	table = soup.findAll('table')[4].findAll('tr')[2].td.table
	if table == None:
		context['num_results'] = 0
		return
	if len(table.findAll('tr')) > 2:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('/html/body/table[3]/tbody/tr[3]/td/table[1]/tbody/tr[2]/td[1]/p/font/a').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	details = soup.findAll('table')[4].findAll('tr')
	ncells = len(details)
	print "Number of rows : ", ncells
	# Lood for Status
	ID = ""
	Agent = ""
	Jurisdiction = ""
	Founding = ""
	Status = ""
	StatusDate = ""
	lastreport = ""
	for y in range (2, ncells):
		line = details[y].td.text
		line = ' '.join(line.split())
		if re.search('ID Num', line) is not None:
			ID = line.split(':')[1]
		if re.search('Agent', line) is not None:
			Agent = line.split(':')[1]
		if re.search('Jurisdiction', line) is not None:
			Jurisdiction = line.split(':')[1]
		if re.search('Formation', line) is not None:
			Founding = line.split(':')[1]
		if re.search('Incorporation/Qualification', line) is not None:
			Founding = line.split(':')[1]
		if re.search('Year of Most Recent Annual Report:', line) is not None:
			field = line.split(':')[1]
			digits = re.findall(r'\d\d', field)
			list = ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12', '13', '14']
			if digits:
				if any(digits[0] in s for s in list):
					lastreport = "20" + digits[0]
				else:
					lasterport = "20" + digits[0]
			else:
				lastreport = ""
			print "last report: ", lastreport
		if re.search('Status', line) is not None:
			if re.search('Date', line) is not None:
				Status = line.split('Date:')[0].split(':')[1]
				Status = Status.replace("&nbsp;", "")
				StatusDate = line.split('Date:')[1]
			else:
				if re.search('AS OF', line) is not None:
					Status = line.split(':')[1].split('AS OF')[0]
					StatusDate = line.split(':')[1].split('AS OF ')[1]
				else:
					Status = line.split(':')[1]

	if lastreport == "":
		if browser.page_source.find("View Document Images") >= 0:
			browser.find_element_by_link_text("View Document Images").click()
			detailsoup = bs(browser.page_source)
			context['page2'] = browser.page_source.encode('ascii', 'ignore')
			cell = detailsoup.findAll('td')
			for y in range (0, len(cell)):
				line = cell[y].text
				line = ' '.join(line.split())
				if re.search('Filing Date', line) is not None:
					lastreport = cell[y+4].text

	print "ID : ", ID
	print "Agent : ", Agent
	print "Jurisdiction : ", Jurisdiction
	print "Founding Date : ", Founding
	print "Status : ", Status
	print "Status Date :", StatusDate
	print "Last Report : ", lastreport
	
	set_context_details(context,
		browser.current_url,
		ID,
		Founding,
		Status,
		agent_name=Agent,
		jurisdiction=Jurisdiction,
		status_date=StatusDate,
		last_report = lastreport
		)

def fill_context_MN(browser, context):
	url = "http://mblsportal.sos.state.mn.us/"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="BusinessName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="search"]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	table = soup.findAll('table', {'class': "simpleGrid results selectable highlight"})[0]

	if len(table.findAll('tr')) == 0:
		print "Didn't find an active firm, now searching for inactive"
		browser.get(url)
		browser.find_element_by_xpath('//*[@id="BusinessName"]').send_keys(context['companyName'])
		browser.find_element_by_xpath('html/body/div[1]/div/div/div[2]/div[1]/div/form/div[1]/div[1]/a').click()
		time.sleep(1)
		browser.find_element_by_xpath('//*[@id="inactive"]').click()
		time.sleep(1)
		browser.find_element_by_xpath('html/body/div[2]/div[11]/div/button').click()
		time.sleep(1)
		browser.find_element_by_xpath('//*[@id="search"]').click()
		soup = bs(browser.page_source)
		context['page'] = browser.page_source.encode('ascii', 'ignore')
		table = soup.findAll('table', {'class': "simpleGrid results selectable highlight"})[0]

	if len(table.findAll('tr')) == 0:
		context['num_results'] = 0
		return
	if len(table.findAll('tr')) > 1:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('//*[@id="main"]/section/table/tbody/tr/td[1]/div[1]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	details = soup.findAll('div', {'id': "filingSummary"})[0]
	set_context_details(context,
		browser.current_url,
		details.findAll('dl')[2].dd.text,
		details.findAll('dl')[4].dd.text,
		re.sub(r'\s+', ' ', details.findAll('dl')[5].dd.text).strip(),
		)

def fill_context_MO(browser, context):
	global didscrape
	details_url = "cache"
	filename = "{0}_{1}.html".format(context['id2'], context['sta'])
	context['cached_file'] = filename
	filename = "{0}/{1}".format(cachedir, filename)
	if os.path.exists(filename):
		didscrape = 0
		print "didscrape is now : ", didscrape
		f = open(filename, "r")
		data = f.read().decode('ascii')
		print "Now passing file to beatifulsoup"
		soup = bs(data)
		context['page'] = data.encode('ascii', 'ignore')
		if soup.find(text=re.compile('Click on the Business Entity Name or Charter Number to view more information')) is not None:
			print "many"
			context['num_results'] = 'many'
			return
	else:
		url = "http://www.sos.mo.gov/BusinessEntity/soskb/csearch.asp"
		browser.get(url)
		browser.find_element_by_xpath('//*[@id="right"]/form/p[1]/font[2]/input[1]').send_keys(context['companyName'])
		browser.find_element_by_xpath('//*[@id="right"]/form/p[1]/font[2]/input[2]').click()
		if browser.page_source.find("No Records were found for the search criteria") >= 0:
			print "zero"
			context['num_results'] = 0
			return
		soup = bs(browser.page_source)
		context['page'] = browser.page_source.encode('ascii', 'ignore')
		rows = soup.findAll('table')[2].findAll('tr')
		if len(rows) > 4:
			context['num_results'] = 'many'
			return
		details_url = urlparse.urljoin(browser.current_url, rows[3].a['href'])
		soup = getsoup(details_url, None, context)

	data = soup.findAll('table')[0].findAll('tr')
	date = ""
	id = ""
	lastreport = ""
	status = ""
	agent = ""
	jurisdiction = ""
	for x in range (0, len(data)):
		line = data[x].findAll('td')[0].text
		if re.search('Charter Number:', line) is not None:
			id = data[x].findAll('td')[1].text
		if re.search('Status:', line) is not None:
			status = data[x].findAll('td')[1].text
		if re.search('Entity Creation Date:', line) is not None:
			date = data[x].findAll('td')[1].text
		if re.search('Last Annual Report Filed:', line) is not None:
			lastreport = data[x].findAll('td')[1].text
		if re.search('Agent Name:', line) is not None:
			agent = data[x].findAll('td')[1].text
		if re.search('State of Business.:', line) is not None:
			jurisdiction = data[x].findAll('td')[1].text
	print "URL :", details_url
	print "ID :", id
	print "Date :", date
	print "Status: ", status
	print "Last report: ", lastreport
	print "Agent: ", agent
	print "Jurisdiction: ", jurisdiction
	set_context_details(context,
		details_url,
		id,
		date,
		status,
		agent_name = agent,
		jurisdiction = jurisdiction,
		last_report = lastreport
		)

def fill_context_MS(browser, context):
	url = "https://business.sos.state.ms.us/corp/soskb/CSearch.asp"
	browser.get(url)
	browser.find_element_by_xpath('/html/body/table/tbody/tr/td[2]/table[2]/tbody/tr[1]/td[2]/table/tbody/tr/td/blockquote/form/p/font/font/input[1]').send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/table/tbody/tr/td[2]/table[2]/tbody/tr[1]/td[2]/table/tbody/tr/td/blockquote/form/p/font/font/input[2]').click()
	if browser.page_source.find("No Records were found for the search criteria") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[10].findAll('tr')
	if len(rows) > 4:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('/html/body/table/tbody/tr/td[2]/table[2]/tbody/tr[1]/td[2]/table/tbody/tr/td/table/tbody/tr[3]/td/table/tbody/tr[4]/td[1]/font/a').click()
	details_url = browser.current_url
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.findAll('table')[9].findAll('tr')
	status = data[6].findAll('td')[1].text
	browser.find_element_by_xpath('/html/body/table/tbody/tr/td[2]/table[2]/tbody/tr[1]/td[2]/table/tbody/tr/td/div/center/table/tbody/tr/td[2]/a/b/font').click()
	context['page2'] = browser.page_source.encode('ascii', 'ignore')
	soup2 = bs(browser.page_source)
	last_report = soup2.findAll('table')[9].findAll('tr')[1].findAll('td')[1].text
	inactive_date = ""
	if status != "Good Standing":
		inactive_date = last_report
	set_context_details(context,
		details_url,
		data[5].findAll('td')[1].text,
		data[8].findAll('td')[1].text,
		status,
		inactive_date=inactive_date,
		last_report=last_report,
		)

def fill_context_MT(browser, context):
	url = "https://app.mt.gov/bes/"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="bessearch"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/table[3]/tbody/tr[4]/td/input[2]').click()
	if browser.page_source.find("is not registered with the Secretary of State.") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[5].findAll('tr')
	if len(rows) > 4:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[1].a['href'])
	soup = getsoup(details_url, None, context)
	data = soup.findAll('table')[4].findAll('tr')[0].findAll('td')[0].text
	inactive_date = ""
	if data.find("Inactive Date:") >= 0:
		inactive_date = re.sub(".*Inactive Date:([^a-zA-Z]*)[a-zA-Z].*", "\\1", data, flags=re.S)
	expiration_date = ""
	if data.find("Expiration Date:") >= 0:
		expiration_date = re.sub(".*Expiration Date:([^a-zA-Z]*)[a-zA-Z].*", "\\1", data, flags=re.S)
	set_context_details(context,
		details_url,
		re.sub(".*ID #:([^:]+)(?:Type|Status):.*", "\\1", data, flags=re.S),
		re.sub(".*(?:Filing Date|Date of (?:Incorporation|Organization)):([^a-zA-Z]*)[a-zA-Z].*", "\\1", data, flags=re.S),
		re.sub(".*Status:([^:]*)Status Reason:.*", "\\1", data, flags=re.S),
		inactive_date=inactive_date,
		expiration_date=expiration_date,
		)

def fill_context_NC(browser, context):
	url = "http://www.secretary.state.nc.us/corporations/CSearch.aspx"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="SosContent_SosContent_SearchStr"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="SosContent_SosContent_cmdSearch"]').click()
	if browser.page_source.find("No Records Found.") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[-1].findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[1].a['href'])
	browser.find_element_by_xpath('//*[@id="SosContent_SosContent_dgCorps"]/tbody/tr[2]/td[2]/a').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.find("table", {"id": "SosContent_SosContent_WucDocuments1_GridView1"}).findAll('table')[1].findAll('tr')
	id = ""
	status = ""
	date = ""
	for x in range (0, 10):
		statust = data[x].findAll('td')
		for y in range (0, len(statust)):
			if statust[y].text == "SOSID:":
				id = statust[y+1].text
			if statust[y].text == "Status:":
				status = statust[y+1].text
			if statust[y].text == "Effective Date:":
				date = statust[y+1].text
			print "Row {}, column {} : {}".format(x, y, statust[y].text)
	
	print "id: ", id
	print "status: ", status
	print "date: ", date 
	
	inactive_date = ""
	if status != "Current-Active":
		browser.find_element_by_xpath('//*[@id="SosContent_SosContent_WucDocuments1_GridView1"]/tbody/tr/td/table[1]/tbody/tr[3]/td/a[1]').click()
		context['page2'] = browser.page_source.encode('ascii', 'ignore')
		soup = bs(browser.page_source)
		inactive_date = soup.table.findAll('tr')[-1].findAll('td')[1].text
	set_context_details(context,
		details_url,
		id,
		date,
		status,
		inactive_date=inactive_date,
		)

def fill_context_ND(browser, context):
	url = "https://apps.nd.gov/sc/busnsrch/busnSearch.htm"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="srchType"]/option[text()="partial match with all of the words"]').click()
	browser.find_element_by_xpath('//*[@id="searchName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="buttonsearch"]/input[1]').click()
	time.sleep(1)
	if browser.page_source.find("No Entities were found matching your selection criteria") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[1].findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('//*[@id="BusnSrchFM"]/div[1]/div/table/tbody/tr[2]/td[3]/a').click()
	details_url = browser.current_url
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.findAll('table')[1].findAll('tr')
	set_context_details(context,
		details_url,
		re.sub(".*:", "", data[0].findAll('td')[0].findAll('li')[0].text, flags=re.S),
		re.sub(".*:", "", data[0].findAll('td')[0].findAll('li')[2].text, flags=re.S),
		re.sub(".*:", "", data[0].findAll('td')[0].findAll('li')[1].text, flags=re.S),
		inactive_date=re.sub(".*:", "", data[0].findAll('td')[1].findAll('li')[1].text, flags=re.S),
		)

def fill_context_NE(browser, context):
	raise NotImplementedError("must be gathered manually")

def fill_context_NH(browser, context):
	url = "https://www.sos.nh.gov/corporate/soskb/csearch.asp"
	browser.get(url)
	browser.find_element_by_xpath('/html/body/div/table[2]/tbody/tr/td[3]/blockquote/form/p/font[2]/input[1]').send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/div/table[2]/tbody/tr/td[3]/blockquote/form/p/font[2]/input[2]').click()
	if browser.page_source.find("No Records were found for the search criteria") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[6].findAll('tr')
	if len(rows) > 4:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[3].td.a['href'])
	soup = getsoup(details_url, None, context)
	data = soup.findAll('table')[5].findAll('tr')
	i = 0
	while data[i].td.text != "Business ID:":
		i += 1
	set_context_details(context,
		details_url,
		data[i].findAll('td')[1].text,
		data[i+3].findAll('td')[1].text,
		data[i+1].findAll('td')[1].text,
		inactive_date=data[i+9].findAll('td')[1].text,
		)

def fill_context_NJ(browser, context):
	url = "https://www.njportal.com/DOR/businessrecords/EntityDocs/BusinessStatCopies.aspx"
	browser.get(url)
	wait()
	browser.find_element_by_xpath('//*[@id="mainContent_wzMain_searchInput_rblSearchType_0"]').click()
	wait()
	browser.find_element_by_xpath('//*[@id="mainContent_wzMain_searchInput_txtBusinessName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="mainContent_wzMain_StartNavigationTemplateContainerID_btnContinue"]').click()
	wait(10)
	try:
		browser.find_element_by_xpath('//*[@id="mainContent_wzMain_searchResult_gvCopiesSearchResult"]/tbody/tr[3]')
		context['num_results'] = 'many'
		return
	except:
		pass
	try:
		browser.find_element_by_xpath('//*[@id="mainContent_wzMain_searchResult_gvCopiesSearchResult"]/tbody/tr[2]')
	except:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	table = soup.findAll('table', {'id': "mainContent_wzMain_searchResult_gvCopiesSearchResult"})[0].findAll('tr')[1]
	set_context_details(context,
		browser.current_url,
		table.findAll('td')[3].text,
		table.findAll('td')[6].text,
		"",
		)
	browser.find_element_by_xpath('//*[@id="mainContent_wzMain_searchResult_gvCopiesSearchResult_cbCopies_0"]').click()
	browser.find_element_by_xpath('//*[@id="mainContent_wzMain_StepNavigationTemplateContainerID_btnContinue"]').click()
	context['page'] = browser.page_source.encode('ascii', 'ignore')

def fill_context_NM(browser, context):
	url = "http://portal.sos.state.nm.us/corps/Corplookup/Lookdn.aspx"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="ctl00_MainContent_txtName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="ctl00_MainContent_btnSearch"]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[4].findAll('tr')
	if len(rows) == 1:
		context['num_results'] = 0
		return
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[1].findAll('td')[5].a['href'])
	soup = getsoup(details_url, None, context)
	data = soup.findAll('table')[3].findAll('tr')
	status = data[1].findAll('td')[1].text
	inactive_date = ""
	if status != "Active Corporation":
		inactive_date = soup.findAll('table')[8].findAll('tr')[-3].findAll('td')[1].text
	set_context_details(context,
		details_url,
		data[0].findAll('td')[1].text,
		data[2].findAll('td')[1].text,
		status,
		inactive_date=inactive_date,
		)

def fill_context_NV(browser, context):
	url = "http://nvsos.gov/sosentitysearch/"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="ctl00_MainContent_txtSearchBox"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="ctl00_MainContent_btnCorpSearch"]').click()
	if browser.page_source.find("No results for entity name search on") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	tables = soup.findAll('table')
	print "Number of tables : ", len(tables)
	tabint = 12
	for x in range (0, len(tables)):
		if tables[x].findAll('tr')[0].findAll('td')[0].text == "Entity Name":
			tabint = x
			print "table of Interest is: ", tabint
	rows = soup.findAll('table')[tabint].findAll('tr')

	details_url = ""

	if len(rows) == 3:
		details_url = urlparse.urljoin(browser.current_url, rows[1].a['href'])

	if len(rows) > 3:
		# Try to find a perfect match, if not return many
		links = soup.findAll('a')
		print "Found links : ", len(links)
		for x in range (0, len(links)):
			if links[x].text.replace(',', '').replace('.', '') == context['companyName']:
				details_url = urlparse.urljoin(url, links[x]['href'])
	
	if details_url == "":
		context['num_results'] = 'many'
		return

	browser.get(details_url)
	soup = bs(browser.page_source)
	data = soup.findAll('table')[14].findAll('tr')
	status = data[0].findAll('td')[1].text
	inactive_date = ""
	if status != "Active":
		links = soup.findAll('a')
		for x in range (0, len(links)):
			if re.search('Click here', links[x].text) is not None:
				fsoup = getsoup(urlparse.urljoin(details_url, links[x]['href']), None, context, key='page2')
				inactive_date = fsoup.findAll('table')[14].findAll('tr')[2].findAll('td')[1].text	
				inactive_date = re.search(r'\d{1,}/\d{1,}/\d{4}', inactive_date)
				inactive_date=inactive_date.group()
	set_context_details(context,
		details_url,
		data[1].findAll('td')[3].text,
		data[0].findAll('td')[3].text,
		status,
		inactive_date=inactive_date
		)
		

def fill_context_NY(browser, context):
	url = "http://www.dos.ny.gov/corps/bus_entity_search.html"
	form_action = "http://appext20.dos.ny.gov/corp_public/CORPSEARCH.SELECT_ENTITY"
	params = {
		'p_entity_name': context['companyName'],
		'p_name_type': '%', # use 'A' for active, '%' for all
		'p_search_type': 'BEGINS', # 'BEGINS', 'CONTAINS', 'PARTIAL'
		}
	soup = getsoup(form_action, params, context)
	if soup.text.find("No business entities were found for") >= 0:
		context['num_results'] = 0
		return
	messages = soup.find('p', { 'class': "messages" })
	if not messages.text == "Only one entity was found.":
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(form_action, soup.find('td', { 'headers': "c1" }).a['href'])
	soup = getsoup(details_url, None, context)
	table = soup.find('table')
	set_context_details(context,
		details_url,
		table.findAll('tr')[1].td.text,
		table.findAll('tr')[2].td.text,
		table.findAll('tr')[6].td.text,
		jurisdiction=table.findAll('tr')[4].td.text,
		)

def fill_context_OH(browser, context):
	url = "http://www2.sos.state.oh.us/pls/bsqry/f?p=100:1:2634963572615303::NO:1:P1_TYPE:NAME"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="P1_BUSINESS_NAME"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="BSSEARCH"]').click()
	time.sleep(1)
	soup = bs(browser.page_source)
	if soup.text.find("Total Number of filings found :0") >= 0:
		context['num_results'] = 0
		return
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	if len(soup.findAll('table')[12].findAll('tr')) > 2:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('//*[@id="report_R25074845068105897"]/tbody/tr[2]/td/table/tbody/tr[2]/td[1]/a[1]').click()
	time.sleep(1)
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	details = soup.findAll('td', {'class':"t12Body"})[0].findAll('table')[0].tr.td.table
	tables = soup.findAll('table')
	print "Number of tables : ", len(tables)
	for x in range (0, len(tables)):
		if len(tables[x].findAll('tr')) > 0 and len(tables[x].findAll('tr')[0].findAll('td'))>0:
			if tables[x].findAll('tr')[0].findAll('td')[0].text == "Filings":
				tabint = x
	
	rows = soup.findAll('table')[tabint].findAll('tr')
	last_report = soup.findAll('table')[tabint].findAll('tr')[len(rows)-1].findAll('td')[1].text
	print "Date in last entry : ", last_report
	set_context_details(context,
		browser.current_url,
		details.findAll('tr')[1].findAll('td')[1].text,
		details.findAll('tr')[5].findAll('td')[1].text,
		details.findAll('tr')[4].findAll('td')[1].text,
		)
	context['last_report'] = last_report


def fill_context_OK(browser, context):
	raise NotImplementedError("must be gathered manually")

def fill_context_OR(browser, context):
	url = "http://egov.sos.state.or.us/br/pkg_web_name_srch_inq.login"
	browser.get(url)
	browser.find_element_by_xpath('/html/body/form/table[3]/tbody/tr[2]/td[2]/input').send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/form/table[6]/tbody/tr/td[2]/input').click()
	if browser.page_source.find("Your search returned no business entity names.") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[3].findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[1].findAll('td')[3].a['href'])
	soup = getsoup(details_url, None, context)
	data = soup.findAll('table')[2].findAll('tr')
	status = data[1].findAll('td')[2].text
	inactive_date = ""
	if status != "ACT":
		numtables = len(soup.findAll('table'))
		for x in range (0, numtables):
			if len(soup.findAll('table')[x].findAll('tr')[0].findAll('td')) >= 3:
				if soup.findAll('table')[x].findAll('tr')[0].findAll('td')[2].text == "Summary History":
					inactive_date = soup.findAll('table')[x+1].findAll('tr')[1].findAll('td')[2].text
	if status == "ACT":
		status = "Active"
	elif status == "INA":
		status = "Inactive"
	set_context_details(context,
		details_url,
		data[1].findAll('td')[0].text,
		data[1].findAll('td')[4].text,
		status,
		inactive_date=inactive_date,
		)


is_PA_authenticated = False
def fill_context_PA(browser, context):
	global is_PA_authenticated
	url = "https://www.corporations.state.pa.us/corp/soskb/csearch.asp"
	if not is_PA_authenticated:
		login_url = "https://www.corporations.state.pa.us/corp/soskb/login.asp"
		browser.get(login_url)
		wait_for_user("please enter your credentials in the window and click the 'Login' button")
		is_PA_authenticated = True
	if browser.current_url[:37] == url[:37]:
		browser.find_element_by_xpath('/html/body/table[3]/tbody/tr/td[2]/table/tbody/tr[2]/td[2]/a/font').click()
	else:
		browser.get(url)
	browser.find_element_by_xpath('/html/body/table[3]/tbody/tr/td[4]/blockquote/form/p[1]/font[2]/input[1]').send_keys(context['companyName'])
	browser.find_element_by_xpath('/html/body/table[3]/tbody/tr/td[4]/blockquote/form/p[1]/font[2]/input[2]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	if soup.text.find('Human Check:') >= 0:
		wait_for_user("please fill in the Captcha and click submit")
	time.sleep(3)
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	table = soup.findAll('table')[5].tr.findNextSiblings('tr')[0].table
	if table == None:
		context['num_results'] = 0
		return
	if len(table.findAll('tr')) > 4:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('/html/body/table[3]/tbody/tr/td[4]/table/tbody/tr[2]/td/table/tbody/tr[4]/td/font/a').click()
	context['page2'] = browser.page_source.encode('ascii', 'ignore')
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	details = soup.findAll('table')[6]
	set_context_details(context,
		browser.current_url,
		details.findAll('tr')[5].findAll('td')[1].font.text,
		details.findAll('tr')[8].findAll('td')[1].font.text,
		details.findAll('tr')[6].findAll('td')[1].font.text,
		)

def fill_context_SC(browser, context):
	url = "http://www.sos.sc.gov/Search%20Business%20Filings"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="content"]/div[1]/form[1]/input[1]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="content"]/div[1]/form[1]/input[2]').click()
	if browser.page_source.find("No Results Found.") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('ol')[0].findAll('li')
	if len(rows) > 1:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('//*[@id="content"]/div/ol/li/a').click()
	details_url = browser.current_url
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.findAll('table')[0].findAll('tr')
	status = data[1].findAll('td')[1].text
	inactive_date = ""
	if not status in ("Good Standing", "Active"):
		inactive_date = soup.findAll('table')[1].findAll('tr')[1].findAll('td')[1].text
	set_context_details(context,
		details_url,
		details_url.split('corporateid=')[1].split('&')[0],
		data[11].findAll('td')[1].text,
		status,
		taxid="",
		jurisdiction="",
		agent_name="",
		last_report="",
		status_date="",
		entity_type="",
		inactive_date="",
		expiration_date=data[13].findAll('td')[1].text,
		)

def fill_context_SD(browser, context):
	raise NotImplementedError("must be gathered manually")

def fill_context_TN(browser, context):
	url = "https://tnbear.tn.gov/Ecommerce/FilingSearch.aspx"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="ctl00_MainContent_txtSearchValue"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="ctl00_MainContent_SearchButton"]').click()
	if browser.page_source.find("No Records Found....") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.findAll('table')[4].findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	id = rows[1].td.text
	details_url = urlparse.urljoin(browser.current_url, rows[1].a['href'])
	browser.get(details_url)
	time.sleep(1)
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.findAll('table')[2].findAll('tr')
	set_context_details(context,
		details_url,
		id,
		data[6].findAll('td')[3].text,
		data[6].findAll('td')[1].text,
		inactive_date=data[9].findAll('td')[3].text,
		)

def fill_context_TX(browser, context):
	raise NotImplementedError("must be gathered manually")

def fill_context_UT(browser, context):
	url = "https://secure.utah.gov/bes/"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="searchName"]/p/input[1]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="index.searchByName"]').click()
	if browser.page_source.find("No results found for ") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.find('div', { 'class': "entities" }).findAll('div', { 'class': "entityRow" })
	if len(rows) > 1:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('//*[@id="results"]/div[1]/div[2]/div[1]/a').click()
	details_url = browser.current_url
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.find('form', { 'id': "details" }).text.encode('ascii', 'ignore')
	status = re.sub(".*Status:([^:]+[0-9])[a-zA-Z ]+:.*", "\\1", data, flags=re.S).split('as of ')
	experation_date = ""
	if len(status) > 1:
		expiration_date = status[1]
	status = status[0]
	set_context_details(context,
		details_url,
		re.sub(".*Entity Number:([^:]+)Company Type:.*", "\\1", data, flags=re.S),
		re.sub(".*Registration Date:([^:]+)Last Renewed:.*", "\\1", data, flags=re.S),
		status,
		expiration_date=expiration_date,
		)

def fill_context_VA(browser, context):
	raise NotImplementedError("must be gathered manually")

def fill_context_VT(browser, context):
	raise NotImplementedError("must be gathered manually")

def fill_context_WA(browser, context):
	url = "http://www.sos.wa.gov/corps/corps_search.aspx"
	data_url = "http://www.sos.wa.gov/corps/search_detail.aspx?ubi={}"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="name"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="one-col-a"]/div/form/p[3]/input[2]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	try:
		links = soup.findAll('ul', { 'class': "CorpsListItems" })[0].findAll('a')
	except:
		context['num_results'] = 0
		return
	atag = None
	if len(links) == 1:
		atag = links[0]
	else:
		for link in links:
			if link.text == context['companyName']:
				atag = link
	if atag == None:
		context['num_results'] = 'many'
		return
	id = atag['onclick'].split("'")[1]
	details_url = data_url.format(id)
	browser.get(details_url)
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.findAll('table', { 'class': "CorpDetail" })[0]
	set_context_details(context,
		details_url,
		data.findAll('tr')[0].findAll('td')[1].text,
		data.findAll('tr')[5].findAll('td')[1].text,
		data.findAll('tr')[3].findAll('td')[1].text,
		inactive_date=data.findAll('tr')[5].findAll('td')[1].text,
		expiration_date=data.findAll('tr')[4].findAll('td')[1].text,
		)

def fill_context_WI(browser, context):
	raise NotImplementedError("must be gathered manually")

def fill_context_WV(browser, context):
	url = "http://apps.sos.wv.gov/business/corporations/"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="txtOrgName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="btnSearch"]').click()
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.find('table', { 'id': "tableResults" }).findAll('tr')
	if rows[2].td.text == "No results found.":
		context['num_results'] = 0
		return
	if len(rows) > 4:
		context['num_results'] = 'many'
		return
	details_url = urlparse.urljoin(browser.current_url, rows[2].a['href'])
	soup = getsoup(details_url, None, context)
	data = soup.find('table', { 'id': "tableResults" }).findAll('tr')[2].findAll('td')
	inactive_date = data[6].text
	if inactive_date == "":
		status = "Active"
	else:
		status = "Inactive"
	set_context_details(context,
		details_url,
		details_url.split('org=')[1].split('&')[0],
		data[1].text,
		status,
		inactive_date=inactive_date,
		)

def fill_context_WY(browser, context):
	url = "https://wyobiz.wy.gov/Business/FilingSearch.aspx"
	browser.get(url)
	browser.find_element_by_xpath('//*[@id="ctl00_contentMain_txtFilingName"]').send_keys(context['companyName'])
	browser.find_element_by_xpath('//*[@id="ctl00_contentMain_cmdSearch"]').click()
	if browser.page_source.find("No Results Found.") >= 0:
		context['num_results'] = 0
		return
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	rows = soup.find('table', { 'id': "filings" }).findAll('tr')
	if len(rows) > 2:
		context['num_results'] = 'many'
		return
	browser.find_element_by_xpath('//*[@id="filings"]/tbody/tr[2]/td[1]/a').click()
	details_url = browser.current_url
	soup = bs(browser.page_source)
	context['page'] = browser.page_source.encode('ascii', 'ignore')
	data = soup.find('table', { 'id': "filingDetails" }).findAll('tr')
	set_context_details(context,
		details_url,
		data[2].findAll('td')[1].text,
		data[7].findAll('td')[3].text,
		data[1].findAll('td')[3].text,
		inactive_date=data[9].findAll('td')[3].text,
		)

fill_functions = {
	'AK': fill_context_AK,
	'AL': fill_context_AL,
	'AR': fill_context_AR,
	'AZ': fill_context_AZ,
	'CA': fill_context_CA,      
	'CO': fill_context_CO,
	'CT': fill_context_CT,
	'DE': fill_context_DE,  
	'FL': fill_context_FL,
	'GA': fill_context_GA,
	'HI': fill_context_HI,
	'IA': fill_context_IA,
	'ID': fill_context_ID,
	'IL': fill_context_IL,
	'IN': fill_context_IN,
	'KS': fill_context_KS,
	'KY': fill_context_KY,
	'LA': fill_context_LA,
	'MA': fill_context_MA,
	'MD': fill_context_MD,
	'ME': fill_context_ME,
	'MI': fill_context_MI,
	'MN': fill_context_MN,
	'MO': fill_context_MO,
	'MS': fill_context_MS,
	'MT': fill_context_MT,
	'NC': fill_context_NC,
	'ND': fill_context_ND,
#	'NE': fill_context_NE,      <- must be manually performed
	'NH': fill_context_NH,
	'NJ': fill_context_NJ,
	'NM': fill_context_NM,
	'NV': fill_context_NV,
	'NY': fill_context_NY,
	'OH': fill_context_OH,
#	'OK': fill_context_OK,      <- must be manually performed
	'OR': fill_context_OR,
	'PA': fill_context_PA,
#	'RI': fill_context_,        <- not yet implemented, site down ATM
	'SC': fill_context_SC,
#	'SD': fill_context_SD,      <- must be manually performed
	'TN': fill_context_TN,
#	'TX': fill_context_TX,      <- must be manually performed
	'UT': fill_context_UT,
#	'VA': fill_context_VA,      <- must be manually performed
#	'VT': fill_context_VT,      <- must be manually performed
	'WA': fill_context_WA,
#	'WI': fill_context_WI,      <- will be manually performed
	'WV': fill_context_WV,
	'WY': fill_context_WY,
}
def fill_context(browser, context, last_state, processed_entities):
	global didscrape
	state = context['sta']
	if state not in fill_functions:
		context['status'] = "no handler for {}".format(state)
		return
	name = context['companyName']
	if state in processed_entities:
		if name in processed_entities[state]:
			print "not looking up {}, already have data from previous duplicate name".format(name)
			context['status'] = "previously processed"
			context['num_results'] = "see other record"
			return
	else:
		processed_entities[state] = {}

	if state == last_state:
		delay()
	print "searching {} for {}".format(state, name)
	try:
		fill_functions[state](browser, context)
		print "Back from fill function, didscrape is : ", didscrape
	except LoadFailedError:
		context['status'] = "FAILED TO LOAD"
		context['num_results'] = "ERROR"
		return
	except NotImplementedError as e:
		context['status'] = "ERROR: {}".format(e.message)
		context['num_results'] = "ERROR"
		return
	except Exception as e:
		context['status'] = "UNKNOWN ERROR: {}".format(e)
		context['num_results'] = "ERROR"
		return
	print "found:", context['num_results']
	processed_entities[state][name] = True
	return

def write_to_cache(context, cachedir):
	filename = "{0}_{1}.html".format(context['id2'], context['sta'])
	context['cached_file'] = filename
	filename = "{0}/{1}".format(cachedir, filename)
#	if os.path.exists(filename):
#		print "ERROR: file already exists: {}".format(filename)
#		raise Exception("file already exists")
	with open(filename, "w") as cachefile:
		cachefile.write(context['page'])
	if 'page2' in context:
		filename = "{0}_{1}_supplemental.html".format(context['id2'], context['sta'])
		context['cached_file'] = ",".join([ context['cached_file'], filename ])
		filename = "{0}/{1}".format(cachedir, filename)
#		if os.path.exists(filename):
#			print "ERROR: file already exists: {}".format(filename)
#			raise Exception("file already exists")
		with open(filename, "w") as cachefile:
			cachefile.write(context['page2'])

def process(inputfilename, outputfilename, cachedir):
	global didscrape
	processed_entities = {}
	completed = {}
	processed_data = []
	try:
		with open(outputfilename) as outfile:
			data = outfile.read().splitlines()
			for line in data[1:]:
				fields = line.split(out_delimiter)
				context = { name:fields[i] for (i,name) in field_index.iteritems() }
				state = context['sta']
				if context['num_results'] != "ERROR":
					processed_data.append(line)
					if state not in processed_entities:
						processed_entities[state] = {}
					processed_entities[state][context['companyName']] = True
					completed[context['id1']] = True
	except IOError:
		pass
	tmpoutputfilename = "{}.tmp".format(outputfilename)
	with open(tmpoutputfilename, 'w') as outfile:
		outfile.write(out_delimiter.join([ field_index[i] for i in range(len(field_index)) ]))
		outfile.write("\n")
		for line in processed_data:
			outfile.write(line)
			outfile.write('\n')
		os.rename(tmpoutputfilename, outputfilename)
	del processed_data
	with open(inputfilename) as infile:
		data = [s.strip() for s in infile.read().splitlines()]
	print "******************************"
	print " CHOOSE YOUR BROWSER        "
	print "                            "
	print " 1: CHROME                  "
	print " 2: FIREFOX                 "
	print "                            "
	print "******************************"
	select = raw_input ("Select your option: ")
	if select == '1':
		browser = webdriver.Chrome()
		url = "https://chrome.google.com/webstore/detail/stop-load/andkkobbpjnjlenkopioemlapmlcpbfl"
		browser.get(url)
		wait_for_user("Install the extension and continue!")
	elif select == "2":
		browser = webdriver.Firefox()
	else:
		print "Option does not exist"
		sys.exit(2)
	last_state = None
	try:
		with open(outputfilename, 'a', 1) as outfile:
			for line in data[1:]:
				fields = line.split(in_delimiter)
				context = { name:'' for name in field_index.values() }
				context['id1'] = fields[0].strip()
				context['id2'] = fields[1].strip()
				context['companyName'] = fields[2].strip()
				context['sta'] = fields[3].strip()
				context['num_results'] = "ERROR"
				if context['id1'] in completed:
					print "skipping {}, already processed".format(context['companyName'])
					continue
				print "About to test didscrape, it is : ", didscrape
				if didscrape == 0:
					last_state = ""
					didscrape = 1
				fill_context(browser, context, last_state, processed_entities)
				print "Back from fill context, didscrape is : ", didscrape
				last_state = context['sta']
				if context['num_results'] not in ["ERROR", "see other record", 0]:
					if context['sta'] == "NJ":
						print "Not writing to cache: Many in NJ made it crash and burn!"
					else:
						write_to_cache(context, cachedir)
				outfile.write(out_delimiter.join(
					[ re.sub(whitespace, ' ', unicode(context[field_index[i]]).encode('utf-8', 'ignore')) for i in range(len(field_index)) ]
					))
				outfile.write('\n')
	finally:
		browser.quit()

usage = "get_company.py\n\t-i <inputfile> -c <cache directory>\n\t-m <min retry delay> -x <max retry delay>"

def main(argv):
	global mindelay
	global maxdelay
	global cachedir
	global didscrape
	didscrape = 0
	inputfilename = None
	cachedir = None
	outputfilename = None
	try:
		opts, args = getopt.getopt(argv, "hi:c:m:x:", ["ifile=","cachedir=","mindelay=","maxdelay="])
		for opt, arg in opts:
			if opt == '-h':
				print usage
				sys.exit()
			elif opt in ("-i", "--ifile"):
				inputfilename = arg
			elif opt in ("-c", "--cachedir"):
				cachedir = arg
			elif opt in ("-m", "--mindelay"):
				mindelay = int(arg)
			elif opt in ("-x", "--maxdelay"):
				maxdelay = int(arg)
	except getopt.GetoptError:
		print usage
		sys.exit(2)
	except:
		print usage
		sys.exit(3)
	if inputfilename == None:
		print "ERROR: no input file provided, use get_company.py -h for help"
		sys.exit(4)
	if maxdelay < mindelay:
		maxdelay = mindelay
	try:
		if inputfilename[-4:] != '.csv':
			print "ERROR: expect input file to be of type CSV"
			sys.exit(5)
		with open(inputfilename): pass
		outputfilename = inputfilename.replace('.csv', '_out.csv')
	except IOError:
		print "ERROR: input file '{0}' doesn't exist, can't continue".format(inputfilename)
		sys.exit(6)
	if cachedir == None:
		print "ERROR: no cache directory specified"
		sys.exit(7)
	if not os.path.exists(cachedir):
		os.makedirs(cachedir)
	elif not os.path.isdir(cachedir):
		print "ERROR: specified cache directory exists but is not a directory"
		sys.exit(8)
	try:
		with open(outputfilename):
			print "output file '{0}' already exists, continuing to process incomplete and unstarted records".format(outputfilename)
	except IOError:
		pass
	process(inputfilename, outputfilename, cachedir)

if __name__ == "__main__":
	main(sys.argv[1:])
