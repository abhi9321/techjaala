import asyncio
import aiohttp
import time

URL = 'http://python.org'


async def fetch_status(session, url):
    async with session.get(url) as response:
        # prints status code
        print(response.status)


async def main():
    #  create requests session
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_status(session, URL) for _ in range(20)]
        # run tasks Concurrently
        await asyncio.gather(*tasks)


if __name__ == '__main__':
    t1 = time.perf_counter()
    asyncio.run(main())
    t2 = time.perf_counter()
    print(f'execution time : {t2 - t1} sec ')
