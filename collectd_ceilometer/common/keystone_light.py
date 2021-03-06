# -*- coding: utf-8 -*-

# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
""" Lightweight (keystone) client for the OpenStack Identity API """

import logging
import requests

LOG = logging.getLogger(__name__)


class KeystoneException(Exception):
    def __init__(self, message, exc=None, response=None):
        if exc:
            message += "\nReason: %s" % exc
        super(KeystoneException, self).__init__(message)

        self.response = response
        self.exception = exc


class InvalidResponse(KeystoneException):
    def __init__(self, exc, response):
        super(InvalidResponse, self).__init__(
            "Invalid response from ident", exc, response)


class MissingServices(KeystoneException):
    def __init__(self, message, exc, response):
        super(MissingServices, self).__init__(
            "MissingServices: " + message, exc, response)


class ClientV3(object):
    """Light weight client for the OpenStack Identity API V3.

    :param string username: Username for authentication.
    :param string password: Password for authentication.
    :param string tenant_name: Tenant name.
    :param string auth_url: Keystone service endpoint for authorization.

    """

    def __init__(self, auth_url, username, password, tenant_name):
        """Initialize a new client"""

        self.auth_url = auth_url
        self.username = username
        self.password = password
        self.tenant_name = tenant_name
        self._auth_token = None
        self._services = ()
        self._services_by_name = {}

    @property
    def auth_token(self):
        """Return token string usable for X-Auth-Token """
        # actualize token
        self.refresh()
        return self._auth_token

    @property
    def services(self):
        """Return list of services retrieved from identity server """
        return self._services

    def refresh(self):
        """Refresh token and services list (getting it from identity server) """
        headers = {'Accept': 'application/json'}
        url = self.auth_url.rstrip('/') + '/auth/tokens'
        params = {
            'auth': {
                'identity': {
                    'methods': ['password'],
                    'password': {
                        'user': {
                            'name': self.username,
                            'domain': {'id': 'default'},
                            'password': self.password
                        }
                    }
                },
                'scope': {
                    'project': {
                        'name': self.tenant_name,
                        'domain': {'id': 'default'}
                    }
                }
            }
        }

        resp = requests.post(url, json=params, headers=headers)
        resp_data = None
        # processing response
        try:
            resp.raise_for_status()
            resp_data = resp.json()['token']
            self._services = tuple(resp_data['catalog'])
            self._services_by_name = {
                service['name']: service for service in self._services
            }
            self._auth_token = resp.headers['X-Subject-Token']
        except (TypeError, KeyError, ValueError,
                requests.exceptions.HTTPError) as e:
            LOG.exception("Error processing response from keystone")
            raise InvalidResponse(e, resp_data)
        return resp_data

    def get_service_endpoint(self, name, urlkey="internalURL", region=None):
        """Return url endpoint of service

        possible values of urlkey = 'adminURL' | 'publicURL' | 'internalURL'
        provide region if more endpoints are available
        """

        try:
            endpoints = self._services_by_name[name]['endpoints']
            if not endpoints:
                raise MissingServices("Missing name '%s' in received services"
                                      % name,
                                      None, self._services)

            if region:
                for ep in endpoints:
                    if ep['region'] == region and ep['interface'] in urlkey:
                        return ep["url"].rstrip('/')
            else:
                for ep in endpoints:
                    if ep['interface'] in urlkey:
                        return ep["url"].rstrip('/')
            raise MissingServices("No valid endpoints found")
        except (KeyError, ValueError) as e:
            LOG.exception("Error while processing endpoints")
            raise MissingServices("Missing data in received services",
                                  e, self._services)


"""
Example of response (part only)
{
  "token": {
    "issued_at": "2015-09-04T08:59:09.991646",
    "expires": "2015-09-04T09:59:09Z",
    "id": "c5bbb1c9a27e470fb482de2a718e08c2",
    "tenant": {
      "enabled": true,
      "description": null,
      "name": "service",
      "id": "fdeec62f6c794c8dbfda448a83de9ce2"
    },
    "audit_ids": [
      "Pig7hVfGQjSuUnt1Hc5mCg"
    ]
  },
  "serviceCatalog": [
    {
      "endpoints_links": [],
      "endpoints": [
        {
          "adminURL": "http://10.237.214.74:8777/",
          "region": "RegionOne",
          "publicURL": "http://10.237.214.74:8777/",
          "internalURL": "http://10.237.214.74:8777/",
          "id": "ac95b1a24a854ec7a4b63b08ed4cbd83"
        }
      ],
      "type": "metering",
      "name": "ceilometer"
    },
  ],
}
"""
