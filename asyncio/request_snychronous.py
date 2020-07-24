import time
import requests

URL = 'http://python.org'


def fetch_status(session, url):
    with session.get(url) as response:
        # prints status code
        print(response.status_code)


def main():
    # create requests session
    with requests.Session() as session:
        # call fetch_status 20 times
        [fetch_status(session, URL) for _ in range(20)]


if __name__ == '__main__':
    t1 = time.perf_counter()
    main()
    t2 = time.perf_counter()
    print(t2 - t1)
