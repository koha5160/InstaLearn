import os
import sqlite3

import gspread
import mysql.connector
import pandas as pd
from mysql.connector.errors import IntegrityError


# Have to use .commit on database connection to save changes made in script
class DB_Session_Local:
    def __init__(self):
        pass

    def __enter__(self):
        self.__connection = sqlite3.connect("instabase.db")
        self.__cursor = self.__connection.cursor()
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        self.__cursor.close()
        self.__connection.close()

    def insert(self, data: tuple):
        """Takes a list of data to be inserted into the local database

        Args:
            data (tuple): List of data for a user
        """
        try:
            self.__cursor.execute(
                """INSERT INTO accounts VALUES('{info[0]}',{info[1]},{info[2]},
                {info[3]},{info[4]},{info[5]},{info[6]},{info[7]}) """.format(
                    info=data
                )
            )
        except sqlite3.IntegrityError:
            self.__cursor.execute(
                """ UPDATE accounts SET posts={d[1]}, followers={d[2]}, following={d[3]}, private={d[4]},
        		bio_tag={d[5]}, external_url={d[6]}, verified={d[7]} WHERE username='{d[0]}'""".format(
                    d=data
                )
            )
        finally:
            self.__connection.commit()

    def backup(self):
        self.__cursor.execute("SELECT * FROM accounts")
        entries = [output for output in self.__cursor]
        with DB_Session() as db:
            for info in entries:
                db.insert(info)
        with DB_Session_Sheets() as sheet:
            sheet.insert(entries)
        self.__cursor.execute("DELETE FROM accounts")
        self.__connection.commit()
        self.__cursor.execute("vacuum")
        self.__connection.commit()

    def transfer_to_server(self):
        """Takes the entries from the local database and inserts them into the MySQL
        database then resizes the local database
        """
        self.__cursor.execute("SELECT * FROM accounts")
        with DB_Session() as db:
            for info in self.__cursor:
                db.insert(info)
            print(db.size())
        self.__cursor.execute("DELETE FROM accounts")
        self.__connection.commit()
        self.__cursor.execute("vacuum")
        self.__connection.commit()

    def transfer_to_sheet(self):
        self.__cursor.execute("SELECT * FROM accounts")
        with DB_Session_Sheets() as sheet:
            sheet.insert(self.__cursor.fetchall())
        self.__cursor.execute("DELETE FROM accounts")
        self.__connection.commit()
        self.__cursor.execute("vacuum")
        self.__connection.commit()

    def show(self):
        """Shows the entries for the account data collected
        """
        self.__cursor.execute("SELECT * FROM accounts")
        return self.__cursor.fetchall()

    def size(self):
        """Shows the number of entries for the user data and the account data
        """
        self.__cursor.execute("SELECT COUNT(*) FROM accounts")
        print(f"Accounts: {self.__cursor.fetchone()[0]}")
        self.__cursor.execute("SELECT COUNT(*) FROM users")
        print(f"Users: {self.__cursor.fetchone()[0]}")


class DB_Session_Sheets:
    def __init__(self):
        pass

    def __enter__(self):
        self.__gc = gspread.service_account(filename="credentials.json")
        self.__sh = self.__gc.open_by_key(os.environ.get("SHEET_KEY"))
        self.__worksheet = self.__sh.sheet1
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        pass

    def insert(self, data: list):
        self.__worksheet.insert_rows(data, 2)

    def show(self):
        return self.__worksheet.get_all_values()


class DB_Session:
    def __init__(self):
        pass

    def __enter__(self):
        self.__connection = mysql.connector.connect(
            host="localhost",
            user=os.environ.get("DB_USER"),
            passwd=os.environ.get("DB_PASS"),
            auth_plugin="mysql_native_password",
            database="instabase",
        )
        self.__cursor = self.__connection.cursor()
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        self.__cursor.close()
        self.__connection.close()

    # Description of table
    def _description(self) -> list:
        """Gives a description of the database table

        Returns:
            list: List of table attributes
        """
        self.__cursor.execute("DESCRIBE insta_train")
        description = [output for output in self.__cursor]
        return description

    def insert(self, data: tuple) -> None:
        """Inserts user data in database

        Args:
            data (tuple): A tuple of user information
        """
        try:
            self.__cursor.execute(
                """INSERT INTO insta_train VALUES('{info[0]}',{info[1]},{info[2]},
            {info[3]},{info[4]},{info[5]},{info[6]},{info[7]}) """.format(
                    info=data
                )
            )
        except IntegrityError:
            self.__cursor.execute(
                """ UPDATE insta_train SET posts={d[1]}, followers={d[2]}, following={d[3]}, private={d[4]}, 
                bio_tag={d[5]}, external_url={d[6]}, verified={d[7]} WHERE username='{d[0]}'""".format(
                    d=data
                )
            )
        finally:
            self.__connection.commit()

    def size(self) -> int:
        """Returns the amount of rows in the database table

        Returns:
            int: Number of rows in database table
        """
        self.__cursor.execute("SELECT COUNT(*) FROM insta_train")
        for output in self.__cursor:
            rows = output[0]
        return rows

    def query(self, users: list) -> pd.DataFrame:
        """Queries and returns user data for the list of users

        Args:
            users (list): A list of usernames

        Returns:
            pd.DataFrame: A dataframe of a table which resembles the database table 
            of the user information queried for
        """
        pd.set_option("display.max_columns", None)
        df = pd.DataFrame(
            columns=[
                "User",
                "Posts",
                "Followers",
                "Following",
                "Private",
                "Bio_Tag",
                "External_Url",
                "Verified",
            ]
        )
        for user in users:
            self.__cursor.execute(
                "SELECT * FROM insta_train WHERE username='{:s}'".format(user)
            )
            s = None
            for output in self.__cursor:
                s = output
            if s:
                df_temp = {
                    "User": s[0],
                    "Posts": s[1],
                    "Followers": s[2],
                    "Following": s[3],
                    "Private": bool(s[4]),
                    "Bio_Tag": bool(s[5]),
                    "External_Url": bool(s[6]),
                    "Verified": bool(s[7]),
                }
                df = df.append(df_temp, ignore_index=True)
            else:
                df = df.append({"User": user}, ignore_index=True)
        return df

    def query_found(self, users: list) -> pd.DataFrame:
        """Searches the database table for users

        Args:
            users (list): List of usernames to search for

        Returns:
            pd.DataFrame: Table of whether the users are in the database table
        """
        df = pd.DataFrame(columns=["User", "Found"])
        for user in users:
            self.__cursor.execute(
                "SELECT * FROM insta_train WHERE username='{:s}'".format(user)
            )
            s = None
            for output in self.__cursor:
                s = output
            if s:
                df = df.append({"User": user, "Found": True}, ignore_index=True)
            else:
                df = df.append({"User": user, "Found": False}, ignore_index=True)
        return df

    def show(self) -> list:
        """Shows all the entries in the database table

        Returns:
            list: A list of all user data within the table
        """
        self.__cursor.execute("SELECT * FROM insta_train")

        return self.__cursor.fetchall()
