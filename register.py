#!/usr/local/bin/python3.9
import sys
sys.path.append('./lib')
from namecheap import Api
import confuse

config = confuse.Configuration('subdomain-auto-registrar', __name__)

fqdn = sys.argv[1]
registrar = sys.argv[2]
external_ip = sys.argv[3]

required_conf = {
  "namecheap": "username api_key username whitelisted_ip"
}

config.set_file(f"conf/{registrar.lower()}.yml")

if registrar.lower() == 'namecheap':
  api = Api(config['username'].get(str), config['api_key'].get(str), config['username'].get(str), config['whitelisted_ip'].get(str))
  api.check_sld(fqdn, external_ip)
