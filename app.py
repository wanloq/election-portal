from flask import Flask, render_template, jsonify, request
import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG

app = Flask(__name__)
app.config.from_pyfile('config.py')

# Database connection function
def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None
