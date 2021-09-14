#!/usr/local/bin/python3.9
import docker
import os

client = docker.from_env()
events = client.events(decode=True)

for event in events:
  if event['Action'] == 'start':
    container = client.containers.get(event['id'])
    container_envs = container.attrs['Config']['Env']
    fqdn_list = registrar = external_ip = None
    for env in container_envs:
      if env.find('VIRTUAL_HOST') > -1:
        fqdn_list = env.split("=", 1)[-1]
        fqdn_list = fqdn_list.split(',')
      if env.find('REGISTRAR') > -1:
        registrar = env.split("=", 1)[-1]
      if env.find('EXTERNAL_IP') > -1:
        external_ip = env.split("=", 1)[-1]
    if fqdn_list and registrar and external_ip:
      for fqdn in fqdn_list:
        os.system(f"cd /usr/src/app && python register.py {fqdn} {registrar} {external_ip}")
