CREATE TABLE players (
  steam_id BIGINT,
  name TEXT,
  model TEXT,
  last_played_timestamp BIGINT DEFAULT 0,
  PRIMARY KEY (steam_id)
);

CREATE TABLE gametypes (
  gametype_id SMALLINT,
  gametype_name TEXT,
  gametype_short TEXT,
  PRIMARY KEY (gametype_id)
);

INSERT INTO gametypes (gametype_id, gametype_name, gametype_short) VALUES
  (1, 'Attack & Defend',  'ad'),
  (2, 'Capture the Flag', 'ctf'),
  (3, 'Team Deathmatch',  'tdm');

CREATE TABLE weapons (
  weapon_id SMALLINT,
  weapon_name TEXT,
  weapon_short TEXT,
  PRIMARY KEY (weapon_id)
);

INSERT INTO weapons (weapon_id, weapon_name, weapon_short) VALUES
  (1, 'Gauntlet',         'gt'),
  (2, 'Machine Gun',      'mg'),
  (3, 'Shotgun',          'sg'),
  (4, 'Grenade Launcher', 'gl'),
  (5, 'Rocket Launcher',  'rl'),
  (6, 'Lightning Gun',    'lg'),
  (7, 'Railgun',          'rg'),
  (8, 'Plasma Gun',       'pg'),
  (9, 'Heavy Machine Gun','hmg');

CREATE TABLE medals (
  medal_id SMALLINT,
  medal_name TEXT,
  medal_short TEXT,
  PRIMARY KEY (medal_id)
);

INSERT INTO medals (medal_id, medal_name, medal_short) VALUES
  (1, 'Accuracy',     'accuracy'),
  (2, 'Assists',      'assists'),
  (3, 'Captures',     'captures'),
  (4, 'Combokill',    'combokill'),
  (5, 'Defends',      'defends'),
  (6, 'Excellent',    'excellent'),
  (7, 'First Frag',   'firstfrag'),
  (8, 'Headshot',     'headshot'),
  (9, 'Humiliation',  'humiliation'),
  (10,'Impressive',   'impressive'),
  (11,'Midair',       'midair'),
  (12,'Perfect',      'perfect'),
  (13,'Perforated',   'perforated'),
  (14,'Quad God',     'quadgod'),
  (15,'Rampage',      'rampage'),
  (16,'Revenge',      'revenge');

CREATE TABLE gametype_ratings (
  steam_id BIGINT,
  gametype_id SMALLINT,
  rating REAL,
  n BIGINT DEFAULT 0,
  last_played_timestamp BIGINT DEFAULT 0,
  FOREIGN KEY (steam_id)    REFERENCES players(steam_id),
  FOREIGN KEY (gametype_id) REFERENCES gametypes(gametype_id),
  PRIMARY KEY (steam_id, gametype_id)
);

CREATE TABLE factories (
  factory_id SMALLINT,
  factory_short TEXT,
  PRIMARY KEY (factory_id)
);

CREATE SEQUENCE factory_seq START 1;

CREATE TABLE maps (
  map_id SMALLINT,
  map_name TEXT,
  PRIMARY KEY (map_id)
);

CREATE SEQUENCE map_seq START 1;

CREATE TABLE matches (
  match_id UUID,
  gametype_id SMALLINT,
  factory_id SMALLINT,
  map_id SMALLINT,
  team1_score SMALLINT,
  team2_score SMALLINT,
  timestamp BIGINT,
  duration SMALLINT,
  post_processed BOOL,
  FOREIGN KEY (gametype_id) REFERENCES gametypes(gametype_id),
  FOREIGN KEY (factory_id)  REFERENCES factories(factory_id),
  FOREIGN KEY (map_id)      REFERENCES maps(map_id),
  PRIMARY KEY (match_id)
);

CREATE TABLE scoreboards (
  match_id UUID,
  steam_id BIGINT,
  team SMALLINT,
  frags SMALLINT,
  deaths SMALLINT,
  damage_dealt INTEGER,
  damage_taken INTEGER,
  score SMALLINT,
  alive_time INTEGER,
  match_perf REAL,
  match_rating REAL,
  old_rating REAL DEFAULT NULL,
  new_rating REAL DEFAULT NULL,
  FOREIGN KEY (match_id) REFERENCES matches(match_id),
  FOREIGN KEY (steam_id) REFERENCES players(steam_id),
  PRIMARY KEY (match_id, steam_id, team)
);

CREATE TABLE scoreboards_weapons (
  match_id UUID,
  steam_id BIGINT,
  team SMALLINT,
  weapon_id SMALLINT,
  frags SMALLINT,
  hits  INTEGER,
  shots INTEGER,
  FOREIGN KEY (match_id, steam_id, team) REFERENCES scoreboards(match_id, steam_id, team),
  FOREIGN KEY (weapon_id) REFERENCES weapons(weapon_id),
  PRIMARY KEY (match_id, steam_id, team, weapon_id)
);

CREATE TABLE scoreboards_medals (
  match_id UUID,
  steam_id BIGINT,
  team SMALLINT,
  medal_id SMALLINT,
  count SMALLINT,
  FOREIGN KEY (match_id, steam_id, team) REFERENCES scoreboards(match_id, steam_id, team),
  FOREIGN KEY (medal_id) REFERENCES medals(medal_id),
  PRIMARY KEY (match_id, steam_id, team, medal_id)
);

