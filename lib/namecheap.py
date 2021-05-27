import sys
import time
import requests
import re
from xml.etree.ElementTree import fromstring, Element

inPy3k = sys.version_info[0] == 3
escape_illegal_xml_characters = lambda x: re.sub(u'[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF\uFFFE\uFFFF]', '', x)

NAMESPACE = "http://api.namecheap.com/xml.response"

# default values for the retry mechanism
DEFAULT_ATTEMPTS_COUNT = 1  # no retries
DEFAULT_ATTEMPTS_DELAY = 0.1  # in seconds

# https://www.namecheap.com/support/api/error-codes.aspx
class ApiError(Exception):
    def __init__(self, number, text):
        Exception.__init__(self, '%s - %s' % (number, text))
        self.number = number
        self.text = text

class Api(object):
    # Follows API spec capitalization in variable names for consistency.
    def __init__(self, ApiUser, ApiKey, UserName, ClientIP,
                 debug=False,
                 attempts_count=DEFAULT_ATTEMPTS_COUNT,
                 attempts_delay=DEFAULT_ATTEMPTS_DELAY):
        self.ApiUser = ApiUser
        self.ApiKey = ApiKey
        self.UserName = UserName
        self.ClientIP = ClientIP
        self.endpoint = 'https://api.namecheap.com/xml.response'
        self.debug = debug
        self.payload_limit = 10  # After hitting this length limit script will move payload from POST params to POST data
        self.attempts_count = attempts_count
        self.attempts_delay = attempts_delay

    @staticmethod
    def get_element(element, element_name):
        # type: (Element, str) -> Element
        return element.find('.//{%(ns)s}%(el)s' % {'ns': NAMESPACE, 'el': element_name})

    @staticmethod
    def get_element_dict(element, element_name):
        # type: (Element, str) -> dict
        return dict(Api.get_element(element, element_name).items())
    def _payload(self, Command, extra_payload={}):
        """Make dictionary for passing to requests.post"""
        payload = {
            'ApiUser': self.ApiUser,
            'ApiKey': self.ApiKey,
            'UserName': self.UserName,
            'ClientIP': self.ClientIP,
            'Command': Command,
        }
        # Namecheap recommends to use HTTPPOST method when setting more than 10 hostnames
        # https://www.namecheap.com/support/api/methods/domains-dns/set-hosts.aspx
        if len(extra_payload) < self.payload_limit:
            payload.update(extra_payload)
            extra_payload = {}
        return payload, extra_payload

    def _fetch_xml(self, payload, extra_payload=None):
        """Make network call and return parsed XML element"""
        attempts_left = self.attempts_count
        while attempts_left > 0:
            if extra_payload:
                r = requests.post(self.endpoint, params=payload, data=extra_payload)
            else:
                r = requests.post(self.endpoint, params=payload)
            if 200 <= r.status_code <= 299:
                break
            if attempts_left <= 1:
                raise ApiError('1', 'Did not receive 200 (Ok) response')
            if self.debug:
                print('Received status %d ... retrying ...' % (r.status_code))
            time.sleep(self.attempts_delay)
            attempts_left -= 1

        if self.debug:
            print("--- Request ---")
            print(r.url)
            print(extra_payload)
            print("--- Response ---")
            print(r.text)
            print("--- END DEBUG ---")

        xml = fromstring(escape_illegal_xml_characters(r.text))

        if xml.attrib['Status'].upper() == 'ERROR':
            xpath = './/{%(ns)s}Errors/{%(ns)s}Error' % {'ns': NAMESPACE}
            error = xml.find(xpath)
            raise ApiError(error.attrib['Number'], error.text)
        return xml

    def _call(self, Command, extra_payload=None):
        """Call an API command"""
        extra_payload = {} if extra_payload is None else extra_payload
        payload, extra_payload = self._payload(Command, extra_payload)
        xml = self._fetch_xml(payload, extra_payload)
        return xml

    class LazyGetListIterator(object):
        """When listing domain names, only one page is returned
        initially. The list needs to be paged through to see all."""
        def _get_more_results(self):
            xml = self.api._fetch_xml(self.payload)
            xpath = './/{%(ns)s}CommandResponse/{%(ns)s}DomainGetListResult/{%(ns)s}Domain' % {'ns': NAMESPACE}
            domains = xml.findall(xpath)
            for domain in domains:
                self.results.append(domain.attrib)
            self.payload['Page'] += 1

        def __init__(self, api, payload):
            self.api = api
            self.payload = payload
            self.results = []
            self.i = -1

        def __iter__(self):
            return self

        def __next__(self):
            self.i += 1
            if self.i >= len(self.results):
                self._get_more_results()

            if self.i >= len(self.results):
                raise StopIteration
            else:
                return self.results[self.i]
        next = __next__

    @classmethod
    def _list_of_dictionaries_to_numbered_payload(cls, l):
        """
        [
            {'foo' : 'bar', 'cat' : 'purr'},
            {'foo' : 'buz'},
            {'cat' : 'meow'}
        ]

        becomes

        {
            'foo1' : 'bar',
            'cat1' : 'purr',
            'foo2' : 'buz',
            'cat3' : 'meow'
        }
        """
        disallow_change = ['EmailType']

        return dict(sum([
            [(k + str(i + 1), v) if k not in disallow_change else (k, v) for k, v in d.items()] for i, d in enumerate(l)
        ], []))

    @classmethod
    def _elements_names_fix(self, host_record):
        """This method converts received message to correct send format.
        API answers you with this format:

        {
            'Name' : '@',
            'Type' : 'URL',
            'Address' : 'http://news.ycombinator.com',
            'MXPref' : '10',
            'TTL' : '100'
        }

        And you should convert it to this one in order to sync the records:

        {
            'HostName' : '@',
            'RecordType' : 'URL',
            'Address' : 'http://news.ycombinator.com',
            'MXPref' : '10',
            'TTL' : '100'
        }
        """

        conversion_map = [
            ("Name", "HostName"),
            ("Type", "RecordType")
        ]

        for field in conversion_map:
            # if source field exists
            if field[0] in host_record:
                # convert it to target field and delete old one
                host_record[field[1]] = host_record[field[0]]
                del(host_record[field[0]])

        return host_record

    # https://www.namecheap.com/support/api/methods/domains-dns/set-hosts.aspx
    def domains_dns_setHosts(self, domain, host_records):
        """Sets the DNS host records for a domain.

        api.domains_dns_setHosts('example.com', [
            {
                'HostName' : '@',
                'RecordType' : 'URL',
                'Address' : 'http://news.ycombinator.com',
                'MXPref' : '10',
                'TTL' : '100'
            }
        ])"""

        extra_payload = self._list_of_dictionaries_to_numbered_payload(host_records)
        sld, tld = domain.split(".", 1)
        extra_payload.update({
            'SLD': sld,
            'TLD': tld
        })
        return self.get_element_dict(self._call("namecheap.domains.dns.setHosts", extra_payload), 'DomainDNSSetHostsResult')

    # https://www.namecheap.com/support/api/methods/domains-dns/get-hosts.aspx
    def domains_dns_getHosts(self, domain):
        """Retrieves DNS host record settings. Note that the key names are different from those
        you use when setting the host records."""
        sld, tld = domain.split(".", 1)
        extra_payload = {
            'SLD': sld,
            'TLD': tld
        }
        xml = self._call("namecheap.domains.dns.getHosts", extra_payload)
        xpath = './/{%(ns)s}CommandResponse/{%(ns)s}DomainDNSGetHostsResult/*' % {'ns': NAMESPACE}
        results = []
        for host in xml.findall(xpath):
            results.append(host.attrib)
        return results

    def check_sld(self, fqdn, target_ip):
        sld, tld = fqdn.split(".", 1)
        hosts = self.domains_dns_getHosts(tld)
        for host in hosts:
            if host['Type'] == 'A':
                if host['Name'] == sld:
                    if host['Address'] == target_ip:
                        print(f"{fqdn} is already registered to {host['Address']}")
                        return
                    else:
                        print(f"{fqdn} is already registered to {host['Address']} instead of {target_ip}, deleting...")
                        self.domains_dns_delHost(tld, {
                            "RecordType": "A",
                            "HostName": sld,
                            "Address": {host['Address']}
                        })
        self.domains_dns_addHost(tld, {
            "RecordType": "A",
            "HostName": sld,
            "Address": target_ip,
            "MXPref": 10, #Default value
            "TTL": 1799 #Value for Automatic TTL
        })
        print(f"{fqdn} is now registered to {target_ip}")
        return 

    def domains_dns_addHost(self, domain, host_record):
        """This method is absent in original API. The main idea is to let user add one record
        while having zero knowledge about the others. Method gonna get full records list, add
        single record and push it to the API.

        api.domains_dns_addHost('example.com', {
            "RecordType": "A",
            "HostName": "test",
            "Address": "127.0.0.1",
            "MXPref": 10,
            "TTL": 1800
        })
        """
        host_records_remote = self.domains_dns_getHosts(domain)

        host_records_remote.append(host_record)
        host_records_remote = [self._elements_names_fix(x) for x in host_records_remote]

        extra_payload = self._list_of_dictionaries_to_numbered_payload(host_records_remote)
        sld, tld = domain.split(".", 1)
        extra_payload.update({
            'SLD': sld,
            'TLD': tld
        })
        return self.get_element_dict(self._call("namecheap.domains.dns.setHosts", extra_payload), 'DomainDNSSetHostsResult')

    def domains_dns_delHost(self, domain, host_record):
        """This method is absent in original API as well. It executes non-atomic
        remove operation over the host record which has the following Type,
        Hostname and Address.

        api.domains_dns_delHost('example.com', {
            "RecordType": "A",
            "HostName": "test",
            "Address": "127.0.0.1"
        })
        """
        host_records_remote = self.domains_dns_getHosts(domain)

        host_records_new = []
        for r in host_records_remote:
            cond_type = r["Type"] == host_record["RecordType"]
            cond_name = r["Name"] == host_record["HostName"]

            if cond_type and cond_name:
                pass
            else:
                host_records_new.append(r)

        host_records_new = [self._elements_names_fix(x) for x in host_records_new]

        # Check that we delete not more than 1 record at a time
        if len(host_records_remote) != len(host_records_new) + 1:
            sys.stderr.write(
                "Something went wrong while removing host record, delta > 1: %i -> %i, aborting API call.\n" % (
                    len(host_records_remote),
                    len(host_records_new)
                )
            )
            return False

        extra_payload = self._list_of_dictionaries_to_numbered_payload(host_records_new)
        sld, tld = domain.split(".", 1)
        extra_payload.update({
            'SLD': sld,
            'TLD': tld
        })
        return self.get_element_dict(self._call("namecheap.domains.dns.setHosts", extra_payload), 'DomainDNSSetHostsResult')
