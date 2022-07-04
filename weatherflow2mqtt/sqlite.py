import datetime
import json
import logging
import os.path
import sqlite3
import time
from datetime import timezone
from sqlite3 import Error as SQLError
from typing import OrderedDict

from .const import (
    COL_DEWPOINT,
    COL_HUMIDITY,
    COL_ILLUMINANCE,
    COL_PRESSURE,
    COL_RAINDURATION,
    COL_RAINRATE,
    COL_SOLARRAD,
    COL_STRIKECOUNT,
    COL_STRIKEENERGY,
    COL_TEMPERATURE,
    COL_UV,
    COL_WINDGUST,
    COL_WINDLULL,
    COL_WINDSPEED,
    DATABASE_VERSION,
    PRESSURE_TREND_TIMER,
    STORAGE_FILE,
    STORAGE_ID,
    STRIKE_COUNT_TIMER,
    TABLE_HIGH_LOW,
    TABLE_LIGHTNING,
    TABLE_PRESSURE,
    TABLE_STORAGE,
    UNITS_IMPERIAL,
    UTC,
)

_LOGGER = logging.getLogger(__name__)


class SQLFunctions:
    """Class to handle SQLLite functions."""

    def __init__(self, unit_system, debug=False):
        """Initialize SQLFunctions."""
        self.connection = None
        self._unit_system = unit_system
        self._debug = debug

    def create_connection(self, db_file):
        """Create a database connection to a SQLite database."""
        try:
            self.connection = sqlite3.connect(db_file)

        except SQLError as e:
            _LOGGER.error("Could not create SQL Database. Error: %s", e)

    def create_table(self, create_table_sql):
        """Create table from the create_table_sql statement.

        :param conn: Connection object
        :param create_table_sql: a CREATE TABLE statement
        :return:
        """
        try:
            c = self.connection.cursor()
            c.execute(create_table_sql)
        except SQLError as e:
            _LOGGER.error("Could not create SQL Table. Error: %s", e)

    def create_storage_row(self, rowdata):
        """Create new storage row into the storage table.

        :param conn:
        :param rowdata:
        :return: project id
        """
        sql = """   INSERT INTO storage(id, rain_today, rain_yesterday, rain_start, rain_duration_today,
                    rain_duration_yesterday, lightning_count, lightning_count_today, last_lightning_time,
                    last_lightning_distance, last_lightning_energy)
                    VALUES(?, ?,?,?,?,?,?,?,?,?,?) """
        try:
            cur = self.connection.cursor()
            cur.execute(sql, rowdata)
            self.connection.commit()
            return cur.lastrowid
        except SQLError as e:
            _LOGGER.error("Could not Insert data in table storage. Error: %s", e)

    def readStorage(self):
        """Return data from the storage table as JSON."""
        try:
            cursor = self.connection.cursor()
            cursor.execute(f"SELECT * FROM storage WHERE id = {STORAGE_ID};")
            data = cursor.fetchall()

            for row in data:
                storage_json = {
                    "rain_today": row[1],
                    "rain_yesterday": row[2],
                    "rain_start": row[3],
                    "rain_duration_today": row[4],
                    "rain_duration_yesterday": row[5],
                    "lightning_count": row[6],
                    "lightning_count_today": row[7],
                    "last_lightning_time": row[8],
                    "last_lightning_distance": row[9],
                    "last_lightning_energy": row[10],
                }

            return storage_json

        except SQLError as e:
            _LOGGER.error("Could not access storage data. Error: %s", e)

    def writeStorage(self, json_data: OrderedDict):
        """Store data in the storage table from JSON."""
        try:
            cursor = self.connection.cursor()
            sql_statement = """UPDATE storage
                               SET  rain_today=?,
                                    rain_yesterday=?,
                                    rain_start=?,
                                    rain_duration_today=?,
                                    rain_duration_yesterday=?,
                                    lightning_count=?,
                                    lightning_count_today=?,
                                    last_lightning_time=?,
                                    last_lightning_distance=?,
                                    last_lightning_energy=?
                                WHERE ID = ?
                                """

            rowdata = (
                json_data["rain_today"],
                json_data["rain_yesterday"],
                json_data["rain_start"],
                json_data["rain_duration_today"],
                json_data["rain_duration_yesterday"],
                json_data["lightning_count"],
                json_data["lightning_count_today"],
                json_data["last_lightning_time"],
                json_data["last_lightning_distance"],
                json_data["last_lightning_energy"],
                STORAGE_ID,
            )

            cursor.execute(sql_statement, rowdata)
            self.connection.commit()

        except SQLError as e:
            _LOGGER.error("Could not update storage data. Error: %s", e)

    def readPressureTrend(self, new_pressure, translations):
        """Return Pressure Trend."""
        if new_pressure is None:
            return "Steady", 0

        try:
            time_point = time.time() - PRESSURE_TREND_TIMER
            cursor = self.connection.cursor()
            cursor.execute(
                f"SELECT pressure FROM pressure WHERE timestamp < {time_point} ORDER BY timestamp DESC LIMIT 1;"
            )
            old_pressure = cursor.fetchone()
            if old_pressure is None:
                old_pressure = new_pressure
            else:
                old_pressure = float(old_pressure[0])
            pressure_delta = new_pressure - old_pressure

            min_value = -1
            max_value = 1
            if self._unit_system == UNITS_IMPERIAL:
                min_value = -0.0295
                max_value = 0.0295

            if pressure_delta > min_value and pressure_delta < max_value:
                return translations["trend"]["steady"], 0
            if pressure_delta <= min_value:
                return translations["trend"]["falling"], round(pressure_delta, 2)
            if pressure_delta >= max_value:
                return translations["trend"]["rising"], round(pressure_delta, 2)

        except SQLError as e:
            _LOGGER.error("Could not read pressure data. Error: %s", e)
        except Exception as e:
            _LOGGER.error("Could not calculate pressure trend. Error message: %s", e)

    def readPressureData(self):
        """Return formatted pressure data - USED FOR TESTING ONLY."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM pressure;")
            data = cursor.fetchall()

            for row in data:
                tid = datetime.datetime.fromtimestamp(row[0]).isoformat()
                print(tid, row[1])

        except SQLError as e:
            _LOGGER.error("Could not access storage data. Error: %s", e)

    def writePressure(self, pressure):
        """Add entry to the Pressure Table."""
        try:
            cur = self.connection.cursor()
            cur.execute(
                f"INSERT INTO pressure(timestamp, pressure) VALUES({time.time()}, {pressure});"
            )
            self.connection.commit()
            return True
        except SQLError as e:
            _LOGGER.error("Could not Insert data in table Pressure. Error: %s", e)
            return False
        except Exception as e:
            _LOGGER.error("Could write to Pressure Table. Error message: %s", e)
            return False

    def readLightningCount(self, hours: int):
        """Return number of Lightning Strikes in the last x hours."""
        try:
            time_point = time.time() - hours * 60 * 60
            cursor = self.connection.cursor()
            cursor.execute(
                f"SELECT COUNT(*) FROM lightning WHERE timestamp > {time_point};"
            )
            data = cursor.fetchone()[0]

            return data

        except SQLError as e:
            _LOGGER.error("Could not access storage data. Error: %s", e)

    def writeLightning(self):
        """Adds an entry to the Lightning Table."""

        try:
            cur = self.connection.cursor()
            cur.execute(f"INSERT INTO lightning(timestamp) VALUES({time.time()});")
            self.connection.commit()
            return True
        except SQLError as e:
            _LOGGER.error("Could not Insert data in table Lightning. Error: %s", e)
            return False
        except Exception as e:
            _LOGGER.error("Could write to Lightning Table. Error message: %s", e)
            return False

    def writeDailyLog(self, sensor_data):
        """Add entry to the Daily Log Table."""
        try:
            data = json.loads(json.dumps(sensor_data))
            temp = data.get("air_temperature")
            pres = data.get("sealevel_pressure")
            wspeed = data.get("wind_speed_avg")

            cursor = self.connection.cursor()
            cursor.execute(
                f"INSERT INTO daily_log(timestamp, temperature, pressure, windspeed) VALUES({time.time()}, ?, ?, ?)",
                (temp, pres, wspeed),
            )
            self.connection.commit()

        except SQLError as e:
            _LOGGER.error("Could not Insert data in table daily_log. Error: %s", e)
        except Exception as e:
            _LOGGER.error("Could not write to daily_log Table. Error message: %s", e)

    def updateDayData(self, sensor_data):
        """Update Day Data Table."""
        try:
            data = json.loads(json.dumps(sensor_data))
            temp = data.get("air_temperature")
            pres = data.get("sealevel_pressure")
            wspeed = data.get("wind_speed_avg")
            hum = data.get("relative_humidity")
            dew = data.get("dewpoint")
            illum = data.get("illuminance")
            rain_dur = data.get("rain_duration_today")
            rain_rate = data.get("rain_rate")
            wgust = data.get("wind_gust")
            wlull = data.get("wind_lull")
            strike_e = data.get("lightning_strike_energy")
            strike_c = data.get("lightning_strike_count_today")
            uv = data.get("uv")
            solrad = data.get("solar_radiation")

            cursor = self.connection.cursor()
            sql_columns = "INSERT INTO day_data("
            sql_columns += "timestamp, air_temperature, sealevel_pressure, wind_speed_avg, relative_humidity, dewpoint,"
            sql_columns += "illuminance, rain_duration_today, rain_rate, wind_gust, wind_lull, lightning_strike_energy,"
            sql_columns += "lightning_strike_count_today, uv, solar_radiation"
            sql_columns += ")"
            cursor.execute(
                f"{sql_columns} VALUES({time.time()}, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    temp,
                    pres,
                    wspeed,
                    hum,
                    dew,
                    illum,
                    rain_dur,
                    rain_rate,
                    wgust,
                    wlull,
                    strike_e,
                    strike_c,
                    uv,
                    solrad,
                ),
            )
            self.connection.commit()

        except SQLError as e:
            _LOGGER.error("Could not Insert data in table day_data. Error: %s", e)
        except Exception as e:
            _LOGGER.error("Could not write to day_data Table. Error message: %s", e)

    def updateHighLow(self, sensor_data):
        """Update High and Low Values."""
        try:
            self.connection.row_factory = sqlite3.Row
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM high_low;")
            table_data = cursor.fetchall()

            data = dict(sensor_data)

            for row in table_data:
                max_sql = None
                min_sql = None
                sensor_value = None
                do_update = False
                # Get Value of Sensor if available
                if data.get(row["sensorid"]) is not None:
                    sensor_value = data[row["sensorid"]]

                # If we have a value, check if min/max changes
                if sensor_value is not None:
                    if sensor_value > row["max_day"]:
                        max_sql = (
                            f" max_day = {sensor_value}, max_day_time = {time.time()} "
                        )
                        do_update = True
                    if sensor_value < row["min_day"]:
                        min_sql = (
                            f" min_day = {sensor_value}, min_day_time = {time.time()} "
                        )
                        do_update = True

                # If min/max changes, update the record
                sql = "UPDATE high_low SET"
                if do_update:
                    if max_sql:
                        sql = f"{sql} {max_sql}"
                    if max_sql and min_sql:
                        sql = f"{sql},"
                    if min_sql:
                        sql = f"{sql} {min_sql}"
                    sql = f"{sql}, latest = {sensor_value} WHERE sensorid = '{row['sensorid']}'"
                    if self._debug:
                        _LOGGER.debug("Min/Max SQL: %s", sql)
                    cursor.execute(sql)
                    self.connection.commit()
                else:
                    if sensor_value is not None:
                        sql = f"{sql} latest = {sensor_value} WHERE sensorid = '{row['sensorid']}'"
                        if self._debug:
                            _LOGGER.debug("Latest SQL: %s", sql)
                        cursor.execute(sql)
                        self.connection.commit()

        except SQLError as e:
            _LOGGER.error("Could not update High and Low data. Error: %s", e)
            return False
        except Exception as e:
            _LOGGER.error("Could not write to High and Low Table. Error message: %s", e)
            return False

    def readHighLow(self):
        """Return data from the high_low table as JSON."""
        try:
            self.connection.row_factory = sqlite3.Row
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM high_low")
            data = cursor.fetchall()

            sensor_json = {}
            for row in data:
                sensor_json[row["sensorid"]] = {
                    "max_day": row["max_day"],
                    "max_day_time": None
                    if not row["max_day_time"]
                    else datetime.datetime.utcfromtimestamp(round(row["max_day_time"]))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "max_month": row["max_month"],
                    "max_month_time": None
                    if not row["max_month_time"]
                    else datetime.datetime.utcfromtimestamp(
                        round(row["max_month_time"])
                    )
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "max_all": row["max_all"],
                    "max_all_time": None
                    if not row["max_all_time"]
                    else datetime.datetime.utcfromtimestamp(round(row["max_all_time"]))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "min_day": row["min_day"],
                    "min_day_time": None
                    if not row["min_day_time"]
                    else datetime.datetime.utcfromtimestamp(round(row["min_day_time"]))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "min_month": row["min_month"],
                    "min_month_time": None
                    if not row["min_month_time"]
                    else datetime.datetime.utcfromtimestamp(
                        round(row["min_month_time"])
                    )
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "min_all": row["min_all"],
                    "min_all_time": None
                    if not row["min_all_time"]
                    else datetime.datetime.utcfromtimestamp(round(row["min_all_time"]))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                }
            return sensor_json

        except SQLError as e:
            _LOGGER.error("Could not access high_low data. Error: %s", e)
            return None
        except Exception as e:
            _LOGGER.error("Could not get all High Low values. Error message: %s", e)
            return sensor_json

    def migrateStorageFile(self):
        """Migrate old .storage.json file to the database."""
        try:
            with open(STORAGE_FILE, "r") as jsonFile:
                old_data = json.load(jsonFile)

                # We need to convert the Rain Start to timestamp
                dt = datetime.datetime.strptime(
                    old_data["rain_start"], "%Y-%m-%dT%H:%M:%S"
                )
                timestamp = dt.replace(tzinfo=timezone.utc).timestamp()

                storage_json = {
                    "rain_today": old_data["rain_today"],
                    "rain_yesterday": old_data["rain_yesterday"],
                    "rain_start": timestamp,
                    "rain_duration_today": old_data["rain_duration_today"],
                    "rain_duration_yesterday": old_data["rain_duration_yesterday"],
                    "lightning_count": old_data["lightning_count"],
                    "lightning_count_today": old_data["lightning_count_today"],
                    "last_lightning_time": old_data["last_lightning_time"],
                    "last_lightning_distance": old_data["last_lightning_distance"],
                    "last_lightning_energy": old_data["last_lightning_energy"],
                }

                self.writeStorage(storage_json)

        except FileNotFoundError as e:
            _LOGGER.error("Could not find old storage file. Error message: %s", e)
        except Exception as e:
            _LOGGER.error("Could not Read storage file. Error message: %s", e)

    def createInitialDataset(self):
        """Initialize Initial database, and migrate data if needed."""
        try:
            with self.connection:
                # Create Empty Tables
                self.create_table(TABLE_STORAGE)
                self.create_table(TABLE_LIGHTNING)
                self.create_table(TABLE_PRESSURE)
                self.create_table(TABLE_HIGH_LOW)

                # Store Initial Data
                storage = (STORAGE_ID, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                self.create_storage_row(storage)
                self.initializeHighLow()

                # Update the version number
                cursor = self.connection.cursor()
                cursor.execute(f"PRAGMA main.user_version = {DATABASE_VERSION};")

                # Migrate data if they exist
                if os.path.isfile(STORAGE_FILE):
                    self.migrateStorageFile()

        except Exception as e:
            _LOGGER.error("Could not Read storage file. Error message: %s", e)

    def upgradeDatabase(self):
        """Upgrade Database to ensure tables and columns are correct."""
        try:
            # Get Database Version
            cursor = self.connection.cursor()
            cursor.execute("PRAGMA main.user_version;")
            db_version = int(cursor.fetchone()[0])

            if db_version < 1:
                _LOGGER.info("Upgrading the database to version 1")
                # Create Empty Tables
                self.create_table(TABLE_HIGH_LOW)
                # Add Initial data to High Low
                self.initializeHighLow()

            if db_version < DATABASE_VERSION:
                _LOGGER.info("Upgrading the database to version 2")
                cursor.execute("ALTER TABLE high_low ADD max_yday REAL")
                cursor.execute("ALTER TABLE high_low ADD max_yday_time REAL")
                cursor.execute("ALTER TABLE high_low ADD min_yday REAL")
                cursor.execute("ALTER TABLE high_low ADD min_yday_time REAL")

                self.connection.commit()

                # if db_version < 2:
                #     _LOGGER.info("Upgrading the database to version 2")
                #     cursor.execute("ALTER TABLE high_low ADD max_yday REAL")
                #     cursor.execute("ALTER TABLE high_low ADD max_yday_time REAL")
                #     cursor.execute("ALTER TABLE high_low ADD min_yday REAL")
                #     cursor.execute("ALTER TABLE high_low ADD min_yday_time REAL")

                # if db_version < DATABASE_VERSION:
                #     _LOGGER.info("Upgrading the database to version %s...", DATABASE_VERSION)
                #     self.create_table(TABLE_DAY_DATA)
                #     self.connection.commit()

                # Finally update the version number
                cursor.execute(f"PRAGMA main.user_version = {DATABASE_VERSION};")
                _LOGGER.info("Database now version %s", DATABASE_VERSION)

        except Exception as e:
            _LOGGER.error("An undefined error occured. Error message: %s", e)

    def initializeHighLow(self):
        """Write Initial Data to the High Low Tabble."""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_DEWPOINT}', -9999, 9999);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_HUMIDITY}', -9999, 9999);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_ILLUMINANCE}', 0, 0);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_PRESSURE}', -9999, 9999);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_RAINDURATION}', 0, 0);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_RAINRATE}', 0, 0);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_SOLARRAD}', 0, 0);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_STRIKECOUNT}', 0, 0);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_STRIKEENERGY}', 0, 0);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_TEMPERATURE}', -9999, 9999);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_UV}', 0, 0);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_WINDGUST}', 0, 0);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_WINDLULL}', 0, 0);"
            )
            cursor.execute(
                f"INSERT INTO high_low(sensorid, max_day, min_day) VALUES('{COL_WINDSPEED}', 0, 0);"
            )
            self.connection.commit()

        except SQLError as e:
            _LOGGER.error("Could not Insert data in table high_low. Error: %s", e)
        except Exception as e:
            _LOGGER.error("Could write to high_low Table. Error message: %s", e)

    def dailyHousekeeping(self):
        """Clean up old data, daily."""
        try:
            # Cleanup the Pressure Table
            pres_time_point = time.time() - PRESSURE_TREND_TIMER - 60
            cursor = self.connection.cursor()
            cursor.execute(f"DELETE FROM pressure WHERE timestamp < {pres_time_point};")

            # Cleanup the Lightning Table
            strike_time_point = time.time() - STRIKE_COUNT_TIMER - 60
            cursor.execute(
                f"DELETE FROM lightning WHERE timestamp < {strike_time_point};"
            )

            # Update All Time Values values
            cursor.execute(
                f"UPDATE high_low SET max_all = max_day, max_all_time = max_day_time WHERE max_day > max_all or max_all IS NULL"
            )
            cursor.execute(
                f"UPDATE high_low SET min_all = min_day, min_all_time = min_day_time WHERE (min_day < min_all or min_all IS NULL) and min_day_time IS NOT NULL"
            )

            # Update or Reset Year Values
            cursor.execute(
                f"UPDATE high_low SET max_year = max_day, max_year_time = max_day_time WHERE (max_day > max_year or max_year IS NULL) AND strftime('%Y', 'now') = strftime('%Y', datetime(max_day_time, 'unixepoch', 'localtime'))"
            )
            cursor.execute(
                f"UPDATE high_low SET min_year = min_day, min_year_time = min_day_time WHERE ((min_day < min_year or min_year IS NULL) AND min_day_time IS NOT NULL) AND strftime('%Y', 'now') = strftime('%Y', datetime(min_day_time, 'unixepoch', 'localtime'))"
            )
            cursor.execute(
                f"UPDATE high_low SET max_year = latest, max_year_time = {time.time()}, min_year = latest, min_year_time = {time.time()} WHERE min_day <> 0 AND strftime('%Y', 'now') <> strftime('%Y', datetime(max_day_time, 'unixepoch', 'localtime'))"
            )
            cursor.execute(
                f"UPDATE high_low SET max_year = 0, max_year_time = {time.time()} WHERE min_day = 0 AND strftime('%Y', 'now') <> strftime('%Y', datetime(max_day_time, 'unixepoch', 'localtime'))"
            )

            # Update or Reset Month Values
            cursor.execute(
                f"UPDATE high_low SET max_month = max_day, max_month_time = max_day_time WHERE (max_day > max_month or max_month IS NULL) AND strftime('%m', 'now') = strftime('%m', datetime(max_day_time, 'unixepoch', 'localtime'))"
            )
            cursor.execute(
                f"UPDATE high_low SET min_month = min_day, min_month_time = min_day_time WHERE ((min_day < min_month or min_month IS NULL) AND min_day_time IS NOT NULL) AND strftime('%m', 'now') = strftime('%m', datetime(min_day_time, 'unixepoch', 'localtime'))"
            )
            cursor.execute(
                f"UPDATE high_low SET max_month = latest, max_month_time = {time.time()}, min_month = latest, min_month_time = {time.time()} WHERE min_day <> 0 AND strftime('%m', 'now') <> strftime('%m', datetime(max_day_time, 'unixepoch', 'localtime'))"
            )
            cursor.execute(
                f"UPDATE high_low SET max_month = 0, max_month_time = {time.time()} WHERE min_day = 0 AND strftime('%m', 'now') <> strftime('%m', datetime(max_day_time, 'unixepoch', 'localtime'))"
            )

            # Update or Reset Week Values
            cursor.execute(
                f"UPDATE high_low SET max_week = max_day, max_week_time = max_day_time WHERE (max_day > max_week or max_week IS NULL) AND strftime('%W', 'now') = strftime('%W', datetime(max_day_time, 'unixepoch', 'localtime'))"
            )
            cursor.execute(
                f"UPDATE high_low SET min_week = min_day, min_week_time = min_day_time WHERE ((min_day < min_week or min_week IS NULL) AND min_day_time IS NOT NULL) AND strftime('%W', 'now') = strftime('%W', datetime(min_day_time, 'unixepoch', 'localtime'))"
            )
            cursor.execute(
                f"UPDATE high_low SET max_week = latest, max_week_time = {time.time()}, min_week = latest, min_week_time = {time.time()} WHERE min_day <> 0 AND strftime('%W', 'now') <> strftime('%W', datetime(max_day_time, 'unixepoch', 'localtime'))"
            )
            cursor.execute(
                f"UPDATE high_low SET max_week = 0, max_week_time = {time.time()} WHERE min_day = 0 AND strftime('%W', 'now') <> strftime('%W', datetime(max_day_time, 'unixepoch', 'localtime'))"
            )

            # Update Yesterday Values
            cursor.execute(
                f"UPDATE high_low SET max_yday = max_day, max_yday_time = max_day_time, min_yday = min_day, min_yday_time = min_day_time"
            )

            # Reset Day High and Low values
            cursor.execute(
                f"UPDATE high_low SET max_day = latest, max_day_time = {time.time()}, min_day = latest, min_day_time = {time.time()} WHERE min_day <> 0"
            )
            cursor.execute(
                f"UPDATE high_low SET max_day = 0, max_day_time = {time.time()} WHERE min_day = 0"
            )
            self.connection.commit()

            return True

        except SQLError as e:
            _LOGGER.error("Could not perform daily housekeeping. Error: %s", e)
            return False
        except Exception as e:
            _LOGGER.error("Could not perform daily housekeeping. Error message: %s", e)
            return False
