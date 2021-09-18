## How to use
### Set your registrar auth conf
Example with namecheap:
- Set your conf/namecheap.yml
```
username: "my_username"
api_key: "my_api_key"
whitelisted_ip: "my_whitelisted_ip"
```
### Set your docker-compose environment
- Add environment variables to your docker-compose file
```
version: '3.1'

services:

  persifleur:
    image: persifleur:latest
    restart: always
    ports:
      - 1337:1337
    environment:
      VIRTUAL_HOST: www.magnier.io,magnier.io
      VIRTUAL_PORT: 1337
      LETSENCRYPT_HOST: www.magnier.io,magnier.io
      LETSENCRYPT_EMAIL: adam@magnier.io
      REGISTRAR: namecheap
      EXTERNAL_IP: 152.228.170.93

networks:
   default:
     external:
       name: nginx-proxy
```
### Start the listener
docker-compose
### Enjoy
screens/demo
### Credits
Inspired by docker-gen

Namecheap API script based on https://github.com/Bemmu/PyNamecheap