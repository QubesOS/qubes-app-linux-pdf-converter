import asyncio

async def foobar():
    try:
        await asyncio.sleep(5)
    except asyncio.CancelledError:
        print("foobar() got cancelled")

async def run():
    task = asyncio.create_task(foobar())
    await asyncio.sleep(1)
    task.cancel()
    await task
    print("done")

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())

main()
