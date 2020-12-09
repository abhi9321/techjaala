import requests


class Requests:
    """
    Custom Requests module:
    example:
    base_url = 'https://api.yotpo.com'

    extended_url = '/v1/apps/7iRas2It4piijhOgK1yNtPNRfj7UB4jkXIr7ZtHd/reviews'
    payload = {'utoken': 'UAsutsYEzX1arTETYZ43ggXpxws5dkaW7Y6UNc9A',
               'page': 1,
               'count': 1000}

    r_obj = Requests(base_url)
    r_obj.get_requests(extended_url, payload)

    payload = {
        "client_id": "7iRas2It4piijhOgK1yNtPNRfj7UB4jkXIr7ZtHd",
        "client_secret": "4mw9w8qjwdOQLSeIQ5fg2ZONKv6OCVX5uHQhhhYM",
        "grant_type": "client_credentials"
    }
    extended_url = 'oauth/token'
    r = r_obj.post_requests(extended_url, payload)
    print(r)
    """
    def __init__(self, base_url, headers={}):
        self.base_url = base_url
        self.headers = headers

    def extension(self, extended_url, kwargs):
        payload = ''
        endpoint = '/'.join([self.base_url, extended_url])
        if kwargs:
            # add payload
            payload = kwargs.get('payload')

        return endpoint, payload

    def get_requests(self, extended_url, **kwargs):
        """
        extended url : any extra url which can be concatenated with base_url
        payload : dictionary params
        return: json response , status_code
        """

        endpoint, payload = self.extension(extended_url, kwargs)

        response = requests.get(endpoint, headers=self.headers, params=payload)
        # print(f'url: {response.url} ')
        response.raise_for_status()

        return response.json(), response.status_code

    def post_requests(self, extended_url, **kwargs):
        """
        :param extended_url: pass extended url which will be added to base url
        :param kwargs:
        :return: reponse
        """
        endpoint, payload = self.extension(extended_url, kwargs)
        response = requests.post(endpoint, json=payload)
        print(f'base url: {self.base_url} ')
        response.raise_for_status()

        return response.json(), response.status_code


if __name__ == "__main__":
    pass
