#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

import sys
import traceback
import psycopg2
from urllib.parse import urlparse
from config import cfg
from sqlalchemy.exc import ProgrammingError
from math import ceil

GAMETYPE_IDS = {}
MEDAL_IDS    = {}
WEAPON_IDS   = {}

MIN_ALIVE_TIME_TO_RATE = 60*10


def db_connect():
  result = urlparse( cfg["db_url"] )
  username = result.username
  password = result.password
  database = result.path[1:]
  hostname = result.hostname
  return psycopg2.connect(database = database, user = username, password = password, host = hostname)


# https://github.com/PredatH0r/XonStat/blob/380fbd4aeafb722c844f66920fb850a0ad6821d3/xonstat/views/submission.py#L19
def parse_stats_submission(body):
  """
  Parses the POST request body for a stats submission
  """
  # storage vars for the request body
  game_meta = {}
  events = {}
  players = []
  teams = []

  # we're not in either stanza to start
  in_P = in_Q = False

  for line in body.split('\n'):
    try:
      (key, value) = line.strip().split(' ', 1)

      if key not in 'P' 'Q' 'n' 'e' 't' 'i':
        game_meta[key] = value

      if key == 'Q' or key == 'P':
        #log.debug('Found a {0}'.format(key))
        #log.debug('in_Q: {0}'.format(in_Q))
        #log.debug('in_P: {0}'.format(in_P))
        #log.debug('events: {0}'.format(events))

        # check where we were before and append events accordingly
        if in_Q and len(events) > 0:
          #log.debug('creating a team (Q) entry')
          teams.append(events)
          events = {}
        elif in_P and len(events) > 0:
          #log.debug('creating a player (P) entry')
          players.append(events)
          events = {}

        if key == 'P':
          #log.debug('key == P')
          in_P = True
          in_Q = False
        elif key == 'Q':
          #log.debug('key == Q')
          in_P = False
          in_Q = True

        events[key] = value

      if key == 'e':
        (subkey, subvalue) = value.split(' ', 1)
        events[subkey] = subvalue
      if key == 'n':
        events[key] = value
      if key == 't':
        events[key] = value
    except:
      # no key/value pair - move on to the next line
      pass

  # add the last entity we were working on
  if in_P and len(events) > 0:
    players.append(events)
  elif in_Q and len(events) > 0:
    teams.append(events)

  return {"game_meta": game_meta, "players": players, "teams": teams}


def is_instagib(data):
  '''
  Checks if match is played with instagib mode
  '''
  def is_player_using_weapon( player, weapon ):
    try:
      return True if player['acc-' + weapon + '-cnt-fired'] == '0' else False
    except KeyError:
      return True 

  def is_player_using_railgun_and_gauntlet_only( player ):
    return all( map( lambda weapon: is_player_using_weapon( player, weapon), ['mg', 'sg', 'gl', 'rl', 'lg', 'pg', 'hmg', 'bfg', 'cg', 'ng', 'pm', 'gh'] ) )

  return all( map ( lambda player: is_player_using_railgun_and_gauntlet_only( player ), data['players'] ) )


def get_list(gametype, page):

  try:
    gametype_id = GAMETYPE_IDS[ gametype ];
  except KeyError:
    return {
      "ok": False,
      "message": "gametype is not supported: " + gametype
    }

  try:
    db = db_connect()
  except Exception as e:
    traceback.print_exc(file=sys.stderr)
    result = {
      "ok": False,
      "message": type(e).__name__ + ": " + str(e)
    }
    return result

  try:
    cu = db.cursor()
    query = '''
    SELECT
      p.steam_id, p.name, p.model, gr.rating, gr.n, count(*) OVER () AS count
    FROM
      players p
    LEFT JOIN gametype_ratings gr ON
      gr.steam_id = p.steam_id
    WHERE
      gr.n >= 10 AND
      gr.gametype_id = %s
    ORDER BY gr.rating DESC
    LIMIT %s
    OFFSET %s'''
    cu.execute(query, [gametype_id, cfg["player_count_per_page"], cfg["player_count_per_page"]*page])

    result = []
    rank = cfg["player_count_per_page"]*page + 1
    player_count = 0
    for row in cu.fetchall():
      if row[0] != None:
        result.append({
          "_id": str(row[0]),
          "name": row[1],
          "model": row[2] + ("/default" if row[2].find("/") == -1 else ""),
          "rating": row[3],
          "n": row[4],
          "rank": rank
        })
        rank += 1
      player_count = row[5]

    result = {
      "ok": True,
      "response": result,
      "page_count": ceil(player_count / cfg["player_count_per_page"])
    }
  except Exception as e:
    db.rollback()
    traceback.print_exc(file=sys.stderr)
    result = {
      "ok": False,
      "message": type(e).__name__ + ": " + str(e)
    }
  finally:
    cu.close()
    db.close()

  return result


def get_player_info(steam_id):

  try:
    db = db_connect()
  except Exception as e:
    traceback.print_exc(file=sys.stderr)
    result = {
      "ok": False,
      "message": type(e).__name__ + ": " + str(e)
    }
    return result

  try:
    cu = db.cursor()
    result = {}
    for gametype, gametype_id in GAMETYPE_IDS.items():
      query = '''
      SELECT 
        p.steam_id, p.name, p.model, g.gametype_short, gr.rating, gr.n, m.match_id, m.timestamp, m.old_rating
      FROM
        players p
      LEFT JOIN gametype_ratings gr ON gr.steam_id = p.steam_id
      LEFT JOIN gametypes g on gr.gametype_id = g.gametype_id
      LEFT JOIN (
        SELECT
          m.match_id, m.timestamp, m.gametype_id, s.old_rating
        FROM
          matches m
        LEFT JOIN scoreboards s ON s.match_id = m.match_id
        WHERE
          s.old_rating IS NOT NULL AND
          s.steam_id = %s AND
          m.gametype_id = %s
        ORDER BY m.timestamp DESC
        LIMIT 50
      ) m ON m.gametype_id = g.gametype_id
      WHERE
        p.steam_id = %s AND
        g.gametype_id = %s
      ORDER BY m.timestamp ASC
      '''
      cu.execute(query, [steam_id, gametype_id, steam_id, gametype_id])
      for row in cu.fetchall():
        result[ "_id" ] = str(row[0])
        result[ "name" ] = row[1]
        result[ "model" ] = row[2]
        if gametype not in result:
          result[ gametype ] = {"rating": round(row[4], 2), "n": row[5], "history": []}
        result[ gametype ][ "history" ].append({"match_id": row[6], "timestamp": row[7], "rating": round(row[8], 2)})

    result = {
      "ok": True,
      "player": result
    }
  except Exception as e:
    db.rollback()
    traceback.print_exc(file=sys.stderr)
    result = {
      "ok": False,
      "message": type(e).__name__ + ": " + str(e)
    }
  finally:
    cu.close()
    db.close()

  return result


def get_factory_id( cu, factory ):
  cu.execute( "SELECT factory_id FROM factories WHERE factory_short = %s", [factory] )
  try:
    return cu.fetchone()[0]
  except TypeError:
    cu.execute("INSERT INTO factories (factory_id, factory_short) VALUES (nextval('factory_seq'), %s) RETURNING factory_id", [factory])
    return cu.fetchone()[0]


def get_map_id( cu, map_name ):
  map_name = map_name.lower()
  cu.execute( "SELECT map_id FROM maps WHERE map_name = %s", [map_name] )
  try:
    return cu.fetchone()[0]
  except TypeError:
    cu.execute("INSERT INTO maps (map_id, map_name) VALUES (nextval('map_seq'), %s) RETURNING map_id", [map_name])
    return cu.fetchone()[0]


def get_player_rating( cu, steam_id, gametype_id ):
  cu.execute( "SELECT rating FROM gametype_ratings WHERE steam_id = %s AND gametype_id = %s", [steam_id, gametype_id] )
  try:
    return cu.fetchone()[0]
  except TypeError:
    cu.execute("INSERT INTO gametype_ratings (steam_id, gametype_id, rating) VALUES (%s, %s, %s)", [steam_id, gametype_id, None])
    return None


def get_for_balance_plugin( steam_ids ):
  """
  Outputs player ratings compatible with balance.py plugin from miqlx-plugins

  Args:
    steam_ids (list): array of steam ids

  Returns:
    on success:
    {
      "ok": True
      "players": [...],
      "deactivated": []
    }

    on fail:
    {
      "ok": False
      "message": "error message"
    }
  """
  players = {}
  result = []
  try:

    db = db_connect()
    cu = db.cursor()

    query = '''
    SELECT
      steam_id, gametype_short, rating, n
    FROM
      gametype_ratings gr
    LEFT JOIN
      gametypes gt ON gr.gametype_id = gt.gametype_id
    WHERE
      steam_id IN %s'''
    cu.execute( query, [tuple(steam_ids)] )
    for row in cu.fetchall():
      steam_id = str(row[0])
      gametype = row[1]
      rating   = round(row[2], 2)
      n        = row[3]
      if steam_id not in players:
        players[ steam_id ] = {"steamid": steam_id}
      players[ steam_id ][ gametype ] = {"games": n, "elo": rating}

    for steam_id, data in players.items():
      result.append( data )
    result = {
      "ok": True,
      "players": result,
      "deactivated": []
    }

  except Exception as e:
    db.rollback()
    traceback.print_exc(file=sys.stderr)
    result = {
      "ok": False,
      "message": type(e).__name__ + ": " + str(e)
    }
  finally:
    db.close()

  return result


def count_player_match_rating( gametype, player_data ):
  alive_time    = int( player_data["alivetime"] )
  score         = int( player_data["scoreboard-score"] )
  damage_dealt  = int( player_data["scoreboard-pushes"] )
  damage_taken  = int( player_data["scoreboard-destroyed"] )
  frags_count   = int( player_data["scoreboard-kills"] )
  deaths_count  = int( player_data["scoreboard-deaths"] )
  capture_count = int( player_data["medal-captures"] )
  win           = 1 if "win" in player_data else 0

  if alive_time < MIN_ALIVE_TIME_TO_RATE:
    return None
  else:
    time_factor   = 1200./alive_time

  return {
    "ad": ( damage_dealt/100 + frags_count + capture_count ) * time_factor,
    "ctf": ( damage_dealt/damage_taken * ( score + damage_dealt/20 ) * time_factor + win*300 ) / 2.35,
    "tdm": ( 0.5 * (frags_count - deaths_count) + 0.004 * (damage_dealt - damage_taken) + 0.003 * damage_dealt ) * time_factor
  }[gametype]


def post_process(cu, match_id, gametype_id):
  """
  Updates players' ratings for match_id. I call this post processing

  """
  cu.execute("SELECT steam_id, team, match_rating FROM scoreboards WHERE match_rating IS NOT NULL AND match_id = %s", [match_id])

  rows = cu.fetchall()
  for row in rows:
    steam_id     = row[0]
    team         = row[1]
    match_rating = round(row[2], 2)

    old_rating = get_player_rating( cu, steam_id, gametype_id )

    cu.execute("UPDATE scoreboards SET old_rating = %s WHERE match_id = %s AND steam_id = %s AND team = %s", [old_rating, match_id, steam_id, team])
    assert cu.rowcount == 1

    if old_rating == None:
      new_rating = match_rating
    else:
      query_string = '''
      SELECT
        AVG(rating)
      FROM (
        SELECT
          s.match_rating as rating
        FROM
          matches m
        LEFT JOIN
          scoreboards s on s.match_id = m.match_id
        WHERE
          s.steam_id = %s AND
          m.gametype_id = %s AND
          (m.post_processed = TRUE OR m.match_id = %s) AND
          s.match_rating IS NOT NULL
        ORDER BY m.timestamp DESC
        LIMIT 50
      ) t'''
      cu.execute(query_string, [steam_id, gametype_id, match_id])
      new_rating = cu.fetchone()[0]
      assert new_rating != None

    cu.execute("UPDATE gametype_ratings SET rating = %s, n = n + 1 WHERE steam_id = %s AND gametype_id = %s", [new_rating, steam_id, gametype_id])
    assert cu.rowcount == 1

  cu.execute("UPDATE matches SET post_processed = TRUE WHERE match_id = %s", [match_id])
  assert cu.rowcount == 1


def submit_match(data):
  """
  Match report handler

  Args:
    data (str): match report

  Returns: {
      "ok: True/False - on success/fail
      "message":      - operation result description
      "match_id":     - match_id of match_report
    }
  """
  try:
    if type(data).__name__ == 'str':
      data = parse_stats_submission( data )

    if is_instagib(data):
      data["game_meta"]["G"] = "i" + data["game_meta"]["G"]

    match_id = data["game_meta"]["I"]

    if data["game_meta"]["G"] not in GAMETYPE_IDS:
      return {
        "ok": False,
        "message": "gametype is not accepted: " + data["game_meta"]["G"],
        "match_id": match_id
      }

    db = db_connect()

  except Exception as e:
    traceback.print_exc(file=sys.stderr)
    return {
      "ok": False,
      "message": type(e).__name__ + ": " + str(e),
      "match_id": None
    }

  try:
    cu = db.cursor()

    team_scores = [None, None]
    team_index = -1
    for team_data in data["teams"]:
      team_index = int( team_data["Q"].replace("team#", "") ) - 1
      for key in ["scoreboard-rounds", "scoreboard-caps", "scoreboard-score"]:
        if key in team_data:
          team_scores[team_index] = int(team_data[key])
    team1_score, team2_score = team_scores

    cu.execute("INSERT INTO matches (match_id, gametype_id, factory_id, map_id, timestamp, duration, team1_score, team2_score, post_processed) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", [
      match_id,
      GAMETYPE_IDS[ data["game_meta"]["G"] ],
      get_factory_id( cu, data["game_meta"]["O"] ),
      get_map_id( cu, data["game_meta"]["M"] ),
      int( data["game_meta"]["1"] ),
      int( data["game_meta"]["D"] ),
      team1_score,
      team2_score,
      cfg["run_post_process"]
    ])

    for player in data["players"]:
      player["P"] = int(player["P"])
      team = int(player["t"]) if "t" in player else 0

      cu.execute( "SELECT EXISTS(SELECT steam_id FROM players WHERE steam_id = %s)", [player["P"]] )
      player_exists = cu.fetchone()[0]

      if player_exists:
        cu.execute( "UPDATE players SET name = %s, model = %s WHERE steam_id = %s", [player["n"], player["playermodel"], player["P"]] )
      else:
        cu.execute( "INSERT INTO players (steam_id, name, model) VALUES (%s, %s, %s)", [player["P"], player["n"], player["playermodel"]] )

      cu.execute("INSERT INTO scoreboards (match_id, steam_id, match_rating, alive_time, team) VALUES (%s, %s, %s, %s, %s)", [
        match_id,
        player["P"],
        count_player_match_rating( data["game_meta"]["G"], player),
        int( player["alivetime"] ),
        team
      ])

      for weapon, weapon_id in WEAPON_IDS.items():
        cu.execute("INSERT INTO scoreboards_weapons (match_id, steam_id, team, weapon_id, frags, hits, shots) VALUES (%s, %s, %s, %s, %s, %s, %s)", [
          match_id,
          player["P"],
          team,
          weapon_id,
          int( player["acc-" + weapon + "-frags"] ),
          int( player["acc-" + weapon + "-cnt-hit"] ),
          int( player["acc-" + weapon + "-cnt-fired"] )
        ])

      for medal, medal_id in MEDAL_IDS.items():
        cu.execute("INSERT INTO scoreboards_medals (match_id, steam_id, team, medal_id, count) VALUES (%s, %s, %s, %s, %s)", [
          match_id,
          player["P"],
          team,
          medal_id,
          int( player["medal-" + medal] )
        ])

    # post processing
    if cfg["run_post_process"] == True:
      post_process( cu, match_id, GAMETYPE_IDS[ data["game_meta"]["G"] ] )
      result = {
        "ok": True,
        "message": "done",
        "match_id": match_id
      }
    else:
      result = {
        "ok": True,
        "message": "skipped post processing",
        "match_id": match_id
      }

    db.commit()
  except Exception as e:
    db.rollback()
    traceback.print_exc(file=sys.stderr)
    result = {
      "ok": False,
      "message": type(e).__name__ + ": " + str(e),
      "match_id": match_id
    }
  finally:
    db.close()

  return result


def get_scoreboard(match_id):

  try:
    db = db_connect()
  except Exception as e:
    traceback.print_exc(file=sys.stderr)
    result = {
      "ok": False,
      "message": type(e).__name__ + ": " + str(e)
    }
    return result

  try:
    cu = db.cursor()

    query = '''
    SELECT
      json_build_object(
        'gametype',    g.gametype_short,
        'factory',     f.factory_short,
        'map',         mm.map_name,
        'team1_score', m.team1_score,
        'team2_score', m.team2_score,
        'timestamp',   m.timestamp,
        'duration',    m.duration
      )
    FROM
      matches m
    LEFT JOIN gametypes g ON g.gametype_id = m.gametype_id
    LEFT JOIN factories f ON f.factory_id = m.factory_id
    LEFT JOIN maps mm ON m.map_id = mm.map_id
    WHERE
      match_id = %s;
    '''
    cu.execute(query, [match_id])
    try:
      summary = cu.fetchone()[0]
    except TypeError:
      return {
        "message": "match not found",
        "ok": False
      }

    query = '''
    SELECT
      json_object_agg(t.steam_id, t.weapon_stats)
    FROM (
      SELECT
        t.steam_id::text,
        json_object_agg(t.weapon_short, ARRAY[t.frags, t.hits, t.shots]) AS weapon_stats
      FROM (
        SELECT
          s.steam_id,
          w.weapon_short,
          SUM(sw.frags) AS frags,
          SUM(sw.hits) AS hits,
          SUM(sw.shots) AS shots
        FROM
          scoreboards s
        LEFT JOIN scoreboards_weapons sw ON sw.match_id = s.match_id AND sw.steam_id = s.steam_id AND sw.team = s.team
        LEFT JOIN weapons w ON w.weapon_id = sw.weapon_id
        WHERE
          s.match_id = %s
        GROUP BY s.steam_id, w.weapon_short
      ) t
      GROUP BY t.steam_id
    ) t;
    '''
    cu.execute(query, [match_id])
    player_weapon_stats = cu.fetchone();

    query = '''
    SELECT
      json_object_agg(t.steam_id, t.medal_stats)
    FROM (
      SELECT
        t.steam_id::text,
        json_object_agg(t.medal_short, t.count) AS medal_stats
      FROM (
        SELECT
          s.steam_id,
          m.medal_short,
          SUM(sm.count) AS count
        FROM
          scoreboards s
        LEFT JOIN scoreboards_medals sm ON sm.match_id = s.match_id AND sm.steam_id = s.steam_id AND sm.team = s.team
        LEFT JOIN medals m ON m.medal_id = sm.medal_id
        WHERE
          s.match_id = %s
        GROUP BY s.steam_id, m.medal_short
      ) t
      GROUP BY t.steam_id
    ) t;
    '''
    cu.execute(query, [match_id])
    player_medal_stats = cu.fetchone();

    result = {
      "summary": summary,
      "player_stats": {"weapons": player_weapon_stats, "medals": player_medal_stats},
      "ok": True
    }
  except Exception as e:
    db.rollback()
    traceback.print_exc(file=sys.stderr)
    result = {
      "ok": False,
      "message": type(e).__name__ + ": " + str(e)
    }
  finally:
    cu.close()
    db.close()

  return result

db = db_connect()
cu = db.cursor()
cu.execute("SELECT gametype_id, gametype_short FROM gametypes")
for row in cu.fetchall():
  GAMETYPE_IDS[ row[1] ] = row[0]

cu.execute("SELECT medal_id, medal_short FROM medals")
for row in cu.fetchall():
  MEDAL_IDS[ row[1] ] = row[0]

cu.execute("SELECT weapon_id, weapon_short FROM weapons")
for row in cu.fetchall():
  WEAPON_IDS[ row[1] ] = row[0]

if cfg["run_post_process"]:
  cu.execute("SELECT match_id, gametype_id, timestamp FROM matches WHERE post_processed = FALSE ORDER BY timestamp ASC")
  for row in cu.fetchall():
    print("running post process: " + str(row[0]) + "\t" + str(row[2]))
    post_process(cu, row[0], row[1])
    db.commit()

cu.close()
db.close()

