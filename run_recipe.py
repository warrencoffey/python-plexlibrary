#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Automated Plex library script

Usage:
    # FIXME

Requirements:
    requests
    plexapi
    trakt

Disclaimer:
    Use at your own risk! I am not responsible for damages to your Plex server or libraries.

Author:
    /u/haeri

Credit:
    Originally based on https://gist.github.com/JonnyWong16/f5b9af386ea58e19bf18c09f2681df23
    by /u/SwiftPanda16
"""

import sys
import os
import importlib
import json
import subprocess
import time
import datetime
import shelve

import requests
from plexapi.server import PlexServer
import trakt

import config

TMDB_REQUEST_COUNT = 0  # DO NOT CHANGE
TVDB_REQUEST_COUNT = 0  # DO NOT CHANGE
TVDB_TOKEN = None


class Colors(object):
    RED  = "\033[1;31m"
    BLUE = "\033[1;34m"
    CYAN = "\033[1;36m"
    GREEN = "\033[0;32m"
    RESET = "\033[0;0m"
    BOLD = "\033[;1m"
    REVERSE = "\033[;7m"


def create_new_library(name, folder, library_type='movie'):
    headers = {"X-Plex-Token": config.PLEX_TOKEN}
    params = {
        'name': name,
        'language': 'en',
        'location': folder,
    }
    if library_type == 'movie':
        params['type'] = 'movie'
        params['agent'] = 'com.plexapp.agents.imdb'
        params['scanner'] = 'Plex Movie Scanner'
    elif library_type == 'tv':
        params['type'] = 'tv'
        params['agent'] = 'com.plexapp.agents.tvdb'  # FIXME?
        params['scanner'] = 'TheTVDB'
    else:
        raise Exception("Library type should be 'movie' or 'tv'")

    url = '{base_url}/library/sections'.format(base_url=config.PLEX_URL)
    r = requests.post(url, headers=headers, params=params)


def add_sort_title(library_key, rating_key, number, title, library_type):
    headers = {'X-Plex-Token': config.PLEX_TOKEN}
    if library_type == 'movie':
        search_type = 1
    elif library_type == 'tv':
        search_type = 2
    params = {
        'type': search_type,
        'id': rating_key,
        'titleSort.value': recipe.SORT_TITLE_FORMAT.format(
            number=str(number).zfill(6), title=title),
        'titleSort.locked': 1,
    }

    if recipe.SORT_TITLE_VISIBLE:
        params['title.value'] = recipe.SORT_TITLE_FORMAT.format(
            number=str(number), title=title)
        params['title.locked'] = 1
    else:
        params['title.value'] = title=title
        params['title.locked'] = 0

    url = "{base_url}/library/sections/{library}/all".format(
            base_url=config.PLEX_URL, library=library_key)
    r = requests.put(url, headers=headers, params=params)


def get_imdb_id_from_tmdb(tmdb_id, library_type='movie'):
    global TMDB_REQUEST_COUNT

    if not config.TMDB_API_KEY:
        return None

    if library_type not in ('movie', 'tv'):
        raise Exception("Library type should be 'movie' or 'tv'")

    # Wait 10 seconds for the TMDb rate limit
    if TMDB_REQUEST_COUNT >= 40:
        print(u"Waiting 10 seconds for the TMDb rate limit...")
        time.sleep(10)
        TMDB_REQUEST_COUNT = 0

    params = {"api_key": config.TMDB_API_KEY}

    if library_type == 'movie':
        url = "https://api.themoviedb.org/3/movie/{tmdb_id}".format(
            tmdb_id=tmdb_id)
    else:
        url = "https://api.themoviedb.org/3/tv/{tmdb_id}/external_ids".format(
            tmdb_id=tmdb_id)
    r = requests.get(url, params=params)

    TMDB_REQUEST_COUNT += 1

    if r.status_code == 200:
        item = json.loads(r.text)
        return item.get('imdb_id')
    else:
        return None


def get_tmdb_details(tmdb_id, library_type='movie'):
    global TMDB_REQUEST_COUNT

    if library_type not in ('movie', 'tv'):
        raise Exception("Library type should be 'movie' or 'tv'")

    # Use cache
    cache = shelve.open(config.TMDB_CACHE_FILE)
    if cache.has_key(str(tmdb_id)) and \
            (cache[str(tmdb_id)]['cached'] + 3600 * 24) > int(time.time()):
        item = cache[str(tmdb_id)]
        cache.close()
        return item

    if not config.TMDB_API_KEY:
        cache.close()
        return None

    # Wait 10 seconds for the TMDb rate limit
    if TMDB_REQUEST_COUNT >= 40:
        print(u"Waiting 10 seconds for the TMDb rate limit...")
        time.sleep(10)
        TMDB_REQUEST_COUNT = 0

    params = {
        'api_key': config.TMDB_API_KEY,
    }

    if library_type == 'movie':
        params['append_to_response'] = 'release_dates'
        url = "https://api.themoviedb.org/3/movie/{tmdb_id}".format(
                tmdb_id=tmdb_id)
    else:
        url = "https://api.themoviedb.org/3/tv/{tmdb_id}".format(
                tmdb_id=tmdb_id)
    r = requests.get(url, params=params)

    TMDB_REQUEST_COUNT += 1

    if r.status_code == 200:
        item = json.loads(r.text)
        item['cached'] = int(time.time())
        cache[str(tmdb_id)] = item
        cache.close()
        return item
    else:
        cache.close()
        return None


def get_imdb_id_from_tvdb(tvdb_id):
    global TVDB_REQUEST_COUNT
    global TVDB_TOKEN

    if not config.TVDB_API_KEY:
        return None

    if not TVDB_TOKEN:
        data = {
            "apikey": config.TVDB_API_KEY,
            "userkey": config.TVDB_USER_KEY,
            "username": config.TVDB_USERNAME,
        }

        url = "https://api.thetvdb.com/login"
        r = requests.post(url, json=data)

        TVDB_REQUEST_COUNT += 1

        if r.status_code == 200:
            result = r.json()
            TVDB_TOKEN = result['token']
        else:
            return None

    url = "https://api.thetvdb.com/series/{id}".format(id=tvdb_id)
    r = requests.get(url, headers={'Authorization': 'Bearer {token}'.format(token=TVDB_TOKEN)})

    TVDB_REQUEST_COUNT += 1

    if r.status_code == 200:
        tv_show = r.json()
        return tv_show['data']['imdbId']
    else:
        return None


def weighted_sorting(item_list, recipe, library_type):
    def _get_non_theatrical_release(release_dates):
        # Returns earliest release date that is not theatrical
        types = {}
        for country in release_dates.get('results', []):
            # FIXME Look at others too?
            if country['iso_3166_1'] != 'US':
                continue
            for d in country['release_dates']:
                if d['type'] in (4, 5, 6):
                    # 4: Digital, 5: Physical, 6: TV
                    types[str(d['type'])] = datetime.datetime.strptime(
                        d['release_date'], '%Y-%m-%dT%H:%M:%S.%fZ').date()
            break

        release_date = None
        for t, d in types.items():
            if not release_date or d < release_date:
                release_date = d

        return release_date

    def _get_age_weight(days):
        if library_type == 'movie':
            # Everything younger than this will get 1
            min_days = 100
            # Everything older than this will get 0
            max_days = float(recipe.MAX_AGE) / 4.0 * 365.25 or 200
        else:
            min_days = 14
            max_days = float(recipe.MAX_AGE) / 4.0 * 365.25 or 100
        if days <= min_days:
            return 1
        elif days >= max_days:
            return 0
        else:
            return 1 - (days - min_days) / (max_days - min_days)

    total_items = len(item_list)

    # TMDB details
    today = datetime.date.today()
    total_tmdb_vote = 0.0
    tmdb_votes = []
    for i, m in enumerate(item_list):
        details = get_tmdb_details(m['tmdb_id'], library_type)
        m['tmdb_popularity'] = float(details['popularity'])
        m['tmdb_vote'] = float(details['vote_average'])
        m['tmdb_vote_count'] = int(details['vote_count'])
        if library_type == 'movie':
            if recipe.BETTER_RELEASE_DATE:
                m['release_date'] = _get_non_theatrical_release(
                    details['release_dates']) or \
                    datetime.datetime.strptime(details['release_date'],
                    '%Y-%m-%d').date()
            else:
                m['release_date'] = datetime.datetime.strptime(
                    details['release_date'], '%Y-%m-%d').date()
            item_age_td = today - m['release_date']
        elif library_type == 'tv':
            m['last_air_date'] = datetime.datetime.strptime(
                details['last_air_date'], '%Y-%m-%d').date()
            item_age_td = today - m['last_air_date']
        m['original_idx'] = i + 1
        m['genres'] = [g['name'].lower() for g in details['genres']]
        m['age'] = item_age_td.days
        if library_type == 'tv' or m['tmdb_vote_count'] > 150 or m['age'] > 50:
            tmdb_votes.append(m['tmdb_vote'])
        total_tmdb_vote += m['tmdb_vote']
        item_list[i] = m
    average_tmdb_vote = total_tmdb_vote / float(total_items)

    tmdb_votes.sort()

    for i, m in enumerate(item_list):
        # Distribute all weights evenly from 0 to 1 (times global factor)
        # More weight means it'll go higher in the final list
        index_weight = float(total_items - i) / float(total_items)
        if library_type == 'tv' or m['tmdb_vote_count'] > 150 or m['age'] > 50:
            vote_weight = (tmdb_votes.index(m['tmdb_vote']) + 1) / float(len(tmdb_votes))
        else:
            # Assume below average rating for new/less voted items
            vote_weight = 0.25
        age_weight = _get_age_weight(float(m['age']))
        weight = (index_weight * recipe.WEIGHT_TRAKT_TREND
                  + vote_weight * recipe.WEIGHT_VOTE
                  + age_weight * recipe.WEIGHT_AGE)
        for genre, value in recipe.WEIGHT_GENRE_BIAS.items():
            if genre.lower() in m['genres']:
                weight *= value
        m['index_weight'] = index_weight
        m['vote_weight'] = vote_weight
        m['age_weight'] = age_weight
        m['weight'] = weight
        item_list[i] = m

    item_list.sort(key = lambda m: m['weight'], reverse=True)

    for i, m in enumerate(item_list):
        if (i+1) < m['original_idx']:
            net = Colors.GREEN + u'↑'
        elif (i+1) > m['original_idx']:
            net = Colors.RED + u'↓'
        else:
            net = u' '
        net += str(abs(i + 1 - m['original_idx'])).rjust(3)
        print(u"{} {:>3}: trnd:{:>3}, w_trnd:{:0<5}; vote:{}, w_vote:{:0<5}; "
            "age:{:>4}, w_age:{:0<5}; w_cmb:{:0<5}; {} {}{}".format(
                net, i+1, m['original_idx'], round(m['index_weight'], 3),
                m['tmdb_vote'], round(m['vote_weight'], 3), m['age'],
                round(m['age_weight'], 3), round(m['weight'], 3),
                m['title'].encode('utf8'), m['year'], Colors.RESET))

    return item_list


def run_trakt_watched_sort_only(recipe, library_type):
    try:
        plex = PlexServer(config.PLEX_URL, config.PLEX_TOKEN)
    except:
        print(u"No Plex server found at: {base_url}".format(base_url=config.PLEX_URL))
        print(u"Exiting script.")
        return 0

    if library_type not in ('movie', 'tv'):
        raise Exception("Library type should be 'movie' or 'tv'")

    trakt.init(config.TRAKT_USERNAME, client_id=config.TRAKT_CLIENT_ID,
               client_secret=config.TRAKT_CLIENT_SECRET)
    trakt_core = trakt.core.Core()
    item_list = []
    item_ids = []
    curyear = datetime.datetime.now().year

    def _movie_add_from_trakt_list(url):
        print(u"Retrieving the trakt list: {}".format(url))
        movie_data = trakt_core._handle_request('get', url)
        for m in movie_data:
            # Skip already added movies
            if m['movie']['ids']['imdb'] in item_ids:
                continue
            # Skip old movies
            if recipe.MAX_AGE != 0 \
                    and (curyear - (recipe.MAX_AGE - 1)) > int(m['movie']['year']):
                continue
            item_list.append({
                'id': m['movie']['ids']['imdb'],
                'tmdb_id': m['movie']['ids']['tmdb'],
                'title': m['movie']['title'].encode('utf8'),
                'year': m['movie']['year'],
            })
            item_ids.append(m['movie']['ids']['imdb'])
            print(u"{} {} {}".format(
                len(item_list), m['movie']['title'], m['movie']['year']))

    # Get the trakt lists
    if library_type == 'movie':
        for url in recipe.SOURCE_LIST_URLS:
            _movie_add_from_trakt_list(url)
    else:
        for url in recipe.SOURCE_LIST_URLS:
            _tv_add_from_trakt_list(url)

    new_library = plex.library.section(recipe.NEW_LIBRARY_NAME)
    new_library_key = new_library.key
    all_new_items = new_library.all()

    if not recipe.SORT_TITLE_ABSOLUTE and recipe.WEIGHTED_SORTING:
        if config.TMDB_API_KEY:
            item_list = weighted_sorting(item_list, recipe, library_type)
        else:
            print(u"TMDd API key is required for weighted sorting")

    # Create a dictionary of {imdb_id: item}
    imdb_map = {}
    for m in all_new_items:
        if m.guid != None and 'imdb://' in m.guid:
            imdb_id = m.guid.split('imdb://')[1].split('?')[0]
        elif m.guid != None and 'themoviedb://' in m.guid:
            tmdb_id = m.guid.split('themoviedb://')[1].split('?')[0]
            imdb_id = get_imdb_id_from_tmdb(tmdb_id)
        elif m.guid != None and 'thetvdb://' in m.guid:
            tvdb_id = m.guid.split('thetvdb://')[1].split('?')[0].split('/')[0]
            imdb_id = get_imdb_id_from_tvdb(tvdb_id)
        else:
            imdb_id = None

        if imdb_id and imdb_id in item_ids:
            imdb_map[imdb_id] = m
        else:
            imdb_map[m.ratingKey] = m

    # Modify the sort titles
    print(u"Setting the sort titles for the '{}' library...".format(
        recipe.NEW_LIBRARY_NAME))
    in_library_idx = []
    if recipe.SORT_TITLE_ABSOLUTE:
        for i, m in enumerate(item_list):
            item = imdb_map.pop(m['id'], None)
            if item:
                add_sort_title(new_library_key, item.ratingKey, i+1, m['title'], library_type)
                in_library_idx.append(i)
    else:
        i = 0
        for m in item_list:
            item = imdb_map.pop(m['id'], None)
            if item:
                i += 1
                add_sort_title(new_library_key, item.ratingKey, i, m['title'], library_type)
                in_library_idx.append(i)



def run_trakt_watched(recipe, library_type):
    try:
        plex = PlexServer(config.PLEX_URL, config.PLEX_TOKEN)
    except:
        print(u"No Plex server found at: {base_url}".format(base_url=config.PLEX_URL))
        print(u"Exiting script.")
        return 0

    if library_type not in ('movie', 'tv'):
        raise Exception("Library type should be 'movie' or 'tv'")

    trakt.init(config.TRAKT_USERNAME, client_id=config.TRAKT_CLIENT_ID,
               client_secret=config.TRAKT_CLIENT_SECRET)
    trakt_core = trakt.core.Core()
    item_list = []
    item_ids = []
    curyear = datetime.datetime.now().year

    def _movie_add_from_trakt_list(url):
        print(u"Retrieving the trakt list: {}".format(url))
        movie_data = trakt_core._handle_request('get', url)
        for m in movie_data:
            # Skip already added movies
            if m['movie']['ids']['imdb'] in item_ids:
                continue
            # Skip old movies
            if recipe.MAX_AGE != 0 \
                    and (curyear - (recipe.MAX_AGE - 1)) > int(m['movie']['year']):
                continue
            item_list.append({
                'id': m['movie']['ids']['imdb'],
                'tmdb_id': m['movie']['ids']['tmdb'],
                'title': m['movie']['title'],
                'year': m['movie']['year'],
            })
            item_ids.append(m['movie']['ids']['imdb'])

    def _tv_add_from_trakt_list(url):
        print(u"Retrieving the trakt list: {}".format(url))
        show_data = trakt_core._handle_request('get', url)
        for m in show_data:
            # Skip already added shows
            if m['show']['ids']['imdb'] in item_ids:
                continue
            # Skip old shows
            if recipe.MAX_AGE != 0 \
                    and (curyear - (recipe.MAX_AGE - 1)) > int(m['show']['year']):
                continue
            item_list.append({
                'id': m['show']['ids']['imdb'],
                'tmdb_id': m['show']['ids']['tmdb'],
                'tvdb_id': m['show']['ids']['tvdb'],
                'title': m['show']['title'],
                'year': m['show']['year'],
            })
            item_ids.append(m['show']['ids']['imdb'])

    # Get the trakt lists
    if library_type == 'movie':
        for url in recipe.SOURCE_LIST_URLS:
            _movie_add_from_trakt_list(url)
    else:
        for url in recipe.SOURCE_LIST_URLS:
            _tv_add_from_trakt_list(url)

    # Get list of items from the Plex server
    print(u"Trying to match with items from the '{library}' library ".format(
        library=recipe.SOURCE_LIBRARY_NAME))
    try:
        source_library = plex.library.section(recipe.SOURCE_LIBRARY_NAME)
        #all_items = source_library.all()
    except:
        print(u"The '{library}' library does not exist in Plex.".format(
            library=recipe.SOURCE_LIBRARY_NAME))
        print(u"Exiting script.")
        return 0

    # Create a list of matching items
    matching_items = []
    nonmatching_idx = []
    for i, m in enumerate(item_list):
        if len(matching_items) >= recipe.MAX_COUNT:
            nonmatching_idx.append(i)
            continue
        try:
            if library_type == 'movie':
                res = source_library.search(title=m['title'], year=m['year'])
                if not res:
                    res = source_library.search(title=m['title'], year=int(m['year'])+1)
                if not res:
                    res = source_library.search(title=m['title'], year=int(m['year'])-1)
            else:
                res = source_library.search(title=m['title'])
        except KeyError:
            print(u"Warning: Unable to look for '{} ({})', skipping.".format(
                m['title'], m['year']))
            res = None
        if res:
            for r in res:
                imdb_id = None
                tmdb_id = None
                tvdb_id = None
                if r.guid != None and 'imdb://' in r.guid:
                    imdb_id = r.guid.split('imdb://')[1].split('?')[0]
                elif r.guid != None and 'themoviedb://' in r.guid:
                    tmdb_id = r.guid.split('themoviedb://')[1].split('?')[0]
                elif r.guid != None and 'thetvdb://' in r.guid:
                    tvdb_id = r.guid.split('thetvdb://')[1].split('?')[0]

                if imdb_id and str(imdb_id) == str(m['id']):
                    matching_items.append(r)
                    print(u"{} {} {}".format(
                        len(matching_items), m['title'], m['year']))
                    break
                elif tmdb_id and str(tmdb_id) == str(m['tmdb_id']):
                    matching_items.append(r)
                    print(u"{} {} {}".format(
                        len(matching_items), m['title'], m['year']))
                    break
                elif tvdb_id and str(tvdb_id) == str(m['tvdb_id']):
                    matching_items.append(r)
                    print(u"{} {} {}".format(
                        len(matching_items), m['title'], m['year']))
                    break
            else:
                nonmatching_idx.append(i)
        if not res:
            nonmatching_idx.append(i)

    if not recipe.SORT_TITLE_ABSOLUTE:
        for i in reversed(nonmatching_idx):
            del item_list[i]
            del item_ids[i]

    # Create symlinks for all items in your library on the trakt watched
    print(u"Creating symlinks for {count} matching items in the "
          u"library...".format(count=len(matching_items)))

    try:
        if not os.path.exists(recipe.NEW_LIBRARY_FOLDER):
            os.mkdir(recipe.NEW_LIBRARY_FOLDER)
    except:
        print(u"Unable to create the new library folder "
              u"'{folder}'.".format(folder=recipe.NEW_LIBRARY_FOLDER))
        print(u"Exiting script.")
        return 0

    count = 0
    updated_paths = []
    if library_type == 'movie':
        for item in matching_items:
            for part in item.iterParts():
                old_path_file = part.file.encode('UTF-8')
                old_path, file_name = os.path.split(old_path_file)

                folder_name = ''
                for f in recipe.SOURCE_LIBRARY_FOLDERS:
                    f = os.path.abspath(f)
                    if old_path.lower().startswith(f.lower()):
                        folder_name = os.path.relpath(old_path, f)

                if folder_name == '.':
                    new_path = os.path.join(recipe.NEW_LIBRARY_FOLDER, file_name)
                    dir = False
                else:
                    new_path = os.path.join(recipe.NEW_LIBRARY_FOLDER, folder_name)
                    dir = True
                    parent_path = os.path.dirname(os.path.abspath(new_path))
                    if not os.path.exists(parent_path):
                        try:
                            os.makedirs(parent_path)
                        except OSError as e:
                            if e.errno == errno.EEXIST and \
                                    os.path.isdir(parent_path):
                                pass
                            else:
                                raise
                    # Clean up old, empty directories
                    if os.path.exists(new_path) and not os.listdir(new_path):
                        os.rmdir(new_path)

                if (dir and not os.path.exists(new_path)) or \
                        (not dir and not os.path.isfile(new_path)):
                    try:
                        if os.name == 'nt':
                            if dir:
                                subprocess.call(['mklink', '/D', new_path,
                                                 old_path], shell=True)
                            else:
                                subprocess.call(['mklink', new_path,
                                                 old_path_file], shell=True)
                        else:
                            if dir:
                                os.symlink(old_path, new_path)
                            else:
                                os.symlink(old_path_file, new_path)
                        count += 1
                        updated_paths.append(new_path)
                    except Exception as e:
                        print(u"Symlink failed for {path}: {e}".format(
                            path=new_path, e=e))
    else:
        for tv_show in matching_items:
            done = False
            if done:
                continue
            for episode in tv_show.episodes():
                if done:
                    break
                for part in episode.iterParts():
                    if done:
                        break
                    old_path_file = part.file.encode('UTF-8')
                    old_path, file_name = os.path.split(old_path_file)
                    old_path =  recipe.SOURCE_LIBRARY_FOLDERS[0] + '/' + old_path.replace(recipe.SOURCE_LIBRARY_FOLDERS[0], '').strip('/').split('/')[0]

                    folder_name = ''
                    for f in recipe.SOURCE_LIBRARY_FOLDERS:
                        if old_path.lower().startswith(f.lower()):
                            folder_name = os.path.relpath(old_path, f)

                    new_path = os.path.join(recipe.NEW_LIBRARY_FOLDER, folder_name)
                    dir = True

                    if (dir and not os.path.exists(new_path)) or (not dir and not os.path.isfile(new_path)):
                        try:
                            if os.name == 'nt':
                                if dir:
                                    subprocess.call(['mklink', '/D', new_path, old_path], shell=True)
                                else:
                                    subprocess.call(['mklink', new_path, old_path_file], shell=True)
                            else:
                                if dir:
                                    os.symlink(old_path, new_path)
                                else:
                                    os.symlink(old_path_file, new_path)
                            count += 1
                            updated_paths.append(new_path)
                            done = True
                        except Exception as e:
                            print(u"Symlink failed for {path}: {e}".format(path=new_path, e=e))

    print(u"Created symlinks for {count} items.".format(count=count))

    # Check if the new library exists in Plex
    print(u"Creating the '{}' library in Plex...".format(
        recipe.NEW_LIBRARY_NAME))
    try:
        new_library = plex.library.section(recipe.NEW_LIBRARY_NAME)
        new_library_key = new_library.key
        print(u"Library already exists in Plex. Refreshing the library...")

        new_library.update()
    except:
        create_new_library(recipe.NEW_LIBRARY_NAME, recipe.NEW_LIBRARY_FOLDER, library_type)
        new_library = plex.library.section(recipe.NEW_LIBRARY_NAME)
        new_library_key = new_library.key

    if not recipe.SORT_TITLE_ABSOLUTE and recipe.WEIGHTED_SORTING:
        # While we wait for refresh, query TMDb etc.
        if config.TMDB_API_KEY:
            print(u"Getting data from TMDb to add weighted sorting...")
            item_list = weighted_sorting(item_list, recipe, library_type)
        else:
            print(u"TMDd API key is required for weighted sorting")

    # Wait for metadata to finish downloading before continuing
    print(u"Waiting for metadata to finish downloading...")
    new_library = plex.library.section(recipe.NEW_LIBRARY_NAME)
    while new_library.refreshing:
        time.sleep(5)
        new_library = plex.library.section(recipe.NEW_LIBRARY_NAME)

    #time.sleep(5)

    # Retrieve a list of items from the new library
    print(u"Retrieving a list of items from the '{library}' library in "
          u"Plex...".format(library=recipe.NEW_LIBRARY_NAME))
    all_new_items = new_library.all()

    # Create a dictionary of {imdb_id: item}
    imdb_map = {}
    for m in all_new_items:
        if m.guid != None and 'imdb://' in m.guid:
            imdb_id = m.guid.split('imdb://')[1].split('?')[0]
        elif m.guid != None and 'themoviedb://' in m.guid:
            tmdb_id = m.guid.split('themoviedb://')[1].split('?')[0]
            imdb_id = get_imdb_id_from_tmdb(tmdb_id)
        elif m.guid != None and 'thetvdb://' in m.guid:
            tvdb_id = m.guid.split('thetvdb://')[1].split('?')[0].split('/')[0]
            imdb_id = get_imdb_id_from_tvdb(tvdb_id)
        else:
            imdb_id = None

        if imdb_id and imdb_id in item_ids:
            imdb_map[imdb_id] = m
        else:
            imdb_map[m.ratingKey] = m

    # Modify the sort titles
    print(u"Setting the sort titles for the '{}' library...".format(
        recipe.NEW_LIBRARY_NAME))
    in_library_idx = []
    if recipe.SORT_TITLE_ABSOLUTE:
        for i, m in enumerate(item_list):
            item = imdb_map.pop(m['id'], None)
            if item:
                add_sort_title(new_library_key, item.ratingKey, i+1, m['title'], library_type)
                in_library_idx.append(i)
    else:
        i = 0
        for m in item_list:
            item = imdb_map.pop(m['id'], None)
            if item:
                i += 1
                add_sort_title(new_library_key, item.ratingKey, i, m['title'], library_type)
                in_library_idx.append(i)

    if recipe.REMOVE_FROM_LIBRARY:
        # Remove items from library with are no longer on the trakt watched list
        print(u"Removing symlinks for items which are not on the trakt watched "
              u"list...".format(library=recipe.NEW_LIBRARY_NAME))
        count = 0
        updated_paths = []
        if library_type == 'movie':
            for movie in imdb_map.values():
                for part in movie.iterParts():
                    old_path_file = part.file.encode('UTF-8')
                    old_path, file_name = os.path.split(old_path_file)

                    folder_name = os.path.relpath(old_path, recipe.NEW_LIBRARY_FOLDER)

                    if folder_name == '.':
                        new_path = os.path.join(recipe.NEW_LIBRARY_FOLDER, file_name)
                        dir = False
                    else:
                        new_path = os.path.join(recipe.NEW_LIBRARY_FOLDER, folder_name)
                        dir = True

                    if (dir and os.path.exists(new_path)) or \
                            (not dir and os.path.isfile(new_path)):
                        try:
                            if os.name == 'nt':
                                if dir:
                                    os.rmdir(new_path)
                                else:
                                    os.remove(new_path)
                            else:
                                os.unlink(new_path)
                            count += 1
                            updated_paths.append(new_path)
                        except Exception as e:
                            print(u"Remove symlink failed for {path}: {e}".format(
                                path=new_path, e=e))
        else:
            for tv_show in imdb_map.values():
                done = False
                if done:
                    continue
                for episode in tv_show.episodes():
                    if done:
                        break
                    for part in episode.iterParts():
                        if done:
                            break
                        old_path_file = part.file.encode('UTF-8')
                        old_path, file_name = os.path.split(old_path_file)
                        old_path =  TV_LIBRARY_FOLDERS[0] + '/' + old_path.replace(TV_LIBRARY_FOLDERS[0], '').strip('/').split('/')[0]

                        folder_name = ''
                        for f in TV_LIBRARY_FOLDERS:
                            if old_path.lower().startswith(f.lower()):
                                folder_name = os.path.relpath(old_path, f)

                        new_path = os.path.join(recipe.NEW_LIBRARY_FOLDER, folder_name)
                        dir = True

                        if (dir and os.path.exists(new_path)) or (not dir and os.path.isfile(new_path)):
                            try:
                                if os.name == 'nt':
                                    if dir:
                                        os.rmdir(new_path)
                                    else:
                                        os.remove(new_path)
                                else:
                                    os.unlink(new_path)
                                count += 1
                                updated_paths.append(new_path)
                            except Exception as e:
                                print(u"Remove symlink failed for {path}: {e}".format(path=new_path, e=e))

        print(u"Removed symlinks for {count} items.".format(count=count))

        # Refresh the library to clean up the deleted items
        print(u"Refreshing the '{library}' library...".format(
            library=recipe.NEW_LIBRARY_NAME))
        new_library.update()
        time.sleep(10)
        new_library = plex.library.section(recipe.NEW_LIBRARY_NAME)
        while new_library.refreshing:
            time.sleep(5)
            new_library = plex.library.section(recipe.NEW_LIBRARY_NAME)
        new_library.emptyTrash()
    elif len(all_new_items) < recipe.MAX_COUNT:
        # TODO
        while imdb_map:
            item = imdb_map.pop(m['id'])
            i += 1
            add_sort_title(new_library_key, item.ratingKey, i, m['title'], library_type)
            in_library_idx.append(i)

    return len(item_ids)


if __name__ == "__main__":
    d, recipe_name = os.path.split(sys.argv[1])
    try:
        recipe = importlib.import_module('recipes.' + recipe_name.strip('.py'))
    except ImportError:
        raise Exception("Invalid recipe")

    if recipe.LIBRARY_TYPE.lower().startswith('movie'):
        library_type = 'movie'
    elif recipe.LIBRARY_TYPE.lower().startswith('tv'):
        library_type = 'tv'
    else:
        raise Exception("Library type should be 'movie' or 'tv'")

    if '--sort-only' in sys.argv:
        run_trakt_watched_sort_only(recipe, library_type)
    else:
        list_count = run_trakt_watched(recipe, library_type)
        print(u"Number of items in the new library: {count}".format(
            count=list_count))

    print(u"Done!")
