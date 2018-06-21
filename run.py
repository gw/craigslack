import datetime
import os
import random
import shelve
import time

from craigslist import CraigslistHousing
from slackclient import SlackClient


def filter_bedrooms(listing: dict):
    MIN_BR = 3
    bedrooms = listing['bedrooms']
    if bedrooms is None or int(bedrooms) >= MIN_BR:
        return True
    return False

NEIGHBORHOODS = [
    'berkeley',
    'oakland',
]
def filter_where(listing: dict, hoods=None):
    where = listing['where']
    hoods = NEIGHBORHOODS if hoods is None else hoods

    if where is None:
        return True

    if any(hood in where.lower() for hood in hoods):
        return True

    return False

BLACKLISTED_WORDS = [
    'studio',
]
BR_STRINGS = [
    '{} bed',
    '{}bed',
    '{} br',
    '{}br',
]

for s in BR_STRINGS:
    BLACKLISTED_WORDS = BLACKLISTED_WORDS + [s.format(num) for num in [1, 2]]

def filter_name(listing: dict, blacklist=None):
    name = listing['name']
    blacklist = BLACKLISTED_WORDS if blacklist is None else blacklist

    if name is None:
        # This should really never happen
        return True

    if any(badword in name.lower() for badword in blacklist):
        return False

    return True

def map_price_per_occupant(listing: dict):
    price = listing['price']
    bedrooms = listing['bedrooms']

    if bedrooms is None or price is None:
        listing['price_per_occupant'] = 'n/a'
    else:
        price = price.replace('$', '')
        listing['price_per_occupant'] = int(price) // int(bedrooms)

    return listing

DB = 'listing.db'

def seen(id: str) -> bool:
    with shelve.open(DB) as db:
        return True if id in db else False

def update_seen(id: str):
    with shelve.open(DB) as db:
        db[id] = True

SLACK_TOKEN = os.environ['SLACK_TOKEN']
LISTING_CHANNEL = "#bot-incoming"
LOG_CHANNEL = "#bot-logs"

def post_to_slack(params: dict):
    if seen(params['id']):
        return False
    if params['repost_of'] is not None and seen(params['repost_of']):
        return False

    sc = SlackClient(SLACK_TOKEN)
    desc = ">>>>>>>>>\n{}|${}|{}\n{}\n<{}>\n".format(
        params["bedrooms"] or 'n/a',
        params["price_per_occupant"],
        params["where"],
        params["name"],
        params["url"],
    )
    sc.api_call(
        "chat.postMessage", channel=LISTING_CHANNEL, text=desc,
        username='craig', icon_emoji=':robot_face:'
    )

    update_seen(params['id'])

    return True


if __name__ == '__main__':
    time.sleep(random.randint(0, 120))

    print('Starting job: {}'.format(datetime.datetime.now()))

    cl = CraigslistHousing(
        site='sfbay',
        area='eby',
        category='apa',
        filters={'max_price': 0, 'min_price': 0}
    )

    results = cl.get_results(sort_by='newest', geotagged=True, limit=50)
    results = list(results)
    print('Found {} initial results'.format(len(results)))

    filtered = filter(filter_bedrooms, results)
    filtered = filter(filter_where, filtered)
    filtered = filter(filter_name, filtered)
    filtered = list(filtered)
    print('Filtered down to {} results'.format(len(filtered)))

    mapped = map(map_price_per_occupant, filtered)

    skipped = 0
    for listing in mapped:
        if not post_to_slack(listing):
            skipped += 1

    posted = len(filtered) - skipped
    print('Posted {} new results'.format(posted))

    sc = SlackClient(SLACK_TOKEN)
    desc = "Found {}, filtered to {}, posted {}".format(
        len(results),
        len(filtered),
        posted,
    )
    sc.api_call(
        "chat.postMessage", channel=LOG_CHANNEL, text=desc,
        username='craig-logs', icon_emoji=':robot_face:'
    )

