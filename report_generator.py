# REQUIREMENTS :
#   appdirs==1.4.3
#   beautifulsoup4==4.5.3
#   packaging==16.8
#   pkg-resources==0.0.0
#   pyparsing==2.2.0
#   requests==2.13.0
#   six==1.10.0
#   urllib3==1.20
#   xlwt==1.2.0
#   lxml==3.7.3
#   cssselect==1.0.1

import argparse
import xlwt
import json
import openpyxl
import lxml.html
import os

from bs4 import BeautifulSoup
from lxml.cssselect import CSSSelector
from datetime import datetime, timedelta
from copy import deepcopy
from requests import get
from shutil import copyfile


def parse_args():
    try: 
        parse = argparse.ArgumentParser()
        group = parse.add_mutually_exclusive_group(required=True)
        group.add_argument('-w', '--weekly', action='store_true',
                           help=''' Generate list for previous week ''')
        group.add_argument('-m', '--monthly', action='store_true',
                           help=''' Generate list for previous Month ''')
    except argparse.ArgumentError:
        parse.exit("Exiting. Read help for further information 'python create_tarball.py --help'") 
    return parse.parse_args()


def suppressors(fun):
    def fun_wrapper(*largs, **kargs):
        try:
            print ('\nScraping {}'.format(largs[-1]), end=" ")
            return fun(*largs, **kargs)
        except:
            print('\nError while handling {}'.format(largs[-1]))
            print ('Skipping url')
            pass
    return fun_wrapper

class DataScraper:    
    def __init__(self):
        ''' Initializing data structure, self.value is a python dict
       which is used for storing fields of excel table '''
        self.value ={'val_name': '--',
                    'severity' : '--',
                    'date' : '--',
                    'description': '--',
                    'affected': '--',
                    'solution': '--',
                    'link': '--'
                    }
        self.data = []

    def get_html_data(self, url):
         ''' Method to fetch html data and return a Beutifulsoup object'''
         print('.', end=" ")
         return BeautifulSoup(get(url).text, "html.parser")

    @suppressors
    def scrape_kb_crt(self, url):
        ''' This method is used for parsing www.kb.cert.or'''
        data = self.get_html_data(url)
        lists = data.find(id="list-of-vuls").find_all("li") # Selecting list of valuns from https://www.kb.cert.org/vuls/
        for li in lists:
            temp_data = deepcopy(self.value)                # creating copy of self.value 
            temp_data['val_name'] = li.find("span", class_="vul-title truncate").text # parsing name using class name of span
            date = li.find("span", class_="vul-date").text  # parsing published using class name of span 
            temp_data['date'] = datetime.strptime(date, '%d %b %Y').date()
            page_link = "{}{}".format(url.strip('/vuls/'),li.a['href'])   # Creating link address
            temp_data['link'] = page_link
            new_data = self.get_html_data(page_link).find(id="vulnerability-note-content") # fetching link data and selecting a specific div using id 
            temp_data['description'] = new_data.p.text
            temp_data['solution'] = new_data.find_all("table")[2].find("tr").text # selecting solution part from html page using 'tr' tabs 
            self.data.append(temp_data) # appending temp data info to class variable called self.data
            temp_data['severity'] = "Medium" 
            temp_data['affected'] = "Please find description"

    @suppressors
    def scrape_vmware(self, url):
        data = self.get_html_data(url)
        section = data.find('div', class_ ="securityadvisorieslisting section")
        blocks = section.find_all("div", class_="news_block")[:10]  # only first 10 numbers

        for block in blocks:
            temp_data = deepcopy(self.value)
            temp_data['date'] = datetime.strptime(block.p.text, '%B %d, %Y').date()
            temp_data['val_name'] = block.a.text.strip()
            link = block.a['href']
            domain_name = url.strip('/security/advisories')
            full_link = domain_name + link
            temp_data['link'] = full_link
            new_data = self.get_html_data(full_link)
            first_table = new_data.find("div", class_='comparisonTable section')
            table_rows = first_table.find_all('div', class_ = 'rTableRow')
            for row in table_rows:
                for span in row.find_all('span'):
                    span.decompose()
                raw_values = row.find_all('div', class_='rTableCell')
                if 'Severity' in raw_values[0].text:
                    temp_data['severity'] = raw_values[1].text
                elif 'Synopsis' in raw_values[0].text:
                    temp_data['description'] = raw_values[1].text

            paragraphs = new_data.find_all('div', class_="paragraphText parbase section")
            relevant_product_section = [ i for i in paragraphs if '2. Relevant Products' in i.text]
            if relevant_product_section:
                ul = relevant_product_section[0].find('ul')
                lis = ul.find_all('li')
                products = ''
                for li in lis:
                    br = li.find('br')
                    if br:
                        br.unwrap()
                    prod = li.text.strip()
                    products = '{}\n{}'.format(products, prod)
                temp_data['affected'] = products

            solution_section = [ i for i in paragraphs if '4. Solution' in i.text]
            if solution_section:                           # need to optimize solution parsing 
                text  = solution_section[0].text.strip()   
                text = text.replace('\xa0', '')
                temp_data['solution'] = text
            self.data.append(temp_data) # appending temp data info to class variable called self.data

    @suppressors
    def scrape_microsoft(self, url):
        ''' This method is used for parsing https://technet.microsoft.com/en-us/security/advisories'''
        data = self.get_html_data(url)      # souping
        table_data = data.find('div', class_="", id="sec_advisory") # identifying the required tag
        for row in table_data.find_all('tr')[1:10]:   # Iterating through advisory column 
            temp_data = deepcopy(self.value)                # creating copy of self.value
            colomns = row.find_all('td')
            date = colomns[0].text.strip()
            temp_data['date'] = datetime.strptime(date, '%m/%d/%Y').date()
            temp_data['val_name'] = colomns[2].text.strip()
            temp_data['severity'] = "Medium"
            page_link = colomns[2].find('a').get('href')    # child link to advisory
            temp_data['link'] = page_link
            new_data = self.get_html_data(page_link)    # souping

            temp_data['description'] = new_data.find("div", id="mainBody").find_all('p')[2].text    
            if new_data.find("table", summary="table"):     # checking for tables
                table = new_data.find("table", summary="table") # table datas
                table_rows = len(table.find_all('tr'))  # validating
                if(table_rows > 2):
                    affected_products = ''
                    for i in range(2,table_rows): # iterating for all affected products list
                        if(table.find_all('tr')[i].p):
                            product = table.find_all('tr')[i].p.text.strip()
                            affected_products = '{}\n{}'.format(affected_products, product)
                            temp_data['affected'] = affected_products
                            
            temp_data['solution'] = "You will need to fix both direct dependencies and review and fix any transitive dependencies. "
            self.data.append(temp_data) # appending temp data info to class variable called self.data

    @suppressors
    def scrape_fortinet(self, url):
        # ''' This method is used for parsing http://www.fortiguard.com/psirt'''
        data_fn = self.get_html_data(url)      # souping
        advisory_fn = data_fn.find('div', class_ ="results") # identifying the required tagset
        section_fn = advisory_fn.find_all('div', class_ ="title")
        for list in section_fn:
            temp_data_fn = deepcopy(self.value)
            temp_data_fn['val_name'] = list.text.strip()
            page_link_fn = "{}{}".format(url.strip('/psirt/'),list.a['href'])
            temp_data_fn['link'] = page_link_fn
            new_data_fn = self.get_html_data(page_link_fn)
            temp_data_fn['description'] = new_data_fn.find_all('div', class_="detail-item")[1].html.body.p.text.strip()
            
            new_table_fn = new_data_fn.find('table', class_="table table-responsive table-borderless")
            date = new_table_fn.find_all('tr')[1].find_all('td')[1].text.strip()
            temp_data_fn['date'] = datetime.strptime(date, '%b %d, %Y').date()
            temp_data_fn['severity'] = "Medium"
            temp_data_fn['affected'] = "Please find description"
            temp_data_fn['solution'] = "Information not available in website" 
            self.data.append(temp_data_fn) # appending temp data info to class variable called self.data

    @suppressors
    def scrape_brocade(self, url):
        # ''' This method is used for parsing http://www.brocade.com/en/support/security-advisories.html'''
        data_br = self.get_html_data(url)      # souping

        table_br = data_br.find('table') # identifying the required tagset
        for row in table_br.find_all('tr')[1:20]:   # Iterating through advisory column 
            temp_data_br = deepcopy(self.value)
            date = row.find_all('td')[3].text.strip()
            temp_data_br['date'] = datetime.strptime(date, '%d %B %Y').date()
            temp_data_br['val_name'] = row.find_all('td')[1].text.strip()
            page_link_br = "http://www.brocade.com"+(row.find_all('td')[0].a['href']) 
            temp_data_br['link'] = page_link_br
            new_data_br = self.get_html_data(page_link_br)
            temp_data_br['description'] = new_data_br.find_all('h1')[1].text.strip()
            
            new_table_br = new_data_br.find_all('table', class_="MsoTableGrid")[1]
            products_br = ''
            for new_row in new_table_br.find_all('tr')[1:]:   # Iterating through products affected column
                prod_br = new_row.find_all('td')[0].text.strip()
                products_br = '{}\n{}'.format(products_br, prod_br)
            temp_data_br['affected'] = products_br
            temp_data_br['solution'] = new_data_br.find_all('p', class_="MsoBodyText")[1].text.strip()

            new2_table_br = new_data_br.find_all('table', class_="MsoNormalTable")[0]
            for new_row in new2_table_br.find_all('p')[4]:   # Iterating through products affected column
                temp_data_br['severity'] = new_row.text.strip()
            self.data.append(temp_data_br) # appending temp data info to class variable called self.data

    def convert_juniper_date(self, date):
        if 'days ago' in date:
            today = datetime.today().date()
            days = int(date.strip('days ago'))
            return today - timedelta(days=days)
        elif 'day ago' in date:
            today = datetime.today().date()
            days = int(date.strip('day ago'))
            return today - timedelta(days=days)
        elif 'hours ago' in date:
            today = datetime.today().date()
            return today
        else:
            return datetime.strptime(date, '%Y-%m-%d').date()

    @suppressors
    def scrape_juniper(self, url):
        # ''' This method is used for parsing https://kb.juniper.net/InfoCenter/index?page=content&channel=SECURITY_ADVISORIES'''
        data_ju = self.get_html_data(url)      # souping
        table_ju1 = data_ju.find('table', summary="components:content:c_list:2", recursive=True) # Table starting at PgNo:1465 # identifying the required tagset
        table_ju2 = data_ju.find('table', summary="components:content:c_list:outer_pagination") # Table starting at PgNo:1469
        table_ju3 = data_ju.find('table', summary="components:content:c_list:upper_pagination") # Table starting at PgNo:1472
        table_ju4 = data_ju.find('table', summary="components:content:c_list:main_list") # Table starting at PgNo:1486
        table_ju5 = data_ju.find('table', class_="gradientContainer") # Table starting at PgNo:1442
        table_ju6 = data_ju.find('table', summary="components:content:c_list:lower_pagination") # Table starting at PgNo:1770
        table_ju7 = data_ju.find('table', cellpadding="2") # Table starting at PgNo:1842

        for row in table_ju7.find_all('tr', class_='odd', recursive=True):   # Iterating through advisory column 

            temp_data_ju = deepcopy(self.value)
            temp_data_ju['val_name'] = row.find_all('td')[1].text.strip()
            temp_data_ju['description'] = row.find_all('td')[2].text.strip()
            date = row.find_all('td')[4].text.strip()
            temp_data_ju['date'] = self.convert_juniper_date(date)

            page_link_ju = "https://kb.juniper.net/InfoCenter/"+(row.find_all('td')[2].a['href']) 

            temp_data_ju['link'] = page_link_ju
            new_data_ju = self.get_html_data(page_link_ju)
            temp_data_ju['affected'] = new_data_ju.find_all('div', class_="content nonfileattachment")[0].text.strip()
            temp_data_ju['solution'] = new_data_ju.find_all('div', class_="content nonfileattachment")[2].text.strip()
            temp_data_ju['severity'] = new_data_ju.find('div', class_="content contentlist").text
            self.data.append(temp_data_ju) # appending temp data info to class variable called self.data

        for row in table_ju1.find_all('tr', class_='even', recursive=True):   # Iterating through advisory column 
            temp_data_ju = deepcopy(self.value)
            temp_data_ju['val_name'] = row.find_all('td')[1].text.strip()
            temp_data_ju['description'] = row.find_all('td')[2].text.strip()
            date = row.find_all('td')[4].text.strip()
            temp_data_ju['date'] = self.convert_juniper_date(date)
            page_link_ju = "https://kb.juniper.net/InfoCenter/"+(row.find_all('td')[2].a['href']) 

            temp_data_ju['link'] = page_link_ju
            new_data_ju = self.get_html_data(page_link_ju)
            temp_data_ju['affected'] = new_data_ju.find_all('div', class_="content nonfileattachment")[0].text.strip()
            temp_data_ju['solution'] = new_data_ju.find_all('div', class_="content nonfileattachment")[2].text.strip()
            temp_data_ju['severity'] = new_data_ju.find('div', class_="content contentlist").text
            self.data.append(temp_data_ju) # appending temp data info to class variable called self.data

    def convert_cisco_date(self, date):
        date = date.split('T')[0]
        return datetime.strptime(date, '%Y-%m-%d').date()

    @suppressors
    def scrape_cisco(self, url):
         # Scraping the Ajax page (Identified the json call)
        ajax_data = get("https://tools.cisco.com/security/center/publicationService.x?criteria=exact&cves=&keyword=&last_published_date=&limit=30&offset=0&publicationTypeIDs=1,3&securityImpactRatings=&sort=-day_sir&title=").text
        json_data = json.loads(ajax_data) #convert to json (Type: List of dicts)
        for dictionary in json_data[:9]:
            temp_data_ci = deepcopy(self.value)
            temp_data_ci['val_name'] = dictionary['title']
            temp_data_ci['severity'] = dictionary['severity']
            temp_data_ci['date'] = self.convert_cisco_date(dictionary['firstPublished'])     # skip all updates and include only new advisories
            page_link_ci = dictionary['url']
            temp_data_ci['link'] = page_link_ci
            # Scraping the CSS part
            css_data = get(page_link_ci)
            css_tree = lxml.html.fromstring(css_data.text)  # build the DOM Tree
            sel = CSSSelector('meta')   # construct a CSS Selector
            results = sel(css_tree)     # Apply the selector to the DOM tree.
            match = results[38]     # copy the list for the 38th result.
            temp_data_ci['description'] = match.get('content')  # get the content attribute for the 38th result.
            
            new_data_ci = self.get_html_data(page_link_ci)
            temp_data_ci['affected'] = new_data_ci.find('div', class_="ud-innercontent-area", id="vulnerableproducts").text.strip()
            temp_data_ci['solution'] = new_data_ci.find('div', class_="ud-innercontent-area", id="workaroundsfield").text.strip()
#            temp_data_ci['solution'] = new_data_ci.find('div', class_="ud-innercontent-area", id="fixedsoftfield",).text.strip() #alternate
            self.data.append(temp_data_ci) # appending temp data info to class variable called self.data

def download_template(url, output):
    resp = get(url, stream=True)
    with open(output, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=1024): 
            if chunk: 
                f.write(chunk)

def is_in_between(count, date):
    today = datetime.today().date()
    last_date = today - timedelta(days=count)
    if last_date <= date <= today:
        return True
    else:
        return False

def write_data(file_name, data, period):
    ''' Method used for writing data into .xls file '''
    wb = openpyxl.load_workbook(filename=file_name)
    sheet = wb['Vulnerabilities']

    number = 1
    for row_data in data:
        if is_in_between(period, row_data['date']):
            values = []
            values.append(number)
            values.append(row_data['val_name'])
            values.append(row_data['severity'])
            values.append(row_data['date'])
            values.append(row_data['description'])
            values.append(row_data['affected'])
            values.append(row_data['solution'])
            values.append(row_data['link'])

            for index, value in enumerate(values, start=1):
                sheet.cell(row=number+10, column=index+1).value = value
            number+=1
    wb.save(filename=file_name)


def main(template):
    if not os.path.exists(template):
        raise IOError('Template file not found , Please check repo')

    args = parse_args()
    if args.weekly:
        period = 7
    elif args.monthly:
        period = 30

    obj = DataScraper()
    obj.scrape_kb_crt('https://www.kb.cert.org/vuls/')
    obj.scrape_vmware('http://www.vmware.com/security/advisories')
    obj.scrape_microsoft('https://technet.microsoft.com/en-us/security/advisories')
    obj.scrape_fortinet('http://www.fortiguard.com/psirt')
    obj.scrape_brocade('http://www.brocade.com/en/support/security-advisories.html')
    obj.scrape_juniper('https://kb.juniper.net/InfoCenter/index?page=content&channel=SECURITY_ADVISORIES')
    obj.scrape_cisco('http://tools.cisco.com/security/center/publicationListing.x')   

    today = datetime.today().date()
    dest_file = 'Security_Advisories_{}.xlsx'.format(today)
    copyfile(template, dest_file)
    write_data(dest_file, obj.data, period)

if __name__ == '__main__':
    path = os.path.realpath(__file__)
    dir_name = os.path.dirname(path)
    template_file = os.path.join(dir_name, 'Template.xlsx')
    main(template_file)
